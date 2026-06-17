# SafeTrace

Modular, **fully-offline**, GPU-ready safety-violation detection system.
Upload videos or images, the pipeline retrieves the most relevant frames
with SigLIP + FAISS, detects objects with YOLOv9-seg + MobileSAM, applies
a deterministic rule engine, and (optionally) generates natural-language
explanations with a local VLM. Results are served through a Streamlit UI.

---

## Architecture

```
User upload (video / images)
        │
        ▼
Frame Sampler (configurable FPS)
        │
        ▼
SigLIP image embeddings ──► FAISS IndexFlatIP (data/index.faiss)
        │
        ▼
semantic_search(query, k) ─ top-K candidate frames
        │
        ▼
YOLOv9-seg ── boxes + coarse masks
        │
        ▼
MobileSAM (vit_t) ── refined binary masks per box
        │
        ▼
Rule engine
   • helmet_missing       IoU(head, helmet)        < 0.20
   • hands_off_wheel      IoU(hand, wheel)         < 0.10
   • phone_use            IoU(phone, hand)         > 0.30
   • seatbelt_missing     IoU(seatbelt, torso)     < 0.20
        │
        ▼
Optional VLM (Phi-3-Vision / MiniCPM-V) — natural language summary
        │
        ▼
Streamlit UI: overlays, evidence table, JSON download
```

---

## Project layout

```
SafeTrace/
├── src/
│   ├── clip_embedder.py         # SigLIP / CLIP loader + batch embeddings
│   ├── faiss_index.py           # IndexFlatIP build / load / semantic_search
│   ├── yolo_detector.py         # YOLOv9-seg (Ultralytics) wrapper
│   ├── mobile_sam_segmenter.py  # MobileSAM box → refined mask
│   ├── rule_engine.py           # IoU-based safety rules
│   ├── vlm_reasoner.py          # Optional local VLM explanations
│   ├── pipeline.py              # End-to-end orchestrator + analyze_query()
│   ├── schemas.py               # Detection / Violation / FrameAnalysis
│   ├── utils.py                 # Frame extraction, IoU, overlays, IO
│   └── config.py                # Central settings (env-overridable)
├── frontend/
│   └── app.py                   # Streamlit UI
├── data/                        # Frames, embeddings, FAISS index, annotated outputs
├── checkpoints/                 # Local model weights (mounted in Docker)
├── docker/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── entrypoint.sh
├── main.py                      # CLI: ingest / query / ui
└── README.md
```

---

## Local checkpoints (required for offline mode)

Place each checkpoint under `checkpoints/`:

| Component   | Default path                                            | How to obtain                               |
|-------------|---------------------------------------------------------|---------------------------------------------|
| SigLIP      | `checkpoints/siglip-base-patch16-224/`                  | `huggingface-cli download google/siglip-base-patch16-224 --local-dir checkpoints/siglip-base-patch16-224` |
| YOLOv9-seg  | `checkpoints/yolov9c-seg.pt`                            | Ultralytics release asset                   |
| YOLOv8-seg* | `checkpoints/yolov8s-seg.pt` *(fallback)*               | Ultralytics release asset                   |
| MobileSAM   | `checkpoints/mobile_sam.pt`                             | https://github.com/ChaoningZhang/MobileSAM  |
| VLM (opt.)  | `checkpoints/vlm_model/`                                | e.g. `microsoft/Phi-3-vision-128k-instruct` |

All paths are overridable via environment variables — see `src/config.py`.

---

## Quick start (local Python)

```bash
pip install -r docker/requirements.txt   # or your own pinned env
python main.py ingest path/to/video.mp4 path/to/image.jpg
python main.py query "worker without helmet" --k 5 --output report.json
python main.py ui                        # http://localhost:8501
```

---

## Docker (GPU + offline)

Two Dockerfiles are provided:

| File                                | Base                              | When to use                                                                 |
|-------------------------------------|-----------------------------------|-----------------------------------------------------------------------------|
| `docker/Dockerfile`                 | `pytorch/pytorch:2.2.0-cuda12.1`  | Default. CPU-safe; CUDA works on Ampere/Ada (sm_80–sm_89).                   |
| `docker/Dockerfile.blackwell`       | `nvidia/cuda:12.8.0` + torch 2.7  | Required for **RTX 50-series / Blackwell (sm_120)** — the default image lacks kernels for those GPUs and will raise *"CUDA error: no kernel image is available for execution on the device"*. |

Build the default image:
```bash
docker build -f docker/Dockerfile -t safetrace:latest .
```

Build the Blackwell-capable image (RTX 50-series):
```bash
docker build -f docker/Dockerfile.blackwell -t safetrace:blackwell .
# then change `image:` in docker-compose.yml and set SAFETRACE_DEVICE: "auto"
```

Run with GPU and your local checkpoints / data mounted:
```bash
docker run --gpus all --rm -it \
    -p 8501:8501 \
    -v "$(pwd)/checkpoints:/app/checkpoints:ro" \
    -v "$(pwd)/data:/app/data" \
    safetrace:latest
```
Open http://localhost:8501.

CLI variants:
```bash
docker run --gpus all --rm \
    -v "$(pwd)/checkpoints:/app/checkpoints:ro" \
    -v "$(pwd)/data:/app/data" \
    safetrace:latest ingest /app/data/in.mp4

docker run --gpus all --rm \
    -v "$(pwd)/checkpoints:/app/checkpoints:ro" \
    -v "$(pwd)/data:/app/data" \
    safetrace:latest query "driver using phone" --k 5
```

---

## Configuration

All settings live in `src/config.py` and accept environment overrides:

| Env var                      | Default                                          | Purpose                          |
|------------------------------|--------------------------------------------------|----------------------------------|
| `SAFETRACE_DEVICE`           | `auto`                                           | `auto` / `cuda` / `cpu` (also switchable from the UI sidebar) |
| `SAFETRACE_OFFLINE`          | `1`                                              | Force HF + transformers offline  |
| `SAFETRACE_ENABLE_VLM`       | `0`                                              | Enable optional VLM explanations |
| `SAFETRACE_FPS`              | `1.0`                                            | Frame sampling FPS               |
| `SAFETRACE_TOPK`             | `5`                                              | Default semantic-search k        |
| `SAFETRACE_SIGLIP_DIR`       | `checkpoints/siglip-base-patch16-224`            | Embedding model dir              |
| `SAFETRACE_YOLO_CKPT`        | `checkpoints/yolov9c-seg.pt`                     | Detector weights                 |
| `SAFETRACE_MSAM_CKPT`        | `checkpoints/mobile_sam.pt`                      | MobileSAM weights                |
| `SAFETRACE_VLM_DIR`          | `checkpoints/vlm_model`                          | Optional VLM dir                 |
| `STREAMLIT_SERVER_MAX_UPLOAD_SIZE` | `51200`                                    | Per-file upload limit in **MB** (default 50 GB) |
| `STREAMLIT_SERVER_MAX_MESSAGE_SIZE`| `51200`                                    | Streamlit websocket message cap in **MB**       |

### Frontend controls

The Streamlit sidebar exposes:
- **Frame sampling FPS / Top-K / VLM toggle** — same semantics as the CLI flags.
- **Compute › Device** — switch between `cpu`, `cuda`, and `auto` at runtime.
  Changing the device transparently rebuilds the model cache. If `cuda` is
  selected on an image without GPU kernels for your card, the UI warns and
  falls back to CPU. For RTX 50-series GPUs use the Blackwell image (above).
- **Uploads** — local Streamlit runs default to the `.streamlit/config.toml`
  cap, and Docker runs can be tuned via `STREAMLIT_SERVER_MAX_UPLOAD_SIZE`
  (MB).

---

## Programmatic usage

```python
from src.pipeline import SafeTracePipeline

pipe = SafeTracePipeline()
pipe.ingest(["video.mp4", "image.jpg"], fps=1.0)
results = pipe.analyze_query("driver not wearing seatbelt", k=5)
# results: List[Dict] with frame metadata, detections, violations, explanation
```

Or, matching the spec signature:
```python
from src.pipeline import analyze_query
results = analyze_query("worker without helmet")
```

---

## Notes

- The system never reaches the network at runtime: HuggingFace offline flags
  are set in both the container and `src/config.py`.
- MobileSAM and the VLM are **optional**: if checkpoints are missing the
  pipeline degrades gracefully (YOLO masks only, deterministic explanations).
- YOLO label spaces vary across checkpoints; `src/config.py` contains a
  configurable `CLASS_ALIASES` map normalizing labels for the rule engine.

---

## Queued jobs and bulk ZIP uploads

The Streamlit UI now queues uploads instead of running heavy model inference
inside the upload click. After queueing a job, the app automatically starts a
background subprocess equivalent to:

```bash
python main.py worker --once
```

The UI returns immediately and reads job progress from `data/jobs`. The manual
worker commands are still available for debugging or CLI use:

```bash
python main.py worker --once
python main.py worker
```

Inspect queued/completed jobs:

```bash
python main.py job-status
python main.py job-status JOB_ID
```

While a selected job is `queued` or `processing`, the Streamlit UI can
auto-refresh every few seconds. The sidebar control **Auto-refresh while
processing** is enabled by default. Results are loaded only after the job
status becomes `completed`; until then the UI shows the current status, stage,
progress, processed frames, and media records.

Reviewer-facing confidence values are displayed as percentages in the UI
(`87%`, `92.5%`). Internal JSON fields keep decimal confidence values for
compatibility, with raw JSON available only inside optional expanders.

Queued job state and isolated outputs are stored under:

```text
data/jobs/{job_id}/job.json
data/jobs/{job_id}/outputs/index.faiss
data/jobs/{job_id}/outputs/metadata.json
data/jobs/{job_id}/outputs/results.json
```

The Streamlit uploader supports normal video files (`.mp4`, `.avi`, `.mov`,
`.mkv`, `.webm`) and bulk `.zip` uploads. A normal video upload keeps the
single-video queue flow. A ZIP upload is parsed as a batch and the ZIP file
itself is not sent through video ingestion.

Bulk upload ZIPs must contain top-level vehicle folders. The top-level folder
name becomes `vehicle_id`.

```text
upload.zip
  Vehicle_A/
    video1.mp4
  Vehicle_B/
    video2.mp4
```

Non-video files inside the ZIP are ignored. Unsafe paths and videos at the ZIP
root are rejected.

If a ZIP contains exactly one outer wrapper folder and multiple vehicle folders
inside it, SafeTrace treats the inner folders as vehicles:

```text
upload.zip
  test upload/
    Vehicle A/
      a.mp4
    Vehicle B/
      b.mp4
```

This produces `vehicle_id` values `Vehicle A` and `Vehicle B`.

Local Streamlit runs use `.streamlit/config.toml`, which sets:

```toml
[server]
maxUploadSize = 1024
```

The value is in MB. Increase it if your ZIP/video files are larger. Docker runs
still use the existing `STREAMLIT_SERVER_MAX_UPLOAD_SIZE` and
`STREAMLIT_SERVER_MAX_MESSAGE_SIZE` environment variables, which are passed by
`docker/entrypoint.sh`.

On Windows/local ML runtimes, SafeTrace sets these compatibility variables for
the auto-worker subprocess, so the user does not need to type them manually:

```text
TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1
KMP_DUPLICATE_LIB_OK=TRUE
OMP_NUM_THREADS=1
```

---

## Custom detector configuration

Place fine-tuned YOLO-compatible weights in `checkpoints/`, for example:

```text
checkpoints/driver-monitoring.pt
checkpoints/driver_classes.json
```

Configure them with:

```bash
set SAFETRACE_DETECTOR_WEIGHTS=checkpoints/driver-monitoring.pt
set SAFETRACE_DETECTOR_CLASSES_PATH=checkpoints/driver_classes.json
set SAFETRACE_DETECTOR_CONF_THRESHOLD=0.25
set SAFETRACE_DETECTOR_IOU_THRESHOLD=0.45
```

If `SAFETRACE_DETECTOR_WEIGHTS` is missing or points to a missing file,
SafeTrace logs a warning and falls back to the default YOLO checkpoint.

Runtime class mapping is JSON. Numeric keys map model class ids to canonical
SafeTrace labels, and aliases add extra raw label spellings:

```json
{
  "classes": {
    "0": "seatbelt",
    "1": "hand",
    "2": "steering_wheel",
    "3": "torso",
    "4": "face"
  },
  "aliases": {
    "seatbelt": ["seat belt", "safety belt"],
    "steering_wheel": ["steering wheel"]
  }
}
```

For fine-tuning, keep using the standard YOLO dataset YAML format required by
Ultralytics. The JSON file above is only the SafeTrace runtime mapping.

---

## Preprocessing and aggregation settings

Additional environment settings:

| Env var | Default | Purpose |
|---------|---------|---------|
| `SAFETRACE_TARGET_FPS` | `SAFETRACE_FPS` or `1.0` | Frame sampling rate |
| `SAFETRACE_MAX_FRAMES` | `600` | Per-video sampled frame cap |
| `SAFETRACE_FRAME_BATCH_SIZE` | `16` | Embedding batch size |
| `SAFETRACE_EMBED_WINDOW_SIZE` | `1` | Frames per embedding window |
| `SAFETRACE_EMBED_WINDOW_STRIDE` | `1` | Window stride |
| `SAFETRACE_SEATBELT_GRACE_SECONDS` | `15` | Initial missing-seatbelt grace period |
| `SAFETRACE_MAX_CONCURRENT_JOBS` | `1` | Documented local queue limit |
| `SAFETRACE_VIDEO_BATCH_SIZE` | `1` | Reserved for video batching policy |
| `SAFETRACE_MAX_UPLOAD_SIZE_MB` | `51200` | Upload size policy |
| `SAFETRACE_JOB_TIMEOUT_SECONDS` | `0` | Reserved timeout setting |

Video-level summaries aggregate all sampled frames/windows, not only top-k
query results. Top-k search is still available in completed job reports.

---

## Tests

Run the backend tests with:

```bash
python -m pytest
```
