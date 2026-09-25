import json
obs=json.load(open('equip_ground_truth.json',encoding='utf8'))
for o in obs:
 if o['slot']==1:
  print(f"{o['index']:02} {o['name']} {o['record']} {o['effect']}")
