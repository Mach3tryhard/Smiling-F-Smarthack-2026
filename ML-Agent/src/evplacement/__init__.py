"""Synthetic EV charging-placement benchmark and decision support."""

import os
import sys
from pathlib import Path

# The generator lives in the sibling ``data-generation`` package. Add its
# ``src`` directory to the path so ``import evdata`` works in a source checkout
# without a second editable install.
_DATA_GENERATION_SRC = Path(__file__).resolve().parents[3] / "data-generation" / "src"
if _DATA_GENERATION_SRC.is_dir() and str(_DATA_GENERATION_SRC) not in sys.path:
    sys.path.insert(0, str(_DATA_GENERATION_SRC))

# The sandboxed Windows runtime has no ``wmic``; without this joblib prints a
# noisy warning while probing physical cores. The pipeline is single-process.
os.environ.setdefault("LOKY_MAX_CPU_COUNT", "1")

__version__ = "3.0.0"
