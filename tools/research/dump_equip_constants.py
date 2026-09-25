from pathlib import Path
from runtime_loader import install
import json,os
from tools.project_paths import EQUIPMENT_DATA_DIR

root=Path.cwd().parent/'exe-analysis'/'tool.exe_extracted';install(root);import models.CczEquip as e
out={n:e.__dict__[n] for n in ['__GOOD_SKILL_PREFIX_LIST','__FOLLOW_UP_EQUIP_LIST','__LEGACY_LIST','__LVBU_EQUIP_LIST','__ZHUGELIANG_EQUIP_LIST','__LIUBEI_EQUIP_LIST','__GUANYU_EQUIP_LIST','__ZHANGFEI_EQUIP_LIST','__ZHAOYUN_EQUIP_LIST']}
(EQUIPMENT_DATA_DIR/'equip_private_constants.json').write_text(json.dumps(out,ensure_ascii=True,indent=2),encoding='ascii')
