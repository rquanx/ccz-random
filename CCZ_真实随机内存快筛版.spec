# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['fast_randomizer.py'],
    pathex=[],
    binaries=[],
    datas=[
        (
            'C:/Users/91658/Documents/Codex/2026-09-18/hi/work/exe-analysis/tool.exe_extracted',
            'original',
        ),
        ('random_s00.eex', '.'),
        ('source_slot_20_help.png', '.'),
        ('native/ccz_control.dll', 'native'),
        ('native/ccz_injector.exe', 'native'),
    ],
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
    name='2.10随机工具',
    icon='2.10随机工具.ico',
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
)
