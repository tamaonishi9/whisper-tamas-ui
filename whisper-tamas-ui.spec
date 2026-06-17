# -*- mode: python ; coding: utf-8 -*-
import glob
import os

from PyInstaller.utils.hooks import collect_all
from PyInstaller.utils.hooks import collect_dynamic_libs

datas = []
binaries = []
hiddenimports = []

binaries += collect_dynamic_libs("ctranslate2")

for package_name in ("faster_whisper", "ctranslate2", "tokenizers", "PIL", "pynput"):
    collected = collect_all(package_name)
    datas += collected[0]
    binaries += collected[1]
    hiddenimports += collected[2]

# GPU(CUDA)実行用DLLをcuda_libsへ同梱する
# nvidia-cublas-cu12 / nvidia-cudnn-cu12(8.x) / nvidia-cuda-nvrtc-cu12 が必要
# 未インストール時（CPU専用ビルド）は何も追加されずCPU動作のままになる
_venv_site = os.path.join(os.getcwd(), ".venv", "Lib", "site-packages")
for _sub in ("nvidia/cublas/bin", "nvidia/cudnn/bin", "nvidia/cuda_nvrtc/bin"):
    for _dll in glob.glob(os.path.join(_venv_site, _sub, "*.dll")):
        binaries.append((_dll, "cuda_libs"))


a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
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
    name="WhisperTamas",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    version="file_version_info.txt",
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
    name="WhisperTamas",
)
