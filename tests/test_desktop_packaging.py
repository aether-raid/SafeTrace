import json
import os
import sys
from pathlib import Path

from fastapi.testclient import TestClient

import src.api.server as server_module
from scripts.build_backend_exe import BACKEND_EXE_NAME, DEFAULT_DIST_DIR, build_command
from scripts.build_desktop_prototype import (
    PACKAGE_ASSET_ALLOWLIST,
    PROTECTED_ASSET_RULES,
    AssetValidationError,
    build_prototype,
)
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
    assert "SAFETRACE_MOBILESAM_CHECKPOINT=checkpoints/mobile_sam.pt" in content
    assert "SAFETRACE_VLM_PROVIDER=auto" in content
    assert "SAFETRACE_VLM_MODEL_PATH=models/vlm" in content
    assert "SAFETRACE_VLM_DIR=models/vlm" in content
    assert "SAFETRACE_VLM_MODEL=local-vlm" in content


def test_desktop_manifest_example_shape():
    path = Path("packaging/desktop_packaging_manifest.example.json")

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["component"] == "safetrace-desktop-package"
    assert payload["schema_version"] == 2
    assert payload["release_runtime_layout"]["mobileSamCheckpoint"] == "checkpoints/mobile_sam.pt"
    assert payload["release_runtime_layout"]["vlmAssets"] == "models/vlm/"
    assert payload["frontend"]["dist_path"] == "frontend/dist"
    assert payload["frontend"]["live_frontend_supported"] is True
    assert payload["backend"]["entrypoint"] == "safetrace-backend.exe"
    assert payload["packaged_assets"]["ollamaRequired"] is False
    assert payload["packaged_assets"]["chat"].startswith("models/chat/")
    assert payload["packaged_assets"]["vlm"] == "models/vlm/"
    assert "config/" in payload["preserve_paths"]
    assert "checkpoints/" in payload["preserve_paths"]
    assert "*.gguf" in payload["excluded_asset_rules"]
    assert "*.onnx" in payload["excluded_asset_rules"]
    assert "dist/SafeTrace/models/vlm/**" in payload["package_asset_allowlist"]


def test_package_script_creates_layout_and_excludes_generated_data(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "config").mkdir()
    (repo / "config" / "safetrace.env.example").write_text("SAFETRACE_SERVE_FRONTEND=true\n", encoding="utf-8")
    (repo / "frontend-react" / "dist" / "assets").mkdir(parents=True)
    (repo / "frontend-react" / "dist" / "index.html").write_text("<div>SafeTrace</div>", encoding="utf-8")
    (repo / "frontend-react" / "dist" / "assets" / "index.js").write_text("console.log('ok');", encoding="utf-8")
    (repo / "models" / "chat").mkdir(parents=True)
    (repo / "models" / "chat" / "model.gguf").write_bytes(b"model")
    (repo / "models" / "vlm").mkdir(parents=True)
    (repo / "models" / "vlm" / "config.json").write_text("{}", encoding="utf-8")
    (repo / "data").mkdir()
    (repo / "data" / "upload.mp4").write_bytes(b"video")

    summary = build_prototype(repo, tmp_path / "out", clean=True)
    package = Path(summary["package_root"])

    assert (package / "SafeTraceLauncher.bat").is_file()
    assert (package / "backend" / "backend_manifest.json").is_file()
    assert not (package / "backend" / "safetrace-backend.exe").exists()
    assert (package / "frontend" / "dist" / "index.html").is_file()
    assert (package / "config" / "safetrace.env.example").is_file()
    assert (package / "config" / "README.txt").is_file()
    assert (package / "models" / "chat").is_dir()
    assert (package / "models" / "chat" / "model.gguf").read_bytes() == b"model"
    assert (package / "models" / "vlm" / "config.json").is_file()
    assert (package / "checkpoints").is_dir()
    assert (package / "checkpoints" / "README.txt").is_file()
    assert (package / "data").is_dir()
    assert (package / "logs").is_dir()
    assert (package / "packaging_manifest.json").is_file()
    assert (package / "OPTIONAL_ASSETS_REPORT.txt").is_file()
    assert not list((package / "backend").rglob("*.gguf"))
    assert not list(package.rglob("*.pt"))
    assert not (package / "data" / "upload.mp4").exists()
    assert summary["backend_exe_copied"] is False
    assert summary["mobile_sam_checkpoint_included"] is False
    assert summary["chat_models_included"] == ["model.gguf"]
    assert summary["vlm_assets_included"] is True
    assert "*.gguf" in summary["excluded_asset_rules"]
    assert PROTECTED_ASSET_RULES == summary["excluded_asset_rules"]
    assert PACKAGE_ASSET_ALLOWLIST == summary["package_asset_allowlist"]


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


def test_package_script_copies_optional_mobilesam_checkpoint_when_present(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    checkpoint = repo / "checkpoints" / "mobile_sam.pt"
    checkpoint.parent.mkdir(parents=True)
    checkpoint.write_bytes(b"mobile sam checkpoint placeholder")
    (repo / "checkpoints" / "other_model.pt").write_bytes(b"do not copy")

    summary = build_prototype(repo, tmp_path / "out", clean=True)
    package = Path(summary["package_root"])

    assert summary["mobile_sam_checkpoint_included"] is True
    assert (package / "checkpoints" / "mobile_sam.pt").read_bytes() == b"mobile sam checkpoint placeholder"
    assert not (package / "checkpoints" / "other_model.pt").exists()
    assert not list(package.rglob("*.gguf"))


def test_package_script_copies_optional_chat_model_when_present(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    model = repo / "models" / "chat" / "assistant.gguf"
    model.parent.mkdir(parents=True)
    model.write_bytes(b"chat model placeholder")

    summary = build_prototype(repo, tmp_path / "out", clean=True)
    package = Path(summary["package_root"])

    assert summary["chat_models_included"] == ["assistant.gguf"]
    assert (package / "models" / "chat" / "assistant.gguf").read_bytes() == b"chat model placeholder"
    assert "assistant.gguf" in (package / "OPTIONAL_ASSETS_REPORT.txt").read_text(encoding="utf-8")


def test_package_script_copies_optional_vlm_assets_when_present(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    vlm_dir = repo / "models" / "vlm"
    (vlm_dir / "nested").mkdir(parents=True)
    (vlm_dir / "config.json").write_text("{}", encoding="utf-8")
    (vlm_dir / "nested" / "weights.safetensors").write_bytes(b"vlm weights placeholder")

    summary = build_prototype(repo, tmp_path / "out", clean=True)
    package = Path(summary["package_root"])

    assert summary["vlm_assets_included"] is True
    assert (package / "models" / "vlm" / "config.json").is_file()
    assert (package / "models" / "vlm" / "nested" / "weights.safetensors").read_bytes() == b"vlm weights placeholder"
    assert "local VLM assets: included" in (package / "OPTIONAL_ASSETS_REPORT.txt").read_text(encoding="utf-8")


def test_package_script_non_strict_allows_missing_release_assets(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()

    summary = build_prototype(repo, tmp_path / "out", clean=True)

    assert summary["backend_exe_copied"] is False
    assert summary["mobile_sam_checkpoint_included"] is False
    assert summary["chat_models_included"] == []
    assert summary["vlm_assets_included"] is False
    assert summary["strict_asset_failures"]


def test_package_script_strict_assets_fails_clearly_when_missing(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()

    try:
        build_prototype(repo, tmp_path / "out", clean=True, strict_assets=True)
    except AssetValidationError as exc:
        message = str(exc)
    else:  # pragma: no cover - defensive
        raise AssertionError("strict assets should fail without release assets")

    assert "Backend executable missing" in message
    assert "config/safetrace.env" in message
    assert "checkpoints/mobile_sam.pt" in message
    assert "models/chat/*.gguf" in message
    assert "models/vlm/" in message


def test_package_script_strict_assets_passes_with_release_assets(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    backend_exe = repo / DEFAULT_DIST_DIR / BACKEND_EXE_NAME
    backend_exe.parent.mkdir(parents=True)
    backend_exe.write_bytes(b"exe")
    (repo / "config").mkdir()
    (repo / "config" / "safetrace.env").write_text(
        "\n".join(
            [
                "SAFETRACE_CHAT_ENABLED=auto",
                "SAFETRACE_CHAT_PROVIDER=packaged_llamacpp",
                "SAFETRACE_VLM_ENABLED=auto",
                "SAFETRACE_VLM_PROVIDER=auto",
            ]
        ),
        encoding="utf-8",
    )
    mobile_sam = repo / "checkpoints" / "mobile_sam.pt"
    mobile_sam.parent.mkdir(parents=True)
    mobile_sam.write_bytes(b"mobile sam")
    chat_model = repo / "models" / "chat" / "assistant.gguf"
    chat_model.parent.mkdir(parents=True)
    chat_model.write_bytes(b"chat")
    vlm_dir = repo / "models" / "vlm"
    vlm_dir.mkdir(parents=True)
    (vlm_dir / "config.json").write_text("{}", encoding="utf-8")

    summary = build_prototype(repo, tmp_path / "out", clean=True, strict_assets=True)
    package = Path(summary["package_root"])

    assert summary["strict_asset_failures"] == []
    assert (package / "backend" / "safetrace-backend.exe").is_file()
    assert (package / "config" / "safetrace.env").is_file()
    assert (package / "checkpoints" / "mobile_sam.pt").is_file()
    assert (package / "models" / "chat" / "assistant.gguf").is_file()
    assert (package / "models" / "vlm" / "config.json").is_file()
    assert (package / "OPTIONAL_ASSETS_REPORT.txt").is_file()


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
        "SAFETRACE_MOBILESAM_CHECKPOINT",
        "SAFETRACE_CHAT_MODEL_PATH",
        "SAFETRACE_VLM_PROVIDER",
        "SAFETRACE_VLM_MODEL_PATH",
        "SAFETRACE_VLM_DIR",
        "SAFETRACE_VLM_MODEL",
        "SAFETRACE_SERVE_FRONTEND",
        "SAFETRACE_FRONTEND_DIST",
        "SAFETRACE_BUILD_MODE",
        "SAFETRACE_RUNTIME_LAYOUT",
    ):
        monkeypatch.delenv(key, raising=False)

    backend_entrypoint.apply_packaged_defaults(tmp_path)

    assert Path(os.environ["SAFETRACE_PROJECT_ROOT"]) == tmp_path
    assert Path(os.environ["SAFETRACE_DATA_DIR"]) == tmp_path / "data"
    assert Path(os.environ["SAFETRACE_CHECKPOINTS_DIR"]) == tmp_path / "checkpoints"
    assert Path(os.environ["SAFETRACE_MOBILESAM_CHECKPOINT"]) == tmp_path / "checkpoints" / "mobile_sam.pt"
    assert Path(os.environ["SAFETRACE_CHAT_MODEL_PATH"]) == (
        tmp_path / "models" / "chat" / "safetrace-assistant-qwen2.5-1.5b-instruct-q4.gguf"
    )
    assert os.environ["SAFETRACE_VLM_PROVIDER"] == "auto"
    assert Path(os.environ["SAFETRACE_VLM_MODEL_PATH"]) == tmp_path / "models" / "vlm"
    assert Path(os.environ["SAFETRACE_VLM_DIR"]) == tmp_path / "models" / "vlm"
    assert os.environ["SAFETRACE_VLM_MODEL"] == "local-vlm"
    assert os.environ["SAFETRACE_SERVE_FRONTEND"] == "true"
    assert Path(os.environ["SAFETRACE_FRONTEND_DIST"]) == tmp_path / "frontend" / "dist"
    assert os.environ["SAFETRACE_BUILD_MODE"] == "release-package"
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
