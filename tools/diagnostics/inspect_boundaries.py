from PIL import Image
from collections import Counter
im=Image.open(r'D:\randResult\randResult_2.png').convert('RGB')
print(im.size)
for x in range(im.width):
 c=Counter(im.getpixel((x,y)) for y in range(im.height))
 common,n=c.most_common(1)[0]
 if n>2800 and (common[0]>180 or common[2]>100): print(x,common,n)
