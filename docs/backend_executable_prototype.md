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
SAFETRACE_FRONTEND_DIST=<app root>\frontend\dist
SAFETRACE_MOBILESAM_CHECKPOINT=<app root>\checkpoints\mobile_sam.pt
SAFETRACE_VLM_PROVIDER=auto
SAFETRACE_VLM_MODEL_PATH=<app root>\models\vlm
SAFETRACE_VLM_DIR=<app root>\models\vlm
```

The real `config/safetrace.env` can override those defaults on an installed
machine.

## Live Frontend Bridge

The backend executable should start the local API on `127.0.0.1:8000` so a
public static SafeTrace website can discover it from the user's browser. The
website remains locked until `/api/health` and `/api/system/status` respond.

For a deployed live frontend, set:

```cmd
SAFETRACE_ALLOWED_ORIGINS=https://your-site.pages.dev
```

Do not switch the backend bind address to `0.0.0.0` for this flow. Keep the
runtime local and update the allowed origin list instead.

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

The packaged local LLM remains external to the backend executable. Main
SafeTrace upload, ZIP/batch upload, and analysis flows must still start if the
chat model or llama-cpp runtime is missing.

MobileSAM and VLM assets also remain external to the executable but should be
bundled with the local SafeTrace package. A one-dir PyInstaller backend should
not embed `checkpoints/mobile_sam.pt` or `models/vlm/`; the desktop package may
place them at `SafeTrace/checkpoints/mobile_sam.pt` and `SafeTrace/models/vlm/`
instead. A one-file executable is not preferred for checkpoints because
replacing the backend should not overwrite data, config, logs, GGUF chat
models, or safety model assets.

The optional VLM provider is local-only. Auto mode preserves the existing local
transformer VLM provider first using packaged `models/vlm/` assets and may call
a local Ollama vision runtime on `127.0.0.1` only as an optional provider.
Ollama is not required for the no-extra-steps release. SafeTrace must not use
cloud VLM APIs or upload frames/images/videos to internet services.

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
