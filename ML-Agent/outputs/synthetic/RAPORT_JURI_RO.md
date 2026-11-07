# EV Charge Synthetic — rezumat pentru juriu

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
| Orașe train / validare / test / OOD | 300 / 40 / 40 / 20 |
| Noduri / stații | ~501k / ~36k |
| R² utilizare pe orașe nevăzute | **0.871** |
| Spearman utilizare | **0.931** |
| Spearman uplift candidați | **0.801** |
| MAE log | **0.166** |
| Amplasare vs oracle | **85.5%** |
| Regret | **14.5%** |
| Baseline random | 8.7% |
| Baseline populație | 11.3% |
| Test OOD — din oracle | **88.4%** |

Modelul nu doar prezice: alegerea sa capturează **85.5%** din câștigul unui oracle care cunoaște cererea reală. Baseline-urile simple sunt departe.

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
- `priority_sites.csv` — 320 acțiuni, dintre care 14 la review;
- `RAPORT_DETALIAT_RO.md` — metodologia completă.

**Mesajul de o frază:** am construit un laborator de decizie cu ground truth în care agentul învață să amplaseze stații și este evaluat pe câtă utilizare reală creează, nu doar pe o hartă frumoasă.
