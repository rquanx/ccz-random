from pathlib import Path
from runtime_loader import install
root=Path.cwd().parent/'exe-analysis'/'tool.exe_extracted'; install(root)
import models.CczEquip as e, os
os.chdir(root)
e.__dict__['__initEquipMat']()
for n in ['__equipMap','__weaponMap','__bodyMap','__assistMap','__attachEquipMap']:
 v=e.__dict__[n]; print('\n',n,len(v));
 for k,x in list(v.items())[:100]: print(repr(k),repr(vars(x)) if hasattr(x,'__dict__') else repr(x))
