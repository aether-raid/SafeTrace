# SafeTrace Assistant

SafeTrace Assistant is optional and limited to SafeTrace questions about the
app, local backend status, current analysis results, batch manifests, evidence
frames, exports, and known limitations. Guardrails run before any provider call,
so out-of-scope questions are refused without invoking a model.

## Default Packaged Provider

The default backend configuration uses a packaged local llama.cpp provider:

```cmd
set SAFETRACE_CHAT_ENABLED=auto
set SAFETRACE_CHAT_PROVIDER=packaged_llamacpp
set SAFETRACE_CHAT_MODEL_PATH=models/chat/safetrace-assistant-qwen2.5-1.5b-instruct-q4.gguf
set SAFETRACE_CHAT_CONTEXT_WINDOW=4096
set SAFETRACE_CHAT_MAX_TOKENS=512
set SAFETRACE_CHAT_TEMPERATURE=0.2
set SAFETRACE_CHAT_TOP_P=0.9
set SAFETRACE_CHAT_AUTOLOAD=false
```

In packaged mode, users do not need to run Ollama manually. The backend checks
for `llama-cpp-python` and the configured GGUF file. The model is lazy-loaded on
the first chat request by default, then cached for later requests.

Place local model files under:

```text
models/chat/
```

The approved default filename is:

```text
safetrace-assistant-qwen2.5-1.5b-instruct-q4.gguf
```

Model files are ignored by git and must not be committed.

## Fast Local Profile

For a lighter, more mobile-feeling assistant experience, use the fast profile:

```cmd
set SAFETRACE_CHAT_SPEED_PROFILE=fast
set SAFETRACE_CHAT_CONTEXT_WINDOW=2048
set SAFETRACE_CHAT_MAX_TOKENS=256
set SAFETRACE_CHAT_TEMPERATURE=0.1
set SAFETRACE_CHAT_TOP_P=0.85
set SAFETRACE_CHAT_REPEAT_PENALTY=1.15
```

`SAFETRACE_CHAT_SPEED_PROFILE=fast` also makes the backend send shorter,
summarized context to the local model by default. Explicit environment values
for context window, max tokens, temperature, top-p, or repeat penalty still take
precedence.

Recommended quality/speed balance:

```text
Qwen2.5-1.5B-Instruct Q4 GGUF
```

Recommended faster/mobile option:

```text
Qwen2.5-0.5B-Instruct Q4 GGUF
```

Alternative fast option:

```text
Llama-3.2-1B-Instruct Q4 GGUF
```

Do not download or commit model files automatically. Place approved local model
files manually or through a future installer/release package.

## Status Endpoint

Endpoints:

- `GET /api/chat/status`
- `POST /api/chat`

`GET /api/chat/status` reports one of these states:

- `available`: provider and model are ready.
- `disabled`: `SAFETRACE_CHAT_ENABLED` disables chat.
- `missing_model`: packaged provider is enabled but the GGUF file is absent.
- `missing_runtime`: packaged provider is enabled but `llama_cpp` is not installed.
- `loading`: the packaged local model is currently loading.
- `unavailable`: the selected provider is configured but cannot answer.

The status response also includes diagnostic fields such as `enabled_mode`,
`provider`, `model_path`, `model_exists`, `runtime_available`, `reason`, and
`action_hint`. If `SAFETRACE_CHAT_ENABLED=false`, restart the backend with:

```cmd
set SAFETRACE_CHAT_ENABLED=auto
set SAFETRACE_CHAT_PROVIDER=packaged_llamacpp
set SAFETRACE_CHAT_MODEL_PATH=models/chat/safetrace-assistant-qwen2.5-1.5b-instruct-q4.gguf
```

If chat is disabled, unavailable, missing the runtime, or missing the model,
`POST /api/chat` returns a structured `503` error instead of crashing. Main
SafeTrace analysis, single-video upload, and ZIP/batch upload continue to work.

## Optional Ollama Fallback

Ollama remains available as an explicit optional provider:

```cmd
set SAFETRACE_CHAT_ENABLED=true
set SAFETRACE_CHAT_PROVIDER=ollama
set SAFETRACE_OLLAMA_BASE_URL=http://127.0.0.1:11434
set SAFETRACE_OLLAMA_MODEL=llama3.2:3b
```

No Ollama binaries, GGUF files, or model weights are stored in this repository.
