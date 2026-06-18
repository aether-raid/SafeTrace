# SafeTrace React Frontend

This folder contains the new user-facing SafeTrace React frontend. It is a polished dashboard for selecting media, configuring analysis settings, reviewing safety violation findings, and exporting evidence reports.

The existing Streamlit frontend remains the debugging and pipeline UI under `frontend/`. This React version uses local sample data only and does not call the Python backend yet.

## Prerequisites

- Node.js 18 or newer
- npm 9 or newer

## Run locally

```bash
cd frontend-react
npm install
npm run dev
```

Vite will print the local development URL, usually `http://127.0.0.1:5173/`.

If pnpm is preferred, the app should also work with:

```bash
pnpm install
pnpm dev
```

## Current behavior

- Uses local SafeTrace sample media and analysis data from `src/data/mockAnalysis.ts`.
- Displays annotated frame images from `public/sample-evidence/` for the default sample video, with a clear warning if required evidence images are missing.
- Uses `src/services/analysisService.ts` as the service boundary for future API calls.
- Supports clickable sample media, local file selection, configurable analysis settings, staged analysis progress, grouped violation summaries, evidence frame navigation, and collapsed technical details.
- Exports a user-facing summary report and a technical JSON evidence package in the browser.
- Keeps raw evidence fields out of the primary user-facing findings view.

## Future integration notes

- Replace or extend `runMockAnalysis` and `getMockMediaLibrary` in `src/services/analysisService.ts` with calls to a Python/FastAPI backend.
- Keep `src/types/analysis.ts` aligned with the backend result schema.
- Map backend frame image or annotated image URLs into `FrameResult.imageUrl` when media serving is available.
- Preserve the UI flow: React UI -> analysis service -> Python/FastAPI backend -> SafeTrace pipeline.
- Tauri packaging can be added later once the browser-based Vite frontend and backend API are stable.

## Sample evidence images

The default demo expects annotated frame images in:

`public/sample-evidence/`

Expected files:
- `video_2026-06-18_11-38-42_000046_annotated.jpg`
- `video_2026-06-18_11-38-42_000016_annotated.jpg`
- `video_2026-06-18_11-38-42_000019_annotated.jpg`
- `video_2026-06-18_11-38-42_000021_annotated.jpg`
- `video_2026-06-18_11-38-42_000033_annotated.jpg`

If these files are missing, the app will show an evidence-image warning instead of silently using drawn fallback visuals.
