from pathlib import Path
p=Path(r'E:\game\ccz\曹操传加强版V2.10.4c\曹操传加强版V2.10.4c\Imsg.e5'); b=p.read_bytes()
for off in [0x7080,0x16000,0x16800,0x1a000,0x1c000,0x60000,0x61000]:
 print('\nOFF',hex(off));
 raw=b[off:off+0x1000]
 # print zero separated decodable runs
 start=0
 for i,x in enumerate(raw+b'\0'):
  if x==0:
   if i-start>=2:
    s=raw[start:i].decode('gbk',errors='ignore').strip()
    if any('\u4e00'<=c<='\u9fff' for c in s): print(hex(off+start),repr(s))
   start=i+1
