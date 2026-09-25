from pathlib import Path
from runtime_loader import install
install(Path.cwd().parent/'exe-analysis'/'tool.exe_extracted')
from window.CczWindow import CczEquipWindow
import dis
for fn in ['flipDownPage','flipUpPage','getEquipMap']:
 print('\n',fn);dis.dis(getattr(CczEquipWindow,fn))
