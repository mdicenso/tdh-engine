# Wedge — motore di allocazione budget promo per mercato estero

Fetta verticale (MVP) del motore-prodotto: una sola decisione, end-to-end.
**Input** (fonti proxy) → **metodo** (regressione lagged + stagionalità esplicita)
→ **output decisionale difendibile** (raccomandazione + evidenza + effetto con
intervallo + confidenza + meccanismo + rischio).

## Cosa fa — e cosa NON fa
- **Fa**: ordina i mercati per *momentum del segnale leading × valore economico ×
  fattibilità*, con incertezza calibrata, in un formato spiegabile in sala.
- **Non fa**: NON stima l'effetto causale della spesa promo ("metti €X → +Y presenze").
  Quella è una pretesa causale che richiede un disegno quasi-sperimentale
  (geo-experiment, diff-in-diff, synthetic control) ed è un modulo successivo.
  Promettere il causale con questi dati = indifendibile.

## Modello del primo giro (trasparente per la sala)
```
presenze_t = β0
           + β_search · search_(t−L)     ← segnale leading, lag L stimato
           + β_fx     · fx_t             ← driver cambio (solo mercati non-Euro)
           + Σ effetti_mese              ← stagionalità ESPLICITA (11 dummy)
           + β_t · t                     ← trend
           + ε
```
Ogni coefficiente ha una frase in italiano corrente (`FitResult.coefficient_reading()`).
**Barriera di onestà**: il modello deve battere la *naive stagionale*; se non la batte,
il mercato si etichetta "segnale insufficiente" e non si forecasta.

## Esecuzione
```bash
pip install pandas numpy statsmodels
python run_wedge.py
```
Stampa il ranking, una scheda decisionale, la lettura dei coefficienti per l'assessore,
e salva `decision_output.json`.

## Dati: da sintetico a reale
Oggi gira su `SyntheticProvider` (pannello con lead-lag e stagionalità *piantati*,
per collaudare che il motore li recuperi). Per i dati veri, implementa
`RealPanelProvider.monthly_panel()` in `tourism_wedge/data.py`:

| Colonna     | Ruolo            | Fonte reale (rete aperta)                          |
|-------------|------------------|----------------------------------------------------|
| `presences` | target (lagging) | ISTAT, movimento clienti per provenienza (SDMX)    |
| `search`    | segnale leading  | Google Trends via `pytrends`, geo = paese origine  |
| `fx`        | driver           | ECB Statistical Data Warehouse (EXR)               |
| valore €/visitatore | peso       | Banca d'Italia, indagine turismo internazionale    |
| capacità voli       | vincolo    | Eurostat `avia_par`                                |

Il motore non cambia: si sostituisce l'adattatore e basta.

## Struttura
```
tourism_wedge/
  data.py      adattatori + Market + SyntheticProvider + stub RealPanelProvider
  engine.py    stima lag, fit modello interpretabile, backtest vs naive, forecast + PI, confidenza
  decision.py  schede decisionali + ranking di portafoglio
run_wedge.py   orchestrazione + output leggibile + JSON
```

## Motore statistico (stato attuale)
Spina dorsale: modello lineare **OLS** (stagionalità esplicita + trend + dummy COVID)
con **barriera di onestà** — si prevede solo se si batte la *naive stagionale* nel backtest.

**Tier 1 — sfidanti nelle proiezioni** (`tdhlib.project_seasonal_best`): per ogni serie
gareggiano OLS · **ETS/Holt-Winters** · **SARIMAX** · **stato latente (UnobservedComponents)**
e si tiene il modello con l'errore di backtest più basso (skill riportato vs naive). Il trend
annuale (`project_var`) ha l'opzione **robusta** (Huber) per gli outlier tipo COVID.

**Tier 2 — struttura tra regioni**: **partial pooling** empirical-Bayes
(`partial_pool_slopes`) per stabilizzare le serie corte verso la media nazionale, e
**riconciliazione** gerarchica Italia↔regioni (`reconcile_bottom_up`). Calcolo offline in
`tier2_structural.py` → artefatto `.cache/tier2_pooled_trends.json`, letto dalla Scheda Regione.

**Evidenza**: i bake-off (`bakeoff.py`, `bakeoff_natl.py`) sui dati reali mostrano che i modelli
complessi NON battono di norma la naive stagionale (segnale ~95% autoregressivo) → la complessità
si attiva solo se supera il backtest. Analisi completa: `@_scorciatoie/TDH_Studio_Modelli.docx`.

Confine invariato: **ranking decisionale**, NON stima causale della spesa promozionale.

> Regola di progetto: ad ogni modifica che cambia comportamento/metodo, aggiornare questo README.
