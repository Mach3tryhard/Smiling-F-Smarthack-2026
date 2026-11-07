"""Interactive demo map for one synthetic city."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from .generator import SyntheticCity


def write_demo_map(
    city: SyntheticCity,
    actions: pd.DataFrame,
    summary: dict,
    path: Path,
) -> Path:
    nodes = city.nodes.copy()
    # Synthetic coordinates are in [0,1]; project them into a small Romania-like
    # bounding box so Leaflet/OSM can display them. This is a demo canvas, not a
    # claim that the synthetic city is a real place.
    lat0, lon0 = 45.20, 24.70
    scale = 0.18
    nodes["lat"] = lat0 + (nodes["y"] - 0.5) * scale
    nodes["lon"] = lon0 + (nodes["x"] - 0.5) * scale
    lookup = nodes.set_index("node_id")

    edges = []
    for a, b in city.edges:
        edges.append(
            [
                [float(lookup.loc[a, "lat"]), float(lookup.loc[a, "lon"])],
                [float(lookup.loc[b, "lat"]), float(lookup.loc[b, "lon"])],
            ]
        )

    node_records = []
    for row in nodes.itertuples():
        node_records.append(
            {
                "node": int(row.node_id),
                "lat": float(row.lat),
                "lon": float(row.lon),
                "demand": round(float(row.latent_demand), 2),
                "station": int(row.is_station),
                "usage": None if pd.isna(row.observed_usage) else round(float(row.observed_usage), 2),
            }
        )
    action_records = []
    for row in actions.itertuples():
        action_records.append(
            {
                "rank": int(row.rank),
                "node": int(row.node_id),
                "lat": float(lookup.loc[row.node_id, "lat"]),
                "lon": float(lookup.loc[row.node_id, "lon"]),
                "predicted": float(row.predicted_usage),
                "uncertainty": float(row.uncertainty),
                "confidence": str(row.confidence),
                "review": bool(row.requires_human_review),
                "explanation": row.explanation,
            }
        )
    data = {
        "city": city.city_id,
        "params": city.params,
        "nodes": node_records,
        "edges": edges,
        "actions": action_records,
        "summary": summary,
    }
    template = r"""<!doctype html>
<html lang="ro"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>EV synthetic city — agent demo</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<style>
body{margin:0;font-family:Inter,Segoe UI,Arial,sans-serif;color:#0f172a;background:#f8fafc}#map{position:absolute;inset:0}
.panel{position:absolute;z-index:1000;background:rgba(255,255,255,.97);border:1px solid #e2e8f0;border-radius:14px;box-shadow:0 12px 36px rgba(15,23,42,.18)}
.title{top:16px;left:16px;width:400px;padding:16px 18px}.title h1{margin:0 0 4px;font-size:19px}.title p{margin:0;color:#475569;font-size:12px;line-height:1.5}
.kpis{display:flex;gap:8px;margin-top:10px}.kpi{flex:1;background:#f1f5f9;border-radius:8px;padding:8px}.kpi b{display:block;font-size:17px}.kpi span{font-size:10px;color:#64748b;text-transform:uppercase}
.legend{bottom:16px;left:16px;padding:10px 12px;font-size:11px;color:#475569;width:340px;line-height:1.5}.dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:5px}
.side{top:16px;right:16px;width:360px;max-height:calc(100% - 32px);overflow:auto;padding:14px}.side h2{font-size:15px;margin:0 0 6px}
.site{border-left:3px solid #b91c1c;background:#fff7f7;border-radius:6px;padding:7px 9px;margin:6px 0;font-size:11px}.site b{font-size:12px}
</style></head><body><div id="map"></div>
<div class="panel title"><h1>EV synthetic city — agent demo</h1><p>Oraș generate cu ground truth: cerere latentă, stații existente, utilizare simulată. Modelul a fost antrenat pe alte orașe.</p>
<div class="kpis"><div class="kpi"><b>__ACTIONS__</b><span>stații propuse</span></div><div class="kpi"><b>__RATIO__</b><span>din oracle</span></div><div class="kpi"><b>__K__</b><span>buget</span></div></div></div>
<div class="panel side"><h2>Decizii propuse</h2><div id="sites"></div><p style="font-size:11px;color:#64748b;line-height:1.5">Scorul este utilizarea estimată (sesiuni/zi). Ground truth-ul există doar în simulator și este folosit pentru evaluare, nu de agent.</p></div>
<div class="panel legend"><span class="dot" style="background:#1d4ed8"></span>stație existentă &nbsp; <span class="dot" style="background:#b91c1c"></span>recomandare &nbsp; <span class="dot" style="background:#cbd5e1"></span>nod urban<br/>Culorile nodurilor: cerere latentă (ground truth simulator).</div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
const DATA=__DATA__;const map=L.map('map',{preferCanvas:true}).setView([45.2,24.7],12);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'&copy; OpenStreetMap'}).addTo(map);
DATA.edges.forEach(e=>L.polyline(e,{color:'#cbd5e1',weight:.7,opacity:.5}).addTo(map));
function color(d){const t=Math.min(1,Math.max(0,(d-30)/170));return `hsl(${28-24*t},${55+25*t}%,${88-45*t}%)`;}
DATA.nodes.forEach(n=>{L.circleMarker([n.lat,n.lon],{radius:2.2,color:'#fff',weight:.3,fillColor:color(n.demand),fillOpacity:.8}).bindTooltip(`Nod ${n.node}<br>Cerere latentă: ${n.demand}<br>${n.station?'Stație existentă':'Fără stație'}`).addTo(map);});
DATA.nodes.filter(n=>n.station).forEach(n=>L.circleMarker([n.lat,n.lon],{radius:5,color:'#fff',weight:1.5,fillColor:'#1d4ed8',fillOpacity:1}).bindPopup(`<b>Stație existentă</b><br>Utilizare observată: ${n.usage} sesiuni/zi`).addTo(map));
DATA.actions.forEach(a=>{L.marker([a.lat,a.lon],{icon:L.divIcon({className:'',html:`<div style="background:#b91c1c;color:#fff;border:2px solid #fff;border-radius:50%;width:25px;height:25px;display:flex;align-items:center;justify-content:center;font:700 11px Arial;box-shadow:0 2px 7px rgba(0,0,0,.35)">${a.rank}</div>`,iconSize:[25,25],iconAnchor:[12,12]})}).bindPopup(`<b>#${a.rank} · ${a.predicted.toFixed(1)} sesiuni/zi estimate</b><br>Încredere: ${a.confidence}<br><small>${a.review?'Revizuire umană':'Pregătit pentru aprobare'}</small>`).addTo(map);});
document.getElementById('sites').innerHTML=DATA.actions.map(a=>`<div class="site"><b>#${a.rank} · nod ${a.node}</b><br>${a.predicted.toFixed(1)} ± ${a.uncertainty.toFixed(1)} sesiuni/zi<br><small>${a.confidence}${a.review?' · revizuire':''}</small></div>`).join('');
</script></body></html>"""
    html = (
        template.replace("__DATA__", json.dumps(data, ensure_ascii=False))
        .replace("__ACTIONS__", str(len(action_records)))
        .replace("__RATIO__", f"{summary.get('mean_utility_ratio', 0)*100:.0f}%")
        .replace("__K__", str(len(action_records)))
    )
    path.write_text(html, encoding="utf-8")
    return path


def write_preview(city: SyntheticCity, actions: pd.DataFrame, path: Path, scores: pd.Series | None = None) -> Path:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection

    xy = city.nodes[["x", "y"]].to_numpy()
    fig, ax = plt.subplots(figsize=(9, 8), dpi=180)
    segments = [[xy[a], xy[b]] for a, b in city.edges]
    ax.add_collection(LineCollection(segments, colors="#dbe3ec", linewidths=0.55, zorder=1))
    nodes = city.nodes
    if scores is not None:
        values = nodes["node_id"].map(scores).fillna(0.0).to_numpy()
        label = "Nod urban (uplift estimat de model)"
    else:
        values = nodes["latent_demand"].to_numpy()
        label = "Nod urban (cerere latentă)"
    ax.scatter(
        nodes["x"],
        nodes["y"],
        c=values,
        cmap="YlOrRd",
        s=8,
        linewidths=0,
        alpha=0.85,
        zorder=2,
        label=label,
    )
    stations = nodes[nodes["is_station"] == 1]
    ax.scatter(stations["x"], stations["y"], s=42, c="#1d4ed8", edgecolors="white", linewidths=0.8, zorder=4, label="Stație existentă")
    if len(actions):
        ax.scatter(actions["x"], actions["y"], s=190, marker="*", c="#b91c1c", edgecolors="white", linewidths=0.7, zorder=5, label="Recomandare agent")
        for row in actions.itertuples():
            ax.annotate(str(int(row.rank)), (row.x, row.y), xytext=(5, 4), textcoords="offset points", fontsize=7, color="#7f1d1d")
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title(f"Oraș sintetic {city.city_id} — stații existente și recomandări", fontsize=12)
    ax.legend(loc="lower left", fontsize=8, frameon=True)
    ax.text(0.01, 0.01, "Ground truth simulator. Coordonate normalizate, nu o hartă reală.", transform=ax.transAxes, fontsize=6.5, color="#64748b", va="bottom")
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def write_validation_plot(predictions: pd.DataFrame, placement: pd.DataFrame, path: Path) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8), dpi=170, gridspec_kw={"width_ratios": [1, 1.15]})
    axes[0].scatter(predictions["observed_usage"], predictions["predicted_usage"], s=16, alpha=0.6, color="#1d4ed8", edgecolors="white", linewidths=0.3)
    max_value = float(max(predictions["observed_usage"].max(), predictions["predicted_usage"].max()) * 1.05)
    axes[0].plot([0, max_value], [0, max_value], color="#111827", linestyle="--", linewidth=1.1)
    axes[0].set_xlim(0, max_value)
    axes[0].set_ylim(0, max_value)
    axes[0].set_xlabel("Utilizare reală (sesiuni/zi)")
    axes[0].set_ylabel("Utilizare prezisă")
    axes[0].set_title("Model pe stații din orașe nevăzute")
    axes[0].grid(alpha=0.2)

    ordered = placement.sort_values("utility_ratio")
    axes[1].barh(ordered["city_id"], ordered["utility_ratio"] * 100, color="#b91c1c", alpha=0.85)
    axes[1].axvline(100, color="#111827", linestyle="--", linewidth=1.1, label="Oracle")
    axes[1].set_xlabel("Utilizare creată vs oracle (%)")
    axes[1].set_title("Eroarea de amplasare pe oraș")
    axes[1].legend(fontsize=8)
    axes[1].grid(axis="x", alpha=0.2)
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path
