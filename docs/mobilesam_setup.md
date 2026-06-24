# MobileSAM Setup

MobileSAM is optional. SafeTrace uses YOLO detector boxes and rule-based
evidence even when MobileSAM is missing.

## Local Checkpoint

Place the checkpoint at:

```text
checkpoints/mobile_sam.pt
```

Equivalent environment variables:

```cmd
set SAFETRACE_MOBILESAM_ENABLED=auto
set SAFETRACE_MOBILESAM_CHECKPOINT=checkpoints\mobile_sam.pt
```

`SAFETRACE_MSAM_CKPT` remains accepted for compatibility, but
`SAFETRACE_MOBILESAM_CHECKPOINT` is preferred.

## Status Values

`GET /api/system/status` reports MobileSAM as:

- `available`: checkpoint and Python runtime are present.
- `disabled`: `SAFETRACE_MOBILESAM_ENABLED` is disabled/off/false.
- `missing_checkpoint`: checkpoint is absent.
- `missing_runtime`: checkpoint exists but the `mobile_sam` runtime is absent.
- `unavailable`: another non-blocking readiness issue was detected.

Missing MobileSAM never blocks analysis. If refinement is unavailable,
SafeTrace keeps using detector-box evidence.

## Packaging

The prototype package builder looks for:

```text
checkpoints/mobile_sam.pt
```

If present locally, it copies the checkpoint into:

```text
dist/SafeTrace/checkpoints/mobile_sam.pt
```

If absent, it creates `dist/SafeTrace/checkpoints/README.txt` and prints:

```text
MobileSAM checkpoint missing; package will use detector-box fallback
```

Do not commit checkpoints or model weights. The `.gitignore` rules keep
`*.pt`, `*.pth`, `*.bin`, `*.safetensors`, `*.gguf`, and `*.onnx` ignored.
