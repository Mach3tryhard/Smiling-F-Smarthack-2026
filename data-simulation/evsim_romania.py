#!/usr/bin/env python3
"""
evsim_romania - Romanian version of the simulator: real data where it could be found,
synthetic data for the rest, same output format as evsim.

REAL (collected from the web, see romania_data/ and sources.json)
  * city list, county, 2021 census population, elevation (major cities)  - Wikipedia
  * coordinates                                                          - GeoNames (geonamescache)
  * average net wage per county (Jan 2026)                               - INS via Economedia
  * national totals: BEV fleet, public charging points, passenger-car fleet,
    electricity price, fuel price, EUR/RON                               - news / BNR
SYNTHETIC (generated with the evsim models, clearly flagged in data_provenance.csv)
  * zones inside big cities (core / inner / outer belt), densities and areas
  * elevation of cities missing from the table (interpolated), terrain roughness
  * temperature climatology, home-charging access, motorisation
  * per-city EV share and public chargers: model calibrated so that the national totals
    match the real figures
  * all trips and energy consumption (physics model)

Usage
-----
    python evsim_romania.py --out romania --n-trips 100000 --seed 1
    python evsim_romania.py --out romania --min-pop 30000 --set mobility.intercity_frac=0.08
"""
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd

import evsim
from evsim import Config

DATA = Path(__file__).parent / "romania_data"

# development regions (NUTS-2) by county - official administrative grouping
REGIONS = {
    "Nord-Vest": ["Bihor", "Bistrița-Năsăud", "Cluj", "Maramureș", "Satu Mare", "Sălaj"],
    "Centru": ["Alba", "Brașov", "Covasna", "Harghita", "Mureș", "Sibiu"],
    "Nord-Est": ["Bacău", "Botoșani", "Iași", "Neamț", "Suceava", "Vaslui"],
    "Sud-Est": ["Brăila", "Buzău", "Constanța", "Galați", "Tulcea", "Vrancea"],
    "Sud-Muntenia": ["Argeș", "Călărași", "Dâmbovița", "Giurgiu", "Ialomița", "Prahova", "Teleorman"],
    "București-Ilfov": ["București", "Ilfov"],
    "Sud-Vest Oltenia": ["Dolj", "Gorj", "Mehedinți", "Olt", "Vâlcea"],
    "Vest": ["Arad", "Caraș-Severin", "Hunedoara", "Timiș"],
}
COUNTY_REGION = {c: i for i, (_, cs) in enumerate(REGIONS.items()) for c in cs}

# towns that are part of a larger city's urban area -> modelled as 'outer' zones of the parent
METRO_CHILDREN = {
    "Bucharest": ["Popești-Leordeni", "Voluntari", "Bragadiru", "Pantelimon", "Otopeni", "Buftea", "Chitila"],
    "Brașov": ["Săcele", "Codlea", "Râșnov"],
    "Constanța": ["Năvodari"],
    "Pitești": ["Mioveni"],
    "Sibiu": ["Cisnădie"],
}
CHILD_PARENT = {c: p for p, cs in METRO_CHILDREN.items() for c in cs}

# not in geonamescache: approximate coordinates from general knowledge (+-3 km), flagged in provenance
MANUAL_COORDS = {
    "Călărași": (44.2008, 27.3306), "Onești": (46.2500, 26.7667), "Bragadiru": (44.3667, 25.9833),
    "Otopeni": (44.5500, 26.0667), "Chitila": (44.5000, 25.9833), "Ștefănești": (44.8667, 24.9500),
    "Vicovu de Sus": (47.9333, 25.6833), "Câmpulung": (45.2667, 25.0500),
}
ALIAS = {"Reghin": "Reghin-Sat"}
AREA_OVERRIDE_KM2 = {"Bucharest": 238.0}     # approximate administrative area (general knowledge)

# synthetic urban density law: people/km2 = A * (pop/1e5)^B   (city-average, administrative area)
DENS_A, DENS_B = 900.0, 0.20


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    return re.sub(r"[^a-z0-9]", "", "".join(c for c in s if not unicodedata.combining(c)).lower())


# ----------------------------------------------------------------------------
# real data loading
# ----------------------------------------------------------------------------
def _coords_table(cities: pd.DataFrame) -> pd.DataFrame:
    cache = DATA / "ro_city_coords.csv"
    if cache.exists():
        return pd.read_csv(cache)
    import geonamescache                                   # pip install geonamescache
    gc = [v for v in geonamescache.GeonamesCache().get_cities().values() if v["countrycode"] == "RO"]
    idx = {}
    for v in gc:
        for n in [v["name"]] + v["alternatenames"]:
            idx.setdefault(_norm(n), []).append(v)
    rows = []
    for r in cities.itertuples():
        if r.city in MANUAL_COORDS:
            lat, lon = MANUAL_COORDS[r.city]
            rows.append((r.city, lat, lon, "approximate (general knowledge; not in GeoNames cache)"))
            continue
        c = idx.get(_norm(ALIAS.get(r.city, r.city)))
        if not c:
            raise SystemExit(f"no coordinates for {r.city}")
        exact = [v for v in c if _norm(v["name"]) == _norm(ALIAS.get(r.city, r.city))]
        c = exact or c                                    # prefer primary-name matches over alternate names
        v = min(c, key=lambda v: abs(np.log(max(v["population"], 1) / r.pop2021)))
        rows.append((r.city, v["latitude"], v["longitude"], "GeoNames"))
    out = pd.DataFrame(rows, columns=["city", "lat", "lon", "coord_src"])
    dup = out[out.duplicated(["lat", "lon"], keep=False)]
    if len(dup):
        raise SystemExit(f"duplicate coordinates for {dup.city.tolist()}: add MANUAL_COORDS entries")
    out.to_csv(cache, index=False)
    return out


def load_cities(min_pop: float) -> pd.DataFrame:
    df = pd.read_csv(DATA / "ro_cities_wikipedia_2021.csv", dtype={"elevation_m": str})
    df = df[df.pop2021 >= min_pop].reset_index(drop=True)
    df = df.merge(_coords_table(pd.read_csv(DATA / "ro_cities_wikipedia_2021.csv")), on="city", how="left")

    def parse(e):
        if pd.isna(e) or str(e).strip() == "":
            return np.nan
        return float(np.mean([float(p) for p in re.split(r"[–-]", str(e)) if p.strip()]))

    df["elev"] = df.elevation_m.map(parse)
    df["elev_src"] = np.where(df.elev.isna(), "interpolated (synthetic)",
                              np.where(df.elevation_m.astype(str).str.contains("–"),
                                       "Wikipedia (range midpoint)", "Wikipedia"))
    lat0, lon0 = df.lat.min() - 0.1, df.lon.min() - 0.1
    df["x"] = (df.lon - lon0) * 111.32 * np.cos(np.radians(45.8))
    df["y"] = (df.lat - lat0) * 110.57
    # fill missing elevations by inverse-distance weighting of the 5 nearest known cities
    known = df[df.elev.notna()]
    for i in df.index[df.elev.isna()]:
        d = np.hypot(known.x - df.x[i], known.y - df.y[i]).to_numpy()
        k = np.argsort(d)[:5]
        w = 1 / (d[k] + 5.0)
        df.loc[i, "elev"] = float(np.sum(w * known.elev.to_numpy()[k]) / w.sum())
    df["parent"] = df.city.map(CHILD_PARENT)
    return df


# ----------------------------------------------------------------------------
# configuration for Romania
# ----------------------------------------------------------------------------
def romania_config(overrides=()) -> tuple[Config, dict]:
    P = json.loads((DATA / "ro_national_params.json").read_text())
    fx = P["eur_ron"]["value"]
    cfg = Config()
    e, g, m, en = cfg.econ, cfg.geo, cfg.mobility, cfg.energy
    e.year = 2026
    e.elec_price_eur_kwh = P["electricity_household_ron_kwh"]["value"] / fx           # real
    e.fuel_price_eur_l = P["petrol_ron_l"]["value"] / fx                              # real
    e.income_base = P["net_wage_national_ron_month"]["value"] * 12 / fx               # real (annual net wage, EUR)
    e.price_region_sd = 0.01
    e.motorization_base, e.motorization_income_exp, e.motorization_density_exp = 0.42, 0.5, 0.0   # assumption
    e.hc_density_mid = 1500.0                                                         # assumption: many blocks of flats
    g.t_season_amp_c, g.t_diurnal_amp_c, g.weather_sd_c, g.rain_prob = 12.5, 5.0, 4.5, 0.14      # assumption
    g.metro_radius_scale = 0.5
    m.circuity_long, m.trips_per_person_day, m.intercity_frac = 1.25, 2.0, 0.05      # assumption
    m.road_capacity_density_exp = 0.7                                                 # denser cities have denser road networks
    en.highway_kmh, en.arterial_kmh = 95.0, 55.0                                      # assumption: few motorways
    fleet = {f["name"]: f for f in en.fleet}
    for name, share in dict(city=0.30, sedan=0.25, suv=0.40, van=0.05).items():     # informed by BEV brand split
        fleet[name]["share"] = share
    for item in overrides:
        evsim.load_config  # keep import used
        key, _, raw = item.partition("=")
        try:
            val = json.loads(raw)
        except json.JSONDecodeError:
            val = raw
        obj = cfg
        parts = key.split(".")
        for p_ in parts[:-1]:
            obj = getattr(obj, p_)
        setattr(obj, parts[-1], val)
    return cfg, P


# ----------------------------------------------------------------------------
# node construction (same schema as evsim.build_nodes)
# ----------------------------------------------------------------------------
def build_nodes_ro(cfg: Config, cities: pd.DataFrame, P: dict, rng, covered_share=0.85):
    g, e = cfg.geo, cfg.econ
    fx = P["eur_ron"]["value"]
    wages = pd.read_csv(DATA / "ro_county_wages_2026_01.csv").set_index("county").net_wage_ron_month
    lat0 = cities.lat.min() - 0.1; lon0 = cities.lon.min() - 0.1

    def to_ll(x, y):
        return lat0 + y / 110.57, lon0 + x / (111.32 * np.cos(np.radians(45.8)))

    def town_density(pop):
        return DENS_A * (pop / 1e5) ** DENS_B

    kids_of = {}
    for r in cities[cities.parent.notna()].itertuples():
        if r.parent in set(cities.city):
            kids_of.setdefault(r.parent, []).append(r)
    top = cities[~cities.parent.isin(cities.city)].reset_index(drop=True)   # standalone cities + metro parents

    rows, look, prov = [], [], []

    def add(city_id, zt, name, county, region, x, y, city_pop, pop, dens, elev, srcs):
        nid = len(rows)
        lat, lon = to_ll(x, y)
        rows.append(dict(node_id=nid, city_id=city_id, zone_type=zt, region=region, x=x, y=y,
                         city_pop=city_pop, pop=pop, density=dens, area_km2=pop / dens, elev_m=elev))
        look.append(dict(node_id=nid, city_id=city_id, name=name, county=county,
                         region_name=list(REGIONS)[region], lat=lat, lon=lon))
        prov.append(dict(node_id=nid, name=name, **srcs))

    for city_id, p in enumerate(top.itertuples()):
        kids = kids_of.get(p.city, [])
        county = p.county
        region = COUNTY_REGION[county]
        city_pop = p.pop2021 + sum(k.pop2021 for k in kids)
        zoned = bool(kids) or p.pop2021 >= g.zones_threshold
        base_src = dict(coords=p.coord_src, elevation=p.elev_src)
        if not zoned:
            add(city_id, "town", p.city, county, region, p.x, p.y, city_pop, p.pop2021,
                town_density(p.pop2021) * rng.lognormal(0, 0.15), p.elev,
                dict(population="real (census 2021, Wikipedia)", density_area="synthetic (density law)",
                     coords=p.coord_src, elevation=p.elev_src))
            continue
        R = g.metro_radius_scale * np.sqrt(city_pop / 1000.0)
        if kids:
            fc, fi = g.core_frac / (g.core_frac + g.inner_frac), g.inner_frac / (g.core_frac + g.inner_frac)
            zones = [("core", 0.0, fc), ("inner", 0.5 * R, fi)]
        else:
            rest = 1 - g.core_frac - g.inner_frac
            f = rng.uniform(0.4, 0.6)
            zones = [("core", 0.0, g.core_frac), ("inner", 0.5 * R, g.inner_frac),
                     ("outer", R, rest * f), ("outer", R, rest * (1 - f))]
        D = town_density(p.pop2021) * rng.lognormal(0, 0.15)
        mult = g.zone_density_mult
        dsrc = "synthetic (density law)"
        if p.city in AREA_OVERRIDE_KM2:                      # keep the known total area
            D = sum(p.pop2021 * fr / mult[zt] for zt, _, fr in zones) / AREA_OVERRIDE_KM2[p.city]
            dsrc = "approximate real area (general knowledge) + synthetic zone split"
        for zt, rad, fr in zones:
            ang = rng.uniform(0, 2 * np.pi)
            x, y = p.x + rad * np.cos(ang), p.y + rad * np.sin(ang)
            add(city_id, zt, p.city if zt == "core" else f"{p.city} ({zt})", county, region, x, y, city_pop,
                p.pop2021 * fr, D * mult[zt] * rng.lognormal(0, 0.08), p.elev + (0 if zt == "core" else rng.normal(0, 8)),
                dict(population="real total (census 2021) x synthetic zone split",
                     density_area=dsrc, coords="synthetic offset from real centre" if zt != "core" else p.coord_src,
                     elevation=p.elev_src if zt == "core" else "synthetic offset from real centre"))
        for k in kids:
            add(city_id, "outer", k.city, k.county, COUNTY_REGION[k.county], k.x, k.y, city_pop, k.pop2021,
                town_density(k.pop2021) * rng.lognormal(0, 0.1), k.elev,
                dict(population="real (census 2021, Wikipedia)", density_area="synthetic (density law)",
                     coords=k.coord_src, elevation=k.elev_src))

    df = pd.DataFrame(rows)
    lk = pd.DataFrame(look)
    pv = pd.DataFrame(prov)

    # ---- attributes shared by all nodes ----
    df["roughness_m_km"] = g.roughness_m_per_km * rng.lognormal(0, 0.4, len(df)) * (1 + df.elev_m / 800)
    lat = lk.lat.to_numpy()
    df["t_mean_c"] = 35.3 - 0.53 * lat - 0.0065 * df.elev_m + g.uhi_c_per_log_pop * np.log10(df.city_pop / 1e4)
    wage = lk.county.map(wages).to_numpy()
    df["income"] = (wage * 12 / fx * df.zone_type.map(e.zone_income_mult).to_numpy()
                    * (df.city_pop / 1e5) ** 0.05 * rng.lognormal(0, 0.04, len(df)))
    df["elec_price"] = e.elec_price_eur_kwh * rng.lognormal(0, e.price_region_sd, len(df))
    df["fuel_price"] = e.fuel_price_eur_l * rng.lognormal(0, e.price_region_sd, len(df))
    df["home_charging"] = evsim.sigmoid(-e.hc_steepness * np.log(df.density / e.hc_density_mid))
    shape = (df.income / e.income_base) ** 0.8 * (df.city_pop / 1e5) ** 0.1 * rng.lognormal(0, 0.3, len(df))
    target_points = P["public_charging_points"]["value"] * covered_share
    e.chargers_per_10k_base = target_points / float((shape * df["pop"] / 1e4).sum())     # calibration
    df["chargers_per_10k"] = e.chargers_per_10k_base * shape
    df["vehicles_per_capita"] = np.clip(
        e.motorization_base * (df.income / e.income_base) ** e.motorization_income_exp
        * (df.density / 1000) ** e.motorization_density_exp, 0.10, 0.85)

    # ---- calibrate EV adoption so the national BEV fleet matches the real figure ----
    target_ev = P["bev_fleet"]["value"] * covered_share
    lo, hi = -15.0, 5.0
    for _ in range(40):
        e.ev_bias = 0.5 * (lo + hi)
        n_ev = evsim.ev_adoption(df.copy(), cfg).n_evs.sum()
        lo, hi = (e.ev_bias, hi) if n_ev < target_ev else (lo, e.ev_bias)
    pv["density_area"] = pv.density_area
    pv["income"] = "real county net wage (INS, Jan 2026) x synthetic city/zone modifier"
    pv["temperature"] = "synthetic climatology (lat/elevation regression)"
    pv["prices"] = "real national (electricity, petrol) with 1% synthetic noise"
    pv["ev_share"] = "model calibrated to real national BEV fleet"
    pv["chargers"] = "model calibrated to real national public charging points"
    pv["vehicles_per_capita"] = "synthetic (calibrated assumption)"
    meta = dict(covered_share=covered_share, target_bev=target_ev, target_charging_points=target_points,
                ev_bias=e.ev_bias, chargers_per_10k_base=e.chargers_per_10k_base)
    return df, lk, pv, meta


# ----------------------------------------------------------------------------
# top level
# ----------------------------------------------------------------------------
def setup(overrides=(), min_pop=15000, seed=42, covered_share=0.85):
    """Return (cfg, nodes, city_lookup, provenance, meta, sources) ready for evsim.run / the charging world."""
    cfg, P = romania_config(overrides)
    cfg.seed = seed
    cities = load_cities(min_pop)
    nodes, lk, pv, meta = build_nodes_ro(cfg, cities, P, np.random.default_rng(seed + 7), covered_share)
    return cfg, nodes, lk, pv, meta, P


def generate(outdir, n_trips=100_000, seed=42, min_pop=15000, overrides=(), covered_share=0.85, quiet=False):
    cfg, nodes, lk, pv, meta, P = setup(overrides, min_pop, seed, covered_share)
    cfg.output.n_trips = n_trips
    out = Path(outdir)
    nodes_o, od_df, trips, summ = evsim.run(cfg, str(out), quiet=quiet, nodes_override=nodes)
    lk.to_csv(out / "city_lookup.csv", index=False)
    pv.to_csv(out / "data_provenance.csv", index=False)
    (out / "sources.json").write_text(json.dumps(dict(real_inputs=P, calibration=meta,
                                                      assumptions_not_sourced=ASSUMPTIONS), indent=2, ensure_ascii=False))
    # validation against the partial real EV distribution (start of 2024)
    n = nodes_o.merge(lk[["node_id", "name", "county"]], on="node_id")
    tot = n.n_evs.sum()
    bz = n[n.county == "București"].n_evs.sum() / tot
    il = n[n.county == "Ilfov"].n_evs.sum() / tot
    cj = n[n.county == "Cluj"].n_evs.sum() / tot
    real = P["bev_by_county_2024"]
    val = dict(
        model_total_bev_in_cities=float(tot), real_total_bev_2026=P["bev_fleet"]["value"],
        model_vehicles_per_capita=float(nodes_o.n_vehicles.sum() / nodes_o["pop"].sum()),
        model_share_bev_of_cities_fleet=float(tot / nodes_o.n_vehicles.sum()),
        model_share_of_bevs_bucharest=float(bz), real_share_bucharest_2024=real["București"] / real["_total_2024"],
        model_share_of_bevs_ilfov=float(il), real_share_ilfov_2024=real["Ilfov"] / real["_total_2024"],
        model_share_of_bevs_cluj=float(cj), real_share_cluj_2024=real["Cluj"] / real["_total_2024"],
        note="real shares are from early 2024 and cover whole counties; model shares are 2026 and cover listed cities")
    (out / "validation.json").write_text(json.dumps(val, indent=2))
    if not quiet:
        print(f"\nRomania: {nodes_o.city_id.nunique()} cities/metros, {len(nodes_o)} nodes, "
              f"{nodes_o['pop'].sum():,.0f} inhabitants, {len(trips)} trips")
        print(json.dumps({k: (round(v, 4) if isinstance(v, float) else v) for k, v in val.items() if k != "note"}, indent=2))
    return cfg, nodes_o, od_df, trips, summ


ASSUMPTIONS = [
    "covered_share: 85% of national BEVs and public charging points assumed to be in the listed cities",
    "motorisation_base 0.42, income exponent 0.5, no density effect",
    "home-charging density midpoint 1,500 people/km2",
    "season/diurnal/weather temperature spread, rain probability",
    "circuity 1.25-1.45, 2.0 trips/person/day, 5% intercity share, road capacity ~ density^0.7",
    "average highway speed 95 km/h and arterial 55 km/h (few motorways)",
    "fleet class mix city 30% / sedan 25% / SUV 40% / van 5% (informed by BEV brand split)",
    "EV purchase subsidy left at the simulator default (3,000 EUR); not sourced for Romania",
    "urban density law 900*(pop/1e5)^0.2 people/km2; Bucharest area 238 km2 from general knowledge",
    "8 small towns have approximate coordinates from general knowledge (flagged)",
]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True)
    ap.add_argument("--n-trips", type=int, default=100_000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--min-pop", type=float, default=15000)
    ap.add_argument("--covered-share", type=float, default=0.85)
    ap.add_argument("--set", action="append", default=[], metavar="section.key=value")
    a = ap.parse_args(argv)
    generate(a.out, a.n_trips, a.seed, a.min_pop, a.set, a.covered_share)


if __name__ == "__main__":
    main()
