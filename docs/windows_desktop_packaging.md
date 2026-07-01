# SafeTrace Windows Desktop Runtime

Phase 4 prepares SafeTrace for offline Windows desktop usage. It does not build
the final packaged `.exe`.

Phase 5 adds a prototype package layout under `dist/SafeTrace/`. That generated
folder is ignored and must not be committed.

## Development Launcher

Use:

```cmd
scripts\start_safetrace_windows.bat
```

The launcher can be called from any current directory. It changes into the repo
root, verifies `.venv\Scripts\python.exe`, verifies
`frontend-react\package.json`, then starts:

- FastAPI backend at `http://127.0.0.1:8000`
- React frontend at `http://127.0.0.1:5173`

It keeps backend and frontend logs visible in separate terminals and opens the
frontend URL after a short delay.

## Local Runtime Environment

The launcher sets local Windows-safe defaults:

```cmd
set KMP_DUPLICATE_LIB_OK=TRUE
set OMP_NUM_THREADS=1
set SAFETRACE_DEVICE=cpu
set SAFETRACE_ANALYSIS_SAFE_MODE=true
set SAFETRACE_CHAT_ENABLED=auto
set SAFETRACE_CHAT_PROVIDER=packaged_llamacpp
set SAFETRACE_CHAT_SPEED_PROFILE=fast
set SAFETRACE_CHAT_MODEL_PATH=%APP_ROOT%\models\chat\safetrace-assistant-qwen2.5-1.5b-instruct-q4.gguf
set SAFETRACE_SIGLIP_DIR=%APP_ROOT%\checkpoints\siglip-base-patch16-224
set SAFETRACE_YOLO_CKPT=%APP_ROOT%\checkpoints\yolov9c-seg.pt
set SAFETRACE_YOLO_FALLBACK_CKPT=%APP_ROOT%\checkpoints\yolov8s-seg.pt
set SAFETRACE_MOBILESAM_ENABLED=false
set SAFETRACE_MOBILESAM_CHECKPOINT=%APP_ROOT%\checkpoints\mobile_sam.pt
set SAFETRACE_VLM_ENABLED=false
set SAFETRACE_VLM_PROVIDER=auto
set SAFETRACE_VLM_PROFILE=rule_based
set SAFETRACE_VLM_MODEL_PATH=%APP_ROOT%\models\vlm
set SAFETRACE_VLM_DIR=%APP_ROOT%\models\vlm
set SAFETRACE_VLM_OLLAMA_BASE_URL=http://127.0.0.1:11434
set SAFETRACE_VLM_MODEL=local-vlm
```

`KMP_DUPLICATE_LIB_OK=TRUE` is a local development workaround for duplicate
OpenMP runtime issues on some Windows Python/ML installs. It is reported by
`GET /api/system/status` so users can see whether the process was launched with
the workaround enabled.

## Future Packaged App Layout

The expected future installer layout is:

```text
SafeTrace/
  SafeTrace.exe or SafeTraceLauncher.exe
  backend/
    safetrace-backend.exe
  frontend/
  .venv/ or packaged Python runtime/
  checkpoints/
    siglip-base-patch16-224/
    yolov8s-seg.pt
    mobile_sam.pt
    yolov9c-seg.pt optional
  models/chat/
    safetrace-assistant-qwen2.5-1.5b-instruct-q4.gguf
  models/vlm/
    lightweight-256m/
      <local/non-Ollama VLM assets>
  config/
    safetrace.env
  data/
  logs/
```

The packaged app should start the backend first, then serve or open the frontend.
The same environment defaults above should be applied by the app launcher.

## Prototype Package Layout

Create the local prototype package with:

```cmd
python scripts\build_desktop_prototype.py --clean
```

The script creates `dist/SafeTrace/` with:

- `SafeTraceLauncher.bat`
- `backend/`
- `frontend/dist/`
- `config/safetrace.env.example`
- `models/chat/`
- `models/vlm/`
- `checkpoints/`
- `data/`
- `logs/`
- `packaging_manifest.json`

The prototype does not build a final backend `.exe`. It can copy an existing
local `dist/backend/safetrace-backend.exe` into the generated package. It also
copies approved local release assets when they already exist:

- `checkpoints/siglip-base-patch16-224/`
- `checkpoints/yolov8s-seg.pt`
- `checkpoints/yolov9c-seg.pt` when present
- `checkpoints/mobile_sam.pt`
- `models/chat/*.gguf`
- `models/vlm/lightweight-256m/**`

It never copies uploads, generated evidence, reports, or local caches.
Generated package output remains ignored and must not be committed.

The builder writes `OPTIONAL_ASSETS_REPORT.txt` inside the generated package.
Use `python scripts\build_desktop_prototype.py --dry-run --strict-assets` to
validate that release assets are present before distribution.

The generated `SafeTraceLauncher.bat` waits up to 90 seconds for backend health,
prints progress every 5 seconds, avoids starting a duplicate supervisor when a
healthy backend is already running, and prints startup diagnostics on timeout.
The supervisor restarts `backend\safetrace-backend.exe` after unexpected exits
with a short delay and writes logs under `dist\SafeTrace\logs`.

Phase 6 adds a backend executable prototype. The dry-run command is:

```cmd
python scripts\build_backend_exe.py
```

Developers with PyInstaller installed can attempt a local build with:

```cmd
python scripts\build_backend_exe.py --run
```

For assistant runtime support, build with the Python environment that has
`llama-cpp-python` installed:

```cmd
.venv\Scripts\python.exe scripts\build_backend_exe.py --run
```

Using a global Python without `llama_cpp` can produce a backend executable that
finds the GGUF model file but reports the packaged assistant runtime as
missing. Chat remains optional; analysis still works with rule-based fallback.

Generated backend executable output belongs under `dist/backend/` and must not
be committed. If `dist/backend/safetrace-backend.exe` exists, the desktop
package builder copies it into `dist/SafeTrace/backend/safetrace-backend.exe`.
If it is missing, the package builder still creates the placeholder backend
folder.

The generated `SafeTraceLauncher.bat` starts a backend supervisor with
`--app-root`, writes backend stdout/stderr to
`logs\backend_launcher_stdout.log` and `logs\backend_launcher_stderr.log`,
restarts the backend if it exits unexpectedly, and waits for
`http://127.0.0.1:8000/api/health`. If the backend does not become healthy, the
launcher exits with an error and prints the latest log lines. Run foreground
mode when debugging a packaged runtime:

```cmd
dist\SafeTrace\SafeTraceLauncher.bat --foreground
```

If a developer runs `backend\safetrace-backend.exe` directly from the package,
the frozen entrypoint infers the parent `SafeTrace/` folder as its app root. The
launcher remains preferred because it also sets the release environment,
captures logs, and performs the health check.

## Packaged Frontend Serving

The FastAPI backend can serve the React production build in packaged mode:

```cmd
set SAFETRACE_SERVE_FRONTEND=true
set SAFETRACE_FRONTEND_DIST=frontend/dist
```

When enabled, `/` serves the React app, `/assets/*` serves static assets, and
unknown frontend routes fall back to `index.html`. `/api/*` remains API-only.
Vite development mode remains supported by leaving `SAFETRACE_SERVE_FRONTEND`
unset or false.

## Hybrid Live Frontend Mode

Phase 7 also supports a public static React frontend that connects to the local
SafeTrace runtime on the user's computer. The live website stays locked until
the local backend responds on:

```text
http://127.0.0.1:8000/api/health
http://127.0.0.1:8000/api/system/status
```

For local development, use:

```cmd
scripts\start_safetrace_windows.bat
```

For a deployed live frontend, configure the backend with the exact live origin:

```cmd
set SAFETRACE_ALLOWED_ORIGINS=https://your-site.pages.dev
```

The backend still binds to `127.0.0.1` by default. Do not expose it to the LAN
or use unrestricted CORS origins for the public website flow. See
`docs/live_frontend_deployment.md`.

The release-facing user flow is:

1. Open the live SafeTrace website.
2. If it reports the runtime is disconnected, run `SafeTrace.exe` locally.
3. Click `Reconnect to Local Runtime`.
4. Analyze media locally.

## Update-Friendly Backend Executable Design

The future backend executable should be a replaceable component, not a hard to
update monolith. Prefer this install shape:

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
  data/
    api_jobs/
    reports/
    uploads/
  logs/
```

Keep `config/`, `data/`, `models/`, `checkpoints/`, and `logs/` outside the backend runtime
folder. The launcher should point the backend to those external paths with
environment variables so a backend replacement never overwrites user data,
generated reports, local model files, the GGUF chat model, or local settings.

SigLIP, YOLO, MobileSAM, and lightweight VLM assets should be bundled with the
no-extra-steps release package. Embedding uses
`checkpoints/siglip-base-patch16-224/`; detector fallback uses
`checkpoints/yolov8s-seg.pt`; optional primary detection can use
`checkpoints/yolov9c-seg.pt` when present. MobileSAM refinement uses
`checkpoints/mobile_sam.pt` when present and otherwise falls back to
detector-box evidence. VLM explanations can use packaged
`models/vlm/lightweight-256m/` assets after explicit activation, optional local
Ollama only when explicitly configured/available, and otherwise fall back to
rule-based explanation text. Enhanced VLM assets are not included in the
prototype package. Ollama is optional and is not required for the release
package. The SafeTrace Assistant remains a separate chat feature and uses
`models/chat/`.

A future updater should:

1. Stop the backend process.
2. Stage the new backend folder in a temporary location.
3. Verify `backend_manifest.json` and file hashes before replacement.
4. Move the current `backend/` folder to a rollback backup.
5. Move the verified backend folder into place.
6. Restart the backend and check `/api/health` plus `/api/system/status`.

If startup or status checks fail, restore the previous backend folder and leave
`config/`, `data/`, `models/`, and `logs/` untouched. See
`docs/backend_exe_update_strategy.md` and
`packaging/backend_manifest.example.json` for the detailed backend design note.
See `docs/desktop_packaging_prototype.md` and
`packaging/desktop_packaging_manifest.example.json` for the desktop package
prototype contract.
See `docs/backend_executable_prototype.md` for the backend executable prototype
strategy, PyInstaller/Nuitka tradeoff, PyTorch/CUDA risks, and rollback flow.

## Model Files

Do not commit local model assets:

- `*.gguf`
- `*.bin`
- `*.safetensors`
- `*.pt`
- `*.pth`
- `*.onnx`
- `models/chat/*.gguf`
- `models/vlm/**`
- `data/`
- `uploads/`
- `generated/`
- `generated_media/`
- `checkpoints/`
- model assets

The approved packaged chat model filename is:

```text
models/chat/safetrace-assistant-qwen2.5-1.5b-instruct-q4.gguf
```

Main SafeTrace analysis continues to work if the chat model or llama-cpp runtime
is missing. The assistant reports structured missing-model or missing-runtime
states instead of blocking upload or analysis.
