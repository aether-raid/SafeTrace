# SafeTrace Desktop Release Package Prototype

Phase 9 prepares the package contract for the no-extra-steps user flow:

```text
1. Open the live SafeTrace website.
2. Run SafeTrace.exe or SafeTraceLauncher.exe locally.
3. Click Reconnect and use SafeTrace.
```

The backend executable remains update-friendly. MobileSAM, chat, and VLM assets
are bundled beside the runtime package, not embedded inside the backend binary.

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
    mobile_sam.pt
  models/
    chat/
      safetrace-assistant-qwen2.5-1.5b-instruct-q4.gguf
    vlm/
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
- `checkpoints/mobile_sam.pt` -> `checkpoints/mobile_sam.pt`
- `models/chat/*.gguf` -> `models/chat/`
- `models/vlm/**` -> `models/vlm/`

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
- `checkpoints/mobile_sam.pt`
- packaged chat GGUF when `SAFETRACE_CHAT_ENABLED` is not disabled and provider is `packaged_llamacpp`
- local VLM assets under `models/vlm/` when `SAFETRACE_VLM_ENABLED` is not disabled and provider is `auto`/local

Strict mode is allowed to fail on developer machines that do not have release
assets. The failure message names the missing paths.

## Runtime Environment

The release launcher resolves paths from the local SafeTrace folder:

```cmd
set SAFETRACE_PROJECT_ROOT=%APP_ROOT%
set SAFETRACE_DATA_DIR=%APP_ROOT%\data
set SAFETRACE_CHECKPOINTS_DIR=%APP_ROOT%\checkpoints
set SAFETRACE_MOBILESAM_CHECKPOINT=%APP_ROOT%\checkpoints\mobile_sam.pt
set SAFETRACE_CHAT_MODEL_PATH=%APP_ROOT%\models\chat\safetrace-assistant-qwen2.5-1.5b-instruct-q4.gguf
set SAFETRACE_VLM_MODEL_PATH=%APP_ROOT%\models\vlm
set SAFETRACE_VLM_DIR=%APP_ROOT%\models\vlm
set SAFETRACE_VLM_PROVIDER=auto
```

`SAFETRACE_VLM_PROVIDER=auto` prefers packaged local/non-Ollama VLM assets,
then optional local Ollama only if explicitly configured and available, then
rule-based explanations. Ollama is not required for the no-extra-steps release.

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
