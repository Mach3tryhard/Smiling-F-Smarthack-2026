# Smiling-F-Smarthack-2026

**EV charging-station placement on a synthetic ground-truth city benchmark.**

The ML project, trained models, and methodology live in [`ML-Agent/`](ML-Agent/); the synthetic generator and its dataset live in [`data-generation/`](data-generation/).

- **[Detailed README](ML-Agent/README.md)** — the full machine-learning logic, feature design, training decisions, evaluation protocol, results, and limitations.
- **[Interactive UI](frontend/README.md)** — Charge Quest, a white-canvas tower-defense view of the 320 recommendations.
- **[Data generator](data-generation/README.md)** — the standalone synthetic city generator and its benchmark builder.
- **[Generated dataset](data-generation/data/synthetic/cities.joblib)** — 400 synthetic cities, 501,812 nodes, 36,809 existing stations.
- **[Results](ML-Agent/outputs/synthetic/metrics.json)** — usage R² 0.871 and 85.5% of an oracle's placement value on 40 unseen cities.
- **[Artifacts and demo](ML-Agent/outputs/synthetic/)** — models, predictions, placement results, dashboard, and Romanian reports.

Quick start:

```powershell
cd ML-Agent
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install -e . --no-deps
.\.venv\Scripts\python.exe -m evplacement run --k 8
```

See [Reproducing the benchmark](ML-Agent/README.md#12-reproducing-the-benchmark) for details.

To open the interactive recommendation UI:

```powershell
cd frontend
..\ML-Agent\.venv\Scripts\python.exe server.py
```

See the [frontend README](frontend/README.md) for the white-canvas map, tower details, CSV view, deployment plan, and presentation mode.
