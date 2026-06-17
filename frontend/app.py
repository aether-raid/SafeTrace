"""SafeTrace Streamlit UI.

Run:
    streamlit run frontend/app.py
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import List

import streamlit as st

# Allow running with `streamlit run frontend/app.py` from project root.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import SETTINGS  # noqa: E402
from src.jobs import JobStore  # noqa: E402
from src.uploads import (  # noqa: E402
    EXPECTED_ZIP_STRUCTURE,
    UploadValidationError,
    build_single_media_items,
    extract_vehicle_zip,
    is_zip_upload,
)
from src.ui_format import (  # noqa: E402
    current_media_text,
    format_confidence_percent,
    format_evidence_values,
    media_status_for_display,
)
from src.utils import imread_rgb, read_json  # noqa: E402

st.set_page_config(page_title="SafeTrace", layout="wide", page_icon=":shield:")


@st.cache_data(show_spinner=False)
def _cuda_status() -> dict:
    """Probe whether CUDA is actually usable on this host."""
    info = {
        "available": False,
        "name": None,
        "compute_cap": None,
        "usable": False,
        "error": None,
    }
    try:
        import torch
    except Exception as exc:
        info["error"] = f"torch import failed: {exc}"
        return info

    if not torch.cuda.is_available():
        return info
    info["available"] = True
    try:
        info["name"] = torch.cuda.get_device_name(0)
        major, minor = torch.cuda.get_device_capability(0)
        info["compute_cap"] = f"{major}.{minor}"
    except Exception:
        pass

    try:
        x = torch.randn(1, 3, 8, 8, device="cuda")
        w = torch.randn(2, 3, 3, 3, device="cuda")
        torch.nn.functional.conv2d(x, w)
        torch.cuda.synchronize()
        info["usable"] = True
    except Exception as exc:
        info["error"] = str(exc).splitlines()[0]
    return info


store = JobStore()


# --------------------------------------------------------------------------- #
# Sidebar
# --------------------------------------------------------------------------- #
with st.sidebar:
    st.title("SafeTrace")
    st.caption("Offline safety violation detection")

    fps = st.number_input("Frame sampling FPS", 0.1, 30.0, float(SETTINGS.frame_fps), 0.1)
    top_k = st.slider("Top-K frames to analyze", 1, 20, int(SETTINGS.top_k))
    enable_vlm = st.toggle(
        "Enable VLM explanations",
        value=SETTINGS.enable_vlm,
        help="Requires a local VLM checkpoint in checkpoints/vlm_model/",
    )
    auto_refresh = st.checkbox("Auto-refresh while processing", value=True)
    refresh_seconds = st.slider("Refresh interval seconds", 2, 5, 3)

    st.divider()
    st.subheader("Compute")
    cuda = _cuda_status()
    cuda_ok = cuda["usable"]
    device_options = ["cpu", "cuda", "auto"]
    default_choice = SETTINGS.device if SETTINGS.device in device_options else "cpu"
    device_choice = st.selectbox(
        "Device",
        device_options,
        index=device_options.index(default_choice),
        help=(
            "`cpu` is the safest default. `cuda` enables GPU acceleration but "
            "requires a PyTorch build with kernels for your GPU's compute "
            "capability. `auto` picks CUDA if usable, else CPU."
        ),
    )

    if device_choice == "cpu":
        resolved_device = "cpu"
    elif cuda_ok:
        resolved_device = "cuda"
    else:
        resolved_device = "cpu"
        if device_choice in {"cuda", "auto"}:
            if cuda["available"]:
                st.error(
                    f"GPU detected ({cuda['name']}, sm_{cuda['compute_cap']}) "
                    "but the installed PyTorch build cannot use it. Falling back to CPU."
                )
                if cuda.get("error"):
                    st.write(f"Probe error: `{cuda['error']}`")
            else:
                st.warning("No CUDA device is visible. Falling back to CPU.")

    st.divider()
    st.subheader("System")
    st.write(f"Resolved device: `{resolved_device}`")
    if cuda["available"]:
        st.write(f"GPU: `{cuda['name']}` (sm_{cuda['compute_cap']})")
        st.write(f"GPU usable by PyTorch: `{cuda_ok}`")
    else:
        st.write("GPU: not detected")
    st.write(f"Embedding model: `{SETTINGS.siglip_model_dir.name}`")
    st.write(f"Detector: `{SETTINGS.yolo_checkpoint.name}`")
    st.write(
        "MobileSAM:",
        "available" if SETTINGS.mobile_sam_checkpoint.exists() else "missing",
    )


# --------------------------------------------------------------------------- #
# Header / upload controls
# --------------------------------------------------------------------------- #
st.title("Safety Violation Detection")
st.write(
    "Upload a video, one or more images, or a ZIP with vehicle subfolders, "
    "then queue the job for local processing."
)

uploaded = st.file_uploader(
    "Upload a video/image file or a ZIP containing vehicle folders",
    type=["jpg", "jpeg", "png", "bmp", "webp", "mp4", "avi", "mov", "mkv", "webm", "zip"],
    accept_multiple_files=True,
)

query = st.text_input(
    "Query",
    value="worker without helmet",
    help="Used by FAISS to retrieve the most relevant frames after ingestion.",
)

col_a, col_b = st.columns([1, 5])
queue_clicked = col_a.button("Queue job", type="primary", use_container_width=True)
reset = col_b.button("Reset session", use_container_width=False)

if reset:
    st.session_state.clear()
    st.rerun()


def _persist_uploaded_file(upload, dst: Path) -> Path:
    dst.parent.mkdir(parents=True, exist_ok=True)
    with open(dst, "wb") as fh:
        fh.write(upload.getbuffer())
    return dst


def _queue_uploads(files) -> dict:
    job_id = store.new_job_id()
    batch_id = job_id
    upload_dir = store.job_dir(job_id) / "uploads"
    media_items: list[dict] = []
    single_paths: List[Path] = []

    for upload in files:
        safe_name = Path(upload.name).name
        dst = _persist_uploaded_file(upload, upload_dir / safe_name)
        if is_zip_upload(dst):
            extracted = extract_vehicle_zip(dst, upload_dir / "bulk", batch_id=batch_id)
            media_items.extend(item.to_dict() for item in extracted)
        else:
            single_paths.append(dst)

    media_items.extend(
        item.to_dict()
        for item in build_single_media_items(single_paths, batch_id=batch_id)
    )
    if not media_items:
        raise UploadValidationError(
            "No usable video files were found. Upload a supported video file or a ZIP "
            "containing vehicle folders."
        )

    return store.create_job(
        media_items,
        query=query.strip(),
        settings={
            "fps": float(fps),
            "top_k": int(top_k),
            "enable_vlm": bool(enable_vlm),
            "device": resolved_device,
            "max_frames": int(SETTINGS.max_frames),
        },
        batch_id=batch_id,
        job_id=job_id,
    )


def _start_auto_worker(job_id: str) -> dict:
    result = store.start_worker_once_subprocess(repo_root=ROOT)
    st.session_state[f"auto_worker_{job_id}"] = result
    return result


def _show_auto_worker_result(result: dict) -> None:
    if not result:
        return
    if result.get("started"):
        st.success(f"Auto-processing started in the background (pid `{result.get('pid')}`).")
        return
    reason = result.get("reason") or "Unknown reason."
    if "already" in reason.lower() or "processing" in reason.lower():
        st.info(f"Auto-processing is already active: {reason}")
        return
    st.warning(
        "Job was queued but auto-processing failed to start. "
        "You can run `python main.py worker --once` manually."
    )
    if result.get("error"):
        st.error(result["error"])


if queue_clicked:
    if not uploaded:
        st.warning("Please upload at least one image, video, or ZIP file.")
    else:
        try:
            job = _queue_uploads(uploaded)
            st.session_state["selected_job_id"] = job["job_id"]
            st.success(f"Queued job `{job['job_id']}`.")
            _show_auto_worker_result(_start_auto_worker(job["job_id"]))
        except UploadValidationError as exc:
            st.error(str(exc))
            st.code(EXPECTED_ZIP_STRUCTURE, language="text")
        except Exception as exc:
            st.exception(exc)


def _job_label(job: dict) -> str:
    return f"{job['job_id']} - {job.get('status', 'unknown')} - {job.get('stage', '')}"


def _show_image(path, caption=None):
    if not path:
        st.info("No representative frame available.")
        return

    path = str(path)
    if not Path(path).exists():
        st.warning(f"Image not found: {path}")
        return

    try:
        st.image(imread_rgb(path), caption=caption or Path(path).name, use_container_width=True)
    except TypeError:
        st.image(imread_rgb(path), caption=caption or Path(path).name, use_column_width=True)


def _violation_label(violation: dict) -> str:
    return str(violation.get("name") or violation.get("type") or "violation")


def _render_violation_readable(violation: dict) -> None:
    st.markdown(f"**{_violation_label(violation)}**")
    description = violation.get("description") or violation.get("reasoning")
    if description:
        st.write(description)
    if violation.get("severity"):
        st.write(f"Severity: `{violation['severity']}`")
    if violation.get("status"):
        st.write(f"Status: `{violation['status']}`")
    if violation.get("confidence") is not None:
        st.write(f"Confidence: `{format_confidence_percent(violation['confidence'])}`")
    if violation.get("evidence"):
        st.write(format_evidence_values(violation.get("evidence")))
    with st.expander("Show raw evidence JSON"):
        st.json(violation)


def _frame_title(frame: dict) -> str:
    timestamp = frame.get("timestamp")
    if timestamp is None:
        timestamp = (frame.get("metadata") or {}).get("timestamp", 0.0)
    return f"{frame.get('frame_id', 'frame')} at {float(timestamp or 0.0):.2f}s"


def _render_frame_card(frame: dict) -> None:
    left, right = st.columns([2, 1], gap="large")
    with left:
        _show_image(frame.get("annotated_path") or frame.get("frame_path"), caption=_frame_title(frame))
    with right:
        violations = frame.get("violations") or []
        if violations:
            st.error(f"{len(violations)} violation(s) detected")
            for violation in violations:
                _render_violation_readable(violation)
        else:
            st.success("No violations detected")
        if frame.get("explanation"):
            st.markdown("**Explanation**")
            st.write(frame["explanation"])
        with st.expander("Show raw frame JSON"):
            st.json(frame)


def _render_frame_evidence(frames: list[dict]) -> None:
    evidence = [frame for frame in frames if frame.get("violations")]
    if not evidence:
        st.write("No frame-level violations were retained.")
        return
    for frame in evidence[:50]:
        with st.expander(_frame_title(frame)):
            _render_frame_card(frame)


def _first_representative_frame(event: dict) -> dict:
    reps = event.get("representative_frames") or []
    return reps[0] if reps else {}


def _render_event(summary: dict, event: dict) -> None:
    rep = _first_representative_frame(event)
    left, right = st.columns([2, 1], gap="large")
    with left:
        _show_image(rep.get("annotated_path") or rep.get("frame_path"), caption=rep.get("frame_id"))
    with right:
        st.markdown(f"**{event.get('type', 'violation')}**")
        st.write(f"Status: `{event.get('status')}`")
        st.write(f"Confidence: `{format_confidence_percent(event.get('confidence'))}`")
        st.write(
            f"Time: `{event.get('start_time')}s` to `{event.get('end_time')}s` "
            f"({event.get('duration_seconds')}s)"
        )
        st.write(f"Evidence frames: `{event.get('evidence_frame_count', 0)}`")
        if event.get("reasoning"):
            st.write(event["reasoning"])
        with st.expander("Show raw evidence JSON"):
            st.json({"summary": summary, "event": event})


def _render_results(result: dict) -> None:
    st.subheader("Video summaries")
    for summary in result.get("summaries", []):
        st.markdown(
            f"### `{summary.get('video_id')}`"
            f"  \nVehicle: `{summary.get('vehicle_id') or 'unknown'}`"
            f"  \nStatus: `{summary.get('overall_status')}`"
            f"  \nConfidence: `{format_confidence_percent(summary.get('overall_confidence'))}`"
        )
        st.write(summary.get("summary", ""))
        for event in summary.get("violations", []):
            _render_event(summary, event)

    with st.expander("Frame-level evidence"):
        _render_frame_evidence(result.get("frame_results", []))

    search_results = result.get("search_results", [])
    if search_results:
        with st.expander("Top-K search results"):
            for idx, frame in enumerate(search_results, start=1):
                st.markdown(f"**Frame {idx}: `{frame['frame_id']}`** score `{frame['score']:.3f}`")
                _render_frame_card(frame)


# --------------------------------------------------------------------------- #
# Job status / results display
# --------------------------------------------------------------------------- #
jobs = store.list_jobs()
if jobs:
    if st.button("Refresh status"):
        st.rerun()

    default_job = st.session_state.get("selected_job_id")
    options = [job["job_id"] for job in jobs]
    index = options.index(default_job) if default_job in options else 0
    selected_job_id = st.selectbox(
        "Job",
        options,
        index=index,
        format_func=lambda job_id: _job_label(next(j for j in jobs if j["job_id"] == job_id)),
    )
    st.session_state["selected_job_id"] = selected_job_id
    job = store.get_job(selected_job_id)
    _show_auto_worker_result(st.session_state.get(f"auto_worker_{selected_job_id}", {}))

    st.progress(float(job.get("progress", 0.0)))
    st.write(f"Status: `{job.get('status')}`")
    st.write(f"Stage: `{job.get('stage')}`")
    current_media = current_media_text(job)
    if current_media:
        st.write(f"Current media: `{current_media}`")
    if job.get("processed_frames"):
        st.write(f"Processed frames: `{job.get('processed_frames')}`")
    if job.get("error"):
        st.error(job["error"])

    media = job.get("media") or []
    if media:
        with st.expander("Uploaded media records", expanded=job.get("status") == "queued"):
            st.dataframe(
                [
                    {
                        "vehicle_id": item.get("vehicle_id") or "",
                        "filename": item.get("filename") or "",
                        "relative_path": item.get("original_relative_path") or "",
                        "media_type": item.get("media_type") or "",
                        "status": media_status_for_display(item, job.get("status", "")),
                    }
                    for item in media
                ],
                use_container_width=True,
            )

    result_path = job.get("result_path")
    if job.get("status") == "completed" and result_path and Path(result_path).exists():
        st.write(f"Result path: `{result_path}`")
        result = read_json(result_path)
        st.download_button(
            "Download JSON report",
            data=json.dumps(result, indent=2).encode("utf-8"),
            file_name=f"safetrace_{selected_job_id}.json",
            mime="application/json",
        )
        _render_results(result)
    elif job.get("status") in {"queued", "processing"}:
        st.info("Results will appear here after the job status is completed.")
    elif job.get("status") == "completed":
        st.warning("Job completed, but the result file is not available yet.")

    if job.get("status") == "queued":
        if not store.worker_lock_exists() and not store.has_processing_job():
            _show_auto_worker_result(_start_auto_worker(selected_job_id))
        else:
            st.info("Job is queued and a background worker is already active.")

    if auto_refresh and job.get("status") in {"queued", "processing"}:
        time.sleep(refresh_seconds)
        st.rerun()
else:
    st.info("Upload media and queue a job to begin.")
