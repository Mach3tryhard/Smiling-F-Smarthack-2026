"""Compatibility layer for the generator moved to ``../data-generation``.

The canonical implementation lives in the sibling ``data-generation`` package
(``evdata.generator``). This module re-exports it so the ML code, agent,
dashboard, CLI, and tests keep their existing imports.

``evplacement`` adds ``../data-generation/src`` to ``sys.path`` on import, so
the separate package does not need a second editable install in this monorepo.
"""

from __future__ import annotations

from evdata.generator import (
    SYNTHETIC_DIR,
    CityParams,
    SyntheticCity,
    build_benchmark,
    candidate_uplift,
    generate_batch,
    generate_city,
    make_params,
    simulate_usage,
    total_expected_usage,
)

from ..config import PROJECT_ROOT

# ML outputs remain inside ML-Agent; only the dataset moved to data-generation.
SYNTHETIC_OUTPUT_DIR = PROJECT_ROOT / "outputs" / "synthetic"

__all__ = [
    "PROJECT_ROOT",
    "SYNTHETIC_DIR",
    "SYNTHETIC_OUTPUT_DIR",
    "CityParams",
    "SyntheticCity",
    "build_benchmark",
    "candidate_uplift",
    "generate_batch",
    "generate_city",
    "make_params",
    "simulate_usage",
    "total_expected_usage",
]
