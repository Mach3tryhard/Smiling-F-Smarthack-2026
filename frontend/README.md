# PPC EV Siting Lab

A standalone, white-canvas decision-support UI for the **synthetic EV charging placement benchmark**. It turns the benchmark's 320 agent recommendations into a ranked map and site-inspection workflow: each recommendation shows predicted uplift, confidence, uncertainty, a local explanation, and the exact source CSV row.

The visual language combines PPC's clean energy palette (navy, blue, teal, orange) with a bold, card-based editorial style: strong outlines, offset shadows, clear rank badges, warm accent colour, and compact data panels. No game assets or game terminology are used.

![Site map view](preview.png)

![Model results view](preview-model.png)

## Why the map is blank white

The city is a synthetic graph. There is **no basemap, no streets, and no imagery** on purpose: a real map would imply that the normalized node coordinates are geographic, and the city outline would distract from the node positions. The canvas shows only:

- small grey dots = synthetic urban nodes;
- faint links = graph edges;
- blue dots = existing stations;
- orange/amber dots with rank numbers = recommended new sites.

Everything is drawn on white so the recommendation pattern is the only thing that matters.

## Features

### Site map
- Pure white canvas, no tile layer.
- Pan, wheel zoom, fit-to-city, double-click fit.
- Existing stations, recommendation ranks, review flags, optional graph links, optional simulator-demand layer.
- Hover tooltip and click-to-inspect hit testing.
- Abstract coordinates are labelled as such.

### Site inspection
Select any recommended node (or a row) to see:
- rank badge and action ID;
- **confidence level and 0–100 confidence score**;
- predicted uplift, predicted usage, ensemble spread;
- review reason if the action needs human review;
- local occlusion explanation (“Why this site”), with bars;
- the **actual `priority_sites.csv` row**;
- copy row and jump to the CSV view.

Selecting an existing station or a plain candidate node also works; the panel explains what that node is and points to the nearest recommendation.

### City controls
- 40 test cities.
- Confidence filter (all/high/medium/low).
- Review-queue-only filter.
- Search by node, action, rank, or confidence.
- City scorecard: oracle capture, regret, oracle overlap, Spearman, baseline.

### Rankings
- All 320 recommendations ranked by predicted incremental sessions/day.
- Confidence and review filters, search.
- Select any row to jump to the node on the map.

### CSV data
- The exact `priority_sites.csv` data, all 16 columns, horizontally scrollable.
- Search across the raw row.
- Select a row to inspect the node.
- Download the original CSV.

### Model view
- Headline metrics: usage R², Spearman, uplift R², oracle capture, OOD capture, review count.
- Model vs random/population/hand-index/activity baseline bars.
- Permutation feature-importance bars.
- “How a site is selected” three-step explainer.
- 40-city scorecard mosaic.
- Scope note: synthetic benchmark, not a real Romanian demand forecast.

### Interaction
- Keyboard: `←`/`→` cycle recommendations, `Esc` clears the selection, `F` fits the map.
- URL hash preserves city/node/view state.
- Responsive layout; mobile puts the map first.

## Run

From the repository root:

```powershell
cd frontend
..\ML-Agent\.venv\Scripts\python.exe server.py
```

The server prints a URL (default `http://127.0.0.1:8000/`, auto-increments if busy) and opens it. No build step, no npm, no extra Python dependencies.

### Rebuild the demo data

The frontend reads a generated bundle, not the 261 MB `cities.joblib` directly:

```powershell
cd frontend
..\ML-Agent\.venv\Scripts\python.exe tools\build_data.py
```

It reads:

- `data-generation/data/synthetic/cities.joblib`
- `ML-Agent/outputs/synthetic/priority_sites.csv`
- `ML-Agent/outputs/synthetic/placement_results.csv`
- `ML-Agent/outputs/synthetic/review_queue.csv`
- `ML-Agent/outputs/synthetic/metrics.json`
- `ML-Agent/outputs/synthetic/feature_importance.csv`
- `ML-Agent/outputs/synthetic/agent_state.json`
- `data-generation/data/synthetic/benchmark.json`

and writes `data/dashboard.json` (40 cities, 320 recommendations, ~4 MB) plus copies of the human-readable CSV/JSON artifacts.

## Files

```text
frontend/
├── index.html              # app shell and inline SVG icon sprite
├── styles.css              # white-canvas editorial/utility theme
├── app.js                  # canvas map, state, details, tables
├── server.py               # dependency-free static server
├── data/                   # generated bundle + copied CSV/JSON artifacts
├── tools/build_data.py     # artifacts → UI JSON
├── preview.png             # site map view
├── preview-leaderboard.png
├── preview-csv.png
├── preview-model.png
└── preview-mobile.png
```

## Design notes

- **White canvas, no basemap.** A deliberate data-literacy choice.
- **Site cards, not pins.** A recommendation is a decision unit: rank, value, confidence, risk.
- **Confidence is not a probability.** It is derived from disagreement across the three MLP seeds; the meter explains this.
- **The CSV is first-class.** The UI never hides the underlying artifact; the exact row is shown on selection.
- **Model view is separate.** The map is the product; the model tab documents the evidence and caveats.
- **No external map or chart library.** Canvas 2D and hand-built SVG/CSS keep the demo portable and offline-friendly (Google Fonts degrade gracefully to system fonts).

## Limitations

- The benchmark is synthetic; absolute sessions/day are simulator quantities.
- Confidence is a heuristic triage signal, not a calibrated interval.
- The map is not geographic; normalized coordinates are not lon/lat.
- The UI displays the existing `priority_sites.csv`; it does not retrain or re-run the agent in the browser.
- The page needs a local HTTP server for `fetch()`; opening `index.html` directly from disk will not load the JSON bundle.
