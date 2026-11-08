"""Build the compact JSON bundle consumed by the frontend.

The source of truth stays in data-generation/ and ML-Agent/; this script only
translates the generated artifacts into a browser-friendly payload.
"""

from __future__ import annotations

import ast
import csv
import io
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DATA_GEN_SRC = ROOT / "data-generation" / "src"
ML_AGENT_SRC = ROOT / "ML-Agent" / "src"
for source in (DATA_GEN_SRC, ML_AGENT_SRC):
    if str(source) not in sys.path:
        sys.path.insert(0, str(source))

from evplacement.synthetic.agent import select_actions
from evplacement.synthetic.model import evaluate_placement

CITIES_PATH = ROOT / "data-generation" / "data" / "synthetic" / "cities.joblib"
BENCHMARK_PATH = ROOT / "data-generation" / "data" / "synthetic" / "benchmark.json"
OUTPUT_DIR = ROOT / "ML-Agent" / "outputs" / "synthetic"
FRONTEND_DATA = ROOT / "frontend" / "data"

BENCHMARK_K = 8
MAX_K = 12

ACTIONS_PATH = OUTPUT_DIR / "priority_sites.csv"
PLACEMENT_PATH = OUTPUT_DIR / "placement_results.csv"
REVIEW_PATH = OUTPUT_DIR / "review_queue.csv"
METRICS_PATH = OUTPUT_DIR / "metrics.json"
IMPORTANCE_PATH = OUTPUT_DIR / "feature_importance.csv"
AGENT_STATE_PATH = OUTPUT_DIR / "agent_state.json"

FEATURE_COLUMNS = [
    "population",
    "activity",
    "income",
    "ev_adoption",
    "centrality",
    "road_capacity",
    "transit_access",
    "highway_access",
    "parking",
    "poi_density",
    "dist_center",
    "degree",
    "closeness",
    "zone_business",
    "zone_residential",
    "zone_industrial",
    "competing_capacity",
    "n_stations_1km",
    "nearest_station_dist",
    "local_population",
    "local_activity",
    "planned_capacity",
    "city_nodes",
    "city_station_rate",
]

CONTEXT_FEATURES = [
    "population",
    "activity",
    "ev_adoption",
    "competing_capacity",
    "nearest_station_dist",
    "n_stations_1km",
    "dist_center",
    "transit_access",
    "poi_density",
    "planned_capacity",
]


def _num(value, digits=4):
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    return round(float(value), digits)


def _int(value):
    return int(value) if value is not None and not pd.isna(value) else None


def _parse_explanation(value):
    if isinstance(value, list):
        return value
    if not isinstance(value, str) or not value.strip():
        return []
    try:
        parsed = ast.literal_eval(value)
        return parsed if isinstance(parsed, list) else []
    except (ValueError, SyntaxError):
        return []


def _csv_line(row, header):
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="")
    writer.writerow([row.get(key, "") for key in header])
    return buffer.getvalue()


def build() -> dict:
    FRONTEND_DATA.mkdir(parents=True, exist_ok=True)
    for path in (ACTIONS_PATH, PLACEMENT_PATH, REVIEW_PATH, METRICS_PATH, IMPORTANCE_PATH, AGENT_STATE_PATH, BENCHMARK_PATH):
        if not path.exists():
            raise FileNotFoundError(path)

    cities = joblib.load(CITIES_PATH)
    test_cities = [city for city in cities.values() if city.split == "test"]
    test_cities.sort(key=lambda city: city.city_id)

    actions = pd.read_csv(ACTIONS_PATH)
    with ACTIONS_PATH.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        csv_header = list(reader.fieldnames or [])
        raw_rows = {row["action_id"]: row for row in reader}
    placement = pd.read_csv(PLACEMENT_PATH).set_index("city_id")
    metrics = json.loads(METRICS_PATH.read_text(encoding="utf-8"))
    benchmark = json.loads(BENCHMARK_PATH.read_text(encoding="utf-8"))
    importance = pd.read_csv(IMPORTANCE_PATH)
    agent_state = json.loads(AGENT_STATE_PATH.read_text(encoding="utf-8"))
    experiment = joblib.load(OUTPUT_DIR / "experiment.joblib")

    # Precompute a longer decision order once. The greedy selection is
    # prefix-consistent: ranks 1..8 are the original K=8 artifact; ranks 9..12
    # are a live extension used only by the K control.
    generated_actions = select_actions(
        experiment["uplift_model"],
        test_cities,
        MAX_K,
        experiment["alpha"],
        importance=importance,
        usage_model=experiment["usage_model"],
    )

    placement_fields = [
        "n_nodes",
        "n_existing",
        "oracle_utility",
        "base_utility",
        "model_utility",
        "model_incremental",
        "oracle_incremental",
        "utility_ratio",
        "regret",
        "oracle_overlap",
        "spearman_pred_vs_true_uplift",
        "population_ratio",
        "activity_ratio",
        "hand_index_ratio",
        "random_ratio",
    ]

    k_metrics = {}
    k_city_placements = {}
    for k in range(1, MAX_K + 1):
        result = evaluate_placement(experiment["uplift_model"], test_cities, experiment["alpha"], k=k)
        k_metrics[str(k)] = result["summary"]
        for _, row in result["cities"].iterrows():
            k_city_placements.setdefault(str(row["city_id"]), {})[str(k)] = {
                key: (_num(row[key]) if key not in {"n_nodes", "n_existing"} else _int(row[key]))
                for key in placement_fields
                if key in row
            }

    city_payloads = []
    flat_actions = []
    all_actions = []
    for city in test_cities:
        nodes = city.nodes
        node_arrays = []
        for _, row in nodes.iterrows():
            observed = row["observed_usage"]
            node_arrays.append(
                [
                    round(float(row["x"]), 6),
                    round(float(row["y"]), 6),
                    int(row["is_station"]),
                    round(float(row["latent_demand"]), 2),
                    round(float(row["station_capacity"]), 3),
                    None if pd.isna(observed) else round(float(observed), 3),
                ]
            )
        edges = [[int(a), int(b)] for a, b in city.edges]
        feature_frame = city.features.reset_index(drop=True)
        if "node_id" in feature_frame.columns:
            feature_rows = feature_frame.set_index("node_id")
        else:
            feature_rows = feature_frame
        city_medians = {feature: round(float(feature_frame[feature].median()), 4) for feature in FEATURE_COLUMNS}

        placement_row = placement.loc[city.city_id]
        placement_payload = {
            key: (_num(placement_row[key]) if key not in {"n_nodes", "n_existing"} else _int(placement_row[key]))
            for key in placement_fields
            if key in placement_row
        }

        city_actions = []
        original_by_rank = {
            int(row["rank"]): row
            for _, row in actions[actions["city_id"] == city.city_id].iterrows()
        }
        generated_by_rank = {
            int(row["rank"]): row
            for _, row in generated_actions[generated_actions["city_id"] == city.city_id].iterrows()
        }
        for rank in range(1, MAX_K + 1):
            if rank in original_by_rank:
                row = original_by_rank[rank]
                raw = raw_rows.get(str(row["action_id"]), {})
                source = "priority_sites"
            else:
                row = generated_by_rank[rank]
                raw = {}
                source = "demo_extension"
            action_id = str(row["action_id"])
            explanation = _parse_explanation(row.get("explanation"))
            node_id = int(row["node_id"])
            if node_id in feature_rows.index:
                feature_row = feature_rows.loc[node_id]
            else:
                feature_row = feature_frame.iloc[node_id]
            drivers = []
            for item in explanation:
                feature = item.get("feature")
                if feature not in FEATURE_COLUMNS:
                    continue
                drivers.append(
                    {
                        "feature": feature,
                        "value": round(float(feature_row[feature]), 4),
                        "median": city_medians[feature],
                        "drop": round(float(item.get("drop_sessions_per_day", 0.0)), 2),
                    }
                )
            context = {feature: round(float(feature_row[feature]), 4) for feature in CONTEXT_FEATURES}
            action = {
                "action_id": action_id,
                "action": str(row["action"]),
                "city_id": str(row["city_id"]),
                "node_id": node_id,
                "rank": rank,
                "predicted_uplift": _num(row["predicted_uplift"], 2),
                "predicted_usage": _num(row["predicted_usage"], 2),
                "uncertainty": _num(row["uncertainty"], 2),
                "confidence": str(row["confidence"]),
                "confidence_score": _num(row["confidence_score"], 1),
                "requires_human_review": str(row["requires_human_review"]).lower() == "true",
                "review_reason": "" if pd.isna(row.get("review_reason")) else str(row["review_reason"]),
                "explanation": explanation,
                "drivers": drivers,
                "context": context,
                "status": str(row.get("status", "PROPOSED")),
                "source": source,
                "csv_row": _csv_line(raw, csv_header) if raw else "",
            }
            city_actions.append(action)
            all_actions.append(action)
            if rank <= BENCHMARK_K:
                flat_actions.append(action)

        city_payloads.append(
            {
                "city_id": city.city_id,
                "seed": int(city.seed),
                "split": city.split,
                "n_nodes": int(len(nodes)),
                "n_existing": int(len(city.station_nodes)),
                "params": {
                    "n_nodes": int(city.params["n_nodes"]),
                    "n_centers": int(city.params["n_centers"]),
                    "station_rate": round(float(city.params["station_rate"]), 5),
                    "ev_base": round(float(city.params["ev_base"]), 4),
                    "noise": round(float(city.params["noise"]), 4),
                    "lambda_norm": round(float(city.params["lambda_norm"]), 5),
                },
                "placement": placement_payload,
                "k_placement": k_city_placements[str(city.city_id)],
                "nodes": node_arrays,
                "edges": edges,
                "medians": {feature: city_medians[feature] for feature in CONTEXT_FEATURES},
                "actions": [action for action in city_actions if action["rank"] <= BENCHMARK_K],
                "k_actions": city_actions,
            }
        )

    flat_actions.sort(key=lambda action: action["predicted_uplift"], reverse=True)
    all_actions.sort(key=lambda action: action["predicted_uplift"], reverse=True)
    k_review_counts = {
        str(k): sum(1 for action in all_actions if action["rank"] <= k and action["requires_human_review"])
        for k in range(1, MAX_K + 1)
    }
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "city_count": len(city_payloads),
        "action_count": len(flat_actions),
        "all_action_count": len(all_actions),
        "review_count": sum(1 for action in flat_actions if action["requires_human_review"]),
        "k_review_counts": k_review_counts,
        "benchmark_k": BENCHMARK_K,
        "k_min": 1,
        "k_max": MAX_K,
        "k_metrics": k_metrics,
        "benchmark": benchmark,
        "metrics": metrics,
        "feature_importance": importance.round(6).to_dict(orient="records"),
        "agent_state": agent_state,
        "csv_header": csv_header,
        "cities": city_payloads,
        "actions": flat_actions,
        "all_actions": all_actions,
        "demo_city": city_payloads[0]["city_id"] if city_payloads else None,
    }
    (FRONTEND_DATA / "dashboard.json").write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    for source, name in (
        (ACTIONS_PATH, "priority_sites.csv"),
        (REVIEW_PATH, "review_queue.csv"),
        (METRICS_PATH, "metrics.json"),
        (IMPORTANCE_PATH, "feature_importance.csv"),
        (BENCHMARK_PATH, "benchmark.json"),
        (AGENT_STATE_PATH, "agent_state.json"),
    ):
        shutil.copyfile(source, FRONTEND_DATA / name)

    size_mb = (FRONTEND_DATA / "dashboard.json").stat().st_size / 1e6
    print(f"cities: {len(city_payloads)} | actions: {len(flat_actions)} | JSON: {size_mb:.1f} MB -> {FRONTEND_DATA / 'dashboard.json'}")
    return payload


if __name__ == "__main__":
    build()
