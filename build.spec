# -*- mode: python ; coding: utf-8 -*-
# Fichier de build PyInstaller pour Discord Server Cloner.
# Compilation : pyinstaller build.spec

import customtkinter
from pathlib import Path

ctk_path = Path(customtkinter.__file__).parent

a = Analysis(
    ["app.py"],
    pathex=[],
    binaries=[],
    datas=[
        (str(ctk_path), "customtkinter"),
        ("assets", "assets"),
    ],
    hiddenimports=["discord", "aiohttp"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="DiscordServerCloner",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/icon.ico",
)
