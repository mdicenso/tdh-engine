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

**Identità "dashboard esecutiva"** (in `tdhlib.py`):
- `page_header(title, subtitle, group, emoji, region_code)` — banner di pagina con gradiente teal,
  **breadcrumb** (`gruppo › titolo`), titolo grande e **badge regione** (📍) sulle pagine region-aware.
  Drop-in al posto di `st.header()`+`st.caption()`. Applicato a **tutte le pagine** (tranne Home).
- `kpi_row(items)` — riga di KPI "executive" (numeri grandi, label maiuscola, delta ▲/▼ e hint
  opzionali) al posto di `st.metric`. Usata su **tutte** le pagine con KPI (Sintesi, Regione, Spesa,
  Forecast, Mercati d'origine, Dettaglio, Struttura, Occupazione, Operatori): **zero `st.metric`
  residui** in `app.py`.
- **Niente doppio banner**: la barra globale `hero()` (in `app.py`) è **disattivata** — ogni pagina
  ha il proprio `page_header`. `hero()` resta come funzione ma non è più chiamata. Banner compatti
  (padding e font ridotti) per non rubare spazio verticale.

Pulsante "View X more" / "View less" della navigazione (`stSidebarNavViewButton`):
schiarito a `#cbd5e1` (verde-acqua `#5eead4` su hover) — sul fondo scuro della sidebar
era scuro e illeggibile, come gli altri link della nav.

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
grafici temporali/verticali restano con griglia orizzontale. Il grafico **Copertura temporale
delle serie** (`chart_coverage`, timeline in Gestione dati) ha linee verticali di riferimento:
**maggiori per anno** (solide, etichetta `%Y`) e **minori per semestre** (punteggiate, `dtick` M12/M6).

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

**Turisti esteri per PAESE × regione/provincia (ISTAT cube `122_54_DF_DCSC_TUR_9`, ANNUALE)**:
scoperta 2026-07-07 che riempie il buco storico (prima si credeva non esistesse — vedi memoria
vincolo dati). A differenza di `_7` (solo `IT`/`WRL_X_ITA`), il cube `_9` espone i **singoli paesi**
(DE/FR/AT/ES/US/CH_LI…) per **ogni regione e provincia**, arrivi (`AR`) e presenze (`NI`), 2008→oggi.
Scaricato via SDMX-CSV (`real_sources`/script) in `.cache/istat_estero_regione_prov_annuale.csv`
(dimensioni secondarie fissate a `ALL`/`TOT` per evitare righe doppie). Reader in `tdhlib`:
`estero_regione_long`, `estero_markets(code, datatype, year, top)`, `estero_country_series`,
`estero_years`, `estero_country_name`. NB: il per-paese × regione **mensile** resta non disponibile
(solo annuale via `_9`; il mensile per-paese `_5` è solo nazionale). Registrato in **Gestione dati**
(Tabella *Dati Presenti* via `builtin_sources`) e matrice di copertura aggiornata: la riga *Presenze
per PAESE di origine* passa da 🔴 buco a ✅ (regione+provincia, annuale); voce anche nella *Copertura
temporale delle serie*. Scaricato con `scratchpad/download_tur9.py` (resumibile, per-territorio,
retry sui 502/timeout ISTAT) — 130 territori, ~263k righe, 2008→2024. **Agganciato
all'auto-refresh**: `real_sources.fetch_estero_country_region_annual()` (downloader per-territorio,
i territori falliti tengono le righe già in cache → nessuna perdita su refresh parziale) +
`fetch_estero_latest_year()` (probe leggero). In `update_check.py` è la fonte `istat_estero`;
il job settimanale fa lo **skip intelligente**: riscarica i 131 territori SOLO se ISTAT pubblica
un anno più recente di quello in cache (dato annuale, download pesante).

**Spesa STIMATA turisti stranieri per mercato × regione** (pagina Spesa turistica, *Grafico 5 +
Tabella 1*): ISTAT non produce la spesa del turismo estero in entrata (solo flussi fisici); la spesa
la dà solo la Banca d'Italia, ma per regione **o** per paese, mai il loro incrocio. Stima trasparente:
`estero_spesa_stimata(code)` = notti reali per mercato in regione (`_9`) × spesa media a notte del
mercato a livello nazionale (`bdi_spend_per_night(year)`, da BdI TS1); mappa `_ISTAT_TO_BDI` per i
codici paese, solo mercati presenti in entrambe le fonti, anno = il più recente comune completo.
Etichettata **esplicitamente come stima** (non dato ufficiale). `chart_estero_spesa_stimata`.

Pagina **Mercati esteri per paese** (`page_mercati_paese`) ora è **region-aware** e parte dal dato
**reale** della regione selezionata (da `_9`): selettore metrica *Presenze/Arrivi* + anno, *Grafico 1*
top mercati (barre), *Tabella 1* con **quota %** sul totale esteri e **var % a/a**, *Grafico 2* trend
storico 2008→ con multiselect dei mercati. Sotto, il **contesto nazionale** BdI (spesa/notti/viaggiatori,
*Grafico 3 + Tabella 2*). Funzioni: `estero_markets_table` (quota+yoy), `chart_estero_markets`,
`chart_estero_trend`. Rimosso il vecchio caveat "ISTAT non espone il per-paese regionale" (ora superato).

**Ranking motore — peso economico REGIONALE** (non più nazionale): `rank_markets` ha un nuovo
`weight_override`; lo **score** (`= forza × momentum × peso × fattibilità`) ora usa il **valore
economico reale del mercato NELLA regione** = presenze reali (`_9`, ultimo anno) × spesa/notte BdI
(mediana come fallback, es. NL), via `region_market_value(code)` in `compute_real`. Il `€/viaggiatore`
nazionale BdI resta **mostrato** in scheda (campo `valore_eur_per_visitatore`) ma non è più il peso
dello score; il peso usato è il nuovo campo `peso_score`. Effetto: es. in Abruzzo la Germania (valore
reale ~30 M€) sale, gli USA (alto €/viaggiatore nazionale ma pochi arrivi in Abruzzo) scendono. Pagina
Ranking *Grafico 2* mostra `chart_region_weight_bar` (peso regionale M€); fallback al vecchio
`chart_value_bar` (€/viaggiatore naz.) se `_9` manca.

Pagina **Advisor Operatori** (`page_advisor_operatori`, gruppo *Sistema*, sotto Gestione dati):
documento di **studio** (non integra dati) che confronta le 3 fonti candidate per i dati reali degli
operatori/affitti brevi — **Inside Airbnb** (gratis/aperta, poche città), **AirDNA** (a pagamento,
copertura ampia), **AirROI** (low-cost, da verificare) — con matrice comparativa, pro/contro per fonte
e raccomandazione a fasi. Nota chiave: canali/funnel/conversione/affluenza sono dati proprietari dei
gestionali, non disponibili aperti (nella pagina Operatori vanno tolti o marcati "simulato").

**Base Dati Regionale** (`page_base_dati_regionale`, gruppo *Cosa è successo*, **region-aware**: segue
il selettore di regione). Pagina "base dati" per la regione selezionata, in tre blocchi con
numerazione unica per-pagina:
1. **Tabella 1 — Catalogo fonti** (`region_data_catalog(code, ov)`): quali fonti coprono *questa*
   regione, con Fonte · Dato · Granularità · Ultimo periodo · Copertura · Stato (🟢/🟡/🔴). Costruito
   **offline** dove possibile (`_9`, BdI, Trends, connettività da file-check) riusando `ov` per non
   rifare le chiamate live ISTAT.
2. **Sintesi ISTAT** (KPI + *Grafico 1* presenze mensili tot/straniere, *Grafico 2* top mercati esteri
   da `_9`, *Grafico 3* posti letto per anno via `chart_region_letti`).
3. **Dettaglio locale**: fonte territoriale ricca dove esiste — **Provincia di Bolzano `ITD1`** via
   **ASTAT** (*Grafico 4-6 + Tabella 2*), **Lombardia `ITC4`** via **Open Data Lombardia**
   (*Grafico 4-5 + Tabella 2*, con selettore provincia) e **Toscana `ITE1`** via **Open Data Regione
   Toscana** (*Grafico 4-6 + Tabella 2*, con selettore provincia); per le altre regioni un avviso
   (candidato: Sardegna). Robusta ai down ISTAT: se `region_overview` fallisce, catalogo + fonti offline
   restano visibili.

**Fonte ASTAT — Alto Adige/Bolzano (COMPLEMENTARE)**: portale SDMX ASTAT
(`astatsdmxservices.prov.bz.it`, dataflow `ITH1,DF_TOUR_ACC_CAP_TOURASS_MONTHLY_1`), dato della **sola
provincia di Bolzano** (= regione `ITD1` nel modello dati dell'app). Non è multi-regione e **non ha il
paese di origine** → non alimenta il motore di ranking; vale per due cose che le basi ISTAT nazionali
non danno: **mensilità recente** (arrivi/presenze fino a mag-2026) e il **lato offerta** (esercizi +
posti letto per categoria: stelle, residence, campeggi, agriturismi…). Key SDMX:
`FREQ.TYPE_PERIOD.TYPE_GEO.TOUR_GEO.CATEGORY.INDICATOR`; SDMX-CSV con separatore `;` (ISTAT usa `,`),
nessun proxy/auth. Reader in `real_sources`: `fetch_astat_flussi_mensili`
(→ `.cache/astat_bolzano_flussi_mensili.csv`), `fetch_astat_capacita_categoria`
(→ `.cache/astat_bolzano_capacita_categoria.csv`), `fetch_astat_bolzano`, `fetch_astat_latest_period`.
Helper in `tdhlib`: `astat_flussi/capacita/kpi/capacita_table`, `chart_astat_flussi`,
`chart_astat_stagionalita`, `chart_astat_capacita` (renderizzati nel blocco locale della pagina).
Registrata in **Gestione dati** (`builtin_sources`), nella *Copertura temporale delle serie*
(`series_coverage`) e nella matrice (*Flussi MENSILI per categoria ricettiva*, 🟡 solo Alto Adige).
**Auto-refresh**: fonte `astat` in `update_check.py` con **skip intelligente** (riscarica solo se ASTAT
pubblica un mese più recente di quello in cache).

**Fonte Open Data Lombardia (COMPLEMENTARE, regione `ITC4`)**: portale Socrata `dati.lombardia.it`,
dataset `xzck-giqt` *"Flussi turistici per mese nelle province lombarde"*. Dà una cosa che nessun'altra
fonte del motore ha: il **mercato estero MENSILE a livello sub-nazionale** — arrivi/presenze per **12
province × provenienza** (regioni italiane + paesi esteri, colonna `provenienza_turisti`, 83 valori) ×
alberghiero/extra, **2019-2024** (64.285 righe). API SODA (JSON/CSV, `$select/$where/$limit/$offset`,
nessun proxy/auth), scaricata a pagine da 50k. Reader in `real_sources`: `fetch_lombardia_flussi`
(→ `.cache/lombardia_flussi_provincia_mese.csv`, con pulizia dei valori sporchi alla fonte:
`Austrialia`→Australia, `Israel`→Israele, 3 grafie di *Monza e Brianza*), `fetch_lombardia_latest_year`.
Helper in `tdhlib`: `lomb_flussi`, `lomb_provinces`, `lomb_markets_table`, `lomb_kpi`,
`chart_lomb_flussi_mensili`, `chart_lomb_markets`; `_lomb_is_foreign` classifica la provenienza come
paese estero (esclude regioni italiane e «non specificato»). Nel blocco locale della pagina Base Dati
Regionale c'è un **selettore provincia** (o tutta la Lombardia). Registrata in Gestione dati
(`builtin_sources`, `series_coverage`) e in matrice (riga *Mercato ESTERO mensile sub-nazionale*, 🟡 solo
Lombardia). **Auto-refresh**: fonte `lombardia` in `update_check.py`, cadenza annuale, **skip
intelligente** (riscarica solo se Socrata pubblica un anno più recente).

**Fonte Open Data Regione Toscana (COMPLEMENTARE, regione `ITE1`)**: portale CKAN `dati.toscana.it`,
serie *"Movimento dei clienti e struttura dell'offerta ricettiva. Toscana. Anno YYYY"*. Dà una cosa che
nessun'altra fonte del motore ha: il **movimento a livello COMUNALE** — arrivi/presenze **annuali per
~272 comuni × ambito turistico**, con split **italiani/stranieri**, **2018-2025** (org. Regione Toscana,
escluse le locazioni brevi). Struttura CKAN a **un dataset per anno** (URL a UUID casuale): il reader li
**enumera via `package_search`** e per ogni anno prende la risorsa CSV *movimento*. I file annuali hanno
**formati eterogenei** — *wide* (2024-25, colonne `arrivi_italiani/stranieri`), *long* con `;` (2018-22,
`Provenienza`=Italiani/Stranieri o colonna `Italiano-Straniero`=ITA/STR) e *long* con **TAB** (2023,
`ProvenienzaMacro`=ITA/STR) — normalizzati a uno schema unico via `_tosc_canonkey` (mappa le intestazioni)
+ sniffing del separatore; encoding **cp1252**. Reader in `real_sources`: `fetch_toscana_movimento`
(→ `.cache/toscana_movimento_comune_anno.csv`, 2.170 righe), `_tosc_movimento_urls`, `_tosc_parse`,
`fetch_toscana_latest_year`. Helper in `tdhlib`: `tosc_movimento`, `tosc_provinces`, `tosc_yearly_totals`,
`tosc_top_comuni`, `tosc_ambiti`, `tosc_kpi`, `chart_tosc_yearly`, `chart_tosc_top_comuni`,
`chart_tosc_ambiti`. Nel blocco locale della pagina Base Dati Regionale c'è un **selettore provincia** (o
tutta la Toscana). Registrata in Gestione dati (`builtin_sources`, `series_coverage`) e in matrice (riga
*Movimento a livello COMUNALE*, 🟡 solo Toscana). **Auto-refresh**: fonte `toscana` in `update_check.py`,
cadenza annuale, **skip intelligente** (riscarica solo se CKAN pubblica un anno più recente). Prossimo
candidato con feed pulito: **Sardegna** (osservatorio, CSV CC0); **Trentino/ISPAT** scartato (solo HTML
da scrapare, nessun export).

### Aggiornamento automatico delle fonti (scheduler)

`update_check.py` ha un entry-point CLI: senza argomenti fa **solo il controllo** (probe leggero, elenca
le fonti con dati nuovi, exit 10 se ce ne sono); con `--apply` **scarica davvero** nella cache le fonti
aggiornabili (`refresh_all()`, salta `manual`/`ecb`); con `--apply --fast` (usato dallo scheduler)
aggiorna **solo le fonti territoriali con skip intelligente su server veloci** — **ASTAT, Lombardia,
Toscana**: fanno un *probe leggero* e scaricano **solo se c'è davvero un anno/mese nuovo**. In `--fast`
sono **escluse tutte le fonti ISTAT** (l'endpoint `esploradati.istat.it` è lento e a volte si appende su
chiamate non interattive) e **Trends/Wikipedia** (rate-limited): quelle restano aggiornabili a mano da
**«Gestione dati»**.

Il lanciatore **`aggiorna_fonti.cmd`** (radice progetto) incatena il tutto per lo scheduler: forza
`PYTHONIOENCODING=utf-8` (la console cp1252 va altrimenti in `UnicodeEncodeError` sui caratteri di stato)
→ `update_check.py --apply --fast` → `git add` **chirurgico dei soli 4 file cache** di ASTAT/Lombardia/
Toscana (per non trascinare nel commit altri file di cache sporcati da app/test) → se sono cambiati
**commit + push** su GitHub (così il cruscotto su Streamlit Cloud si aggiorna da solo), altrimenti non fa
nulla. Log in `data/update_scheduler.log`. È un file `.cmd` (cmd.exe), quindi non è toccato dal
ConstrainedLanguage di PowerShell del PC; si può anche lanciare a mano col doppio click.

**Task Scheduler di Windows**: task **«TDH Aggiorna Fonti»**, cadenza **settimanale** (lunedì 09:30), gira
quando l'utente è connesso. ⚠️ Il Task Scheduler **non** lancia bene un `.cmd` il cui percorso contiene
spazi/`@` (la cartella OneDrive del progetto), quindi il task punta a un **wrapper senza spazi**
`C:\Users\mcenso\tdh_aggiorna_fonti.cmd` che con `call "…"` richiama il launcher vero nel progetto.
Gestione: `schtasks /Query /TN "TDH Aggiorna Fonti"`, esecuzione immediata `schtasks /Run /TN "TDH
Aggiorna Fonti"`, rimozione `schtasks /Delete /TN "TDH Aggiorna Fonti" /F`.

> Regola di progetto: ad ogni modifica che cambia comportamento/metodo, aggiornare questo README.

<!-- deploy: rebuild forzato 2026-07-03 (pull nuovo tdhlib: chart_italy_map(year=), bdi_region_years) -->
