from rapidocr_onnxruntime import RapidOCR
from pathlib import Path
import cv2,json
ocr=RapidOCR()
for name in ['equip-page-1.png','equip-page-2.png']:
 img=cv2.imread(name);res,_=ocr(img)
 lines=[]
 for box,text,score in res or []:
  x=min(q[0] for q in box);y=min(q[1] for q in box)
  lines.append({'x':round(x,1),'y':round(y,1),'text':text,'score':round(score,3)})
 Path(name.replace('.png','-ocr.json')).write_text(json.dumps(sorted(lines,key=lambda z:(z['y'],z['x'])),ensure_ascii=False,indent=2),encoding='utf8')
 print(name,len(lines))
