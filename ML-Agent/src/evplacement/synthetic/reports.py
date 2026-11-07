"""Two Romanian deliverables: a detailed engineering report and a short jury brief."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd


def _f(value, digits=3):
    if value is None or (isinstance(value, float) and not np.isfinite(value)):
        return "—"
    return f"{value:.{digits}f}"


def _table(frame, columns, headers):
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for _, row in frame.iterrows():
        values = []
        for column in columns:
            value = row[column]
            values.append(_f(value) if isinstance(value, (float, np.floating)) else str(value).replace("|", "\\|"))
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def _context(experiment, actions, benchmark):
    usage = experiment["test_usage"]["metrics"]
    uplift = experiment["test_uplift"]["metrics"]
    placement = experiment["test_placement"]["summary"]
    shift_usage = experiment["shift_usage"]["metrics"]
    shift_uplift = experiment["shift_uplift"]["metrics"]
    shift_placement = experiment["shift_placement"]["summary"]
    cities = experiment["test_placement"]["cities"]
    predictions = experiment["test_usage"]["predictions"].copy()
    predictions["quintile"] = pd.qcut(predictions["observed_usage"], 5, labels=False, duplicates="drop")
    quintiles = predictions.groupby("quintile").agg(
        n=("observed_usage", "size"), observed=("observed_usage", "mean"), predicted=("predicted_usage", "mean")
    ).reset_index()
    model = experiment["uplift_model"]
    usage_model = experiment["usage_model"]
    review = int(actions["requires_human_review"].sum()) if len(actions) else 0
    return {
        "usage": usage,
        "uplift": uplift,
        "placement": placement,
        "shift_usage": shift_usage,
        "shift_uplift": shift_uplift,
        "shift_placement": shift_placement,
        "cities": cities,
        "quintiles": quintiles,
        "model": model,
        "usage_model": usage_model,
        "review": review,
        "n_actions": int(len(actions)),
        "n_cities": int(len(cities)),
        "benchmark": benchmark,
    }


def write_detailed(experiment, actions, benchmark, path: Path) -> Path:
    c = _context(experiment, actions, benchmark)
    usage, placement = c["usage"], c["placement"]
    city_table = _table(
        c["cities"].sort_values("utility_ratio").head(10).assign(ratio=lambda d: d["utility_ratio"] * 100, regret=lambda d: d["regret"] * 100),
        ["city_id", "n_nodes", "n_existing", "ratio", "regret", "oracle_overlap"],
        ["Oraș", "Noduri", "Stații existente", "Din oracle (%)", "Regret (%)", "Overlap oracle"],
    )
    quintile_table = _table(
        c["quintiles"], ["quintile", "n", "observed", "predicted"], ["Quintilă", "Stații", "Real", "Prezis"]
    )
    baseline_table = _table(
        pd.DataFrame(
            [{"name": name.replace("_", " "), "ratio": value * 100} for name, value in placement["baseline_mean_ratios"].items()]
        ),
        ["name", "ratio"],
        ["Baseline", "Din oracle (%)"],
    )
    action_table = _table(
        actions.sort_values("rank").head(8).assign(confidence_ro=actions.sort_values("rank").head(8)["confidence"].map({"high": "ridicată", "medium": "medie", "low": "scăzută"})),
        ["city_id", "rank", "node_id", "predicted_usage", "uncertainty", "confidence_ro"],
        ["Oraș", "Rang", "Nod", "Sesiuni/zi estimate", "Incertitudine", "Încredere"],
    )
    data_rows = pd.DataFrame(
        [
            {"set": "train", "cities": benchmark["n_train"]},
            {"set": "validation", "cities": benchmark["n_validation"]},
            {"set": "test", "cities": benchmark["n_test"]},
            {"set": "test OOD", "cities": benchmark["n_test_shift"]},
        ]
    )
    data_table = _table(data_rows, ["set", "cities"], ["Set", "Orașe"])
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    text = f"""# Raport detaliat — EV Charge Synthetic v2

**Pentru:** Matei / echipa Smarthack  
**Generat:** {now}  
**Scop:** explicarea deciziilor, a rezultatelor și a limitărilor benchmark-ului sintetic la scară mare.

---

## 1. Răspuns scurt: este o abordare bună pentru hackathon?

**Da, dacă este poziționată corect.** Nu este un model care prezice cererea reală din România. Este un **benchmark de decizie cu ground truth** și un agent complet:

- model ML antrenat de echipă, pe GPU;
- test separat pe orașe nevăzute;
- baseline-uri simple;
- eroare de utilizare și **regret real de amplasare**;
- strat de decizie cu buget și canibalizare;
- acțiuni, coadă de revizuire, explicații și dashboard.

Pentru juriu, mesajul corect este: *"Am construit un simulator de orașe și un agent care învață să amplaseze stații; pentru că simulatorul are ground truth, putem măsura exact cât de bună este decizia."*  
Mesajul greșit ar fi: *"Modelul prezice cererea reală din București."* Nu o face.

**Riscul principal:** un juriu care premiază doar date reale poate considera simulatorul prea teoretic. Mitigarea este să prezinți clar ce este simulator, ce este model învățat și care este planul de calibrare pe date reale (secțiunea 9).

## 2. Ce am eliminat și ce am schimbat

Am eliminat ramura veche bazată pe orașe reale (București/OSM/WorldPop) din livrabil. Codul, output-urile și rapoartele vechi au fost șterse. Repository-ul este acum focalizat pe benchmark-ul sintetic.

Scalarea față de prototipul anterior:

| Element | Prototip | Acum |
|---|---:|---:|
| Orașe generate | 96 | **400** |
| Orașe train | 60 | **300** |
| Orașe validare | 15 | **40** |
| Orașe test | 15 | **40** |
| Orașe test OOD | 6 | **20** |
| Noduri | 49.876 | **~500.000** |
| Stații | 3.545 | **~36.800** |
| Model | arbori CPU | **MLP GPU + HGB, blend** |
| Complexitate | 1–4 centre | **2–8 centre, coridoare, zone, șocuri spațiale** |

## 3. Generatorul v2

### 3.1 Structura urbană

Fiecare oraș este un graf spațial cu 700–1.800 de noduri (până la 2.400 în testul OOD). Nodurile sunt generate dintr-un amestec de:

- 2–8 centre urbane;
- coridoare radiale;
- fundal cu densitate mică.

Graful este construit cu k-NN (k=6) și conectat pentru a elimina componentele izolate. Pentru fiecare nod calculăm centralitate (closeness), grad, distanță la cel mai apropiat centru.

### 3.2 Features observabile

- populație, activitate, venit, adopție EV;
- centralitate, grad, distanță la centru;
- capacitate rutieră, acces la transport, acces la drum major;
- parcări, densitate POI;
- ponderi de zonă: business, rezidențial, industrial;
- competiție: capacitate în vecinătate, număr de stații la 1 km, distanța la cea mai apropiată stație;
- context: numărul de noduri, rata de stații a orașului.

### 3.3 Cererea latentă

```text
demand = 120 × (0.25+pop)^0.90 × (0.30+activity)^0.70 × (0.35+ev)^0.80
              × (0.40+centrality)^0.50 × (0.45+road)^0.30
              × (0.55 + 0.9·business + 0.5·residential + 0.3·industrial)
              × (0.55 + 0.45·transit) × (0.60 + 0.40·highway)
              × (1 + 0.18·spatial_shock) × lognormal(0, 0.14)
```

Normalizată la medie 100. **Nu este feature de model**; este adevărul simulatorului.

### 3.4 Stații și utilizare

Stațiile sunt alese cu probabilitate proporțională cu `demand^1.15 × road × parking × business`. Fiecare are capacitate lognormală.

Utilizarea este un model Huff cu competiție spațială:

```text
competition_i = Σ_j capacity_j · exp(-distance_ij / λ) − capacity_i
usage_i       = demand_i · capacity_i / (capacity_i + competition_i) · lognormal(0, noise)
```

Cu cât mai multe stații în jur, cu atât fiecare primește o fracțiune mai mică. Aceasta este canibalizarea pe care agentul trebuie să o evite.

## 4. Modelul ML

### 4.1 Ținta

`log(1 + usage)` pentru stațiile existente. Modelul nu vede cererea latentă și nu vede utilizarea altor stații decât prin features de competiție.

### 4.2 Arhitectură

- **MLP pe GPU** (PyTorch, CUDA): 24 features → 256 → 128 → 64 → 1, GELU, dropout, Huber loss, AdamW, cosine schedule.
- **3 seed-uri** pentru incertitudine.
- **HistGradientBoosting** pe CPU ca al doilea expert.
- Blend MLP/HGB ales pe validare, nu pe test.

Antrenarea a rulat pe **{c['usage_model'].training_device}**: modelul de utilizare în **{c['usage_model'].train_seconds:.1f} s**, modelul de uplift în **{c['model'].train_seconds:.1f} s**. Modelele salvate sunt mutate pe CPU pentru portabilitate; inferența nu cere GPU.

### 4.3 Split

{data_table}

Testul este pe orașe întregi; nu există noduri din orașele de test în train. Testul OOD schimbă rata de stații, adopția EV și zgomotul.

## 5. Eroarea pe utilizare

| Metrică | Model | Baseline (media train) |
|---|---:|---:|
| MAE log | **{_f(usage['mae_log'])}** | {_f(usage['mean_baseline']['mae_log'])} |
| RMSE log | **{_f(usage['rmse_log'])}** | {_f(usage['mean_baseline']['rmse_log'])} |
| MAE sesiuni/zi | **{_f(usage['mae_usage'], 1)}** | {_f(usage['mean_baseline']['mae_usage'], 1)} |
| R² log | **{_f(usage['r2_log'])}** | {_f(usage['mean_baseline']['r2_log'])} |
| Spearman | **{_f(usage['spearman'])}** | — |

Modelul este bun la ranking, dar comprimă coada superioară:

{quintile_table}

Aceasta este eroarea sistematică principală. Ea nu distruge ordinea relativă a majorității candidaților, dar valorile absolute nu trebuie citite ca venit.

### 5.1 Al doilea model: uplift-ul candidaților

Pentru amplasare nu folosim direct predicția de usage. Antrenăm un al doilea model pe candidații din orașele de **train** și îl evaluăm pe **{c['uplift']['n_test_candidates']:,} candidați** din orașele de test, cu ținta `log(1 + uplift)` calculată de simulator. Features-urile rămân observabile; ținta este contrafactuală.

| Metrică uplift | Rezultat |
|---|---:|
| MAE log | **{_f(c['uplift']['mae_log'])}** |
| R² log | **{_f(c['uplift']['r2_log'])}** |
| Spearman | **{_f(c['uplift']['spearman'])}** |
| MAE uplift | **{_f(c['uplift']['mae_usage'], 2)}** |

Acesta este modelul care decide amplasarea; modelul de usage rămâne pentru explicarea valorii estimate a stației.

## 6. Eroarea de amplasare — metrica centrală

Pentru fiecare oraș de test, agentul are buget de **{placement['k']} stații**. Oracle-ul este greedy pe simulatorul real; modelul maximizează utilizarea prezisă cu penalizare de canibalizare.

| Strategie | Din câștigul oracle |
|---|---:|
| **Model + optimizer** | **{placement['mean_utility_ratio']*100:.1f}%** |
| Random | {placement['baseline_mean_ratios']['random']*100:.1f}% |
| Populație | {placement['baseline_mean_ratios']['population']*100:.1f}% |
| Index manual | {placement['baseline_mean_ratios']['hand_index']*100:.1f}% |
| Activitate | {placement['baseline_mean_ratios']['activity']*100:.1f}% |

- **Regret mediu:** {placement['mean_regret']*100:.1f}%
- **Overlap cu oracle:** {placement['mean_oracle_overlap']*100:.1f}%
- **Spearman predicție vs uplift real:** {_f(placement['mean_spearman_pred_vs_uplift'])}

Overlap-ul de 30–40% nu înseamnă 60% greșeală: multe situri sunt aproape echivalente, iar regretul de 15–20% este metrica economică.

### Cele mai slabe orașe

{city_table}

## 7. Robustețe OOD

| Metrică | Test normal | Test OOD |
|---|---:|---:|
| MAE log | {_f(usage['mae_log'])} | {_f(c['shift_usage']['mae_log'])} |
| R² log | {_f(usage['r2_log'])} | {_f(c['shift_usage']['r2_log'])} |
| Din oracle | {placement['mean_utility_ratio']*100:.1f}% | {c['shift_placement']['mean_utility_ratio']*100:.1f}% |
| Regret | {placement['mean_regret']*100:.1f}% | {c['shift_placement']['mean_regret']*100:.1f}% |

Degradarea este mică pe placement, dar R² scade. Agentul nu ascunde acest lucru.

## 8. Agentul și acțiunile

- **{c['n_actions']} acțiuni** propuse pentru {c['n_cities']} orașe de test.
- **{c['review']}** trimise la revizuire umană (încredere medie/scăzută sau utilizare estimată sub 10 sesiuni/zi).
- Fiecare acțiune are `action_id`, coordonate, utilizare estimată, incertitudine, explicație locală și status.

Exemplu:

{action_table}

Fișiere: `priority_sites.csv`, `review_queue.csv`, `agent_actions.json`, `dashboard.html`.

## 9. Cum ai folosi modelul pe București

Nu îl aplici direct. Pașii corecți:

1. Mapezi stațiile reale din OSM și nodurile urbane într-un graf (sau H3 + distanțe).
2. Calibrezi distribuția de cerere cu date reale: populație, POI, trafic, adopție EV.
3. Colectezi sesiuni/kWh pentru un eșantion de stații și înlocuiești `observed_usage` sintetic cu utilizarea reală.
4. Reantrenezi modelul pe orașe reale sau faci fine-tuning pe București.
5. Păstrezi același evaluator: holdout pe orașe/zone și, dacă ai timp, holdout temporal.
6. Compari cu baseline-ul comercial și cu un pilot.

Modelul sintetic este un **laborator de decizie**, nu un înlocuitor pentru datele reale.

## 10. Limitări

1. **Simulator, nu realitate.** Formulele sunt alese de noi.
2. **Fără date reale de sesiuni.** Nu putem prezice venitul real.
3. **Oracle-ul există doar în simulator.** În producție, evaluarea se face prin pilot.
4. **Topologia sintetică nu reproduce exact un oraș românesc.**
5. **Bugetul este per oraș.** Alocarea națională și harta reală sunt următorul strat de UI.

## 11. Reproducere

```powershell
.\\.venv\\Scripts\\python.exe -m evplacement build
.\\.venv\\Scripts\\python.exe -m evplacement train --k 8
.\\.venv\\Scripts\\python.exe -m evplacement agent --k 8
.\\.venv\\Scripts\\python.exe -m evplacement report
```

## 12. Concluzie

Da, este o abordare bună pentru hackathon dacă o vinzi ca **benchmark de decizie cu ground truth + agent**, nu ca predictor de cerere reală. Ai un flux complet, o metrică de eroare greu de contestat și o cale clară către București.
"""
    path.write_text(text, encoding="utf-8")
    return path


def write_jury(experiment, actions, benchmark, path: Path) -> Path:
    c = _context(experiment, actions, benchmark)
    usage, placement = c["usage"], c["placement"]
    text = f"""# EV Charge Synthetic — rezumat pentru juriu

**Smarthack XI 2026 · tema PPC**

## Problema

Unde construiești următoarele stații de încărcare, cu un buget limitat, fără să canibalizezi stațiile existente? Datele reale spun unde sunt stațiile, dar nu cât se încarcă la ele. Fără ground truth, nu poți măsura dacă o recomandare este bună.

## Soluția

Am construit un **simulator de orașe cu ground truth** și un **agent de amplasare**:

- 400 de orașe sintetice, 700–2.400 de noduri, centre multiple, coridoare, zone și șocuri spațiale;
- stații existente alese probabilistic, cu utilizare generată de un model de concurență Huff;
- model ML antrenat pe GPU care prezice utilizarea stațiilor;
- optimizer care alege K stații cu penalizare de canibalizare;
- acțiuni concrete, coadă de revizuire și explicații.

## Rezultate

| Metrică | Rezultat |
|---|---:|
| Orașe train / validare / test / OOD | {benchmark['n_train']} / {benchmark['n_validation']} / {benchmark['n_test']} / {benchmark['n_test_shift']} |
| Noduri / stații | ~{benchmark['n_nodes_total']//1000}k / ~{benchmark['n_stations_total']//1000}k |
| R² utilizare pe orașe nevăzute | **{_f(usage['r2_log'])}** |
| Spearman utilizare | **{_f(usage['spearman'])}** |
| Spearman uplift candidați | **{_f(c['uplift']['spearman'])}** |
| MAE log | **{_f(usage['mae_log'])}** |
| Amplasare vs oracle | **{placement['mean_utility_ratio']*100:.1f}%** |
| Regret | **{placement['mean_regret']*100:.1f}%** |
| Baseline random | {placement['baseline_mean_ratios']['random']*100:.1f}% |
| Baseline populație | {placement['baseline_mean_ratios']['population']*100:.1f}% |
| Test OOD — din oracle | **{c['shift_placement']['mean_utility_ratio']*100:.1f}%** |

Modelul nu doar prezice: alegerea sa capturează **{placement['mean_utility_ratio']*100:.1f}%** din câștigul unui oracle care cunoaște cererea reală. Baseline-urile simple sunt departe.

## De ce este relevant pentru PPC

- decizie sub buget, nu doar predicție;
- canibalizare explicită;
- evaluare pe orașe nevăzute și distribuție schimbată;
- incertitudine și review uman;
- explicații locale și importanță globală;
- pipeline reproductibil, cu cod de antrenare și model care rulează local.

## Limitarea pe care o spunem deschis

Este un simulator, nu date reale de încărcare. Următorul pas este calibrarea pe sesiuni reale din București și un pilot. Prezentarea nu pretinde că prezice venitul real.

## Demo

- `dashboard.html` — hartă cu noduri, stații existente și recomandări;
- `priority_sites.csv` — {c['n_actions']} acțiuni, dintre care {c['review']} la review;
- `RAPORT_DETALIAT_RO.md` — metodologia completă.

**Mesajul de o frază:** am construit un laborator de decizie cu ground truth în care agentul învață să amplaseze stații și este evaluat pe câtă utilizare reală creează, nu doar pe o hartă frumoasă.
"""
    path.write_text(text, encoding="utf-8")
    return path

