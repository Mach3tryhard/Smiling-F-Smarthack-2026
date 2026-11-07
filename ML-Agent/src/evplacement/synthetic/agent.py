"""Agent action layer for the synthetic graph benchmark."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from .generator import SyntheticCity
from .model import FEATURES, UsageEnsemble, _model_greedy, candidate_frame


def _confidence(predicted: np.ndarray, std: np.ndarray) -> tuple[str, float]:
    relative = std / np.clip(predicted, 1e-6, None)
    score = float(np.clip(1.0 - relative.mean() / 0.45, 0.0, 1.0) * 100.0) if len(relative) else 0.0
    if score >= 70:
        return "high", score
    if score >= 45:
        return "medium", score
    return "low", score


def explain_node(
    model: UsageEnsemble,
    row: pd.Series,
    medians: pd.Series,
    features: list[str],
    top_features: list[str],
) -> list[dict]:
    base = float(model.predict(pd.DataFrame([row[features]]))[0])
    explanations = []
    for feature in top_features:
        mutated = row.copy()
        mutated[feature] = medians[feature]
        score = float(model.predict(pd.DataFrame([mutated[features]]))[0])
        drop = base - score
        if drop > 1e-4:
            explanations.append({"feature": feature, "drop_sessions_per_day": round(drop, 3)})
    explanations.sort(key=lambda item: item["drop_sessions_per_day"], reverse=True)
    return explanations[:3]


def select_actions(
    model: UsageEnsemble,
    cities: list[SyntheticCity],
    k: int,
    alpha: float,
    importance: pd.DataFrame | None = None,
    usage_model: UsageEnsemble | None = None,
) -> pd.DataFrame:
    rows = []
    top_features = importance["feature"].head(5).tolist() if importance is not None else FEATURES[:5]
    for city in cities:
        candidates = np.where(city.nodes["is_station"].to_numpy() == 0)[0]
        frame = candidate_frame(city)
        predictions = model.predict(frame[FEATURES])
        std = model.predict_std(frame[FEATURES])
        usage_predictions = usage_model.predict(frame[FEATURES]) if usage_model is not None else predictions
        selected = _model_greedy(city, predictions, candidates, k, alpha, city.params["lambda_norm"])
        medians = frame[FEATURES].median()
        lookup = {int(node): index for index, node in enumerate(candidates)}
        for rank, node in enumerate(selected, start=1):
            index = lookup[int(node)]
            row = frame.iloc[index]
            confidence, confidence_score = _confidence(predictions[index : index + 1], std[index : index + 1])
            explanation = explain_node(model, row, medians, FEATURES, top_features)
            predicted_uplift = float(predictions[index])
            predicted_usage = float(usage_predictions[index])
            low_business_case = predicted_usage < 10.0
            review = (confidence != "high") or low_business_case
            reason = []
            if confidence == "medium":
                reason.append("încredere medie între modele")
            if confidence == "low":
                reason.append("incertitudine mare între modele")
            if low_business_case:
                reason.append("utilizare estimată sub 10 sesiuni/zi")
            rows.append(
                {
                    "action_id": f"SYN-{city.city_id}-{rank:02d}",
                    "action": "SITE_VALIDATION" if review else "INSTALL_EV_CHARGER",
                    "city_id": city.city_id,
                    "node_id": int(node),
                    "x": float(row["x"]),
                    "y": float(row["y"]),
                    "rank": rank,
                    "predicted_uplift": round(predicted_uplift, 2),
                    "predicted_usage": round(predicted_usage, 2),
                    "uncertainty": round(float(std[index]), 2),
                    "confidence": confidence,
                    "confidence_score": round(confidence_score, 1),
                    "requires_human_review": review,
                    "review_reason": "; ".join(reason),
                    "explanation": explanation,
                    "status": "PROPOSED",
                }
            )
    return pd.DataFrame(rows)


def run_agent(
    model: UsageEnsemble,
    cities: list[SyntheticCity],
    k: int,
    alpha: float,
    importance: pd.DataFrame | None,
    output_dir,
    usage_model: UsageEnsemble | None = None,
) -> dict:
    actions = select_actions(model, cities, k, alpha, importance, usage_model=usage_model)
    output_dir.mkdir(parents=True, exist_ok=True)
    actions.to_csv(output_dir / "priority_sites.csv", index=False)
    if len(actions):
        actions[actions["requires_human_review"]].to_csv(output_dir / "review_queue.csv", index=False)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "agent": "synthetic-city-placement-v2",
        "budget_per_city": k,
        "alpha": alpha,
        "actions": actions.to_dict(orient="records"),
    }
    (output_dir / "agent_actions.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    state = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "cities": len(cities),
        "actions": int(len(actions)),
        "review_required": int(actions["requires_human_review"].sum()) if len(actions) else 0,
        "budget_per_city": k,
    }
    (output_dir / "agent_state.json").write_text(json.dumps(state, indent=2), encoding="utf-8")
    return {"actions": actions, "state": state}
