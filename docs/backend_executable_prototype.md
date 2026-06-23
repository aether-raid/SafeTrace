# Backend Executable Prototype

Phase 6 adds a prototype path for building a local Windows backend executable.
It does not commit a built `.exe` and does not commit PyInstaller output.

## Strategy

SafeTrace keeps the FastAPI application in source form and exposes a packaging
entrypoint at:

```text
src/api/__main__.py
```

The executable prototype uses PyInstaller:

```text
packaging/backend/safetrace_backend.spec
scripts/build_backend_exe.py
```

PyInstaller is the lower-risk prototype because it can wrap the existing Python
entrypoint without changing FastAPI routing, queue behavior, analysis pipeline
logic, or model loading behavior. Nuitka may be evaluated later for startup or
runtime performance, but it has a larger compiler/toolchain surface for this
Windows prototype.

## Dry Run

From the repository root:

```cmd
python scripts\build_backend_exe.py
```

The default mode prints the PyInstaller command and exits without creating
build output. To attempt a local build on a developer machine that already has
PyInstaller installed:

```cmd
python scripts\build_backend_exe.py --run
```

Do not commit generated output. Expected local output is ignored:

```text
build/
dist/backend/
*.exe
*.spec-generated
```

## Expected Executable Location

The prototype expects the local build to produce:

```text
dist/backend/safetrace-backend.exe
```

The desktop package builder can copy that file into:

```text
dist/SafeTrace/backend/safetrace-backend.exe
```

If the executable is absent, the package builder still creates the prototype
layout and prints a warning.

## External Runtime Paths

These paths remain outside the backend executable:

```text
config/
models/
data/
logs/
frontend/
checkpoints/
```

The entrypoint sets packaged defaults such as:

```cmd
SAFETRACE_PROJECT_ROOT=<app root>
SAFETRACE_DATA_DIR=<app root>\data
SAFETRACE_CHECKPOINTS_DIR=<app root>\checkpoints
SAFETRACE_SERVE_FRONTEND=true
SAFETRACE_FRONTEND_DIST=frontend\dist
```

The real `config/safetrace.env` can override those defaults on an installed
machine.

## What Must Never Be Embedded Or Committed

Do not bundle or commit:

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
- uploaded videos
- generated reports
- local logs

The packaged local LLM remains optional. Main SafeTrace upload, ZIP/batch
upload, and analysis flows must still start if the chat model or llama-cpp
runtime is missing.

## PyTorch And CUDA Risks

PyTorch, OpenCV, and model-adjacent packages can make Windows executable builds
large and sensitive to DLL discovery. CUDA builds are especially risky because
drivers and GPU runtime libraries belong to the installed machine, not to the
SafeTrace backend executable contract. Keep models and machine-specific runtime
configuration external so backend patches remain replaceable.

If a one-file executable becomes unreliable, switch the backend runtime folder
to a one-dir PyInstaller layout while preserving the same package boundary:

```text
SafeTrace/backend/
```

The launcher and updater should still treat `backend/` as replaceable while
preserving `config/`, `data/`, `models/`, `logs/`, and `frontend/`.

## Update And Rollback

Update flow:

1. Stop the backend.
2. Stage the new backend executable or backend runtime folder.
3. Verify `backend_manifest.json` and hashes.
4. Move the current `backend/` folder to a timestamped backup.
5. Move the staged backend into place.
6. Restart and check `/api/health` plus `/api/system/status`.

Rollback flow:

1. Stop the backend.
2. Move the failed `backend/` folder aside for diagnostics.
3. Restore the last known-good backend folder.
4. Restart and recheck `/api/health` and `/api/system/status`.

Rollback must not alter local config, data, logs, frontend assets, checkpoints,
or model files.
