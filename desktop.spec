# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files

a = Analysis(
    ['desktop.py'],
    pathex=[],
    binaries=[],
    datas=[('index.html', '.'), ('app.js', '.'), ('style.css', '.')] + collect_data_files('certifi'),
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='ProjectWorkspace', console=True)
coll = COLLECT(exe, a.binaries, a.datas, name='ProjectWorkspace')
