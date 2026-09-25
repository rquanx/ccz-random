from pathlib import Path
import re,json
root=Path('../exe-analysis/tool.exe_extracted/templates/ccz/equip/skill')
names=set()
for p in root.rglob('*.png'):
 s=p.stem
 if s.startswith('prefix_'):
  parts=s.split('_',2)
  if len(parts)==3:names.add(parts[2])
 else:
  parts=s.split('_',1)
  if len(parts)==2:names.add(parts[1])
print(len(names))
Path('equip_skill_names.txt').write_text('\n'.join(sorted(names)),encoding='utf8')
