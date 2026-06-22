"""FAISS vector store for SafeTrace.

Uses ``IndexFlatIP`` with L2-normalized vectors for cosine similarity.
Embeddings, metadata, and the index file all live under ``data/`` for
fully offline reuse.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional, Sequence

import faiss
import numpy as np

from .clip_embedder import ClipEmbedder
from .config import SETTINGS
from .utils import read_json, write_json

logger = logging.getLogger("safetrace.faiss")


class FaissIndex:
    def __init__(
        self,
        embedder: Optional[ClipEmbedder] = None,
        index_path: Path | None = None,
        metadata_path: Path | None = None,
        embeddings_path: Path | None = None,
    ) -> None:
        self.index_path = Path(index_path or SETTINGS.index_path)
        self.metadata_path = Path(metadata_path or SETTINGS.metadata_path)
        self.embeddings_path = Path(embeddings_path or SETTINGS.embeddings_path)
        self._embedder = embedder
        self.index: Optional[faiss.Index] = None
        self.metadata: List[dict] = []

    # ------------------------------------------------------------------ #
    # Build / load / save
    # ------------------------------------------------------------------ #
    def build(self, embeddings: np.ndarray, metadata: Sequence[dict]) -> None:
        if embeddings.ndim != 2 or embeddings.size == 0:
            raise ValueError("Embeddings must be a non-empty 2-D array.")
        dim = embeddings.shape[1]
        index = faiss.IndexFlatIP(dim)
        index.add(embeddings.astype(np.float32))
        self.index = index
        self.metadata = list(metadata)
        logger.info("Built FAISS IndexFlatIP with %d vectors (dim=%d)", index.ntotal, dim)

    def save(self) -> None:
        if self.index is None:
            raise RuntimeError("Cannot save: no index in memory.")
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self.index, str(self.index_path))
        write_json(self.metadata_path, self.metadata)
        logger.info("Saved FAISS index → %s", self.index_path)

    def load(self) -> None:
        if not self.index_path.exists():
            raise FileNotFoundError(f"FAISS index not found: {self.index_path}")
        if not self.metadata_path.exists():
            raise FileNotFoundError(f"Metadata not found: {self.metadata_path}")
        self.index = faiss.read_index(str(self.index_path))
        self.metadata = read_json(self.metadata_path)
        logger.info("Loaded FAISS index with %d vectors", self.index.ntotal)

    def build_from_frames(self, frame_paths: Sequence[Path]) -> list[dict]:
        if self._embedder is None:
            self._embedder = ClipEmbedder()
        embs, meta = self._embedder.build_corpus(frame_paths)
        self.build(embs, meta)
        self.save()
        return meta

    # ------------------------------------------------------------------ #
    # Search
    # ------------------------------------------------------------------ #
    def semantic_search(self, query: str, k: int = 5) -> List[dict]:
        """Encode a text query and return top-k metadata records with scores."""
        if self.index is None:
            self.load()
        if self._embedder is None:
            self._embedder = ClipEmbedder()
        if not self.metadata:
            return []

        q = self._embedder.embed_text(query)
        k = max(1, min(k, self.index.ntotal))
        scores, idxs = self.index.search(q.astype(np.float32), k)
        results: List[dict] = []
        for score, idx in zip(scores[0], idxs[0]):
            if idx < 0 or idx >= len(self.metadata):
                continue
            entry = dict(self.metadata[idx])
            entry["score"] = float(score)
            results.append(entry)
        return results
