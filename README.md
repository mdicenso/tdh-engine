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
gareggiano 6 motori — OLS · **ETS/Holt-Winters** · **SARIMAX** · **stato latente (UnobservedComponents)**
· **Theta** · **STL+ARIMA** — e si tiene quello con l'errore più basso in un backtest
**rolling-origin** (più finestre mobili da 12 mesi → scelta affidabile, non frutto di una sola
finestra fortunata). La Scheda Regione mostra la **classifica** dei motori (MAE medio, skill vs
naive, finestre vinte). Il trend annuale (`project_var`) ha l'opzione **robusta** (Huber) per gli
outlier tipo COVID.

**Tier 2 — struttura tra regioni**: **partial pooling** empirical-Bayes
(`partial_pool_slopes`) per stabilizzare le serie corte verso la media nazionale, e
**riconciliazione** gerarchica Italia↔regioni (`reconcile_bottom_up`). Calcolo offline in
`tier2_structural.py` → artefatto `.cache/tier2_pooled_trends.json`, letto dalla Scheda Regione.

**Evidenza**: i bake-off (`bakeoff.py`, `bakeoff_natl.py`) sui dati reali mostrano che i modelli
complessi NON battono di norma la naive stagionale (segnale ~95% autoregressivo) → la complessità
si attiva solo se supera il backtest. Analisi completa: `@_scorciatoie/TDH_Studio_Modelli.docx`.

Confine invariato: **ranking decisionale**, NON stima causale della spesa promozionale.

## Stile / UI (tdhlib.py)
Il tema è centralizzato in `tdhlib.py`: variabile `CSS` (iniettata da `inject_css()` una volta
sola in `app.py` dopo `set_page_config`) + `_layout()` per i grafici Plotly. Redesign con
gerarchia tipografica (h1/h2/h3 distinti, h2 con accent teal), metric card con ombra e bordo
superiore, grafici con `paper_bgcolor` trasparente integrato sullo sfondo `#f1f5f9`, sidebar
scura. Helper opzionale `section_header(title, subtitle, icon)` per le intestazioni di sezione
(in alternativa a `st.subheader`). Palette: `#0e7490` teal primario, `#f59e0b` amber, `#f1f5f9`
sfondo.

Scrollbar personalizzata (in `CSS`): più **chiara** (`#94a3b8`, `#cbd5e1` nella sidebar
scura) e un po' più **larga** (16px), con pollice arrotondato — quella scura di default
era quasi invisibile sul fondo `#1e293b` della sidebar. Stile sia `::-webkit-scrollbar`
(Chrome/Edge) sia `scrollbar-color` (Firefox).

Tabelle "Gestione dati": la colonna **Righe** passa per `fmt_count_col()` che la rende
uniforme a stringa (numeri con separatore migliaia, `—` per le fonti live senza file). Serve
a evitare il mix int/placeholder che rompeva la serializzazione Arrow di `st.dataframe`.

Griglia dei grafici: `_layout()` riconosce le **barre orizzontali** (`go.Bar` con
`orientation="h"`) e inverte la griglia — linee guida **verticali** sull'asse degli importi
(così ogni barra corrisponde al suo valore), niente linee orizzontali tra le categorie. I
grafici temporali/verticali restano con griglia orizzontale.

Selettore anno (ultimi 3 anni completi) su tre pagine, tutte sulla stessa sorgente multi-anno
`regions_spend_ranking_year(year)` / `bdi_region_years()` (da `bdi_region_long`, serie BdI
regionale trimestrale 1997–oggi; il 2024 coincide con `bdi_extended`):
- **Confronto regioni**: classifica regioni per spesa straniera dell'anno scelto.
- **Italia**: la mappa (`chart_italy_map(highlight, year)`) si **ricolora** per l'anno scelto.
- **Spesa turistica**: il *Grafico 2 — Confronto regioni* usa `chart_regions_ranking(highlight, year)`
  (evidenzia la **regione attiva**, non più «Abruzzo» cablato). Rimossa la vecchia
  `chart_regions_spend` (dead code, sostituita da quella anno-parametrica).

Pagina **Provincia** ("Cosa è successo"): struttura DOVE → COSA È CAMBIATO → QUANDO. Mappa +
tabella con **peso %** sul totale regionale e nota di concentrazione; **variazione % a/a** per
provincia (`province_yoy` + `chart_province_yoy`, ultimi 12 mesi vs 12 precedenti, sul totale);
**heatmap stagionale** mese×provincia normalizzata al picco (`chart_province_seasonality`);
trend mensile con toggle **Totali/Straniere**. `compute_provinces` ora restituisce anche
`panel_str` (serie mensile straniera per provincia, dove ISTAT la espone). Limiti dati: posti
letto/struttura/occupazione non disponibili a livello provinciale (solo regionale).

Stesso schema narrativo (adattato, senza dimensione spaziale) esteso alle pagine descrittive:
- **Struttura**: COM'È COMPOSTO (metriche + donut) → COSA È CAMBIATO (variazione % a/a per
  segmento) → QUANDO (stagionalità per segmento) → trend mensile. Riusa i grafici *generici*
  `province_yoy` e `chart_province_seasonality` (lavorano su qualsiasi pannello `date` + N
  colonne), passando un pannello con colonne rinominate `Alberghiero`/`Extra-alberghiero`.
- **Occupazione**: QUANT'È (livello + **variazione a/a in punti percentuali** come `delta` della
  metrica, ultimi 12 mesi vs 12 precedenti) → COSA È CAMBIATO (trend occupazione lorda) → QUANDO
  (stagionalità). Il delta è in *punti* (non %) perché l'occupazione è già un tasso.

> Regola di progetto: ad ogni modifica che cambia comportamento/metodo, aggiornare questo README.

<!-- deploy: rebuild forzato 2026-07-03 (pull nuovo tdhlib: chart_italy_map(year=), bdi_region_years) -->
