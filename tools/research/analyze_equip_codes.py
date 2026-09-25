import collections
import json
import re

from tools.project_paths import EQUIPMENT_DATA_DIR


obs = json.loads(
    (EQUIPMENT_DATA_DIR / "equip_ground_truth.json").read_text(
        encoding="utf-8"
    )
)
def stem(s):
 s=s.replace('→','-').replace('一','1')
 s=re.sub(r'[+\-]?\d+%?|ALL$','',s)
 return s
by=collections.defaultdict(collections.Counter)
for o in obs: by[o['bytes'][0]][stem(o['effect'])]+=1
for code,c in sorted(by.items()):
 print(f'{code:02x}',sum(c.values()),c.most_common())
