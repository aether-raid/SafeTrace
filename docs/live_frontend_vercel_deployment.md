# SafeTrace Live Frontend on Vercel

SafeTrace uses a hybrid deployment model:

```text
static Vercel React frontend + local Windows SafeTrace backend runtime
```

The Vercel site is only the user interface. Videos, ZIP uploads, analysis jobs,
reports, evidence media, VLM explanations, and SafeTrace Assistant requests are
processed by the local backend at `http://127.0.0.1:8000`. The frontend must not
upload videos or results to Vercel.

## Vercel Suitability

Vercel is appropriate for demo and non-commercial Hobby usage. Business,
commercial, team, or production usage may require Vercel Pro or a different
hosting plan. Review Vercel's current plan terms before public release.

## Build Settings

Deploy from `frontend-react` with:

```text
Framework: Vite
Build command: npm run build
Output directory: dist
Install command: npm install
```

The frontend should stay backend-required:

```text
VITE_SAFETRACE_REQUIRE_BACKEND=true
VITE_SAFETRACE_ENABLE_PREVIEW_MODE=false
VITE_SAFETRACE_API_BASE_URL=http://127.0.0.1:8000
```

If `VITE_SAFETRACE_API_BASE_URL` is unset, the frontend discovers the local
runtime at:

```text
http://127.0.0.1:8000/api
http://localhost:8000/api
```

## Deployment Command

Do not run deployment from Codex unless explicitly requested. When ready, run:

```bat
cd frontend-react
npx vercel --prod
cd ..
```

The helper script performs install, build, and deploy:

```bat
scripts\deploy_frontend_vercel.bat
```

On the first run, Vercel CLI may ask you to log in and link the project.

## Backend Allowed Origins

After deployment, copy the deployed URL, for example:

```text
https://safetrace-example.vercel.app
```

Add it to `config/safetrace.env` before building or starting the local backend:

```text
SAFETRACE_ALLOWED_ORIGINS=https://safetrace-example.vercel.app,http://127.0.0.1:5173,http://localhost:5173
```

Restart the backend after changing allowed origins. Rebuild the backend
executable and release package before sharing a package that should work with a
new Vercel URL.

## Backend EXE and Package Flow

After changing `SAFETRACE_ALLOWED_ORIGINS`, rebuild the local runtime:

```bat
python scripts\build_backend_exe.py --run
python scripts\build_desktop_prototype.py --clean
```

The backend executable and release package are generated output. Do not commit:

```text
dist/
frontend-react/dist/
.vercel/
*.exe
*.gguf
*.pt
*.pth
*.onnx
*.bin
*.safetensors
data/
uploads/
generated/
generated_media/
models/vlm/
models/chat/*.gguf
checkpoints/mobile_sam.pt
```

## Live Frontend Test Flow

1. Deploy the frontend to Vercel.
2. Copy the deployed URL, such as `https://safetrace-example.vercel.app`.
3. Add it to `config/safetrace.env`:

   ```text
   SAFETRACE_ALLOWED_ORIGINS=https://safetrace-example.vercel.app,http://127.0.0.1:5173,http://localhost:5173
   ```

4. Rebuild the backend EXE:

   ```bat
   python scripts\build_backend_exe.py --run
   ```

5. Build the local package:

   ```bat
   python scripts\build_desktop_prototype.py --clean
   ```

6. Start the packaged backend or launcher from `dist\SafeTrace`.
7. Open the Vercel URL.
8. Confirm the frontend is disconnected when the backend is off.
9. Start the backend EXE.
10. Click `Reconnect to Local Runtime`.
11. Confirm these local endpoints work:

    ```text
    http://127.0.0.1:8000/api/health
    http://127.0.0.1:8000/api/system/status
    ```

12. Run Safe Mode rule-based analysis first.
13. Keep Lightweight VLM disabled for the main Safe Mode release package.
14. Confirm the browser Network tab calls `http://127.0.0.1:8000/api/...` and
    does not upload videos or results to Vercel.

## Troubleshooting

If the live frontend cannot connect:

- Confirm the backend is running on `127.0.0.1:8000`.
- Confirm `SAFETRACE_ALLOWED_ORIGINS` exactly matches the deployed Vercel origin.
- Restart the backend after editing `config/safetrace.env`.
- Check the browser console for CORS or private-network preflight errors.
- Keep rule-based Safe Mode analysis working before experimenting with optional
  VLM profiles outside the main release package.
