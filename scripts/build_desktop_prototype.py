"""Create a local SafeTrace desktop package prototype.

This script prepares a replaceable-runtime package layout under dist/SafeTrace.
It does not build a final .exe and intentionally excludes local data, uploads,
generated media, reports, and cache folders. It may copy approved local release
assets into generated package output when those assets already exist locally:
MobileSAM, the packaged assistant GGUF, and local/non-Ollama VLM assets.
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Iterable


PACKAGE_DIRNAME = "SafeTrace"
DEFAULT_BACKEND_EXE = Path("dist") / "backend" / "safetrace-backend.exe"
PACKAGED_BACKEND_EXE = Path("backend") / "safetrace-backend.exe"
MOBILE_SAM_SOURCE = Path("checkpoints") / "mobile_sam.pt"
MOBILE_SAM_PACKAGE_PATH = Path("checkpoints") / "mobile_sam.pt"
CHAT_MODEL_SOURCE_DIR = Path("models") / "chat"
CHAT_MODEL_PATTERN = "*.gguf"
CHAT_MODEL_PACKAGE_DIR = Path("models") / "chat"
DEFAULT_CHAT_MODEL_NAME = "safetrace-assistant-qwen2.5-1.5b-instruct-q4.gguf"
VLM_SOURCE_DIR = Path("models") / "vlm"
VLM_PACKAGE_DIR = Path("models") / "vlm"
CONFIG_SOURCE = Path("config") / "safetrace.env"
CONFIG_EXAMPLE_SOURCE = Path("config") / "safetrace.env.example"
OPTIONAL_ASSETS_REPORT = "OPTIONAL_ASSETS_REPORT.txt"

PROTECTED_ASSET_RULES = [
    "*.gguf",
    "*.bin",
    "*.safetensors",
    "*.pt",
    "*.pth",
    "*.onnx",
    "checkpoints/",
    "models/chat/*.gguf",
    "models/vlm/",
    "data/",
    "uploads/",
    "generated/",
    "generated_media/",
    "!dist/SafeTrace/checkpoints/mobile_sam.pt",
    "!dist/SafeTrace/models/chat/*.gguf",
    "!dist/SafeTrace/models/vlm/**",
]
PACKAGE_ASSET_ALLOWLIST = [
    "dist/SafeTrace/checkpoints/mobile_sam.pt",
    "dist/SafeTrace/models/chat/*.gguf",
    "dist/SafeTrace/models/vlm/**",
]
PRESERVE_PATHS = ["config/", "data/", "models/", "logs/", "checkpoints/"]


LAUNCHER_TEXT = rf"""@echo off
setlocal

set "APP_ROOT=%~dp0"
for %%I in ("%APP_ROOT%.") do set "APP_ROOT=%%~fI"
cd /d "%APP_ROOT%" || exit /b 1

if exist "config\safetrace.env" (
  for /f "usebackq eol=# tokens=1,* delims==" %%A in ("config\safetrace.env") do (
    if not "%%A"=="" set "%%A=%%B"
  )
) else if exist "config\safetrace.env.example" (
  for /f "usebackq eol=# tokens=1,* delims==" %%A in ("config\safetrace.env.example") do (
    if not "%%A"=="" set "%%A=%%B"
  )
)

if not defined SAFETRACE_PROJECT_ROOT set "SAFETRACE_PROJECT_ROOT=%APP_ROOT%"
if not defined SAFETRACE_DATA_DIR set "SAFETRACE_DATA_DIR=%APP_ROOT%\data"
if not defined SAFETRACE_CHECKPOINTS_DIR set "SAFETRACE_CHECKPOINTS_DIR=%APP_ROOT%\checkpoints"
if not defined KMP_DUPLICATE_LIB_OK set "KMP_DUPLICATE_LIB_OK=TRUE"
if not defined OMP_NUM_THREADS set "OMP_NUM_THREADS=1"
if not defined SAFETRACE_CHAT_ENABLED set "SAFETRACE_CHAT_ENABLED=auto"
if not defined SAFETRACE_CHAT_PROVIDER set "SAFETRACE_CHAT_PROVIDER=packaged_llamacpp"
if not defined SAFETRACE_CHAT_SPEED_PROFILE set "SAFETRACE_CHAT_SPEED_PROFILE=fast"
if not defined SAFETRACE_CHAT_MODEL_PATH set "SAFETRACE_CHAT_MODEL_PATH=%APP_ROOT%\models\chat\{DEFAULT_CHAT_MODEL_NAME}"
if not defined SAFETRACE_SERVE_FRONTEND set "SAFETRACE_SERVE_FRONTEND=true"
if not defined SAFETRACE_FRONTEND_DIST set "SAFETRACE_FRONTEND_DIST=%APP_ROOT%\frontend\dist"
if not defined SAFETRACE_BUILD_MODE set "SAFETRACE_BUILD_MODE=release-package"
if not defined SAFETRACE_RUNTIME_LAYOUT set "SAFETRACE_RUNTIME_LAYOUT=packaged"
if not defined SAFETRACE_MOBILESAM_ENABLED set "SAFETRACE_MOBILESAM_ENABLED=auto"
if not defined SAFETRACE_MOBILESAM_CHECKPOINT set "SAFETRACE_MOBILESAM_CHECKPOINT=%APP_ROOT%\checkpoints\mobile_sam.pt"
if not defined SAFETRACE_VLM_ENABLED set "SAFETRACE_VLM_ENABLED=auto"
if not defined SAFETRACE_VLM_PROVIDER set "SAFETRACE_VLM_PROVIDER=auto"
if not defined SAFETRACE_VLM_MODEL_PATH set "SAFETRACE_VLM_MODEL_PATH=%APP_ROOT%\models\vlm"
if not defined SAFETRACE_VLM_DIR set "SAFETRACE_VLM_DIR=%SAFETRACE_VLM_MODEL_PATH%"
if not defined SAFETRACE_VLM_OLLAMA_BASE_URL set "SAFETRACE_VLM_OLLAMA_BASE_URL=http://127.0.0.1:11434"
if not defined SAFETRACE_VLM_MODEL set "SAFETRACE_VLM_MODEL=local-vlm"

echo [SafeTrace] App root: "%APP_ROOT%"
echo [SafeTrace] Backend health: http://127.0.0.1:8000/api/health
echo [SafeTrace] Live frontend may reconnect to this local runtime.
echo [SafeTrace] Runtime layout: %SAFETRACE_RUNTIME_LAYOUT%
echo [SafeTrace] MobileSAM: "%SAFETRACE_MOBILESAM_CHECKPOINT%"
echo [SafeTrace] VLM assets: "%SAFETRACE_VLM_DIR%"
echo.

if exist "backend\safetrace-backend.exe" (
  start "SafeTrace Backend" /D "%APP_ROOT%" cmd /k "backend\safetrace-backend.exe --host 127.0.0.1 --port 8000 --log-level info"
  timeout /t 3 /nobreak >nul
  exit /b 0
)

echo [SafeTrace] Prototype package does not include backend\safetrace-backend.exe.
echo [SafeTrace] Build or copy the backend executable before release packaging.
exit /b 1
"""


BACKEND_README = """SafeTrace backend runtime placeholder.

Release packaging should place safetrace-backend.exe and runtime dependencies
in this folder. Keep data, logs, uploads, checkpoints, and model files outside
the backend folder so backend updates do not overwrite local assets.
"""


FRONTEND_README = """SafeTrace frontend dist placeholder.

The no-extra-steps release flow normally uses the live website plus local
runtime. This folder is still supported when a packaged local frontend build is
included.

To include frontend assets in a developer package:

  cd frontend-react
  npm.cmd run build
"""


CHECKPOINT_README = """SafeTrace checkpoint folder.

The no-extra-steps release package should include:

  checkpoints/mobile_sam.pt

This generated README appears because the local checkpoint was not found during
package generation. The app still runs with detector-box evidence, but strict
release validation will fail until the checkpoint is supplied locally.
"""


CHAT_README = f"""SafeTrace assistant model folder.

The no-extra-steps release package should include the packaged assistant model:

  models/chat/{DEFAULT_CHAT_MODEL_NAME}

This generated README appears because no local GGUF was found during package
generation. Do not commit GGUF files to Git.
"""


VLM_README = """SafeTrace local VLM asset folder.

The no-extra-steps release package should include local/non-Ollama VLM assets:

  models/vlm/

SafeTrace uses SAFETRACE_VLM_PROVIDER=auto and prefers this local provider.
Ollama remains an optional developer/advanced provider only. Do not commit VLM
model files or checkpoint assets to Git.
"""


CONFIG_README = """SafeTrace config folder.

Strict release packages should include:

  config/safetrace.env

This generated README appears because only config/safetrace.env.example was
available during package generation.
"""


class AssetValidationError(RuntimeError):
    """Raised when --strict-assets validation fails."""

    def __init__(self, failures: list[str]) -> None:
        super().__init__("Strict asset validation failed:\n" + "\n".join(f"- {failure}" for failure in failures))
        self.failures = failures


def repo_root_from_script() -> Path:
    return Path(__file__).resolve().parents[1]


def package_root(repo_root: Path, output_dir: Path | None = None) -> Path:
    base = output_dir or repo_root / "dist"
    return base / PACKAGE_DIRNAME


def manifest_payload() -> dict:
    return {
        "component": "safetrace-desktop-package",
        "version": "0.0.0-dev",
        "build_mode": "release-package-prototype",
        "schema_version": 2,
        "release_runtime_layout": {
            "launcher": "SafeTrace.exe or SafeTraceLauncher.exe",
            "backend": "backend/safetrace-backend.exe",
            "mobileSamCheckpoint": "checkpoints/mobile_sam.pt",
            "chatModel": f"models/chat/{DEFAULT_CHAT_MODEL_NAME}",
            "vlmAssets": "models/vlm/",
            "config": "config/safetrace.env",
            "data": "data/",
            "logs": "logs/",
        },
        "frontend": {
            "live_frontend_supported": True,
            "dist_path": "frontend/dist",
            "served_by_backend": True,
        },
        "backend": {
            "layout": "backend/",
            "entrypoint": "safetrace-backend.exe",
            "manifest": "backend/backend_manifest.json",
        },
        "packaged_assets": {
            "mobileSam": str(MOBILE_SAM_PACKAGE_PATH).replace("\\", "/"),
            "chat": str(CHAT_MODEL_PACKAGE_DIR / DEFAULT_CHAT_MODEL_NAME).replace("\\", "/"),
            "vlm": str(VLM_PACKAGE_DIR).replace("\\", "/") + "/",
            "ollamaRequired": False,
        },
        "preserve_paths": PRESERVE_PATHS,
        "excluded_asset_rules": PROTECTED_ASSET_RULES,
        "package_asset_allowlist": PACKAGE_ASSET_ALLOWLIST,
        "notes": "Generated dist/SafeTrace output and copied model assets must not be committed.",
    }


def backend_manifest_payload() -> dict:
    return {
        "component": "safetrace-backend",
        "version": "0.0.0-dev",
        "build_mode": "release-package-prototype",
        "requires_frontend_version": ">=0.0.0",
        "schema_version": 1,
        "entrypoint": "safetrace-backend.exe",
        "external_assets": {
            "config": "config/safetrace.env",
            "data": "data/",
            "logs": "logs/",
            "mobileSam": "checkpoints/mobile_sam.pt",
            "chat": f"models/chat/{DEFAULT_CHAT_MODEL_NAME}",
            "vlm": "models/vlm/",
        },
        "preserve_paths": PRESERVE_PATHS,
        "notes": "Backend executable updates must not overwrite external model, config, data, or log paths.",
    }


def ensure_dirs(root: Path, paths: Iterable[str]) -> list[Path]:
    created = []
    for relative in paths:
        path = root / relative
        path.mkdir(parents=True, exist_ok=True)
        created.append(path)
    return created


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def path_has_contents(path: Path) -> bool:
    if path.is_file():
        return True
    if not path.is_dir():
        return False
    return any(item.is_file() for item in path.rglob("*"))


def read_env_values(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def disabled(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"0", "false", "no", "off", "disabled", "none"}


def release_config_values(repo_root: Path) -> dict[str, str]:
    values = read_env_values(repo_root / CONFIG_EXAMPLE_SOURCE)
    values.update(read_env_values(repo_root / CONFIG_SOURCE))
    return values


def release_chat_expected(values: dict[str, str]) -> bool:
    if disabled(values.get("SAFETRACE_CHAT_ENABLED", "auto")):
        return False
    return values.get("SAFETRACE_CHAT_PROVIDER", "packaged_llamacpp").strip().lower() == "packaged_llamacpp"


def release_vlm_expected(values: dict[str, str]) -> bool:
    if disabled(values.get("SAFETRACE_VLM_ENABLED", "auto")):
        return False
    provider = values.get("SAFETRACE_VLM_PROVIDER", "auto").strip().lower()
    return provider in {"", "auto", "local", "legacy", "existing", "transformers", "local_transformers", "local_dir"}


def source_backend_exe(repo_root: Path, backend_exe: Path | None = None) -> Path:
    source = backend_exe or repo_root / DEFAULT_BACKEND_EXE
    return source if source.is_absolute() else repo_root / source


def chat_model_sources(repo_root: Path) -> list[Path]:
    source_dir = repo_root / CHAT_MODEL_SOURCE_DIR
    if not source_dir.is_dir():
        return []
    return sorted(path for path in source_dir.glob(CHAT_MODEL_PATTERN) if path.is_file())


def strict_asset_failures(repo_root: Path, backend_exe: Path | None = None) -> list[str]:
    values = release_config_values(repo_root)
    failures: list[str] = []
    if not source_backend_exe(repo_root, backend_exe).is_file():
        failures.append(f"Backend executable missing at {DEFAULT_BACKEND_EXE}.")
    if not (repo_root / CONFIG_SOURCE).is_file():
        failures.append("Release config missing at config/safetrace.env.")
    if not (repo_root / MOBILE_SAM_SOURCE).is_file():
        failures.append("MobileSAM checkpoint missing at checkpoints/mobile_sam.pt.")
    if release_chat_expected(values) and not chat_model_sources(repo_root):
        failures.append("Packaged chat model missing under models/chat/*.gguf.")
    if release_vlm_expected(values) and not path_has_contents(repo_root / VLM_SOURCE_DIR):
        failures.append("Local VLM assets missing under models/vlm/.")
    return failures


def copy_if_exists(source: Path, target: Path) -> bool:
    if not source.exists():
        return False
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(
        source,
        target,
        ignore=shutil.ignore_patterns(
            "*.map",
            "data",
            "uploads",
            "generated",
            "generated_media",
            "checkpoints",
            ".pytest_cache",
            "node_modules",
        ),
    )
    return True


def add_asset_report(
    report: list[dict],
    *,
    name: str,
    source: Path,
    target: Path,
    status: str,
    required_in_strict: bool,
    message: str,
) -> None:
    report.append(
        {
            "name": name,
            "source": str(source),
            "target": str(target),
            "status": status,
            "required_in_strict": required_in_strict,
            "message": message,
        }
    )


def copy_config_files(repo_root: Path, package: Path, report: list[dict]) -> tuple[bool, bool]:
    env_source = repo_root / CONFIG_SOURCE
    env_example_source = repo_root / CONFIG_EXAMPLE_SOURCE
    env_target = package / CONFIG_SOURCE
    env_example_target = package / CONFIG_EXAMPLE_SOURCE

    copied_env = False
    copied_example = False
    if env_source.is_file():
        env_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(env_source, env_target)
        copied_env = True
    else:
        write_text(package / "config" / "README.txt", CONFIG_README)

    if env_example_source.is_file():
        env_example_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(env_example_source, env_example_target)
        copied_example = True

    add_asset_report(
        report,
        name="release config",
        source=env_source,
        target=env_target,
        status="included" if copied_env else "missing",
        required_in_strict=True,
        message="Release config copied." if copied_env else "config/safetrace.env missing; copied example only if present.",
    )
    return copied_env, copied_example


def copy_backend_exe_if_exists(
    repo_root: Path,
    package: Path,
    report: list[dict],
    backend_exe: Path | None = None,
) -> bool:
    source = source_backend_exe(repo_root, backend_exe)
    target = package / PACKAGED_BACKEND_EXE
    if not source.is_file():
        add_asset_report(
            report,
            name="backend executable",
            source=source,
            target=target,
            status="missing",
            required_in_strict=True,
            message="Backend executable missing; package contains backend placeholder.",
        )
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    add_asset_report(
        report,
        name="backend executable",
        source=source,
        target=target,
        status="included",
        required_in_strict=True,
        message="Backend executable copied.",
    )
    return True


def copy_mobile_sam_checkpoint(repo_root: Path, package: Path, report: list[dict]) -> bool:
    source = repo_root / MOBILE_SAM_SOURCE
    target = package / MOBILE_SAM_PACKAGE_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    if not source.is_file():
        write_text(package / "checkpoints" / "README.txt", CHECKPOINT_README)
        add_asset_report(
            report,
            name="MobileSAM checkpoint",
            source=source,
            target=target,
            status="missing",
            required_in_strict=True,
            message="MobileSAM checkpoint missing; detector-box fallback remains available.",
        )
        return False
    shutil.copy2(source, target)
    add_asset_report(
        report,
        name="MobileSAM checkpoint",
        source=source,
        target=target,
        status="included",
        required_in_strict=True,
        message="MobileSAM checkpoint copied.",
    )
    return True


def copy_chat_models(repo_root: Path, package: Path, report: list[dict]) -> list[str]:
    sources = chat_model_sources(repo_root)
    target_dir = package / CHAT_MODEL_PACKAGE_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    if not sources:
        write_text(target_dir / "README.txt", CHAT_README)
        add_asset_report(
            report,
            name="packaged chat model",
            source=repo_root / CHAT_MODEL_SOURCE_DIR / CHAT_MODEL_PATTERN,
            target=target_dir,
            status="missing",
            required_in_strict=True,
            message="No GGUF chat model found; assistant reports missing-model state.",
        )
        return []

    copied: list[str] = []
    for source in sources:
        target = target_dir / source.name
        shutil.copy2(source, target)
        copied.append(source.name)
    add_asset_report(
        report,
        name="packaged chat model",
        source=repo_root / CHAT_MODEL_SOURCE_DIR,
        target=target_dir,
        status="included",
        required_in_strict=True,
        message=f"Copied {len(copied)} GGUF chat model file(s): {', '.join(copied)}.",
    )
    return copied


def copy_vlm_assets(repo_root: Path, package: Path, report: list[dict]) -> bool:
    source = repo_root / VLM_SOURCE_DIR
    target = package / VLM_PACKAGE_DIR
    target.parent.mkdir(parents=True, exist_ok=True)
    if not path_has_contents(source):
        target.mkdir(parents=True, exist_ok=True)
        write_text(target / "README.txt", VLM_README)
        add_asset_report(
            report,
            name="local VLM assets",
            source=source,
            target=target,
            status="missing",
            required_in_strict=True,
            message="Local VLM assets missing; rule-based fallback remains available.",
        )
        return False

    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(
        source,
        target,
        ignore=shutil.ignore_patterns(
            ".git",
            "__pycache__",
            ".pytest_cache",
            ".cache",
            "data",
            "uploads",
            "generated",
            "generated_media",
        ),
    )
    add_asset_report(
        report,
        name="local VLM assets",
        source=source,
        target=target,
        status="included",
        required_in_strict=True,
        message="Local/non-Ollama VLM assets copied.",
    )
    return True


def asset_report_text(summary: dict) -> str:
    lines = [
        "SafeTrace optional/release package asset report",
        f"Package root: {summary['package_root']}",
        "",
        "Assets:",
    ]
    for item in summary["asset_report"]:
        required = "required in strict mode" if item["required_in_strict"] else "optional"
        lines.extend(
            [
                f"- {item['name']}: {item['status']} ({required})",
                f"  source: {item['source']}",
                f"  target: {item['target']}",
                f"  note: {item['message']}",
            ]
        )
    lines.extend(
        [
            "",
            "Ollama required: false",
            "Default VLM provider: auto (local packaged VLM first, optional Ollama only if explicitly configured).",
            "Generated package output and copied model assets must not be committed.",
            "",
        ]
    )
    return "\n".join(lines)


def write_asset_report(package: Path, summary: dict) -> None:
    write_text(package / OPTIONAL_ASSETS_REPORT, asset_report_text(summary))


def build_prototype(
    repo_root: Path,
    output_dir: Path | None = None,
    *,
    clean: bool = False,
    backend_exe: Path | None = None,
    strict_assets: bool = False,
) -> dict:
    repo_root = repo_root.resolve()
    failures = strict_asset_failures(repo_root, backend_exe)
    if strict_assets and failures:
        raise AssetValidationError(failures)

    package = package_root(repo_root, output_dir).resolve()

    if clean and package.exists():
        shutil.rmtree(package)

    created_dirs = ensure_dirs(
        package,
        [
            "backend",
            "frontend/dist",
            "config",
            "models/chat",
            "models/vlm",
            "checkpoints",
            "data",
            "logs",
        ],
    )

    asset_report: list[dict] = []
    write_text(package / "SafeTraceLauncher.bat", LAUNCHER_TEXT)
    write_text(package / "backend" / "README.txt", BACKEND_README)
    write_json(package / "backend" / "backend_manifest.json", backend_manifest_payload())
    write_json(package / "packaging_manifest.json", manifest_payload())

    backend_exe_copied = copy_backend_exe_if_exists(repo_root, package, asset_report, backend_exe)
    copied_config, copied_config_example = copy_config_files(repo_root, package, asset_report)
    frontend_copied = copy_if_exists(repo_root / "frontend-react" / "dist", package / "frontend" / "dist")
    if not frontend_copied:
        write_text(package / "frontend" / "dist" / "README.txt", FRONTEND_README)
    mobile_sam_checkpoint_included = copy_mobile_sam_checkpoint(repo_root, package, asset_report)
    chat_models_included = copy_chat_models(repo_root, package, asset_report)
    vlm_assets_included = copy_vlm_assets(repo_root, package, asset_report)

    warnings = [
        "Excluded local data, uploads, generated reports, generated media, and cache folders.",
        "Model/checkpoint assets are copied only into ignored generated package output.",
        "Ollama is optional and is not required for the no-extra-steps release package.",
    ]
    if not backend_exe_copied:
        warnings.append("Backend executable not found; created a placeholder backend folder only.")
    if not copied_config:
        warnings.append("config/safetrace.env was not found; strict release validation will fail.")
    if not copied_config_example:
        warnings.append("config/safetrace.env.example was not found in the source tree.")
    if not frontend_copied:
        warnings.append("frontend-react/dist was not found; created a frontend placeholder instead.")
    if mobile_sam_checkpoint_included:
        warnings.append("MobileSAM checkpoint included from local checkpoints/mobile_sam.pt.")
    else:
        warnings.append("MobileSAM checkpoint missing; package will use detector-box fallback.")
    if chat_models_included:
        warnings.append(f"Packaged chat model included: {', '.join(chat_models_included)}.")
    else:
        warnings.append("Packaged chat model missing; assistant remains structured but unavailable.")
    if vlm_assets_included:
        warnings.append("Local VLM assets included from models/vlm/.")
    else:
        warnings.append("Local VLM assets missing; visual explanations use rule-based fallback.")

    summary = {
        "package_root": str(package),
        "created_dirs": [str(path) for path in created_dirs],
        "backend_exe_copied": backend_exe_copied,
        "frontend_copied": frontend_copied,
        "config_copied": copied_config,
        "config_example_copied": copied_config_example,
        "mobile_sam_checkpoint_included": mobile_sam_checkpoint_included,
        "chat_models_included": chat_models_included,
        "vlm_assets_included": vlm_assets_included,
        "preserve_paths": PRESERVE_PATHS,
        "excluded_asset_rules": PROTECTED_ASSET_RULES,
        "package_asset_allowlist": PACKAGE_ASSET_ALLOWLIST,
        "asset_report": asset_report,
        "asset_report_path": str(package / OPTIONAL_ASSETS_REPORT),
        "strict_asset_failures": failures,
        "warnings": warnings,
    }
    write_asset_report(package, summary)
    return summary


def print_summary(summary: dict) -> None:
    print(f"SafeTrace desktop prototype: {summary['package_root']}")
    print("Created package folders:")
    for path in summary["created_dirs"]:
        print(f"  - {path}")
    print(f"Backend executable copied: {summary['backend_exe_copied']}")
    print(f"Frontend dist copied: {summary['frontend_copied']}")
    print(f"Release config copied: {summary['config_copied']}")
    print(f"Config example copied: {summary['config_example_copied']}")
    print(f"MobileSAM checkpoint included: {summary['mobile_sam_checkpoint_included']}")
    print(f"Chat models included: {len(summary['chat_models_included'])}")
    print(f"Local VLM assets included: {summary['vlm_assets_included']}")
    print(f"Asset report: {summary['asset_report_path']}")
    print("Preserved external paths:")
    for path in summary["preserve_paths"]:
        print(f"  - {path}")
    print("Intentional source-control exclusions:")
    for rule in summary["excluded_asset_rules"]:
        print(f"  - {rule}")
    print("Generated package asset allowlist:")
    for rule in summary["package_asset_allowlist"]:
        print(f"  - {rule}")
    print("Asset report:")
    print(asset_report_text(summary), end="")
    print("Warnings:")
    for warning in summary["warnings"]:
        print(f"  - {warning}")


def print_dry_run(repo_root: Path, package: Path, backend_exe: Path | None, strict_assets: bool) -> int:
    backend_source = source_backend_exe(repo_root, backend_exe)
    values = release_config_values(repo_root)
    failures = strict_asset_failures(repo_root, backend_exe)
    print(f"Would create SafeTrace desktop prototype at: {package}")
    print(f"Would copy backend exe if present: {backend_source}")
    print(f"Would copy release config if present: {repo_root / CONFIG_SOURCE}")
    print(f"Would copy MobileSAM checkpoint if present: {repo_root / MOBILE_SAM_SOURCE}")
    print(f"Would copy chat GGUF models if present: {repo_root / CHAT_MODEL_SOURCE_DIR / CHAT_MODEL_PATTERN}")
    print(f"Would copy local VLM assets if present: {repo_root / VLM_SOURCE_DIR}")
    print(f"Chat expected in strict mode: {release_chat_expected(values)}")
    print(f"Local VLM expected in strict mode: {release_vlm_expected(values)}")
    print("Would write package asset report: OPTIONAL_ASSETS_REPORT.txt")
    print("Would exclude from source control:")
    for rule in PROTECTED_ASSET_RULES:
        print(f"  - {rule}")
    print("Would allow inside ignored generated package output:")
    for rule in PACKAGE_ASSET_ALLOWLIST:
        print(f"  - {rule}")
    if failures:
        print("Strict asset validation failures:")
        for failure in failures:
            print(f"  - {failure}")
    elif strict_assets:
        print("Strict asset validation would pass.")
    return 2 if strict_assets and failures else 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=None, help="Base output directory; default is ./dist")
    parser.add_argument(
        "--backend-exe",
        type=Path,
        default=None,
        help="Optional path to an already-built safetrace-backend.exe to copy into the package",
    )
    parser.add_argument("--clean", action="store_true", help="Remove existing dist/SafeTrace before creating it")
    parser.add_argument("--dry-run", action="store_true", help="Print the planned package path and exclusions only")
    parser.add_argument(
        "--strict-assets",
        action="store_true",
        help="Fail when release package assets such as backend exe, config, MobileSAM, chat, or VLM are missing",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = repo_root_from_script()
    package = package_root(repo_root, args.output_dir)
    if args.dry_run:
        return print_dry_run(repo_root, package, args.backend_exe, args.strict_assets)
    try:
        summary = build_prototype(
            repo_root,
            args.output_dir,
            clean=args.clean,
            backend_exe=args.backend_exe,
            strict_assets=args.strict_assets,
        )
    except AssetValidationError as exc:
        print(str(exc))
        return 2
    print_summary(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
