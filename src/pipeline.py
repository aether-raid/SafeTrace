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
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .clip_embedder import ClipEmbedder
from .config import SETTINGS
from .faiss_index import FaissIndex
from .lightweight_vlm_worker_client import LightweightVlmWorkerReasoner
from .mobile_sam_segmenter import MobileSamSegmenter
from .mobile_sam_worker_client import MobileSamWorkerSegmenter
from .rule_engine import evaluate as evaluate_rules
from .safe_frame_ranking import RankedFrameCandidate, parse_query_intent, score_frame_for_safe_mode, select_ranked_frames
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
from .vlm_reasoner import RuleBasedReasoner, VlmReasoner
from .yolo_detector import YoloDetector

logger = logging.getLogger("safetrace.pipeline")


def _disabled_mode(value: str | None) -> bool:
    return (value or "").strip().lower() in {"0", "false", "no", "off", "disabled", "none"}


def _analysis_safe_mode() -> bool:
    return bool(getattr(SETTINGS, "analysis_safe_mode", False))


def _safe_mode_allows_mobile_sam() -> bool:
    return _analysis_safe_mode() and bool(getattr(SETTINGS, "safe_mode_allow_mobilesam", False))


def _mobile_sam_worker_enabled() -> bool:
    return bool(getattr(SETTINGS, "mobile_sam_worker_enabled", False))


def _lightweight_vlm_worker_enabled() -> bool:
    return bool(getattr(SETTINGS, "lightweight_vlm_worker_enabled", False))


class CoarseMaskSegmenter:
    """Fast fallback segmenter that preserves detector-provided coarse masks."""

    available = False

    def refine(self, image, detections):  # noqa: ARG002
        for detection in detections:
            if detection.refined_mask is None and detection.coarse_mask is not None:
                detection.refined_mask = detection.coarse_mask
        return detections


def _mobile_sam_runtime_requested() -> bool:
    if _analysis_safe_mode():
        return _safe_mode_allows_mobile_sam() and not _disabled_mode(
            getattr(SETTINGS, "mobile_sam_enabled", "disabled")
        )
    return not _disabled_mode(getattr(SETTINGS, "mobile_sam_enabled", "disabled"))


def _vlm_runtime_requested() -> bool:
    if _analysis_safe_mode():
        return False
    mode = str(getattr(SETTINGS, "vlm_enabled", "auto") or "").strip().lower()
    return bool(SETTINGS.enable_vlm) and not _disabled_mode(mode)


def _lightweight_vlm_worker_runtime_requested() -> bool:
    if not _analysis_safe_mode():
        return False
    mode = str(getattr(SETTINGS, "vlm_enabled", "auto") or "").strip().lower()
    profile = str(getattr(SETTINGS, "vlm_profile", "rule_based") or "rule_based").strip().lower()
    return bool(
        SETTINGS.enable_vlm
        and _lightweight_vlm_worker_enabled()
        and not _disabled_mode(mode)
        and profile == "lightweight_256m"
    )


def _profiled_explanation_source(source: Optional[str]) -> Optional[str]:
    if source != "vlm_local":
        return source
    profile = str(getattr(SETTINGS, "vlm_profile", "rule_based") or "rule_based").strip().lower()
    if profile == "lightweight_256m":
        return "vlm_lightweight"
    if profile == "enhanced_2b":
        return "vlm_enhanced"
    return source


class SafeTracePipeline:
    def __init__(
        self,
        embedder: Optional[ClipEmbedder] = None,
        index: Optional[FaissIndex] = None,
        detector: Optional[YoloDetector] = None,
        segmenter: Optional[MobileSamSegmenter] = None,
        vlm: Optional[VlmReasoner] = None,
    ) -> None:
        self.safe_mode = _analysis_safe_mode()
        safe_mode_mobile_sam_allowed = _safe_mode_allows_mobile_sam()
        mobile_sam_requested = _mobile_sam_runtime_requested()
        mobile_sam_worker_enabled = bool(mobile_sam_requested and _mobile_sam_worker_enabled())
        lightweight_vlm_worker_requested = _lightweight_vlm_worker_runtime_requested()
        self.component_diagnostics: Dict = {
            "safeMode": self.safe_mode,
            "device": "cpu" if self.safe_mode else SETTINGS.device,
            "requestedVisualExplanationMode": getattr(SETTINGS, "vlm_profile", "rule_based"),
            "effectiveExplanationMode": (
                "lightweight_256m"
                if lightweight_vlm_worker_requested
                else
                "rule_based_with_mobilesam"
                if self.safe_mode and mobile_sam_requested
                else "rule_based"
                if self.safe_mode or not _vlm_runtime_requested()
                else getattr(SETTINGS, "vlm_profile", "rule_based")
            ),
            "vlmRequested": bool(getattr(SETTINGS, "enable_vlm", False)) and getattr(SETTINGS, "vlm_profile", "rule_based") != "rule_based",
            "vlmEffectiveEnabled": bool(_vlm_runtime_requested() or lightweight_vlm_worker_requested),
            "vlmAttempted": False,
            "vlmLoaded": False,
            "lightweightVlmWorkerEnabled": lightweight_vlm_worker_requested,
            "lightweightVlmWorkerTimeoutSeconds": float(getattr(SETTINGS, "lightweight_vlm_worker_timeout_seconds", 60.0) or 60.0),
            "lightweightVlmWorkerAttempted": False,
            "lightweightVlmWorkerSucceeded": False,
            "lightweightVlmWorkerTimedOut": False,
            "lightweightVlmWorkerExitCode": None,
            "lightweightVlmFallbackReason": None,
            "lightweightVlmExplanationSource": "disabled" if not lightweight_vlm_worker_requested else "rule_based",
            "safeModeMobileSamAllowed": safe_mode_mobile_sam_allowed,
            "mobileSamRequested": mobile_sam_requested,
            "mobileSamAttempted": False,
            "mobileSamLoaded": False,
            "mobileSamFallbackReason": None,
            "mobileSamWorkerEnabled": mobile_sam_worker_enabled,
            "mobileSamWorkerTimeoutSeconds": float(getattr(SETTINGS, "mobile_sam_worker_timeout_seconds", 60.0) or 60.0),
            "mobileSamWorkerAttempted": False,
            "mobileSamWorkerSucceeded": False,
            "mobileSamWorkerTimedOut": False,
            "mobileSamWorkerExitCode": None,
            "mobileSamRefinementSource": "disabled",
            "embeddingRequested": not self.safe_mode,
            "embeddingLoaded": False,
            "detectorRequested": True,
            "detectorLoaded": False,
            "detectorCheckpointUsed": None,
            "currentPipelineStage": "initializing",
            "stageTimings": {},
            "safeFrameRankingEnabled": self.safe_mode,
            "safeFrameRankingStrategy": "object_rule_temporal" if self.safe_mode else None,
        }
        self._stage_started_at: Optional[float] = None
        self._active_stage: Optional[str] = None
        self._mark_stage("initializing")

        self.embedder = embedder
        self.index = index
        if not self.safe_mode:
            self._mark_stage("embedding_model_load")
            self.embedder = self.embedder or ClipEmbedder()
            self.component_diagnostics["embeddingLoaded"] = True
            self.index = self.index or FaissIndex(embedder=self.embedder)

        self._mark_stage("detector_load")
        self.detector = detector or YoloDetector()
        self.component_diagnostics["detectorLoaded"] = True
        checkpoint = getattr(self.detector, "checkpoint", None)
        self.component_diagnostics["detectorCheckpointUsed"] = str(checkpoint) if checkpoint else None

        self._mark_stage("segmentation_setup")
        self._safe_mode_mobile_sam_segmenter = None
        if self.safe_mode:
            # Safe Mode ranking must remain lightweight; MobileSAM is lazy-loaded
            # only for already-selected evidence frames when explicitly allowed.
            self.segmenter = CoarseMaskSegmenter()
            self._safe_mode_mobile_sam_segmenter = segmenter
        else:
            self.segmenter = segmenter or (MobileSamSegmenter() if mobile_sam_requested else CoarseMaskSegmenter())
            self.component_diagnostics["mobileSamLoaded"] = bool(getattr(self.segmenter, "available", False))

        self._mark_stage("explanation_setup")
        if vlm is not None:
            self.vlm = vlm
        elif lightweight_vlm_worker_requested:
            self.vlm = LightweightVlmWorkerReasoner(device="cpu")
        elif _vlm_runtime_requested():
            self.vlm = VlmReasoner()
        else:
            self.vlm = RuleBasedReasoner()
        self.component_diagnostics["vlmLoaded"] = (
            bool(getattr(self.vlm, "enabled", False))
            and getattr(self.vlm, "provider", "rule_based") not in {"rule_based", "vlm_lightweight_worker"}
        )
        self.component_diagnostics["effectiveExplanationMode"] = (
            "lightweight_256m"
            if lightweight_vlm_worker_requested and bool(getattr(self.vlm, "enabled", False))
            else
            _profiled_explanation_source("vlm_local")
            if self.component_diagnostics["vlmLoaded"]
            else "rule_based"
        )
        self._vlm_explanations_remaining = max(0, int(getattr(SETTINGS, "vlm_max_frames", 0) or 0))
        self.last_processing_metadata: Dict = {}
        self._finish_active_stage()

    def _selected_frame_mobile_sam_segmenter(self):
        if self._safe_mode_mobile_sam_segmenter is None:
            if _mobile_sam_worker_enabled():
                self._safe_mode_mobile_sam_segmenter = MobileSamWorkerSegmenter(device="cpu")
            else:
                self._safe_mode_mobile_sam_segmenter = MobileSamSegmenter(device="cpu")
        return self._safe_mode_mobile_sam_segmenter

    def _merge_mobile_sam_diagnostics(self, segmenter) -> None:
        diagnostics = dict(getattr(segmenter, "last_diagnostics", {}) or {})
        if diagnostics:
            self.component_diagnostics.update(diagnostics)
        if diagnostics.get("mobileSamWorkerEnabled"):
            self.component_diagnostics["mobileSamLoaded"] = False
            self.component_diagnostics["mobileSamFallbackReason"] = diagnostics.get("mobileSamFallbackReason")
            if diagnostics.get("mobileSamWorkerSucceeded"):
                self.component_diagnostics["effectiveExplanationMode"] = "rule_based_with_mobilesam"
            else:
                self.component_diagnostics["effectiveExplanationMode"] = "rule_based"
            return
        if bool(getattr(segmenter, "available", False)):
            self.component_diagnostics["mobileSamLoaded"] = True
            self.component_diagnostics["mobileSamRefinementSource"] = "worker" if diagnostics.get("mobileSamWorkerSucceeded") else "fallback"

    def _merge_lightweight_vlm_diagnostics(self) -> None:
        diagnostics = dict(getattr(self.vlm, "last_diagnostics", {}) or {})
        if not diagnostics:
            return
        self.component_diagnostics.update(diagnostics)
        if diagnostics.get("lightweightVlmWorkerEnabled"):
            self.component_diagnostics["vlmLoaded"] = False
            self.component_diagnostics["vlmAttempted"] = bool(diagnostics.get("lightweightVlmWorkerAttempted"))
            if diagnostics.get("lightweightVlmWorkerSucceeded"):
                self.component_diagnostics["effectiveExplanationMode"] = "lightweight_256m"
            elif self.component_diagnostics.get("mobileSamWorkerSucceeded") or self.component_diagnostics.get("mobileSamLoaded"):
                self.component_diagnostics["effectiveExplanationMode"] = "rule_based_with_mobilesam"
            else:
                self.component_diagnostics["effectiveExplanationMode"] = "rule_based"

    def _refine_selected_safe_mode_frame(self, image, detections):
        if not self.safe_mode or not _mobile_sam_runtime_requested() or not detections:
            return detections
        self.component_diagnostics["mobileSamAttempted"] = True
        self._mark_stage("selected_mobilesam_refine")
        try:
            segmenter = self._selected_frame_mobile_sam_segmenter()
            if not bool(getattr(segmenter, "available", False)):
                self.component_diagnostics["mobileSamLoaded"] = False
                self._merge_mobile_sam_diagnostics(segmenter)
                self.component_diagnostics["mobileSamFallbackReason"] = (
                    self.component_diagnostics.get("mobileSamFallbackReason") or "unavailable"
                )
                self.component_diagnostics["mobileSamRefinementSource"] = "fallback"
                return CoarseMaskSegmenter().refine(image, detections)
            refined = segmenter.refine(image, detections)
            self._merge_mobile_sam_diagnostics(segmenter)
            if not self.component_diagnostics.get("mobileSamWorkerEnabled"):
                self.component_diagnostics["mobileSamLoaded"] = True
                self.component_diagnostics["effectiveExplanationMode"] = "rule_based_with_mobilesam"
            elif self.component_diagnostics.get("mobileSamWorkerSucceeded"):
                self.component_diagnostics["effectiveExplanationMode"] = "rule_based_with_mobilesam"
            return refined
        except Exception as exc:  # pragma: no cover - optional runtime safety net
            logger.warning("MobileSAM selected-frame refinement failed: %s", exc)
            self.component_diagnostics["mobileSamLoaded"] = False
            self.component_diagnostics["mobileSamFallbackReason"] = type(exc).__name__
            self.component_diagnostics["mobileSamRefinementSource"] = "fallback"
            return CoarseMaskSegmenter().refine(image, detections)

    def _mark_stage(self, stage: str) -> None:
        now = time.perf_counter()
        if self._active_stage is not None and self._stage_started_at is not None:
            timings = self.component_diagnostics.setdefault("stageTimings", {})
            timings[self._active_stage] = timings.get(self._active_stage, 0.0) + (now - self._stage_started_at)
        self._active_stage = stage
        self._stage_started_at = now
        self.component_diagnostics["currentPipelineStage"] = stage

    def _finish_active_stage(self) -> None:
        if self._active_stage is None:
            return
        self._mark_stage("idle")

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

        self._mark_stage("frame_sampling")
        all_frames, sampling_runs, input_counts = self._collect_input_frames(inputs, fps=fps, max_frames=max_frames)

        if not all_frames:
            raise ValueError("No usable frames produced from the supplied inputs.")

        if self.index is None:
            raise RuntimeError("Embedding index is unavailable in safe analysis mode.")

        self._mark_stage("embedding_build")
        index_metadata = self.index.build_from_frames(all_frames)
        self.component_diagnostics["embeddingLoaded"] = True
        self.last_processing_metadata = build_processing_metadata(
            sampled_frame_count=len(all_frames),
            sampling_strategy="fixed_fps" if input_counts["videos"] else "image_inputs",
            fps=fps if input_counts["videos"] else None,
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
        self.last_processing_metadata["inputVideoCount"] = input_counts["videos"]
        self.last_processing_metadata["inputImageCount"] = input_counts["images"]
        self.last_processing_metadata["samplingRuns"] = sampling_runs
        self._finish_active_stage()
        return all_frames

    def _collect_input_frames(
        self,
        inputs: Iterable[str | Path],
        *,
        fps: float,
        max_frames: int,
        uniform_over_video: bool = False,
    ) -> tuple[List[Path], List[Dict], Dict[str, int]]:
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
                uniform_over_video=uniform_over_video,
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

        return all_frames, sampling_runs, {"videos": len(videos), "images": len(images)}

    # ------------------------------------------------------------------ #
    # Analysis
    # ------------------------------------------------------------------ #
    def analyze_frame(
        self,
        frame_path: str | Path,
        score: float = 1.0,
        *,
        precomputed: Optional[Dict[str, Any]] = None,
    ) -> FrameAnalysis:
        frame_path = Path(frame_path)
        self._mark_stage("frame_read")
        image = imread_rgb(frame_path)

        if precomputed:
            detections = list(precomputed.get("detections") or [])
            violations = list(precomputed.get("violations") or [])
            detections = self._refine_selected_safe_mode_frame(image, detections)
        else:
            self._mark_stage("detector_inference")
            detections = self.detector.detect(image)
            self._mark_stage("segmentation_refine")
            detections = self.segmenter.refine(image, detections)
            self._mark_stage("rule_evaluation")
            violations = evaluate_rules(detections)

        explanation: Optional[str] = None
        explanation_source: Optional[str] = None
        if violations:
            try:
                vlm_is_active = bool(getattr(self.vlm, "enabled", False)) and getattr(self.vlm, "provider", "rule_based") != "rule_based"
                if vlm_is_active and self._vlm_explanations_remaining <= 0:
                    self._mark_stage("rule_based_explanation")
                    explanation = RuleBasedReasoner().explain_violation(image, violations)
                    explanation_source = "rule_based"
                else:
                    if vlm_is_active:
                        self.component_diagnostics["vlmAttempted"] = True
                        self._vlm_explanations_remaining -= 1
                        self._mark_stage(
                            "lightweight_vlm_worker_explanation"
                            if getattr(self.vlm, "provider", "") == "vlm_lightweight_worker"
                            else "vlm_explanation"
                        )
                    else:
                        self._mark_stage("rule_based_explanation")
                    explanation = self.vlm.explain_violation(image, violations)
                    self._merge_lightweight_vlm_diagnostics()
                    explanation_source = _profiled_explanation_source(
                        getattr(self.vlm, "last_explanation_source", "rule_based")
                    )
                    if explanation_source == "vlm_lightweight":
                        self.component_diagnostics["effectiveExplanationMode"] = "lightweight_256m"
                    if explanation_source == "rule_based" and not (
                        self.safe_mode and self.component_diagnostics.get("mobileSamLoaded")
                    ):
                        self.component_diagnostics["effectiveExplanationMode"] = "rule_based"
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("VLM explanation failed: %s", exc)

        annotated_path: Optional[str] = None
        if detections:
            self._mark_stage("annotation_write")
            annotated = draw_overlays(image, detections)
            ann_dir = SETTINGS.data_dir / "annotated"
            ann_dir.mkdir(parents=True, exist_ok=True)
            out_path = ann_dir / f"{frame_path.stem}_annotated.jpg"
            imwrite_rgb(out_path, annotated)
            annotated_path = str(out_path)
        self._finish_active_stage()

        return FrameAnalysis(
            frame_id=frame_path.stem,
            frame_path=str(frame_path),
            score=float(score),
            detections=detections,
            violations=violations,
            explanation=explanation,
            explanation_source=explanation_source,
            annotated_path=annotated_path,
        )

    def analyze_query(self, query: str, k: int | None = None) -> List[Dict]:
        """Run the full pipeline for a natural-language query."""
        if self.safe_mode:
            logger.warning("Safe mode bypasses semantic search; use run() with inputs for direct frame analysis.")
            return []

        k = k or SETTINGS.top_k
        try:
            self._mark_stage("semantic_search")
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
        self._finish_active_stage()
        return payloads

    def _rank_safe_mode_frame(
        self,
        frame_path: Path,
        *,
        frame_index: int,
        total_frames: int,
        query_intent,
    ) -> RankedFrameCandidate:
        self._mark_stage("safe_ranking_frame_read")
        image = imread_rgb(frame_path)
        self._mark_stage("safe_ranking_detector_inference")
        detections = self.detector.detect(image)
        self._mark_stage("safe_ranking_rule_evaluation")
        detections = CoarseMaskSegmenter().refine(image, detections)
        violations = evaluate_rules(detections)
        return score_frame_for_safe_mode(
            frame_path=frame_path,
            frame_index=frame_index,
            total_frames=total_frames,
            detections=detections,
            violations=violations,
            query_intent=query_intent,
            image_shape=image.shape,
        )

    def analyze_frames_direct(self, frames: Iterable[Path], *, query: str = "", k: int | None = None) -> List[Dict]:
        """Safe-mode direct frame analysis without embeddings or semantic search."""
        frame_list = list(frames)
        top_k = max(1, int(k or SETTINGS.top_k))
        query_intent = parse_query_intent(query)
        self._mark_stage("safe_frame_ranking")
        ranked_frames = [
            self._rank_safe_mode_frame(
                Path(frame_path),
                frame_index=index,
                total_frames=len(frame_list),
                query_intent=query_intent,
            )
            for index, frame_path in enumerate(frame_list)
        ]
        selected_frames = select_ranked_frames(ranked_frames, top_k=top_k)
        ranking_summary = {
            "strategy": "object_rule_temporal",
            "queryIntent": query_intent.to_dict(),
            "framesScanned": len(ranked_frames),
            "framesSelected": len(selected_frames),
            "topScores": [
                {
                    "frame": candidate.frame_path.name,
                    "score": round(candidate.raw_score, 4),
                    "selectedFor": candidate.selected_for,
                    "reason": candidate.ranking_reason,
                }
                for candidate in selected_frames[:10]
            ],
        }
        self.component_diagnostics["safeFrameRanking"] = ranking_summary
        self.component_diagnostics["safeRankingFramesScanned"] = len(ranked_frames)
        self.component_diagnostics["safeRankingSelectedFrames"] = len(selected_frames)
        self.component_diagnostics["safeRankingQueryIntent"] = query_intent.to_dict()
        if self.last_processing_metadata is not None:
            self.last_processing_metadata["safeFrameRanking"] = ranking_summary
            self.last_processing_metadata["processingWindowCount"] = len(selected_frames)

        payloads: List[Dict] = []
        for rank, candidate in enumerate(selected_frames, start=1):
            fa = self.analyze_frame(
                candidate.frame_path,
                score=candidate.normalized_score,
                precomputed={
                    "detections": candidate.detections,
                    "violations": candidate.violations,
                },
            )
            payload = fa.to_dict()
            payload["search_metadata"] = candidate.search_metadata(rank=rank)
            if self.component_diagnostics.get("mobileSamRequested"):
                payload["search_metadata"]["mobileSamRefinement"] = {
                    "mobileSamWorkerEnabled": self.component_diagnostics.get("mobileSamWorkerEnabled"),
                    "mobileSamWorkerAttempted": self.component_diagnostics.get("mobileSamWorkerAttempted"),
                    "mobileSamWorkerSucceeded": self.component_diagnostics.get("mobileSamWorkerSucceeded"),
                    "mobileSamWorkerTimedOut": self.component_diagnostics.get("mobileSamWorkerTimedOut"),
                    "mobileSamWorkerExitCode": self.component_diagnostics.get("mobileSamWorkerExitCode"),
                    "mobileSamFallbackReason": self.component_diagnostics.get("mobileSamFallbackReason"),
                    "mobileSamRefinementSource": self.component_diagnostics.get("mobileSamRefinementSource"),
                }
            if self.component_diagnostics.get("lightweightVlmWorkerEnabled"):
                payload["search_metadata"]["lightweightVlmExplanation"] = {
                    "lightweightVlmWorkerEnabled": self.component_diagnostics.get("lightweightVlmWorkerEnabled"),
                    "lightweightVlmWorkerAttempted": self.component_diagnostics.get("lightweightVlmWorkerAttempted"),
                    "lightweightVlmWorkerSucceeded": self.component_diagnostics.get("lightweightVlmWorkerSucceeded"),
                    "lightweightVlmWorkerTimedOut": self.component_diagnostics.get("lightweightVlmWorkerTimedOut"),
                    "lightweightVlmWorkerExitCode": self.component_diagnostics.get("lightweightVlmWorkerExitCode"),
                    "lightweightVlmFallbackReason": self.component_diagnostics.get("lightweightVlmFallbackReason"),
                    "lightweightVlmExplanationSource": self.component_diagnostics.get("lightweightVlmExplanationSource"),
                    "lightweightVlmQualityIssue": self.component_diagnostics.get("lightweightVlmQualityIssue"),
                    "lightweightVlmRawTextPreview": self.component_diagnostics.get("lightweightVlmRawTextPreview"),
                    "lightweightVlmCleanTextPreview": self.component_diagnostics.get("lightweightVlmCleanTextPreview"),
                    "lightweightVlmGenerationTimeoutSeconds": self.component_diagnostics.get(
                        "lightweightVlmGenerationTimeoutSeconds"
                    ),
                    "lightweightVlmMaxTokens": self.component_diagnostics.get("lightweightVlmMaxTokens"),
                }
            if self.last_processing_metadata:
                payload["processing_metadata"] = self.last_processing_metadata
            payloads.append(payload)
        self._finish_active_stage()
        return payloads

    def run_safe_mode(
        self,
        inputs: Iterable[str | Path],
        query: str,
        fps: float | None = None,
        k: int | None = None,
    ) -> List[Dict]:
        fps = fps or SETTINGS.frame_fps
        max_frames = SETTINGS.max_frames
        self._mark_stage("safe_frame_sampling")
        all_frames, sampling_runs, input_counts = self._collect_input_frames(
            inputs,
            fps=fps,
            max_frames=max_frames,
            uniform_over_video=True,
        )
        if not all_frames:
            raise ValueError("No usable frames produced from the supplied inputs.")
        self.last_processing_metadata = build_processing_metadata(
            sampled_frame_count=len(all_frames),
            sampling_strategy="safe_object_ranked_frame_scan",
            fps=fps if input_counts["videos"] else None,
            max_frames=max_frames,
            embedding_batch_size=0,
            embedding_window_size=1,
            embedding_window_stride=1,
            embedding_pooling_strategy="mean",
            processing_window_count=min(len(all_frames), max(1, int(k or SETTINGS.top_k))),
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
        self.last_processing_metadata["inputVideoCount"] = input_counts["videos"]
        self.last_processing_metadata["inputImageCount"] = input_counts["images"]
        self.last_processing_metadata["samplingRuns"] = sampling_runs
        self.last_processing_metadata["safeMode"] = True
        self.last_processing_metadata["semanticSearch"] = False
        self.last_processing_metadata["embeddingBypassed"] = True
        return self.analyze_frames_direct(all_frames, query=query, k=k)

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
        if self.safe_mode:
            return self.run_safe_mode(inputs_list, query=query, fps=fps, k=k)
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
