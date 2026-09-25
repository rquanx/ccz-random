from rapidocr_onnxruntime import RapidOCR
from pathlib import Path
import cv2,json
ocr=RapidOCR()
for p in sorted(Path('.').glob('ref_*.png')):
 img=cv2.imread(str(p))
 crop=img[:,334:740]
 res,_=ocr(crop)
 lines=[]
 for box,text,score in (res or []):
  x=min(q[0] for q in box)+334;y=min(q[1] for q in box)
  lines.append({'x':round(x,1),'y':round(y,1),'text':text,'score':round(score,3)})
 Path(p.stem+'_equip_ocr.json').write_text(json.dumps(sorted(lines,key=lambda z:(z['x'],z['y'])),ensure_ascii=False,indent=2),encoding='utf-8')
 print(p.name,len(lines),[(z['text'],z['score']) for z in lines[:8]])
