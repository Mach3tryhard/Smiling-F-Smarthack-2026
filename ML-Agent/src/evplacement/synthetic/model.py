"""GPU-trained usage model and ground-truth placement evaluation.

The model predicts log usage at existing stations. The evaluator uses the
generator's counterfactual simulator to compute the true system-wide utility of
any candidate station portfolio, so placement regret is measurable.
"""

from __future__ import annotations

import copy
import time
import warnings
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import torch
from scipy.stats import spearmanr
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.preprocessing import StandardScaler
from torch import nn

from .generator import SyntheticCity, total_expected_usage

FEATURES = [
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


class MLP(nn.Module):
    def __init__(self, n_features: int):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(n_features, 256),
            nn.GELU(),
            nn.Dropout(0.10),
            nn.Linear(256, 128),
            nn.GELU(),
            nn.Dropout(0.08),
            nn.Linear(128, 64),
            nn.GELU(),
            nn.Linear(64, 1),
        )

    def forward(self, x):
        return self.net(x).squeeze(-1)


@dataclass
class UsageEnsemble:
    random_state: int = 42
    epochs: int = 70
    batch_size: int = 2048
    learning_rate: float = 1e-3
    mlp_models: list = field(default_factory=list)
    mlp_states: list = field(default_factory=list)
    hgb: HistGradientBoostingRegressor | None = None
    scaler: StandardScaler | None = None
    blend_weight: float = 0.5
    device_name: str = "cpu"
    training_device: str = "cpu"
    train_seconds: float = 0.0

    def fit(self, X: pd.DataFrame, y: np.ndarray, X_val: pd.DataFrame | None = None, y_val: np.ndarray | None = None):
        start = time.time()
        self.scaler = StandardScaler().fit(X)
        Xs = self.scaler.transform(X).astype(np.float32)
        if X_val is None:
            X_val = X.iloc[-max(1, len(X) // 10):]
            y_val = y[-max(1, len(y) // 10):]
        Xv = self.scaler.transform(X_val).astype(np.float32)
        y_log = np.log1p(y).astype(np.float32)
        yv_log = np.log1p(y_val).astype(np.float32)

        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.device_name = str(device)
        self.training_device = str(device)
        x_tensor = torch.tensor(Xs, dtype=torch.float32, device=device)
        y_tensor = torch.tensor(y_log, dtype=torch.float32, device=device)
        xv_tensor = torch.tensor(Xv, dtype=torch.float32, device=device)
        yv_tensor = torch.tensor(yv_log, dtype=torch.float32, device=device)

        self.mlp_models = []
        self.mlp_states = []
        n = len(Xs)
        for seed_offset in range(3):
            torch.manual_seed(self.random_state + seed_offset)
            model = MLP(Xs.shape[1]).to(device)
            optimizer = torch.optim.AdamW(model.parameters(), lr=self.learning_rate, weight_decay=1e-4)
            scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=self.epochs)
            loss_fn = nn.HuberLoss(delta=0.5)
            best_state = copy.deepcopy(model.state_dict())
            best_val = float("inf")
            patience = 0
            generator = torch.Generator().manual_seed(self.random_state + seed_offset)
            for epoch in range(self.epochs):
                model.train()
                permutation = torch.randperm(n, generator=generator).to(device)
                for start_idx in range(0, n, self.batch_size):
                    indices = permutation[start_idx : start_idx + self.batch_size]
                    optimizer.zero_grad()
                    loss = loss_fn(model(x_tensor[indices]), y_tensor[indices])
                    loss.backward()
                    optimizer.step()
                scheduler.step()
                model.eval()
                with torch.no_grad():
                    val_pred = model(xv_tensor).cpu().numpy()
                val_mae = float(np.mean(np.abs(val_pred - yv_log)))
                if val_mae < best_val - 1e-5:
                    best_val = val_mae
                    best_state = copy.deepcopy(model.state_dict())
                    patience = 0
                else:
                    patience += 1
                    if patience >= 10:
                        break
            model.load_state_dict(best_state)
            model.eval()
            self.mlp_models.append(model)
            self.mlp_states.append({key: value.detach().cpu() for key, value in best_state.items()})

        self.hgb = HistGradientBoostingRegressor(
            loss="squared_error",
            learning_rate=0.05,
            max_iter=300,
            max_leaf_nodes=31,
            min_samples_leaf=20,
            l2_regularization=2.0,
            max_features=0.9,
            early_stopping=False,
            random_state=self.random_state,
        )
        self.hgb.fit(Xs, y_log)

        # Pick the MLP/HGB blend on validation only.
        mlp_val = self._mlp_log(Xv)
        hgb_val = self.hgb.predict(Xv)
        best_weight, best_score = 0.5, float("inf")
        for weight in (0.0, 0.25, 0.5, 0.75, 1.0):
            score = mean_absolute_error(yv_log, weight * mlp_val + (1 - weight) * hgb_val)
            if score < best_score:
                best_score = score
                best_weight = weight
        self.blend_weight = best_weight
        # Keep the saved model portable: training was on GPU, inference can be
        # CPU on any judge machine. The GPU time is reported in the metrics.
        for model in self.mlp_models:
            model.to("cpu").eval()
        self.device_name = "cpu"
        self.train_seconds = time.time() - start
        return self

    def _mlp_log(self, X_scaled: np.ndarray) -> np.ndarray:
        device = torch.device(self.device_name)
        tensor = torch.tensor(X_scaled, dtype=torch.float32, device=device)
        predictions = []
        with torch.no_grad():
            for model in self.mlp_models:
                model.eval()
                predictions.append(model(tensor).cpu().numpy())
        return np.mean(predictions, axis=0)

    def predict_log(self, X: pd.DataFrame) -> np.ndarray:
        Xs = self.scaler.transform(X).astype(np.float32)
        return self.blend_weight * self._mlp_log(Xs) + (1 - self.blend_weight) * self.hgb.predict(Xs)

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        return np.clip(np.expm1(self.predict_log(X)), 0.0, None)

    def predict_std(self, X: pd.DataFrame) -> np.ndarray:
        Xs = self.scaler.transform(X).astype(np.float32)
        device = torch.device(self.device_name)
        tensor = torch.tensor(Xs, dtype=torch.float32, device=device)
        predictions = []
        with torch.no_grad():
            for model in self.mlp_models:
                model.eval()
                predictions.append(np.expm1(model(tensor).cpu().numpy()))
        return np.std(np.column_stack(predictions), axis=1)


def station_frame(cities: list[SyntheticCity]) -> pd.DataFrame:
    rows = []
    for city in cities:
        stations = city.features[city.features["is_station"] == 1].copy()
        stations["observed_usage"] = city.nodes.loc[stations.index, "observed_usage"].to_numpy()
        stations["city_id"] = city.city_id
        stations["city_seed"] = city.seed
        rows.append(stations)
    return pd.concat(rows, ignore_index=True)


def candidate_frame(city: SyntheticCity) -> pd.DataFrame:
    frame = city.features[city.features["is_station"] == 0].copy()
    frame["planned_capacity"] = 1.0
    return frame


def uplift_frame(cities: list[SyntheticCity]) -> pd.DataFrame:
    """Build candidate-level labels from the counterfactual simulator."""
    rows = []
    for city in cities:
        frame = candidate_frame(city)
        truth = candidate_incremental(city)
        frame = frame.copy()
        frame["true_uplift"] = truth["uplift"].to_numpy()
        frame["city_id"] = city.city_id
        rows.append(frame)
    return pd.concat(rows, ignore_index=True)


def _regression_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    log_true, log_pred = np.log1p(y_true), np.log1p(y_pred)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        rho = spearmanr(y_true, y_pred).correlation
    return {
        "mae_log": float(mean_absolute_error(log_true, log_pred)),
        "rmse_log": float(np.sqrt(mean_squared_error(log_true, log_pred))),
        "mae_usage": float(mean_absolute_error(y_true, y_pred)),
        "rmse_usage": float(np.sqrt(mean_squared_error(y_true, y_pred))),
        "r2_log": float(r2_score(log_true, log_pred)),
        "spearman": float(rho) if np.isfinite(rho) else float("nan"),
        "mean_usage": float(y_true.mean()),
        "n": int(len(y_true)),
    }


def train_usage_model(train_cities, val_cities):
    train = station_frame(train_cities)
    val = station_frame(val_cities)
    model = UsageEnsemble()
    model.fit(train[FEATURES], train["observed_usage"].to_numpy(), val[FEATURES], val["observed_usage"].to_numpy())
    val_pred = model.predict(val[FEATURES])
    metrics = _regression_metrics(val["observed_usage"].to_numpy(), val_pred)
    metrics.update(
        {
            "n_train_stations": int(len(train)),
            "n_val_stations": int(len(val)),
            "device": model.training_device,
            "blend_weight": model.blend_weight,
            "train_seconds": round(model.train_seconds, 1),
        }
    )
    mean_pred = np.full(len(val), float(train["observed_usage"].mean()))
    metrics["mean_baseline"] = _regression_metrics(val["observed_usage"].to_numpy(), mean_pred)
    return model, metrics


def train_uplift_model(train_cities, val_cities):
    train = uplift_frame(train_cities)
    val = uplift_frame(val_cities)
    model = UsageEnsemble()
    model.fit(train[FEATURES], train["true_uplift"].to_numpy(), val[FEATURES], val["true_uplift"].to_numpy())
    val_pred = model.predict(val[FEATURES])
    metrics = _regression_metrics(val["true_uplift"].to_numpy(), val_pred)
    metrics.update(
        {
            "n_train_candidates": int(len(train)),
            "n_val_candidates": int(len(val)),
            "device": model.training_device,
            "blend_weight": model.blend_weight,
            "train_seconds": round(model.train_seconds, 1),
        }
    )
    mean_pred = np.full(len(val), float(train["true_uplift"].mean()))
    metrics["mean_baseline"] = _regression_metrics(val["true_uplift"].to_numpy(), mean_pred)
    return model, metrics


def evaluate_uplift(model, cities):
    test = uplift_frame(cities)
    predictions = model.predict(test[FEATURES])
    metrics = _regression_metrics(test["true_uplift"].to_numpy(), predictions)
    metrics["n_test_candidates"] = int(len(test))
    mean_pred = np.full(len(test), float(test["true_uplift"].mean()))
    metrics["mean_baseline"] = _regression_metrics(test["true_uplift"].to_numpy(), mean_pred)
    output = test[["city_id", "node_id", "x", "y", "true_uplift"]].copy()
    output["predicted_uplift"] = predictions
    output["residual"] = output["true_uplift"] - output["predicted_uplift"]
    return {"metrics": metrics, "predictions": output}


# ---------------------------------------------------------------------------
# Ground-truth placement simulator (vectorised over candidates)
# ---------------------------------------------------------------------------


def _current_state(city: SyntheticCity, extra_nodes=None, extra_capacity=None):
    nodes = list(city.station_nodes)
    capacity = list(city.station_capacity)
    if extra_nodes is not None:
        nodes += list(extra_nodes)
        capacity += list(extra_capacity)
    nodes = np.asarray(nodes, dtype=int)
    capacity = np.asarray(capacity, dtype=float)
    xy = city.nodes[["x", "y"]].to_numpy()[nodes]
    d = city.latent_demand[nodes]
    lam = city.params["lambda_norm"]
    distances = np.sqrt(((xy[:, None, :] - xy[None, :, :]) ** 2).sum(axis=2))
    kernel = np.exp(-distances / lam)
    np.fill_diagonal(kernel, 1.0)
    competition = kernel @ capacity - capacity
    return nodes, capacity, xy, d, competition, lam


def _total_with_one_candidate(city, candidates, state):
    """Vectorised total system usage after adding one candidate at each node."""
    nodes, capacity, xy, demand, competition, lam = state
    cand_xy = city.nodes[["x", "y"]].to_numpy()[candidates]
    distances = np.sqrt(((cand_xy[:, None, :] - xy[None, :, :]) ** 2).sum(axis=2))
    kernel = np.exp(-distances / lam)
    existing_usage = (demand[None, :] * capacity[None, :]) / (
        capacity[None, :] + competition[None, :] + kernel + 1e-9
    )
    candidate_comp = kernel @ capacity
    candidate_usage = city.latent_demand[candidates] / (1.0 + candidate_comp + 1e-9)
    return existing_usage.sum(axis=1) + candidate_usage


def candidate_incremental(city: SyntheticCity, candidates: np.ndarray | None = None) -> pd.DataFrame:
    if candidates is None:
        candidates = np.where(city.nodes["is_station"].to_numpy() == 0)[0]
    state = _current_state(city)
    base = total_expected_usage(city)
    totals = _total_with_one_candidate(city, candidates, state)
    return pd.DataFrame(
        {
            "city_id": city.city_id,
            "node_id": candidates.astype(int),
            "uplift": np.maximum(0.0, totals - base),
            "total_with_site": totals,
        }
    )


def true_portfolio_utility(city: SyntheticCity, selected: list[int]) -> float:
    if not selected:
        return total_expected_usage(city)
    state = _current_state(city, selected, np.ones(len(selected)))
    nodes, capacity, xy, demand, competition, lam = state
    usage = demand * capacity / (capacity + competition + 1e-9)
    return float(usage.sum())


def _true_greedy(city: SyntheticCity, candidates: np.ndarray, k: int) -> list[int]:
    selected: list[int] = []
    for _ in range(min(k, len(candidates))):
        state = _current_state(city, selected, np.ones(len(selected)))
        totals = _total_with_one_candidate(city, candidates, state)
        totals[np.isin(candidates, selected)] = -np.inf
        best = int(candidates[int(np.argmax(totals))])
        selected.append(best)
    return selected


def _model_greedy(city, predicted_usage, candidates, k, alpha, lambda_norm):
    xy = city.nodes[["x", "y"]].to_numpy()[candidates]
    scores = predicted_usage.copy()
    selected_idx: list[int] = []
    for _ in range(min(k, len(candidates))):
        adjusted = scores.copy()
        if selected_idx:
            chosen_xy = city.nodes[["x", "y"]].to_numpy()[candidates[np.array(selected_idx)]]
            distances = np.sqrt(((xy[:, None, :] - chosen_xy[None, :, :]) ** 2).sum(axis=2))
            penalty = np.exp(-distances / lambda_norm).sum(axis=1)
            adjusted = adjusted / (1.0 + alpha * penalty)
        adjusted[selected_idx] = -np.inf
        best = int(np.argmax(adjusted))
        selected_idx.append(best)
    return [int(candidates[index]) for index in selected_idx]


def _hand_index(frame: pd.DataFrame) -> np.ndarray:
    return (
        0.32 * frame["population"].to_numpy()
        + 0.20 * frame["activity"].to_numpy()
        + 0.14 * frame["ev_adoption"].to_numpy()
        + 0.12 * frame["centrality"].to_numpy()
        + 0.10 * frame["transit_access"].to_numpy()
        + 0.06 * frame["road_capacity"].to_numpy()
        + 0.06 * frame["parking"].to_numpy()
    )


def tune_alpha(model: UsageEnsemble, val_cities, k, alphas=(0.0, 0.25, 0.5, 1.0, 2.0)):
    cache = []
    for city in val_cities:
        candidates = np.where(city.nodes["is_station"].to_numpy() == 0)[0]
        frame = candidate_frame(city)
        predicted = model.predict(frame[FEATURES])
        oracle = _true_greedy(city, candidates, k)
        base = total_expected_usage(city)
        oracle_increment = true_portfolio_utility(city, oracle) - base
        cache.append((city, candidates, predicted, base, oracle_increment))
    ratios = {alpha: [] for alpha in alphas}
    for city, candidates, predicted, base, oracle_increment in cache:
        for alpha in alphas:
            selected = _model_greedy(city, predicted, candidates, k, alpha, city.params["lambda_norm"])
            increment = true_portfolio_utility(city, selected) - base
            ratios[alpha].append(increment / oracle_increment if oracle_increment > 1e-9 else 1.0)
    results = {
        alpha: {"mean_ratio": float(np.mean(values)), "std_ratio": float(np.std(values))}
        for alpha, values in ratios.items()
    }
    best = max(results, key=lambda key: results[key]["mean_ratio"])
    return best, results


def evaluate_placement(model, test_cities, alpha, k=8, seed=42):
    rng = np.random.default_rng(seed)
    rows = []
    rhos = []
    for city in test_cities:
        candidates = np.where(city.nodes["is_station"].to_numpy() == 0)[0]
        frame = candidate_frame(city)
        predicted = model.predict(frame[FEATURES])
        true_uplift = candidate_incremental(city, candidates)["uplift"].to_numpy()
        selected = _model_greedy(city, predicted, candidates, k, alpha, city.params["lambda_norm"])
        oracle = _true_greedy(city, candidates, k)
        base = total_expected_usage(city)
        oracle_utility = true_portfolio_utility(city, oracle)
        model_utility = true_portfolio_utility(city, selected)
        denom = oracle_utility - base
        ratio = (model_utility - base) / denom if denom > 1e-9 else 1.0
        rho = spearmanr(predicted, true_uplift).correlation
        if np.isfinite(rho):
            rhos.append(float(rho))
        baselines = {}
        for name, score in {
            "population": city.nodes.loc[candidates, "population"].to_numpy(),
            "activity": city.nodes.loc[candidates, "activity"].to_numpy(),
            "hand_index": _hand_index(city.nodes.loc[candidates]),
        }.items():
            chosen = list(candidates[np.argsort(-score)[:k]])
            baselines[name] = true_portfolio_utility(city, chosen)
        random_values = []
        for _ in range(3):
            chosen = list(rng.choice(candidates, size=min(k, len(candidates)), replace=False))
            random_values.append(true_portfolio_utility(city, chosen))
        baselines["random"] = float(np.mean(random_values))
        rows.append(
            {
                "city_id": city.city_id,
                "n_nodes": len(city.nodes),
                "n_existing": len(city.station_nodes),
                "oracle_utility": oracle_utility,
                "base_utility": base,
                "model_utility": model_utility,
                "model_incremental": model_utility - base,
                "oracle_incremental": denom,
                "utility_ratio": ratio,
                "regret": max(0.0, 1.0 - ratio),
                "oracle_overlap": len(set(selected) & set(oracle)) / max(1, len(oracle)),
                "spearman_pred_vs_true_uplift": float(rho) if np.isfinite(rho) else float("nan"),
                **{f"{name}_incremental": value - base for name, value in baselines.items()},
                **{f"{name}_ratio": (value - base) / denom if denom > 1e-9 else 1.0 for name, value in baselines.items()},
            }
        )
    frame = pd.DataFrame(rows)
    summary = {
        "k": k,
        "alpha": alpha,
        "n_cities": int(len(frame)),
        "mean_utility_ratio": float(frame["utility_ratio"].mean()),
        "std_utility_ratio": float(frame["utility_ratio"].std()),
        "mean_regret": float(frame["regret"].mean()),
        "mean_oracle_overlap": float(frame["oracle_overlap"].mean()),
        "mean_spearman_pred_vs_uplift": float(np.mean(rhos)) if rhos else float("nan"),
        "baseline_mean_ratios": {
            name: float(frame[f"{name}_ratio"].mean())
            for name in ("population", "activity", "hand_index", "random")
        },
    }
    return {"summary": summary, "cities": frame}


def evaluate_usage(model, cities):
    test = station_frame(cities)
    predictions = model.predict(test[FEATURES])
    metrics = _regression_metrics(test["observed_usage"].to_numpy(), predictions)
    metrics["n_test_stations"] = int(len(test))
    mean_pred = np.full(len(test), float(test["observed_usage"].mean()))
    metrics["mean_baseline"] = _regression_metrics(test["observed_usage"].to_numpy(), mean_pred)
    output = test[["city_id", "node_id", "x", "y", "observed_usage", "competing_capacity", "n_stations_1km"]].copy()
    output["predicted_usage"] = predictions
    output["residual"] = output["observed_usage"] - output["predicted_usage"]
    return {"metrics": metrics, "predictions": output}


def permutation_importance(model, cities, n_repeats=2, seed=42):
    test = station_frame(cities)
    X = test[FEATURES].copy()
    y = test["observed_usage"].to_numpy()
    return _permutation_from_frame(model, X, y, n_repeats, seed)


def permutation_importance_candidates(model, cities, n_repeats=2, seed=42):
    test = uplift_frame(cities)
    return _permutation_from_frame(model, test[FEATURES].copy(), test["true_uplift"].to_numpy(), n_repeats, seed)


def _permutation_from_frame(model, X, y, n_repeats, seed):
    baseline = mean_absolute_error(np.log1p(y), np.log1p(model.predict(X)))
    rng = np.random.default_rng(seed)
    rows = []
    for feature in FEATURES:
        drops = []
        original = X[feature].to_numpy(copy=True)
        for _ in range(n_repeats):
            shuffled = original.copy()
            rng.shuffle(shuffled)
            mutated = X.copy()
            mutated[feature] = shuffled
            score = mean_absolute_error(np.log1p(y), np.log1p(model.predict(mutated)))
            drops.append(score - baseline)
        rows.append({"feature": feature, "mae_increase": float(np.mean(drops))})
    return pd.DataFrame(rows).sort_values("mae_increase", ascending=False)


def run_experiment(train_cities, val_cities, test_cities, shift_cities, k=8):
    start = time.time()
    usage_model, val_usage = train_usage_model(train_cities, val_cities)
    uplift_model, val_uplift = train_uplift_model(train_cities, val_cities)
    alpha, alpha_results = tune_alpha(uplift_model, val_cities, k)
    usage_test = evaluate_usage(usage_model, test_cities)
    uplift_test = evaluate_uplift(uplift_model, test_cities)
    placement_test = evaluate_placement(uplift_model, test_cities, alpha, k)
    usage_shift = evaluate_usage(usage_model, shift_cities)
    uplift_shift = evaluate_uplift(uplift_model, shift_cities)
    placement_shift = evaluate_placement(uplift_model, shift_cities, alpha, k)
    importance = permutation_importance_candidates(uplift_model, test_cities)
    return {
        "usage_model": usage_model,
        "uplift_model": uplift_model,
        "val_usage": val_usage,
        "val_uplift": val_uplift,
        "alpha": alpha,
        "alpha_results": alpha_results,
        "test_usage": usage_test,
        "test_uplift": uplift_test,
        "test_placement": placement_test,
        "shift_usage": usage_shift,
        "shift_uplift": uplift_shift,
        "shift_placement": placement_shift,
        "importance": importance,
        "runtime_seconds": round(time.time() - start, 1),
    }
