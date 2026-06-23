# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller prototype spec for the SafeTrace backend.

This spec intentionally excludes local model files, data, uploads, generated
media, logs, and frontend assets. Those assets are supplied beside the packaged
runtime by the desktop package layout.
"""
from pathlib import Path


repo_root = Path(SPECPATH).parents[1]

block_cipher = None

a = Analysis(
    [str(repo_root / "src" / "api" / "__main__.py")],
    pathex=[str(repo_root)],
    binaries=[],
    datas=[],
    hiddenimports=[
        "src.api.server",
        "uvicorn",
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="safetrace-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
