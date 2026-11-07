#!/usr/bin/env python3
"""
evsim_charging - charging-station placement environment on top of evsim.

What it does
------------
1. Builds a corridor network between cities (spanning tree + k nearest links).
2. Generates CANDIDATE SITES along those corridors, outside every city, each with
   data-derived features (EV flow passing by, flow that needs charging, distance to
   the nearest city, grid cost, elevation, temperature, ...).
3. Evaluates ANY choice of stations (a subset of candidate sites, each with n_ports
   and power_kw): simulates every intercity EV trip with battery state, charging
   stops, detours, queueing (Erlang-C with congestion feedback) and economics.
4. Returns usage tables, network metrics and a scalar `score` that an external
   optimiser / ML model can maximise. Baseline placers are provided for comparison.

Python API
----------
    import evsim, evsim_charging as ec
    cfg = evsim.load_config(overrides=["geo.n_cities=40"])
    world = ec.build_world(cfg)                  # runs evsim and builds the network
    world.candidates                              # DataFrame: features per candidate site
    stations = ec.place_gapfill(world, 40)        # or your ML model's choice:
    #   DataFrame with columns site_id, n_ports, power_kw
    res = world.evaluate(stations)
    res.metrics["score"]; res.tables["station_usage"]

CLI
---
    python evsim_charging.py --out out --strategy gapfill --n-stations 40 --autosize
    python evsim_charging.py --out out --stations-file my_stations.csv
    python evsim_charging.py --out out --compare --n-stations 40
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

import evsim
from evsim import Config


# ----------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------
def _circ(d, m):
    return m.circuity_long + (m.circuity_short - m.circuity_long) * np.exp(-d / m.circuity_scale_km)


def _erlang_wait_h(c: int, a: float, svc_h: float) -> float:
    """Mean wait (hours) in an M/M/c queue with offered load a (Erlangs), service time svc_h."""
    if a <= 0:
        return 0.0
    if a >= c:
        return np.inf
    B = 1.0
    for k in range(1, c + 1):          # Erlang-B recursion
        B = a * B / (k + a * B)
    C = B / (1 - (a / c) * (1 - B))
    return C * svc_h / (c - a)


class Result:
    def __init__(self, stations, metrics, tables):
        self.stations, self.metrics, self.tables = stations, metrics, tables

    def save(self, outdir):
        p = Path(outdir)
        p.mkdir(parents=True, exist_ok=True)
        self.stations.to_csv(p / "stations.csv", index=False)
        for k, v in self.tables.items():
            v.to_csv(p / f"{k}.csv", index=False)
        (p / "metrics.json").write_text(json.dumps(self.metrics, indent=2, default=float))


# ----------------------------------------------------------------------------
# world
# ----------------------------------------------------------------------------
class ChargingWorld:
    def __init__(self, cfg: Config, nodes, od_df, trips, rng):
        self.cfg, self.nodes, self.od_df, self.trips = cfg, nodes, od_df, trips
        self._build_network()
        self._build_candidates()
        self._build_trips(rng)
        self._build_routes()
        self._candidate_features()

    # ---- network between cities ----
    def _build_network(self):
        ch, m = self.cfg.charging, self.cfg.mobility
        nodes = self.nodes
        n = int(nodes.city_id.max()) + 1
        self.n_cities = n
        centre = np.zeros((n, 2)); extent = np.zeros(n); price = np.zeros(n)
        elev = np.zeros(n); temp = np.zeros(n)
        for c, g in nodes.groupby("city_id"):
            a = g[g.zone_type.isin(["core", "town"])].iloc[0]
            centre[c] = (a.x, a.y)
            dist = np.hypot(g.x - a.x, g.y - a.y)
            rad = np.sqrt(g.area_km2 / np.pi)
            extent[c] = (dist + ch.city_extent_frac * rad).max()
            price[c], elev[c], temp[c] = a.elec_price, a.elev_m, a.t_mean_c
        self.centre, self.extent, self.city_price, self.city_elev, self.city_temp = centre, extent, price, elev, temp

        d = np.linalg.norm(centre[:, None] - centre[None], axis=-1)
        edges = set()
        in_tree = np.zeros(n, bool); in_tree[0] = True
        best, parent = d[0].copy(), np.zeros(n, int)
        for _ in range(n - 1):
            b = np.where(in_tree, np.inf, best)
            j = int(np.argmin(b))
            edges.add((min(parent[j], j), max(parent[j], j)))
            in_tree[j] = True
            upd = d[j] < best
            best[upd], parent[upd] = d[j][upd], j
        for i in range(n):
            for j in np.argsort(d[i])[1:1 + ch.knn]:
                edges.add((min(i, j), max(i, j)))
        E = np.array(sorted(edges))
        self.edges = pd.DataFrame(dict(edge_id=np.arange(len(E)), city_a=E[:, 0], city_b=E[:, 1]))
        self.edges["euclid_km"] = d[E[:, 0], E[:, 1]]
        self.edges["road_km"] = self.edges.euclid_km * _circ(self.edges.euclid_km, m)
        self.edge_of = {(a, b): i for i, (a, b) in enumerate(E)}
        self.edge_of.update({(b, a): i for i, (a, b) in enumerate(E)})

        # all-pairs shortest paths (Floyd-Warshall with next hop)
        L = np.full((n, n), np.inf); np.fill_diagonal(L, 0)
        nxt = np.full((n, n), -1)
        for (a, b), r in zip(E, self.edges.road_km):
            L[a, b] = L[b, a] = r
            nxt[a, b], nxt[b, a] = b, a
        for k in range(n):
            alt = L[:, k, None] + L[None, k, :]
            better = alt < L
            L = np.where(better, alt, L)
            nxt = np.where(better, nxt[:, k, None], nxt)
        self.path_len, self._nxt = L, nxt

    def _path(self, a, b):
        p = [a]
        while p[-1] != b:
            p.append(int(self._nxt[p[-1], b]))
        return p

    # ---- candidate sites ----
    def _build_candidates(self):
        ch, m = self.cfg.charging, self.cfg.mobility
        rows = []
        for e in self.edges.itertuples():
            A, B = self.centre[e.city_a], self.centre[e.city_b]
            ts = np.arange(ch.candidate_spacing_km / 2, e.euclid_km, ch.candidate_spacing_km)
            if len(ts) == 0:
                continue
            P = A + (B - A) * (ts / e.euclid_km)[:, None]
            dc = np.linalg.norm(P[:, None] - self.centre[None], axis=-1)
            gap = dc - self.extent[None] - ch.city_buffer_km
            keep = (gap >= 0).all(1)
            for t, p, g, dd in zip(ts[keep], P[keep], gap[keep], dc[keep]):
                near = int(np.argmin(dd))
                f = t / e.euclid_km
                rows.append(dict(
                    edge_id=e.edge_id, city_a=e.city_a, city_b=e.city_b, x=p[0], y=p[1],
                    edge_frac=f, pos_km=t * e.road_km / e.euclid_km,
                    nearest_city=near, dist_nearest_city_km=dd[near],
                    grid_km=dd[near] - self.extent[near],
                    elev_m=(1 - f) * self.city_elev[e.city_a] + f * self.city_elev[e.city_b],
                    t_mean_c=(1 - f) * self.city_temp[e.city_a] + f * self.city_temp[e.city_b],
                    elec_price=self.city_price[near]))
        if not rows:
            raise SystemExit("No candidate sites: reduce charging.city_buffer_km / candidate_spacing_km")
        c = pd.DataFrame(rows)
        c.insert(0, "site_id", np.arange(len(c)))
        c["grid_cost_eur"] = ch.site_cost_eur + ch.grid_cost_eur_per_km * c.grid_km
        self.candidates = c

    # ---- corridor trips ----
    def _build_trips(self, rng):
        ch, en = self.cfg.charging, self.cfg.energy
        t = self.trips[self.trips.is_intercity == 1].reset_index(drop=True)
        n = len(t)
        self.corridor = t
        self.n_trips = n
        age = t.veh_age_years.fillna(t.veh_age_years.median())
        soh = np.clip(1 - en.age_degradation_per_year * age, 0.6, 1)
        self.usable = t.veh_battery_kwh.to_numpy() * soh.to_numpy()
        self.D = t.distance_km.to_numpy()
        self.energy = t.energy_kwh.to_numpy()
        self.ek = self.energy / self.D
        temp = t.temp_c.fillna(10.0).to_numpy()
        vmax = t.veh_class.map(ch.veh_max_kw).fillna(100.0).to_numpy()
        self.veh_kw = vmax * np.clip(1 - ch.cold_derate_per_c * np.maximum(0, 10 - temp), 0.4, 1)
        self.hour0 = t.hour.to_numpy()
        self.speed = t.avg_speed_kmh.to_numpy()
        self.soc0 = np.clip(rng.normal(ch.soc_start_mean, ch.soc_start_sd, n), ch.soc_start_min, 1.0)
        self.plan = (1 + ch.plan_margin) * np.exp(rng.normal(0, ch.plan_error_sigma, n))
        self.W = self.od_df.daily_ev_trips.sum() / len(self.trips) * ch.demand_multiplier  # daily trips per sample trip
        self.comfort = rng.uniform(ch.comfort_min, 1.0, n)
        self.needs = self.energy > (ch.soc_start_mean - ch.reserve_soc) * self.usable

    def _build_routes(self):
        ch = self.cfg.charging
        t = self.corridor
        code = (t.origin_city * self.n_cities + t.dest_city).to_numpy()
        uniq, inv = np.unique(code, return_inverse=True)
        self.od_of_trip = inv
        n_od = len(uniq)
        C = self.candidates[["x", "y"]].to_numpy()
        nc = len(C)
        self.od_dist = np.full((n_od, nc), np.inf)
        self.od_frac = np.zeros((n_od, nc))
        self.od_edges = []
        for k, cd in enumerate(uniq):
            a, b = divmod(int(cd), self.n_cities)
            path = self._path(a, b)
            self.od_edges.append([self.edge_of[(u, v)] for u, v in zip(path[:-1], path[1:])])
            pts = self.centre[path]
            seg = np.diff(pts, axis=0)
            sl = np.linalg.norm(seg, axis=1)
            cum = np.concatenate([[0], np.cumsum(sl)])
            tot = cum[-1]
            for s in range(len(seg)):
                v = seg[s]
                tt = np.clip(((C - pts[s]) @ v) / (v @ v), 0, 1)
                dist = np.linalg.norm(C - (pts[s] + tt[:, None] * v), axis=1)
                better = dist < self.od_dist[k]
                self.od_dist[k, better] = dist[better]
                self.od_frac[k, better] = (cum[s] + tt[better] * sl[s]) / tot
        self.od_cnt = np.bincount(inv, minlength=n_od).astype(float)
        self.od_cnt_need = np.bincount(inv, weights=self.needs.astype(float), minlength=n_od)

    def _candidate_features(self):
        ch = self.cfg.charging
        reach = (self.od_dist <= ch.detour_max_km).astype(float)
        c = self.candidates
        c["flow_ev_day"] = (reach.T @ self.od_cnt) * self.W
        c["flow_need_day"] = (reach.T @ self.od_cnt_need) * self.W
        ef = np.zeros(len(self.edges))
        for k, es in enumerate(self.od_edges):
            for e in es:
                ef[e] += self.od_cnt[k] * self.W
        self.edges["flow_ev_day"] = ef
        # candidate "median position along the trip" of the flow it can serve
        c["mean_trip_frac"] = (reach * self.od_frac * self.od_cnt[:, None]).sum(0) / np.maximum(
            (reach * self.od_cnt[:, None]).sum(0), 1)

    # ---- capex ----
    def station_costs(self, st: pd.DataFrame) -> pd.DataFrame:
        ch = self.cfg.charging
        keys = np.array(sorted(float(k) for k in ch.port_cost_eur))
        vals = np.array([ch.port_cost_eur[str(int(k)) if str(int(k)) in ch.port_cost_eur else str(k)] for k in keys])
        port = np.interp(st.power_kw, keys, vals)
        capex = self.candidates.grid_cost_eur.to_numpy()[st.site_id.to_numpy()] + st.n_ports * port
        r, n = ch.discount_rate, ch.lifetime_years
        crf = r / (1 - (1 + r) ** -n) if r > 0 else 1 / n
        annual = capex * crf + capex * ch.opex_frac_of_capex + st.n_ports * ch.opex_eur_port_year
        return pd.DataFrame(dict(capex_eur=capex, annual_cost_eur=annual))

    # ---- simulation ----
    def _prep_stations(self, stations):
        ch = self.cfg.charging
        st = stations.copy().reset_index(drop=True)
        if "n_ports" not in st:
            st["n_ports"] = ch.default_ports
        if "power_kw" not in st:
            st["power_kw"] = ch.default_power_kw
        st["site_id"] = st.site_id.astype(int)
        if st.site_id.duplicated().any():
            raise ValueError("duplicate site_id in stations")
        if len(st) and (st.site_id.min() < 0 or st.site_id.max() >= len(self.candidates)):
            raise ValueError("site_id outside candidate range")
        st["n_ports"] = st.n_ports.clip(1, ch.max_ports).astype(int)
        return st

    def _simulate(self, st, lists, wait):
        ch = self.cfg.charging
        n = self.n_trips
        kw = st.power_kw.to_numpy(float)
        completed = np.ones(n, bool)
        strand_km = np.full(n, np.nan)
        ev = []
        for i in range(n):
            order, frac, det = lists[self.od_of_trip[i]]
            D, ek, U = self.D[i], self.ek[i], self.usable[i]
            ekp = ek * self.plan[i]
            res = U * ch.reserve_soc
            e, pos, clock, spd = self.soc0[i] * U, 0.0, self.hour0[i], self.speed[i]
            pk = frac * D
            stops = 0
            while e - ekp * (D - pos) < res:
                if stops >= ch.max_stops or len(order) == 0:
                    completed[i], strand_km[i] = False, min(pos + max(e, 0) / ek, D)
                    break
                ahead = pk > pos + 0.5
                need = (pk - pos) + det
                ok = ahead & (need * ekp <= self.comfort[i] * (e - res))
                if not ok.any():
                    ok = ahead & (need * ekp <= e - res)
                if not ok.any():
                    ok = ahead & (need * ek <= e)
                    if not ok.any():
                        completed[i], strand_km[i] = False, min(pos + max(e, 0) / ek, D)
                        break
                chosen, best, bestw = -1, -1, np.inf
                for j in np.nonzero(ok)[0][::-1]:
                    w = wait[order[j], int((clock + (pk[j] - pos) / spd) % 24)]
                    if w <= ch.balk_wait_min:
                        chosen = j
                        break
                    if w < bestw:
                        best, bestw = j, w
                j = chosen if chosen >= 0 else best
                s = order[j]
                drive = need[j]
                e -= ek * drive
                clock += drive / spd
                hr = int(clock % 24)
                soc_in = e / U
                tgt = min(ch.target_soc_max * U, max(e, ekp * (D - pk[j]) + res + ch.charge_buffer_soc * U))
                kwh = max(tgt - e, 0.0)
                pos = pk[j]
                stops += 1
                if kwh < 0.1:
                    continue
                svc_h = kwh / (min(kw[s], self.veh_kw[i]) * ch.taper_eff) + ch.plug_overhead_min / 60
                clock += wait[s, hr] / 60 + svc_h
                e += kwh
                ev.append((i, s, stops, pos, hr, soc_in, e / U, kwh, svc_h * 60, det[j]))
        cols = ["trip", "st", "stop_no", "pos_km", "hour", "soc_in", "soc_out", "kwh", "svc_min", "detour_km"]
        ev = pd.DataFrame(ev, columns=cols) if ev else pd.DataFrame({c: [] for c in cols})
        ev[["trip", "st", "stop_no", "hour"]] = ev[["trip", "st", "stop_no", "hour"]].astype(int)
        return ev, completed, strand_km

    def _queue(self, st, ev):
        ch = self.cfg.charging
        ns = len(st)
        cnt = np.zeros((ns, 24)); ssum = np.zeros((ns, 24)); esum = np.zeros((ns, 24))
        if len(ev):
            np.add.at(cnt, (ev.st, ev.hour), 1)
            np.add.at(ssum, (ev.st, ev.hour), ev.svc_min / 60)
            np.add.at(esum, (ev.st, ev.hour), ev.kwh)
        k = ch.arrival_smooth
        if k > 0:
            sm = lambda x: (1 - 2 * k) * x + k * np.roll(x, 1, axis=1) + k * np.roll(x, -1, axis=1)
            cnt, ssum, esum = sm(cnt), sm(ssum), sm(esum)
        tot = cnt.sum(1)
        overall = np.where(tot > 0, ssum.sum(1) / np.maximum(tot, 1), 0.5)
        svc = np.where(cnt > 0, ssum / np.maximum(cnt, 1), overall[:, None])
        lam = cnt * self.W                       # vehicles / hour
        a = lam * svc                            # offered Erlangs
        c = st.n_ports.to_numpy()
        wq = np.zeros((ns, 24)); blocked = np.zeros((ns, 24))
        for s in range(ns):
            for h in range(24):
                if lam[s, h] <= 0:
                    continue
                w = _erlang_wait_h(int(c[s]), a[s, h], svc[s, h]) * 60
                if w >= ch.max_wait_min:
                    wq[s, h] = ch.max_wait_min
                    blocked[s, h] = max(0.0, 1 - c[s] / a[s, h]) if a[s, h] > c[s] else 0.1
                else:
                    wq[s, h] = w
        return dict(cnt=cnt, lam=lam, a=a, svc=svc, wq=wq, blocked=blocked, esum=esum)

    def evaluate(self, stations: pd.DataFrame, iters: int | None = None) -> Result:
        """iters=1 -> uncongested demand (drivers ignore queues); default uses charging.congestion_iters."""
        ch = self.cfg.charging
        st = self._prep_stations(stations)
        ns = len(st)
        cols = st.site_id.to_numpy()
        empty = (np.array([], int), np.array([]), np.array([]))
        lists = []
        for od in range(len(self.od_cnt)):
            if ns == 0:
                lists.append(empty); continue
            dist, frac = self.od_dist[od, cols], self.od_frac[od, cols]
            j = np.nonzero(dist <= ch.detour_max_km)[0]
            j = j[np.argsort(frac[j])]
            lists.append((j, frac[j], 2 * dist[j] * ch.detour_circuity))
        wait = np.zeros((ns, 24))
        for it in range(max(1, iters or ch.congestion_iters)):
            ev, completed, strand_km = self._simulate(st, lists, wait)
            q = self._queue(st, ev)
            wait = q["wq"] if it == 0 else 0.5 * wait + 0.5 * q["wq"]
        wq = q["wq"]
        W = self.W
        if len(ev):
            ev["wait_min"] = wq[ev.st, ev.hour]
            ev["served"] = 1 - q["blocked"][ev.st, ev.hour]

        # ---- per-station usage ----
        cand = self.candidates.iloc[cols].reset_index(drop=True)
        costs = self.station_costs(st)
        c = st.n_ports.to_numpy()
        busy = np.minimum(q["a"], c[:, None])
        served_lam = q["lam"] * (1 - q["blocked"])
        energy_day = (q["esum"] * (1 - q["blocked"])).sum(1) * W
        price = cand.elec_price.to_numpy() * ch.energy_cost_markup
        margin_day = energy_day * (ch.sell_price_eur_kwh - price)
        usage = pd.DataFrame(dict(
            site_id=cols, edge_id=cand.edge_id, x=cand.x, y=cand.y, n_ports=c, power_kw=st.power_kw,
            sessions_day=served_lam.sum(1), arrivals_day=q["lam"].sum(1), energy_kwh_day=energy_day,
            utilization=(busy / c[:, None]).mean(1), peak_utilization=(busy / c[:, None]).max(1),
            peak_offered_erlangs=q["a"].max(1),
            mean_wait_min=np.where(q["lam"].sum(1) > 0, (wq * q["lam"]).sum(1) / np.maximum(q["lam"].sum(1), 1e-9), 0),
            max_hourly_wait_min=wq.max(1),
            blocked_share=np.where(q["lam"].sum(1) > 0, 1 - served_lam.sum(1) / np.maximum(q["lam"].sum(1), 1e-9), 0),
            revenue_eur_day=energy_day * ch.sell_price_eur_kwh, margin_eur_day=margin_day,
            capex_eur=costs.capex_eur, annual_cost_eur=costs.annual_cost_eur))
        usage["profit_eur_year"] = usage.margin_eur_day * ch.days_per_year - usage.annual_cost_eur
        usage["payback_years"] = np.where(usage.profit_eur_year + usage.annual_cost_eur > 0,
                                          usage.capex_eur / np.maximum(usage.margin_eur_day * ch.days_per_year, 1e-9), np.inf)
        hourly = pd.DataFrame(dict(
            site_id=np.repeat(cols, 24), hour=np.tile(np.arange(24), ns),
            arrivals_per_h=q["lam"].ravel(), offered_erlangs=q["a"].ravel(),
            utilization=(busy / c[:, None]).ravel(), wait_min=wq.ravel(), blocked_share=q["blocked"].ravel()))

        # ---- per-trip outcomes ----
        n = self.n_trips
        agg = ev.groupby("trip").agg(n_stops=("kwh", "size"), charge_min=("svc_min", "sum"),
                                     wait_min=("wait_min", "sum"), detour_km=("detour_km", "sum"),
                                     kwh_charged=("kwh", "sum")) if len(ev) else pd.DataFrame(
            columns=["n_stops", "charge_min", "wait_min", "detour_km", "kwh_charged"])
        out = pd.DataFrame(dict(trip_id=self.corridor.trip_id, origin_city=self.corridor.origin_city,
                                dest_city=self.corridor.dest_city, distance_km=self.D,
                                needs_charge=self.needs.astype(int), completed=completed.astype(int),
                                stranded_at_km=strand_km))
        out = out.join(agg.reindex(range(n)).fillna(0.0))
        out["n_stops"] = out.n_stops.astype(int)
        out["extra_time_min"] = out.wait_min + out.detour_km / self.speed * 60

        events = pd.DataFrame()
        if len(ev):
            events = pd.DataFrame(dict(
                trip_id=self.corridor.trip_id.to_numpy()[ev.trip], site_id=cols[ev.st], stop_no=ev.stop_no,
                pos_km=ev.pos_km, arrival_hour=ev.hour, soc_in=ev.soc_in, soc_out=ev.soc_out,
                energy_kwh=ev.kwh, charge_min=ev.svc_min, wait_min=ev.wait_min, detour_km=ev.detour_km))

        # ---- corridor summary ----
        cs = self.edges.copy()
        cs["n_stations"] = 0; cs["max_gap_km"] = np.nan; cs["energy_served_kwh_day"] = 0.0
        for e, g in usage.groupby("edge_id"):
            cs.loc[e, "n_stations"] = len(g)
            cs.loc[e, "energy_served_kwh_day"] = g.energy_kwh_day.sum()
        pos_by_edge = cand.assign(site_id=cols).groupby("edge_id").pos_km.apply(list).to_dict()
        for r in cs.itertuples():
            ca, cb = r.city_a, r.city_b
            circ = r.road_km / r.euclid_km
            lo, hi = min(self.extent[ca] * circ, r.road_km), max(r.road_km - self.extent[cb] * circ, 0)
            pts = np.sort(np.array([lo] + pos_by_edge.get(r.edge_id, []) + [hi]))
            cs.loc[r.Index, "max_gap_km"] = np.diff(pts).max()

        # ---- metrics ----
        w_day = W
        n_corr_day = n * w_day
        stranded_day = (~completed).sum() * w_day
        served_sessions = served_lam.sum()
        margin_year = margin_day.sum() * ch.days_per_year
        annual_cost = costs.annual_cost_eur.sum()
        wait_h_day = (out.wait_min.sum() / 60) * w_day
        detour_h_day = (out.detour_km / self.speed).sum() * w_day
        time_cost_year = (wait_h_day + detour_h_day) * ch.value_of_time_eur_h * ch.days_per_year
        stranded_cost_year = stranded_day * ch.stranded_cost_eur * ch.days_per_year
        flow_edges = cs[cs.flow_ev_day > 0]
        metrics = dict(
            n_stations=int(ns), n_ports=int(c.sum()) if ns else 0,
            corridor_trips_day=float(n_corr_day),
            trips_needing_charge_day=float(self.needs.sum() * w_day),
            completion_rate=float(completed.mean()),
            completion_rate_needing_charge=float(completed[self.needs].mean()) if self.needs.any() else 1.0,
            stranded_trips_day=float(stranded_day),
            charging_sessions_day=float(served_sessions),
            mean_stops_per_charging_trip=float(out.n_stops[out.n_stops > 0].mean()) if (out.n_stops > 0).any() else 0.0,
            mean_wait_min=float((wq * q["lam"]).sum() / max(q["lam"].sum(), 1e-9)),
            mean_detour_km=float(out.detour_km[out.n_stops > 0].mean()) if (out.n_stops > 0).any() else 0.0,
            blocked_share=float(1 - served_sessions / max(q["lam"].sum(), 1e-9)) if ns else 0.0,
            mean_utilization=float(usage.utilization.mean()) if ns else 0.0,
            max_corridor_gap_km=float(flow_edges.pipe(lambda d: cs.loc[d.index, "max_gap_km"]).max()) if len(flow_edges) else 0.0,
            capex_eur=float(costs.capex_eur.sum()), annual_cost_eur=float(annual_cost),
            margin_eur_year=float(margin_year), network_profit_eur_year=float(margin_year - annual_cost),
            time_cost_eur_year=float(time_cost_year), stranded_cost_eur_year=float(stranded_cost_year),
            score=float(margin_year - annual_cost - time_cost_year - stranded_cost_year))
        tables = dict(station_usage=usage, station_hourly=hourly, charging_events=events,
                      trip_outcomes=out, corridor_summary=cs)
        return Result(st, metrics, tables)


def build_world(cfg: Config | None = None, outdir: str | None = None, quiet=True, nodes=None) -> ChargingWorld:
    """Run evsim (optionally exporting its csvs to outdir) and build the charging environment.
    nodes: optional prebuilt node table (e.g. from evsim_romania.setup) instead of the synthetic region."""
    cfg = cfg or Config()
    nodes, od_df, trips, _ = evsim.run(cfg, outdir, quiet=quiet, nodes_override=nodes)
    rng = np.random.default_rng(cfg.seed + 1000)
    return ChargingWorld(cfg, nodes, od_df, trips, rng)


# ----------------------------------------------------------------------------
# baseline placers (all return DataFrame[site_id, n_ports, power_kw])
# ----------------------------------------------------------------------------
def _mk(world, ids, ports=None, power=None):
    ch = world.cfg.charging
    return pd.DataFrame(dict(site_id=np.asarray(ids, int), n_ports=ports or ch.default_ports,
                             power_kw=power or ch.default_power_kw))


def place_none(world, n=0, **kw):
    return _mk(world, [])


def place_random(world, n, seed=0, **kw):
    rng = np.random.default_rng(seed)
    return _mk(world, rng.choice(len(world.candidates), min(n, len(world.candidates)), replace=False), **kw)


def place_uniform(world, n, **kw):
    """Flow-agnostic: stations spread evenly over corridors proportionally to their length."""
    c, e = world.candidates, world.edges
    has = c.groupby("edge_id").size()
    L = e.road_km[has.index]
    raw = L / L.sum() * n
    k = np.floor(raw).astype(int)
    for ix in (raw - k).sort_values(ascending=False).index[: n - k.sum()]:
        k[ix] += 1
    ids = []
    for eid, m in k.items():
        g = c[c.edge_id == eid].sort_values("pos_km")
        if m <= 0:
            continue
        targets = g.pos_km.min() + (np.arange(m) + 0.5) / m * (g.pos_km.max() - g.pos_km.min() + 1e-9)
        for t in targets:
            ids.append(int(g.site_id.iloc[np.argmin(np.abs(g.pos_km.to_numpy() - t))]))
    return _mk(world, list(dict.fromkeys(ids)), **kw)


def place_flow(world, n, min_sep_km=30.0, **kw):
    """Rank candidates by charging-need flow, enforce a minimum separation."""
    c = world.candidates.sort_values("flow_need_day", ascending=False)
    xy = c[["x", "y"]].to_numpy(); ids = c.site_id.to_numpy()
    sep = min_sep_km
    while True:
        chosen = []
        for i in range(len(c)):
            if all(np.hypot(*(xy[i] - xy[j])) >= sep for j in chosen):
                chosen.append(i)
            if len(chosen) == n:
                break
        if len(chosen) == n or sep < 1:
            break
        sep *= 0.7
    return _mk(world, ids[chosen], **kw)


def place_gapfill(world, n, **kw):
    """Repeatedly fill the largest gap on the corridor with the highest flow*gap score."""
    c, e, ch = world.candidates, world.edges, world.cfg.charging
    chosen = []
    pos = {}
    for r in e.itertuples():
        circ = r.road_km / r.euclid_km
        pos[r.edge_id] = [min(world.extent[r.city_a] * circ, r.road_km),
                          max(r.road_km - world.extent[r.city_b] * circ, 0)]
    by_edge = {k: g for k, g in c.groupby("edge_id")}
    flow = e.flow_ev_day.to_dict()
    used = set()
    while len(chosen) < n:
        best, bs = None, 0
        for eid, g in by_edge.items():
            p = np.sort(pos[eid])
            gaps = np.diff(p)
            k = int(np.argmax(gaps))
            sc = (flow[eid] + 1e-6) * gaps[k]
            if gaps[k] > ch.candidate_spacing_km and sc > bs:
                best, bs, mid = eid, sc, 0.5 * (p[k] + p[k + 1])
        if best is None:
            break
        g = by_edge[best]
        g = g[~g.site_id.isin(used)]
        if g.empty:
            flow[best] = 0
            continue
        s = g.iloc[int(np.argmin(np.abs(g.pos_km.to_numpy() - mid)))]
        used.add(int(s.site_id)); chosen.append(int(s.site_id)); pos[best].append(s.pos_km)
    return _mk(world, chosen, **kw)


PLACERS = dict(none=place_none, random=place_random, uniform=place_uniform, flow=place_flow, gapfill=place_gapfill)


def autosize(world, stations, target_util=0.6, iters=1):
    """Set n_ports per station so the peak-hour offered load / ports ~ target_util."""
    st = stations.copy()
    for _ in range(iters):
        if len(st) == 0:
            break
        res = world.evaluate(st, iters=1)      # size on uncongested demand
        u = res.tables["station_usage"].set_index("site_id")
        need = np.ceil(u.peak_offered_erlangs / target_util).clip(1, world.cfg.charging.max_ports)
        st["n_ports"] = need.reindex(st.site_id).to_numpy().astype(int)
    return st


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config"); ap.add_argument("--set", action="append", default=[])
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int); ap.add_argument("--n-trips", type=int)
    ap.add_argument("--strategy", choices=list(PLACERS), default="gapfill")
    ap.add_argument("--n-stations", type=int, default=40)
    ap.add_argument("--ports", type=int); ap.add_argument("--power-kw", type=float)
    ap.add_argument("--stations-file", help="CSV with site_id[,n_ports,power_kw] (e.g. from your ML model)")
    ap.add_argument("--autosize", action="store_true")
    ap.add_argument("--compare", action="store_true", help="evaluate all baseline strategies")
    ap.add_argument("--romania", action="store_true", help="use the Romanian real+synthetic cities (evsim_romania)")
    a = ap.parse_args(argv)

    ro_nodes = None
    if a.romania:
        import evsim_romania
        cfg, ro_nodes, lk, pv, meta, P = evsim_romania.setup(a.set, seed=a.seed if a.seed is not None else 42)
    else:
        cfg = evsim.load_config(a.config, a.set)
    if a.seed is not None: cfg.seed = a.seed
    if a.n_trips: cfg.output.n_trips = a.n_trips
    out = Path(a.out)
    world = build_world(cfg, str(out / "sim"), quiet=False, nodes=ro_nodes)
    if a.romania:
        lk.to_csv(out / "sim" / "city_lookup.csv", index=False)
    ch = out / "charging"; ch.mkdir(parents=True, exist_ok=True)
    world.candidates.to_csv(ch / "candidates.csv", index=False)
    world.edges.to_csv(ch / "corridors.csv", index=False)
    kw = dict(ports=a.ports, power=a.power_kw)
    print(f"\ncorridor network: {len(world.edges)} links, {len(world.candidates)} candidate sites, "
          f"{world.n_trips} sampled intercity trips (= {world.n_trips * world.W:,.0f} EV trips/day)")

    if a.compare:
        rows = []
        for name, fn in PLACERS.items():
            st = fn(world, a.n_stations, **kw)
            if a.autosize: st = autosize(world, st)
            m = world.evaluate(st).metrics
            rows.append(dict(strategy=name, **m))
        df = pd.DataFrame(rows)
        df.to_csv(ch / "baseline_comparison.csv", index=False)
        show = ["strategy", "n_stations", "n_ports", "completion_rate", "stranded_trips_day", "mean_wait_min",
                "mean_utilization", "max_corridor_gap_km", "capex_eur", "network_profit_eur_year", "score"]
        print(df[show].round(3).to_string(index=False))
        return
    if a.stations_file:
        st = pd.read_csv(a.stations_file)
    else:
        st = PLACERS[a.strategy](world, a.n_stations, **kw)
    if a.autosize: st = autosize(world, st)
    res = world.evaluate(st)
    res.save(ch)
    (ch / "charging_config.json").write_text(json.dumps(asdict(cfg.charging), indent=2))
    print(json.dumps({k: round(v, 3) if isinstance(v, float) else v for k, v in res.metrics.items()}, indent=2))


if __name__ == "__main__":
    main()
