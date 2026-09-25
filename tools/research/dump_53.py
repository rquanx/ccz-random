from pathlib import Path
paths=[Path(r'E:\game\ccz\曹操传加强版V2.10.4c\曹操传加强版V2.10.4c\随即工具\1\SV001.E5S')]
paths += [Path(r'E:\game\ccz\曹操传加强版V2.10.4c\曹操传加强版V2.10.4c\SV')/f'SV{i:03}.E5S' for i in (2,3,15,19)]
for p in paths:
 b=p.read_bytes(); print('\n',p.name,len(b))
 for off in range(0x5300,0x5840,0x40):
  data=b[off:off+0x40]
  print(f'{off:04x}', ' '.join(f'{x:02x}' for x in data))
