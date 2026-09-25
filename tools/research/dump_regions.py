from pathlib import Path
import struct
saves=Path(r'E:\game\ccz\曹操传加强版V2.10.4c\曹操传加强版V2.10.4c\随即工具\1')
for p in sorted(saves.glob('SV*.E5S')):
 b=p.read_bytes()
 print('\n',p.name,len(b))
 for base in [0x6800,0x6840,0x6880,0x68c0,0x6900,0x6a00,0x6b00,0x6c00,0x6d00,0x6e00,0x6f00]:
  chunk=b[base:base+64]
  vals=struct.unpack('<32H',chunk)
  print(f'{base:04x}:',' '.join(f'{v:04x}' for v in vals))
