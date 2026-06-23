# Backend EXE Update Strategy

Future SafeTrace Windows builds should treat the backend executable as a
replaceable runtime component, not a monolithic artifact that owns user data,
configuration, logs, frontend assets, or local model files.

## Why Replaceable Backend Runtime

SafeTrace backend updates may need to fix API behavior, queue hardening,
normalization, packaging, or dependency issues without replacing local evidence
data or large offline model assets. A versioned backend runtime folder lets
developers replace only backend binaries and dependencies while preserving:

- user data
- uploaded media
- generated reports
- local configuration
- logs
- checkpoints and model assets
- GGUF chat models
- frontend assets when the UI did not change

## Recommended Installed Layout

```text
SafeTrace/
  SafeTraceLauncher.exe
  backend/
    safetrace-backend.exe
    backend_manifest.json
    runtime dependencies...
  frontend/
    dist/
  config/
    safetrace.env
  models/
    chat/
      safetrace-assistant-qwen2.5-1.5b-instruct-q4.gguf
  data/
    api_jobs/
    reports/
    uploads/
  logs/
```

The launcher should pass explicit external paths to the backend through
environment variables. Backend builds should never assume data, configuration,
models, or logs live inside the backend executable folder.

## What Stays Outside The Backend EXE

Keep these paths external and preserved across backend updates:

- `config/`
- `data/`
- `models/`
- `logs/`
- uploaded media
- generated reports
- checkpoints and model assets
- GGUF chat model files

Do not commit or embed these assets in backend builds:

- `*.gguf`
- `*.bin`
- `*.safetensors`
- `*.pt`
- `*.pth`
- `data/`
- `uploads/`
- `generated/`
- `generated_media/`
- `checkpoints/`
- model assets

## Safe Backend Update Flow

1. Stop the running backend process.
2. Download or copy the new backend package to a temporary staging folder.
3. Verify `backend_manifest.json`, version compatibility, and file hashes before
   replacing anything.
4. Move the existing `backend/` folder to a timestamped backup folder.
5. Move the staged backend folder into place.
6. Restart the backend through `SafeTraceLauncher.exe`.
7. Check `GET /api/health` and `GET /api/system/status`.
8. Keep `config/`, `data/`, `models/`, and `logs/` untouched.

The updater should fail closed: if manifest verification or health checks fail,
restore the previous backend folder.

## Rollback Flow

1. Stop the backend.
2. Rename the failed `backend/` folder to a diagnostic backup.
3. Restore the last known-good backend folder.
4. Restart the backend.
5. Confirm `/api/health` returns `ok` and `/api/system/status` reports the
   expected `backend_version`, `build_mode`, and `runtime_layout`.

Rollback must not modify user uploads, generated reports, local config, logs, or
model files.

## Frontend And Backend Compatibility

Backend packages should publish a manifest field such as
`requires_frontend_version`. The launcher or future updater should compare this
against the installed frontend bundle before replacing the backend. If a backend
requires a newer frontend contract, ship backend and frontend together as a
coordinated update.

The backend status endpoint exposes lightweight metadata:

- `app_version`
- `backend_version`
- `build_mode`
- `runtime_layout`

These fields are static or environment-driven defaults in source/development
mode and should come from the package manifest in future executable builds.

## Why Models Should Not Be Embedded

GGUF files and other model assets are large, licensed separately, and updated on
a different cadence than backend code. Embedding them in `safetrace-backend.exe`
would make every backend patch heavy, harder to verify, and risk overwriting
user-managed offline model files. Keep model assets in external `models/` or
`checkpoints/` folders and preserve those folders across backend updates.
