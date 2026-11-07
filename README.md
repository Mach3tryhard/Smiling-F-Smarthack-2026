# Smiling-F-Smarthack-2026

**EV charging-station placement on a synthetic ground-truth city benchmark.**

The complete project, dataset, trained models and ML methodology live in [`ML-Agent/`](ML-Agent/):

- **[Detailed README](ML-Agent/README.md)** — the full machine-learning logic, feature design, training decisions, evaluation protocol, results, and limitations.
- **[Generated dataset](ML-Agent/data/synthetic/cities.joblib)** — 400 synthetic cities, 501,812 nodes, 36,809 existing stations.
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
