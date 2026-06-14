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

## Prossimo giro: SARIMAX
Quando la storia regge in sala, si varia il solo `engine.fit_market`:
sostituire l'OLS con `statsmodels` SARIMAX (search e fx come regressori esogeni,
stagionalità nel termine stagionale). Interfaccia, adattatori, strato decisionale
e formato di output restano identici — cambia solo il cuore di stima.
