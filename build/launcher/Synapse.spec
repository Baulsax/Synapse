
# -*- mode: python ; coding: utf-8 -*-

import os

PROJECT_ROOT = os.path.abspath(
    os.path.join(SPECPATH, "..", "..")
)

LAUNCHER_PATH = os.path.join(
    PROJECT_ROOT,
    "Application",
    "launcher.py"
)

ICON_PATH = os.path.join(
    PROJECT_ROOT,
    "Application",
    "assets",
    "synapse_logo.ico"
)

a = Analysis(
    [LAUNCHER_PATH],
    pathex=[PROJECT_ROOT],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="Synapse",
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
    icon=ICON_PATH,
)
