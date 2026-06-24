# SafeTrace Desktop Packaging Prototype

Phase 5 creates a local package layout prototype. It does not build a final
`.exe` and does not copy local data, checkpoints, generated media, uploads, or
model files.

## Create The Prototype Package

From the repository root:

```cmd
python scripts\build_desktop_prototype.py --clean
```

The script creates:

```text
dist/SafeTrace/
  SafeTraceLauncher.bat
  backend/
    README.txt
    backend_manifest.json
  frontend/
    dist/
  config/
    safetrace.env.example
  models/
    chat/
  data/
  logs/
  packaging_manifest.json
```

`dist/SafeTrace/` is generated output and must not be committed.

If a local backend executable already exists at:

```text
dist/backend/safetrace-backend.exe
```

the package builder copies it into:

```text
dist/SafeTrace/backend/safetrace-backend.exe
```

The executable is optional. If it is absent, the package still builds with a
placeholder backend folder and a clear warning.

## What It Contains

- A prototype launcher batch file.
- A backend runtime placeholder folder.
- An optional copied backend executable when one already exists locally.
- A backend manifest placeholder.
- A frontend `dist/` folder. If `frontend-react/dist` exists, it is copied;
  otherwise a placeholder README is written.
- External config example at `config/safetrace.env.example`.
- Empty external folders for `data/`, `logs/`, and `models/chat/`.
- A generated `packaging_manifest.json`.

## What It Excludes

The prototype script intentionally excludes:

- `*.gguf`
- `*.bin`
- `*.safetensors`
- `*.pt`
- `*.pth`
- `checkpoints/`
- `data/`
- `uploads/`
- `generated/`
- `generated_media/`
- local caches
- uploaded media
- generated reports
- model assets

Do not copy the GGUF chat model into the package from source control. A future
installer may place approved model files into `models/chat/` outside the backend
runtime folder.

## External Config

Tracked defaults live in:

```text
config/safetrace.env.example
```

Future installed systems should use:

```text
config/safetrace.env
```

The real local `config/safetrace.env` is ignored. It should hold machine-local
paths and runtime variables such as:

```cmd
KMP_DUPLICATE_LIB_OK=TRUE
OMP_NUM_THREADS=1
SAFETRACE_CHAT_ENABLED=auto
SAFETRACE_CHAT_PROVIDER=packaged_llamacpp
SAFETRACE_CHAT_MODEL_PATH=models/chat/safetrace-assistant-qwen2.5-1.5b-instruct-q4.gguf
SAFETRACE_SERVE_FRONTEND=true
SAFETRACE_FRONTEND_DIST=frontend/dist
```

## Frontend Static Serving

The backend can serve the React production build when:

```cmd
set SAFETRACE_SERVE_FRONTEND=true
set SAFETRACE_FRONTEND_DIST=frontend/dist
```

Rules:

- `/api/*` remains API-only.
- `/` serves `index.html`.
- `/assets/*` serves built React assets.
- Unknown frontend paths fall back to `index.html`.
- Vite development mode remains supported when `SAFETRACE_SERVE_FRONTEND=false`.

## Live Static Frontend

The React bundle can also be deployed to a free static host while the backend
continues running locally on the user's computer. In that mode, the website is
locked until the local runtime responds at `http://127.0.0.1:8000/api`.

Set the backend live-site allowlist with:

```cmd
set SAFETRACE_ALLOWED_ORIGINS=https://your-site.pages.dev
```

See `docs/live_frontend_deployment.md` for Cloudflare Pages, Netlify, Vercel,
and GitHub Pages notes.

## Local Browser Result Cache

The React frontend may cache completed result JSON in the user's browser so
queue switching and batch result review remain responsive. This cache is local
to the browser and can be cleared from the UI. It stores result metadata and
backend evidence URLs only; it must not store raw uploaded videos, copied
evidence image bytes, model files, credentials, or secrets.

## Path To A Future EXE

This prototype is a filesystem contract for later packaging work. Phase 6 adds
a PyInstaller prototype for creating `dist/backend/safetrace-backend.exe`.
The package script can copy that existing local executable into
`backend/safetrace-backend.exe`, or continue with the placeholder backend folder
when no executable has been built. Future builds may replace
`backend/README.txt` with `backend/safetrace-backend.exe` and runtime
dependencies while preserving:

- `config/`
- `data/`
- `models/`
- `logs/`

The backend remains update-friendly because data, configuration, frontend assets,
logs, checkpoints, and GGUF files are external to the backend runtime folder.

See `docs/backend_executable_prototype.md` for the backend executable build
prototype, risks, and rollback guidance.
