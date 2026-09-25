"""兼容导入：规则编辑器已迁移到应用包。"""

from __future__ import annotations

import importlib
import sys


_implementation = importlib.import_module("ccz_randomizer.rules.editor")
sys.modules[__name__] = _implementation

