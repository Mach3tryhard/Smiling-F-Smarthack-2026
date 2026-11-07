# Raport detaliat — EV Charge Synthetic v2

**Pentru:** Matei / echipa Smarthack  
**Generat:** 2026-11-07 22:56 UTC  
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

Antrenarea a rulat pe **cuda**: modelul de utilizare în **17.6 s**, modelul de uplift în **67.7 s**. Modelele salvate sunt mutate pe CPU pentru portabilitate; inferența nu cere GPU.

### 4.3 Split

| Set | Orașe |
|---|---|
| train | 300 |
| validation | 40 |
| test | 40 |
| test OOD | 20 |

Testul este pe orașe întregi; nu există noduri din orașele de test în train. Testul OOD schimbă rata de stații, adopția EV și zgomotul.

## 5. Eroarea pe utilizare

| Metrică | Model | Baseline (media train) |
|---|---:|---:|
| MAE log | **0.166** | 0.502 |
| RMSE log | **0.214** | 0.622 |
| MAE sesiuni/zi | **2.1** | 5.7 |
| R² log | **0.871** | -0.089 |
| Spearman | **0.931** | — |

Modelul este bun la ranking, dar comprimă coada superioară:

| Quintilă | Stații | Real | Prezis |
|---|---|---|---|
| 0.000 | 667.000 | 3.456 | 3.882 |
| 1.000 | 666.000 | 6.343 | 6.735 |
| 2.000 | 667.000 | 9.110 | 9.391 |
| 3.000 | 666.000 | 13.026 | 12.907 |
| 4.000 | 667.000 | 23.289 | 19.907 |

Aceasta este eroarea sistematică principală. Ea nu distruge ordinea relativă a majorității candidaților, dar valorile absolute nu trebuie citite ca venit.

### 5.1 Al doilea model: uplift-ul candidaților

Pentru amplasare nu folosim direct predicția de usage. Antrenăm un al doilea model pe candidații din orașele de **train** și îl evaluăm pe **43,776 candidați** din orașele de test, cu ținta `log(1 + uplift)` calculată de simulator. Features-urile rămân observabile; ținta este contrafactuală.

| Metrică uplift | Rezultat |
|---|---:|
| MAE log | **0.352** |
| R² log | **0.735** |
| Spearman | **0.801** |
| MAE uplift | **1.35** |

Acesta este modelul care decide amplasarea; modelul de usage rămâne pentru explicarea valorii estimate a stației.

## 6. Eroarea de amplasare — metrica centrală

Pentru fiecare oraș de test, agentul are buget de **8 stații**. Oracle-ul este greedy pe simulatorul real; modelul maximizează utilizarea prezisă cu penalizare de canibalizare.

| Strategie | Din câștigul oracle |
|---|---:|
| **Model + optimizer** | **85.5%** |
| Random | 8.7% |
| Populație | 11.3% |
| Index manual | 7.5% |
| Activitate | 5.2% |

- **Regret mediu:** 14.5%
- **Overlap cu oracle:** 41.2%
- **Spearman predicție vs uplift real:** 0.845

Overlap-ul de 30–40% nu înseamnă 60% greșeală: multe situri sunt aproape echivalente, iar regretul de 15–20% este metrica economică.

### Cele mai slabe orașe

| Oraș | Noduri | Stații existente | Din oracle (%) | Regret (%) | Overlap oracle |
|---|---|---|---|---|---|
| test_204619 | 984 | 55 | 60.779 | 39.221 | 0.125 |
| test_204615 | 763 | 44 | 70.683 | 29.317 | 0.250 |
| test_204637 | 1105 | 90 | 75.491 | 24.509 | 0.375 |
| test_204614 | 1551 | 78 | 76.906 | 23.094 | 0.250 |
| test_204606 | 1374 | 134 | 76.977 | 23.023 | 0.250 |
| test_204612 | 1274 | 99 | 78.108 | 21.892 | 0.250 |
| test_204613 | 1575 | 63 | 78.208 | 21.792 | 0.250 |
| test_204634 | 975 | 95 | 80.003 | 19.997 | 0.500 |
| test_204638 | 1374 | 50 | 81.296 | 18.704 | 0.250 |
| test_204618 | 888 | 81 | 82.141 | 17.859 | 0.500 |

## 7. Robustețe OOD

| Metrică | Test normal | Test OOD |
|---|---:|---:|
| MAE log | 0.166 | 0.222 |
| R² log | 0.871 | 0.789 |
| Din oracle | 85.5% | 88.4% |
| Regret | 14.5% | 11.6% |

Degradarea este mică pe placement, dar R² scade. Agentul nu ascunde acest lucru.

## 8. Agentul și acțiunile

- **320 acțiuni** propuse pentru 40 orașe de test.
- **14** trimise la revizuire umană (încredere medie/scăzută sau utilizare estimată sub 10 sesiuni/zi).
- Fiecare acțiune are `action_id`, coordonate, utilizare estimată, incertitudine, explicație locală și status.

Exemplu:

| Oraș | Rang | Nod | Sesiuni/zi estimate | Incertitudine | Încredere |
|---|---|---|---|---|---|
| test_204604 | 1 | 259 | 23.520 | 4.250 | ridicată |
| test_204605 | 1 | 556 | 28.540 | 1.230 | ridicată |
| test_204607 | 1 | 814 | 34.010 | 0.260 | ridicată |
| test_204606 | 1 | 1368 | 11.280 | 0.250 | ridicată |
| test_204634 | 1 | 29 | 13.920 | 0.450 | ridicată |
| test_204635 | 1 | 210 | 18.760 | 1.370 | ridicată |
| test_204633 | 1 | 574 | 34.590 | 4.240 | ridicată |
| test_204632 | 1 | 982 | 30.810 | 0.350 | ridicată |

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
.\.venv\Scripts\python.exe -m evplacement build
.\.venv\Scripts\python.exe -m evplacement train --k 8
.\.venv\Scripts\python.exe -m evplacement agent --k 8
.\.venv\Scripts\python.exe -m evplacement report
```

## 12. Concluzie

Da, este o abordare bună pentru hackathon dacă o vinzi ca **benchmark de decizie cu ground truth + agent**, nu ca predictor de cerere reală. Ai un flux complet, o metrică de eroare greu de contestat și o cale clară către București.
