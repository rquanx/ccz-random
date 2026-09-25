from pathlib import Path
root=Path(r'E:\game\ccz\曹操传加强版V2.10.4c\曹操传加强版V2.10.4c')
terms=['绝对命中','攻击命中','众志成城','引导','迅捷之勇','策略模仿','穿透攻击','强化攻击','破坏耐久','天人之勇','攻击范围','远距攻击']
files=[p for p in root.rglob('*') if p.is_file() and p.stat().st_size<100_000_000]
for term in terms:
 print('\n',term)
 for enc in ['gbk','utf-8','utf-16le']:
  pat=term.encode(enc)
  found=[]
  for p in files:
   try:b=p.read_bytes()
   except:continue
   pos=0
   while True:
    pos=b.find(pat,pos)
    if pos<0:break
    found.append((str(p.relative_to(root)),hex(pos),enc)); pos+=1
    if len(found)>=20:break
  if found:print(found)
