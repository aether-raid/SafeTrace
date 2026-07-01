# SafeTrace Desktop Release Package Prototype

Phase 9 prepares the package contract for the no-extra-steps user flow:

```text
1. Open the live SafeTrace website.
2. Run SafeTrace.exe or SafeTraceLauncher.exe locally.
3. Click Reconnect and use SafeTrace.
```

The backend executable remains update-friendly. SigLIP, YOLO, MobileSAM, chat,
and lightweight VLM assets are bundled beside the runtime package, not embedded
inside the backend binary.

Phase 13 main tester package:

```text
SafeTrace_RC_SafeMode_RuleBased
```

This package defaults to CPU Safe Mode, rule-based visual explanations, improved
object/rule frame ranking, packaged chatbot support, MobileSAM disabled, and VLM
disabled. MobileSAM and Lightweight VLM assets may still be copied as optional
package assets, but Enhanced VLM assets are excluded.

## Create The Prototype Package

From the repository root:

```cmd
python scripts\build_desktop_prototype.py --clean
```

Dry run:

```cmd
python scripts\build_desktop_prototype.py --dry-run
```

Strict release validation:

```cmd
python scripts\build_desktop_prototype.py --dry-run --strict-assets
```

Strict mode fails clearly when release assets are missing. Non-strict mode still
creates a package skeleton and writes placeholder README files.

## Release Runtime Layout

The intended generated package layout is:

```text
dist/SafeTrace/
  SafeTrace.exe or SafeTraceLauncher.exe
  SafeTraceLauncher.bat
  OPTIONAL_ASSETS_REPORT.txt
  backend/
    safetrace-backend.exe
    backend_manifest.json
  frontend/
    dist/
  config/
    safetrace.env
    safetrace.env.example
  checkpoints/
    siglip-base-patch16-224/
    yolov8s-seg.pt
    mobile_sam.pt
    yolov9c-seg.pt              optional, when present
  models/
    chat/
      safetrace-assistant-qwen2.5-1.5b-instruct-q4.gguf
    vlm/
      lightweight-256m/
        <local/non-Ollama VLM assets>
  data/
  logs/
  packaging_manifest.json
```

`dist/SafeTrace/` is generated output and must not be committed.

## Packaged Assets

The package builder includes these local assets only when they already exist on
the developer machine:

- `dist/backend/safetrace-backend.exe` -> `backend/safetrace-backend.exe`
- `config/safetrace.env` -> `config/safetrace.env`
- `checkpoints/siglip-base-patch16-224/` -> `checkpoints/siglip-base-patch16-224/`
- `checkpoints/yolov8s-seg.pt` -> `checkpoints/yolov8s-seg.pt`
- `checkpoints/yolov9c-seg.pt` -> `checkpoints/yolov9c-seg.pt` when present
- `checkpoints/mobile_sam.pt` -> `checkpoints/mobile_sam.pt`
- `models/chat/*.gguf` -> `models/chat/`
- `models/vlm/lightweight-256m/**` -> `models/vlm/lightweight-256m/`

Missing assets do not fail non-strict mode. The builder writes README
placeholders in generated package folders and writes:

```text
dist/SafeTrace/OPTIONAL_ASSETS_REPORT.txt
```

The report lists each asset, source path, package target, included/missing
status, and whether strict mode requires it.

## Strict Asset Validation

`--strict-assets` requires:

- backend executable
- `config/safetrace.env`
- `checkpoints/siglip-base-patch16-224/`
- `checkpoints/yolov8s-seg.pt`
- `checkpoints/mobile_sam.pt`
- packaged chat GGUF when `SAFETRACE_CHAT_ENABLED` is not disabled and provider is `packaged_llamacpp`

`checkpoints/yolov9c-seg.pt` is copied when present but is not required by
strict validation. The packaged default detector fallback remains
`checkpoints/yolov8s-seg.pt`.

`models/vlm/lightweight-256m/` is copied when present as an optional asset, but
the main Safe Mode release keeps `SAFETRACE_VLM_ENABLED=false`, so Lightweight
VLM is not required for the stable package to start or analyze.

Strict mode is allowed to fail on developer machines that do not have release
assets. The failure message names the missing paths.

## Runtime Environment

The release launcher resolves paths from the local SafeTrace folder:

```cmd
set SAFETRACE_PROJECT_ROOT=%APP_ROOT%
set SAFETRACE_DATA_DIR=%APP_ROOT%\data
set SAFETRACE_CHECKPOINTS_DIR=%APP_ROOT%\checkpoints
set SAFETRACE_DEVICE=cpu
set SAFETRACE_ANALYSIS_SAFE_MODE=true
set SAFETRACE_SIGLIP_DIR=%APP_ROOT%\checkpoints\siglip-base-patch16-224
set SAFETRACE_YOLO_CKPT=%APP_ROOT%\checkpoints\yolov9c-seg.pt
set SAFETRACE_YOLO_FALLBACK_CKPT=%APP_ROOT%\checkpoints\yolov8s-seg.pt
set SAFETRACE_MOBILESAM_ENABLED=false
set SAFETRACE_MOBILESAM_CHECKPOINT=%APP_ROOT%\checkpoints\mobile_sam.pt
set SAFETRACE_CHAT_MODEL_PATH=%APP_ROOT%\models\chat\safetrace-assistant-qwen2.5-1.5b-instruct-q4.gguf
set SAFETRACE_VLM_ENABLED=false
set SAFETRACE_VLM_PROFILE=rule_based
set SAFETRACE_VLM_MODEL_PATH=%APP_ROOT%\models\vlm
set SAFETRACE_VLM_DIR=%APP_ROOT%\models\vlm
set SAFETRACE_VLM_PROVIDER=auto
```

The main release keeps `SAFETRACE_VLM_ENABLED=false`. Lightweight local VLM
assets are optional package contents for later explicit experimental activation;
they are not loaded by the Safe Mode release. Enhanced VLM assets are not
included in this prototype package. Ollama is not required for the no-extra-steps
release.

`SafeTraceLauncher.bat` starts a small backend supervisor with `--app-root`
pointed at the local package folder, writes backend stdout/stderr under
`logs/`, restarts the backend if it exits unexpectedly, and waits for
`http://127.0.0.1:8000/api/health`. The packaged health wait is 90 seconds and
prints progress every 5 seconds because the PyInstaller runtime and local ML
imports can take a while to initialize on Windows. If health never becomes
ready, the launcher exits with an error and prints process status, the port 8000
occupant, Safe Mode environment values, the backend command, and the last log
lines. Use foreground mode to debug startup failures directly:

```cmd
dist\SafeTrace\SafeTraceLauncher.bat --foreground
```

When the frozen backend executable is launched directly from `backend/`, it
also infers the parent `SafeTrace/` folder as its app root. The launcher remains
the recommended path because it applies environment defaults, logging, and the
health check.

If the assistant model is found but the assistant runtime is missing, rebuild
the backend executable from the Python environment that has `llama-cpp-python`
installed:

```cmd
.venv\Scripts\python.exe scripts\build_backend_exe.py --run
```

The assistant remains optional; missing `llama_cpp` does not block upload,
single-video analysis, batch analysis, MobileSAM, or rule-based explanation
fallback.

## Live Frontend Flow

The live static frontend remains the preferred user entry point:

1. Open the live SafeTrace URL.
2. If disconnected, run `SafeTrace.exe` on this computer.
3. Click `Reconnect to Local Runtime`.
4. Upload media and analyze locally.

The local backend should allow the exact live origin through
`SAFETRACE_ALLOWED_ORIGINS`. The backend remains bound to `127.0.0.1` by
default.

## Source Control Rules

Do not commit:

- `.exe`
- `dist/`
- `frontend-react/dist/`
- `dist/SafeTrace/`
- model/checkpoint files such as `.pt`, `.pth`, `.bin`, `.safetensors`, `.onnx`, `.gguf`
- uploaded videos
- generated media
- reports
- local caches

The package builder copies approved assets only into ignored generated output.
It never requires those assets to be tracked by Git.
