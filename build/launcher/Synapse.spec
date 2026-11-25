
# -*- mode: python ; coding: utf-8 -*-

import os

from PyInstaller.utils.hooks import (
    collect_all,
    collect_submodules,
)

PROJECT_ROOT = os.path.abspath(
    os.path.join(SPECPATH, "..", "..")
)
APP_ROOT = os.path.join(PROJECT_ROOT, "Application")
MAIN_PATH = os.path.join(APP_ROOT, "main.py")
ICON_PATH = os.path.join(APP_ROOT, "assets", "synapse_logo.ico")
VERSION_PATH = os.path.join(APP_ROOT, "version.txt")

if not os.path.isfile(VERSION_PATH):
    raise FileNotFoundError(
        f"Application version file not found: {VERSION_PATH}"
    )

datas = [
    (os.path.join(APP_ROOT, "assets"), "assets"),
    (os.path.join(APP_ROOT, "styles"), "styles"),
    (os.path.join(APP_ROOT, "web"), "web"),
    (VERSION_PATH, "."),
]

pynput_datas, pynput_binaries, pynput_hiddenimports = collect_all("pynput")
datas += pynput_datas

hiddenimports = (
    collect_submodules("core")
    + collect_submodules("pages")
    + pynput_hiddenimports
    + [
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtWebChannel",
    ]
)

a = Analysis(
    [MAIN_PATH],
    pathex=[APP_ROOT],
    binaries=pynput_binaries,
    datas=datas,
    hiddenimports=hiddenimports,
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
    [],
    exclude_binaries=True,
    name="Synapse",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=ICON_PATH,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Synapse",
)
