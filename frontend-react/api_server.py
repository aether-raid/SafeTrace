"""SafeTrace API integration layer.

Bridges the React frontend to the SafeTrace Python pipeline.
Adds proper timestamp computation from frame indices.

Usage:
    python frontend-react/api_server.py
    # OR
    uvicorn frontend-react.api_server:app --host 127.0.0.1 --port 8080
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import uvicorn
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import SETTINGS
from src.pipeline import SafeTracePipeline
from src.utils import is_video

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
)
logger = logging.getLogger("safetrace.api")

app = FastAPI(title="SafeTrace API", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_pipeline: Optional[SafeTracePipeline] = None


def get_pipeline() -> SafeTracePipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = SafeTracePipeline()
    return _pipeline


FRAME_INDEX_RE = re.compile(r"_(\d{6,})(?:_annotated)?\.(?:jpg|jpeg|png)$")


def parse_frame_index(frame_id: str) -> Optional[int]:
    m = FRAME_INDEX_RE.search(frame_id)
    if m:
        return int(m.group(1))
    return None


def seconds_to_timestamp(total_seconds: float) -> str:
    h = int(total_seconds // 3600)
    m = int((total_seconds % 3600) // 60)
    s = int(total_seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def format_file_size(bytes_val: int) -> str:
    if bytes_val < 1024:
        return f"{bytes_val} B"
    for unit in ("KB", "MB", "GB"):
        bytes_val /= 1024
        if bytes_val < 1024:
            return f"{bytes_val:.1f} {unit}" if bytes_val >= 10 else f"{bytes_val:.2f} {unit}"
    return f"{bytes_val:.1f} TB"


def compute_duration_seconds(video_path: Path) -> float:
    import cv2
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return 0.0
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
    cap.release()
    if frame_count <= 0:
        return 0.0
    return frame_count / fps


def format_duration(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "safetrace-api"}


_media_store: Dict[str, Any] = {}
_results_store: Dict[str, Any] = {}


@app.post("/api/ingest")
async def api_ingest(files: List[UploadFile] = File(...), fps: float = Form(1.0)):
    upload_id = str(uuid.uuid4())[:8]
    tmp_dir = Path(tempfile.mkdtemp(prefix=f"safetrace_{upload_id}_"))
    saved: List[Path] = []
    media_info: List[Dict] = []

    for f in files:
        dst = tmp_dir / (f.filename or f"upload_{len(saved)}")
        content = await f.read()
        dst.write_bytes(content)
        saved.append(dst)

        info: Dict[str, Any] = {
            "id": f"{upload_id}-{dst.stem}",
            "filename": dst.name,
            "type": "video" if is_video(dst) else "image",
            "sizeLabel": format_file_size(dst.stat().st_size),
            "uploadedAt": None,
            "status": "processing",
            "fps": fps,
        }
        if is_video(dst):
            info["durationSeconds"] = compute_duration_seconds(dst)
            info["duration"] = format_duration(info["durationSeconds"])
        media_info.append(info)

    logger.info("Ingesting %d file(s) with fps=%.1f", len(saved), fps)
    pipeline = get_pipeline()
    try:
        pipeline.ingest(saved, fps=fps)
    except Exception as exc:
        logger.error("Ingestion failed: %s", exc)
        return JSONResponse({"error": str(exc)}, status_code=500)

    for info in media_info:
        info["status"] = "completed"

    _media_store[upload_id] = {
        "id": upload_id,
        "media": media_info,
        "fps": fps,
    }

    return {
        "uploadId": upload_id,
        "media": media_info,
        "fps": fps,
        "message": f"Ingested {len(saved)} file(s)",
    }


@app.post("/api/analyze")
async def api_analyze(query: str = Form(...), k: int = Form(5), upload_id: Optional[str] = Form(None)):
    pipeline = get_pipeline()
    try:
        raw_results = pipeline.analyze_query(query, k=k)
    except Exception as exc:
        logger.error("Analysis failed: %s", exc)
        return JSONResponse({"error": str(exc)}, status_code=500)

    result_id = str(uuid.uuid4())[:8]
    fps = 1.0
    media_info: List[Dict] = []
    if upload_id and upload_id in _media_store:
        fps = _media_store[upload_id].get("fps", 1.0)
        media_info = _media_store[upload_id].get("media", [])

    frames = []
    for raw in raw_results:
        frame_id: str = raw.get("frame_id", "")
        score: float = raw.get("score", 0.0)
        frame_index = parse_frame_index(frame_id) or 0

        timestamp_seconds = frame_index / fps if fps > 0 else 0.0

        frame_path: str = raw.get("frame_path", "")
        annotated_path: Optional[str] = raw.get("annotated_path")

        image_url = f"/api/serve-file?path={frame_path}" if frame_path else None
        annotated_url = f"/api/serve-file?path={annotated_path}" if annotated_path else None

        detections = []
        for d in raw.get("detections", []):
            detections.append({
                "id": f"{frame_id}-{d.get('label', 'unknown')}",
                "label": d.get("label", d.get("raw_label", "unknown")),
                "confidence": d.get("confidence", 0.0),
                "bbox": d.get("bbox", [0, 0, 0, 0]),
                "source": "detector",
            })

        violations = []
        for v in raw.get("violations", []):
            violations.append({
                "id": f"{frame_id}-{v.get('name', 'violation')}",
                "type": v.get("name", "unknown"),
                "name": v.get("name", "Unknown"),
                "severity": v.get("severity", "medium").title() if isinstance(v.get("severity"), str) else "Medium",
                "description": v.get("description", ""),
                "confidence": v.get("confidence", 0.0),
                "evidence": v.get("evidence", {}),
            })

        frames.append({
            "id": f"frame-{frame_id}",
            "frameIndex": frame_index,
            "timestamp": seconds_to_timestamp(timestamp_seconds),
            "timestampSeconds": round(timestamp_seconds, 3),
            "internalFilename": frame_path,
            "score": score,
            "imageUrl": image_url,
            "annotatedUrl": annotated_url,
            "explanation": raw.get("explanation"),
            "violations": violations,
            "detections": detections,
        })

    violation_types = set()
    for f in frames:
        for v in f["violations"]:
            violation_types.add(v["type"])

    total_duration = 0.0
    if media_info:
        durations = [m.get("durationSeconds", 0) or 0 for m in media_info if m.get("type") == "video"]
        if durations:
            total_duration = max(durations)

    summary_text = ""
    if frames:
        frames_with_v = sum(1 for f in frames if f["violations"])
        if frames_with_v > 0:
            summary_text = (
                f"I found {len(violation_types)} potential safety violation "
                f"{'type' if len(violation_types) == 1 else 'types'} across "
                f"{frames_with_v} of {len(frames)} relevant frames. "
                f"The detected issues include: {', '.join(sorted(violation_types))}. "
                f"Each finding is backed by visual evidence from the uploaded footage."
            )
        else:
            summary_text = (
                f"I reviewed {len(frames)} frames from your footage and found "
                f"no safety violations matching your query. The workers in the "
                f"selected frames appear to be following safety protocols."
            )

    result = {
        "id": f"analysis-{result_id}",
        "query": query,
        "media": media_info[0] if media_info else {
            "id": f"direct-{result_id}",
            "filename": "direct query",
            "type": "video",
            "duration": format_duration(total_duration),
            "durationSeconds": total_duration,
        },
        "framesAnalyzed": len(frames),
        "generatedAt": None,
        "summaryText": summary_text,
        "frames": frames,
        "totalDurationSeconds": total_duration,
    }

    _results_store[result_id] = result

    return {"resultId": result_id, "result": result}


@app.get("/api/serve-file")
def serve_file(path: str):
    p = Path(path)
    if not p.exists():
        p = ROOT / path
    if not p.exists():
        return JSONResponse({"error": "File not found"}, status_code=404)
    return FileResponse(str(p))


@app.get("/api/results/{result_id}")
def get_result(result_id: str):
    result = _results_store.get(result_id)
    if not result:
        return JSONResponse({"error": "Result not found"}, status_code=404)
    return result


@app.get("/api/media")
def list_media():
    items = []
    for uid, store in _media_store.items():
        for m in store.get("media", []):
            items.append(m)
    return {"media": items}


if __name__ == "__main__":
    port = int(os.environ.get("SAFETRACE_API_PORT", "8080"))
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
