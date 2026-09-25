from pathlib import Path
p=Path(r'E:\game\ccz\曹操传加强版V2.10.4c\曹操传加强版V2.10.4c\Imsg.e5'); b=p.read_bytes()
for term in ['固定减伤','远距攻击圆环','破坏攻击','攻击绝对命中','辅助攻击命中','自动提升防精','个人天赋','兵种技能']:
 pat=term.encode('gbk'); print(term,[hex(i) for i in range(len(b)) if b.startswith(pat,i)][:20])
