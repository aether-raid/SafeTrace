"""Packaging-friendly SafeTrace backend entrypoint."""
from __future__ import annotations

import argparse
import os
from pathlib import Path


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
DEFAULT_LOG_LEVEL = "info"


def load_env_file(path: Path) -> list[str]:
    loaded: list[str] = []
    if not path.is_file():
        return loaded
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        os.environ.setdefault(key, value.strip())
        loaded.append(key)
    return loaded


def apply_packaged_defaults(app_root: Path) -> None:
    os.environ.setdefault("SAFETRACE_PROJECT_ROOT", str(app_root))
    os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    os.environ.setdefault("SAFETRACE_CHAT_ENABLED", "auto")
    os.environ.setdefault("SAFETRACE_CHAT_PROVIDER", "packaged_llamacpp")
    os.environ.setdefault("SAFETRACE_CHAT_SPEED_PROFILE", "fast")
    os.environ.setdefault(
        "SAFETRACE_CHAT_MODEL_PATH",
        str(Path("models") / "chat" / "safetrace-assistant-qwen2.5-1.5b-instruct-q4.gguf"),
    )
    os.environ.setdefault("SAFETRACE_SERVE_FRONTEND", "true")
    os.environ.setdefault("SAFETRACE_FRONTEND_DIST", str(Path("frontend") / "dist"))
    os.environ.setdefault("SAFETRACE_BUILD_MODE", "prototype")
    os.environ.setdefault("SAFETRACE_RUNTIME_LAYOUT", "packaged")
    os.environ.setdefault("SAFETRACE_DATA_DIR", str(app_root / "data"))
    os.environ.setdefault("SAFETRACE_CHECKPOINTS_DIR", str(app_root / "checkpoints"))
    os.environ.setdefault("SAFETRACE_MOBILESAM_ENABLED", "auto")
    os.environ.setdefault("SAFETRACE_MOBILESAM_CHECKPOINT", str(Path("checkpoints") / "mobile_sam.pt"))
    os.environ.setdefault("SAFETRACE_VLM_ENABLED", "auto")
    os.environ.setdefault("SAFETRACE_VLM_PROVIDER", "auto")
    os.environ.setdefault("SAFETRACE_VLM_OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    os.environ.setdefault("SAFETRACE_VLM_MODEL", "llava")
    os.environ.setdefault("SAFETRACE_VLM_TIMEOUT_SECONDS", "30")
    os.environ.setdefault("SAFETRACE_VLM_MAX_FRAMES", "3")
    os.environ.setdefault("SAFETRACE_VLM_MAX_TOKENS", "180")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Start the SafeTrace local backend")
    parser.add_argument("--host", default=os.environ.get("SAFETRACE_HOST", DEFAULT_HOST))
    parser.add_argument("--port", type=int, default=int(os.environ.get("SAFETRACE_PORT", DEFAULT_PORT)))
    parser.add_argument("--log-level", default=os.environ.get("SAFETRACE_LOG_LEVEL", DEFAULT_LOG_LEVEL))
    parser.add_argument("--app-root", type=Path, default=Path.cwd())
    parser.add_argument("--env-file", type=Path, default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    app_root = args.app_root.resolve()
    env_file = args.env_file or app_root / "config" / "safetrace.env"
    load_env_file(env_file)
    apply_packaged_defaults(app_root)

    import uvicorn

    uvicorn.run(
        "src.api.server:app",
        host=args.host,
        port=args.port,
        log_level=args.log_level,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
