# SafeTrace Assistant Model Directory

Place local SafeTrace Assistant model files here for development and packaged
local builds.

Model files must not be committed to git. The expected default filename is:

```text
safetrace-assistant-qwen2.5-1.5b-instruct-q4.gguf
```

Future installer or release packaging can place the approved GGUF file in this
directory automatically. The backend will keep SafeTrace running if the model or
the `llama-cpp-python` runtime is unavailable.

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

Use `SAFETRACE_CHAT_SPEED_PROFILE=fast` for a shorter context window and shorter
answers. This repository documents model placement only; it does not download or
track model files.
