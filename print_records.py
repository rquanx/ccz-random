from pathlib import Path
import struct
p=Path(r'E:\game\ccz\曹操传加强版V2.10.4c\曹操传加强版V2.10.4c\随即工具\1\SV001.E5S')
b=p.read_bytes()
print('block4')
for i in range(45): print(i, b[0x54d8+i*4:0x54dc+i*4].hex(' '))
print('block8')
for i in range(27): print(i,b[0x558c+i*8:0x5594+i*8].hex(' '))
