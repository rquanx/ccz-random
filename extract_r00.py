from pathlib import Path
p=Path(r'E:\game\ccz\曹操传加强版V2.10.4c\曹操传加强版V2.10.4c\RS\R_00.eex'); b=p.read_bytes()
# scan printable GBK strings separated by control bytes, minimum 2 Chinese chars
runs=[]
for start in range(len(b)):
 if start and b[start-1]>=0x20: continue
 for end in range(start+4,min(len(b),start+500)):
  if b[end]<0x20:
   raw=b[start:end]
   try:s=raw.decode('gbk')
   except: break
   if sum('\u4e00'<=c<='\u9fff' for c in s)>=2 and all(c.isprintable() for c in s): runs.append((start,s))
   break
seen=set()
for off,s in runs:
 if (off,s) in seen: continue
 seen.add((off,s)); print(hex(off),repr(s))
