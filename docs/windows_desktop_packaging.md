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
root, verifies `.venv\Scripts\activate.bat`, verifies
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
set SAFETRACE_CHAT_ENABLED=auto
set SAFETRACE_CHAT_PROVIDER=packaged_llamacpp
set SAFETRACE_CHAT_SPEED_PROFILE=fast
set SAFETRACE_CHAT_MODEL_PATH=%APP_ROOT%\models\chat\safetrace-assistant-qwen2.5-1.5b-instruct-q4.gguf
set SAFETRACE_MOBILESAM_ENABLED=auto
set SAFETRACE_MOBILESAM_CHECKPOINT=%APP_ROOT%\checkpoints\mobile_sam.pt
set SAFETRACE_VLM_ENABLED=auto
set SAFETRACE_VLM_PROVIDER=auto
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
    mobile_sam.pt
  models/chat/
    safetrace-assistant-qwen2.5-1.5b-instruct-q4.gguf
  models/vlm/
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

- `checkpoints/mobile_sam.pt`
- `models/chat/*.gguf`
- `models/vlm/**`

It never copies uploads, generated evidence, reports, or local caches.
Generated package output remains ignored and must not be committed.

The builder writes `OPTIONAL_ASSETS_REPORT.txt` inside the generated package.
Use `python scripts\build_desktop_prototype.py --dry-run --strict-assets` to
validate that release assets are present before distribution.

Phase 6 adds a backend executable prototype. The dry-run command is:

```cmd
python scripts\build_backend_exe.py
```

Developers with PyInstaller installed can attempt a local build with:

```cmd
python scripts\build_backend_exe.py --run
```

Generated backend executable output belongs under `dist/backend/` and must not
be committed. If `dist/backend/safetrace-backend.exe` exists, the desktop
package builder copies it into `dist/SafeTrace/backend/safetrace-backend.exe`.
If it is missing, the package builder still creates the placeholder backend
folder.

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

MobileSAM and VLM assets should be bundled with the no-extra-steps release
package. MobileSAM refinement uses `checkpoints/mobile_sam.pt` when present and
otherwise falls back to detector-box evidence. VLM explanations use packaged
`models/vlm/` assets first, optional local Ollama only when explicitly
configured/available, and otherwise fall back to rule-based explanation text.
Ollama is optional and is not required for the release package. The SafeTrace
Assistant remains a separate chat feature and uses `models/chat/`.

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
