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
from typing import Callable, Dict, Iterable, List, Optional

from .aggregation import aggregate_video_findings
from .clip_embedder import ClipEmbedder
from .config import SETTINGS
from .faiss_index import FaissIndex
from .mobile_sam_segmenter import MobileSamSegmenter
from .rule_engine import evaluate as evaluate_rules
from .schemas import FrameAnalysis
from .utils import (
    collect_inputs,
    draw_overlays,
    extract_frame_records,
    imread_rgb,
    imwrite_rgb,
)
from .vlm_reasoner import VlmReasoner
from .yolo_detector import YoloDetector

logger = logging.getLogger("safetrace.pipeline")


def _safe_id(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value)
    return cleaned.strip("_") or "media"


class SafeTracePipeline:
    def __init__(
        self,
        embedder: Optional[ClipEmbedder] = None,
        index: Optional[FaissIndex] = None,
        detector: Optional[YoloDetector] = None,
        segmenter: Optional[MobileSamSegmenter] = None,
        vlm: Optional[VlmReasoner] = None,
        data_dir: str | Path | None = None,
    ) -> None:
        self.data_dir = Path(data_dir or SETTINGS.data_dir)
        self.frames_dir = self.data_dir / "frames"
        self.annotated_dir = self.data_dir / "annotated"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.frames_dir.mkdir(parents=True, exist_ok=True)

        self.embedder = embedder or ClipEmbedder()
        self.index = index or FaissIndex(
            embedder=self.embedder,
            index_path=self.data_dir / "index.faiss",
            metadata_path=self.data_dir / "metadata.json",
            embeddings_path=self.data_dir / "embeddings.npy",
        )
        self.detector = detector or YoloDetector()
        self.segmenter = segmenter or MobileSamSegmenter()
        self.vlm = vlm or VlmReasoner()
        self.last_frame_records: List[dict] = []

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
        records = self.ingest_records(inputs, fps=fps, max_frames=max_frames)
        return [Path(r["frame_path"]) for r in records]

    def ingest_records(
        self,
        inputs: Iterable[str | Path],
        fps: float | None = None,
        max_frames: int | None = None,
        media_metadata: Optional[Dict[str, dict]] = None,
    ) -> List[dict]:
        """Convert media to timestamped frame records and build the FAISS index."""
        fps = fps or SETTINGS.frame_fps
        max_frames = max_frames or SETTINGS.max_frames
        media_metadata = media_metadata or {}

        videos, images = collect_inputs(inputs)
        all_records: List[dict] = []

        for media_index, vid in enumerate(videos):
            meta = dict(media_metadata.get(str(Path(vid).resolve()), {}))
            video_id = meta.get("video_id") or f"{_safe_id(Path(vid).stem)}_{media_index:03d}"
            prefix_parts = [meta.get("vehicle_id"), video_id]
            prefix = "_".join(_safe_id(str(p)) for p in prefix_parts if p)
            frames = extract_frame_records(
                vid,
                self.frames_dir,
                fps=fps,
                max_frames=max_frames,
                prefix=prefix or None,
            )
            for record in frames:
                record.update(meta)
                record.setdefault("video_id", video_id)
                record.setdefault("filename", Path(vid).name)
                record.setdefault("original_relative_path", Path(vid).name)
            all_records.extend(frames)

        # Copy/standardize image inputs into the frames folder so the corpus
        # has one canonical location.
        for media_index, img in enumerate(images):
            meta = dict(media_metadata.get(str(Path(img).resolve()), {}))
            dst = self.frames_dir / img.name
            if str(dst.resolve()) != str(img.resolve()):
                arr = imread_rgb(img)
                imwrite_rgb(dst, arr)
            record = {
                "frame_id": dst.stem,
                "frame_path": str(dst),
                "sample_index": media_index,
                "frame_index": media_index,
                "timestamp": 0.0,
                "source_path": str(img),
                "filename": Path(img).name,
                "original_relative_path": Path(img).name,
            }
            record.update(meta)
            record.setdefault("video_id", meta.get("video_id") or dst.stem)
            all_records.append(record)

        if not all_records:
            raise ValueError("No usable frames produced from the supplied inputs.")

        self.index.build_from_frames(all_records)
        self.last_frame_records = all_records
        return all_records

    # ------------------------------------------------------------------ #
    # Analysis
    # ------------------------------------------------------------------ #
    def analyze_frame(
        self,
        frame_path: str | Path,
        score: float = 1.0,
        metadata: Optional[dict] = None,
    ) -> FrameAnalysis:
        metadata = metadata or {}
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
            ann_dir = self.annotated_dir
            ann_dir.mkdir(parents=True, exist_ok=True)
            out_path = ann_dir / f"{frame_path.stem}_annotated.jpg"
            imwrite_rgb(out_path, annotated)
            annotated_path = str(out_path)

        return FrameAnalysis(
            frame_id=str(metadata.get("frame_id") or frame_path.stem),
            frame_path=str(frame_path),
            score=float(score),
            detections=detections,
            violations=violations,
            explanation=explanation,
            annotated_path=annotated_path,
            timestamp=metadata.get("timestamp"),
            frame_index=metadata.get("frame_index"),
            video_id=metadata.get("video_id"),
            vehicle_id=metadata.get("vehicle_id"),
            metadata=metadata,
        )

    def analyze_frame_records(
        self,
        frame_records: Iterable[dict],
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> List[Dict]:
        """Analyze every sampled frame record for timeline-level summaries."""
        records = list(frame_records)
        results: List[Dict] = []
        total = len(records)
        for idx, record in enumerate(records, start=1):
            fa = self.analyze_frame(record["frame_path"], metadata=record)
            results.append(fa.to_dict())
            if progress_callback:
                progress_callback(idx, total)
        return results

    def summarize_timeline(self, frame_results: Iterable[Dict]) -> List[Dict]:
        """Aggregate full sampled-frame timelines into one summary per video."""
        grouped: Dict[str, List[Dict]] = {}
        for frame in frame_results:
            video_id = frame.get("video_id") or frame.get("metadata", {}).get("video_id") or "video"
            grouped.setdefault(str(video_id), []).append(frame)

        summaries: List[Dict] = []
        for video_id, frames in grouped.items():
            first = frames[0] if frames else {}
            meta = first.get("metadata", {})
            summaries.append(
                aggregate_video_findings(
                    frames,
                    video_id=video_id,
                    vehicle_id=first.get("vehicle_id") or meta.get("vehicle_id"),
                )
            )
        return summaries

    def analyze_query(self, query: str, k: int | None = None) -> List[Dict]:
        """Run the full pipeline for a natural-language query."""
        k = k or SETTINGS.top_k
        try:
            hits = self.index.semantic_search(query, k=k)
        except FileNotFoundError:
            logger.error("FAISS index not built. Call ingest() first.")
            return []

        results: List[FrameAnalysis] = []
        for hit in hits:
            frame_path = hit.get("representative_frame_path") or hit["frame_path"]
            fa = self.analyze_frame(frame_path, score=hit.get("score", 0.0), metadata=hit)
            results.append(fa)
        return [r.to_dict() for r in results]

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
