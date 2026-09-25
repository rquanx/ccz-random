"""兼容导入：规则实现已迁移到应用包。"""

from __future__ import annotations

import importlib
import sys


_implementation = importlib.import_module("ccz_randomizer.rules.config")
sys.modules[__name__] = _implementation

