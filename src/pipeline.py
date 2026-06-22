"""End-to-end SafeTrace pipeline.

Public entry points:
- :class:`SafeTracePipeline.ingest` — extract frames from videos / pass-through
  images, embed them, and (re)build the FAISS index.
- :func:`SafeTracePipeline.analyze_query` — semantic search → YOLO detection →
  MobileSAM refinement → rule evaluation → optional VLM explanation, returning
  a structured JSON-friendly list.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from .clip_embedder import ClipEmbedder
from .config import SETTINGS
from .faiss_index import FaissIndex
from .mobile_sam_segmenter import MobileSamSegmenter
from .rule_engine import evaluate as evaluate_rules
from .schemas import FrameAnalysis
from .preprocessing import build_processing_metadata
from .utils import (
    collect_inputs,
    draw_overlays,
    extract_frames_with_metadata,
    imread_rgb,
    imwrite_rgb,
    is_video,
)
from .vlm_reasoner import VlmReasoner
from .yolo_detector import YoloDetector

logger = logging.getLogger("safetrace.pipeline")


class SafeTracePipeline:
    def __init__(
        self,
        embedder: Optional[ClipEmbedder] = None,
        index: Optional[FaissIndex] = None,
        detector: Optional[YoloDetector] = None,
        segmenter: Optional[MobileSamSegmenter] = None,
        vlm: Optional[VlmReasoner] = None,
    ) -> None:
        self.embedder = embedder or ClipEmbedder()
        self.index = index or FaissIndex(embedder=self.embedder)
        self.detector = detector or YoloDetector()
        self.segmenter = segmenter or MobileSamSegmenter()
        self.vlm = vlm or VlmReasoner()
        self.last_processing_metadata: Dict = {}

    # ------------------------------------------------------------------ #
    # Ingestion
    # ------------------------------------------------------------------ #
    def ingest(
        self,
        inputs: Iterable[str | Path],
        fps: float | None = None,
        max_frames: int | None = None,
    ) -> List[Path]:
        """Convert videos to frames, accept images as-is, then build the FAISS index."""
        fps = fps or SETTINGS.frame_fps
        max_frames = max_frames or SETTINGS.max_frames

        videos, images = collect_inputs(inputs)
        all_frames: List[Path] = []
        sampling_runs: List[Dict] = []

        for vid in videos:
            frames, metadata = extract_frames_with_metadata(
                vid,
                SETTINGS.frames_dir,
                fps=fps,
                max_frames=max_frames,
                max_duration_seconds=SETTINGS.max_video_duration_seconds,
            )
            all_frames.extend(frames)
            sampling_runs.append(metadata)

        # Copy/standardize image inputs into the frames folder so the corpus
        # has one canonical location.
        for img in images:
            dst = SETTINGS.frames_dir / img.name
            if str(dst.resolve()) != str(img.resolve()):
                arr = imread_rgb(img)
                imwrite_rgb(dst, arr)
            all_frames.append(dst)

        if not all_frames:
            raise ValueError("No usable frames produced from the supplied inputs.")

        index_metadata = self.index.build_from_frames(all_frames)
        self.last_processing_metadata = build_processing_metadata(
            sampled_frame_count=len(all_frames),
            sampling_strategy="fixed_fps" if videos else "image_inputs",
            fps=fps if videos else None,
            max_frames=max_frames,
            embedding_batch_size=SETTINGS.embedding_batch_size,
            embedding_window_size=SETTINGS.embedding_window_size,
            embedding_window_stride=SETTINGS.embedding_window_stride,
            embedding_pooling_strategy=SETTINGS.embedding_pooling_strategy,
            processing_window_count=len(index_metadata),
            source_video_duration_seconds=(
                max(
                    (
                        float(run["sourceVideoDurationSeconds"])
                        for run in sampling_runs
                        if run.get("sourceVideoDurationSeconds") is not None
                    ),
                    default=None,
                )
            ),
            source_video_frame_count=sum(int(run.get("sourceVideoFrameCount") or 0) for run in sampling_runs) or None,
        )
        self.last_processing_metadata["inputVideoCount"] = len(videos)
        self.last_processing_metadata["inputImageCount"] = len(images)
        self.last_processing_metadata["samplingRuns"] = sampling_runs
        return all_frames

    # ------------------------------------------------------------------ #
    # Analysis
    # ------------------------------------------------------------------ #
    def analyze_frame(self, frame_path: str | Path, score: float = 1.0) -> FrameAnalysis:
        frame_path = Path(frame_path)
        image = imread_rgb(frame_path)

        detections = self.detector.detect(image)
        detections = self.segmenter.refine(image, detections)
        violations = evaluate_rules(detections)

        explanation: Optional[str] = None
        if violations:
            try:
                explanation = self.vlm.explain_violation(image, violations)
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("VLM explanation failed: %s", exc)

        annotated_path: Optional[str] = None
        if detections:
            annotated = draw_overlays(image, detections)
            ann_dir = SETTINGS.data_dir / "annotated"
            ann_dir.mkdir(parents=True, exist_ok=True)
            out_path = ann_dir / f"{frame_path.stem}_annotated.jpg"
            imwrite_rgb(out_path, annotated)
            annotated_path = str(out_path)

        return FrameAnalysis(
            frame_id=frame_path.stem,
            frame_path=str(frame_path),
            score=float(score),
            detections=detections,
            violations=violations,
            explanation=explanation,
            annotated_path=annotated_path,
        )

    def analyze_query(self, query: str, k: int | None = None) -> List[Dict]:
        """Run the full pipeline for a natural-language query."""
        k = k or SETTINGS.top_k
        try:
            hits = self.index.semantic_search(query, k=k)
        except FileNotFoundError:
            logger.error("FAISS index not built. Call ingest() first.")
            return []

        payloads: List[Dict] = []
        for hit in hits:
            fa = self.analyze_frame(hit["frame_path"], score=hit.get("score", 0.0))
            payload = fa.to_dict()
            payload["search_metadata"] = {
                key: value
                for key, value in hit.items()
                if key not in {"frame_path", "frame_id", "score"}
            }
            if self.last_processing_metadata:
                payload["processing_metadata"] = self.last_processing_metadata
            payloads.append(payload)
        return payloads

    # Convenience: full ingest + analyze in one call.
    def run(
        self,
        inputs: Iterable[str | Path],
        query: str,
        fps: float | None = None,
        k: int | None = None,
    ) -> List[Dict]:
        # Skip re-ingestion if the index already exists and no inputs are given.
        inputs_list = list(inputs)
        if inputs_list:
            self.ingest(inputs_list, fps=fps)
        return self.analyze_query(query, k=k)


# Module-level convenience for the spec signature.
_default_pipeline: Optional[SafeTracePipeline] = None


def get_pipeline() -> SafeTracePipeline:
    global _default_pipeline
    if _default_pipeline is None:
        _default_pipeline = SafeTracePipeline()
    return _default_pipeline


def analyze_query(query: str, k: int | None = None) -> List[Dict]:
    return get_pipeline().analyze_query(query, k=k)
