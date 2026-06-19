# SafeTrace FastAPI Backend Integration

This backend layer prepares SafeTrace for a later React-to-local-API integration while preserving the existing CLI and Streamlit workflows.

## Local Development

Install the backend/API dependencies from the Docker requirements file, then run the API on localhost only:

```cmd
python -m pip install -r docker\requirements.txt
python -m uvicorn src.api.server:app --host 127.0.0.1 --port 8000
```

The API is designed for offline local use. It does not upload media to cloud services and should be bound to `127.0.0.1` for desktop development.

## Endpoints

- `GET /api/health` returns process health without loading models.
- `GET /api/system/status` reports checkpoint/path readiness without instantiating the SafeTrace pipeline.
- `POST /api/analyze` accepts multipart media plus `query`, `fps`, `topK`, `enableVlm`, and `device`, then returns a queued job ID.
- `GET /api/jobs/{job_id}` returns job status and progress.
- `GET /api/jobs/{job_id}/result` returns the normalized React-friendly analysis result once complete.
- `GET /api/media/{job_id}/{filename}` serves registered annotated evidence images for that job only.
- `GET /api/reports/{job_id}/technical-json` returns normalized results plus technical job details.
- `DELETE /api/jobs/{job_id}` clears uploaded media and generated job artifacts for that job.

## Model Loading

The FastAPI app does not instantiate `SafeTracePipeline` at import time. Heavy model construction is isolated inside background job execution for `/api/analyze`. Health and system status checks only inspect configuration paths and local availability.

Missing required checkpoints are reported as API status fields such as `"missing"`. Missing optional checkpoints are reported as `"unavailable"` where appropriate.

## Result Shape

Pipeline-style frame dictionaries are normalized into:

- a media summary,
- aggregate analysis summary,
- grouped violations with affected frames,
- per-frame evidence records,
- job-owned image URLs for annotated frames,
- technical evidence for debugging and report export.

If an annotated image path is absent or unavailable, the API returns `imageUrl: null` and an explanatory `imageMessage` instead of exposing arbitrary local files.

## Testing

Run the targeted backend API tests without loading model checkpoints:

```cmd
python -m pytest tests -q
```

The tests monkeypatch pipeline execution and use temporary job directories.

## Later React Connection

The React frontend can later replace sample/mock analysis calls with:

1. `GET /api/health` on app startup.
2. `GET /api/system/status` to render backend/model readiness.
3. `POST /api/analyze` when the user starts analysis.
4. Polling `GET /api/jobs/{job_id}` until completion.
5. `GET /api/jobs/{job_id}/result` to render findings and evidence frames.
6. `GET /api/media/{job_id}/{filename}` URLs directly in `<img>` elements.
7. `GET /api/reports/{job_id}/technical-json` for technical export.

No React files are changed by this backend task.

## Future Desktop Direction

A future packaged desktop app can use a React UI packaged by Tauri or a similar shell, with the Python FastAPI backend packaged as a local sidecar executable. The backend should bind only to `127.0.0.1`, models should live outside Git beside the packaged app, and analysis should remain offline against user-selected local or thumbdrive media.
