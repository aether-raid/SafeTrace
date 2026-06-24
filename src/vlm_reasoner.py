"""Optional local Vision-Language Model reasoning.

SafeTrace preserves the original in-process local transformers VLM path and can
also use a local Ollama vision model when explicitly selected or when auto mode
cannot use the local provider. If no local provider is available, analysis keeps
running with deterministic rule-based explanations.
"""
from __future__ import annotations

import base64
import io
import logging
from importlib import util as importlib_util
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import urlparse

import httpx
import numpy as np
from PIL import Image

from .config import SETTINGS
from .schemas import Violation
from .utils import resolve_device

logger = logging.getLogger("safetrace.vlm")

AUTO_PROVIDER = "auto"
LOCAL_PROVIDER = "local"
OLLAMA_PROVIDER = "ollama"
RULE_BASED_PROVIDER = "rule_based"
LOCAL_VLM_HOSTS = {"127.0.0.1", "localhost", "::1"}
OLLAMA_PROVIDERS = {"ollama", "ollama_vision"}
TRANSFORMER_PROVIDERS = {"local", "legacy", "existing", "transformers", "local_transformers", "local_dir"}
VLM_PROMPT = (
    "Describe only visible safety evidence in this frame.\n"
    "Do not make legal conclusions.\n"
    "Mention uncertainty from camera angle, blur, glare, or occlusion.\n"
    "Keep answer under 90 words."
)


def _normalized_mode(value: str | None) -> str:
    raw = (value or "auto").strip().lower()
    if raw in {"0", "false", "no", "off", "disabled", "none"}:
        return "disabled"
    if raw in {"1", "true", "yes", "on", "enabled"}:
        return "enabled"
    return "auto"


def _normalized_provider(value: str | None) -> str:
    raw = (value or AUTO_PROVIDER).strip().lower()
    if raw in {"", AUTO_PROVIDER}:
        return AUTO_PROVIDER
    if raw in OLLAMA_PROVIDERS:
        return OLLAMA_PROVIDER
    if raw in TRANSFORMER_PROVIDERS:
        return LOCAL_PROVIDER
    return raw


def _fallback_explanation(violations: Sequence[Violation]) -> str:
    if not violations:
        return "Rule-based explanation: no safety violations were detected in this frame."

    lines = ["Rule-based explanation: SafeTrace flagged visible evidence for reviewer confirmation."]
    for violation in violations:
        lines.append(f"- {violation.name}: {violation.description}")
    lines.append("Confirm against the original footage, especially if blur, glare, angle, or occlusion affects the view.")
    return "\n".join(lines)


def _path_has_contents(path: Path) -> bool:
    if path.is_file():
        return True
    if not path.is_dir():
        return False
    try:
        return any(path.iterdir())
    except OSError:
        return False


def _transformers_runtime_available() -> bool:
    return importlib_util.find_spec("transformers") is not None


def _local_transformer_available(model_dir: Path) -> bool:
    return _transformers_runtime_available() and _path_has_contents(model_dir)


def is_local_vlm_base_url(base_url: str) -> bool:
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"}:
        return False
    host = (parsed.hostname or "").lower()
    return host in LOCAL_VLM_HOSTS


def _ollama_endpoint(path: str) -> str:
    base_url = SETTINGS.vlm_ollama_base_url.rstrip("/")
    return f"{base_url}/{path.lstrip('/')}"


def _ollama_model_names(payload: dict[str, Any]) -> list[str]:
    models = payload.get("models")
    if not isinstance(models, list):
        return []
    names: list[str] = []
    for model in models:
        if isinstance(model, dict) and model.get("name"):
            names.append(str(model["name"]))
    return names


def _model_name_matches(candidate: str, configured: str) -> bool:
    return candidate == configured or candidate.startswith(f"{configured}:")


def _base_details(*, mode: str, requested_provider: str) -> dict[str, Any]:
    return {
        "enabledMode": mode,
        "provider": requested_provider,
        "model": SETTINGS.vlm_model,
        "maxFrames": SETTINGS.vlm_max_frames,
        "maxTokens": SETTINGS.vlm_max_tokens,
    }


def _local_provider_status(base_details: dict[str, Any]) -> dict[str, Any]:
    model_dir = Path(SETTINGS.vlm_model_dir)
    runtime_available = _transformers_runtime_available()
    model_dir_available = _path_has_contents(model_dir)
    details = {
        **base_details,
        "selectedProvider": LOCAL_PROVIDER,
        "providerType": "local_transformers",
        "modelDir": str(model_dir),
        "runtimeAvailable": runtime_available,
        "modelDirAvailable": model_dir_available,
    }
    if not runtime_available:
        return {
            "status": "missing_runtime",
            "path": str(model_dir),
            "message": "Local transformer VLM runtime is not available.",
            "actionHint": "Install the local VLM runtime in the developer environment, or choose another local provider.",
            "details": details,
        }
    if not model_dir_available:
        return {
            "status": "unavailable",
            "path": str(model_dir),
            "message": "Local transformer VLM model directory is missing or empty.",
            "actionHint": "Place the existing local VLM snapshot at SAFETRACE_VLM_DIR, or use rule-based fallback.",
            "details": details,
        }
    return {
        "status": "available",
        "path": str(model_dir),
        "message": "VLM available via local provider.",
        "actionHint": None,
        "details": details,
    }


def _ollama_provider_status(base_details: dict[str, Any]) -> dict[str, Any]:
    base_url = SETTINGS.vlm_ollama_base_url.rstrip("/")
    details = {
        **base_details,
        "selectedProvider": OLLAMA_PROVIDER,
        "providerType": "ollama_vision",
        "baseUrl": base_url,
    }
    if not is_local_vlm_base_url(base_url):
        return {
            "status": "unavailable",
            "message": "VLM provider must point to a local Ollama runtime.",
            "actionHint": "Use SAFETRACE_VLM_OLLAMA_BASE_URL=http://127.0.0.1:11434.",
            "details": details,
        }
    try:
        response = httpx.get(f"{base_url}/api/tags", timeout=1.5)
        response.raise_for_status()
    except Exception:
        return {
            "status": "missing_runtime",
            "message": "VLM unavailable because Ollama is not reachable.",
            "actionHint": "Start Ollama locally only when SAFETRACE_VLM_PROVIDER=ollama or when using Ollama in auto mode.",
            "details": {**details, "runtimeAvailable": False},
        }

    try:
        tags_payload = response.json()
    except Exception:
        tags_payload = {}
    names = _ollama_model_names(tags_payload)
    model_available = any(_model_name_matches(name, SETTINGS.vlm_model) for name in names)
    if not model_available:
        return {
            "status": "unavailable",
            "message": f"Ollama is reachable, but the configured VLM model '{SETTINGS.vlm_model}' was not listed.",
            "actionHint": "Install a local Ollama vision model such as llava or set SAFETRACE_VLM_MODEL.",
            "details": {**details, "runtimeAvailable": True, "availableModels": names},
        }
    return {
        "status": "available",
        "message": f"VLM available via Ollama provider using '{SETTINGS.vlm_model}'.",
        "actionHint": None,
        "details": {**details, "runtimeAvailable": True, "availableModels": names},
    }


def _with_auto_summary(
    payload: dict[str, Any],
    *,
    requested_provider: str,
    selected_provider: str,
    available_providers: list[str],
    local_status: dict[str, Any],
    ollama_status: dict[str, Any],
) -> dict[str, Any]:
    details = {
        **payload.get("details", {}),
        "provider": requested_provider,
        "selectedProvider": selected_provider,
        "availableProviders": available_providers,
        "providers": {
            "local": {
                "status": local_status.get("status"),
                "message": local_status.get("message"),
                "details": local_status.get("details"),
            },
            "ollama": {
                "status": ollama_status.get("status"),
                "message": ollama_status.get("message"),
                "details": ollama_status.get("details"),
            },
        },
    }
    return {**payload, "details": details}


def vlm_status_payload(*, timeout_seconds: float = 1.5) -> dict[str, Any]:  # noqa: ARG001
    """Return a lightweight local VLM status payload without loading a model."""
    mode = _normalized_mode(getattr(SETTINGS, "vlm_enabled", "auto"))
    requested_provider = _normalized_provider(getattr(SETTINGS, "vlm_provider", AUTO_PROVIDER))
    base_details = _base_details(mode=mode, requested_provider=requested_provider)

    if mode == "disabled":
        return {
            "status": "disabled",
            "message": "Enhanced VLM is disabled. Rule-based explanations remain available.",
            "actionHint": "Set SAFETRACE_VLM_ENABLED=auto or enabled to use a local VLM.",
            "details": {
                **base_details,
                "selectedProvider": RULE_BASED_PROVIDER,
                "availableProviders": [],
            },
        }

    if requested_provider == LOCAL_PROVIDER:
        return _local_provider_status(base_details)
    if requested_provider == OLLAMA_PROVIDER:
        return _ollama_provider_status(base_details)
    if requested_provider != AUTO_PROVIDER:
        return {
            "status": "unavailable",
            "message": f"Unsupported local VLM provider '{requested_provider}'.",
            "actionHint": "Set SAFETRACE_VLM_PROVIDER=auto, local, or ollama.",
            "details": {**base_details, "selectedProvider": RULE_BASED_PROVIDER, "availableProviders": []},
        }

    local_status = _local_provider_status(base_details)
    ollama_status = _ollama_provider_status(base_details)
    available_providers = [
        provider
        for provider, status in (
            (LOCAL_PROVIDER, local_status),
            (OLLAMA_PROVIDER, ollama_status),
        )
        if status.get("status") == "available"
    ]
    if local_status.get("status") == "available":
        return _with_auto_summary(
            {
                **local_status,
                "message": "VLM available via local provider.",
            },
            requested_provider=AUTO_PROVIDER,
            selected_provider=LOCAL_PROVIDER,
            available_providers=available_providers,
            local_status=local_status,
            ollama_status=ollama_status,
        )
    if ollama_status.get("status") == "available":
        return _with_auto_summary(
            {
                **ollama_status,
                "message": "VLM available via Ollama provider.",
            },
            requested_provider=AUTO_PROVIDER,
            selected_provider=OLLAMA_PROVIDER,
            available_providers=available_providers,
            local_status=local_status,
            ollama_status=ollama_status,
        )
    return _with_auto_summary(
        {
            "status": "unavailable",
            "message": "VLM unavailable. SafeTrace will use rule-based explanations.",
            "actionHint": "Place the existing local VLM snapshot at SAFETRACE_VLM_DIR, or explicitly configure local Ollama.",
            "details": base_details,
        },
        requested_provider=AUTO_PROVIDER,
        selected_provider=RULE_BASED_PROVIDER,
        available_providers=available_providers,
        local_status=local_status,
        ollama_status=ollama_status,
    )


class VlmReasoner:
    def __init__(
        self,
        model_dir: str | Path | None = None,
        device: str | None = None,
        enabled: bool | None = None,
    ) -> None:
        self.device = resolve_device(device or SETTINGS.device)
        self.model_dir = Path(model_dir or SETTINGS.vlm_model_dir)
        self.requested_provider = _normalized_provider(getattr(SETTINGS, "vlm_provider", AUTO_PROVIDER))
        self.provider = RULE_BASED_PROVIDER
        self.enabled_mode = _normalized_mode(getattr(SETTINGS, "vlm_enabled", "auto"))
        request_enabled = SETTINGS.enable_vlm if enabled is None else enabled
        self.enabled = bool(request_enabled) and self.enabled_mode != "disabled"
        self._model = None
        self._processor = None
        self._loaded = False
        self.last_explanation_source = RULE_BASED_PROVIDER

        if not self.enabled:
            logger.info("VLM disabled by request or configuration.")
            return

        selected_provider = self._select_provider()
        if selected_provider == OLLAMA_PROVIDER:
            if not is_local_vlm_base_url(SETTINGS.vlm_ollama_base_url):
                logger.warning("VLM Ollama base URL is not local; using rule-based fallback.")
                self.enabled = False
                return
            self.provider = OLLAMA_PROVIDER
            self._loaded = True
            return

        if selected_provider == LOCAL_PROVIDER:
            self.provider = LOCAL_PROVIDER
            self._load_transformer_provider()
            return

        logger.info("No local VLM provider available; using rule-based fallback.")
        self.enabled = False

    # ------------------------------------------------------------------ #
    def _select_provider(self) -> str:
        if self.requested_provider == LOCAL_PROVIDER:
            return LOCAL_PROVIDER
        if self.requested_provider == OLLAMA_PROVIDER:
            return OLLAMA_PROVIDER
        if self.requested_provider != AUTO_PROVIDER:
            logger.warning("Unsupported VLM provider %s; using rule-based fallback.", self.requested_provider)
            return RULE_BASED_PROVIDER
        if _local_transformer_available(self.model_dir):
            return LOCAL_PROVIDER
        base_details = _base_details(mode=self.enabled_mode, requested_provider=AUTO_PROVIDER)
        if _ollama_provider_status(base_details).get("status") == "available":
            return OLLAMA_PROVIDER
        return RULE_BASED_PROVIDER

    def _load_transformer_provider(self) -> None:
        if not _path_has_contents(self.model_dir):
            logger.warning("VLM model dir empty/missing at %s; disabling.", self.model_dir)
            self.enabled = False
            return
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoProcessor

            logger.info("Loading VLM from %s on %s", self.model_dir, self.device)
            self._processor = AutoProcessor.from_pretrained(
                str(self.model_dir), trust_remote_code=True, local_files_only=True
            )
            self._model = AutoModelForCausalLM.from_pretrained(
                str(self.model_dir),
                trust_remote_code=True,
                local_files_only=True,
                torch_dtype=torch.float16 if self.device == "cuda" else torch.float32,
            ).to(self.device).eval()
            self._loaded = True
        except Exception as exc:  # pragma: no cover - optional path
            logger.warning("Failed to load local VLM (%s); falling back to rule-based explanation.", exc)
            self.enabled = False
            self.provider = RULE_BASED_PROVIDER

    def explain_violation(self, image: np.ndarray, violations: Sequence[Violation]) -> str:
        self.last_explanation_source = RULE_BASED_PROVIDER
        if not self.enabled or not self._loaded:
            return _fallback_explanation(violations)

        if self.provider == OLLAMA_PROVIDER:
            return self._explain_with_ollama(image, violations)
        if self.provider == LOCAL_PROVIDER:
            return self._explain_with_transformers(image, violations)
        return _fallback_explanation(violations)

    def _prompt_for(self, violations: Sequence[Violation]) -> str:
        names = ", ".join(v.name for v in violations) or "no obvious violations"
        return f"{VLM_PROMPT}\nPotential SafeTrace findings to inspect: {names}."

    def _image_base64(self, image: np.ndarray) -> str:
        pil = image if isinstance(image, Image.Image) else Image.fromarray(image)
        with io.BytesIO() as buffer:
            pil.convert("RGB").save(buffer, format="JPEG", quality=88)
            return base64.b64encode(buffer.getvalue()).decode("ascii")

    def _explain_with_ollama(self, image: np.ndarray, violations: Sequence[Violation]) -> str:
        try:
            response = httpx.post(
                _ollama_endpoint("/api/generate"),
                json={
                    "model": SETTINGS.vlm_model,
                    "prompt": self._prompt_for(violations),
                    "images": [self._image_base64(image)],
                    "stream": False,
                    "options": {
                        "num_predict": SETTINGS.vlm_max_tokens,
                        "temperature": 0.1,
                    },
                },
                timeout=SETTINGS.vlm_timeout_seconds,
            )
            response.raise_for_status()
            text = str(response.json().get("response") or "").strip()
            if text:
                self.last_explanation_source = "vlm_ollama"
                return text
        except Exception as exc:  # pragma: no cover - exercised by fallback tests
            logger.warning("Ollama VLM generation failed (%s); using rule-based fallback.", exc)
        return _fallback_explanation(violations)

    def _explain_with_transformers(self, image: np.ndarray, violations: Sequence[Violation]) -> str:
        try:
            import torch

            pil = image if isinstance(image, Image.Image) else Image.fromarray(image)
            inputs = self._processor(text=self._prompt_for(violations), images=pil, return_tensors="pt").to(self.device)
            with torch.inference_mode():
                output_ids = self._model.generate(
                    **inputs, max_new_tokens=SETTINGS.vlm_max_tokens, do_sample=False
                )
            text = self._processor.batch_decode(
                output_ids, skip_special_tokens=True, clean_up_tokenization_spaces=True
            )[0].strip()
            if text:
                self.last_explanation_source = "vlm_local"
                return text
        except Exception as exc:  # pragma: no cover
            logger.warning("Local VLM generation failed (%s); using rule-based fallback.", exc)
        return _fallback_explanation(violations)
