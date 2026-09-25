"""兼容入口：实际实现位于 :mod:`ccz_randomizer.app`。"""

from __future__ import annotations

import sys

from ccz_randomizer import app as _implementation


if __name__ == "__main__":
    raise SystemExit(_implementation.run_cli())
else:
    sys.modules[__name__] = _implementation
