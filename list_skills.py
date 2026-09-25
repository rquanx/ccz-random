from pathlib import Path
root=Path(r'C:\Users\91658\Documents\Codex\2026-09-18\hi\work\exe-analysis\tool.exe_extracted\templates\ccz\skill')
for d in sorted(root.iterdir()):
 if d.is_dir():
  fs=sorted(d.glob('*.png'))
  print(f'[{d.name}] {len(fs)}')
  for i,f in enumerate(fs): print(i, f.name)
