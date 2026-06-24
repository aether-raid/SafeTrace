# Live Frontend Deployment

SafeTrace supports a hybrid deployment model:

```text
public static React frontend + local SafeTrace backend runtime
```

The live website is only the user interface. Upload, analysis, reports, batch
processing, and chat stay locked until the user starts the local SafeTrace
runtime on the same computer.

## Recommended Hosting

Recommended free static hosts:

- Cloudflare Pages
- Netlify

Both are simple for Vite builds, support HTTPS by default, and work well for a
static React bundle. Vercel and GitHub Pages are also viable.

## Frontend Build Settings

Use these build settings on the hosting provider:

```text
base directory: frontend-react
build command: npm.cmd run build
output directory: frontend-react/dist
```

Environment variable:

```text
VITE_SAFETRACE_API_BASE_URL=http://127.0.0.1:8000
```

You may leave `VITE_SAFETRACE_API_BASE_URL` unset. In that case the frontend
auto-discovers:

```text
http://127.0.0.1:8000/api
http://localhost:8000/api
```

Keep preview mode disabled for public deployments:

```text
VITE_SAFETRACE_REQUIRE_BACKEND=true
VITE_SAFETRACE_ENABLE_PREVIEW_MODE=false
```

## Backend Allowed Origins

The local backend allows Vite dev origins by default:

```text
http://127.0.0.1:5173
http://localhost:5173
```

For a live frontend, set the exact deployed site URL before starting the local
backend:

```cmd
set SAFETRACE_ALLOWED_ORIGINS=https://your-site.pages.dev
```

Multiple origins are comma-separated:

```cmd
set SAFETRACE_ALLOWED_ORIGINS=https://your-site.pages.dev,https://your-site.netlify.app
```

Do not use `*`. SafeTrace should remain a local-only runtime bound to
`127.0.0.1` by default.

## User Flow

When a user opens the live website, it checks:

```text
GET http://127.0.0.1:8000/api/health
GET http://127.0.0.1:8000/api/system/status
```

If the runtime is disconnected, the website stays locked and tells the user to:

1. Run `SafeTrace.exe` on this computer.
2. Keep the local runtime window open.
3. Return to the website and click `Reconnect to Local Runtime`.

During development, run:

```cmd
scripts\start_safetrace_windows.bat
```

## SPA Fallbacks

Netlify:

```text
frontend-react/public/_redirects
frontend-react/netlify.toml
```

Vercel:

```text
frontend-react/vercel.json
```

Cloudflare Pages can use the Vite output directly. If you add client-side routes
later, configure a fallback to `index.html`.

GitHub Pages may need an additional SPA fallback workflow depending on the final
URL shape and routing strategy.

## Browser Troubleshooting

If the live site cannot connect:

- Confirm the local runtime is running at `http://127.0.0.1:8000/api/health`.
- Confirm `SAFETRACE_ALLOWED_ORIGINS` exactly matches the live site origin.
- Try `http://localhost:8000/api/health` if `127.0.0.1` is blocked by local tools.
- Check browser console CORS or private-network preflight errors.
- Restart the backend after changing environment variables.

Some browsers send a private-network preflight when an HTTPS public site calls a
local HTTP backend. SafeTrace only returns
`Access-Control-Allow-Private-Network: true` for allowed origins.

## Backend Executable Relationship

Live frontend mode works best after the backend executable exists. A later
release should provide a `SafeTrace.exe` or launcher that starts the local API at
`127.0.0.1:8000`.

Until then, developers should use:

```cmd
scripts\start_safetrace_windows.bat
```

The live frontend is a shell until the local runtime is running. The backend
executable design remains update-friendly: `config/`, `data/`, `models/`,
`logs/`, frontend assets, checkpoints, and GGUF files stay external.
