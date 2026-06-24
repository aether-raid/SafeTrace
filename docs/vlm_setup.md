# Local VLM Setup

SafeTrace VLM explanations are optional and local-only. If VLM is unavailable,
analysis still completes with rule-based explanations.

## Provider Selection

Default configuration:

```cmd
set SAFETRACE_VLM_ENABLED=auto
set SAFETRACE_VLM_PROVIDER=auto
set SAFETRACE_VLM_MODEL_PATH=models\vlm
set SAFETRACE_VLM_DIR=models\vlm
set SAFETRACE_VLM_OLLAMA_BASE_URL=http://127.0.0.1:11434
set SAFETRACE_VLM_MODEL=local-vlm
set SAFETRACE_VLM_TIMEOUT_SECONDS=30
set SAFETRACE_VLM_MAX_FRAMES=3
set SAFETRACE_VLM_MAX_TOKENS=180
```

`auto` preserves the original local/non-Ollama VLM behavior:

1. Use the existing local transformer VLM provider when `SAFETRACE_VLM_MODEL_PATH`
   or `SAFETRACE_VLM_DIR`
   points to a local model snapshot and the runtime is installed.
2. Otherwise use local Ollama vision only when it is configured and available.
3. Otherwise use rule-based explanation fallback.

Use `SAFETRACE_VLM_PROVIDER=ollama` only when you explicitly want Ollama.

## No-Extra-Steps Release Package

The release package should bundle the local/non-Ollama VLM assets at:

```text
SafeTrace/models/vlm/
```

The launcher resolves this folder relative to the local SafeTrace folder and
sets:

```cmd
set SAFETRACE_VLM_MODEL_PATH=%APP_ROOT%\models\vlm
set SAFETRACE_VLM_DIR=%APP_ROOT%\models\vlm
set SAFETRACE_VLM_PROVIDER=auto
```

Users should not need to run Ollama, copy VLM checkpoints, or edit config for
the default release flow.

## Ollama Vision Provider

Recommended local models:

- `llava`: easier local setup.
- `llama3.2-vision`: stronger vision model when hardware supports it.

SafeTrace only accepts a local Ollama base URL such as
`http://127.0.0.1:11434`. It does not use cloud VLM APIs and does not upload
frames, images, or videos to internet services.

## Prompt Contract

The VLM is asked to:

```text
Describe only visible safety evidence in this frame.
Do not make legal conclusions.
Mention uncertainty from camera angle, blur, glare, or occlusion.
Keep answer under 90 words.
```

The evidence card labels local model output as `VLM explanation`. If VLM is
unavailable or fails, the card labels the fallback as `Rule-based explanation`.

## Assistant Separation

The floating SafeTrace Assistant is separate from VLM explanations. The
assistant answers product, usage, troubleshooting, API, and current-result
questions. VLM explanations describe visual evidence for selected result
frames.

## Fallback

VLM timeout, runtime failure, missing local model, unsupported provider, or a
non-local base URL all fall back to deterministic rule-based explanations.
Main SafeTrace upload, single-video analysis, ZIP/batch analysis, and local
result cache behavior remain available without VLM.
