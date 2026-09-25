from rapidocr_onnxruntime import RapidOCR
from pathlib import Path
import cv2,json,re
ocr=RapidOCR()
out={}
for page,start in [('equip-page-1.png',1),('equip-page-2.png',21)]:
 img=cv2.imread(page)
 for row in range(10):
  for col in range(5):
   num=start+row*5+col
   if num>70: continue
   x0=col*170;y0=row*66
   crop=img[y0:y0+66,x0:x0+170]
   crop=cv2.resize(crop,None,fx=2,fy=2,interpolation=cv2.INTER_CUBIC)
   res,_=ocr(crop)
   texts=[]
   for box,text,score in res or []:
    y=min(p[1] for p in box)
    texts.append((y,text,score))
   texts.sort()
   header='';effect=''
   for y,text,score in texts:
    if 'No' in text or re.search(r'\d+[：:]',text): header=text
    elif y>45 and text not in ('确定',): effect=(effect+' '+text).strip()
   out[num]={'header':header,'effect':effect,'raw':[(round(y),t,round(s,3)) for y,t,s in texts]}
Path('equip_slot001_ocr.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf8')
for k,v in out.items(): print(k,v['header'],'=>',v['effect'],v['raw'])
