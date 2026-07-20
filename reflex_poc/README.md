# UI in Reflex (Python → React) — design «Istituzionale»

App completa del TDH resa come vera app React ma scritta in **Python** con
[Reflex](https://reflex.dev). **Online su Reflex Cloud** (tdh-engine-gold-panda.reflex.run)
dietro **login** (cancello username/password), con logo TDH in alto a sinistra.

**Dati REALI** (dal 12-07-2026): tutte le pagine leggono dal data-layer puro `tdh_data.py`
(in TDH_Engine) — ISTAT presenze/capacità, Banca d'Italia spesa, ISTAT esteri per
paese, Google Trends, Inside Airbnb — gli stessi numeri del cruscotto Streamlit. Selettore
su **tutte le 20 regioni + Italia**. Migrazione dell'intero TDH a Reflex (decisa l'11-07-2026)
oramai in stato avanzato: ~21 pagine.

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
Struttura comune: sidebar chiara (logo in testa + nav a gruppi con icone) · topbar
(breadcrumb + selettore Regione a destra + «Esci») · KPI a filetto · grafici Plotly
affiancati · pannelli larghi 100% allineati alla riga KPI · gate di login (admin/admin
in dev; le credenziali reali stanno in `TDH_LOGINS` come secret, MAI nel codice).

Pagine (~21), per gruppo:
- **Panoramica**: Home · Regione · Italia·mappa (coropletica cliccabile) · Mercati d'origine ·
  Dettaglio mercato · Confronto regioni.
- **Cosa è successo**: Per provincia · Per struttura · **Occupazione** (occ. posti letto:
  trend annuale + stagionalità) · **Affitti brevi · Italia** (aggregato STR ponderato) ·
  **Affitti brevi · territorio** (dettaglio + posizionamento vs media Italia) · Base dati
  regionale · Spesa turistica.
- **Cosa fare**: Ranking regioni · Azioni & budget (motore) · Interesse online (Google
  Trends) · Forecast presenze (motore).
- **Sistema**: Architettura · Gestione dati (inventario sorgenti).

## Deploy (Reflex Cloud)
```
reflex deploy --no-interactive --token <T> --project <P> --app-name tdh-engine --region fra
```
Il **bundle** self-contained sta in `tdh_reflex_poc/tdh_engine/` (copia di `tdh_data.py`,
`regions.py`, `tourism_wedge/`, dati in `datacache/`): dopo ogni modifica a `tdh_data.py`
va **ricopiato** nel bundle prima del deploy. Gotcha noti nella memoria di progetto
(dot-dir esclusi, cap 1MB per file, foreach su `list[dict]`, niente concat `Var + item`).

## Migrazione — stato
- **Fase 3 FATTA** (20-07-2026): `tdhlib.py` non duplica più la logica delle 22
  funzioni-base — sono deleghe sottili a `tdh_data` (stessa firma, ancora `@st.cache_data`).
  `tdh_data.clear_caches()` + `L.clear_data_caches()` collegato ai refresh in `app.py`.
  Verificato: output vecchio-vs-nuovo 77/77 identici. `tdh_data` è ora l'unica fonte di
  verità dei dati, condivisa tra app Streamlit e app Reflex.
- Opzionali rimasti: assistente Claude in-app · video intro in Home · STR con dati reali
  AirROI (fonte a pagamento) · credenziali più robuste di admin/admin.
