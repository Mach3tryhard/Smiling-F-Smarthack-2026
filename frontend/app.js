(() => {
  "use strict";

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

  const state = {
    data: null,
    cityId: null,
    selectedNode: null,
    whyActionId: null,
    k: 8,
    view: "map",
    confidence: "all",
    reviewOnly: false,
    search: "",
    lbSearch: "",
    lbConfidence: "all",
    lbReview: false,
    csvSearch: "",
    layers: { links: true, demand: false, stations: true },
    highlight: null,
    map: {
      scale: 1,
      tx: 0,
      ty: 0,
      hover: null,
      drag: null,
      moved: false,
      dpr: 1,
      fitted: false,
      autoFit: true,
      fitScale: 1,
      minScale: 0.25,
      maxScale: 60,
    },
  };

  const els = {};
  let canvas;
  let ctx;

  const numberFmt = new Intl.NumberFormat("ro-RO");
  const decimalFmt = (digits) => new Intl.NumberFormat("ro-RO", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
  const fmt = (value, digits = 1) => {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
    const n = Number(value);
    if (Number.isInteger(n) && digits === 0) return numberFmt.format(n);
    return decimalFmt(digits).format(n);
  };
  const pct = (value, digits = 1) => {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
    return `${fmt(Number(value) * 100, digits)}%`;
  };
  const esc = (value) =>
    String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]));

  const currentCity = () => state.data?.cities.find((city) => city.city_id === state.cityId) || null;
  const benchmarkK = () => Number(state.data?.benchmark_k) || 8;
  const kMin = () => Number(state.data?.k_min) || 1;
  const kMax = () => Number(state.data?.k_max) || 12;
  const currentK = () => Math.max(kMin(), Math.min(kMax(), Number(state.k) || benchmarkK()));
  const allActions = () => state.data?.all_actions || state.data?.actions || [];
  const cityKSource = (city) => city?.k_actions || city?.actions || [];
  const cityActions = (city = currentCity()) => cityKSource(city).filter((action) => Number(action.rank) <= currentK());
  const actionsForK = () => allActions().filter((action) => Number(action.rank) <= currentK());
  const currentPlacement = (city = currentCity()) => city?.k_placement?.[String(currentK())] || city?.placement || {};
  const kMetric = () => state.data?.k_metrics?.[String(currentK())] || state.data?.metrics?.test_placement?.summary || state.data?.metrics?.test_placement || {};

  const currentAction = () => {
    const city = currentCity();
    if (!city || state.selectedNode === null) return null;
    return cityActions(city).find((action) => action.node_id === Number(state.selectedNode)) || null;
  };

  const actionAt = (city, nodeId) =>
    cityActions(city).find((action) => Number(action.node_id) === Number(nodeId)) || null;

  const matchesFilters = (action) =>
    (state.confidence === "all" || action.confidence === state.confidence) &&
    (!state.reviewOnly || action.requires_human_review);

  function visibleCityActions() {
    const city = currentCity();
    if (!city) return [];
    return cityActions(city).filter(matchesFilters);
  }

  function syncFilterControls() {
    $$("#confidenceFilters .chip").forEach((chip) => {
      const active = chip.dataset.confidence === state.confidence;
      chip.classList.toggle("is-active", active);
      chip.setAttribute("aria-pressed", String(active));
    });
    const review = $("#reviewOnly");
    if (review) review.checked = state.reviewOnly;
  }

  function renderConfidenceChips() {
    const city = currentCity();
    if (!city) return;
    const actions = cityActions(city);
    const counts = { all: actions.length, high: 0, medium: 0, low: 0 };
    actions.forEach((action) => {
      counts[confidenceClass(action.confidence)] += 1;
    });
    const labels = { all: "Toate", high: "Ridicată", medium: "Medie", low: "Scăzută" };
    $$("#confidenceFilters .chip").forEach((chip) => {
      const key = chip.dataset.confidence;
      chip.innerHTML = `<span>${labels[key]}</span><b>${counts[key]}</b>`;
      chip.classList.toggle("is-empty", key !== "all" && counts[key] === 0);
      const active = key === state.confidence;
      chip.classList.toggle("is-active", active);
      chip.setAttribute("aria-pressed", String(active));
    });
    const hint = $("#filterHint");
    if (hint) {
      hint.textContent = `${counts.high} ridicate · ${counts.medium} medii · ${counts.low} scăzute în acest oraș. Filtrele se aplică hărții și listei.`;
    }
  }

  function ensureSelectionWithinFilters() {
    const city = currentCity();
    if (!city) return;
    const selected = actionAt(city, state.selectedNode);
    if (selected && matchesFilters(selected)) return;
    const first = visibleCityActions()[0];
    state.selectedNode = first ? Number(first.node_id) : null;
  }

  function applyFilterChange() {
    syncFilterControls();
    ensureSelectionWithinFilters();
    renderCityMeta();
    renderCityActions();
    renderDetails();
    drawMap();
  }

  function syncKControl() {
    const input = $("#kInput");
    if (!input) return;
    input.min = String(kMin());
    input.max = String(kMax());
    input.value = String(currentK());
    const hint = $("#kHint");
    if (hint) {
      hint.textContent = currentK() === benchmarkK() ? `K=${currentK()} benchmark` : `K=${currentK()} ${currentK() > benchmarkK() ? "extensie demo" : "sub-buget"}`;
    }
    const note = $("#kNote");
    if (note) {
      note.textContent = currentK() > benchmarkK()
        ? `K=${currentK()} depășește benchmark-ul K=8; recomandările suplimentare sunt o extensie demo generată cu același model.`
        : currentK() < benchmarkK()
          ? `K=${currentK()} afișează primele ${currentK()} recomandări din clasamentul K=8.`
          : "K=8 este benchmark-ul original; 1–8 taie din clasament, 9–12 este o extensie demo.";
    }
  }

  function applyK(value) {
    const next = Math.max(kMin(), Math.min(kMax(), Math.round(Number(value) || benchmarkK())));
    if (next === currentK()) {
      syncKControl();
      return;
    }
    closeWhyModal();
    state.k = next;
    syncKControl();
    ensureSelectionWithinFilters();
    renderAll();
    updateHash();
  }

  const actionById = (id) => allActions().find((action) => action.action_id === id) || null;

  const confidenceLabel = (value) => ({ high: "Ridicată", medium: "Medie", low: "Scăzută" }[value] || value);
  const confidenceClass = (value) => (["high", "medium", "low"].includes(value) ? value : "low");
  const statusLabel = (value) => ({ PROPOSED: "PROPUS", INSTALLED: "INSTALAT", REJECTED: "RESPINS" }[value] || value);

  const badge = (action) => {
    const review = action.requires_human_review
      ? `<span class="badge review"><svg class="icon"><use href="#i-warning"></use></svg>Verificare</span>`
      : `<span class="badge install"><svg class="icon"><use href="#i-check"></use></svg>Recomandat</span>`;
    return `<span class="badge ${confidenceClass(action.confidence)}">${esc(confidenceLabel(action.confidence))} - ${fmt(action.confidence_score, 1)}</span>${review}`;
  };

  const FEATURE_META = {
    population: { label: "Index populație", digits: 2 },
    activity: { label: "Index activitate / POI", digits: 2 },
    income: { label: "Indicator venit", digits: 2 },
    ev_adoption: { label: "Indicator adopție EV", digits: 2 },
    centrality: { label: "Centralitate", digits: 2 },
    road_capacity: { label: "Capacitate rutieră", digits: 2 },
    transit_access: { label: "Acces transport", digits: 2 },
    highway_access: { label: "Acces autostradă", digits: 2 },
    parking: { label: "Index parcare", digits: 2 },
    poi_density: { label: "Densitate POI", digits: 2 },
    dist_center: { label: "Distanță față de centru", digits: 2 },
    degree: { label: "Grad în graf", digits: 0 },
    closeness: { label: "Centralitate de apropiere", digits: 3 },
    zone_business: { label: "Pondere zonă de afaceri", digits: 2 },
    zone_residential: { label: "Pondere zonă rezidențială", digits: 2 },
    zone_industrial: { label: "Pondere zonă industrială", digits: 2 },
    competing_capacity: { label: "Capacitate concurentă", digits: 2 },
    n_stations_1km: { label: "Stații apropiate", digits: 0 },
    nearest_station_dist: { label: "Distanță stație", digits: 3 },
    local_population: { label: "Index populație locală", digits: 2 },
    local_activity: { label: "Index activitate locală", digits: 2 },
    planned_capacity: { label: "Capacitate planificată", digits: 2 },
    city_nodes: { label: "Noduri în oraș", digits: 0 },
    city_station_rate: { label: "Rată stații", digits: 3 },
  };

  const featureMeta = (feature) => FEATURE_META[feature] || { label: String(feature).replaceAll("_", " "), digits: 2 };
  const featureLabel = (feature) => featureMeta(feature).label;
  const featureValue = (feature, value) => fmt(value, featureMeta(feature).digits);

  function selectionSummary(action) {
    const city = currentCity();
    const ordered = city ? [...cityActions(city)].sort((a, b) => a.rank - b.rank) : [];
    const index = ordered.findIndex((item) => item.action_id === action.action_id);
    const next = index >= 0 ? ordered[index + 1] : null;
    const average = ordered.length ? ordered.reduce((sum, item) => sum + Number(item.predicted_uplift || 0), 0) / ordered.length : 0;
    return {
      rank: action.rank,
      total: ordered.length,
      average,
      next,
      deltaAverage: Number(action.predicted_uplift || 0) - average,
      deltaNext: next ? Number(action.predicted_uplift || 0) - Number(next.predicted_uplift || 0) : null,
      isFirst: action.rank === 1,
      isLast: action.rank === ordered.length,
    };
  }

  function parseCsvLine(line) {
    const out = [];
    let current = "";
    let quoted = false;
    for (let index = 0; index < String(line || "").length; index += 1) {
      const char = line[index];
      if (quoted) {
        if (char === '"') {
          if (line[index + 1] === '"') {
            current += '"';
            index += 1;
          } else {
            quoted = false;
          }
        } else {
          current += char;
        }
      } else if (char === '"') {
        quoted = true;
      } else if (char === ",") {
        out.push(current);
        current = "";
      } else {
        current += char;
      }
    }
    out.push(current);
    return out;
  }

  function toast(message) {
    if (!els.toast) return;
    els.toast.textContent = message;
    els.toast.classList.add("show");
    window.clearTimeout(toast._timer);
    toast._timer = window.setTimeout(() => els.toast.classList.remove("show"), 2200);
  }

  function updateHash() {
    const params = new URLSearchParams();
    params.set("view", state.view);
    params.set("k", String(currentK()));
    if (state.cityId) params.set("city", state.cityId);
    if (state.selectedNode !== null) params.set("node", String(state.selectedNode));
    history.replaceState(null, "", `#${params.toString()}`);
  }

  function readHash() {
    const params = new URLSearchParams((location.hash || "").replace(/^#/, ""));
    const view = params.get("view");
    if (["map", "leaderboard", "csv", "model"].includes(view)) state.view = view;
    const requestedK = Number(params.get("k"));
    if (Number.isFinite(requestedK)) state.k = requestedK;
    const city = params.get("city");
    if (city && state.data.cities.some((item) => item.city_id === city)) state.cityId = city;
    const node = params.get("node");
    if (node !== null && Number.isFinite(Number(node))) state.selectedNode = Number(node);
  }

  function cityIndex(direction) {
    const cities = state.data.cities;
    const index = cities.findIndex((city) => city.city_id === state.cityId);
    return (index + direction + cities.length) % cities.length;
  }

  function selectCity(cityId, options = {}) {
    const city = state.data.cities.find((item) => item.city_id === cityId);
    if (!city) return;
    const previousCity = state.cityId;
    state.cityId = city.city_id;
    state.map.fitted = false;
    state.map.autoFit = true;
    const requestedNode = options.node !== undefined ? Number(options.node) : null;
    if (requestedNode !== null && (cityKSource(city).some((action) => action.node_id === requestedNode) || city.nodes[requestedNode] !== undefined)) {
      state.selectedNode = requestedNode;
      const action = actionAt(city, requestedNode);
      if (action && !matchesFilters(action)) {
        state.confidence = "all";
        state.reviewOnly = false;
      }
    } else if (previousCity !== city.city_id) {
      state.selectedNode = cityActions(city)[0]?.node_id ?? null;
    }
    if (state.selectedNode !== null && !cityKSource(city).some((action) => action.node_id === Number(state.selectedNode)) && city.nodes[Number(state.selectedNode)] === undefined) {
      state.selectedNode = cityActions(city)[0]?.node_id ?? null;
    }
    ensureSelectionWithinFilters();
    renderAll();
    window.requestAnimationFrame(() => {
      resizeCanvas();
      fitMap();
    });
    updateHash();
  }

  function selectNode(nodeId, options = {}) {
    const city = currentCity();
    const action = actionAt(city, nodeId);
    if (action && !matchesFilters(action)) {
      state.confidence = "all";
      state.reviewOnly = false;
      syncFilterControls();
    }
    state.selectedNode = Number(nodeId);
    if (options.switchView) setView("map", false);
    renderDetails();
    renderCityActions();
    drawMap();
    updateHash();
  }

  function setView(view, update = true) {
    if (!["map", "leaderboard", "csv", "model"].includes(view)) return;
    state.view = view;
    $$(".tab").forEach((tab) => tab.classList.toggle("is-active", tab.dataset.view === view));
    $$(".view").forEach((panel) => panel.classList.toggle("is-active", panel.id === `view-${view}`));
    if (view === "leaderboard") renderLeaderboard();
    if (view === "csv") renderCsv();
    if (view === "model") renderModel();
    if (view === "map") window.requestAnimationFrame(() => { resizeCanvas(); if (!state.map.fitted) fitMap(); else drawMap(); });
    if (update) updateHash();
  }

  function bindEvents() {
    els.citySelect = $("#citySelect");
    els.citySub = $("#citySub");
    els.cityMiniStats = $("#cityMiniStats");
    els.cityStats = $("#cityStats");
    els.cityScorecard = $("#cityScorecard");
    els.mapTitle = $("#mapTitle");
    els.mapKpis = $("#mapKpis");
    els.mapTooltip = $("#mapTooltip");
    els.cityActionList = $("#cityActionList");
    els.cityActionCount = $("#cityActionCount");
    els.detailsEmpty = $("#detailsEmpty");
    els.detailsContent = $("#detailsContent");
    els.topRecommendations = $("#topRecommendations");
    els.leaderboardBody = $("#leaderboardBody");
    els.csvHeadRow = $("#csvHeadRow");
    els.csvBody = $("#csvBody");
    els.modelKpis = $("#modelKpis");
    els.baselineBars = $("#baselineBars");
    els.featureBars = $("#featureBars");
    els.modelSteps = $("#modelSteps");
    els.cityMosaic = $("#cityMosaic");
    els.toast = $("#toast");
    els.whyModal = $("#whyModal");
    els.whyContent = $("#whyContent");

    $$("[data-view]").forEach((element) => {
      element.addEventListener("click", (event) => {
        event.preventDefault();
        setView(element.dataset.view);
      });
    });

    els.citySelect.addEventListener("change", (event) => selectCity(event.target.value));
    $("#prevCity").addEventListener("click", () => selectCity(state.data.cities[cityIndex(-1)].city_id));
    $("#nextCity").addEventListener("click", () => selectCity(state.data.cities[cityIndex(1)].city_id));
    $("#kMinus").addEventListener("click", () => applyK(currentK() - 1));
    $("#kPlus").addEventListener("click", () => applyK(currentK() + 1));
    $("#kInput").addEventListener("change", (event) => applyK(event.target.value));
    $("#kInput").addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        applyK(event.target.value);
        event.target.blur();
      }
    });

    $$("#confidenceFilters .chip").forEach((chip) => {
      chip.addEventListener("click", () => {
        state.confidence = chip.dataset.confidence;
        applyFilterChange();
      });
    });

    $("#reviewOnly").addEventListener("change", (event) => {
      state.reviewOnly = event.target.checked;
      applyFilterChange();
    });
    $("#searchInput").addEventListener("input", (event) => {
      state.search = event.target.value.trim().toLowerCase();
      renderCityActions();
    });
    $("#layerLinks").addEventListener("change", (event) => {
      state.layers.links = event.target.checked;
      drawMap();
    });
    $("#layerDemand").addEventListener("change", (event) => {
      state.layers.demand = event.target.checked;
      drawMap();
    });
    $("#layerStations").addEventListener("change", (event) => {
      state.layers.stations = event.target.checked;
      drawMap();
    });

    $("#zoomIn").addEventListener("click", () => zoomAt(1.3, canvas.clientWidth / 2, canvas.clientHeight / 2));
    $("#zoomOut").addEventListener("click", () => zoomAt(1 / 1.3, canvas.clientWidth / 2, canvas.clientHeight / 2));
    $("#fitMap").addEventListener("click", () => fitMap());

    canvas.addEventListener("pointerdown", onPointerDown);
    canvas.addEventListener("pointermove", onPointerMove);
    canvas.addEventListener("pointerup", onPointerUp);
    canvas.addEventListener("pointerleave", onPointerLeave);
    canvas.addEventListener("wheel", onWheel, { passive: false });
    canvas.addEventListener("dblclick", onCanvasDoubleClick);

    els.detailsContent.addEventListener("click", onDetailsClick);
    els.cityActionList.addEventListener("click", (event) => {
      const button = event.target.closest("[data-node]");
      if (button) selectNode(button.dataset.node);
    });
    els.topRecommendations.addEventListener("click", (event) => {
      const button = event.target.closest("[data-city][data-node]");
      if (button) {
        selectCity(button.dataset.city, { node: button.dataset.node });
        setView("map");
      }
    });
    els.leaderboardBody.addEventListener("click", onTableClick);
    els.csvBody.addEventListener("click", onTableClick);
    els.cityMosaic.addEventListener("click", (event) => {
      const button = event.target.closest("[data-city]");
      if (button) {
        selectCity(button.dataset.city);
        setView("map");
      }
    });

    $("#lbSearch").addEventListener("input", (event) => {
      state.lbSearch = event.target.value.trim().toLowerCase();
      renderLeaderboard();
    });
    $("#lbConfidence").addEventListener("change", (event) => {
      state.lbConfidence = event.target.value;
      renderLeaderboard();
    });
    $("#lbReview").addEventListener("change", (event) => {
      state.lbReview = event.target.checked;
      renderLeaderboard();
    });
    $("#csvSearch").addEventListener("input", (event) => {
      state.csvSearch = event.target.value.trim().toLowerCase();
      renderCsv();
    });

    $('#closeWhyBtn').addEventListener("click", closeWhyModal);
    els.whyModal.addEventListener("click", (event) => {
      if (event.target === els.whyModal) closeWhyModal();
    });
    window.addEventListener("hashchange", applyHash);
    window.addEventListener("resize", () => {
      resizeCanvas();
      if (state.map.autoFit) fitMap();
      else drawMap();
    });
    document.addEventListener("keydown", onKeyDown);

    const mapWrap = canvas.parentElement;
    if ("ResizeObserver" in window) {
      const observer = new ResizeObserver(() => {
        resizeCanvas();
        if (state.map.autoFit) fitMap();
        else drawMap();
      });
      observer.observe(mapWrap);
    }
  }

  function renderAll() {
    syncKControl();
    renderCityMeta();
    renderConfidenceChips();
    renderCityStats();
    renderCityScorecard();
    renderCityActions();
    renderTopRecommendations();
    renderDetails();
    renderLeaderboard();
    renderCsv();
    renderModel();
    drawMap();
  }

  function renderCityMeta() {
    const city = currentCity();
    if (!city) return;
    els.citySelect.value = city.city_id;
    els.citySub.textContent = `${city.city_id} · ${fmt(city.n_nodes, 0)} noduri · ${fmt(city.n_existing, 0)} stații existente`;
    const actions = cityActions(city);
    const reviews = actions.filter((action) => action.requires_human_review).length;
    const placement = currentPlacement(city);
    els.cityMiniStats.innerHTML = `
      <div class="mini-stat"><span>Recomandate</span><strong>${actions.length}</strong></div>
      <div class="mini-stat"><span>De verificat</span><strong>${reviews}</strong></div>
      <div class="mini-stat"><span>Captură oracol</span><strong>${pct(placement.utility_ratio, 0)}</strong></div>
      <div class="mini-stat"><span>Regret</span><strong>${pct(placement.regret, 0)}</strong></div>
    `;
    els.mapTitle.textContent = city.city_id;
    const visible = visibleCityActions().length;
    const siteLabel = visible === actions.length ? `${actions.length} recomandări` : `${visible} din ${actions.length} situri afișate`;
    els.mapKpis.innerHTML = `
      <span class="map-kpi"><span class="dot dot-node"></span>${fmt(city.n_nodes, 0)} noduri</span>
      <span class="map-kpi"><span class="dot dot-station"></span>${fmt(city.n_existing, 0)} existente</span>
      <span class="map-kpi ${visible === actions.length ? "" : "is-filtered"}"><span class="dot dot-site"></span>${siteLabel}</span>
      <span class="map-kpi">${reviews} de verificat</span>
    `;
  }

  function renderCityStats() {
    const city = currentCity();
    if (!city) return;
    const placement = currentPlacement(city);
    const ratio = Math.max(0, Math.min(100, Number(placement.utility_ratio || 0) * 100));
    els.cityStats.innerHTML = `
      <div class="score-top">
        <div class="score-ring" style="--pct:${ratio.toFixed(1)}"><span>${fmt(ratio, 1)}%</span></div>
        <div class="score-copy"><strong>Captură oracol</strong><span>model vs oracolul greedy bazat pe adevărul de referință</span></div>
      </div>
      <div class="score-rows">
        <div class="score-row"><span>Regret</span><strong>${pct(placement.regret)}</strong></div>
        <div class="score-row"><span>Suprapunere cu oracolul</span><strong>${pct(placement.oracle_overlap)}</strong></div>
        <div class="score-row"><span>Spearman creștere</span><strong>${fmt(placement.spearman_pred_vs_true_uplift, 3)}</strong></div>
        <div class="score-row"><span>Referință aleatoare</span><strong>${pct(placement.random_ratio)}</strong></div>
      </div>
    `;
  }

  function renderCityScorecard() {
    const city = currentCity();
    if (!city) return;
    const p = currentPlacement(city);
    els.cityScorecard.innerHTML = `
      <div class="stat"><span>Creștere model</span><strong>${fmt(p.model_incremental, 1)}</strong><small>sesiuni/zi</small></div>
      <div class="stat"><span>Creștere oracol</span><strong>${fmt(p.oracle_incremental, 1)}</strong><small>sesiuni/zi</small></div>
      <div class="stat"><span>Captură oracol</span><strong>${pct(p.utility_ratio)}</strong><small>din câștigul oracolului</small></div>
      <div class="stat"><span>Regret</span><strong>${pct(p.regret)}</strong><small>1 − captură</small></div>
      <div class="stat wide"><span>Structura orașului</span><strong>${fmt(city.n_nodes, 0)} noduri · ${fmt(city.n_existing, 0)} stații · ${currentK()} propuse</strong><small>oraș simulat, coordonate abstracte</small></div>
    `;
  }

  function activeCityActions() {
    const query = state.search;
    return visibleCityActions().filter((action) => {
      if (!query) return true;
      const text = `${action.action_id} ${action.node_id} ${action.rank} ${action.confidence} ${action.predicted_uplift} ${action.review_reason}`.toLowerCase();
      return text.includes(query);
    });
  }

  function renderCityActions() {
    const city = currentCity();
    if (!city) return;
    const actions = activeCityActions();
    els.cityActionCount.textContent = `${actions.length}/${currentK()}`;
    if (!actions.length) {
      els.cityActionList.innerHTML = `<div class="empty-list">Niciun sit nu corespunde filtrelor.</div>`;
      return;
    }
    els.cityActionList.innerHTML = actions
      .map((action) => {
        const selected = Number(action.node_id) === Number(state.selectedNode);
        const review = action.requires_human_review ? `<svg class="icon"><use href="#i-warning"></use></svg>` : "";
        return `
          <button class="action-item ${selected ? "is-selected" : ""}" data-node="${action.node_id}">
            <span class="action-rank">${action.rank}</span>
            <span><strong>${esc(action.action_id.replace("SYN-", ""))}</strong><small>${review} Nod ${action.node_id} · ${esc(confidenceLabel(action.confidence))}</small></span>
            <span class="action-value">${fmt(action.predicted_uplift, 1)}<small>creștere</small></span>
          </button>`;
      })
      .join("");
  }

  function renderTopRecommendations() {
    const top = actionsForK().sort((a, b) => Number(b.predicted_uplift) - Number(a.predicted_uplift)).slice(0, 6);
    els.topRecommendations.innerHTML = top
      .map((action, index) => `
        <button class="top-item" data-city="${esc(action.city_id)}" data-node="${action.node_id}">
          <span class="top-rank" title="Poziția ${index + 1} în listă">${index + 1}</span>
          <span><strong>${esc(action.city_id)} · Nod ${action.node_id}</strong><small>${esc(confidenceLabel(action.confidence))} încredere · rang ${action.rank} în oraș</small></span>
          <span class="top-value">${fmt(action.predicted_uplift, 1)}<small>creștere</small></span>
        </button>`)
      .join("");
  }

  function driverRows(action, limit = 4) {
    const drivers = Array.isArray(action.drivers) && action.drivers.length
      ? action.drivers
      : (Array.isArray(action.explanation) ? action.explanation.map((item) => ({
          feature: item.feature,
          value: null,
          median: null,
          drop: Number(item.drop_sessions_per_day) || 0,
        })) : []);
    if (!drivers.length) return `<div class="muted" style="font-size:10px">Nu există o explicație locală salvată.</div>`;
    const max = Math.max(...drivers.map((item) => Math.abs(Number(item.drop) || 0)), 1);
    return drivers
      .slice(0, limit)
      .map((item) => {
        const drop = Number(item.drop) || 0;
        const width = Math.max(4, (Math.abs(drop) / max) * 100);
        const hasValues = item.value !== null && item.value !== undefined && item.median !== null && item.median !== undefined;
        return `<div class="why-row">
          <span class="feat"><strong>${esc(featureLabel(item.feature))}</strong><small>${hasValues ? `valoare ${featureValue(item.feature, item.value)} | mediana orașului ${featureValue(item.feature, item.median)}` : "explicație locală"}</small></span>
          <span class="bar"><i style="width:${width.toFixed(1)}%"></i></span>
          <b>${drop > 0 ? "-" : "+"}${fmt(Math.abs(drop), 1)}</b>
        </div>`;
      })
      .join("");
  }

  function contextGrid(action) {
    const city = currentCity();
    const context = action.context || {};
    const medians = city?.medians || {};
    const keys = Object.keys(context);
    if (!keys.length) return `<div class="muted" style="font-size:10px">Nu există valori de context salvate.</div>`;
    return `<div class="context-grid">${keys
      .map((feature) => `<div class="context-item" title="${esc(featureLabel(feature))}"><span>${esc(featureLabel(feature))}</span><strong>${featureValue(feature, context[feature])}</strong><small>mediana orașului ${featureValue(feature, medians[feature])}</small></div>`)
      .join("")}</div>`;
  }

  function selectionSentence(action) {
    const summary = selectionSummary(action);
    const prior = summary.rank - 1;
    const position = summary.isFirst
      ? "A fost primul sit selectat."
      : summary.isLast
        ? "A fost ultimul sit selectat în buget."
        : `A fost selectat după ${prior} ${prior === 1 ? "sit mai bine clasat" : "situri mai bine clasate"}.`;
    const next = summary.next
      ? `Următorul sit selectat (rangul ${summary.next.rank}) are o creștere estimată de ${fmt(summary.next.predicted_uplift, 2)} sesiuni/zi.`
      : "Nu a fost selectat niciun sit cu rang inferior în acest oraș.";
    return `${position} Creșterea estimată pentru acest sit este de ${fmt(action.predicted_uplift, 2)} sesiuni/zi. ${next}`;
  }

  function selectionBlock(action) {
    const summary = selectionSummary(action);
    const nextValue = summary.next ? fmt(summary.next.predicted_uplift, 2) : "-";
    const nextDelta = summary.deltaNext === null ? "-" : `${summary.deltaNext >= 0 ? "+" : ""}${fmt(summary.deltaNext, 2)}`;
    return `<div class="why-selection">
      <div class="why-selection-head"><strong>Rangul ${summary.rank} din ${summary.total}</strong><span>selecție greedy K=${summary.total}</span></div>
      <p>${esc(selectionSentence(action))}</p>
      <div class="why-figures">
        <div><span>Acest sit</span><strong>${fmt(action.predicted_uplift, 2)}</strong><small>sesiuni/zi</small></div>
        <div><span>Media siturilor selectate</span><strong>${fmt(summary.average, 2)}</strong><small>sesiuni/zi</small></div>
        <div><span>Față de medie</span><strong>${summary.deltaAverage >= 0 ? "+" : ""}${fmt(summary.deltaAverage, 2)}</strong><small>sesiuni/zi</small></div>
        <div><span>Următorul selectat</span><strong>${nextValue}</strong><small>${nextDelta} față de următorul</small></div>
      </div>
      <p class="why-note">Optimizatorul este greedy: alege câte un sit, recalculează candidații rămași după o penalizare pentru apropierea de siturile deja selectate și se oprește la K=${summary.total}. Este o ordine de selecție constrânsă, nu un optim global.</p>
    </div>`;
  }

  function renderWhyModal() {
    const action = actionById(state.whyActionId) || currentAction();
    if (!action || !els.whyContent) return;
    const summary = selectionSummary(action);
    const review = action.requires_human_review
      ? `<div class="review-alert"><svg class="icon"><use href="#i-warning"></use></svg><span>${esc(action.review_reason || "Marcat pentru verificare umană.")}</span></div>`
      : "";
    els.whyContent.innerHTML = `
      <div class="why-hero">
        <span class="rank-badge"><small>Rang</small><strong>${action.rank}</strong></span>
        <div>
          <h3>${esc(action.city_id)} | Nod ${action.node_id}</h3>
          <p>${esc(action.action_id)} | ${esc(statusLabel(action.status))}</p>
        </div>
        <div class="badge-row">${badge(action)}</div>
      </div>
      ${selectionBlock(action)}
      <section class="why-section">
        <h4>De ce agentul a ales acest nod</h4>
        <p class="why-note">Fiecare caracteristică este înlocuită cu mediana orașului, iar modelul este reevaluat. Un impact negativ înseamnă că valoarea reală ridică creșterea estimată față de un nod tipic; este o sensibilitate locală, nu un efect cauzal.</p>
        <div class="why-list">${driverRows(action, 5)}</div>
      </section>
      <section class="why-section">
        <h4>Contextul sitului văzut de model</h4>
        ${contextGrid(action)}
      </section>
      <section class="why-section">
        <h4>Încredere și verificare</h4>
        <div class="meter-wrap">
          <div class="meter-label"><span>Scor de încredere</span><span>${fmt(action.confidence_score, 1)} / 100</span></div>
          <div class="meter"><i style="width:${Math.max(0, Math.min(100, action.confidence_score))}%"></i></div>
        </div>
        <p class="why-note">Încrederea provine din dezacordul dintre cele trei seed-uri MLP. Dispersia ansamblului: ${fmt(action.uncertainty, 2)} sesiuni/zi.</p>
        ${review}
      </section>
      <details class="why-csv">
        <summary>Rândul CSV sursă</summary>
        ${action.csv_row
          ? `<div class="csv-block">${esc(action.csv_row)}</div>`
          : `<div class="csv-block csv-unavailable">Disponibil doar pentru K≤8. Recomandările suplimentare pentru K&gt;8 sunt o extensie demo generată cu același model.</div>`}
      </details>
      <p class="why-footnote">Aceasta este o predicție a modelului antrenat pe simulatorul sintetic. Explică o decizie a modelului; nu este o garanție a cererii din lumea reală.</p>
    `;
  }

  function openWhyModal(action) {
    if (!action) return;
    state.whyActionId = action.action_id;
    renderWhyModal();
    els.whyModal.hidden = false;
    $("#closeWhyBtn").focus();
  }

  function closeWhyModal() {
    if (!els.whyModal) return;
    els.whyModal.hidden = true;
    state.whyActionId = null;
  }

  function renderDetails() {
    const city = currentCity();
    const action = currentAction();
    if (!city || state.selectedNode === null) {
      const hidden = city ? currentK() - visibleCityActions().length : 0;
      const note = $("#emptyFilterNote");
      if (note) {
        note.hidden = hidden <= 0;
        note.textContent = hidden > 0 ? `Niciun sit nu corespunde filtrului curent — ${hidden} ${hidden === 1 ? "sit ascuns" : "situri ascunse"}.` : "";
      }
      els.detailsEmpty.hidden = false;
      els.detailsContent.hidden = true;
      return;
    }
    els.detailsEmpty.hidden = true;
    els.detailsContent.hidden = false;

    if (action) {
      const review = action.requires_human_review
        ? `<div class="review-alert"><svg class="icon"><use href="#i-warning"></use></svg><span>${esc(action.review_reason || "Flagged for human review.")}</span></div>`
        : "";
      els.detailsContent.innerHTML = `
        <div class="details-top">
          <div class="details-head">
            <span class="rank-badge"><small>Rang</small><strong>${action.rank}</strong></span>
            <div class="details-title">
              <h2>${esc(action.city_id)} · Nod ${action.node_id}</h2>
              <div class="sub">${esc(action.action_id)} · ${esc(statusLabel(action.status))}</div>
            </div>
          </div>
          <div class="badge-row">${badge(action)}</div>
        </div>
        <div class="details-body">
          <div class="stat-grid">
            <div class="stat"><span>Creștere estimată</span><strong>${fmt(action.predicted_uplift, 2)}</strong><small>sesiuni/zi</small></div>
            <div class="stat"><span>Utilizare estimată</span><strong>${fmt(action.predicted_usage, 2)}</strong><small>sesiuni/zi</small></div>
            <div class="stat"><span>Dispersia ansamblului</span><strong>${fmt(action.uncertainty, 2)}</strong><small>± sesiuni/zi</small></div>
            <div class="stat"><span>Scor de încredere</span><strong>${fmt(action.confidence_score, 1)}</strong><small>/ 100</small></div>
          </div>
          <div class="meter-wrap">
            <div class="meter-label"><span>Indicator de încredere</span><span>${fmt(action.confidence_score, 1)} / 100</span></div>
            <div class="meter"><i style="width:${Math.max(0, Math.min(100, action.confidence_score))}%"></i></div>
          </div>
          ${review}
          <div class="why-detail">
            <div class="why-detail-head"><div class="eyebrow">De ce acest nod</div><span class="pill">Rangul ${action.rank} din ${currentK()}</span></div>
            <p class="why-detail-copy">${esc(selectionSentence(action))}</p>
            <div class="why-list">${driverRows(action, 3)}</div>
            <small class="why-detail-note">Impactul = schimbarea creșterii estimate dacă valoarea este readusă la mediana orașului.</small>
            <button class="btn primary small" data-why-action="${esc(action.action_id)}"><svg class="icon"><use href="#i-search"></use></svg>Explicație completă</button>
          </div>
          <div>
            <div class="eyebrow">Rândul CSV real</div>
            ${action.csv_row
              ? `<div class="csv-block">${esc(action.csv_row)}</div>`
              : `<div class="csv-block csv-unavailable">Rândul CSV este disponibil doar pentru K≤8. Această recomandare este o extensie demo generată pentru K&gt;8.</div>`}
          </div>
          <div class="details-actions">
            <button class="btn ghost small" data-copy-action="${esc(action.action_id)}" ${action.csv_row ? "" : "disabled"}><svg class="icon"><use href="#i-copy"></use></svg>Copiază rândul</button>
            <button class="btn ghost small" data-open-csv="${esc(action.action_id)}"><svg class="icon"><use href="#i-table"></use></svg>Vezi CSV</button>
            <button class="btn ghost small" data-rank-action="${esc(action.action_id)}"><svg class="icon"><use href="#i-chart"></use></svg>Clasament</button>
          </div>
          <div class="details-hint">Dublu-click pe acest sit, pe hartă, pentru explicația completă.</div>
        </div>
      `;
      return;
    }

    const node = city.nodes[Number(state.selectedNode)];
    if (!node) return;
    const [x, y, isStation, demand, capacity, observed] = node;
    const nearest = nearestAction(Number(state.selectedNode));
    const station = isStation
      ? `<div class="stat-grid"><div class="stat"><span>Capacitate</span><strong>${fmt(capacity, 2)}</strong><small>unități simulate</small></div><div class="stat"><span>Utilizare observată</span><strong>${fmt(observed, 1)}</strong><small>sesiuni/zi</small></div></div>`
      : `<div class="stat-grid"><div class="stat"><span>Tip de nod</span><strong>Candidat</strong><small>fără stație existentă</small></div><div class="stat"><span>Cerere simulator</span><strong>${fmt(demand, 1)}</strong><small>index latent</small></div></div>`;
    els.detailsContent.innerHTML = `
      <div class="station-panel">
        <div class="eyebrow">${isStation ? "Stație existentă" : "Nod candidat"}</div>
        <h2>Nod ${state.selectedNode}</h2>
        <p>${isStation ? "Acest nod are deja o stație de încărcare simulată. Este o dovadă, nu o recomandare nouă." : "Acest nod nu a fost selectat de model. Îl poți inspecta, dar nu face parte din setul de recomandări."}</p>
        ${station}
        <div class="score-row"><span>Coordonate</span><strong>${fmt(x, 3)}, ${fmt(y, 3)}</strong></div>
        ${nearest ? `<button class="btn primary small" data-nearest="${nearest.node_id}"><svg class="icon"><use href="#i-map"></use></svg>Cea mai apropiată recomandare · rangul ${nearest.rank}</button>` : ""}
      </div>
    `;
  }

  function nearestAction(nodeId) {
    const city = currentCity();
    const node = city?.nodes[nodeId];
    if (!node || !cityActions(city).length) return null;
    let best = null;
    cityActions(city).forEach((action) => {
      const other = city.nodes[action.node_id];
      if (!other) return;
      const distance = Math.hypot(other[0] - node[0], other[1] - node[1]);
      if (!best || distance < best.distance) best = { ...action, distance };
    });
    return best;
  }

  function onDetailsClick(event) {
    const copyButton = event.target.closest("[data-copy-action]");
    if (copyButton) {
      const action = actionById(copyButton.dataset.copyAction);
      if (action) copyText(action.csv_row, "Rândul CSV a fost copiat.");
      return;
    }
    const whyButton = event.target.closest("[data-why-action]");
    if (whyButton) {
      const action = actionById(whyButton.dataset.whyAction);
      if (action) openWhyModal(action);
      return;
    }
    const csvButton = event.target.closest("[data-open-csv]");
    if (csvButton) {
      setView("csv");
      return;
    }
    const nearestButton = event.target.closest("[data-nearest]");
    if (nearestButton) selectNode(nearestButton.dataset.nearest);
    const rankButton = event.target.closest("[data-rank-action]");
    if (rankButton) {
      const action = actionById(rankButton.dataset.rankAction);
      if (action) openActionInRankings(action);
    }
  }

  function openActionInRankings(action) {
    if (!action) return;
    state.highlight = { city: action.city_id, node: Number(action.node_id) };
    state.lbSearch = "";
    state.lbConfidence = "all";
    state.lbReview = false;
    const search = $("#lbSearch");
    if (search) search.value = "";
    const confidence = $("#lbConfidence");
    if (confidence) confidence.value = "all";
    const review = $("#lbReview");
    if (review) review.checked = false;
    setView("leaderboard");
    window.requestAnimationFrame(() => {
      const row = Array.from(els.leaderboardBody.querySelectorAll("tr[data-node]")).find(
        (tr) => tr.dataset.city === action.city_id && Number(tr.dataset.node) === Number(action.node_id),
      );
      if (row) row.scrollIntoView({ block: "center", behavior: "smooth" });
    });
    toast(`Deschis ${action.action_id} în Clasament`);
  }

  function onTableClick(event) {
    const row = event.target.closest("[data-city][data-node]");
    if (!row) return;
    selectCity(row.dataset.city, { node: row.dataset.node });
    setView("map");
  }

  function renderLeaderboard() {
    if (!state.data) return;
    const query = state.lbSearch;
    const filtered = actionsForK()
      .filter((action) => {
        if (state.lbConfidence !== "all" && action.confidence !== state.lbConfidence) return false;
        if (state.lbReview && !action.requires_human_review) return false;
        if (query) {
          const text = `${action.action_id} ${action.city_id} ${action.node_id} ${action.confidence} ${action.review_reason}`.toLowerCase();
          if (!text.includes(query)) return false;
        }
        return true;
      })
      .sort((a, b) => b.predicted_uplift - a.predicted_uplift);
    els.leaderboardBody.innerHTML = filtered.length
      ? filtered
          .map((action, index) => {
            const selected = action.city_id === state.cityId && Number(action.node_id) === Number(state.selectedNode);
            const highlighted =
              Boolean(state.highlight) &&
              state.highlight.city === action.city_id &&
              Number(state.highlight.node) === Number(action.node_id);
            const rowClass = [selected ? "is-selected" : "", highlighted ? "is-highlighted" : ""].join(" ").trim();
            return `
              <tr data-city="${esc(action.city_id)}" data-node="${action.node_id}" class="${rowClass}">
                <td class="num">${index + 1}</td>
                <td><strong>${esc(action.action_id.replace("SYN-", ""))}</strong><div class="muted-cell">rang ${action.rank}</div></td>
                <td class="city-cell">${esc(action.city_id)}</td>
                <td class="num">${action.node_id}</td>
                <td class="num"><span class="mini-bar"><i style="width:${Math.min(100, (action.predicted_uplift / 45) * 100).toFixed(1)}%"></i></span>${fmt(action.predicted_uplift, 1)}</td>
                <td class="num">${fmt(action.predicted_usage, 1)}</td>
                <td><span class="badge ${confidenceClass(action.confidence)}">${esc(confidenceLabel(action.confidence))}</span></td>
                <td>${action.requires_human_review ? `<span class="badge review"><svg class="icon"><use href="#i-warning"></use></svg>Da</span>` : `<span class="muted-cell">—</span>`}</td>
              </tr>`;
          })
          .join("")
      : `<tr><td colspan="8" class="table-empty">Niciun rând nu corespunde.</td></tr>`;
  }

  function renderCsv() {
    if (!state.data) return;
    const header = state.data.csv_header;
    if (!els.csvHeadRow.children.length) {
      els.csvHeadRow.innerHTML = header.map((name) => `<th>${esc(name)}</th>`).join("");
    }
    const query = state.csvSearch;
    const rows = state.data.actions.filter((action) => {
      if (!query) return true;
      return action.csv_row.toLowerCase().includes(query);
    });
    els.csvBody.innerHTML = rows.length
      ? rows
          .map((action) => {
            const values = parseCsvLine(action.csv_row);
            const selected = action.city_id === state.cityId && Number(action.node_id) === Number(state.selectedNode);
            const cells = header
              .map((name, index) => {
                const value = values[index] ?? "";
                const wrap = ["review_reason", "explanation", "csv_row"].includes(name);
                return `<td class="${wrap ? "wrap" : ""}" title="${esc(value)}">${esc(value)}</td>`;
              })
              .join("");
            return `<tr data-city="${esc(action.city_id)}" data-node="${action.node_id}" class="${selected ? "is-selected" : ""}">${cells}</tr>`;
          })
          .join("")
      : `<tr><td colspan="${header.length}" class="table-empty">Niciun rând nu corespunde.</td></tr>`;
  }

  function renderModel() {
    if (!state.data) return;
    const metrics = state.data.metrics;
    const usage = metrics.test_usage.metrics || metrics.test_usage;
    const uplift = metrics.test_uplift.metrics || metrics.test_uplift;
    const placement = kMetric();
    const shift = metrics.shift_placement.summary || metrics.shift_placement;
    const review = actionsForK().filter((action) => action.requires_human_review).length;
    const cards = [
      ["R² utilizare", fmt(usage.r2_log, 3), "țintă log, orașe nevăzute"],
      ["Spearman utilizare", fmt(usage.spearman, 3), "corelație de rang"],
      ["R² creștere", fmt(uplift.r2_log, 3), "țintă contrafactuală"],
      ["Captură oracol", pct(placement.mean_utility_ratio), `orașe de test K=${currentK()}`],
      ["Captură OOD", pct(shift.mean_utility_ratio), "orașe deplasate, K=8"],
      ["Coadă de verificare", fmt(review, 0), `verificări umane la K=${currentK()}`],
    ];
    els.modelKpis.innerHTML = cards
      .map(([label, value, sub]) => `<div class="kpi"><span>${label}</span><strong>${value}</strong><small>${sub}</small></div>`)
      .join("");

    const baselines = [
      ["Model + optimizator", placement.mean_utility_ratio, true],
      ["Aleator", placement.baseline_mean_ratios.random, false],
      ["Populație", placement.baseline_mean_ratios.population, false],
      ["Index manual", placement.baseline_mean_ratios.hand_index, false],
      ["Activitate", placement.baseline_mean_ratios.activity, false],
    ];
    els.baselineBars.innerHTML = baselines
      .map(([label, value, model]) => `<div class="bar-row ${model ? "is-model" : ""}"><span>${label}</span><span class="track"><i style="width:${Math.min(100, Number(value) * 100).toFixed(1)}%"></i></span><b>${pct(value)}</b></div>`)
      .join("");

    const features = state.data.feature_importance.slice(0, 9);
    const maxFeature = Math.max(...features.map((item) => Number(item.mae_increase) || 0), 0.0001);
    els.featureBars.innerHTML = features
      .map((item) => `<div class="bar-row"><span>${esc(featureLabel(item.feature))}</span><span class="track"><i style="width:${((Number(item.mae_increase) / maxFeature) * 100).toFixed(1)}%"></i></span><b>${fmt(item.mae_increase, 2)}</b></div>`)
      .join("");

    els.modelSteps.innerHTML = [
      ["1", "Simulează adevărul de referință", "Generează 400 de orașe-graf cu cerere ascunsă, stații și competiție Huff."],
      ["2", "Învață două ținte", "Prezice log-utilizarea la stații și creșterea contrafactuală la candidați."],
      ["3", "Optimizează K situri", "Clasament greedy după uplift, cu penalizare spațială pentru canibalizare, reglat pe validare."],
    ]
      .map(([num, title, copy]) => `<div class="step"><span class="step-num">${num}</span><div><strong>${title}</strong><span>${copy}</span></div></div>`)
      .join("");

    const cities = [...state.data.cities].sort((a, b) => {
      const first = a.k_placement?.[String(currentK())]?.utility_ratio || 0;
      const second = b.k_placement?.[String(currentK())]?.utility_ratio || 0;
      return second - first;
    });
    els.cityMosaic.innerHTML = cities
      .map((city) => {
        const placement = city.k_placement?.[String(currentK())] || city.placement;
        const ratio = Math.max(0, Math.min(100, Number(placement.utility_ratio) * 100));
        return `<button class="city-tile" data-city="${esc(city.city_id)}" title="${esc(city.city_id)} · ${pct(placement.utility_ratio)} din oracol">
          <strong>${esc(city.city_id.replace("test_", ""))}</strong><span>${ratio.toFixed(0)}%</span><small>${currentK()} situri</small>
          <div class="tile-bar"><i style="width:${ratio.toFixed(1)}%"></i></div>
        </button>`;
      })
      .join("");
  }

  async function copyText(text, message) {
    try {
      await navigator.clipboard.writeText(text);
      toast(message);
    } catch {
      const area = document.createElement("textarea");
      area.value = text;
      area.style.position = "fixed";
      area.style.opacity = "0";
      document.body.appendChild(area);
      area.select();
      document.execCommand("copy");
      area.remove();
      toast(message);
    }
  }

  function onKeyDown(event) {
    const tag = event.target?.tagName?.toLowerCase();
    if (["input", "select", "textarea"].includes(tag)) return;
    if (event.key === "Escape") {
      if (!els.whyModal.hidden) return closeWhyModal();
      state.selectedNode = null;
      renderDetails();
      renderCityActions();
      drawMap();
      updateHash();
      return;
    }
    if (event.key === "f" || event.key === "F") {
      fitMap();
      return;
    }
    if (event.key === "ArrowRight" || event.key === "ArrowDown" || event.key === "ArrowLeft" || event.key === "ArrowUp") {
      const actions = activeCityActions();
      if (!actions.length) return;
      const currentIndex = actions.findIndex((action) => Number(action.node_id) === Number(state.selectedNode));
      const direction = event.key === "ArrowRight" || event.key === "ArrowDown" ? 1 : -1;
      const next = actions[(currentIndex + direction + actions.length) % actions.length];
      event.preventDefault();
      selectNode(next.node_id);
    }
  }

  /* -------------------------------------------------------------- map */
  function resizeCanvas() {
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    const width = Math.max(1, Math.round(rect.width * dpr));
    const height = Math.max(1, Math.round(rect.height * dpr));
    if (canvas.width !== width || canvas.height !== height) {
      canvas.width = width;
      canvas.height = height;
    }
    state.map.dpr = dpr;
    state.map.width = rect.width;
    state.map.height = rect.height;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  function fitMap() {
    const city = currentCity();
    if (!city || !canvas) return;
    const width = canvas.clientWidth;
    const height = canvas.clientHeight;
    if (!width || !height) return;
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    city.nodes.forEach(([x, y]) => {
      minX = Math.min(minX, x); maxX = Math.max(maxX, x);
      minY = Math.min(minY, y); maxY = Math.max(maxY, y);
    });
    if (!Number.isFinite(minX)) return;
    const padding = Math.max(28, Math.min(width, height) * 0.07);
    const spanX = Math.max(0.0001, maxX - minX);
    const spanY = Math.max(0.0001, maxY - minY);
    const scale = Math.min((width - padding * 2) / spanX, (height - padding * 2) / spanY);
    state.map.scale = scale;
    state.map.fitScale = scale;
    state.map.minScale = scale * 0.6;
    state.map.maxScale = scale * 80;
    state.map.tx = (width - spanX * scale) / 2 - minX * scale;
    state.map.ty = (height - spanY * scale) / 2 - minY * scale;
    state.map.fitted = true;
    state.map.autoFit = true;
    drawMap();
  }

  const worldToScreen = (x, y) => [x * state.map.scale + state.map.tx, y * state.map.scale + state.map.ty];
  const screenToWorld = (x, y) => [(x - state.map.tx) / state.map.scale, (y - state.map.ty) / state.map.scale];

  function drawMap() {
    if (!ctx || !canvas || !state.data) return;
    resizeCanvas();
    const width = canvas.clientWidth;
    const height = canvas.clientHeight;
    ctx.clearRect(0, 0, width, height);
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, width, height);

    const city = currentCity();
    if (!city) return;
    const visibleActions = visibleCityActions();
    const actionsByNode = new Map(visibleActions.map((action) => [Number(action.node_id), action]));
    const selectedAction = currentAction();
    const selectedNodeId = state.selectedNode === null ? null : Number(state.selectedNode);

    if (state.layers.links) {
      ctx.beginPath();
      city.edges.forEach(([a, b]) => {
        const first = city.nodes[a];
        const second = city.nodes[b];
        if (!first || !second) return;
        const [x1, y1] = worldToScreen(first[0], first[1]);
        const [x2, y2] = worldToScreen(second[0], second[1]);
        ctx.moveTo(x1, y1);
        ctx.lineTo(x2, y2);
      });
      ctx.strokeStyle = "rgba(11, 35, 64, 0.075)";
      ctx.lineWidth = 0.8;
      ctx.stroke();
    }

    if (state.layers.demand) {
      const maxDemand = Math.max(...city.nodes.map((node) => Number(node[3]) || 0), 1);
      city.nodes.forEach((node) => {
        const [x, y] = worldToScreen(node[0], node[1]);
        const intensity = Math.min(1, (Number(node[3]) || 0) / maxDemand);
        ctx.beginPath();
        ctx.arc(x, y, 3 + intensity * 5, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(255, 122, 0, ${0.08 + intensity * 0.3})`;
        ctx.fill();
      });
    }

    city.nodes.forEach((node, index) => {
      const [x, y, isStation] = node;
      const [screenX, screenY] = worldToScreen(x, y);
      if (!Number.isFinite(screenX) || !Number.isFinite(screenY)) return;
      const action = actionsByNode.get(index);
      const isStationNode = Number(isStation) === 1;
      if (action) return;
      if (isStationNode && state.layers.stations) return;
      ctx.beginPath();
      ctx.arc(screenX, screenY, isStationNode && state.layers.stations ? 3.2 : 1.7, 0, Math.PI * 2);
      ctx.fillStyle = isStationNode && state.layers.stations ? "#0057b8" : "#cdd9e7";
      ctx.fill();
      if (isStationNode && state.layers.stations) {
        ctx.strokeStyle = "#ffffff";
        ctx.lineWidth = 1;
        ctx.stroke();
      }
    });

    if (state.layers.stations) {
      city.nodes.forEach((node) => {
        if (Number(node[2]) !== 1) return;
        const [x, y] = worldToScreen(node[0], node[1]);
        ctx.beginPath();
        ctx.arc(x, y, 3.5, 0, Math.PI * 2);
        ctx.fillStyle = "#0057b8";
        ctx.fill();
        ctx.strokeStyle = "#ffffff";
        ctx.lineWidth = 1.2;
        ctx.stroke();
      });
    }

    const maxUplift = Math.max(...visibleActions.map((action) => Number(action.predicted_uplift) || 0), 1);
    visibleActions.forEach((action) => {
      const node = city.nodes[action.node_id];
      if (!node) return;
      const [x, y] = worldToScreen(node[0], node[1]);
      const selected = Number(action.node_id) === selectedNodeId;
      const hovered = Number(state.map.hover) === Number(action.node_id);
      const intensity = Math.max(0.18, Math.min(1, Number(action.predicted_uplift) / maxUplift));
      ctx.beginPath();
      ctx.arc(x, y, 13 + intensity * 12, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(255, 122, 0, ${0.05 + intensity * 0.08})`;
      ctx.fill();
      if (hovered || selected) {
        ctx.beginPath();
        ctx.arc(x, y, selected ? 17 : 15, 0, Math.PI * 2);
        ctx.fillStyle = selected ? "rgba(0, 87, 184, 0.10)" : "rgba(255, 122, 0, 0.10)";
        ctx.fill();
      }
      const actionColor = action.requires_human_review ? "#ffd23f" : action.confidence === "medium" ? "#f4a300" : "#ff7a00";
      ctx.beginPath();
      ctx.arc(x, y, selected ? 11 : 9.5, 0, Math.PI * 2);
      ctx.fillStyle = actionColor;
      ctx.fill();
      ctx.strokeStyle = selected ? "#0b2340" : "#ffffff";
      ctx.lineWidth = selected ? 2.5 : 2;
      ctx.stroke();
      ctx.beginPath();
      ctx.arc(x, y, 6.6, 0, Math.PI * 2);
      ctx.fillStyle = "#ffffff";
      ctx.fill();
      ctx.fillStyle = "#0b2340";
      ctx.font = "800 9px Inter, Segoe UI, sans-serif";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(String(action.rank), x, y + 0.5);
    });

    if (selectedAction) {
      const node = city.nodes[selectedAction.node_id];
      if (node) {
        const [x, y] = worldToScreen(node[0], node[1]);
        ctx.beginPath();
        ctx.arc(x, y, 18, 0, Math.PI * 2);
        ctx.strokeStyle = "rgba(0, 87, 184, 0.35)";
        ctx.lineWidth = 2;
        ctx.setLineDash([4, 4]);
        ctx.stroke();
        ctx.setLineDash([]);
      }
    }
  }

  function hitTest(clientX, clientY) {
    const city = currentCity();
    if (!city || !canvas) return null;
    const rect = canvas.getBoundingClientRect();
    const x = clientX - rect.left;
    const y = clientY - rect.top;
    let best = null;
    visibleCityActions().forEach((action) => {
      const node = city.nodes[action.node_id];
      if (!node) return;
      const [sx, sy] = worldToScreen(node[0], node[1]);
      const distance = Math.hypot(sx - x, sy - y);
      if (distance < 16 && (!best || distance < best.distance)) best = { node: action.node_id, distance };
    });
    if (best) return best.node;
    city.nodes.forEach((node, index) => {
      if (Number(node[2]) === 0) return;
      const [sx, sy] = worldToScreen(node[0], node[1]);
      const distance = Math.hypot(sx - x, sy - y);
      if (distance < 10 && (!best || distance < best.distance)) best = { node: index, distance };
    });
    if (best) return best.node;
    city.nodes.forEach((node, index) => {
      const [sx, sy] = worldToScreen(node[0], node[1]);
      const distance = Math.hypot(sx - x, sy - y);
      if (distance < 7 && (!best || distance < best.distance)) best = { node: index, distance };
    });
    return best ? best.node : null;
  }

  function showTooltip(clientX, clientY, nodeId) {
    const city = currentCity();
    if (!city) return;
    const action = cityActions(city).find((item) => Number(item.node_id) === Number(nodeId));
    const node = city.nodes[nodeId];
    if (!node) return;
    const label = action
      ? `Rang ${action.rank} | ${esc(action.action_id)}`
      : Number(node[2]) === 1
        ? "Stație de încărcare existentă"
        : "Nod candidat";
    const driver = action?.drivers?.[0];
    const driverLine = driver
      ? `<span class="tip-driver">Factor principal: ${esc(featureLabel(driver.feature))} = ${featureValue(driver.feature, driver.value)} (mediana orașului ${featureValue(driver.feature, driver.median)})</span>`
      : "";
    const hint = action ? `<span class="tip-hint">Click pentru detalii | dublu-click pentru trasabilitatea deciziei</span>` : "";
    els.mapTooltip.innerHTML = `<strong>Nod ${nodeId}</strong>${label}<br>${action ? `${fmt(action.predicted_uplift, 1)} creștere | încredere ${esc(confidenceLabel(action.confidence))}` : `cerere ${fmt(node[3], 1)}`}${driverLine}${hint}`;
    const rect = canvas.getBoundingClientRect();
    const wrapRect = canvas.parentElement.getBoundingClientRect();
    els.mapTooltip.hidden = false;
    els.mapTooltip.style.left = `${clientX - wrapRect.left}px`;
    els.mapTooltip.style.top = `${clientY - wrapRect.top}px`;
  }

  function hideTooltip() {
    if (els.mapTooltip) els.mapTooltip.hidden = true;
  }

  function onPointerDown(event) {
    if (event.button !== 0) return;
    canvas.setPointerCapture?.(event.pointerId);
    state.map.drag = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      tx: state.map.tx,
      ty: state.map.ty,
      moved: false,
    };
  }

  function onPointerMove(event) {
    if (state.map.drag) {
      const dx = event.clientX - state.map.drag.startX;
      const dy = event.clientY - state.map.drag.startY;
      if (Math.abs(dx) + Math.abs(dy) > 3) state.map.drag.moved = true;
      if (state.map.drag.moved) {
        state.map.autoFit = false;
        state.map.tx = state.map.drag.tx + dx;
        state.map.ty = state.map.drag.ty + dy;
        canvas.style.cursor = "grabbing";
        hideTooltip();
        drawMap();
      }
      return;
    }
    const nodeId = hitTest(event.clientX, event.clientY);
    if (nodeId === null) {
      state.map.hover = null;
      hideTooltip();
      canvas.style.cursor = "crosshair";
      drawMap();
      return;
    }
    if (state.map.hover !== nodeId) {
      state.map.hover = nodeId;
      drawMap();
    }
    canvas.style.cursor = "pointer";
    showTooltip(event.clientX, event.clientY, nodeId);
  }

  function onPointerUp(event) {
    const drag = state.map.drag;
    state.map.drag = null;
    canvas.style.cursor = "crosshair";
    if (!drag) return;
    if (drag.moved) {
      drawMap();
      return;
    }
    const nodeId = hitTest(event.clientX, event.clientY);
    if (nodeId !== null) selectNode(nodeId);
  }

  function onPointerLeave() {
    state.map.drag = null;
    state.map.hover = null;
    hideTooltip();
    canvas.style.cursor = "crosshair";
    drawMap();
  }

  function onWheel(event) {
    event.preventDefault();
    const rect = canvas.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    // Normalise mouse wheels (delta ~100) and trackpads (delta ~1–10) so both
    // feel like the same zoom speed.
    const intensity = Math.min(2.5, Math.max(0.6, Math.abs(event.deltaY || 0) / 100));
    const factor = event.deltaY < 0 ? 1 + 0.16 * intensity : 1 / (1 + 0.16 * intensity);
    zoomAt(factor, x, y);
  }

  function zoomAt(factor, screenX, screenY) {
    const fit = state.map.fitScale || state.map.scale || 1;
    const minScale = Math.max(1e-6, state.map.minScale || fit * 0.6);
    const maxScale = Math.max(minScale * 1.5, state.map.maxScale || fit * 80);
    const nextScale = Math.max(minScale, Math.min(maxScale, state.map.scale * factor));
    if (Math.abs(nextScale - state.map.scale) < 1e-9) return;
    // Keep the world point under the cursor fixed while zooming.
    const [worldX, worldY] = screenToWorld(screenX, screenY);
    state.map.autoFit = false;
    state.map.scale = nextScale;
    state.map.tx = screenX - worldX * nextScale;
    state.map.ty = screenY - worldY * nextScale;
    drawMap();
  }

  function onCanvasDoubleClick(event) {
    const city = currentCity();
    const nodeId = hitTest(event.clientX, event.clientY);
    const action = actionAt(city, nodeId);
    if (action) {
      openWhyModal(action);
      return;
    }
    fitMap();
    toast("Harta a fost încadrată pe oraș");
  }

  function populateCities() {
    els.citySelect.innerHTML = state.data.cities
      .map((city) => `<option value="${esc(city.city_id)}">${esc(city.city_id)}</option>`)
      .join("");
  }

  function applyHash() {
    const beforeCity = state.cityId;
    const beforeView = state.view;
    readHash();
    state.k = currentK();
    if (!state.cityId) state.cityId = state.data.demo_city;
    if (!state.data.cities.some((city) => city.city_id === state.cityId)) state.cityId = state.data.demo_city;
    if (state.selectedNode === null) {
      const city = currentCity();
      state.selectedNode = city?.actions[0]?.node_id ?? null;
    }
    renderAll();
    setView(state.view, false);
    window.requestAnimationFrame(() => { resizeCanvas(); fitMap(); });
    if (beforeCity !== state.cityId || beforeView !== state.view) window.scrollTo({ top: 0, behavior: "smooth" });
  }

  async function init() {
    try {
      const response = await fetch("data/dashboard.json", { cache: "no-store" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      state.data = await response.json();
    } catch (error) {
      document.body.innerHTML = `<main style="max-width:640px;margin:10vh auto;font-family:Inter,sans-serif;padding:24px;border:2px solid #0b2340;border-radius:20px;box-shadow:0 4px 0 #d5e3f2"><h1 style="font-family:Fredoka,sans-serif">Demonstrația nu a putut fi încărcată</h1><p>Pornește serverul local din <code>frontend/</code>: <code>python server.py</code>, apoi deschide URL-ul afișat.</p><p style="color:#5e768e">${esc(error.message)}</p></main>`;
      return;
    }
    readHash();
    state.k = currentK();
    if (!state.cityId) state.cityId = state.data.demo_city;
    canvas = $("#mapCanvas");
    ctx = canvas.getContext("2d");
    bindEvents();
    populateCities();
    const city = currentCity();
    if (state.selectedNode === null) state.selectedNode = city?.actions[0]?.node_id ?? null;
    renderAll();
    setView(state.view, false);
    window.requestAnimationFrame(() => { resizeCanvas(); fitMap(); });
    window.setTimeout(() => { resizeCanvas(); fitMap(); }, 120);
  }

  init();

  // Small handle for local debugging and the automated UI check in tools/ui_check.py.
  window.__ppc = {
    state,
    currentCity,
    visibleCityActions,
    worldToScreen,
    fitMap,
    zoomAt,
    openActionInRankings,
  };
})();


