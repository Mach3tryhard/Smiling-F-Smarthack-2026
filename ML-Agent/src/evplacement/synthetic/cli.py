"""CLI for the synthetic graph benchmark."""

from __future__ import annotations

import argparse
import json
import sys

import joblib
import pandas as pd

from .agent import run_agent
from .dashboard import write_demo_map, write_preview, write_validation_plot
from .generator import SYNTHETIC_DIR, SYNTHETIC_OUTPUT_DIR, build_benchmark
from .model import FEATURES, candidate_frame, run_experiment
from .reports import write_detailed, write_jury


def _load_cities():
    path = SYNTHETIC_DIR / "cities.joblib"
    if not path.exists():
        raise FileNotFoundError("Run `python -m evplacement.synthetic build` first")
    return joblib.load(path)


def _split(cities, name):
    return [city for city in cities.values() if city.split == name]


def _save_experiment(result: dict, output_dir):
    output_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(result, output_dir / "experiment.joblib")
    metrics = {
        "validation_usage": result["val_usage"],
        "validation_uplift": result["val_uplift"],
        "test_usage": result["test_usage"]["metrics"],
        "test_uplift": result["test_uplift"]["metrics"],
        "test_placement": result["test_placement"]["summary"],
        "shift_usage": result["shift_usage"]["metrics"],
        "shift_uplift": result["shift_uplift"]["metrics"],
        "shift_placement": result["shift_placement"]["summary"],
        "alpha": result["alpha"],
        "alpha_results": result["alpha_results"],
        "models": {
            "usage_device": result["usage_model"].training_device,
            "usage_train_seconds": round(result["usage_model"].train_seconds, 1),
            "uplift_device": result["uplift_model"].training_device,
            "uplift_train_seconds": round(result["uplift_model"].train_seconds, 1),
        },
        "runtime_seconds": result["runtime_seconds"],
    }
    (output_dir / "metrics.json").write_text(json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8")
    joblib.dump(
        {"model": result["usage_model"], "features": FEATURES, "metrics": result["test_usage"]["metrics"]},
        output_dir / "usage_model.joblib",
    )
    joblib.dump(
        {
            "model": result["uplift_model"],
            "features": FEATURES,
            "alpha": result["alpha"],
            "metrics": result["test_uplift"]["metrics"],
        },
        output_dir / "uplift_model.joblib",
    )
    result["test_usage"]["predictions"].to_csv(output_dir / "test_predictions.csv", index=False)
    result["test_placement"]["cities"].to_csv(output_dir / "placement_results.csv", index=False)
    result["shift_placement"]["cities"].to_csv(output_dir / "placement_shift_results.csv", index=False)
    result["importance"].to_csv(output_dir / "feature_importance.csv", index=False)


def cmd_build(args, config=None):
    summary = build_benchmark(out_dir=SYNTHETIC_DIR)
    print(json.dumps(summary["summary"], indent=2))


def cmd_train(args, config=None):
    cities = _load_cities()
    result = run_experiment(
        _split(cities, "train"),
        _split(cities, "validation"),
        _split(cities, "test"),
        _split(cities, "test_shift"),
        k=args.k,
    )
    _save_experiment(result, SYNTHETIC_OUTPUT_DIR)
    print(f"Usage MAE(log): {result['test_usage']['metrics']['mae_log']:.3f}")
    print(f"Placement: {result['test_placement']['summary']['mean_utility_ratio']*100:.1f}% of oracle")
    print(f"Regret: {result['test_placement']['summary']['mean_regret']*100:.1f}%")
    print(f"Wrote {SYNTHETIC_OUTPUT_DIR / 'metrics.json'}")


def cmd_agent(args, config=None):
    experiment = joblib.load(SYNTHETIC_OUTPUT_DIR / "experiment.joblib")
    cities = _load_cities()
    test = _split(cities, "test")
    result = run_agent(
        experiment["uplift_model"],
        test,
        k=args.k,
        alpha=experiment["alpha"],
        importance=experiment["importance"],
        output_dir=SYNTHETIC_OUTPUT_DIR,
        usage_model=experiment["usage_model"],
    )
    demo_city = test[0]
    demo_actions = result["actions"][result["actions"]["city_id"] == demo_city.city_id]
    write_demo_map(
        demo_city,
        demo_actions,
        experiment["test_placement"]["summary"],
        SYNTHETIC_OUTPUT_DIR / "dashboard.html",
    )
    demo_frame = candidate_frame(demo_city)
    demo_scores = pd.Series(
        experiment["uplift_model"].predict(demo_frame[FEATURES]),
        index=demo_frame["node_id"].to_numpy(),
    )
    write_preview(demo_city, demo_actions, SYNTHETIC_OUTPUT_DIR / "dashboard_preview.png", scores=demo_scores)
    write_validation_plot(
        experiment["test_usage"]["predictions"],
        experiment["test_placement"]["cities"],
        SYNTHETIC_OUTPUT_DIR / "validation.png",
    )
    print(f"Actions: {result['state']['actions']} | review: {result['state']['review_required']}")
    print(f"Wrote {SYNTHETIC_OUTPUT_DIR / 'priority_sites.csv'}")
    print(f"Wrote {SYNTHETIC_OUTPUT_DIR / 'dashboard.html'}")


def cmd_report(args, config=None):
    experiment = joblib.load(SYNTHETIC_OUTPUT_DIR / "experiment.joblib")
    actions = pd.read_csv(SYNTHETIC_OUTPUT_DIR / "priority_sites.csv")
    benchmark = json.loads((SYNTHETIC_DIR / "benchmark.json").read_text(encoding="utf-8"))
    detailed = write_detailed(experiment, actions, benchmark, SYNTHETIC_OUTPUT_DIR / "RAPORT_DETALIAT_RO.md")
    jury = write_jury(experiment, actions, benchmark, SYNTHETIC_OUTPUT_DIR / "RAPORT_JURI_RO.md")
    print(f"Wrote {detailed}")
    print(f"Wrote {jury}")


def cmd_run(args, config=None):
    if not (SYNTHETIC_DIR / "cities.joblib").exists() or args.refresh:
        cmd_build(args)
    cmd_train(args)
    cmd_agent(args)
    cmd_report(args)


def build_parser():
    parser = argparse.ArgumentParser(description="Synthetic EV placement benchmark")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, func in (("build", cmd_build), ("train", cmd_train), ("agent", cmd_agent), ("report", cmd_report), ("run", cmd_run)):
        command = sub.add_parser(name)
        command.add_argument("--k", type=int, default=8)
        command.add_argument("--refresh", action="store_true")
        command.set_defaults(func=func)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        args.func(args)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
