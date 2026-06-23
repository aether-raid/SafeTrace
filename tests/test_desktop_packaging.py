import json
import os
import sys
from pathlib import Path

from fastapi.testclient import TestClient

import src.api.server as server_module
from scripts.build_backend_exe import BACKEND_EXE_NAME, DEFAULT_DIST_DIR, build_command
from scripts.build_desktop_prototype import PROTECTED_ASSET_RULES, build_prototype
from src.api.batches import BatchStore
from src.api.jobs import JobStore
from src.api.server import create_app


def test_config_example_exists_with_packaged_defaults():
    path = Path("config/safetrace.env.example")

    assert path.is_file()
    content = path.read_text(encoding="utf-8")
    assert "KMP_DUPLICATE_LIB_OK=TRUE" in content
    assert "SAFETRACE_CHAT_PROVIDER=packaged_llamacpp" in content
    assert "SAFETRACE_SERVE_FRONTEND=true" in content
    assert "SAFETRACE_FRONTEND_DIST=frontend/dist" in content


def test_desktop_manifest_example_shape():
    path = Path("packaging/desktop_packaging_manifest.example.json")

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["component"] == "safetrace-desktop-package"
    assert payload["schema_version"] == 1
    assert payload["frontend"]["dist_path"] == "frontend/dist"
    assert payload["backend"]["entrypoint"] == "safetrace-backend.exe"
    assert "config/" in payload["preserve_paths"]
    assert "*.gguf" in payload["excluded_asset_rules"]


def test_package_script_creates_layout_without_protected_assets(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "config").mkdir()
    (repo / "config" / "safetrace.env.example").write_text("SAFETRACE_SERVE_FRONTEND=true\n", encoding="utf-8")
    (repo / "frontend-react" / "dist" / "assets").mkdir(parents=True)
    (repo / "frontend-react" / "dist" / "index.html").write_text("<div>SafeTrace</div>", encoding="utf-8")
    (repo / "frontend-react" / "dist" / "assets" / "index.js").write_text("console.log('ok');", encoding="utf-8")
    (repo / "models" / "chat").mkdir(parents=True)
    (repo / "models" / "chat" / "model.gguf").write_bytes(b"model")
    (repo / "data").mkdir()
    (repo / "data" / "upload.mp4").write_bytes(b"video")

    summary = build_prototype(repo, tmp_path / "out", clean=True)
    package = Path(summary["package_root"])

    assert (package / "SafeTraceLauncher.bat").is_file()
    assert (package / "backend" / "backend_manifest.json").is_file()
    assert not (package / "backend" / "safetrace-backend.exe").exists()
    assert (package / "frontend" / "dist" / "index.html").is_file()
    assert (package / "config" / "safetrace.env.example").is_file()
    assert (package / "models" / "chat").is_dir()
    assert (package / "data").is_dir()
    assert (package / "logs").is_dir()
    assert (package / "packaging_manifest.json").is_file()
    assert not list(package.rglob("*.gguf"))
    assert not (package / "data" / "upload.mp4").exists()
    assert summary["backend_exe_copied"] is False
    assert "*.gguf" in summary["excluded_asset_rules"]
    assert PROTECTED_ASSET_RULES == summary["excluded_asset_rules"]


def test_package_script_copies_existing_backend_exe_only_when_present(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    backend_exe = repo / DEFAULT_DIST_DIR / BACKEND_EXE_NAME
    backend_exe.parent.mkdir(parents=True)
    backend_exe.write_bytes(b"local exe placeholder")

    summary = build_prototype(repo, tmp_path / "out", clean=True)
    package = Path(summary["package_root"])

    assert summary["backend_exe_copied"] is True
    assert (package / "backend" / "safetrace-backend.exe").read_bytes() == b"local exe placeholder"
    assert not list(package.rglob("*.gguf"))
    assert not list(package.rglob("*.pt"))
    assert not list(package.rglob("*.safetensors"))


def test_backend_entrypoint_imports_and_loads_env(monkeypatch, tmp_path):
    from src.api import __main__ as backend_entrypoint

    env_file = tmp_path / "safetrace.env"
    env_file.write_text(
        "\n".join(
            [
                "# local settings",
                "SAFETRACE_HOST=127.0.0.2",
                "SAFETRACE_PORT=8010",
                "IGNORED_LINE",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("SAFETRACE_HOST", raising=False)
    monkeypatch.delenv("SAFETRACE_PORT", raising=False)

    loaded = backend_entrypoint.load_env_file(env_file)
    args = backend_entrypoint.parse_args(["--port", "8011"])

    assert loaded == ["SAFETRACE_HOST", "SAFETRACE_PORT"]
    assert args.port == 8011
    assert backend_entrypoint.DEFAULT_HOST == "127.0.0.1"


def test_backend_entrypoint_packaged_defaults(monkeypatch, tmp_path):
    from src.api import __main__ as backend_entrypoint

    for key in (
        "SAFETRACE_PROJECT_ROOT",
        "SAFETRACE_DATA_DIR",
        "SAFETRACE_CHECKPOINTS_DIR",
        "SAFETRACE_SERVE_FRONTEND",
        "SAFETRACE_RUNTIME_LAYOUT",
    ):
        monkeypatch.delenv(key, raising=False)

    backend_entrypoint.apply_packaged_defaults(tmp_path)

    assert Path(os.environ["SAFETRACE_PROJECT_ROOT"]) == tmp_path
    assert Path(os.environ["SAFETRACE_DATA_DIR"]) == tmp_path / "data"
    assert Path(os.environ["SAFETRACE_CHECKPOINTS_DIR"]) == tmp_path / "checkpoints"
    assert os.environ["SAFETRACE_SERVE_FRONTEND"] == "true"
    assert os.environ["SAFETRACE_RUNTIME_LAYOUT"] == "packaged"


def test_backend_exe_build_command_is_dry_run_friendly(tmp_path):
    command = build_command(tmp_path)

    assert command[:3] == [sys.executable, "-m", "PyInstaller"]
    assert "--distpath" in command
    assert str(tmp_path / "dist" / "backend") in command
    assert str(tmp_path / "packaging" / "backend" / "safetrace_backend.spec") in command


def test_static_frontend_serving_preserves_api_routes(monkeypatch, tmp_path):
    frontend_dist = tmp_path / "frontend" / "dist"
    (frontend_dist / "assets").mkdir(parents=True)
    (frontend_dist / "index.html").write_text("<html><body>SafeTrace app</body></html>", encoding="utf-8")
    (frontend_dist / "assets" / "index.js").write_text("console.log('asset');", encoding="utf-8")

    monkeypatch.setattr(server_module.SETTINGS, "serve_frontend", True)
    monkeypatch.setattr(server_module.SETTINGS, "frontend_dist", frontend_dist)
    client = TestClient(create_app(JobStore(tmp_path / "jobs"), BatchStore(tmp_path / "batches")))

    health = client.get("/api/health")
    index = client.get("/")
    nested = client.get("/review/job_123")
    asset = client.get("/assets/index.js")
    missing_api = client.get("/api/not-a-real-route")

    assert health.status_code == 200
    assert health.json()["api"] == "safetrace-local"
    assert index.status_code == 200
    assert "SafeTrace app" in index.text
    assert nested.status_code == 200
    assert "SafeTrace app" in nested.text
    assert asset.status_code == 200
    assert "asset" in asset.text
    assert missing_api.status_code == 404
    assert "SafeTrace app" not in missing_api.text


def test_system_status_reports_packaged_metadata(monkeypatch, tmp_path):
    monkeypatch.setenv("SAFETRACE_BUILD_MODE", "prototype")
    monkeypatch.setenv("SAFETRACE_RUNTIME_LAYOUT", "packaged")
    client = TestClient(create_app(JobStore(tmp_path / "jobs"), BatchStore(tmp_path / "batches")))

    response = client.get("/api/system/status")

    assert response.status_code == 200
    body = response.json()
    assert body["build_mode"] == "prototype"
    assert body["runtime_layout"] == "packaged"
    assert body["runtime"]["frontend"]["serveFrontend"] is False


def test_system_status_defaults_to_source_without_models_or_ollama(monkeypatch, tmp_path):
    monkeypatch.delenv("SAFETRACE_BUILD_MODE", raising=False)
    monkeypatch.delenv("SAFETRACE_RUNTIME_LAYOUT", raising=False)
    monkeypatch.setattr(server_module.SETTINGS, "chat_provider", "packaged_llamacpp")
    monkeypatch.setattr(server_module.SETTINGS, "chat_model_path", tmp_path / "missing.gguf")
    client = TestClient(create_app(JobStore(tmp_path / "jobs"), BatchStore(tmp_path / "batches")))

    response = client.get("/api/system/status")

    assert response.status_code == 200
    body = response.json()
    assert body["build_mode"] == "development"
    assert body["runtime_layout"] == "source"
    assert body["runtime"]["chat"]["provider"] == "packaged_llamacpp"
    assert body["preflight"]["checks"]["assistant"]["details"]["provider"] == "packaged_llamacpp"
