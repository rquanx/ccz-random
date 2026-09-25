from pathlib import Path
from runtime_loader import install
root=Path.cwd().parent/'exe-analysis'/'tool.exe_extracted'; install(root)
import models.CczEquip as e, os
os.chdir(root)
for fn in ['__initEquipMat','__initEquipSkillMap']:
 print('call',fn); print(e.__dict__[fn]())
for n in ['__equipMap','__equipSkillMap','__weaponMap','__bodyMap','__assistMap']:
 v=e.__dict__[n]; print('\n',n,len(v));
 for k,x in list(v.items())[:10]: print(repr(k),repr(vars(x)) if hasattr(x,'__dict__') else repr(x))
print('all info')
try:
 print(e.getEquipInfoTupleList())
except Exception as ex:
 print(type(ex),repr(ex))
for fn in ['getFollowUpEquips','getLegacyEquips','getLvbuEquips','getZhugeliangEquips','getLiubeiEquips','getGuanyuEquips','getZhangfeiEquips','getZhaoyunEquips','getEquipsWithGoodSkills']:
 print(fn,repr(getattr(e,fn)()))
