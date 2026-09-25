from pathlib import Path
b=Path(r'E:\game\ccz\曹操传加强版V2.10.4c\曹操传加强版V2.10.4c\Imsg.e5').read_bytes()
for i in range(350,750):
 raw=b[i*200:(i+1)*200].split(b'\0',1)[0]
 s=raw.decode('gbk',errors='ignore').strip()
 if s: print(f'{i:03} {i-373:03} {s.replace(chr(13)," ").replace(chr(10)," ")}')
