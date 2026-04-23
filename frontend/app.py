"""SafeTrace Streamlit UI.

Run:
    streamlit run frontend/app.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import List

import streamlit as st

# Allow running with `streamlit run frontend/app.py` from project root.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import SETTINGS  # noqa: E402
from src.pipeline import SafeTracePipeline  # noqa: E402
from src.utils import imread_rgb  # noqa: E402

st.set_page_config(page_title="SafeTrace", layout="wide", page_icon="🦺")


# --------------------------------------------------------------------------- #
# Cached pipeline (loaded once per session)
# --------------------------------------------------------------------------- #
@st.cache_resource(show_spinner="Loading SafeTrace models …")
def get_pipeline() -> SafeTracePipeline:
    return SafeTracePipeline()


# --------------------------------------------------------------------------- #
# Sidebar
# --------------------------------------------------------------------------- #
with st.sidebar:
    st.title("🦺 SafeTrace")
    st.caption("Offline safety violation detection")

    fps = st.number_input("Frame sampling FPS", 0.1, 30.0, float(SETTINGS.frame_fps), 0.1)
    top_k = st.slider("Top-K frames to analyze", 1, 20, int(SETTINGS.top_k))
    enable_vlm = st.toggle("Enable VLM explanations", value=SETTINGS.enable_vlm,
                           help="Requires a local VLM checkpoint in checkpoints/vlm_model/")

    st.divider()
    st.subheader("System")
    st.write(f"Device: `{SETTINGS.device}`")
    st.write(f"Embedding model: `{SETTINGS.siglip_model_dir.name}`")
    st.write(f"Detector: `{SETTINGS.yolo_checkpoint.name}`")
    st.write("MobileSAM:", "✅" if SETTINGS.mobile_sam_checkpoint.exists() else "⚠️ missing")


# --------------------------------------------------------------------------- #
# Header
# --------------------------------------------------------------------------- #
st.title("Safety Violation Detection")
st.write(
    "Upload a **video** or one or more **images**, type a natural-language "
    "query (e.g. *worker without helmet*), and click **Analyze**."
)

uploaded = st.file_uploader(
    "Upload media",
    type=["jpg", "jpeg", "png", "bmp", "webp", "mp4", "mov", "avi", "mkv", "webm"],
    accept_multiple_files=True,
)

query = st.text_input(
    "Query",
    value="worker without helmet",
    help="Used by FAISS to retrieve the most relevant frames before detection.",
)

col_a, col_b = st.columns([1, 5])
analyze = col_a.button("🚀 Analyze", type="primary", use_container_width=True)
reset = col_b.button("Reset session", use_container_width=False)

if reset:
    st.session_state.clear()
    st.rerun()


# --------------------------------------------------------------------------- #
# Analysis
# --------------------------------------------------------------------------- #
def _persist_uploads(files) -> List[Path]:
    out: List[Path] = []
    tmp_dir = Path(tempfile.mkdtemp(prefix="safetrace_"))
    for f in files:
        dst = tmp_dir / f.name
        with open(dst, "wb") as fh:
            fh.write(f.getbuffer())
        out.append(dst)
    return out


if analyze:
    if not uploaded:
        st.warning("Please upload at least one image or video.")
    elif not query.strip():
        st.warning("Please enter a query.")
    else:
        SETTINGS.enable_vlm = enable_vlm  # propagate UI toggle
        SETTINGS.frame_fps = float(fps)
        SETTINGS.top_k = int(top_k)

        pipeline = get_pipeline()
        pipeline.vlm.enabled = enable_vlm and pipeline.vlm._loaded

        with st.status("Running pipeline…", expanded=True) as status:
            st.write("• Saving uploads")
            files = _persist_uploads(uploaded)

            st.write("• Extracting frames + building FAISS index")
            try:
                pipeline.ingest(files, fps=fps)
            except Exception as exc:
                status.update(label="Ingestion failed", state="error")
                st.exception(exc)
                st.stop()

            st.write(f"• Retrieving top-{top_k} frames for query: *{query}*")
            try:
                results = pipeline.analyze_query(query, k=top_k)
            except Exception as exc:
                status.update(label="Analysis failed", state="error")
                st.exception(exc)
                st.stop()

            status.update(label=f"Done — {len(results)} frames analyzed", state="complete")

        st.session_state["results"] = results
        st.session_state["query"] = query


# --------------------------------------------------------------------------- #
# Results display
# --------------------------------------------------------------------------- #
results = st.session_state.get("results")
if results:
    st.subheader(f"Results for: *{st.session_state.get('query', '')}*")

    report_bytes = json.dumps(results, indent=2).encode("utf-8")
    st.download_button(
        "⬇️ Download JSON report",
        data=report_bytes,
        file_name="safetrace_report.json",
        mime="application/json",
    )

    for idx, frame in enumerate(results, start=1):
        st.markdown(f"### Frame {idx} — `{frame['frame_id']}`  (score `{frame['score']:.3f}`)")

        c_img, c_meta = st.columns([2, 1], gap="large")
        with c_img:
            img_path = frame.get("annotated_path") or frame.get("frame_path")
            if img_path and Path(img_path).exists():
                st.image(imread_rgb(img_path), caption=Path(img_path).name,
                         use_container_width=True)

        with c_meta:
            violations = frame.get("violations", [])
            if violations:
                st.error(f"{len(violations)} violation(s) detected")
                for v in violations:
                    st.markdown(
                        f"**{v['name']}** ({v['severity']})  \n"
                        f"{v['description']}  \n"
                        f"Confidence: `{v['confidence']:.2f}`"
                    )
                    st.json(v["evidence"])
            else:
                st.success("No violations detected")

            if frame.get("explanation"):
                st.markdown("**Explanation**")
                st.write(frame["explanation"])

            with st.expander("Detections"):
                st.json(frame.get("detections", []))

        st.divider()
else:
    st.info("Upload media and click **Analyze** to begin.")
