from pathlib import Path

from PyInstaller.utils.hooks import collect_all, copy_metadata


PROJECT_ROOT = Path(SPECPATH)

datas = []
binaries = []
hiddenimports = []

# PaddleOCR and PaddleX load pipeline modules, native libraries, and model
# configuration files lazily.  Explicit collection keeps those resources in the
# onedir bundle even when PyInstaller cannot see them from the import graph.
for package in ("paddle", "paddleocr", "paddlex", "customtkinter"):
    package_datas, package_binaries, package_hiddenimports = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hiddenimports

# OcrEnvironmentManager reads these versions through importlib.metadata.
for distribution in ("paddlepaddle", "paddleocr", "paddlex"):
    datas += copy_metadata(distribution)


a = Analysis(
    [str(PROJECT_ROOT / "main.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "pytesseract",
        "tkinter.test",
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MegidoOCR2Excel",
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
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="MegidoOCR2Excel",
)
