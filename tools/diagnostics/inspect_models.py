from pathlib import Path
import sys
sys.path.insert(0, str(Path.cwd()))
from runtime_loader import install
root=Path.cwd().parent/'exe-analysis'/'tool.exe_extracted'
install(root)
import models.CczModels as m
import models.CczEquip as e
import utils.CvUtils as cv
print('CczModels attrs')
for n in sorted(dir(m)):
    if not n.startswith('__'):
        v=getattr(m,n)
        print(n, type(v), repr(v)[:500])
print('CczEquip attrs')
for n in sorted(dir(e)):
    if not n.startswith('__'):
        v=getattr(e,n)
        print(n, type(v), repr(v)[:300])
