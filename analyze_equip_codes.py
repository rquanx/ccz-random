import json,re,collections
obs=json.load(open('equip_ground_truth.json',encoding='utf8'))
def stem(s):
 s=s.replace('→','-').replace('一','1')
 s=re.sub(r'[+\-]?\d+%?|ALL$','',s)
 return s
by=collections.defaultdict(collections.Counter)
for o in obs: by[o['bytes'][0]][stem(o['effect'])]+=1
for code,c in sorted(by.items()):
 print(f'{code:02x}',sum(c.values()),c.most_common())
