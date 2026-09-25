import os,json
from pathlib import Path
from tools.project_paths import EQUIPMENT_DATA_DIR
from tools.research.build_equip_ground_truth import records
root=Path(os.environ['CCZ_GAME_ROOT'])/'SV'
all_codes=set()
for slot in range(1,16):
 for r in records((root/f'SV{slot:03}.E5S').read_bytes()): all_codes.add(r[0])
obs=json.loads((EQUIPMENT_DATA_DIR/'equip_ground_truth.json').read_text(encoding='utf8')); mapped={o['bytes'][0] for o in obs}
print('all',len(all_codes),' '.join(f'{x:02x}' for x in sorted(all_codes)))
print('mapped',len(mapped),'missing',' '.join(f'{x:02x}' for x in sorted(all_codes-mapped)))
