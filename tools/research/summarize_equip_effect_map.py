import json,collections
from tools.project_paths import EQUIPMENT_DATA_DIR

m=json.loads((EQUIPMENT_DATA_DIR/'equip_effect_map.json').read_text(encoding='utf8'))
by=collections.defaultdict(list)
for k,v in m.items():
 c,p=(int(x,16) for x in k.split(':'));by[c].append((p,v))
(EQUIPMENT_DATA_DIR/'equip_effect_code_summary.json').write_text(json.dumps({f'{c:02x}':sorted(vals) for c,vals in sorted(by.items())},ensure_ascii=False,indent=2),encoding='utf8')
