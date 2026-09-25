"""兼容导入：随机流程已迁移到应用包。"""

from __future__ import annotations

import importlib
import sys


_implementation = importlib.import_module(
    "ccz_randomizer.workflow.randomization"
)
sys.modules[__name__] = _implementation

