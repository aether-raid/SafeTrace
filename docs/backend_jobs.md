# SafeTrace Backend Jobs

The FastAPI backend stores each analysis job under `data/api_jobs/<job_id>/`.
Every job now has a `manifest.json` with status, progress, timestamps, input
metadata, result path, media artifacts, and basic timing metrics. Completed
results are written to `result.json` so completed and failed jobs can be
rediscovered after a backend restart.

If the backend finds a queued or running job that has not been updated within
`SAFETRACE_STALE_RUNNING_MINUTES`, it marks that job as failed with
`Job interrupted by backend restart.` This keeps polling clients from waiting on
jobs that were active when the process exited.

Upload bounds:

- `SAFETRACE_MAX_UPLOAD_MB` controls the FastAPI upload limit. Default: `512`.
- `/api/analyze` accepts one uploaded image or video per job.
- `/api/batches/analyze` accepts either one ZIP archive of videos or multiple
  uploaded video files. Each accepted video becomes a normal persisted analysis
  job.
- Only SafeTrace image/video extensions are accepted:
  `.avi`, `.bmp`, `.jpeg`, `.jpg`, `.mkv`, `.mov`, `.mp4`, `.png`, `.webm`,
  `.webp`.
- Bulk analysis accepts video extensions only: `.avi`, `.mkv`, `.mov`, `.mp4`,
  `.webm`.
- Filenames are sanitized before being written into a job upload directory.
- ZIP entries are inspected before extraction. Absolute paths, drive-qualified
  paths, and `..` path traversal entries are rejected before files are accepted.
- `SAFETRACE_BULK_MAX_FILES` controls the maximum number of files in one bulk
  request. Default: `25`.
- `SAFETRACE_BULK_MAX_UNCOMPRESSED_MB` controls the maximum total uncompressed
  ZIP size. Default: `2048`.
- Unsupported or empty files inside an otherwise valid bulk upload are reported
  in the batch manifest as rejected files with reasons.
- `SAFETRACE_MAX_VIDEO_SECONDS` can enforce a duration cap during frame
  extraction. Default: `0`, which means no duration cap is enforced beyond the
  sampled-frame limit.
- `/api/system/status` reports this as `maxVideoDurationUnlimited: true` with a
  warning message when the cap is disabled.
- `SAFETRACE_MAX_FRAMES` controls the maximum sampled frames per ingest. Default:
  `600`.

Preprocessing metadata:

- Video sampling remains fixed-FPS by default and does not load the whole video
  into memory.
- Results include `technicalDetails.processingMetadata` with sampling strategy,
  sampled frame count, processing window count, embedding batch count, embedding
  batch size, window size, stride, and pooling strategy.
- The default embedding representation remains one frame per vector with mean
  pooling, preserving the previous behavior.
- `SAFETRACE_EMB_WINDOW_SIZE` and `SAFETRACE_EMB_WINDOW_STRIDE` can group
  sampled frames into embedding windows for comparison.
- `SAFETRACE_EMB_POOLING` supports `mean` and `max`. Attention pooling and
  temporal models are intentionally future work, not production defaults.

Event aggregation:

- The API result now includes optional `events` and summary event fields.
- Events group nearby repeated frame-level findings of the same violation type
  into potential video-level incidents.
- Raw frame-level evidence remains in `frames` and in the technical JSON.
- Aggregation is presentation/reporting logic only; detector outputs, model
  behavior, ML thresholds, and rule behavior are unchanged.

Retention:

- `SAFETRACE_JOB_RETENTION_HOURS` controls cleanup eligibility. Default: `24`.
- Completed, failed, and cancelled jobs older than the retention window can be
  removed by the job cleanup utility.
- Running or queued jobs are first marked interrupted if stale.
- Cleanup and explicit `DELETE /api/jobs/{job_id}` refuse to delete outside the
  configured API job root.
- Batch manifests are stored under `data/api_batches/<batch_id>/`. Explicit
  `DELETE /api/batches/{batch_id}` removes the batch manifest and its owned jobs,
  using the same path-safety checks.

Queue behavior:

- Jobs are persisted as `queued` before execution starts.
- Execution uses a per-job lock file to prevent duplicate processing of the same
  queued job.
- `SAFETRACE_WORKER_CONCURRENCY` limits concurrent in-process analysis workers.
- If the backend restarts while a queued or running job is stale, recovery marks
  it failed with `Job interrupted by backend restart.` and removes the stale lock.
- Batch status is derived from owned job statuses. Completed jobs remain
  available through the existing `/api/jobs/{job_id}/result` endpoint.

Benchmarking:

```cmd
python scripts/benchmark_safetrace_limits.py
python scripts/benchmark_safetrace_limits.py --json
python scripts/benchmark_safetrace_limits.py --jobs-root path\to\api_jobs
python scripts/benchmark_pooling_strategies.py
python scripts/benchmark_pooling_strategies.py --embeddings-npy data\embeddings.npy --window-size 4 --stride 2
```

The benchmark scripts do not read videos, run detectors, load checkpoints,
perform segmentation, run VLM, or perform model inference. The pooling benchmark
compares mean and max pooling over synthetic or existing embedding arrays only.

Lower CPU/RAM guidance:

- Keep `SAFETRACE_WORKER_CONCURRENCY=1`.
- Reduce `SAFETRACE_MAX_UPLOAD_MB`, `SAFETRACE_MAX_FRAMES`, and
  `SAFETRACE_EMB_BATCH`.
- Keep `SAFETRACE_EMB_WINDOW_SIZE=1` unless comparing pooling strategies.

This remediation pass does not improve detector quality, add fine-tuning,
change ML thresholds, alter detector behavior, alter model logic, or change
violation rule behavior.
