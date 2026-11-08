# data-generation

**Synthetic graph-city generator with known ground truth for EV charging placement.**

This folder owns the data-generating process and the generated benchmark dataset. It is deliberately separate from the ML code in [`../ML-Agent/`](../ML-Agent/): the generator can be run, tested, and versioned on its own, while the ML package imports it for training and evaluation.

## Layout

```text
data-generation/
├── pyproject.toml              # installable "evdata" package
├── src/evdata/
│   ├── generator.py            # city graph, demand, stations, Huff usage, counterfactuals
│   └── cli.py                  # `evdata build`
└── data/synthetic/
    ├── cities.joblib           # 400 SyntheticCity objects (~261 MB, Git LFS)
    └── benchmark.json          # split counts, seeds, generator version
```

## Quick start

Standalone:

```powershell
cd data-generation
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m evdata build
```

Or reuse the ML-Agent environment (it already has the dependencies, and ML-Agent adds this package's `src/` to its import path):

```powershell
cd ML-Agent
.\.venv\Scripts\python.exe -m evplacement build
```

Both commands write the dataset to `data-generation/data/synthetic/` by default. `evdata build --out <dir>` writes somewhere else.

## What is generated

Each seed produces one city with:

- **700–1,800 nodes** (up to 2,400 for the OOD batch), built from 2–8 urban centres, radial corridors, and sparse background; k-NN graph with `k = 6`, disconnected components joined.
- **24 observable features**: population, activity, income, EV adoption, centrality, road/transit/highway access, parking, POI density, distance to centre, graph degree/closeness, land-use shares, competition measures, local neighbourhood demand, planned capacity, city size and station rate.
- **Hidden latent demand** from a polycentric, zone-aware formula with spatial shocks and lognormal noise, normalized to mean 100 per city. It is never used as a model feature.
- **Existing stations**: `max(5, round(n_nodes × station_rate))` sampled without replacement with probability proportional to `demand^1.15 × (0.35 + road) × (0.45 + parking) × (0.5 + business)`.
- **Station capacity**: `clip(lognormal(0, 0.30), 0.5, 2.6)`.
- **Observed usage**: Huff competition with a spatial kernel, `usage_i = demand_i · capacity_i / (capacity_i + competition_i) · lognormal(0, noise)`.
- **Ground-truth counterfactuals**: `uplift_i = U(S ∪ {i}) − U(S)` for every candidate node, computed noise-free, plus the total utility of any portfolio.

The full methodology — including why the demand and Huff formulas were chosen, the split protocol, and how the ML models consume the labels — is in [`../ML-Agent/README.md`](../ML-Agent/README.md).

## Benchmark composition

| Split | Cities | Seed base | Shift |
|---|---:|---:|---|
| train | 300 | 202,600 | no |
| validation | 40 | 203,600 | no |
| test | 40 | 204,600 | no |
| test_shift (OOD) | 20 | 205,600 | yes |

Total: **400 cities, 501,812 nodes, 36,809 stations**. OOD cities vary node count, station rate, EV adoption, and usage noise; the structural equations stay the same.

## Output schema

`cities.joblib` is a dict keyed by `city_id` (`{split}_{seed}`). Each value is a `SyntheticCity` dataclass with:

| Field | Content |
|---|---|
| `city_id`, `seed`, `split` | identity and split |
| `nodes` | DataFrame with coordinates, 24 features, `latent_demand`, `is_station`, `station_capacity`, `observed_usage` |
| `edges` | `(E, 2)` graph edge array |
| `centers` | `(n_centers, 2)` urban centres |
| `params` | `n_nodes`, `n_centers`, `station_rate`, `ev_base`, `noise`, `lambda_norm`, `shift` |
| `station_nodes`, `station_capacity`, `station_usage` | existing stations |
| `latent_demand` | hidden demand per node |
| `features` | `nodes` plus engineered competition/context columns |

`observed_usage` is `NaN` for candidate nodes. `latent_demand` and `observed_usage` are ground truth and are excluded from model features by the ML package.

## Reproducibility

- `generate_city(seed, ...)` is deterministic: the same seed produces the same graph, demand, stations, and usage.
- `build_benchmark(n_train=300, n_val=40, n_test=40, base_seed=202600)` generates the four batches in fixed order.
- The ML tests include a same-seed reproducibility check and a vectorized-vs-direct counterfactual check.

## Integration with ML-Agent

`ML-Agent/src/evplacement/synthetic/generator.py` is now a compatibility layer. It re-exports the generator from `evdata` and keeps the `SYNTHETIC_OUTPUT_DIR` constant used by the ML outputs. The ML package adds `../data-generation/src` to `sys.path` automatically, so no second install is needed when running from this monorepo.

From `ML-Agent/`:

```powershell
.\.venv\Scripts\python.exe -m evplacement build
.\.venv\Scripts\python.exe -m evplacement train --k 8
.\.venv\Scripts\python.exe -m evplacement agent --k 8
```
