# POC UI in Reflex (Python → React) — design «Istituzionale»

Prototipo di **una** pagina ("Regione") che dimostra il design scelto, reso come vera app
React ma scritta in **Python** con [Reflex](https://reflex.dev). Dati di **ESEMPIO**.
Da qui parte la migrazione dell'intero TDH a Reflex (deciso l'11-07-2026).

Contiene solo il **sorgente** (`tdh_reflex_poc.py` = pagina+stato, `rxconfig.py` = config).
La cartella generata `.web/` + `node_modules` NON sono qui (pesanti, si rigenerano).

## Come rilanciarlo in locale
1. Serve **Node** (verificato con v24) già presente sul PC.
2. venv dedicato + dipendenze:
   ```
   python -m venv C:\Users\mcenso\reflex_venv
   C:\Users\mcenso\reflex_venv\Scripts\python -m pip install reflex plotly
   ```
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
