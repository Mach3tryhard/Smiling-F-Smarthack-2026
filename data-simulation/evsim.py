#!/usr/bin/env python3
"""
evsim - synthetic generator for EV mobility + energy-consumption data.

Pipeline
--------
1. Geography   : cities (rank-size law), large cities split into zones
                 (core / inner suburb / outer commuter belt), terrain, climate.
2. Economics   : income, energy prices, subsidies, public chargers,
                 home-charging access (falls with density).
3. EV adoption : logit model on economics + spatial spillover + time S-curve.
4. Mobility    : gravity model. Local (commuter) flows inside a metro area and
                 intercity flows are separate; congestion (BPR) feeds back on speeds.
5. Energy      : physics model per trip (rolling, aero, kinetic/regen, climb,
                 HVAC, battery temperature, vehicle class, driver, wind, rain)
                 + heteroscedastic noise + outliers.
6. Export      : nodes / od / trips / od_energy_summary + metadata.json.

Usage
-----
    python evsim.py --out data --n-trips 200000 --seed 1
    python evsim.py --out data --set econ.ev_subsidy=8000 --set geo.n_cities=60
    python evsim.py --print-default-config > my.json   # edit, then:
    python evsim.py --config my.json --out data
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field, asdict, fields, is_dataclass
from pathlib import Path

import numpy as np
import pandas as pd

__version__ = "1.0"
G = 9.81


# ----------------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------------
@dataclass
class GeoConfig:
    n_cities: int = 30
    region_km: float = 500.0              # side of the square region
    n_regions: int = 4                    # clusters of cities (economic/climate regions)
    region_spread: float = 0.12           # cluster std as fraction of region_km
    largest_city_pop: float = 1_800_000
    rank_size_exponent: float = 1.0       # Zipf exponent (higher = more primate)
    min_city_pop: float = 15_000
    base_density: float = 300.0           # people/km2 for a 100k city
    density_pop_exponent: float = 0.25    # bigger cities are denser
    zones_threshold: float = 150_000      # cities above this are split in zones
    metro_radius_scale: float = 1.0       # R[km] = scale * sqrt(pop/1000)
    core_frac: float = 0.35               # population share of the core
    inner_frac: float = 0.40              # inner suburbs; remainder = outer belt (2 nodes)
    zone_density_mult: dict = field(default_factory=lambda: {
        "core": 3.0, "inner": 1.0, "outer": 0.25, "town": 1.0})
    intra_zone_scale: float = 0.52        # mean intra-zone trip length = scale*sqrt(area)
    base_elev_m: float = 150.0
    elev_amp_m: float = 350.0             # terrain amplitude (sum of sinusoids)
    terrain_wavelength_km: float = 160.0
    roughness_m_per_km: float = 6.0       # mean rolling gain per km
    t_mean_c: float = 11.0                # mean annual temperature at y=0
    t_north_gradient_c: float = 5.0       # cooling from south(y=0) to north(y=region)
    t_season_amp_c: float = 11.0
    t_diurnal_amp_c: float = 4.0
    weather_sd_c: float = 3.5
    uhi_c_per_log_pop: float = 0.35       # urban heat island
    rain_prob: float = 0.12
    wind_sd_ms: float = 2.5


@dataclass
class EconConfig:
    year: int = 2026
    income_base: float = 24_000.0         # EUR/yr per capita at 100k pop
    income_pop_exponent: float = 0.12
    income_sigma: float = 0.12
    region_income_sd: float = 0.18
    zone_income_mult: dict = field(default_factory=lambda: {
        "core": 0.95, "inner": 1.10, "outer": 1.20, "town": 1.0})
    elec_price_eur_kwh: float = 0.22
    fuel_price_eur_l: float = 1.75
    price_region_sd: float = 0.10
    ice_l_per_100km: float = 7.0
    ev_subsidy_eur: float = 3000.0        # one-off purchase subsidy
    chargers_per_10k_base: float = 4.0
    motorization_base: float = 0.45       # vehicles per capita at income_base
    motorization_income_exp: float = 0.35
    motorization_density_exp: float = -0.08
    # adoption logit weights
    ev_bias: float = -2.6
    w_income: float = 0.9
    w_home_charging: float = 1.0
    w_chargers: float = 0.5
    w_subsidy_per_1000: float = 0.10
    w_price_ratio: float = 0.5            # fuel cost / electricity cost per km
    adoption_speed_per_year: float = 0.35  # logit shift per year after 2026
    max_ev_share: float = 0.90
    spatial_rho: float = 0.35             # weight of neighbour spillover
    spatial_scale_km: float = 60.0
    hc_density_mid: float = 2000.0        # density where home-charging access = 50%
    hc_steepness: float = 0.9


@dataclass
class MobilityConfig:
    active_frac: float = 0.55             # share of pop making car-trip chains
    trips_per_person_day: float = 2.2
    intercity_frac: float = 0.06
    commute_scale_km: float = 14.0        # local deterrence exp(-d/scale)
    intercity_gamma: float = 1.6          # intercity deterrence d^-gamma
    attraction_mult: dict = field(default_factory=lambda: {
        "core": 2.5, "inner": 1.0, "outer": 0.35, "town": 1.0})
    circuity_short: float = 1.45
    circuity_long: float = 1.18
    circuity_scale_km: float = 30.0
    road_capacity_trips_km2_day: float = 6000.0   # at 1000 people/km2
    road_capacity_density_exp: float = 0.0        # capacity ~ (density/1000)^exp; 0 = constant per km2
    bpr_alpha: float = 0.15
    bpr_beta: float = 4.0
    rush_boost: float = 1.6


@dataclass
class VehicleClass:
    name: str
    share: float
    mass_kg: float
    cda_m2: float
    crr: float
    battery_kwh: float
    eta_drive: float
    regen_eta: float
    premium: float                        # tilt toward rich areas
    heat_pump_prob: float


def _default_fleet():
    return [asdict(v) for v in [
        VehicleClass("city",   0.25, 1250, 0.60, 0.0085, 40, 0.88, 0.60, -0.5, 0.2),
        VehicleClass("sedan",  0.30, 1700, 0.62, 0.0080, 62, 0.90, 0.65,  0.0, 0.5),
        VehicleClass("suv",    0.35, 2100, 0.78, 0.0090, 78, 0.89, 0.62,  0.8, 0.6),
        VehicleClass("van",    0.10, 2400, 1.05, 0.0100, 70, 0.87, 0.55, -0.3, 0.1),
    ]]


@dataclass
class EnergyConfig:
    fleet: list = field(default_factory=_default_fleet)
    fleet_income_tilt: float = 0.8
    urban_free_kmh: float = 38.0
    arterial_kmh: float = 62.0
    highway_kmh: float = 112.0
    stops_per_km: dict = field(default_factory=lambda: {"urban": 2.4, "arterial": 0.5, "highway": 0.06})
    highway_scale_km: float = 40.0
    urban_density_mid: float = 1200.0
    driver_speed_sigma: float = 0.08
    driver_aggr_sigma: float = 0.12
    occupant_mass_kg: float = 78.0
    cargo_kg_mean: float = 25.0
    aux_base_w: float = 350.0
    heat_w_per_deg: float = 110.0         # cabin heating power per degC below 18
    cool_w_per_deg: float = 90.0
    cold_battery_pen_per_c: float = 0.006  # drivetrain efficiency loss per degC below 18
    wet_crr_boost: float = 0.15
    age_degradation_per_year: float = 0.018
    noise_sigma: float = 0.05
    noise_short_trip_sigma: float = 0.10  # extra noise for trips of few km
    outlier_prob: float = 0.01
    outlier_range: tuple = (1.3, 2.0)


@dataclass
class OutputConfig:
    n_trips: int = 100_000
    temp_sensor_sd: float = 0.7           # noise on the exported temperature feature
    missing_rate: float = 0.0             # NaN rate injected in noisy features
    missing_cols: list = field(default_factory=lambda: ["temp_c", "veh_age_years", "passengers"])
    split_strategy: str = "random"        # random | origin_city | od_pair | month
    split_fracs: tuple = (0.7, 0.15, 0.15)
    drop_latent: bool = False             # drop gt_* columns (ground truth internals)
    min_samples_od_summary: int = 5
    fmt: str = "csv"                      # csv | parquet


@dataclass
class ChargingConfig:
    # corridor network and candidate sites (used by evsim_charging.py)
    knn: int = 2                          # extra links per city beyond the spanning tree
    city_extent_frac: float = 0.6         # city extent = max(dist of zone + frac*zone radius)
    city_buffer_km: float = 5.0           # stations must be this far outside a city extent
    candidate_spacing_km: float = 6.0
    detour_max_km: float = 4.0            # max one-way distance route -> station
    detour_circuity: float = 1.3
    # driver behaviour
    soc_start_mean: float = 0.85
    soc_start_sd: float = 0.12
    soc_start_min: float = 0.35
    reserve_soc: float = 0.10             # fraction of usable battery kept in reserve
    plan_margin: float = 0.10             # drivers overestimate consumption by this much
    plan_error_sigma: float = 0.08        # lognormal error in the driver's estimate
    target_soc_max: float = 0.80          # DC fast charging stops at this SoC
    charge_buffer_soc: float = 0.05
    min_charge_kwh: float = 3.0
    comfort_min: float = 0.45             # driver stops within U(comfort_min,1) x of planned reach
    balk_wait_min: float = 15.0           # drivers skip stations with longer expected wait
    max_stops: int = 6
    # charging physics
    veh_max_kw: dict = field(default_factory=lambda: {"city": 60, "sedan": 120, "suv": 150, "van": 100})
    taper_eff: float = 0.78               # average / peak power over 10-80% SoC
    cold_derate_per_c: float = 0.012      # charge-power loss per degC below 10
    plug_overhead_min: float = 3.0
    # demand and queueing
    demand_multiplier: float = 0.3        # share of corridor EV trips that rely on public fast charging (calibration / growth knob)
    congestion_iters: int = 3
    arrival_smooth: float = 0.25          # smooths hourly arrival noise (weight on each neighbouring hour)
    max_wait_min: float = 90.0            # longer waits are counted as blocked
    # station defaults and sizing
    default_ports: int = 8
    default_power_kw: float = 150.0
    max_ports: int = 40
    # economics
    sell_price_eur_kwh: float = 0.55
    energy_cost_markup: float = 1.15      # x local electricity price
    site_cost_eur: float = 60_000
    grid_cost_eur_per_km: float = 25_000  # per km beyond the nearest city extent
    port_cost_eur: dict = field(default_factory=lambda: {"50": 35_000, "150": 85_000, "350": 160_000})
    opex_frac_of_capex: float = 0.04
    opex_eur_port_year: float = 2_000
    discount_rate: float = 0.06
    lifetime_years: int = 12
    days_per_year: int = 365
    value_of_time_eur_h: float = 18.0
    stranded_cost_eur: float = 150.0      # per stranded trip (tow, lost time)


@dataclass
class Config:
    seed: int = 42
    geo: GeoConfig = field(default_factory=GeoConfig)
    econ: EconConfig = field(default_factory=EconConfig)
    mobility: MobilityConfig = field(default_factory=MobilityConfig)
    energy: EnergyConfig = field(default_factory=EnergyConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    charging: ChargingConfig = field(default_factory=ChargingConfig)


def _from_dict(cls, d):
    kw = {}
    for f in fields(cls):
        if f.name in d:
            v = d[f.name]
            sub = f.type if not isinstance(f.type, str) else globals().get(f.type)
            kw[f.name] = _from_dict(sub, v) if (sub is not None and is_dataclass(sub) and isinstance(v, dict)) else v
    return cls(**kw)


def load_config(path=None, overrides=()) -> Config:
    cfg = _from_dict(Config, json.loads(Path(path).read_text())) if path else Config()
    for item in overrides:
        key, _, raw = item.partition("=")
        try:
            val = json.loads(raw)
        except json.JSONDecodeError:
            val = raw
        obj = cfg
        parts = key.split(".")
        for p in parts[:-1]:
            obj = getattr(obj, p)
        if not hasattr(obj, parts[-1]):
            raise SystemExit(f"Unknown parameter: {key}")
        if isinstance(getattr(obj, parts[-1]), tuple) and isinstance(val, list):
            val = tuple(val)
        setattr(obj, parts[-1], val)
    return cfg


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------
def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def zscore(x):
    s = np.std(x)
    return (x - np.mean(x)) / (s if s > 0 else 1.0)


# ----------------------------------------------------------------------------
# 1+2. Geography and economics
# ----------------------------------------------------------------------------
def build_nodes(cfg: Config, rng) -> pd.DataFrame:
    g, e = cfg.geo, cfg.econ
    n = g.n_cities
    centres = rng.uniform(0.15, 0.85, (g.n_regions, 2)) * g.region_km
    region = rng.integers(0, g.n_regions, n)
    xy = np.clip(centres[region] + rng.normal(0, g.region_spread * g.region_km, (n, 2)), 0, g.region_km)

    ranks = np.arange(1, n + 1)
    pops = np.maximum(g.largest_city_pop / ranks ** g.rank_size_exponent, g.min_city_pop)
    pops = rng.permutation(pops * rng.lognormal(0, 0.08, n))

    # terrain: sum of random sinusoids
    K = rng.normal(0, 2 * np.pi / g.terrain_wavelength_km, (5, 2))
    PH = rng.uniform(0, 2 * np.pi, 5)

    def elevation(p):
        return np.maximum(g.base_elev_m + (g.elev_amp_m / np.sqrt(5)) * np.sin(p @ K.T + PH).sum(1), 0.0)

    region_income = rng.lognormal(0, e.region_income_sd, g.n_regions)
    region_elec = rng.lognormal(0, e.price_region_sd, g.n_regions)
    region_fuel = rng.lognormal(0, e.price_region_sd * 0.5, g.n_regions)

    rows = []
    for c in range(n):
        pop = pops[c]
        base_dens = g.base_density * (pop / 1e5) ** g.density_pop_exponent * rng.lognormal(0, 0.25)
        if pop >= g.zones_threshold:
            R = g.metro_radius_scale * np.sqrt(pop / 1000.0)
            rest = 1 - g.core_frac - g.inner_frac
            f = rng.uniform(0.4, 0.6)
            zones = [("core", 0.0, g.core_frac), ("inner", 0.5 * R, g.inner_frac),
                     ("outer", R, rest * f), ("outer", R, rest * (1 - f))]
        else:
            zones = [("town", 0.0, 1.0)]
        for zi, (zt, rad, frac) in enumerate(zones):
            ang = rng.uniform(0, 2 * np.pi)
            p = xy[c] + rad * np.array([np.cos(ang), np.sin(ang)])
            zpop = pop * frac
            dens = base_dens * g.zone_density_mult[zt] * rng.lognormal(0, 0.1)
            rows.append(dict(
                node_id=len(rows), city_id=c, zone_type=zt, region=int(region[c]),
                x=p[0], y=p[1], city_pop=pop, pop=zpop, density=dens, area_km2=zpop / dens,
            ))
    df = pd.DataFrame(rows)

    P = df[["x", "y"]].to_numpy()
    df["elev_m"] = elevation(P)
    df["roughness_m_km"] = g.roughness_m_per_km * rng.lognormal(0, 0.4, len(df)) * (1 + df["elev_m"] / 800)
    df["t_mean_c"] = (g.t_mean_c - g.t_north_gradient_c * df["y"] / g.region_km
                      - 6.5e-3 * df["elev_m"] + g.uhi_c_per_log_pop * np.log10(df["city_pop"] / 1e4))

    # economics
    zmult = df["zone_type"].map(e.zone_income_mult).to_numpy()
    df["income"] = (e.income_base * (df["city_pop"] / 1e5) ** e.income_pop_exponent
                    * region_income[df["region"]] * zmult * rng.lognormal(0, e.income_sigma, len(df)))
    df["elec_price"] = e.elec_price_eur_kwh * region_elec[df["region"]]
    df["fuel_price"] = e.fuel_price_eur_l * region_fuel[df["region"]]
    df["home_charging"] = sigmoid(-e.hc_steepness * np.log(df["density"] / e.hc_density_mid))
    df["chargers_per_10k"] = (e.chargers_per_10k_base * (df["income"] / e.income_base) ** 0.8
                              * (df["city_pop"] / 1e5) ** 0.1 * rng.lognormal(0, 0.3, len(df)))
    df["vehicles_per_capita"] = np.clip(
        e.motorization_base * (df["income"] / e.income_base) ** e.motorization_income_exp
        * (df["density"] / 1000) ** e.motorization_density_exp, 0.10, 0.85)
    return df


def ev_adoption(df: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    e = cfg.econ
    P = df[["x", "y"]].to_numpy()
    d = np.linalg.norm(P[:, None] - P[None], axis=-1)
    price_ratio = (df["fuel_price"] * e.ice_l_per_100km) / (df["elec_price"] * 17.0)  # EUR/100km ratio
    logit = (e.ev_bias
             + e.w_income * zscore(np.log(df["income"]))
             + e.w_home_charging * (df["home_charging"] - 0.5) * 2
             + e.w_chargers * zscore(np.log(df["chargers_per_10k"]))
             + e.w_subsidy_per_1000 * e.ev_subsidy_eur / 1000
             + e.w_price_ratio * zscore(np.log(price_ratio))
             + e.adoption_speed_per_year * (e.year - 2026)).to_numpy()
    W = np.exp(-d / e.spatial_scale_km)
    np.fill_diagonal(W, 0)
    W /= W.sum(1, keepdims=True) + 1e-12
    logit = (1 - e.spatial_rho) * logit + e.spatial_rho * (W @ logit)
    df["ev_share"] = e.max_ev_share * sigmoid(logit)
    df["n_vehicles"] = df["pop"] * df["vehicles_per_capita"]
    df["n_evs"] = df["n_vehicles"] * df["ev_share"]
    return df


# ----------------------------------------------------------------------------
# 3. Mobility (gravity, local commuter + intercity)
# ----------------------------------------------------------------------------
def build_od(df: pd.DataFrame, cfg: Config) -> dict:
    m, g = cfg.mobility, cfg.geo
    n = len(df)
    P = df[["x", "y"]].to_numpy()
    d = np.linalg.norm(P[:, None] - P[None], axis=-1)
    intra = np.maximum(g.intra_zone_scale * np.sqrt(df["area_km2"].to_numpy()), 1.0)
    d[np.arange(n), np.arange(n)] = intra
    circ = m.circuity_long + (m.circuity_short - m.circuity_long) * np.exp(-d / m.circuity_scale_km)
    road = d * circ

    city = df["city_id"].to_numpy()
    same = city[:, None] == city[None]
    pop = df["pop"].to_numpy()
    O = pop * m.active_frac * m.trips_per_person_day
    A_loc = pop * df["zone_type"].map(m.attraction_mult).to_numpy()

    # local / commuter flows
    wl = A_loc[None] * np.exp(-road / m.commute_scale_km) * same
    Tl = O[:, None] * (1 - m.intercity_frac) * wl / wl.sum(1, keepdims=True)
    # intercity
    wi = pop[None] * (road + 10.0) ** (-m.intercity_gamma) * (~same)
    s = wi.sum(1, keepdims=True)
    Ti = np.where(s > 0, O[:, None] * m.intercity_frac * wi / np.maximum(s, 1e-12), 0.0)
    T = Tl + Ti

    # congestion (BPR-like) per node: vehicle trips touching the node / capacity
    cap = m.road_capacity_trips_km2_day * (df["density"].to_numpy() / 1000.0) ** m.road_capacity_density_exp
    load = (T.sum(0) + T.sum(1) - np.diag(T)) / (cap * df["area_km2"].to_numpy())
    speed_factor = 1.0 / (1.0 + m.bpr_alpha * load ** m.bpr_beta)
    return dict(dist=d, road=road, T=T, same=same, load=load, speed_factor=speed_factor)


# ----------------------------------------------------------------------------
# 4. Trip sampling and energy physics
# ----------------------------------------------------------------------------
def sample_trips(df: pd.DataFrame, od: dict, cfg: Config, rng) -> pd.DataFrame:
    en, geo, mob, out = cfg.energy, cfg.geo, cfg.mobility, cfg.output
    n = len(df)
    N = out.n_trips

    # --- which OD pair: proportional to daily EV trips ---
    w = od["T"] * df["ev_share"].to_numpy()[:, None]
    w = w.ravel() / w.sum()
    idx = rng.choice(w.size, size=N, p=w)
    o, d_ = idx // n, idx % n
    O, D = df.iloc[o].reset_index(drop=True), df.iloc[d_].reset_index(drop=True)
    road = od["road"][o, d_]
    eucl = od["dist"][o, d_]
    local = od["same"][o, d_]

    # --- time ---
    weekday = rng.integers(0, 7, N)
    is_wd = weekday < 5
    mix = rng.random(N)
    hour = np.where(mix < 0.35, rng.normal(8, 1.2, N), np.where(mix < 0.70, rng.normal(17.5, 1.5, N),
                                                              rng.uniform(6, 22, N)))
    hour = np.where(is_wd & local, hour, rng.uniform(7, 22, N)) % 24
    month = rng.integers(1, 13, N)
    doy = (month - 0.5) * 30.4
    peak = np.clip(np.exp(-0.5 * ((hour - 8) / 1.5) ** 2) + np.exp(-0.5 * ((hour - 17.5) / 1.7) ** 2), 0, 1) * is_wd

    # --- weather ---
    t_mid = 0.5 * (O["t_mean_c"].to_numpy() + D["t_mean_c"].to_numpy())
    T = (t_mid - geo.t_season_amp_c * np.cos(2 * np.pi * (doy - 200) / 365)
         - geo.t_diurnal_amp_c * np.cos(2 * np.pi * (hour - 15) / 24)
         + rng.normal(0, geo.weather_sd_c, N))
    rain = rng.random(N) < geo.rain_prob
    wind = rng.normal(0, geo.wind_sd_ms, N)                          # headwind component (signed)
    elev_o, elev_d = O["elev_m"].to_numpy(), D["elev_m"].to_numpy()
    rho = 1.225 * 288.15 / (T + 273.15) * np.exp(-0.5 * (elev_o + elev_d) / 8500)

    # --- vehicle ---
    fleet = pd.DataFrame(en.fleet)
    inc_rel = (0.5 * (O["income"].to_numpy() + D["income"].to_numpy()) / cfg.econ.income_base)
    logp = np.log(fleet["share"].to_numpy())[None] + en.fleet_income_tilt * np.log(inc_rel)[:, None] * fleet["premium"].to_numpy()[None]
    pr = np.exp(logp - logp.max(1, keepdims=True))
    pr /= pr.sum(1, keepdims=True)
    cls = (rng.random(N)[:, None] > pr.cumsum(1)).sum(1).clip(0, len(fleet) - 1)
    V = fleet.iloc[cls].reset_index(drop=True)
    age = rng.gamma(2.0, 1.6, N)
    soh = np.clip(1 - en.age_degradation_per_year * age, 0.6, 1)
    heat_pump = rng.random(N) < V["heat_pump_prob"].to_numpy()
    passengers = 1 + rng.binomial(3, np.where(local & (hour < 9.5) & is_wd, 0.08, 0.28))
    mass = (V["mass_kg"].to_numpy() + passengers * en.occupant_mass_kg
            + rng.exponential(en.cargo_kg_mean, N))

    # --- driver ---
    drv_speed = rng.lognormal(0, en.driver_speed_sigma, N)
    aggr = np.clip(1 + 2.0 * (drv_speed - 1) + rng.normal(0, en.driver_aggr_sigma, N), 0.6, 1.8)

    # --- road mix ---
    hw = 0.9 * (1 - np.exp(-road / en.highway_scale_km)) * np.where(local, 0.4, 1.0)
    hw = np.clip(hw * (1 + rng.normal(0, 0.1, N)), 0, 0.95)
    rest = 1 - hw
    dens_mean = np.sqrt(O["density"].to_numpy() * D["density"].to_numpy())
    u = np.clip(sigmoid(1.2 * (np.log(dens_mean) - np.log(en.urban_density_mid))) + rng.normal(0, 0.08, N), 0, 1)
    f_urb, f_art, f_hw = rest * u, rest * (1 - u), hw

    # --- congestion & speeds ---
    sf0 = 0.5 * (od["speed_factor"][o] + od["speed_factor"][d_])
    load = 0.5 * (od["load"][o] + od["load"][d_])
    vc = load * (0.4 + mob.rush_boost * peak)
    sf = 1.0 / (1.0 + mob.bpr_alpha * vc ** mob.bpr_beta)
    v_urb = en.urban_free_kmh * sf * drv_speed
    v_art = en.arterial_kmh * (1 - 0.5 * (1 - sf)) * drv_speed
    v_hw = en.highway_kmh * (1 - 0.3 * (1 - sf)) * drv_speed

    # --- physics ---
    cda, crr = V["cda_m2"].to_numpy(), V["crr"].to_numpy() * (1 + en.wet_crr_boost * rain)
    eta, regen = V["eta_drive"].to_numpy(), V["regen_eta"].to_numpy()
    cold = 1 + en.cold_battery_pen_per_c * np.maximum(0, 18 - T)
    aged = 1 + 0.15 * (1 - soh)

    def seg(frac, v_kmh, stops, shelter):
        v = v_kmh / 3.6
        vair = np.maximum(v + wind * shelter, 0.0)
        f_roll = crr * mass * G
        f_aero = 0.5 * rho * cda * vair ** 2 * aggr
        f_kin = stops / 1000 * 0.5 * mass * (1.3 * v) ** 2 * (1 - regen) * aggr
        wh_km = (f_roll + f_aero + f_kin) / 3.6 / eta
        return wh_km * frac * road / 1000, frac * road / v_kmh      # kWh, hours

    e_u, t_u = seg(f_urb, v_urb, en.stops_per_km["urban"], 0.3)
    e_a, t_a = seg(f_art, v_art, en.stops_per_km["arterial"], 0.7)
    e_h, t_h = seg(f_hw, v_hw, en.stops_per_km["highway"], 1.0)
    flat = (e_u + e_a + e_h)

    rough = 0.5 * (O["roughness_m_km"].to_numpy() + D["roughness_m_km"].to_numpy())
    dh = elev_d - elev_o
    up = np.maximum(dh, 0) + rough * road / 2
    down = np.maximum(-dh, 0) + rough * road / 2
    climb_kwh = mass * G * up / eta / 3.6e6
    regen_kwh = mass * G * down * regen * eta / 3.6e6
    drive = np.maximum((flat + climb_kwh - regen_kwh) * cold * aged, 0.25 * flat)

    hours = t_u + t_a + t_h
    heat_cop = np.where(heat_pump, np.clip(2.4 + 0.07 * T, 1.0, 3.5), 1.0)
    p_hvac = (en.heat_w_per_deg * np.maximum(0, 18 - T) / heat_cop
              + en.cool_w_per_deg * np.maximum(0, T - 23) / 2.8)
    hvac = p_hvac * hours / 1000
    aux = en.aux_base_w * hours / 1000
    kwh_true = drive + hvac + aux

    sigma = en.noise_sigma + en.noise_short_trip_sigma * np.exp(-road / 8.0)
    noise = rng.lognormal(-0.5 * sigma ** 2, sigma)
    outl = rng.random(N) < en.outlier_prob
    noise = np.where(outl, noise * rng.uniform(*en.outlier_range, N), noise)
    kwh = kwh_true * noise

    elec = 0.5 * (O["elec_price"].to_numpy() + D["elec_price"].to_numpy())
    trips = pd.DataFrame(dict(
        trip_id=np.arange(N),
        origin=O["node_id"], dest=D["node_id"],
        origin_city=O["city_id"], dest_city=D["city_id"],
        origin_zone=O["zone_type"], dest_zone=D["zone_type"],
        is_intercity=(~local).astype(int),
        distance_km=road, euclid_km=eucl,
        origin_pop=O["pop"], dest_pop=D["pop"],
        origin_density=O["density"], dest_density=D["density"],
        origin_income=O["income"], dest_income=D["income"],
        origin_ev_share=O["ev_share"], dest_ev_share=D["ev_share"],
        origin_elev_m=elev_o, dest_elev_m=elev_d, delta_elev_m=dh,
        hour=hour, weekday=weekday, month=month,
        temp_c=T + rng.normal(0, out.temp_sensor_sd, N), rain=rain.astype(int),
        congestion_index=vc,
        veh_class=V["name"], veh_mass_kg=V["mass_kg"], veh_battery_kwh=V["battery_kwh"],
        veh_age_years=age, heat_pump=heat_pump.astype(int), passengers=passengers,
        elec_price=elec,
        # targets
        energy_kwh=kwh,
        consumption_kwh_100km=kwh / road * 100,
        duration_min=hours * 60,
        avg_speed_kmh=road / hours,
        cost_eur=kwh * elec,
        needs_charge=(kwh > 0.8 * V["battery_kwh"].to_numpy() * soh).astype(int),
        # latent ground truth
        gt_energy_noisefree_kwh=kwh_true, gt_drive_kwh=drive, gt_hvac_kwh=hvac,
        gt_climb_net_kwh=climb_kwh - regen_kwh, gt_driver_aggr=aggr, gt_wind_ms=wind,
        gt_frac_highway=f_hw, gt_true_temp_c=T, gt_is_outlier=outl.astype(int),
    ))
    return trips


# ----------------------------------------------------------------------------
# 5. Post-processing and export
# ----------------------------------------------------------------------------
def assign_split(trips: pd.DataFrame, out: OutputConfig, rng) -> np.ndarray:
    ftr, fva, fte = out.split_fracs
    N = len(trips)
    label = np.array(["train", "val", "test"])

    def by_group(keys):
        u = pd.unique(keys)
        u = rng.permutation(u)
        k1, k2 = int(len(u) * ftr), int(len(u) * (ftr + fva))
        m = {g: ("train" if i < k1 else "val" if i < k2 else "test") for i, g in enumerate(u)}
        return np.array([m[k] for k in keys])

    s = out.split_strategy
    if s == "random":
        r = rng.random(N)
        return label[(r > ftr).astype(int) + (r > ftr + fva).astype(int)]
    if s == "origin_city":
        return by_group(trips["origin_city"].to_numpy())
    if s == "od_pair":
        return by_group((trips["origin"] * 10_000 + trips["dest"]).to_numpy())
    if s == "month":
        return by_group(trips["month"].to_numpy())
    raise SystemExit(f"unknown split_strategy {s}")


def od_summary(trips: pd.DataFrame, min_n: int) -> pd.DataFrame:
    g = trips.groupby(["origin", "dest"])
    s = g.agg(n=("energy_kwh", "size"), distance_km=("distance_km", "mean"),
              kwh_mean=("energy_kwh", "mean"), kwh_std=("energy_kwh", "std"),
              c100_mean=("consumption_kwh_100km", "mean"), c100_std=("consumption_kwh_100km", "std"),
              c100_p10=("consumption_kwh_100km", lambda x: x.quantile(0.1)),
              c100_p50=("consumption_kwh_100km", "median"),
              c100_p90=("consumption_kwh_100km", lambda x: x.quantile(0.9)))
    return s[s["n"] >= min_n].reset_index()


def write(df, path: Path, fmt):
    if fmt == "parquet":
        df.to_parquet(path.with_suffix(".parquet"), index=False)
    else:
        df.to_csv(path.with_suffix(".csv"), index=False)


def run(cfg: Config, outdir: str | None = None, quiet=False, nodes_override: pd.DataFrame | None = None):
    """nodes_override: use a prebuilt node table (same schema as build_nodes), e.g. real-city data."""
    rng = np.random.default_rng(cfg.seed)
    base = build_nodes(cfg, rng) if nodes_override is None else nodes_override.copy()
    nodes = ev_adoption(base, cfg)
    od = build_od(nodes, cfg)
    trips = sample_trips(nodes, od, cfg, rng)
    trips["split"] = assign_split(trips, cfg.output, rng)

    if cfg.output.missing_rate > 0:
        for c in cfg.output.missing_cols:
            trips.loc[rng.random(len(trips)) < cfg.output.missing_rate, c] = np.nan
    if cfg.output.drop_latent:
        trips = trips.drop(columns=[c for c in trips.columns if c.startswith("gt_")])

    n = len(nodes)
    ii, jj = np.meshgrid(np.arange(n), np.arange(n), indexing="ij")
    od_df = pd.DataFrame(dict(origin=ii.ravel(), dest=jj.ravel(), road_km=od["road"].ravel(),
                              daily_trips=od["T"].ravel(),
                              daily_ev_trips=(od["T"] * nodes["ev_share"].to_numpy()[:, None]).ravel(),
                              same_city=od["same"].ravel().astype(int)))
    nodes["congestion_load"] = od["load"]
    nodes["speed_factor"] = od["speed_factor"]
    summ = od_summary(trips, cfg.output.min_samples_od_summary)

    if outdir:
        p = Path(outdir)
        p.mkdir(parents=True, exist_ok=True)
        write(nodes, p / "nodes", cfg.output.fmt)
        write(od_df, p / "od", cfg.output.fmt)
        write(trips, p / "trips", cfg.output.fmt)
        write(summ, p / "od_energy_summary", cfg.output.fmt)
        (p / "metadata.json").write_text(json.dumps(
            dict(version=__version__, config=asdict(cfg),
                 targets=["energy_kwh", "consumption_kwh_100km", "duration_min", "avg_speed_kmh",
                          "cost_eur", "needs_charge"],
                 latent_prefix="gt_"), indent=2, default=str))
    if not quiet:
        print(f"nodes={len(nodes)}  cities={nodes.city_id.nunique()}  trips={len(trips)}  "
              f"od_pairs_in_summary={len(summ)}")
        print(f"population={nodes['pop'].sum():,.0f}  EV share (pop-weighted)="
              f"{(nodes['n_evs'].sum() / nodes['n_vehicles'].sum()):.1%}")
        print(trips[["distance_km", "consumption_kwh_100km", "avg_speed_kmh"]].describe().round(2).to_string())
    return nodes, od_df, trips, summ


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", help="JSON config file")
    ap.add_argument("--set", action="append", default=[], metavar="section.key=value",
                    help="override a parameter (JSON value), e.g. econ.ev_subsidy=8000")
    ap.add_argument("--out", help="output directory")
    ap.add_argument("--seed", type=int)
    ap.add_argument("--n-trips", type=int)
    ap.add_argument("--format", choices=["csv", "parquet"])
    ap.add_argument("--print-default-config", action="store_true")
    a = ap.parse_args(argv)
    if a.print_default_config:
        print(json.dumps(asdict(Config()), indent=2))
        return
    cfg = load_config(a.config, a.set)
    if a.seed is not None:
        cfg.seed = a.seed
    if a.n_trips:
        cfg.output.n_trips = a.n_trips
    if a.format:
        cfg.output.fmt = a.format
    run(cfg, a.out)


if __name__ == "__main__":
    main()
