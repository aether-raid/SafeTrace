"""Create a local SafeTrace desktop package prototype.

This script prepares a replaceable-runtime package layout under dist/SafeTrace.
It does not build a final .exe and intentionally excludes local data, uploads,
generated media, checkpoints, and model files.
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
PROTECTED_ASSET_RULES = [
    "*.gguf",
    "*.bin",
    "*.safetensors",
    "*.pt",
    "*.pth",
    "checkpoints/",
    "data/",
    "uploads/",
    "generated/",
    "generated_media/",
    "models/chat/*.gguf",
]
PRESERVE_PATHS = ["config/", "data/", "models/", "logs/"]


LAUNCHER_TEXT = r"""@echo off
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

if not defined KMP_DUPLICATE_LIB_OK set "KMP_DUPLICATE_LIB_OK=TRUE"
if not defined OMP_NUM_THREADS set "OMP_NUM_THREADS=1"
if not defined SAFETRACE_CHAT_ENABLED set "SAFETRACE_CHAT_ENABLED=auto"
if not defined SAFETRACE_CHAT_PROVIDER set "SAFETRACE_CHAT_PROVIDER=packaged_llamacpp"
if not defined SAFETRACE_CHAT_SPEED_PROFILE set "SAFETRACE_CHAT_SPEED_PROFILE=fast"
if not defined SAFETRACE_CHAT_MODEL_PATH set "SAFETRACE_CHAT_MODEL_PATH=models\chat\safetrace-assistant-qwen2.5-1.5b-instruct-q4.gguf"
if not defined SAFETRACE_SERVE_FRONTEND set "SAFETRACE_SERVE_FRONTEND=true"
if not defined SAFETRACE_FRONTEND_DIST set "SAFETRACE_FRONTEND_DIST=frontend\dist"
if not defined SAFETRACE_BUILD_MODE set "SAFETRACE_BUILD_MODE=prototype"
if not defined SAFETRACE_RUNTIME_LAYOUT set "SAFETRACE_RUNTIME_LAYOUT=packaged"

echo [SafeTrace] App root: "%APP_ROOT%"
echo [SafeTrace] Backend health: http://127.0.0.1:8000/api/health
echo [SafeTrace] Frontend:       http://127.0.0.1:8000/
echo [SafeTrace] Runtime layout: %SAFETRACE_RUNTIME_LAYOUT%
echo.

if exist "backend\safetrace-backend.exe" (
  start "SafeTrace Backend" /D "%APP_ROOT%" cmd /k "backend\safetrace-backend.exe --host 127.0.0.1 --port 8000"
  timeout /t 3 /nobreak >nul
  start "" "http://127.0.0.1:8000/"
  exit /b 0
)

echo [SafeTrace] Prototype package does not include a final backend .exe.
echo [SafeTrace] Build or copy backend\safetrace-backend.exe in a future packaging phase.
exit /b 1
"""


BACKEND_README = """SafeTrace backend runtime placeholder.

Future packaging should place safetrace-backend.exe and runtime dependencies in
this folder. Do not place data, logs, uploads, checkpoints, or model files here.
"""


FRONTEND_README = """SafeTrace frontend dist placeholder.

Run the React production build first if you want this prototype package to
include frontend assets:

  cd frontend-react
  npm.cmd run build
"""


def repo_root_from_script() -> Path:
    return Path(__file__).resolve().parents[1]


def package_root(repo_root: Path, output_dir: Path | None = None) -> Path:
    base = output_dir or repo_root / "dist"
    return base / PACKAGE_DIRNAME


def manifest_payload() -> dict:
    return {
        "component": "safetrace-desktop-package",
        "version": "0.0.0-dev",
        "build_mode": "prototype",
        "schema_version": 1,
        "frontend": {
            "dist_path": "frontend/dist",
            "served_by_backend": True,
        },
        "backend": {
            "layout": "backend/",
            "entrypoint": "safetrace-backend.exe",
            "manifest": "backend/backend_manifest.json",
        },
        "preserve_paths": PRESERVE_PATHS,
        "excluded_asset_rules": PROTECTED_ASSET_RULES,
        "notes": "Prototype package only. Do not commit generated dist/SafeTrace output.",
    }


def backend_manifest_payload() -> dict:
    return {
        "component": "safetrace-backend",
        "version": "0.0.0-dev",
        "build_mode": "prototype",
        "requires_frontend_version": ">=0.0.0",
        "schema_version": 1,
        "entrypoint": "safetrace-backend.exe",
        "preserve_paths": PRESERVE_PATHS,
        "notes": "Prototype manifest only. Do not place model files in backend builds.",
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
            "*.gguf",
            "*.bin",
            "*.safetensors",
            "*.pt",
            "*.pth",
            "data",
            "uploads",
            "generated",
            "generated_media",
            "checkpoints",
        ),
    )
    return True


def copy_config_example(repo_root: Path, package: Path) -> bool:
    source = repo_root / "config" / "safetrace.env.example"
    if not source.exists():
        return False
    shutil.copy2(source, package / "config" / "safetrace.env.example")
    return True


def copy_backend_exe_if_exists(repo_root: Path, package: Path, backend_exe: Path | None = None) -> bool:
    source = backend_exe or repo_root / DEFAULT_BACKEND_EXE
    if not source.is_absolute():
        source = repo_root / source
    if not source.is_file():
        return False
    target = package / PACKAGED_BACKEND_EXE
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return True


def build_prototype(
    repo_root: Path,
    output_dir: Path | None = None,
    *,
    clean: bool = False,
    backend_exe: Path | None = None,
) -> dict:
    repo_root = repo_root.resolve()
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
            "data",
            "logs",
        ],
    )

    write_text(package / "SafeTraceLauncher.bat", LAUNCHER_TEXT)
    write_text(package / "backend" / "README.txt", BACKEND_README)
    write_json(package / "backend" / "backend_manifest.json", backend_manifest_payload())
    write_json(package / "packaging_manifest.json", manifest_payload())

    backend_exe_copied = copy_backend_exe_if_exists(repo_root, package, backend_exe)
    copied_config = copy_config_example(repo_root, package)
    frontend_copied = copy_if_exists(repo_root / "frontend-react" / "dist", package / "frontend" / "dist")
    if not frontend_copied:
        write_text(package / "frontend" / "dist" / "README.txt", FRONTEND_README)

    warnings = [
        "Excluded local data, uploads, generated reports, generated media, and cache folders.",
        "Excluded checkpoints and model assets, including GGUF chat models.",
    ]
    if not backend_exe_copied:
        warnings.append("Backend executable not found; created a placeholder backend folder only.")
    if not copied_config:
        warnings.append("config/safetrace.env.example was not found in the source tree.")
    if not frontend_copied:
        warnings.append("frontend-react/dist was not found; created a frontend placeholder instead.")

    return {
        "package_root": str(package),
        "created_dirs": [str(path) for path in created_dirs],
        "backend_exe_copied": backend_exe_copied,
        "frontend_copied": frontend_copied,
        "config_copied": copied_config,
        "preserve_paths": PRESERVE_PATHS,
        "excluded_asset_rules": PROTECTED_ASSET_RULES,
        "warnings": warnings,
    }


def print_summary(summary: dict) -> None:
    print(f"SafeTrace desktop prototype: {summary['package_root']}")
    print("Created package folders:")
    for path in summary["created_dirs"]:
        print(f"  - {path}")
    print(f"Backend executable copied: {summary['backend_exe_copied']}")
    print(f"Frontend dist copied: {summary['frontend_copied']}")
    print(f"Config example copied: {summary['config_copied']}")
    print("Preserved external paths:")
    for path in summary["preserve_paths"]:
        print(f"  - {path}")
    print("Intentional exclusions:")
    for rule in summary["excluded_asset_rules"]:
        print(f"  - {rule}")
    print("Warnings:")
    for warning in summary["warnings"]:
        print(f"  - {warning}")


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
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = repo_root_from_script()
    package = package_root(repo_root, args.output_dir)
    if args.dry_run:
        print(f"Would create SafeTrace desktop prototype at: {package}")
        backend_exe = args.backend_exe or repo_root / DEFAULT_BACKEND_EXE
        print(f"Would copy backend exe if present: {backend_exe}")
        print("Would exclude:")
        for rule in PROTECTED_ASSET_RULES:
            print(f"  - {rule}")
        return 0
    summary = build_prototype(repo_root, args.output_dir, clean=args.clean, backend_exe=args.backend_exe)
    print_summary(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
