from pathlib import Path
root=Path(r'E:\game\ccz\曹操传加强版V2.10.4c\曹操传加强版V2.10.4c')
terms=['攻击绝对命中','众志成城','引导攻击','迅捷之勇','远距攻击','策略模仿','个人天赋','兵种技能']
files=[p for p in root.rglob('*') if p.is_file() and p.stat().st_size<100_000_000]
for term in terms:
 print('\nTERM',term)
 for enc in ['gbk','utf-8','utf-16le','utf-16be']:
  pat=term.encode(enc,errors='ignore')
  found=[]
  for p in files:
   try: b=p.read_bytes()
   except: continue
   pos=b.find(pat)
   if pos>=0: found.append((str(p.relative_to(root)),hex(pos),enc))
  if found:
   print(found[:20])
