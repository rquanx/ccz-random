from pathlib import Path
from runtime_loader import install
install(Path.cwd().parent/'exe-analysis'/'tool.exe_extracted')
import models.CczModels as m
for objname in ['CCZ_MODELS','CCZ_SKILL_UNKNOWN','CCZ_JOB_UNKNOWN']:
 obj=getattr(m,objname); print('\n',objname,vars(obj))
print('types', list(m.CczType))
for cls in [m.CczSkill,m.CczJob,m.CczMember]:
 print('\nCLASS',cls.__name__)
 print('attrs', cls.__dict__)
root=Path.cwd().parent/'exe-analysis'/'tool.exe_extracted'/'templates'/'ccz'/'skill'
for d in root.iterdir():
 if d.is_dir():
  fs=sorted(d.glob('*.png'))
  print('\n',d.name,len(fs))
  for f in fs: print(f.name)
