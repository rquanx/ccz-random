import json
from tools.project_paths import EQUIPMENT_DATA_DIR

obs=json.loads((EQUIPMENT_DATA_DIR/'equip_ground_truth.json').read_text(encoding='utf8'))
for o in obs:
 if o['slot']==1:
  print(f"{o['index']:02} {o['name']} {o['record']} {o['effect']}")
