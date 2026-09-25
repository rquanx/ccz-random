from pathlib import Path
p=Path(r'E:\game\ccz\曹操传加强版V2.10.4c\曹操传加强版V2.10.4c\Imsg.e5')
b=p.read_bytes()
for off in [0x11d46]:
 print(b[off-300:off+500].decode('gbk',errors='replace'))
# extract null/control separated GBK runs containing Chinese, 3+ chars
out=[]; start=0
for i,x in enumerate(b+b'\0'):
 if x in (0,10,13) or x<9:
  if i-start>=4:
   raw=b[start:i]
   try:s=raw.decode('gbk')
   except: s=''
   if any('\u4e00'<=c<='\u9fff' for c in s): out.append((start,s))
  start=i+1
print('count',len(out))
for off,s in out[:300]: print(hex(off),repr(s))
