from pathlib import Path
import struct
from runtime_loader import install
install(Path.cwd().parent/'exe-analysis'/'tool.exe_extracted')
import models.CczModels as m
for fn in ['SV001.E5S','SV002.E5S','SV015.E5S']:
 p=Path(r'E:\game\ccz\曹操传加强版V2.10.4c\曹操传加强版V2.10.4c\随即工具\1')/fn if fn=='SV001.E5S' else Path(r'E:\game\ccz\曹操传加强版V2.10.4c\曹操传加强版V2.10.4c\SV')/fn
 b=p.read_bytes(); print('\n',fn)
 for j in range(7):
  vals=[]
  for k in range(6):
   off=0x6800+(j*6+k)*8
   a,c,d,e=struct.unpack_from('<4H',b,off)
   vals.append((a,c,d,e))
  print(j, vals)
  print('ids', [a for a,c,d,e in vals if a<len(m.CCZ_MODELS.skills)], [m.CCZ_MODELS.skills[a].name if a<len(m.CCZ_MODELS.skills) else str(a) for a,c,d,e in vals if a<len(m.CCZ_MODELS.skills)])
