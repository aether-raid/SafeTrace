# SafeTrace Runtime Preflight

`GET /api/system/status` is the lightweight runtime preflight endpoint for the
Windows desktop flow. It must not load heavy analysis models or the local chat
GGUF just to report status.

## Top-Level Sections

- `device`: configured SafeTrace device mode.
- `gpuAvailable`: whether PyTorch reports CUDA availability.
- `models`: path/readiness checks for embedding model, detector, MobileSAM, and
  VLM.
- `limits`: upload, batch, sampling, queue, and retention limits.
- `queue`: current job status counts and active/terminal states.
- `runtime`: Python, working directory, OpenMP, chat, model, and job-store
  diagnostics.
- `preflight`: actionable checks intended for the React sidebar.

## Runtime Diagnostics

The `runtime` section includes:

- backend status and offline mode
- Python executable and version
- current working directory
- configured device and GPU availability
- model readiness
- chat provider, model path, model existence, llama-cpp runtime availability
- OpenMP workaround environment status
- upload and batch limits
- job store path

## Preflight Checks

The `preflight.checks` object includes:

- `backend`
- `openmp`
- `embeddingModel`
- `detector`
- `mobileSam`
- `vlm`
- `assistant`
- `assistantModel`
- `assistantRuntime`

Each check has a `status`, `message`, and optional `path`, `actionHint`, and
`details`. Missing optional features such as VLM, MobileSAM, or chat should not
block upload or analysis.

Optional model statuses include:

- `available`: optional runtime and model/checkpoint are ready.
- `disabled`: feature is intentionally disabled by environment configuration.
- `missing_checkpoint`: an optional checkpoint such as `checkpoints/mobile_sam.pt`
  is absent.
- `missing_runtime`: the local runtime dependency or local service is absent.
- `unavailable`: a non-blocking optional readiness issue was detected.

MobileSAM details include checkpoint existence, runtime availability, and the
packaged expected path. VLM details include `provider`, `selectedProvider`,
`availableProviders`, provider-specific runtime/model readiness, and action
hints. With `SAFETRACE_VLM_PROVIDER=auto`, SafeTrace prefers the existing local
transformer VLM provider, then optional local Ollama, then rule-based fallback.
VLM status is independent from SafeTrace Assistant status.

## Chat Status Safety

System preflight calls chat status in no-load mode. Even when
`SAFETRACE_CHAT_AUTOLOAD=true`, `/api/system/status` only checks the configured
path and runtime availability. It does not instantiate the packaged local LLM.

Use `POST /api/chat/warmup` for the optional assistant warmup path. Warmup is
only attempted when `SAFETRACE_CHAT_WARMUP_ON_OPEN=true` and the assistant panel
opens in the React frontend.
