"""Synthetic EV charging-placement benchmark and decision support."""

import os

# The sandboxed Windows runtime has no ``wmic``; without this joblib prints a
# noisy warning while probing physical cores. The pipeline is single-process.
os.environ.setdefault("LOKY_MAX_CPU_COUNT", "1")

__version__ = "3.0.0"
