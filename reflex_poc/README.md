# POC UI in Reflex (Python → React) — design «Istituzionale»

Prototipo della pagina "Regione" che dimostra il design scelto, reso come vera app
React ma scritta in **Python** con [Reflex](https://reflex.dev).

**Dati REALI** (dal 12-07-2026): la pagina legge dal data-layer puro `tdh_data.py`
(in TDH_Engine) — ISTAT presenze/capacità, Banca d'Italia spesa, ISTAT esteri per
paese — gli stessi numeri del cruscotto Streamlit. Selettore su **tutte le 20 regioni
+ Italia**. È il primo passo della migrazione dell'intero TDH a Reflex (deciso l'11-07-2026).

Contiene solo il **sorgente** (`tdh_reflex_poc.py` = pagina+stato, `rxconfig.py` = config).
La cartella generata `.web/` + `node_modules` NON sono qui (pesanti, si rigenerano).

## Architettura dei dati (Fase 1)
- `TDH_Engine/tdh_data.py` = **data-layer puro** (nessun import di Streamlit/statsmodels;
  `functools.lru_cache` al posto di `st.cache_data`; path dati assoluti radicati su
  TDH_Engine). Espone `regione_snapshot(code)` in tipi Python semplici + le funzioni
  base (`region_overview`, `estero_markets`, `region_spend`, `region_annual_panel`, …).
- Carica `regions.py` e `tourism_wedge/real_sources.py` **direttamente dal file** (via
  `importlib`), così NON scatta `tourism_wedge/__init__.py` (che importa `engine`→statsmodels,
  inutile al data-layer e assente nel venv Reflex).
- Il POC lo aggancia via `sys.path` (variabile d'ambiente `TDH_ENGINE_DIR` per override).
- Prossima convergenza (Fase 3): far importare a `tdhlib` queste stesse funzioni da
  `tdh_data`, eliminando la duplicazione con le copie oggi ancora presenti in `tdhlib`.

## Come rilanciarlo in locale
1. Serve **Node** (verificato con v24) già presente sul PC.
2. venv dedicato + dipendenze:
   ```
   python -m venv C:\Users\mcenso\reflex_venv
   C:\Users\mcenso\reflex_venv\Scripts\python -m pip install reflex plotly pandas openpyxl
   ```
   (`pandas`/`openpyxl` servono al data-layer `tdh_data`: lettura CSV di cache e xlsx BdI.)
3. Ricostruire il progetto:
   ```
   mkdir tdh_reflex_poc && cd tdh_reflex_poc
   ..\..\reflex_venv\Scripts\reflex init --template blank
   ```
   poi sostituire `rxconfig.py` con quello qui e `tdh_reflex_poc/tdh_reflex_poc.py` con `tdh_reflex_poc.py` qui.
4. `reflex run` → apri **http://localhost:3000** (backend :8000).

## Cosa mostra
Sidebar chiara (brand in testa + nav a gruppi con icone) · topbar (breadcrumb + selettore
Regione a destra) · KPI a filetto · grafici Plotly affiancati · tabella ranking · selettore
regione reattivo (Toscana/Lazio/Lombardia).

## Migrazione (prossimi passi)
1. Fondamenta: scorporare il *data layer* da `tdhlib` (oggi legato a Streamlit) in funzioni
   pure; design-system Reflex condiviso (kpi/panel/sidebar/topbar/grafici).
2. Pagine core con dati REALI (Regione, Italia/mappa, Base Dati Regionale, Ranking, STR).
3. Resto pagine + assistente Claude + Gestione dati.
4. Deploy: Reflex Cloud o Docker self-host (non Streamlit Cloud).
