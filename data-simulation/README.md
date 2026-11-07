# evsim: EV mobility, energy and charging-placement simulator

A parametrised, seeded generator of synthetic (and, for Romania, partly real) data about:

- **cities**: population, density, zones (core / suburbs / commuter belt), terrain, climate, income, prices;
- **EV ownership** per zone, driven by economics, home-charging access, chargers and neighbours;
- **trips** between all zones (local commuter flows and intercity flows) with congestion;
- **energy consumption** of every trip from a physics model, with noise, giving a distribution of kWh per trip and per origin→destination pair;
- **charging-station placement**: candidate sites between cities, and an environment that simulates how any placement is used (battery state, stops, detours, queues, economics) and returns a score.

It exists to feed and test ML models: one that predicts energy consumption, and an external one that places charging stations. The ML models are **not** part of this repository.

---

## Contents
1. [Quick start](#1-quick-start)
2. [Files in this folder](#2-files-in-this-folder)
3. [How a run works](#3-how-a-run-works)
4. [Output files and data dictionary](#4-output-files-and-data-dictionary)
5. [How the data is generated](#5-how-the-data-is-generated)
6. [Using the data for ML](#6-using-the-data-for-ml)
7. [Parameters](#7-parameters)
8. [Charging-station placement environment](#8-charging-station-placement-environment)
9. [Romania](#9-romania)
10. [Design decisions and lessons learned](#10-design-decisions-and-lessons-learned)
11. [Limitations](#11-limitations)
12. [Reproducibility and runtime](#12-reproducibility-and-runtime)
13. [Reference results](#13-reference-results)

---

## 1. Quick start

```bash
pip install numpy pandas                  # pyarrow only for --format parquet
                                          # geonamescache only if romania_data/ro_city_coords.csv is missing
```

**A. Synthetic region** (about 5 seconds, 100k trips)
```bash
python evsim.py --out data --n-trips 100000 --seed 1
python evsim.py --out data --set econ.ev_subsidy_eur=8000 --set geo.n_cities=60     # override any parameter
python evsim.py --print-default-config > my.json && python evsim.py --config my.json --out data
```

**B. Charging-station placement** on the synthetic region
```bash
python evsim_charging.py --out out --compare --autosize --n-stations 60             # all baselines side by side
python evsim_charging.py --out out --strategy flow --n-stations 60 --autosize       # one strategy, full outputs
python evsim_charging.py --out out --stations-file my_stations.csv                  # score YOUR placement
```

**C. Romania** (real cities + synthetic fill, same output format)
```bash
python evsim_romania.py --out romania --n-trips 100000 --seed 1                     # needs romania_data/ next to the script
python evsim_charging.py --out ro_ch --romania --compare --autosize --n-stations 60 # charging placement on Romania
```

**D. From Python**
```python
import evsim, evsim_charging as ec
cfg = evsim.load_config(None, ["geo.n_cities=40", "econ.year=2030"])   # (config_path, overrides)
nodes, od, trips, od_summary = evsim.run(cfg, "data")                    # also writes csvs; use None to skip writing

world = ec.build_world(cfg)                       # runs evsim + builds corridor network and candidate sites
world.candidates                                  # features per candidate site (input for your placement model)
stations = ec.place_flow(world, 60)               # or your own DataFrame: site_id, n_ports, power_kw
res = world.evaluate(stations)                    # ~0.1-0.5 s
res.metrics["score"]; res.tables["station_usage"]

import evsim_romania as ro                        # Romania into the same machinery
cfg, nodes, lookup, prov, meta, P = ro.setup(seed=1)
world = ec.build_world(cfg, nodes=nodes)
```

---

## 2. Files in this folder

| File | Purpose |
|---|---|
| `evsim.py` | Core simulator: configuration, cities/zones, economics, EV adoption, mobility, energy physics, export. Also holds `ChargingConfig`. |
| `evsim_charging.py` | Charging environment: corridor network, candidate sites, driver/queue simulation, economics, baselines, CLI. |
| `evsim_romania.py` | Romanian cities: loads real data, fills gaps synthetically, calibrates to national figures, runs the same pipeline. |
| `romania_data/ro_cities_wikipedia_2021.csv` | Real: city, county, 2021 census population, elevation (Wikipedia). |
| `romania_data/ro_city_coords.csv` | Coordinates of those cities (GeoNames, plus 8 flagged approximations). Cache so `geonamescache` is not needed. |
| `romania_data/ro_county_wages_2026_01.csv` | Real: average net monthly wage per county, January 2026. |
| `romania_data/ro_national_params.json` | Real national figures (fleet, chargers, prices, FX) with source URLs and dates. |
| `README.md` | This file. |

A delivered example dataset (Romania, seed 1, 100k trips) has the layout described in section 4 plus the Romania extras in section 9.

---

## 3. How a run works

```
build_nodes ──► ev_adoption ──► build_od ──► sample_trips ──► split / noise / export
 (cities,        (EV share       (gravity       (trip rows: features, physics energy,
 zones, climate,  per zone)       flows,         targets, latent ground truth)
 economics)                       congestion)

                                      ┌───────────────────────────────────────────────┐
                                      ▼                                               │
corridor network ─► candidate sites ─► evaluate(stations): per intercity trip simulate battery,
 (MST + k nearest)   (outside cities)   charging stops, detours ─► Erlang-C queues per station and
                                         hour ─► feedback to driver choices (few iterations) ─► usage, KPIs, score
```
`evsim.run(cfg, outdir, nodes_override=None)` is the single entry point. `nodes_override` replaces `build_nodes`, which is how Romania plugs in real cities.

---

## 4. Output files and data dictionary

Written to the `--out` directory. The schema is identical for the synthetic region and for Romania.

### 4.1 `nodes.csv`: one row per zone (a city, or a zone of a big city)
| Column | Meaning |
|---|---|
| `node_id` | Zone id (key used by `od.csv` and `trips.csv`) |
| `city_id` | Parent city / metro area (0..n-1, contiguous). Several nodes share a `city_id` for big cities |
| `zone_type` | `core`, `inner` (suburb), `outer` (commuter belt), `town` (small, unsplit city) |
| `region` | Cluster id. Synthetic: random geographic cluster. Romania: NUTS-2 development region index (0 Nord-Vest, 1 Centru, 2 Nord-Est, 3 Sud-Est, 4 Sud-Muntenia, 5 București-Ilfov, 6 Sud-Vest Oltenia, 7 Vest) |
| `x`, `y` | Position in km on a plane (`y` grows northward). Romania: equirectangular projection of lat/lon |
| `city_pop` | Population of the whole city (sum of its zones) |
| `pop` | Population of this zone |
| `density` | People per km² of this zone |
| `area_km2` | `pop / density` |
| `elev_m` | Elevation (m) |
| `roughness_m_km` | Mean rolling terrain gain per km (extra climb on any trip from/to this zone) |
| `t_mean_c` | Annual mean temperature (°C) |
| `income` | Synthetic region: EUR per capita per year. **Romania: annual net wage per employee in EUR** (not per capita) |
| `elec_price`, `fuel_price` | EUR/kWh and EUR/litre |
| `home_charging` | 0–1 index of access to home charging (falls with density) |
| `chargers_per_10k` | Public chargers per 10,000 inhabitants |
| `vehicles_per_capita` | Motorisation rate |
| `ev_share` | Fraction of vehicles that are EVs |
| `n_vehicles`, `n_evs` | Vehicle and EV counts (fractional) |
| `congestion_load` | Daily vehicle trips touching the zone ÷ road capacity (≈1 = at capacity) |
| `speed_factor` | Free-flow speed multiplier from congestion (1 = free flow) |

### 4.2 `od.csv`: expected daily demand for every ordered zone pair
Includes the diagonal (`origin == dest`, trips inside a zone) and pairs with zero demand.
| Column | Meaning |
|---|---|
| `origin`, `dest` | `node_id`s |
| `road_km` | Road distance (straight line × circuity; for `origin == dest` an estimated mean intra-zone length, at least 1 km × circuity) |
| `daily_trips` | Expected car trips per day, all vehicles |
| `daily_ev_trips` | `daily_trips × ev_share(origin)` |
| `same_city` | 1 = local/commuter (same `city_id`), 0 = intercity |

### 4.3 `trips.csv`: the ML dataset, one row per simulated EV trip
Trips are drawn with probability proportional to `daily_ev_trips`, so busy pairs appear more often.

| Group | Columns |
|---|---|
| Identifiers (not features) | `trip_id`, `origin`, `dest`, `origin_city`, `dest_city`, `split` (`train`/`val`/`test`) |
| Route | `origin_zone`, `dest_zone`, `is_intercity` (1 = different `city_id`), `distance_km` (road), `euclid_km` |
| Origin / destination attributes | `origin_pop`, `dest_pop`, `origin_density`, `dest_density`, `origin_income`, `dest_income`, `origin_ev_share`, `dest_ev_share`, `origin_elev_m`, `dest_elev_m`, `delta_elev_m` (dest − origin) |
| Time and weather | `hour` (0–24, fractional), `weekday` (0–4 weekday, 5–6 weekend), `month` (1–12), `temp_c` (measured: true temperature + sensor noise, may be NaN if `missing_rate > 0`), `rain` (0/1) |
| Traffic | `congestion_index` (zone load × time-of-day factor; higher at weekday rush hours) |
| Vehicle | `veh_class` (`city`, `sedan`, `suv`, `van`), `veh_mass_kg` (empty mass; passengers and cargo are not included), `veh_battery_kwh` (nominal), `veh_age_years`, `heat_pump` (0/1), `passengers` |
| Price | `elec_price` (mean of origin and destination) |
| **Targets** | `energy_kwh` (noisy), `consumption_kwh_100km` (= energy / distance × 100, the usual regression target), `duration_min`, `avg_speed_kmh`, `cost_eur` (= energy × `elec_price`), `needs_charge` (1 if energy > 80% of usable battery, where usable = nominal × state of health from age) |
| **Latent ground truth (`gt_*`)** | `gt_energy_noisefree_kwh`, `gt_drive_kwh`, `gt_hvac_kwh`, `gt_climb_net_kwh` (climb minus regeneration), `gt_driver_aggr`, `gt_wind_ms`, `gt_frac_highway`, `gt_true_temp_c`, `gt_is_outlier`. For diagnostics only; remove with `output.drop_latent=true` |

### 4.4 `od_energy_summary.csv`: the A→B consumption distribution
One row per origin–destination pair with at least `output.min_samples_od_summary` (default 5) trips.
`n`, `distance_km` (mean), `kwh_mean`, `kwh_std`, `c100_mean`, `c100_std` (kWh/100 km), `c100_p10`, `c100_p50`, `c100_p90`. Computed from **all** trips, including test rows (see leakage warning in section 6). Covers only busy pairs.

### 4.5 `metadata.json`
Library version, the complete configuration (every parameter and the seed), target names and the latent prefix. This is enough to regenerate the dataset exactly.

### 4.6 Charging outputs: see section 8.6. Romania extras: see section 9.6.

---

## 5. How the data is generated

### 5.1 Cities and populations (synthetic region)
- `geo.n_regions` cluster centres are placed uniformly in 15–85% of the square region (`geo.region_km`). Each city gets a random cluster and a position normally scattered around the centre (`geo.region_spread × region_km`), clipped to the map. Clusters double as economic/climate regions.
- **City populations** follow a rank-size law: `largest_city_pop / rank^rank_size_exponent`, floored at `min_city_pop`, multiplied by lognormal noise (σ = 0.08), then randomly permuted over the cities (so the largest city is not always rank 1 spatially).
- **Average density** of a city: `base_density × (pop / 1e5)^density_pop_exponent × lognormal(σ = 0.25)`: bigger cities are denser.

### 5.2 Zones inside cities (the commuter-belt problem)
- A city with `pop ≥ geo.zones_threshold` is split into four nodes; smaller ones become one `town` node.
  - **core**: at the city centre, `core_frac` of the population (default 35%).
  - **inner**: suburb ring at radius `0.5 R`, `inner_frac` (40%).
  - **outer**: two commuter-belt nodes at radius `R` in random directions, sharing the remainder (25%, split uniformly 40–60/60–40).
  - `R = metro_radius_scale × sqrt(pop / 1000)` km.
- Zone density = city density × `zone_density_mult` (core 3, inner 1, outer 0.25, town 1) × lognormal(σ = 0.1); `area = zone_pop / zone_density`.
- Commuter flows arise later from the gravity model: core zones attract more (`attraction_mult`), outer zones generate trips but attract few, so suburbs → core flows dominate and load the core's roads.

### 5.3 Terrain and climate
- **Elevation**: base elevation plus a sum of five random sinusoids (`terrain_wavelength_km`, amplitude `elev_amp_m`), floored at 0. `roughness_m_km = roughness_m_per_km × lognormal(σ = 0.4) × (1 + elev/800)`.
- **Mean temperature** of a node: `t_mean_c − t_north_gradient_c × y/region_km − 0.0065 × elev + uhi_c_per_log_pop × log10(city_pop/1e4)`.
- **Temperature of a trip**: mean of origin and destination `t_mean_c`, minus the seasonal term `t_season_amp_c × cos(2π(day_of_year − 200)/365)`, minus the daily term `t_diurnal_amp_c × cos(2π(hour − 15)/24)`, plus N(0, `weather_sd_c`). `temp_c` in the file adds sensor noise on top.
- Rain (`rain_prob`) raises rolling resistance; wind is a signed headwind component N(0, `wind_sd_ms`).

### 5.4 Economics
- **Income** = `income_base × (city_pop/1e5)^income_pop_exponent × region_multiplier × zone_income_mult × lognormal(σ)`. Region multipliers are lognormal (`region_income_sd`). Suburbs are richer than cores by default.
- **Prices**: national base × a lognormal regional factor (`price_region_sd`; fuel gets half of that spread).
- **Home-charging access** = `sigmoid(−hc_steepness × ln(density / hc_density_mid))`: about 50% at `hc_density_mid` people/km², lower in dense areas.
- **Public chargers per 10k** = `chargers_per_10k_base × (income/income_base)^0.8 × (city_pop/1e5)^0.1 × lognormal(σ = 0.3)`.
- **Vehicles per capita** = `clip(motorization_base × (income/income_base)^motorization_income_exp × (density/1000)^motorization_density_exp, 0.10, 0.85)`.

### 5.5 EV ownership
Per zone, a logit then a spatial blend:
```
logit = ev_bias
      + w_income          × z(ln income)
      + w_home_charging   × 2 × (home_charging − 0.5)
      + w_chargers        × z(ln chargers_per_10k)
      + w_subsidy_per_1000 × ev_subsidy_eur / 1000
      + w_price_ratio     × z(ln[(fuel_price × ice_l_per_100km) / (elec_price × 17)])
      + adoption_speed_per_year × (year − 2026)
logit = (1 − spatial_rho) × logit + spatial_rho × (distance-weighted mean of the other zones' logits)   # kernel exp(−d / spatial_scale_km)
ev_share = max_ev_share × sigmoid(logit)
n_evs    = pop × vehicles_per_capita × ev_share
```
`z()` standardises across zones. Default weights: bias −2.6, income 0.9, home charging 1.0, chargers 0.5, subsidy 0.10 per 1,000 EUR, price ratio 0.5, 0.35 logit per year, ρ = 0.35, scale 60 km, cap 90%. Typical result in the default region: dense cores about 9% EVs, suburbs and commuter belts 23–26%.

### 5.6 Mobility (gravity model)
- **Distances**: straight-line between node positions; intra-zone distance `0.52 × sqrt(area)`, at least 1 km. Road distance = straight line × circuity, where circuity falls from `circuity_short` (1.45) to `circuity_long` (1.18) with scale 30 km.
- **Trip production** of a zone: `pop × active_frac × trips_per_person_day` (default 0.55 × 2.2).
- **Local flows** (same `city_id`, including the zone itself): share `1 − intercity_frac` of production, distributed over destinations ∝ `pop_j × attraction_mult[zone_j] × exp(−road/commute_scale_km)` (production-constrained).
- **Intercity flows** (different `city_id`): share `intercity_frac` (6%), distributed ∝ `pop_j × (road + 10)^(−intercity_gamma)`.
- **Congestion**: node load = (inflow + outflow) / (`road_capacity_trips_km2_day × (density/1000)^road_capacity_density_exp × area`); speed factor `1/(1 + bpr_alpha × load^bpr_beta)` (BPR curve). At trip level the load is scaled by time of day: `load × (0.4 + rush_boost × peak)` with weekday peaks around 8:00 and 17:30. The capacity exponent defaults to 0 (constant capacity per km²) for the synthetic region and is 0.7 for Romania (section 10).

### 5.7 Sampling trips
1. Choose an OD pair with probability ∝ `daily_ev_trips`.
2. Hour: weekday local trips mix 35% N(8, 1.2), 35% N(17.5, 1.5), 30% U(6, 22); all other trips U(7, 22). Weekday uniform 0–6, month uniform 1–12 (all months equally likely, no holidays).
3. Weather as in 5.3. Air density from temperature and mean elevation.
4. **Vehicle class** probabilities ∝ `share × (income/income_base)^(fleet_income_tilt × premium)`, so richer areas get more SUVs. Age ~ Gamma(2, 1.6) years; state of health `1 − 0.018 × age` (floor 0.6); heat pump by class probability; passengers 1 + Binomial(3, p) (p lower on weekday morning local trips); cargo ~ Exponential(25 kg); occupant mass 78 kg.
5. **Driver**: speed factor lognormal(σ = 0.08); aggressiveness `1 + 2 × (speed_factor − 1) + N(0, 0.12)`, clipped 0.6–1.8 (correlated with speed).

Default fleet (class: share, empty mass kg, CdA m², Crr, battery kWh, drivetrain η, regen η, heat-pump probability): city 25%, 1250, 0.60, 0.0085, 40, 0.88, 0.60, 0.2; sedan 30%, 1700, 0.62, 0.0080, 62, 0.90, 0.65, 0.5; suv 35%, 2100, 0.78, 0.0090, 78, 0.89, 0.62, 0.6; van 10%, 2400, 1.05, 0.0100, 70, 0.87, 0.55, 0.1.

### 5.8 Energy model (per trip)
- **Road mix**: highway share `0.9 × (1 − exp(−road / highway_scale_km))` (×0.4 for local trips, ×(1 + N(0, 0.1)), clipped at 0.95). The remainder is split into urban and arterial by `sigmoid(1.2 × (ln density_mean − ln urban_density_mid)) + N(0, 0.08)`, where `density_mean` is the geometric mean of origin and destination density.
- **Speeds**: urban 38, arterial 62, highway 112 km/h (free flow), reduced by congestion and scaled by the driver's speed factor.
- **Per segment**, force-equivalent at the wheels: rolling `Crr × m × g` (× 1.15 in rain) + aerodynamic `½ ρ CdA v_air² × aggressiveness` (headwind shelters: 0.3 urban, 0.7 arterial, 1.0 highway) + stop-and-go kinetic `stops_per_km/1000 × ½ m (1.3 v)² × (1 − regen η) × aggressiveness` (2.4, 0.5, 0.06 stops/km). Battery energy = force ÷ 3.6 ÷ drivetrain η Wh per km.
- **Terrain**: climb energy `m g Δh_up / η`, with `Δh_up = max(Δelev, 0) + roughness × distance / 2`; recovered `m g Δh_down × regen η × η`. Drive energy = `max((flat + climb − recovered) × cold × aged, 0.25 × flat)`, `cold = 1 + 0.006 × max(0, 18 − T)`, `aged = 1 + 0.15 × (1 − state of health)`.
- **HVAC and auxiliaries** over the trip duration: heating `110 W/°C × max(0, 18 − T) / COP`, cooling `90 W/°C × max(0, T − 23) / 2.8`, COP of a heat pump `clip(2.4 + 0.07 T, 1, 3.5)` (1 otherwise), plus 350 W of baseline load.
- **Noise**: multiplicative lognormal with mean 1 and σ = `0.05 + 0.10 × exp(−distance/8 km)` (short trips are noisier); 1% of trips are outliers multiplied by U(1.3, 2.0) (`gt_is_outlier`).

### 5.9 Splits and imperfections
`output.split_strategy`: `random`, `origin_city` (spatial holdout), `od_pair`, `month` (group holdout); fractions `split_fracs` = (0.7, 0.15, 0.15). `output.missing_rate` injects NaN into `output.missing_cols` (default `temp_c`, `veh_age_years`, `passengers`). `output.temp_sensor_sd` is the noise on exported temperature.

---

## 6. Using the data for ML

- **Energy model**: predict `consumption_kwh_100km` (or `energy_kwh`) from the route, place, time, weather and vehicle columns. A gradient-boosting baseline with the `origin_city` split on the default region reached R² ≈ 0.48 and MAE ≈ 3.4 kWh/100 km (mean 19.5), so the task is not trivial.
- **Features to drop when predicting energy**: `energy_kwh` / `consumption_kwh_100km` (whichever is the target), `duration_min`, `avg_speed_kmh`, `cost_eur`, `needs_charge` (derived from the target), every `gt_*` column, and the identifiers (`trip_id`, `origin`, `dest`, `origin_city`, `dest_city`, `split`). Categorical columns to encode: `origin_zone`, `dest_zone`, `veh_class`.
- **Leakage warning**: `od_energy_summary.csv` uses all rows. If you use it as a feature or baseline, recompute it from the training rows only.
- **Generalisation tests**: `split_strategy=origin_city` tests unseen cities; `month` tests unseen seasons. For distribution shift, generate a second dataset with another seed and a changed configuration (e.g. `geo.t_mean_c=4`, `econ.year=2032`, `energy.noise_sigma=0.12`) and evaluate a model trained on the first.
- **Sampling weights**: busy OD pairs are over-represented relative to rare ones. Use `od.csv` if you need population-level statistics.
- **Distribution per A→B**: `od_energy_summary.csv` gives per-pair statistics; for a model of the whole distribution (not just the mean) use the trip rows of a pair.

---

## 7. Parameters

Everything is a dataclass field in `evsim.py`. Set with `--set section.key=value` (JSON values; dict/list values as JSON), a `--config file.json`, or in Python. `python evsim.py --print-default-config` prints all of them.

| Section | Key parameters (default) |
|---|---|
| `geo` | `n_cities` (30), `region_km` (500), `n_regions` (4), `largest_city_pop` (1.8M), `rank_size_exponent` (1.0), `min_city_pop` (15k), `base_density` (300), `density_pop_exponent` (0.25), `zones_threshold` (150k), `metro_radius_scale` (1.0), `core_frac` (0.35), `inner_frac` (0.40), `zone_density_mult`, `elev_amp_m` (350), `roughness_m_per_km` (6), `t_mean_c` (11), `t_north_gradient_c` (5), `t_season_amp_c` (11), `t_diurnal_amp_c` (4), `weather_sd_c` (3.5), `rain_prob` (0.12), `wind_sd_ms` (2.5) |
| `econ` | `year` (2026), `income_base` (24,000), `income_pop_exponent` (0.12), `elec_price_eur_kwh` (0.22), `fuel_price_eur_l` (1.75), `ev_subsidy_eur` (3,000), `chargers_per_10k_base` (4), `motorization_base` (0.45), adoption weights `ev_bias`, `w_income`, `w_home_charging`, `w_chargers`, `w_subsidy_per_1000`, `w_price_ratio`, `adoption_speed_per_year`, `max_ev_share`, `spatial_rho`, `spatial_scale_km`, `hc_density_mid` (2000) |
| `mobility` | `active_frac` (0.55), `trips_per_person_day` (2.2), `intercity_frac` (0.06), `commute_scale_km` (14), `intercity_gamma` (1.6), `attraction_mult`, `circuity_short/long` (1.45 / 1.18), `road_capacity_trips_km2_day` (6000), `road_capacity_density_exp` (0), `bpr_alpha`, `bpr_beta`, `rush_boost` (1.6) |
| `energy` | `fleet` (list of classes), `fleet_income_tilt`, `urban_free_kmh` / `arterial_kmh` / `highway_kmh` (38 / 62 / 112), `stops_per_km`, `highway_scale_km` (40), `aux_base_w` (350), `heat_w_per_deg` (110), `cool_w_per_deg` (90), `cold_battery_pen_per_c` (0.006), `age_degradation_per_year` (0.018), `noise_sigma` (0.05), `noise_short_trip_sigma` (0.10), `outlier_prob` (0.01) |
| `output` | `n_trips` (100,000), `temp_sensor_sd`, `missing_rate`, `split_strategy`, `split_fracs`, `drop_latent`, `min_samples_od_summary`, `fmt` (`csv`/`parquet`) |
| `charging` | See section 8.8 |

Top-level `seed` (default 42). CLI shortcuts: `--seed`, `--n-trips`, `--format`.

---

## 8. Charging-station placement environment

`evsim_charging.py`. Intended use: your algorithm reads `world.candidates`, decides which sites get a station and how big, calls `world.evaluate(...)`, and learns from the metrics or the scalar `score`.

### 8.1 Corridor network and candidate sites
- Cities are connected by a **minimum spanning tree plus `charging.knn` (2) nearest neighbours per city** (not real roads). Trips between cities follow shortest paths on this network (Floyd–Warshall).
- **City extent** = max over the city's zones of (distance from the centre + `city_extent_frac` × zone radius).
- **Candidate sites** are placed along every link every `candidate_spacing_km` (6 km), starting at half a spacing, and kept only if they are at least `city_extent + city_buffer_km` (5 km) from **every** city, so that stations are genuinely between cities. A station is one of these sites.
- A site can serve a trip if it lies within `detour_max_km` (4 km) of the route.

### 8.2 What a station is
A DataFrame with columns `site_id` (index into `world.candidates`), `n_ports` (1…`max_ports`, default max 40) and `power_kw` (per port). `n_ports` and `power_kw` are optional; defaults 8 ports and 150 kW. One station per site.

### 8.3 Candidate features (`candidates.csv`)
`site_id`, `edge_id`, `city_a`, `city_b` (link ends), `x`, `y`, `edge_frac` (0–1 along the link), `pos_km` (road km from `city_a`), `nearest_city`, `dist_nearest_city_km`, `grid_km` (distance beyond that city's extent; drives grid cost), `elev_m`, `t_mean_c`, `elec_price`, `grid_cost_eur` (site cost + grid cost), and the demand features derived from the generated trips: `flow_ev_day` (daily EV trips passing within the detour limit), `flow_need_day` (the part that cannot complete the trip without charging), `mean_trip_frac` (mean position along trips that pass by, 0 = start, 1 = end). `corridors.csv`: `edge_id`, `city_a`, `city_b`, `euclid_km`, `road_km`, `flow_ev_day`.

### 8.4 Driver simulation (per intercity trip)
Corridor trips are the sampled trips with `is_intercity = 1`. Each sample trip represents `W = Σ daily_ev_trips / n_trips × demand_multiplier` real trips per day.
1. Start SoC ~ N(0.85, 0.12), clipped 0.35–1. Usable battery = nominal × state of health.
2. The driver **plans** with consumption × (1 + `plan_margin`) × lognormal error (σ = 0.08) and keeps a reserve of `reserve_soc` (10%). If the planned consumption does not reach the destination with the reserve, a stop is needed.
3. The driver picks a station ahead within a random comfort fraction `U(comfort_min = 0.45, 1)` of the planned reach (the farthest such station, otherwise the full planned reach, otherwise the actual reach with no margin). Stations with an expected wait above `balk_wait_min` (15) are skipped if another is acceptable; otherwise the shortest-wait one is used.
4. The trip pays the detour (2 × distance to the site × `detour_circuity` 1.3), arrives with the remaining SoC, and charges to the energy needed plus `charge_buffer_soc` (5%), capped at `target_soc_max` (80%). Charge power = min(station kW, vehicle max kW) × `taper_eff` (0.78); vehicle max power by class (60 / 120 / 150 / 100 kW) is derated 1.2% per °C below 10 °C; plus 3 min plug-in overhead.
5. Repeat up to `max_stops` (6). If no station is reachable, the trip is **stranded** (`completed = 0`, `stranded_at_km`).

### 8.5 Queueing and feedback
- Per station and hour of day, arrivals (smoothed with a 0.25/0.5/0.25 kernel over neighbouring hours to remove sampling noise) are scaled by `W`. Service time is the mean charge time of arrivals in that hour.
- Each station-hour is an **M/M/c queue** (c = ports, Erlang-C mean wait). If the mean wait would exceed `max_wait_min` (90) the hour is treated as saturated: wait capped at 90 and the overflow share is reported as `blocked_share`.
- Driver choices use the previous iteration's waits; `congestion_iters` (3) rounds with damping 0.5. Reported wait for each charging event is taken from the final queue table.
- `world.evaluate(stations, iters=1)` gives uncongested demand (used by `autosize`).

### 8.6 Outputs of `evaluate` (also saved in `<out>/charging/`)
| Table | Columns |
|---|---|
| `station_usage.csv` | `site_id`, `edge_id`, `x`, `y`, `n_ports`, `power_kw`, `sessions_day`, `arrivals_day`, `energy_kwh_day`, `utilization` (mean busy-port share over 24 h), `peak_utilization`, `peak_offered_erlangs`, `mean_wait_min`, `max_hourly_wait_min`, `blocked_share`, `revenue_eur_day`, `margin_eur_day`, `capex_eur`, `annual_cost_eur`, `profit_eur_year`, `payback_years` |
| `station_hourly.csv` | `site_id`, `hour`, `arrivals_per_h`, `offered_erlangs`, `utilization`, `wait_min`, `blocked_share` |
| `charging_events.csv` | `trip_id`, `site_id`, `stop_no`, `pos_km`, `arrival_hour`, `soc_in`, `soc_out`, `energy_kwh`, `charge_min`, `wait_min`, `detour_km` |
| `trip_outcomes.csv` | `trip_id`, `origin_city`, `dest_city`, `distance_km`, `needs_charge`, `completed`, `stranded_at_km`, `n_stops`, `charge_min`, `wait_min`, `detour_km`, `kwh_charged`, `extra_time_min` |
| `corridor_summary.csv` | link columns plus `n_stations`, `max_gap_km` (largest gap between charging opportunities; city boundaries count as charging points), `energy_served_kwh_day` |
| `stations.csv` | the evaluated placement |
| `metrics.json` | `n_stations`, `n_ports`, `corridor_trips_day`, `trips_needing_charge_day`, `completion_rate`, `completion_rate_needing_charge`, `stranded_trips_day`, `charging_sessions_day`, `mean_stops_per_charging_trip`, `mean_wait_min`, `mean_detour_km`, `blocked_share`, `mean_utilization`, `max_corridor_gap_km`, `capex_eur`, `annual_cost_eur`, `margin_eur_year`, `network_profit_eur_year`, `time_cost_eur_year`, `stranded_cost_eur_year`, `score` |

Trip-level rows each represent `world.W` real daily trips; `*_day` quantities are already scaled to daily totals.

### 8.7 Economics and score
- **Capex** = `site_cost_eur` (60k) + `grid_cost_eur_per_km` (25k) × `grid_km` + `n_ports` × port cost (interpolated by `power_kw` from {50: 35k, 150: 85k, 350: 160k} EUR). **Annual cost** = capex × capital-recovery factor (6%, 12 years) + 4% of capex + 2,000 EUR per port.
- **Margin** = energy sold × (`sell_price_eur_kwh` 0.55 − local electricity price × `energy_cost_markup` 1.15).
- **Score** (to maximise) = margin/year − annual cost − time cost − stranded cost, where time cost = (wait + detour hours) × `value_of_time_eur_h` (18) and stranded cost = stranded trips/day × 365 × `stranded_cost_eur` (150). The components are in `metrics.json`; build your own reward if you prefer.

### 8.8 Baselines and sizing
| Name | Idea |
|---|---|
| `none` | no stations (lower bound) |
| `random` | random sites |
| `uniform` | stations spread evenly over links ∝ link length, ignoring flow |
| `flow` | rank sites by `flow_need_day`, enforce a 30 km minimum separation |
| `gapfill` | repeatedly add a station in the middle of the largest gap, on the link with the highest flow × gap |

`autosize(world, stations, target_util=0.6)` sets ports from the uncongested peak offered load (ports = peak Erlangs ÷ 0.6, within 1…`max_ports`). Power level stays a free decision variable. CLI: `--strategy`, `--n-stations`, `--ports`, `--power-kw`, `--stations-file`, `--autosize`, `--compare`, `--romania`. Output folders: `<out>/sim/` (the evsim dataset) and `<out>/charging/`.

Key `charging.*` parameters (defaults): `demand_multiplier` (0.3), `candidate_spacing_km` (6), `city_buffer_km` (5), `detour_max_km` (4), `knn` (2), `comfort_min` (0.45), `balk_wait_min` (15), `plan_margin` (0.10), `reserve_soc` (0.10), `target_soc_max` (0.80), `soc_start_mean` (0.85), `taper_eff` (0.78), `congestion_iters` (3), `arrival_smooth` (0.25), `max_wait_min` (90), `default_ports` (8), `default_power_kw` (150), `max_ports` (40), and the economic parameters above.

---

## 9. Romania

`evsim_romania.py` produces the same files from Romania's cities: real data where it could be found online, synthetic data for the rest. Data was collected on 2026-11-07.

### 9.1 Real inputs and sources
| Data | Value / use | Source |
|---|---|---|
| City list, county, 2021 census population, elevation | 120 localities ≥ 14.7k (table truncated at that size) | Wikipedia, [List of cities and towns in Romania](https://en.wikipedia.org/wiki/List_of_cities_and_towns_in_Romania) |
| Coordinates | 112 from GeoNames, 8 approximate (see 9.4) | GeoNames via the `geonamescache` package |
| Net wage per county, Jan 2026 | 42 units incl. Bucharest (INS data compiled by Economedia) | [economedia.ro](https://economedia.ro/?p=332146) |
| National average net wage 2025 | 5,266 lei/month (sets `income_base`) | [wall-street.ro](https://www.wall-street.ro/articol/economie-and-finante/prapastia-salariala-din-romania-cum-arata-topul-castigurilor-romanilor-in-2025) |
| EUR/RON | 5.3403 (BNR, 2 Nov 2026) | [cursbnr.nxm.ro](https://cursbnr.nxm.ro/data/02-11-2026) |
| Household electricity | 1.67 lei/kWh incl. VAT (central estimate, autumn 2026) | [alba24.ro](https://alba24.ro/facturi-mai-mari-la-energie-pretul-noilor-oferte-ar-putea-ajunge-la-167-lei-kwh-cat-ar-plati-in-plus-o-familie-1161501.html) |
| Petrol / diesel | 9.39 / 10.44 lei/l (31 Jul 2026); petrol used | [newsweek.ro](https://newsweek.ro/economie/soc-la-pompa-in-romania-motorina-a-ajuns-1044-leil-benzina-939-leil-gpl-ul-457-leil) |
| Battery EV fleet | over 75,000 (end Sep 2026) | [wall-street.ro](https://www.wall-street.ro/articol/auto/studiu-cate-puncte-de-incarcare-pentru-masini-electrice-are-romania-in-2026) |
| Public charging points | over 10,000 (5,010 DC, 5,060 AC; end Sep 2026) | same article |
| Passenger car fleet | 8,106,570 (end 2023) | [economica.net](https://www.economica.net/?p=722930) |
| BEVs by county, start 2024 | Bucharest 15,618, Cluj 2,415, Ilfov 1,968, total about 38,271 (used for validation only) | [automarket.ro](https://www.automarket.ro/stiri/cate-masini-electrice-sunt-inmatriculate-in-romania-cele-mai-multe-sunt-in-116863.html) |
| BEV brand split, July 2026 | Dacia 25.4%, Tesla 18.5% (informs fleet mix) | [wall-street.ro](https://www.wall-street.ro/articol/auto/analiza-romania-a-trecut-de-70000-de-masini-electrice-inmatriculate.html) |

All values, dates and URLs are also in `romania_data/ro_national_params.json` and in `sources.json` of each generated dataset.

### 9.2 How the Romanian nodes are built
1. **Cities**: keep localities with `pop2021 ≥ --min-pop` (default 15,000: 118 cities). Elevation ranges in the table ("110–170") use the midpoint. Elevation missing in the table (13 towns) is interpolated from the 5 nearest cities with elevation (inverse distance, weights 1/(d + 5 km)).
2. **Projection**: x,y in km from lat/lon, equirectangular at 45.8°N, origin at the south-west corner.
3. **Satellite towns merged into a parent city** as `outer` zones, keeping their real population and coordinates: Popești-Leordeni, Voluntari, Bragadiru, Pantelimon, Otopeni, Buftea, Chitila → Bucharest; Săcele, Codlea, Râșnov → Brașov; Năvodari → Constanța; Mioveni → Pitești; Cisnădie → Sibiu. Trips among them are local/commuter trips (same `city_id`). Result: 118 cities → 106 metros → 147 nodes, 8.34 M inhabitants.
4. **Zones of big cities**: a city with population ≥ `geo.zones_threshold` (150k) or with satellites gets `core` and `inner` zones (with satellites: core 46.7% / inner 53.3% of the parent's own population; without: the default 35/40 plus two synthetic outer nodes). Radius `R = 0.5 × sqrt(city_pop/1000)` km (22 km for Bucharest). Zone populations are real totals × synthetic split.
5. **Density and area**: synthetic law `900 × (pop/1e5)^0.2` people/km² times lognormal noise; zone multipliers as in the synthetic region. Bucharest keeps its approximate real area of 238 km² (the zone densities are rescaled to match; the area comes from general knowledge, not from a fetched source).
6. **Region**: NUTS-2 development region of the county. **Terrain roughness**: same formula as the synthetic region, with real elevation.
7. **Temperature**: `T = 35.3 − 0.53 × lat − 0.0065 × elev + urban heat island`, a regression fitted by hand to about 10 approximate city climate normals (general knowledge, not sourced). Season amplitude 12.5 °C, diurnal 5 °C, weather σ 4.5 °C, rain 14%.
8. **Income** = county net wage × 12 ÷ EUR/RON × zone multiplier × `(city_pop/1e5)^0.05` × lognormal(σ = 0.04). `income_base` = national average wage in EUR.
9. **Prices**: real national electricity and petrol prices, with 1% lognormal noise per node.
10. **Home charging, vehicles per capita**: synthetic formulas with Romania settings (`hc_density_mid` 1500, `motorization_base` 0.42, income exponent 0.5, no density effect). The model gives 0.44 vehicles per capita against 0.43 nationally.
11. **Public chargers**: shape as in 5.4, scaled so the total over the listed cities equals 85% of the real 10,000 points.
12. **EV adoption**: the standard model (5.5) with `ev_bias` found by bisection so that total BEVs in the listed cities equals 85% of the real 75,000 (63,750). The 85% (`--covered-share`) is an assumption.
13. **Other Romania settings**: highway speed 95 km/h and arterial 55 (few motorways), circuity long 1.25, 2.0 trips/person/day, intercity share 5%, road capacity ∝ density^0.7, fleet mix city 30% / sedan 25% / SUV 40% / van 5%.

### 9.3 Real vs synthetic, field by field
| Field | Origin |
|---|---|
| City list, county, population | Real (census 2021); zone populations are real total × synthetic split |
| Coordinates | Real (GeoNames) for city centres; 8 towns approximate; zone offsets synthetic |
| Elevation | Real for 100 cities (+5 range midpoints); 13 interpolated; zone offsets synthetic |
| Wages and prices | Real (county wage × synthetic modifier; national prices) |
| EV share, chargers | Model calibrated to real national totals |
| Density, area, zones, temperature, roughness, home charging, motorisation | Synthetic |
| Trips, flows, energy | Simulated |

### 9.4 Known data quirks (all documented in the provenance file)
- Eight towns are not in the GeoNames package: Călărași, Onești, Bragadiru, Otopeni, Chitila, Ștefănești, Vicovu de Sus and Câmpulung (Argeș). Their coordinates are from general knowledge (within a few km). A first run matched Câmpulung to the wrong town through an alternate name; matching now prefers exact primary names and refuses duplicate coordinates.
- Bucharest's area (238 km²) is approximate and unsourced.
- Towns below about 14.7k inhabitants are not in the data (the Wikipedia table was only retrieved down to that size), and `--min-pop` below 14,762 therefore has no extra effect.

### 9.5 Romania-specific files
| File | Content |
|---|---|
| `city_lookup.csv` | `node_id`, `city_id`, `name`, `county`, `region_name`, `lat`, `lon` |
| `data_provenance.csv` | per node: how `population`, `density_area`, `coords`, `elevation`, `income`, `temperature`, `prices`, `ev_share`, `chargers`, `vehicles_per_capita` were obtained (real / synthetic / calibrated) |
| `sources.json` | every real input with source, the calibration constants, and the list of unsourced assumptions |
| `validation.json` | model versus real checks (below) |

### 9.6 Validation (seed 1)
- Modelled BEVs in the listed cities: 63,750 (target 85% × 75,000). BEV share of the vehicle fleet in these cities: 1.7%.
- **Not tuned:** Bucharest holds 38.9% of the modelled BEVs against 40.8% in the real county data (early 2024). The model overshoots in the suburbs (Ilfov 13.1% vs 5.1% real; Cluj 9.6% vs 6.3%). Real shares are from a different year and whole counties, so these are plausibility checks.
- Climate: Constanța 12.2 °C, Iași 10.2, Timișoara 11.0, Cluj-Napoca 8.7, Suceava 8.3, Brașov 7.6.

### 9.7 Charging on Romania
`python evsim_charging.py --out ro_ch --romania --compare --autosize --n-stations 60`. The corridor network is still synthetic (MST + 2 nearest links: 145 links, 507 candidate sites), **not** the real road or motorway network. See section 13 for results.

---

## 10. Design decisions and lessons learned

**Simulator**
- Everything is dataclasses + JSON/`--set` overrides, so any parameter can be changed from the command line and the full config is stored with each dataset.
- Trips are sampled ∝ expected EV trips rather than uniformly over pairs, so the data reflects where EVs actually drive; the cost is that rare pairs are under-represented.
- Ground-truth internals are exported as `gt_*` columns (and can be dropped) so model errors can be diagnosed against known causes.
- Splits by group (city, OD pair, month) are built in because spatial generalisation is the realistic test.
- A zone structure (core / inner / outer) plus separate local and intercity gravity models was chosen to represent the commuter-belt problem and economic differences (richer, less dense suburbs adopt EVs more).
- **Road capacity vs density** (found with Romania): with constant capacity per km², Bucharest's core reached 4.6× capacity and speeds collapsed to 0.03 km/h, producing absurd consumption. Capacity now optionally scales with `density^road_capacity_density_exp` (default 0 so earlier datasets are unchanged; Romania uses 0.7, giving peak loads ≤ 0.75).

**Charging environment**
- Stations are limited to **discrete candidate sites** with ports and power as extra decision variables, so a placement is a simple table an ML model can output.
- `evaluate` is deterministic (random draws are fixed when the world is built), so placements can be compared fairly and optimised.
- **Herding fix**: if everyone stops at the farthest reachable station, a few hubs saturate. Drivers now stop within a random fraction of their reach (`comfort_min`).
- **Autosize circularity**: sizing from congested demand under-sizes stations because avoided stations look empty. Sizing uses the uncongested demand (`iters=1`).
- **Port cap 16 → 40, default ports 4 → 8, candidate spacing 10 → 6 km**: with 4–16 ports the busiest sites saturate (demand up to about 5,000 arrivals/day at one site against about 1,300 sessions/day for 16 ports); denser candidates let busy corridors host several stations.
- **`demand_multiplier` 1.0 → 0.3**: at full demand even using all 143 candidates (about 2,400 ports) left mean waits of about 36 min. 0.3 is a calibration knob, interpreted as the share of long-distance EV trips that depend on public fast charging. Raise it for growth or harder scenarios.
- Hourly arrivals are smoothed because each sample trip stands for about 16 real trips, which otherwise gives spiky profiles.
- More congestion iterations did **not** converge to a calmer state in the saturated regime (more stations became saturated), so the default is 3 damped iterations.
- `gapfill` initially stopped early because a loop iteration was consumed when an edge ran out of candidate sites; fixed.

**Romania**
- Wikipedia could not be fetched directly; the page was found through search results and fetched in chunks (first 120 rows, down to 14.7k inhabitants). Elevation APIs (Open-Meteo) were not reachable from the sandbox, so missing elevations are interpolated.
- County wages came from several news pages; the one used (Economedia, January 2026) listed all 42 units. Earlier pages listed only some counties.
- Satellite towns of the capital and a few large cities are merged as `outer` zones to avoid double counting with the synthetic belt and to make their commutes local flows.
- EV and charger counts are only available nationally (plus partial county data), so the per-city values come from the model and are calibrated to the national totals; partial county data are used only to validate.

---

## 11. Limitations

**General**
- A single-year snapshot: no time series, no vehicle histories, no trip chains (each trip is independent, one vehicle per trip), no mode choice or public transport, no weekend/holiday volume changes (only the hour distribution differs), months and weekdays equally likely.
- Gravity-model flows are plausible, not calibrated to observed OD data. Local flows are production-constrained only.
- The energy model is a simplified physics model (lumped fleet classes, fixed speeds per road type, constant stops per km, no tyre or battery temperature models beyond simple penalties). Distribution tails come from an injected 1% outlier process, not observed behaviour.
- Defaults are plausible, not calibrated to a specific country or real telemetry; calibrate before drawing real-world conclusions.
- Node count is small (tens to about 150), so n×n arrays are fine; very large regions would need sparse matrices.
- `od_energy_summary.csv` covers only well-sampled pairs and is computed from all splits.
- `distance_km` for intra-zone trips is an estimate (0.52 × √area), not a real route.

**Charging**
- Greenfield assumption: existing public chargers are not modelled on the corridors; charging inside cities (home, work, urban) is assumed available, and only intercity trips can need a stop.
- The corridor network (MST + nearest links) is not a real road network; trips between two cities use one shortest path and all stations are on straight links between city centres.
- A station can only be at a candidate site; one station per site; charging power is flat per port with a fixed average taper; no grid-capacity limits, price competition, brand loyalty, reservations or in-route re-planning after a full queue.
- Queues are M/M/c per hour of an average day; the sample hour distribution is the average over the year, so seasonal or weekend peaks are not separated.
- Driver behaviour uses simple rules and random parameters, not a learned or observed behaviour model. Stranded trips are counted but no recovery or rerouting is modelled.
- Everything in `charging.*` economics (prices, costs, VOT, stranded cost) is an assumption, not a sourced figure.

**Romania**
- Only localities ≥ `--min-pop` are included; rural and small-town traffic is missing; `covered_share` (0.85) is assumed.
- Per-city EV share, chargers, density, area, motorisation, temperature are modelled, not observed. Suburban EV shares are overestimated against the partial real data.
- `income` is the annual net wage per employee, which differs from the per-capita meaning used in the synthetic region.
- The unsourced assumptions listed in `sources.json` (circuity, speeds, fleet mix, motorisation, home-charging density midpoint, EV subsidy left at the simulator default 3,000 EUR) have not been verified for Romania.
- Charging on Romania uses the synthetic corridor network, not real roads, and the low EV share (1.7%) makes stations unprofitable in the default scenario (about −3 to −5 M EUR/year for 60 stations).

---

## 12. Reproducibility and runtime
- One master `seed` (default 42). The core simulator uses `default_rng(seed)` sequentially (nodes → trips → split → missing values). The charging world uses `default_rng(seed + 1000)`, Romanian node generation `default_rng(seed + 7)`. `place_random` takes its own `seed`.
- Same configuration and seed give identical files. The full configuration is in `metadata.json`.
- Timing (laptop-class CPU): about 5 s for the synthetic dataset with 100k trips; `trips.csv` is about 59 MB for 100k trips; one `evaluate` call 0.1–0.5 s; a `--compare` run of five strategies with autosize about 8–15 s. Writing parquet needs `pyarrow`.

---

## 13. Reference results

**Synthetic region** (defaults, seed 1, 100k trips): 66 nodes, 30 cities, 7.13 M inhabitants, 20.1% EV share of vehicles. Consumption mean 19.5 kWh/100 km (σ 6.3). Zone EV share: core 9%, inner 23%, outer 26%, town 9%. Consumption by temperature: 23.6 (below −5 °C), 21.1 (−5 to 5), 18.4 (5 to 15), 16.4 (15 to 25) kWh/100 km. By class: city 15.7, sedan 16.7, SUV 21.3, van 28.6. Intercity 24.4 vs local 19.2. `needs_charge` 1.9% of trips. Baseline GBM (origin-city holdout): R² 0.48, MAE 3.4.

**Charging, synthetic region** (seed 1, 143 candidate sites, 5,968 sampled intercity trips = 28,791 EV trips/day; with autosize):

| Stations | Strategy | Completion | Stranded trips/day |
|---|---|---|---|
| 0 | none | 62.4% | 10,835 |
| 40 | random / uniform / flow / gapfill | 95.9% / 96.7% / 97.1% / 95.9% | 1,172 / 950 / 830 / 1,187 |
| 80 | random / uniform / flow / gapfill | 97.2% / 97.2% / 96.5% / 97.2% | 820 / 815 / 994 / 810 |

A single 60-station `flow` + autosize run: 97.3% completion, 878 ports, mean wait 0.2 min, capex about 104 M EUR. Residual stranded trips are mostly small-battery cars and vans on long, cold or high-consumption trips.

**Romania** (seed 1, 100k trips): 147 nodes, 106 metros, 8.34 M inhabitants, 63,750 modelled BEVs in the cities (1.7% of fleet), no NaN or infinite values, consumption mean 17.2 kWh/100 km, average speed 45 km/h. Charging compare with 60 stations and autosize (507 candidate sites, 2,169 EV intercity trips/day): none 58.3% completion; flow 98.7% (28 stranded/day); uniform 96.2% (83/day); gapfill 96.2% (82/day).
