from pathlib import Path
from runtime_loader import install
root=Path.cwd().parent/'exe-analysis'/'tool.exe_extracted'
install(root)
import models.CczModels as m
for group in ['jobs','skills','carrySkills','imbaSkills','specialSkills']:
 print('\n['+group+']')
 for i,x in enumerate(getattr(m.CCZ_MODELS,group)):
  print(i, {k:(str(v) if k=='type' else v) for k,v in vars(x).items() if k!='mat'}, 'shape',getattr(x,'mat',None).shape if hasattr(getattr(x,'mat',None),'shape') else None)
