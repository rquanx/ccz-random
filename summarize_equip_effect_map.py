import json,collections
m=json.load(open('equip_effect_map.json',encoding='utf8'))
by=collections.defaultdict(list)
for k,v in m.items():
 c,p=(int(x,16) for x in k.split(':'));by[c].append((p,v))
open('equip_effect_code_summary.json','w',encoding='utf8').write(json.dumps({f'{c:02x}':sorted(vals) for c,vals in sorted(by.items())},ensure_ascii=False,indent=2))
