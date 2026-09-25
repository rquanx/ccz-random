from pathlib import Path
import struct
from runtime_loader import install
install(Path.cwd().parent/'exe-analysis'/'tool.exe_extracted')
import models.CczModels as m
p=Path(r'E:\game\ccz\曹操传加强版V2.10.4c\曹操传加强版V2.10.4c\随即工具\1\SV001.E5S'); b=p.read_bytes()
for idx in [0x57,0x10,0x1d,0x0c,0x3e,0x0f,0x28,0x4b,0x13]:
 vals=struct.unpack_from('<4H',b,0x6800+idx*8)
 names=[m.CCZ_MODELS.skills[x].name if x<len(m.CCZ_MODELS.skills) else str(x) for x in vals[:3]]
 print(hex(idx),vals,names)
