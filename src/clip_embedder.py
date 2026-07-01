"""SigLIP / CLIP image+text embedder.

Loads a local HuggingFace model directory (offline) and produces L2-normalized
embeddings suitable for cosine-similarity search via FAISS ``IndexFlatIP``.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable, List, Sequence

import numpy as np
import torch
from PIL import Image

from .config import SETTINGS
from .preprocessing import build_frame_windows, normalize_pooling_strategy, pool_embeddings
from .utils import imread_rgb, resolve_device, write_json

logger = logging.getLogger("safetrace.embedder")


def _l2_normalize(x: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(x, axis=-1, keepdims=True)
    return x / np.clip(norm, 1e-12, None)


def _feature_tensor(output):
    """Extract a tensor from common HuggingFace feature output shapes."""
    if isinstance(output, torch.Tensor):
        return output
    for attr in ("image_embeds", "text_embeds", "pooler_output"):
        value = getattr(output, attr, None)
        if isinstance(value, torch.Tensor):
            return value
    value = getattr(output, "last_hidden_state", None)
    if isinstance(value, torch.Tensor):
        return value.mean(dim=1)
    if isinstance(output, (tuple, list)) and output and isinstance(output[0], torch.Tensor):
        return output[0]
    raise TypeError(f"Unsupported embedding output type: {type(output)}")


class ClipEmbedder:
    """Wraps a local SigLIP (default) or CLIP model.

    The class auto-detects which HuggingFace AutoClass to use based on the
    config files present in the local model directory.
    """

    def __init__(
        self,
        model_dir: str | Path | None = None,
        device: str | None = None,
        batch_size: int | None = None,
    ) -> None:
        self.model_dir = Path(model_dir or SETTINGS.siglip_model_dir)
        self.device = resolve_device(device or SETTINGS.device)
        self.batch_size = batch_size or SETTINGS.embedding_batch_size

        if not self.model_dir.exists():
            raise FileNotFoundError(
                f"Embedding model directory not found: {self.model_dir}. "
                "Place a local SigLIP/CLIP model snapshot there for offline use."
            )

        from transformers import AutoModel, AutoProcessor

        logger.info("Loading embedding model from %s on %s", self.model_dir, self.device)
        self.processor = AutoProcessor.from_pretrained(str(self.model_dir), local_files_only=True)
        self.model = AutoModel.from_pretrained(str(self.model_dir), local_files_only=True)
        self.model.to(self.device).eval()

    # ------------------------------------------------------------------ #
    # Image embeddings
    # ------------------------------------------------------------------ #
    @torch.inference_mode()
    def embed_images(self, images: Sequence[np.ndarray | str | Path]) -> np.ndarray:
        if not images:
            return np.zeros((0, self._dim()), dtype=np.float32)

        out: List[np.ndarray] = []
        for start in range(0, len(images), self.batch_size):
            batch = images[start : start + self.batch_size]
            pil_batch = [self._to_pil(x) for x in batch]
            inputs = self.processor(images=pil_batch, return_tensors="pt")
            inputs = {k: v.to(self.device) for k, v in inputs.items()}
            feats = _feature_tensor(self.model.get_image_features(**inputs))
            out.append(feats.detach().cpu().float().numpy())
        arr = np.concatenate(out, axis=0)
        return _l2_normalize(arr).astype(np.float32)

    @torch.inference_mode()
    def embed_text(self, texts: str | Iterable[str]) -> np.ndarray:
        if isinstance(texts, str):
            texts = [texts]
        texts = list(texts)
        if not texts:
            return np.zeros((0, self._dim()), dtype=np.float32)

        # SigLIP processors expect padding="max_length"; CLIP works with True.
        try:
            inputs = self.processor(
                text=texts, return_tensors="pt", padding="max_length", truncation=True
            )
        except Exception:
            inputs = self.processor(
                text=texts, return_tensors="pt", padding=True, truncation=True
            )
        inputs = {k: v.to(self.device) for k, v in inputs.items()}
        feats = _feature_tensor(self.model.get_text_features(**inputs))
        arr = feats.detach().cpu().float().numpy()
        return _l2_normalize(arr).astype(np.float32)

    # ------------------------------------------------------------------ #
    # Persistence helpers
    # ------------------------------------------------------------------ #
    def build_corpus(
        self,
        frame_paths: Sequence[Path],
        embeddings_path: Path | None = None,
        metadata_path: Path | None = None,
    ) -> tuple[np.ndarray, list[dict]]:
        """Embed frames, optionally pool frame windows, persist embeddings + metadata."""
        embeddings_path = Path(embeddings_path or SETTINGS.embeddings_path)
        metadata_path = Path(metadata_path or SETTINGS.metadata_path)
        pooling_strategy = normalize_pooling_strategy(SETTINGS.embedding_pooling_strategy)
        window_size = max(int(SETTINGS.embedding_window_size or 1), 1)
        window_stride = max(int(SETTINGS.embedding_window_stride or 1), 1)

        logger.info("Embedding %d frames", len(frame_paths))
        frame_embeddings = self.embed_images([str(p) for p in frame_paths])
        windows = build_frame_windows(frame_paths, window_size=window_size, stride=window_stride)
        embeddings = pool_embeddings(frame_embeddings, windows, strategy=pooling_strategy)

        metadata = [
            {
                "frame_id": Path(window.representative_frame_path).stem,
                "frame_path": window.representative_frame_path,
                "index": i,
                "window_id": window.window_id,
                "window": window.to_metadata(),
                "pooling_strategy": pooling_strategy,
            }
            for i, window in enumerate(windows)
        ]

        embeddings_path.parent.mkdir(parents=True, exist_ok=True)
        np.save(embeddings_path, embeddings)
        write_json(metadata_path, metadata)
        logger.info("Wrote %s and %s", embeddings_path, metadata_path)
        return embeddings, metadata

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #
    def _dim(self) -> int:
        cfg = getattr(self.model, "config", None)
        return int(getattr(cfg, "projection_dim", 512) or 512)

    @staticmethod
    def _to_pil(x) -> Image.Image:
        if isinstance(x, Image.Image):
            return x.convert("RGB")
        if isinstance(x, (str, Path)):
            return Image.fromarray(imread_rgb(x))
        if isinstance(x, np.ndarray):
            return Image.fromarray(x)
        raise TypeError(f"Unsupported image type: {type(x)}")
