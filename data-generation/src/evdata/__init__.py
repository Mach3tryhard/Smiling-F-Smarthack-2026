"""Synthetic graph-city generator for EV charging placement.

This package owns the data-generating process: urban graphs, observable
features, latent demand, existing-station siting, Huff usage, and the
counterfactual labels used by the ML benchmark. It has no dependency on the
``ML-Agent`` package, so the dataset can be generated independently.
"""

from __future__ import annotations

from .generator import (
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

__version__ = "1.0.0"

__all__ = [
    "SYNTHETIC_DIR",
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
