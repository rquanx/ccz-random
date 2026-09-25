"""兼容导入：运行时加载器已迁移到应用包。"""

from __future__ import annotations

import importlib
import sys


_implementation = importlib.import_module("ccz_randomizer.runtime.loader")
sys.modules[__name__] = _implementation

