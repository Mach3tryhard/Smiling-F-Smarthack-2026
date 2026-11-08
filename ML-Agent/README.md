# EV Charge Synthetic

**A ground-truth benchmark and machine-learning model for EV charging-station placement.**

This repository generates a synthetic population of graph cities, trains two supervised models on them, and evaluates placement decisions against a simulator that knows the true counterfactual. It is built to answer one question honestly:

> If we install chargers at the nodes the model chooses, how much of the usage created by an oracle that knows the ground truth do we actually capture?

The short answer on the held-out test cities: **85.5% of the oracle, with 14.5% regret**, against 5–11% for simple baselines. The longer answer, including why this is a simulator and not a real demand forecast, is in this document.

---

## Contents

1. [At a glance](#1-at-a-glance)
2. [The decision problem](#2-the-decision-problem)
3. [Why synthetic ground truth](#3-why-synthetic-ground-truth)
4. [How the world is generated](#4-how-the-world-is-generated)
5. [The two learning tasks](#5-the-two-learning-tasks)
6. [Model architecture and training](#6-model-architecture-and-training)
7. [Evaluation methodology](#7-evaluation-methodology)
8. [Results](#8-results)
9. [The decision layer (agent)](#9-the-decision-layer-agent)
10. [Data and artifacts](#10-data-and-artifacts)
11. [Design decisions and trade-offs](#11-design-decisions-and-trade-offs)
12. [Reproducing the benchmark](#12-reproducing-the-benchmark)
13. [Limitations and the path to real data](#13-limitations-and-the-path-to-real-data)
14. [Glossary](#14-glossary)

---

## 1. At a glance

| Element | Value |
|---|---:|
| Synthetic cities | **400** |
| Train / validation / test / OOD cities | **300 / 40 / 40 / 20** |
| Urban nodes | **501,812** |
| Existing charging stations | **36,809** |
| Node range | 700–1,800 (up to 2,400 OOD) |
| Usage model | 24 features → 3-seed MLP ensemble, `log1p(usage)` target |
| Placement model | same architecture, `log1p(counterfactual uplift)` target |
| Placement budget | K = 8 stations per city |
| Test usage R² (log) | **0.871** |
| Test usage Spearman | **0.931** |
| Test uplift R² (log) | **0.735** |
| Test uplift Spearman | **0.801** |
| Placement vs greedy oracle | **85.5%** |
| Placement regret | **14.5%** |
| OOD placement vs oracle | **88.4%** |
| Agent actions / human review | **320 / 14** |

**The honest claim.** This is a complete, measurable decision benchmark: a simulator, two learned models, a placement optimizer, and an error metric defined against known counterfactual usage. It is **not** a forecast of real Romanian charging demand. Section 13 explains exactly what would be required to make that step.

**Repository scope.** The earlier real-data Bucharest/OSM prototype is not part of this deliverable. This repository is self-contained around the synthetic benchmark; old out-of-core pyrosm scratch directories and caches have been removed. The generator and dataset live in [`../data-generation/`](../data-generation/); the models, evaluation, and agent are in `src/evplacement/synthetic/`.

**Interactive UI.** [`../frontend/`](../frontend/) contains the standalone Charge Quest UI: a white-canvas node map, ranked tower recommendations, click-through confidence/CSV details, a deployment planner, and a model-results view. Run it with `python ../frontend/server.py` from this folder (or see the [frontend README](../frontend/README.md)).

---

## 2. The decision problem

A city is a graph of candidate locations. Some nodes already have a charging station with a known capacity. A planner has a budget of K new stations and must choose where to put them.

Formally:

```text
Given:   city graph G = (V, E)
         existing stations S with capacities c
         candidate set C = V \ S
         budget K
Choose:  A ⊂ C, |A| = K
Maximize: U(S ∪ A) = total expected charging sessions/day
```

The objective is **system-wide usage**, not the usage of the new stations alone. Adding a station near an existing one steals part of its demand; that cannibalization must be subtracted from the apparent gain. This is the key reason a naive "rank nodes by predicted demand" approach is not enough.

The model deliberately ignores several real constraints that a production planner would need: installation cost differences, grid connection capacity, land ownership, permitting, equity targets, and time-of-day queueing. They are listed again in Section 13.

---

## 3. Why synthetic ground truth

Supervised placement needs labels. Real charging data provides two things:

1. where stations are;
2. how much those stations were used.

It does **not** provide the counterfactual: how much a station at a *different* node would have been used, or how much total system usage would change if a new station were added. It also suffers from strong selection bias — stations were built where operators already expected demand, so the observed sample is not random.

Without counterfactuals there is no honest way to compute placement regret. A model can be judged on "does it rank existing stations well?" but not on "would its recommended new sites actually create usage?".

The simulator solves the label problem by construction:

- it draws a hidden latent demand for every node;
- it draws a realistic set of existing stations;
- it generates station usage with a spatial competition model;
- it can simulate the system with **any** station portfolio, including portfolios that never existed.

That yields two ground-truth quantities a real dataset never has:

| Quantity | Symbol | Used for |
|---|---|---|
| Counterfactual incremental usage of adding one station at any candidate | `uplift_i = U(S ∪ {i}) − U(S)` | training target and candidate diagnostics |
| System-wide incremental usage of any station portfolio | `U(S ∪ A) − U(S)` | greedy oracle and placement regret |

**Design principle: the simulator and the model are kept strictly separate.** The model sees only features an operator could observe before building. Latent demand, realized station usage of other stations, and the `is_station` flag are never model inputs. Ground truth is used for labels during training and for scoring during evaluation — not as a feature.

---

## 4. How the world is generated

All generation is deterministic given a seed. The code is in [`../data-generation/src/evdata/generator.py`](../data-generation/src/evdata/generator.py).

### 4.1 Urban graph

Each city is a 2-D spatial graph in normalized coordinates `[0, 1]²`:

1. **2–8 urban centres** are sampled uniformly.
2. Nodes are assigned to a centre and jittered with Gaussian noise (`σ = 0.085`).
3. **~24% of nodes** are moved onto a radial corridor from the first centre, with small angular noise.
4. **~16% of nodes** are placed as low-density background anywhere in the unit square.
5. Coordinates are clipped to `[0.01, 0.99]`.
6. A **k-nearest-neighbour graph** (`k = 6`) is built and disconnected components are joined by their closest pair.

This produces polycentric cities with corridors and sparse outskirts, rather than a single Gaussian blob. The graph supplies `degree` and `closeness` (NetworkX), which become model features.

### 4.2 Observable features

Every node has 24 model features. They are all things a planner could plausibly know before placing a charger:

| Group | Features |
|---|---|
| Demand proxies | `population`, `activity`, `income`, `ev_adoption`, `poi_density` |
| Accessibility | `centrality`, `road_capacity`, `transit_access`, `highway_access`, `parking` |
| Geometry / graph | `dist_center`, `degree`, `closeness` |
| Land use | `zone_business`, `zone_residential`, `zone_industrial` |
| Competition | `competing_capacity`, `n_stations_1km`, `nearest_station_dist` |
| Local context | `local_population`, `local_activity` |
| Capacity / city context | `planned_capacity`, `city_nodes`, `city_station_rate` |

Notes on definitions that matter for interpretation:

- **`n_stations_1km` is a slight misnomer.** The radius is `0.12` in normalized city coordinates, not a real kilometre. It means "stations in the immediate neighbourhood". The name is kept for backward compatibility with the trained artifacts.
- **`competing_capacity`** is the kernel-weighted capacity of existing stations excluding the node itself:
  `Σ_{j ∈ S, j ≠ i} capacity_j · exp(−distance_ij / λ)`.
- **`nearest_station_dist`** excludes the node itself for existing stations, so it measures distance to the nearest *other* station.
- **`local_population` / `local_activity`** are Gaussian-kernel neighbourhood sums with radius `0.20`.
- **`planned_capacity`** is the station's own capacity for existing stations, and `1.0` for candidates. This lets one model handle both regimes and encodes the one-connector assumption used by the optimizer.
- **`city_nodes`** and **`city_station_rate`** give the model city-level context (size and station density).

### 4.3 Hidden latent demand

Latent demand is the simulator's ground truth. It is **never** a model feature.

```text
demand_i = 120
         × (0.25 + population)^0.90
         × (0.30 + activity)^0.70
         × (0.35 + ev_adoption)^0.80
         × (0.40 + centrality)^0.50
         × (0.45 + road_capacity)^0.30
         × (0.55 + 0.9·zone_business + 0.5·zone_residential + 0.3·zone_industrial)
         × (0.55 + 0.45·transit_access)
         × (0.60 + 0.40·highway_access)
         × (1 + 0.18·normalized_spatial_shock)
         × lognormal(0, 0.14)
```

Then `demand` is rescaled so that each city has mean 100. Per-city normalization keeps cities comparable in scale while preserving within-city heterogeneity.

The **spatial shocks** are 2–8 Gaussian bumps at random locations, summed and min-max normalized before the `0.18` multiplier. They create local demand hotspots that are only partially visible through the observable proxies. That is intentional: it prevents the model from recovering latent demand exactly and makes the benchmark non-trivial.

### 4.4 Existing stations

The number of stations is:

```text
n_stations = max(5, round(n_nodes × station_rate))
```

Station nodes are sampled **without replacement** with probability proportional to:

```text
latent_demand^1.15 × (0.35 + road_capacity)
                   × (0.45 + parking)
                   × (0.50 + zone_business)
```

Each station gets a capacity:

```text
capacity ~ clip(lognormal(0, 0.30), 0.5, 2.6)
```

This siting process is deliberately biased toward high-demand, accessible, commercial locations — the same selection bias real operators exhibit. The model must therefore learn usage **conditional on competition**, not merely "high demand means high usage".

### 4.5 Usage model (Huff competition)

Station usage is generated by a spatial Huff-style market-share model:

```text
kernel_ij     = exp(−distance_ij / λ)        (diagonal set to 1)
competition_i = Σ_{j ≠ i} capacity_j · kernel_ij
share_i       = capacity_i / (capacity_i + competition_i)
usage_i       = demand_i · share_i · lognormal(0, noise)
usage_i       = max(usage_i, 0.01)
```

- `λ` (the competition length scale) is drawn per city from `U(0.075, 0.18)`.
- `noise` is drawn per city from `U(0.08, 0.24)` for in-distribution cities.
- The diagonal term means a station always keeps a share of its own demand; a station never gets zero usage because it exists.

The resulting behaviour is intuitive: a station in a dense area with many nearby high-capacity stations receives a smaller share than an isolated station with the same latent demand. This is the cannibalization signal the placement model must respect.

**Important:** noise is applied only to `observed_usage` of existing stations. The `total_expected_usage` function used for uplift labels and the oracle is noise-free. Uplift is therefore an *expected* system quantity, not a noisy observation. This is a deliberate modelling decision, discussed in Section 5.

### 4.6 What the model sees vs what the simulator knows

| Available to the model | Hidden from the model |
|---|---|
| 24 observable features | `latent_demand` |
| Station existence through competition features | `observed_usage` of other stations |
| City size and station rate | `is_station` as a feature |
| `planned_capacity` (own capacity or 1.0) | The simulator's noise draw |
| | The true uplift of any candidate |

A unit test asserts that `latent_demand`, `observed_usage`, and `is_station` are not in `FEATURES`.

### 4.7 Splits, seeds, and OOD shift

`build_benchmark()` generates four independent batches:

| Split | Cities | Seed base | Shift? |
|---|---:|---:|---|
| train | 300 | 202,600 | no |
| validation | 40 | 203,600 | no |
| test | 40 | 204,600 | no |
| test_shift (OOD) | 20 | 205,600 | yes |

City IDs are `{split}_{seed}`, e.g. `test_204600`. The generator version stored in `benchmark.json` is `1.0`.

The OOD batch changes the *parameters* of the data-generating process, not its equations:

| Parameter | In-distribution | OOD |
|---|---|---|
| Nodes per city | 700–1,800 | 700–2,400 |
| Station rate | 0.035–0.105 | 0.018–0.170 |
| EV adoption offset (`ev_base`) | −0.2–1.3 | −0.9–1.9 |
| Usage noise | 0.08–0.24 | 0.18–0.40 |
| Competition length `λ` | 0.075–0.18 | 0.075–0.18 |

This is a **parametric shift test**, not a geographic one. It checks whether the model survives cities that are denser/sparser, more/less EV-heavy, and noisier — but still generated by the same family. It does not prove transfer to Bucharest.

### 4.8 Reproducibility

- All randomness comes from seeded `numpy.random.Generator` instances.
- The same seed always produces the same city graph, demand, stations, and usage. A unit test checks this.
- Training seeds are fixed (`42`, `43`, `44` for the three MLPs; `42` for HGB).
- Full bit-for-bit determinism across different GPUs/CUDA versions is not guaranteed by PyTorch; the saved artifacts and metrics are the reference.

---

## 5. The two learning tasks

The project trains two separate supervised models with the *same* architecture class but different targets. This is the most important design decision in the repository.

| | Usage model | Uplift model |
|---|---|---|
| Question | How many sessions/day will an existing station get? | How much total system usage does adding a station at this candidate create? |
| Unit of a row | existing station | candidate node with no station |
| Target | `log1p(observed_usage)` | `log1p(max(0, U(S ∪ {i}) − U(S)))` |
| Label source | simulated noisy usage | noise-free counterfactual simulator |
| Train rows | 27,324 stations | 350,187 candidates |
| Validation rows | 3,507 stations | 45,330 candidates |
| Test rows | 3,333 stations | 43,776 candidates |
| Used for | reporting expected sessions, review threshold | ranking candidates for placement |

### 5.1 Why `log1p`?

Usage is positive and heavily right-skewed: most stations do a few sessions/day, a few do dozens. Training on the raw scale would let the tail dominate the loss and produce unstable gradients. `log1p` compresses the tail, stabilizes variance, and makes an absolute error in log space approximately a relative error in the original space:

```text
Δlog ≈ Δusage / usage
```

Predictions are converted back with `expm1` and clipped at zero. All regression metrics are reported both in log space (primary) and in sessions/day (interpretable).

### 5.2 Why a separate uplift model?

A natural shortcut is to predict usage for every candidate and pick the top K. That is wrong for two reasons:

1. **A candidate has no usage label.** The usage model is trained on existing stations with their own capacities. A candidate's "usage if built" is a counterfactual, not the same distribution.
2. **The decision objective is incremental, not individual.** Adding a station changes the usage of nearby stations. The uplift target subtracts that cannibalization by construction:

```text
uplift_i = U(S ∪ {i}) − U(S)
```

where `U` is the noise-free total expected usage of the whole station portfolio. `uplift_i` is exactly the marginal value the planner cares about. A station with high standalone usage but severe cannibalization gets a low label.

The two models therefore answer different questions and are not interchangeable. The usage model remains useful for explaining the expected absolute value of a site and for the "below 10 sessions/day" review rule. The uplift model is what ranks sites.

### 5.3 Why not end-to-end optimization?

An end-to-end approach could try to differentiate through the simulator and learn a placement policy directly. We deliberately did not do that:

- the two-stage design has explicit, debuggable targets;
- each model can be validated independently;
- the placement optimizer is a transparent greedy procedure with one tunable penalty;
- counterfactual labels are cheap to generate offline, so supervised learning is the natural fit.

The cost is that the placement policy is not jointly optimized with the predictor. Section 11 lists this as a known limitation.

### 5.4 Leakage controls

The following are enforced:

- **City-level splits.** No node from a test city appears in training. Random node splits would leak spatial context and overstate performance.
- **No ground-truth features.** `latent_demand`, `observed_usage`, and `is_station` are excluded and unit-tested.
- **No target-derived features.** Competition features are computed from *existing* stations only; they do not include the candidate being scored or the K stations selected later.
- **Tuning on validation only.** The MLP/HGB blend weight and the cannibalization `alpha` are chosen on validation cities. Test cities are touched once, for reporting.
- **No city embeddings.** `city_id` and `city_seed` are not features; the model must generalize from observable city context (`city_nodes`, `city_station_rate`).

One subtlety: the constant baseline used in the test metrics is the **mean of the evaluated split**, not the training mean. It is therefore a generous baseline (it "knows" the test mean). The model still beats it by a wide margin, but the baseline is intentionally naive in a different way: it is an arithmetic mean on the raw scale, evaluated in log space, so its log-space R² is negative. It is a sanity check, not a tuned competitor.

---

## 6. Model architecture and training

Both targets use the same `UsageEnsemble` class (`src/evplacement/synthetic/model.py`).

### 6.1 The MLP

```text
input (24)
  → Linear(24, 256) → GELU → Dropout(0.10)
  → Linear(256, 128) → GELU → Dropout(0.08)
  → Linear(128, 64) → GELU
  → Linear(64, 1)
```

| Choice | Value | Reason |
|---|---|---|
| Hidden widths | 256 → 128 → 64 | A capacity/speed compromise for 27k–350k rows; enough nonlinearity without a huge parameter count |
| Activation | GELU | Smooth, standard for tabular MLPs, and well-behaved with the chosen optimizer |
| Dropout | 0.10, 0.08 | Mild regularization; the dataset is large and noisy |
| Loss | `HuberLoss(delta=0.5)` on log target | Limits the influence of the remaining tail and label noise compared with squared error |
| Optimizer | AdamW, `lr=1e-3`, `weight_decay=1e-4` | Stable default; decoupled weight decay |
| Schedule | Cosine annealing, `T_max=70` | Smooth decay over the epoch budget |
| Batch size | 2,048 | GPU-efficient at this row count |
| Max epochs | 70 | With early stopping |
| Early stopping | patience 10 on validation MAE (log) | Restores the best epoch's weights |
| Seeds | 3 (`42`, `43`, `44`) | Variance reduction and ensemble uncertainty |
| Preprocessing | `StandardScaler` fit on train | Features have different scales (`degree`, `competing_capacity`, etc.) |

The three MLPs are trained independently with different seeds. Their average is the MLP prediction. Their disagreement (standard deviation after `expm1`) is used as an uncertainty signal in the decision layer.

### 6.2 The gradient-boosted expert

A `HistGradientBoostingRegressor` is trained on the same scaled feature matrix:

| Parameter | Value |
|---|---|
| Loss | squared error |
| Learning rate | 0.05 |
| Max iterations | 300 |
| Max leaf nodes | 31 |
| Min samples per leaf | 20 |
| L2 regularization | 2.0 |
| Max features | 0.9 |
| Early stopping | off |
| Random state | 42 |

It provides a different inductive bias: axis-aligned splits and interactions, no scaling requirements, and robustness on small or noisy slices. It is trained after the MLPs, on the same training split.

### 6.3 Blending: validation chooses the expert

The final prediction is:

```text
prediction = w · MLP_mean + (1 − w) · HGB
```

`w` is chosen from `{0.0, 0.25, 0.5, 0.75, 1.0}` by validation MAE in log space.

**The selected weight was `1.0` for both models.** In other words, validation preferred the 3-seed MLP average and gave the HGB zero weight. The HGB is trained and saved as a robustness artifact, but it does not contribute to the reported predictions. This is reported honestly rather than hidden: the ensemble search was real, and the data chose the MLP.

Implication: the reported uncertainty is **MLP seed disagreement only**, not MLP-vs-HGB disagreement. A future version could force a non-zero HGB weight or use a stacked meta-learner, but that would be a different model and would need its own validation.

### 6.4 GPU training, CPU inference

Training runs on CUDA when available:

| Stage | Device | Time (reference run) |
|---|---|---:|
| Usage model (3 MLPs + HGB) | CUDA (RTX 4070 Laptop) | 17.6 s |
| Uplift model (3 MLPs + HGB) | CUDA (RTX 4070 Laptop) | 67.7 s |
| Full train + evaluation | CUDA | 247.6 s |

After training, the MLPs are moved to CPU and saved. `training_device` is kept in the metrics for reporting, while inference runs on any machine without a GPU. This matters for judges and for deployment: the artifact is portable.

A CPU-only run works but is slower, especially for the 350k-row uplift model. The code falls back to CPU automatically when CUDA is unavailable.

### 6.5 What the model does *not* use

- No graph neural network. Graph structure enters through `degree`, `closeness`, and competition features. A GNN could exploit the graph directly; it was not necessary to beat the baselines and would complicate CPU inference.
- No sequence model or temporal features. Usage is treated as a static daily rate.
- No explicit revenue or price model. The objective is sessions/day, a usage proxy.
- No quantile regression. Uncertainty comes from seed disagreement, not calibrated predictive intervals.

---

## 7. Evaluation methodology

### 7.1 Held-out cities

The test set contains 40 cities generated with seeds never used in training or validation. Every station in those cities is a test row. Every non-station node is a test candidate. The OOD set contains 20 additional cities with shifted parameters.

This is stricter than random row splits and is the only split that answers the real question: *does the model generalize to a city it has never seen?*

### 7.2 Usage metrics

For target `y` and prediction `ŷ`:

```text
MAE_log   = mean |log1p(y) − log1p(ŷ)|
RMSE_log  = sqrt(mean (log1p(y) − log1p(ŷ))²)
MAE_usage = mean |y − ŷ|                  (sessions/day)
R²_log    = 1 − SS_res(log) / SS_tot(log)
Spearman  = rank correlation between y and ŷ
```

Spearman is reported because placement is a ranking problem: the absolute calibration matters less than getting the order right. R² is computed in log space, matching the training target.

### 7.3 Uplift metrics

The same metrics are computed on candidate nodes with `y = true_uplift` and `ŷ = predicted_uplift`. The test set has 43,776 candidates. This measures whether the model can rank counterfactual gains, which is the quantity the optimizer consumes.

### 7.4 Placement protocol

For each test city:

1. **Candidate set** = all nodes without an existing station.
2. **Predict** uplift for every candidate with the uplift model.
3. **Model greedy selection** with budget K = 8:
   ```text
   score_i = predicted_uplift_i / (1 + alpha · Σ_{j ∈ selected} exp(−distance_ij / λ_city))
   ```
   The penalty discourages placing the next station next to one already selected. `λ_city` is the city's competition length scale from the generator. `alpha` is a single scalar tuned on validation.
4. **Oracle greedy selection** on the true simulator: at each step, add the candidate that maximizes the true total system usage. This is the reference.
5. **Compute ratios**:
   ```text
   utility_ratio = (U(S ∪ A_model) − U(S)) / (U(S ∪ A_oracle) − U(S))
   regret        = max(0, 1 − utility_ratio)
   ```
6. **Also compute**: oracle overlap (fraction of selected nodes shared with the oracle), Spearman between predicted and true candidate uplift, and the same ratio for four baselines.

The oracle is **greedy**, not exhaustive. Selecting the optimal 8 of ~1,000 candidates is combinatorial; greedy is a strong, transparent reference and the standard practical baseline. A model could in principle beat greedy on a given city; none did in this test set (max ratio 0.988).

### 7.5 The cannibalization penalty and `alpha`

The model predicts each candidate's uplift independently, assuming the current station set. If we simply pick the top K, they tend to cluster in the same hotspot and cannibalize each other. The penalty approximates the simulator's competition kernel without access to ground truth.

`alpha` is tuned on validation cities from `{0, 0.25, 0.5, 1.0, 2.0}`:

| alpha | Mean utility ratio (validation) |
|---:|---:|
| 0.00 | 0.665 |
| 0.25 | 0.787 |
| 0.50 | 0.829 |
| **1.00** | **0.852** |
| 2.00 | 0.849 |

`alpha = 1.0` was selected. This is one of the largest single gains in the pipeline: going from no penalty to `alpha = 1.0` raises captured oracle utility from ~67% to ~85%. It confirms that cannibalization is not a cosmetic detail; it is the core of the placement problem.

The penalty uses the same exponential form as the generator's Huff kernel. That is a modelling choice: it encodes the assumption that competition decays with distance at a similar rate. On real data, `alpha` and the kernel shape would need to be calibrated.

### 7.6 Baselines

| Baseline | Rule | Notes |
|---|---|---|
| Random | 3 random draws of K candidates, averaged | Lower bound |
| Population | top K by `population` | "Build where people are" |
| Activity | top K by `activity` | "Build where activity is" |
| Hand index | weighted sum: `0.32·population + 0.20·activity + 0.14·ev_adoption + 0.12·centrality + 0.10·transit_access + 0.06·road_capacity + 0.06·parking` | A plausible expert heuristic |

The non-random baselines select the top K by score **without** a sequential cannibalization penalty. That makes them weaker than a human planner who would space stations out, and it is a caveat when comparing. The comparison is still useful: even a strong hand index captures only ~7.5% of oracle utility, while the learned model + optimizer captures ~85%.

### 7.7 Feature importance

Permutation importance on the test candidates, using the uplift model and true uplift labels:

```text
importance_f = MAE_log(shuffled feature f) − MAE_log(original)
```

Two repeats, averaged. This is model-agnostic and does not require SHAP. `planned_capacity` has zero importance because it is constant (`1.0`) for all candidates; that is expected and is a useful sanity check.

### 7.8 Error analysis

Beyond aggregate metrics, the pipeline reports:

- predicted vs actual usage scatter (`validation.png`);
- per-city placement regret;
- usage by quintile, to expose calibration bias;
- the weakest cities, with node and station counts;
- per-feature permutation importance.

The most important systematic error is **top-tail compression**, discussed in Section 8.6.

---

## 8. Results

All numbers below are from the saved artifacts (`outputs/synthetic/metrics.json`, `placement_results.csv`, `feature_importance.csv`) and are reproducible from the commands in Section 12.

### 8.1 Usage model on 40 unseen cities

| Metric | Model | Naive constant baseline |
|---|---:|---:|
| MAE log | **0.166** | 0.502 |
| RMSE log | **0.214** | 0.622 |
| MAE sessions/day | **2.12** | 5.70 |
| RMSE sessions/day | **3.53** | 7.81 |
| R² (log) | **0.871** | −0.089 |
| Spearman | **0.931** | — |
| n stations | 3,333 | 3,333 |

Validation (40 cities, used for tuning) was slightly better: MAE log 0.158, R² 0.901, Spearman 0.949. That gap is small and in the expected direction.

**Interpretation.** The model ranks stations very well (Spearman 0.93) and explains most of the log-variance. The raw MAE of 2.12 sessions/day is modest relative to a mean usage of 11.0. Absolute values should still be treated as estimates, not revenue forecasts.

### 8.2 Uplift model on 43,776 test candidates

| Metric | Model | Naive constant baseline |
|---|---:|---:|
| MAE log | **0.352** | 1.015 |
| RMSE log | **0.512** | 1.141 |
| MAE uplift (sessions/day) | **1.35** | 3.84 |
| R² (log) | **0.735** | −0.314 |
| Spearman | **0.801** | — |

Validation: MAE log 0.300, R² 0.769, Spearman 0.798.

**Interpretation.** Uplift is harder than usage. The target is a difference of two simulated totals, so it is smaller, noisier in relative terms, and depends on cannibalization. A Spearman of 0.80 is enough for the greedy optimizer to capture most of the oracle's utility, which is the result that matters.

### 8.3 Placement: the central metric

K = 8, 40 test cities, `alpha = 1.0`:

| Strategy | Share of oracle's incremental utility |
|---|---:|
| **Model + cannibalization-aware greedy** | **85.5%** |
| Random | 8.7% |
| Population | 11.3% |
| Hand index | 7.5% |
| Activity | 5.2% |

- Mean regret: **14.5%**
- Mean oracle overlap: **41.3%**
- Mean Spearman(predicted uplift, true uplift): **0.845**
- Per-city ratio standard deviation: **0.070**

**Why is overlap only ~41% but captured utility ~85%?** Because many candidate sites are near-equivalents. The oracle picks one of several good nodes; the model may pick a different one with almost the same true uplift. Overlap is a strict set metric and understates quality. Regret is the economic metric: it measures how much actual usage is lost, not whether the exact same node was chosen.

The per-city worst case is `test_204619` at 60.8% of oracle (39.2% regret); the best is `test_204628` at 98.8%. The distribution is in `placement_results.csv`.

### 8.4 Out-of-distribution test

| Metric | Test | OOD |
|---|---:|---:|
| Usage MAE log | 0.166 | 0.222 |
| Usage R² log | 0.871 | 0.789 |
| Uplift MAE log | 0.352 | 0.304 |
| Uplift R² log | 0.735 | 0.692 |
| Placement vs oracle | 85.5% | **88.4%** |
| Placement regret | 14.5% | **11.6%** |
| Oracle overlap | 41.3% | 47.5% |

**Interpretation.** Usage accuracy degrades under shift, as expected. Placement does not degrade and in fact slightly improves. The OOD batch is not a controlled one-factor change, though: its cities average 1,418 nodes (vs 1,178), 132 stations (vs 83), usage noise 0.273 (vs 0.161), and a higher EV-adoption offset. The placement result therefore cannot be attributed to one cause, and it should not be read as general robustness. It is one parametric shift; a controlled ablation would vary one parameter at a time.

### 8.5 `alpha` ablation (validation)

| alpha | Ratio | Std |
|---:|---:|---:|
| 0.00 | 0.665 | 0.114 |
| 0.25 | 0.787 | 0.089 |
| 0.50 | 0.829 | 0.072 |
| **1.00** | **0.852** | **0.057** |
| 2.00 | 0.849 | 0.063 |

The plateau at 1.0–2.0 suggests the penalty is not overly sensitive once it is strong enough. The standard deviation also shrinks, meaning the penalty makes performance more consistent across cities, not just higher on average.

### 8.6 Calibration: the model compresses the top tail

Mean usage by observed quintile on the test stations:

| Quintile | Stations | Actual | Predicted |
|---:|---:|---:|---:|
| 0 | 667 | 3.46 | 3.88 |
| 1 | 666 | 6.34 | 6.74 |
| 2 | 667 | 9.11 | 9.39 |
| 3 | 666 | 13.03 | 12.91 |
| 4 | 667 | 23.29 | **19.91** |

The model over-predicts the bottom and under-predicts the top. The top decile is under-predicted by about 19% (actual 28.5, predicted 23.2 sessions/day). Likely causes:

- regression to the mean under Huber loss;
- few extreme examples relative to the bulk;
- log-space training compresses large values;
- unobserved demand shocks are not fully recoverable from features.

This is a real limitation for revenue estimates. It matters less for ranking: Spearman remains high, and the optimizer mostly needs the correct order. The agent's `predicted_usage` should be read as a conservative estimate, not a point forecast of revenue.

### 8.7 Weakest cities

| City | Nodes | Existing stations | Share of oracle | Regret |
|---|---:|---:|---:|---:|
| test_204619 | 984 | 55 | 60.8% | 39.2% |
| test_204615 | 763 | 44 | 70.7% | 29.3% |
| test_204637 | 1,105 | 90 | 75.5% | 24.5% |
| test_204614 | 1,551 | 78 | 76.9% | 23.1% |
| test_204606 | 1,374 | 134 | 77.0% | 23.0% |

Across the test set, the correlation between utility ratio and station count is only 0.16, and with node count 0.03 — so neither city size nor station density explains the failures. The weak cities likely have spatial shock patterns that the observable features do not reveal, plus near-ties among candidates. The honest conclusion is that a single aggregate metric hides meaningful per-city variance (std 0.070, worst case 0.39 regret).

### 8.8 Feature importance (uplift model, test candidates)

Permutation importance, MAE increase in log space:

| Rank | Feature | MAE increase |
|---:|---|---:|
| 1 | `competing_capacity` | 0.495 |
| 2 | `dist_center` | 0.194 |
| 3 | `n_stations_1km` | 0.176 |
| 4 | `population` | 0.153 |
| 5 | `nearest_station_dist` | 0.153 |
| 6 | `activity` | 0.089 |
| 7 | `city_nodes` | 0.082 |
| 8 | `city_station_rate` | 0.062 |
| 9 | `closeness` | 0.048 |
| 10 | `centrality` | 0.036 |
| 11 | `local_population` | 0.022 |
| 12 | `transit_access` | 0.020 |

The model relies most on **competition** (three of the top five features are competition measures), then on demand proxies and centrality. This matches the generator: in a Huff world, what matters is demand relative to nearby supply. The fact that competition dominates is also a warning for real-world transfer: if real competition is measured differently (e.g., by port count or operator, not capacity), the model's most important input changes meaning.

### 8.9 Runtime

| Stage | Time |
|---|---:|
| Full train + evaluation (`run_experiment`) | 247.6 s |
| Usage model training | 17.6 s |
| Uplift model training | 67.7 s |
| Dataset generation | separate; minutes for 400 cities |

Reference machine: RTX 4070 Laptop, CUDA. Inference is CPU and fast: scoring one city is milliseconds to a few seconds depending on node count.

---

## 9. The decision layer (agent)

The agent is a thin downstream layer that turns the uplift model into concrete actions. It is **not** used to compute any of the ML metrics above, and it does not see ground truth.

### 9.1 Action generation

For each of the 40 test cities:

1. Take all non-station candidates.
2. Predict uplift for each with the uplift model.
3. Run the same cannibalization-aware greedy selection with K = 8.
4. For each selected node, predict usage with the usage model (for reporting and the review rule).
5. Emit an action row with rank, coordinates, predicted uplift, predicted usage, uncertainty, confidence, explanation, and status.

Result: **320 actions** (40 cities × 8), of which **306** are `INSTALL_EV_CHARGER` and **14** are `SITE_VALIDATION`.

### 9.2 Confidence and uncertainty

Uncertainty is the standard deviation of the three MLP seeds' `expm1` predictions. Confidence converts relative uncertainty into a 0–100 score:

```text
relative = std / max(predicted_usage, 1e-6)
score    = 100 · clip(1 − mean(relative) / 0.45, 0, 1)

high   if score ≥ 70
medium if score ≥ 45
low    otherwise
```

This is a heuristic, not a calibrated probability. It is useful for triage and for driving human review; it should not be read as "70% chance the site is good".

### 9.3 Review rule

An action requires human review when either condition holds:

- confidence is not `high`; or
- predicted usage is below **10 sessions/day**.

The 10-session threshold is a business heuristic, not an economically optimized cutoff. In the current run, 14 actions are flagged: 13 only because of low predicted usage, and 1 because of medium confidence *and* low usage. No action is flagged for low confidence alone.

### 9.4 Local explanations

For each selected node, the agent performs a simple occlusion explanation on the uplift model:

1. Compute the base prediction for the node.
2. For each of the top 5 globally important features, replace the node's value with the median value from that city's candidate pool.
3. Re-predict and record the drop.
4. Keep the three features with the largest positive drop.

This answers: "which observed features are propping up this site's predicted uplift relative to a typical candidate?" It is model-agnostic, local, and cheap. It is **not** a causal explanation and does not account for feature interactions beyond the model's own response.

### 9.5 Outputs

| File | Content |
|---|---|
| `priority_sites.csv` | 320 action rows |
| `review_queue.csv` | 14 rows requiring human review |
| `agent_actions.json` | Full action log with explanations and metadata |
| `agent_state.json` | Summary counts and generation timestamp |
| `dashboard.html` | Interactive Leaflet demo for one test city |
| `dashboard_preview.png` | Static preview of the same city |

The dashboard projects synthetic normalized coordinates into a small Romania-like bounding box for display. This is a demo canvas, not a geographic claim.

---

## 10. Data and artifacts

### 10.1 Repository layout

```text
Smiling-F-Smarthack-2026/
├── README.md
├── data-generation/
│   ├── README.md
│   ├── pyproject.toml            # installable "evdata" package
│   ├── src/evdata/
│   │   ├── generator.py          # city + ground truth + Huff simulator
│   │   └── cli.py                # `evdata build`
│   └── data/synthetic/
│       ├── cities.joblib         # 400 SyntheticCity objects (~261 MB)
│       └── benchmark.json        # counts, seeds, generator version
└── ML-Agent/
    ├── README.md
    ├── pyproject.toml
    ├── requirements.txt
    ├── outputs/
    │   └── synthetic/            # models, metrics, predictions, agent, reports
    ├── src/evplacement/
    │   ├── config.py
    │   └── synthetic/
    │       ├── generator.py      # compatibility re-export from evdata
    │       ├── model.py          # MLP/HGB ensemble, labels, oracle, metrics
    │       ├── agent.py          # action layer
    │       ├── dashboard.py      # HTML/PNG demos
    │       ├── reports.py        # two Romanian reports
    │       └── cli.py            # build / train / agent / report / run
    └── tests/
        └── test_synthetic.py
```

### 10.2 `cities.joblib`

The dataset lives at [`../data-generation/data/synthetic/cities.joblib`](../data-generation/data/synthetic/cities.joblib). It is a dictionary keyed by `city_id` (`{split}_{seed}`), where each value is a `SyntheticCity` dataclass:

| Field | Type | Content |
|---|---|---|
| `city_id` | str | e.g. `test_204600` |
| `seed` | int | generator seed |
| `split` | str | train / validation / test / test_shift |
| `nodes` | DataFrame | all node-level columns, including latent demand and observed usage |
| `edges` | ndarray | `(E, 2)` graph edges |
| `centers` | ndarray | `(n_centers, 2)` urban centre coordinates |
| `params` | dict | `n_nodes`, `n_centers`, `station_rate`, `ev_base`, `noise`, `lambda_norm`, `shift` |
| `station_nodes` | ndarray | indices of existing stations |
| `station_capacity` | ndarray | capacity per existing station |
| `station_usage` | ndarray | simulated usage per existing station |
| `latent_demand` | ndarray | hidden demand per node |
| `features` | DataFrame | `nodes` plus engineered competition/context features |

Key `nodes`/`features` columns:

- `x`, `y`, `node_id`, `city_id`
- the 24 model features (Section 4.2)
- `latent_demand` (ground truth, never a feature)
- `is_station`, `station_capacity`, `observed_usage` (NaN for candidates)

### 10.3 Output artifacts

| File | Content |
|---|---|
| `usage_model.joblib` | dict: `{model, features, metrics}` for the usage model |
| `uplift_model.joblib` | dict: `{model, features, alpha, metrics}` for the uplift model |
| `experiment.joblib` | Canonical full bundle: both models, predictions, metrics, importance |
| `metrics.json` | All usage, uplift, placement, OOD, alpha, and runtime metrics |
| `test_predictions.csv` | Held-out station predictions and residuals |
| `placement_results.csv` | Per-city test placement ratios, regret, overlap, baselines |
| `placement_shift_results.csv` | Same for the OOD cities |
| `feature_importance.csv` | Permutation importance of the uplift model |
| `priority_sites.csv` | 320 agent actions |
| `review_queue.csv` | 14 human-review cases |
| `agent_actions.json` | Traceable action log with explanations |
| `agent_state.json` | Action/review counts |
| `dashboard.html` | Interactive demo map (needs internet for Leaflet/OSM tiles) |
| `dashboard_preview.png` | Static city preview |
| `validation.png` | Predicted-vs-actual and per-city regret plot |
| `RAPORT_DETALIAT_RO.md` | Detailed Romanian engineering report |
| `RAPORT_JURI_RO.md` | Short Romanian jury brief |

`experiment.joblib` is the source of truth if the standalone model files and the metrics ever disagree. The standalone files are convenience exports for inference; the training command rewrites all three.

### 10.4 Loading a model

```python
import joblib
from evplacement.synthetic.model import FEATURES

payload = joblib.load("outputs/synthetic/uplift_model.joblib")
model = payload["model"]          # UsageEnsemble, CPU
features = payload["features"]    # same 24 names as FEATURES
alpha = payload["alpha"]          # 1.0

predictions = model.predict(frame[features])          # sessions/day
uncertainty = model.predict_std(frame[features])      # MLP seed disagreement
```

---

## 11. Design decisions and trade-offs

This section is the "why" behind the code. Each row is a deliberate choice, not an accident.

| Decision | Alternative | Why we chose this | Cost / trade-off |
|---|---|---|---|
| **Synthetic simulator** | Train on real Bucharest/OSM data | Real data has no counterfactual and strong siting selection bias; a simulator gives measurable regret | Formulas are ours; not a real demand forecast; external validity is limited |
| **City-level split** | Random node or station split | Random splits leak spatial context and overstate generalization | Fewer effective samples; test cities are entire new worlds |
| **Two models (usage + uplift)** | One usage model, rank candidates | Uplift is the decision objective and includes cannibalization; candidates have no usage label | Two training runs; two artifacts; usage model not used for ranking |
| **`log1p` target** | Raw sessions/day | Stabilizes a right-skewed target; Huber on log ≈ relative error | Compresses the top tail; under-predicts the busiest stations |
| **Noise-free uplift labels** | Add measurement noise to uplift | Placement is about expected system value; noise in observed usage is a nuisance for the usage model | Uplift is slightly optimistic relative to a noisy realized outcome |
| **Huber loss** | MSE | Robust to tail and label noise; better validation MAE | Less aggressive fit to extremes; contributes to top-tail compression |
| **3-seed MLP ensemble** | Single MLP | Variance reduction + uncertainty signal at low cost | 3× training compute; still not a calibrated interval |
| **HGB as second expert** | MLP only | Different inductive bias; cheap robustness check | Validation gave it zero weight; it adds artifact size and complexity for no current gain |
| **Blend chosen on validation** | Fixed 50/50 | Avoids tuning on test; lets data decide | With only 5 grid points, the choice is coarse |
| **Cannibalization penalty (`alpha`)** | Pick top K independently | Top-K clusters and cannibalizes; penalty raises validation ratio from 0.67 to 0.85 | Uses the generator's kernel shape; `alpha` is not calibrated to real economics |
| **Greedy oracle** | Exhaustive optimum | Exhaustive is combinatorial; greedy is strong, transparent, and standard | Oracle is not truly optimal; model could theoretically beat it |
| **K = 8 per city** | National budget allocation | Keeps the benchmark comparable across cities | No cross-city prioritization; not a full capital allocation model |
| **No ground-truth features** | Include latent demand as an input | Would make the benchmark meaningless; unit-tested | Model must infer demand from proxies; irreducible error remains |
| **Per-city demand normalization** | Global demand scale | Makes cities comparable and learning stable | Removes absolute city-size effects that a real planner might care about |
| **CPU inference** | Require GPU at demo time | Portability for judges/deployment | Slightly slower inference; model must be moved after training |
| **Occlusion explanations** | SHAP / integrated gradients | Simple, fast, model-agnostic, no extra dependency | Local sensitivity, not causal; interactions are opaque |
| **No GNN** | Graph neural network over the city | Strong tabular baseline first; graph information is already summarized | Ignores explicit message passing; a GNN is a plausible next step |
| **No real calibration yet** | Fine-tune on Bucharest data | No real session labels were available in this deliverable | The model cannot be used operationally without recalibration |

---

## 12. Reproducing the benchmark

All commands assume the current directory is `ML-Agent/`.

### 12.1 Environment

Tested on Python 3.13 / Windows 11. PyTorch is installed from the default wheel; for CUDA, install the matching PyTorch build first from <https://pytorch.org/get-started/locally/>.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install -e . --no-deps
```

`requirements.txt` pins the tested versions. `torch>=2.2` is intentionally loose so the correct CUDA/CPU wheel can be chosen for the machine.

### 12.2 Commands

```powershell
# 1. Generate 400 cities (writes ../data-generation/data/synthetic/)
.\.venv\Scripts\python.exe -m evplacement build

# 2. Train usage + uplift models, evaluate holdout and OOD
.\.venv\Scripts\python.exe -m evplacement train --k 8

# 3. Generate 320 agent actions, dashboard, plots
.\.venv\Scripts\python.exe -m evplacement agent --k 8

# 4. Generate the two Romanian reports
.\.venv\Scripts\python.exe -m evplacement report
```

Or all at once:

```powershell
.\.venv\Scripts\python.exe -m evplacement run --k 8
```

`run` rebuilds the dataset only if `../data-generation/data/synthetic/cities.joblib` is missing or `--refresh` is passed; otherwise it reuses the existing cities and retrains.

The generator is also a standalone package. From `data-generation/`:

```powershell
python -m pip install -e .
python -m evdata build
```

The console scripts `evplacement` and `evcharge-synthetic` are equivalent to `python -m evplacement`.

### 12.3 Tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The suite covers:

- same-seed reproducibility of a generated city;
- positive usage and station/usage length agreement;
- non-negative candidate uplift;
- no ground-truth features in the model input;
- vectorized counterfactual equals direct simulation;
- true greedy improves true utility.

### 12.4 Expected runtime and outputs

On the reference machine, `train` takes about 4 minutes (247.6 s for the measured train + evaluation stage). `build` is separate. `agent` and `report` are fast (seconds to a minute).

After a full run, `outputs/synthetic/` should contain the files listed in Section 10.3. The headline numbers should match Section 8 closely; exact last digits can differ slightly across hardware due to floating-point and GPU non-determinism.

---

## 13. Limitations and the path to real data

### 13.1 Limitations

1. **It is a simulator, not Romanian driver behaviour.** The demand, siting, and Huff formulas are chosen by us, not estimated from real session data.
2. **No real usage labels.** The model cannot predict real revenue, queueing, or utilization.
3. **The oracle exists only in the simulator.** In production, the counterfactual is unobservable; evaluation would require a pilot, an A/B test, or a credible causal design.
4. **Synthetic topology is not a specific city.** The graph is polycentric but does not replicate Bucharest's street network, river, airports, or administrative boundaries.
5. **Top-tail compression.** The model under-predicts the busiest stations by roughly 19% in the top decile. Ranking is better than calibration.
6. **Parametric OOD only.** The shift test changes generator parameters, not the generator family. It is not evidence of geographic transfer.
7. **Per-city budget only.** There is no national allocation, cross-city prioritization, or budget coupling.
8. **Uncalibrated uncertainty.** Seed disagreement is a heuristic, not a predictive interval.
9. **No cost model.** All sites are treated as equally expensive and equally feasible; grid capacity, land, and permitting are ignored.
10. **No temporal dynamics.** Time-of-day demand, queues, and occupancy are collapsed into a daily rate.

### 13.2 What would transfer to a real city

The transferable parts are the **method and the evaluation harness**, not the learned weights:

- the graph/feature representation of urban space;
- the two-target formulation (usage + incremental uplift);
- the city-held-out evaluation protocol;
- the cannibalization-aware greedy optimizer;
- the review/confidence layer;
- the discipline of keeping ground truth out of features.

The non-transferable parts are the demand formula, the siting process, the Huff parameters, and every number learned from them.

### 13.3 A credible Bucharest plan

The synthetic model should not be applied directly to Bucharest. A defensible path:

1. **Build the graph.** Map real stations and candidate sites from OSM, or use an H3 hex grid with real road distances. Attach population, POI, traffic, transit, parking, and grid-capacity layers.
2. **Collect labels.** Obtain session counts and kWh for a sample of real stations (operator data, roaming data, or a pilot). Even a few dozen stations with time series would be a start.
3. **Calibrate the demand distribution.** Replace the synthetic latent-demand formula with a model estimated from real features and observed usage. Keep the Huff-style competition structure if the data supports it; estimate `λ` and capacity effects rather than assuming them.
4. **Retrain or fine-tune.** Train the usage model on real stations, then the uplift model on counterfactual labels generated by the calibrated simulator (or, better, on experimental variation).
5. **Keep the same evaluation discipline.** Hold out cities or districts, not random nodes; if possible, hold out time periods. Compare against the hand index and the incumbent operator's siting policy.
6. **Validate with a pilot.** The only real proof is installing a small number of model-chosen stations and measuring incremental usage against a matched control. That is the real-world version of the oracle.

### 13.4 What would make the biggest difference

- **Real session labels** (even a small sample) — unlocks calibration and honest error bars.
- **A real competition measure** (port count, operator, price) — the current model's most important feature is `competing_capacity`, which is synthetic.
- **Cost and grid data** — turns "best K sites" into a real budget allocation.
- **Temporal demand** — time-of-day and weekday/weekend patterns change which sites are valuable.
- **A causal pilot design** — the only way to measure uplift outside a simulator.

---

## 14. Glossary

| Term | Meaning |
|---|---|
| **Node** | A candidate location in the synthetic city graph. |
| **Station** | A node with an existing charger and a simulated capacity/usage. |
| **Candidate** | A node without a station; eligible for placement. |
| **Latent demand** | The simulator's hidden demand per node. Never a model feature. |
| **Observed usage** | Noisy sessions/day generated for existing stations; the usage-model target. |
| **Uplift** | True incremental system usage from adding one station, `U(S ∪ {i}) − U(S)`. |
| **Cannibalization** | Usage stolen from nearby existing or newly added stations. |
| **Oracle** | Greedy selection using the true simulator; the reference for placement quality. |
| **Regret** | `1 − utility_ratio`; the share of oracle-created usage the model fails to capture. |
| **Utility ratio** | Model incremental utility divided by oracle incremental utility. |
| **OOD** | Out-of-distribution; the 20 cities generated with shifted parameters. |
| **Huff model** | A spatial market-share model where attractiveness is divided by attractiveness plus competition. |
| **Permutation importance** | MAE increase after shuffling one feature; a model-agnostic importance measure. |
| **Occlusion explanation** | Local explanation that replaces a feature with a baseline value and measures the prediction drop. |

---

## Companion documents

- [`outputs/synthetic/RAPORT_DETALIAT_RO.md`](outputs/synthetic/RAPORT_DETALIAT_RO.md) — detailed Romanian engineering report (methodology, results, limitations, Bucharest plan).
- [`outputs/synthetic/RAPORT_JURI_RO.md`](outputs/synthetic/RAPORT_JURI_RO.md) — one-page Romanian jury brief.
- [`outputs/synthetic/dashboard.html`](outputs/synthetic/dashboard.html) — interactive city demo.
- [`outputs/synthetic/validation.png`](outputs/synthetic/validation.png) — predicted-vs-actual and per-city regret.

**One-sentence summary:** we built a simulator with ground truth, two learned models that predict usage and counterfactual uplift, and a cannibalization-aware optimizer that captures 85.5% of an oracle's placement value on unseen cities — and we are explicit that this is a decision laboratory, not a real-world demand forecast.
