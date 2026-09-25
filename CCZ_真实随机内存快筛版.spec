# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path


extracted_root = Path(
    'C:/Users/91658/Documents/Codex/2026-09-18/hi/work/'
    'exe-analysis/tool.exe_extracted'
)
excluded_original_folders = {
    'cv2',
    'numpy',
    'numpy.libs',
    'numpy-2.4.6.dist-info',
    'PIL',
}
runtime_packages = {
    'cfg',
    'encrypt',
    'keyboard',
    'models',
    'pydirectinput',
    'task',
    'utils',
    'win32con',
    'window',
}
excluded_original_files = {
    'PYZ.pyz',
    'base_library.zip',
    'cczReRand.pyc',
    'python314.dll',
    'after-click.png',
    'before-click.png',
    'choice-after.bin',
    'choice-before.bin',
    'choice-menu.bin',
    'choice-runtime-code.txt',
    'loaded-row0-memory.bin',
    'r1_jobs_round20.json',
    'robust-loaded.png',
    'title-y72.png',
    'title-y135.png',
    'title-y198.png',
    'title-y261.png',
}
original_datas = []
for source in extracted_root.rglob('*'):
    if not source.is_file():
        continue
    relative = source.relative_to(extracted_root)
    if relative.parts[0] in excluded_original_folders:
        continue
    if len(relative.parts) == 1 and (
        relative.name in excluded_original_files
        or relative.name.startswith('probe-')
    ):
        continue
    if relative.parts[0] == 'PYZ.pyz_extracted':
        module_name = Path(relative.parts[1]).stem
        if module_name not in runtime_packages:
            continue
    destination = Path('original') / relative.parent
    original_datas.append((str(source), str(destination)))


a = Analysis(
    ['fast_randomizer.py'],
    pathex=[],
    binaries=[],
    datas=original_datas + [
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
