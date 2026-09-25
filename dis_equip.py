from pathlib import Path
from runtime_loader import install
install(Path.cwd().parent/'exe-analysis'/'tool.exe_extracted')
import models.CczEquip as e, dis
for fn in ['__initEquipMat','__initEquipSkillMap','addEquipWithMat','getEquipByMat','getEquipSkillNameByMat','getEquipInfoTupleList','_getSetEquips']:
 print('\n###',fn); dis.dis(e.__dict__.get(fn) or getattr(e,fn))
for cls in [e.CczEuqip,e.CczEquipSkill]:
 print('\n### CLASS',cls.__name__); dis.dis(cls.__init__)
