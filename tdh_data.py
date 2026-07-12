"""
TDH — data layer PURO (framework-agnostico).

Contiene SOLO calcolo/lettura dati: nessun import di Streamlit, nessun grafico
Plotly. È la fonte di verità dei dati, importabile sia dal cruscotto Streamlit
(`tdhlib`, che espone questi stessi risultati nei grafici) sia dalla futura app
Reflex. Multi-regione by construction (la regione è un codice NUTS2).

Note di portabilità:
- I path dei dati sono ASSOLUTI, radicati sulla cartella di questo file
  (`_ROOT/.cache/...`): funziona a prescindere dalla working directory, quindi
  anche lanciando l'app da un'altra cartella (es. il progetto Reflex).
- La cache di Streamlit (`@st.cache_data`) è sostituita da `functools.lru_cache`,
  che memorizza in-memory dentro il processo (nessuna dipendenza da Streamlit).

Fase 1 della migrazione a Reflex (decisa l'11-07-2026): scorporo del data layer.
"""
from __future__ import annotations

import functools
import importlib.util
import json
import os
import re
import sys

import pandas as pd

# ── radici dei dati (assolute) ──────────────────────────────────────────────
_ROOT = os.path.dirname(os.path.abspath(__file__))
_CACHE = os.path.join(_ROOT, ".cache")

# `regions` è autonomo (solo stdlib): import normale, assicurando _ROOT su sys.path
# (garantisce l'import anche quando l'app gira da un'altra cartella, es. Reflex).
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
import regions as RG  # noqa: E402


# `real_sources.py` è AUTONOMO (stdlib + numpy/pandas, nessun import relativo): lo
# carichiamo DIRETTAMENTE dal file, così NON scatta `tourism_wedge/__init__.py`, che
# importa `engine` → statsmodels & c. (inutili al data-layer e assenti nel venv Reflex).
def _load_by_path(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


RS = _load_by_path("tdh_real_sources", os.path.join(_ROOT, "tourism_wedge", "real_sources.py"))


def _cpath(*parts: str) -> str:
    """Path assoluto dentro la cartella .cache del progetto."""
    return os.path.join(_CACHE, *parts)


# ════════════════════════════════════════════════════════════════════════════
# BANCA D'ITALIA — spesa/notti/viaggiatori dei turisti stranieri
# ════════════════════════════════════════════════════════════════════════════
# colonna del foglio TS2 -> codice/i NUTS2 (Trentino = una colonna -> Bolzano+Trento).
_BDI_REG_COL = {4: ["ITC1"], 5: ["ITC2"], 6: ["ITC4"], 7: ["ITC3"], 9: ["ITD1", "ITD2"],
                10: ["ITD3"], 11: ["ITD4"], 12: ["ITD5"], 14: ["ITE1"], 15: ["ITE2"],
                16: ["ITE3"], 17: ["ITE4"], 19: ["ITF1"], 20: ["ITF2"], 21: ["ITF3"],
                22: ["ITF4"], 23: ["ITF5"], 24: ["ITF6"], 25: ["ITG1"], 26: ["ITG2"]}
_BDI_REG_SHEETS = {"spesa": "TS2-S-S", "notti": "TS2-N-S", "viaggiatori": "TS2-V-S"}

# fogli TS1 (nazionale per PAESE di origine)
_BDI_COLMAP = {4: "DE", 5: "FR", 6: "AT", 7: "ES", 9: "GB", 10: "CH", 11: "RU",
               13: "US", 14: "CA", 17: "JP"}
_BDI_SHEETS = {"notti": "TS1-N-S", "spesa": "TS1-S-S", "viaggiatori": "TS1-V-S"}
BDI_MARKETS = ["DE", "AT", "GB", "CH", "US", "FR", "ES"]

_BDI_XLSX = _cpath("bdi_turismo_ts.xlsx")


@functools.lru_cache(maxsize=None)
def bdi_region_long():
    """Spesa/notti/viaggiatori dei turisti stranieri per REGIONE visitata (trimestrale,
    1997-2025). DataFrame: date·code·spesa·notti·viaggiatori. None se l'xlsx manca."""
    if not os.path.exists(_BDI_XLSX):
        return None
    import openpyxl
    wb = openpyxl.load_workbook(_BDI_XLSX, read_only=True, data_only=True)
    recs = []
    for metric, sheet in _BDI_REG_SHEETS.items():
        year = None
        for r in wb[sheet].iter_rows(values_only=True):
            if r and r[0] is not None:
                try:
                    year = int(r[0])
                except (TypeError, ValueError):
                    pass
            m = re.match(r"\s*(\d)", str((r[1] or r[2]) if r else ""))
            if not (year and m):
                continue
            q = int(m.group(1))
            date = pd.Timestamp(year, q * 3 - 2, 1)
            for col, codes in _BDI_REG_COL.items():
                if col < len(r) and r[col] is not None:
                    try:
                        val = float(r[col])
                    except (TypeError, ValueError):
                        continue
                    for code in codes:
                        recs.append((date, code, metric, val))
    if not recs:
        return None
    df = pd.DataFrame(recs, columns=["date", "code", "metric", "value"])
    return df.pivot_table(index=["date", "code"], columns="metric", values="value").reset_index()


def bdi_national_annual():
    """Spesa straniera ANNUALE per TUTTA Italia = somma delle regioni visitate (BdI).
    Deduplica il Trentino, che nei dati è duplicato su Bolzano (ITD1) e Trento (ITD2)."""
    df = bdi_region_long()
    if df is None or df.empty:
        return None
    reps = {codes[0] for codes in _BDI_REG_COL.values()}  # un codice per colonna-regione (no doppio Trentino)
    d = df[df["code"].isin(reps)].copy()
    if d.empty:
        return None
    qn = d.groupby("date").agg(spesa=("spesa", "sum"), notti=("notti", "sum"),
                               viaggiatori=("viaggiatori", "sum")).reset_index()
    qn["anno"] = qn["date"].dt.year
    return qn.groupby("anno").agg(spesa=("spesa", "sum"), notti=("notti", "sum"),
                                  viaggiatori=("viaggiatori", "sum"),
                                  trimestri=("date", "count")).reset_index()


def bdi_region_annual(code: str):
    """Aggregato ANNUALE (spesa M€, notti/viaggiatori in migliaia) per la regione,
    oppure il totale Italia se è selezionata la vista nazionale."""
    if RG.is_national(code):
        return bdi_national_annual()
    df = bdi_region_long()
    if df is None or df.empty:
        return None
    d = df[df["code"] == code].copy()
    if d.empty:
        return None
    d["anno"] = d["date"].dt.year
    return d.groupby("anno").agg(spesa=("spesa", "sum"), notti=("notti", "sum"),
                                 viaggiatori=("viaggiatori", "sum"),
                                 trimestri=("date", "count")).reset_index()


@functools.lru_cache(maxsize=None)
def bdi_country_long():
    """Flussi nazionali BdI per paese di origine: DataFrame date·code·notti·spesa·viaggiatori
    (trimestrale). Sorgente: fogli TS1 dell'xlsx BdI. None se il file manca."""
    if not os.path.exists(_BDI_XLSX):
        return None
    import openpyxl
    wb = openpyxl.load_workbook(_BDI_XLSX, read_only=True, data_only=True)
    recs = []
    for metric, sheet in _BDI_SHEETS.items():
        rows = list(wb[sheet].iter_rows(values_only=True))
        h = next((i for i, r in enumerate(rows) if r and any(c == "Germania" for c in r if c)), None)
        if h is None:
            continue
        year = None
        for r in rows[h + 1:]:
            if r[0] is not None:
                year = int(r[0])
            m = re.match(r"\s*(\d)", str(r[1] or r[2] or ""))
            if not (year and m):
                continue
            q = int(m.group(1))
            date = pd.Timestamp(year, q * 3 - 2, 1)
            for col, code in _BDI_COLMAP.items():
                if col < len(r) and r[col] is not None:
                    recs.append((date, code, metric, float(r[col])))
    if not recs:
        return None
    df = pd.DataFrame(recs, columns=["date", "code", "metric", "value"])
    return df.pivot_table(index=["date", "code"], columns="metric", values="value").reset_index()


@functools.lru_cache(maxsize=None)
def bdi_extended():
    """Aggregati BdI pre-calcolati (spesa regioni 2024, struttura/motivo nazionale...)."""
    p = _cpath("bdi_extended.json")
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None


# ════════════════════════════════════════════════════════════════════════════
# ISTAT — esteri per PAESE × territorio, ANNUALE (cube DCSC_TUR_9)
# ════════════════════════════════════════════════════════════════════════════
_TUR9_PATH = _cpath("istat_estero_regione_prov_annuale.csv")

# Nomi leggibili dei codici COUNTRY_RES_GUESTS (ISO2 + aggregati). Pass-through se ignoto.
_ISTAT_COUNTRY_NAME = {
    "DE": "Germania", "FR": "Francia", "AT": "Austria", "ES": "Spagna",
    "GB": "Regno Unito", "UK": "Regno Unito", "CH_LI": "Svizzera e Liechtenstein",
    "CH": "Svizzera", "US": "Stati Uniti", "CA": "Canada", "NL": "Paesi Bassi",
    "BE": "Belgio", "RU": "Russia", "CN": "Cina", "JP": "Giappone", "BR": "Brasile",
    "AR": "Argentina", "AU": "Australia", "PL": "Polonia", "SE": "Svezia",
    "DK": "Danimarca", "FI": "Finlandia", "NO": "Norvegia", "IE": "Irlanda",
    "PT": "Portogallo", "GR": "Grecia", "CZ": "Rep. Ceca", "HU": "Ungheria",
    "HR": "Croazia", "SI": "Slovenia", "SK": "Slovacchia", "RO": "Romania",
    "BG": "Bulgaria", "EE": "Estonia", "LT": "Lituania", "LV": "Lettonia",
    "CY": "Cipro", "MT": "Malta", "LU": "Lussemburgo", "IN": "India",
    "KR": "Corea del Sud", "MX": "Messico", "TR": "Turchia", "IL": "Israele",
    "EG": "Egitto", "ZA": "Sudafrica", "NZ": "Nuova Zelanda",
    "WORLD": "Mondo (totale)", "WRL_X_ITA": "Estero (tutti i paesi)",
    "IT": "Italia (residenti)", "EU": "Unione Europea",
    "EUR_NEU": "Altri Europa non-UE", "EUR_OTH": "Altri Europa",
    "AFRMED": "Africa mediterranea", "AFR_OTH": "Altri Africa",
    "AME_N_OTH": "Altri America del Nord", "AME_C_S_OTH": "America centro-sud (altri)",
    "ASI_OTH": "Altri Asia", "ASI_W_OTH": "Asia occidentale (altri)",
    "OCE_OTH": "Altri Oceania",
}


def estero_country_name(code: str) -> str:
    """Nome leggibile del codice paese ISTAT (pass-through se non mappato)."""
    return _ISTAT_COUNTRY_NAME.get(code, code)


def _tur9_is_aggregate(c: str) -> bool:
    """True se il codice è un aggregato (mondo/ripartizioni continentali/UE) o l'Italia,
    non un singolo paese estero. CH_LI (Svizzera+Liechtenstein) è tenuto come mercato."""
    if c in {"WORLD", "WRL_X_ITA", "IT", "EU"}:
        return True
    if c.endswith("_OTH") or c.endswith("_NEU"):
        return True
    return c in {"AFRMED", "EUR", "AFR", "ASI", "AME", "OCE"}


@functools.lru_cache(maxsize=None)
def estero_regione_long():
    """Presenze/arrivi turisti ESTERI per PAESE × territorio (naz/regione/provincia),
    ANNUALE (ISTAT DCSC_TUR_9). DataFrame: area·datatype·country·anno·valore.
    None se la cache manca."""
    if not os.path.exists(_TUR9_PATH):
        return None
    df = pd.read_csv(_TUR9_PATH, dtype={"REF_AREA": str, "DATA_TYPE": str,
                                        "COUNTRY_RES_GUESTS": str})
    if df.empty:
        return None
    df = df.rename(columns={"REF_AREA": "area", "DATA_TYPE": "datatype",
                            "COUNTRY_RES_GUESTS": "country", "TIME_PERIOD": "anno",
                            "OBS_VALUE": "valore"})
    df["anno"] = pd.to_numeric(df["anno"], errors="coerce").astype("Int64")
    df["valore"] = pd.to_numeric(df["valore"], errors="coerce")
    return df.dropna(subset=["anno", "valore"])


def estero_markets(code: str, datatype: str = "NI", year: int | None = None,
                   only_countries: bool = True, top: int | None = None):
    """Classifica dei mercati esteri per la regione (o Italia): DataFrame
    country·nome·valore per l'anno scelto (o l'ultimo disponibile), ordinata desc.
    datatype: 'NI' presenze, 'AR' arrivi. only_countries esclude gli aggregati."""
    df = estero_regione_long()
    if df is None:
        return None
    area = RG.istat_area(code)
    d = df[(df["area"] == area) & (df["datatype"] == datatype)]
    if only_countries:
        d = d[~d["country"].map(_tur9_is_aggregate)]
    if d.empty:
        return None
    if year is None:
        year = int(d["anno"].max())
    d = d[d["anno"] == year].copy()
    if d.empty:
        return None
    d["nome"] = d["country"].map(estero_country_name)
    out = d.sort_values("valore", ascending=False)[["country", "nome", "valore"]].reset_index(drop=True)
    return out.head(top).reset_index(drop=True) if top else out


def estero_years(code: str, datatype: str = "NI"):
    """Anni disponibili per la regione/territorio (lista ordinata di int)."""
    df = estero_regione_long()
    if df is None:
        return []
    area = RG.istat_area(code)
    d = df[(df["area"] == area) & (df["datatype"] == datatype)]
    return sorted(int(a) for a in d["anno"].dropna().unique())


def estero_country_series(code: str, country: str, datatype: str = "NI"):
    """Serie storica annuale di un paese in una regione: DataFrame anno·valore."""
    df = estero_regione_long()
    if df is None:
        return None
    area = RG.istat_area(code)
    d = df[(df["area"] == area) & (df["datatype"] == datatype) & (df["country"] == country)]
    if d.empty:
        return None
    return d.sort_values("anno")[["anno", "valore"]].reset_index(drop=True)


# ════════════════════════════════════════════════════════════════════════════
# ISTAT — presenze mensili e capacità (per regione, tutte le 20)
# ════════════════════════════════════════════════════════════════════════════
def region_overview(code: str) -> dict:
    """Presenze mensili (totale + stranieri) e capacità della regione richiesta.
    Funziona per tutte le 20 regioni (ISTAT per NUTS2). Legge dai CSV di cache."""
    info = RG.region(code)
    area = RG.istat_area(code)
    stran = RS.fetch_istat_presences(area=area, country="WRL_X_ITA", start="2019-01", cache_dir=_CACHE)
    tot = RS.fetch_istat_presences(area=area, country="WORLD", start="2019-01", cache_dir=_CACHE)
    df = (stran.rename(columns={"presences": "stranieri"})
          .merge(tot.rename(columns={"presences": "totale"}), on="date", how="outer")
          .sort_values("date").reset_index(drop=True))
    letti = anno = None
    try:
        cap = RS.fetch_istat_capacity(area=area, cache_dir=_CACHE)
        letti, anno = int(cap["letti"].iloc[-1]), int(cap["anno"].iloc[-1])
    except Exception:  # noqa: BLE001
        pass
    return {"info": info, "presenze": df, "letti": letti, "anno_letti": anno}


# Registro variabili annuali della scheda Regione: chiave · etichetta · unità · decimali.
REGION_VARS = [
    ("presenze_tot", "Presenze totali", "n", 0),
    ("presenze_str", "Presenze straniere", "n", 0),
    ("quota_str", "Quota stranieri", "%", 1),
    ("spesa", "Spesa straniera", "M€", 0),
    ("spesa_per_viagg", "Spesa per viaggiatore", "€", 0),
    ("spesa_per_notte", "Spesa per notte", "€", 0),
    ("viaggiatori", "Viaggiatori stranieri", "migliaia", 0),
    ("notti", "Pernottamenti stranieri", "migliaia", 0),
    ("letti", "Posti letto", "n", 0),
    ("occ", "Occupazione", "%", 1),
]
REGION_VAR_LABEL = {k: lab for k, lab, _u, _d in REGION_VARS}
REGION_VAR_UNIT = {k: u for k, _l, u, _d in REGION_VARS}
REGION_VAR_DEC = {k: d for k, _l, _u, d in REGION_VARS}


@functools.lru_cache(maxsize=None)
def region_annual_panel(code: str) -> pd.DataFrame:
    """Pannello ANNUALE (anno × variabili) per regione o Italia. Unisce ISTAT (presenze
    mensili→somma annua su anni completi, capacità) e Banca d'Italia (spesa/notti/viaggiatori,
    anni completi). Aggiunge le derivate. Le celle mancanti restano NaN."""
    out: dict[int, dict] = {}
    try:
        p = region_overview(code)["presenze"].copy()
        p["anno"] = p["date"].dt.year
        for col, key in (("totale", "presenze_tot"), ("stranieri", "presenze_str")):
            if col in p:
                g = p.dropna(subset=[col]).groupby("anno")[col].agg(["sum", "count"])
                for y, r in g.iterrows():
                    if r["count"] >= 12:
                        out.setdefault(int(y), {})[key] = float(r["sum"])
    except Exception:  # noqa: BLE001
        pass
    g = bdi_region_annual(code)
    if g is not None and not g.empty:
        for _, r in g.iterrows():
            if r["trimestri"] >= 4:
                d = out.setdefault(int(r["anno"]), {})
                d["spesa"], d["notti"], d["viaggiatori"] = float(r["spesa"]), float(r["notti"]), float(r["viaggiatori"])
    try:
        cap = RS.fetch_istat_capacity(area=RG.istat_area(code), cache_dir=_CACHE)
        for _, r in cap.iterrows():
            out.setdefault(int(r["anno"]), {})["letti"] = float(r["letti"])
    except Exception:  # noqa: BLE001
        pass
    if not out:
        return pd.DataFrame()
    df = pd.DataFrame(out).T.sort_index()
    df.index.name = "anno"
    if {"presenze_str", "presenze_tot"} <= set(df.columns):
        df["quota_str"] = df["presenze_str"] / df["presenze_tot"] * 100
    if {"spesa", "viaggiatori"} <= set(df.columns):
        df["spesa_per_viagg"] = df["spesa"] * 1e6 / (df["viaggiatori"] * 1e3)
    if {"spesa", "notti"} <= set(df.columns):
        df["spesa_per_notte"] = df["spesa"] * 1e6 / (df["notti"] * 1e3)
    if {"presenze_tot", "letti"} <= set(df.columns):
        df["occ"] = df["presenze_tot"] / (df["letti"] * 365) * 100
    cols = [k for k, *_ in REGION_VARS if k in df.columns]
    return df[cols]


# ════════════════════════════════════════════════════════════════════════════
# RANKING regioni per spesa straniera (multi-regione by construction)
# ════════════════════════════════════════════════════════════════════════════
@functools.lru_cache(maxsize=None)
def regions_spend_ranking() -> tuple:
    """Classifica delle regioni per spesa turistica straniera 2024 (Banca d'Italia).
    Tupla di dict: code (NUTS2) · regione · spesa_M · rank. (tupla per l'lru_cache)."""
    ext = bdi_extended()
    spese = (ext or {}).get("regioni_2024", {})
    if not spese:
        return ()
    rows = []
    for code, info in RG.REGIONS.items():
        sp = spese.get(info["bdi"])
        if sp is not None:
            rows.append({"code": code, "regione": info["nome"], "spesa_M": float(sp)})
    rows.sort(key=lambda r: r["spesa_M"], reverse=True)
    for i, r in enumerate(rows):
        r["rank"] = i + 1
    return tuple(rows)


@functools.lru_cache(maxsize=None)
def bdi_region_years() -> tuple:
    """Anni con i 4 trimestri completi nella serie regionale BdI (per i selettori)."""
    df = bdi_region_long()
    if df is None or df.empty:
        return ()
    g = df.assign(anno=df["date"].dt.year).groupby("anno")["date"].nunique()
    return tuple(sorted(int(y) for y, n in g.items() if n >= 4))


@functools.lru_cache(maxsize=None)
def regions_spend_ranking_year(year: int) -> tuple:
    """Come regions_spend_ranking() ma per l'ANNO indicato (spesa straniera M€, BdI)."""
    df = bdi_region_long()
    if df is None or df.empty:
        return ()
    d = df[df["date"].dt.year == year]
    if d.empty:
        return ()
    by_name: dict[str, float] = {}
    for code, val in d.groupby("code")["spesa"].sum().items():
        info = RG.REGIONS.get(code)
        if info:
            by_name[info["bdi"]] = float(val)
    rows = []
    for code, info in RG.REGIONS.items():
        sp = by_name.get(info["bdi"])
        if sp is not None:
            rows.append({"code": code, "regione": info["nome"], "spesa_M": sp})
    rows.sort(key=lambda r: r["spesa_M"], reverse=True)
    for i, r in enumerate(rows):
        r["rank"] = i + 1
    return tuple(rows)


def region_spend(code: str):
    """(spesa_M, rank, totale_regioni) per la regione richiesta, o None.
    Per la vista nazionale: (totale_Italia, None, n_regioni) — rank=None = «Italia»."""
    rk = regions_spend_ranking()
    if RG.is_national(code):
        return (sum(r["spesa_M"] for r in rk), None, len(rk)) if rk else None
    bdi = RG.region(code)["bdi"]
    hit = next((r for r in rk if RG.REGIONS[r["code"]]["bdi"] == bdi), None)
    return (hit["spesa_M"], hit["rank"], len(rk)) if hit else None


# ════════════════════════════════════════════════════════════════════════════
# API DI ALTO LIVELLO per il layer UI (Reflex/Streamlit): tutto in tipi Python
# semplici (str/num/list), niente pandas/plotly. Multi-regione.
# ════════════════════════════════════════════════════════════════════════════
MESI_IT = ["Gen", "Feb", "Mar", "Apr", "Mag", "Giu", "Lug", "Ago", "Set", "Ott", "Nov", "Dic"]


def _it_int(n) -> str:
    """Intero con separatore delle migliaia all'italiana (1.234.567). '—' se None/NaN."""
    if n is None:
        return "—"
    try:
        return f"{int(round(float(n))):,}".replace(",", ".")
    except (TypeError, ValueError):
        return "—"


def regione_snapshot(code: str, top_mercati: int = 5) -> dict:
    """Quadro turistico sintetico di una regione (o Italia), in tipi Python puri.
    Pensato per alimentare direttamente lo stato di una UI (Reflex/Streamlit) senza
    che questa conosca pandas. Tutti i campi sono robusti ai dati mancanti."""
    info = RG.region(code)
    ov = region_overview(code)
    pres = ov["presenze"]

    # serie mensile presenze straniere (ultimi 24 mesi disponibili)
    serie_x: list[str] = []
    serie_y: list[float] = []
    ultimo_mese = None
    if pres is not None and not pres.empty and "stranieri" in pres:
        s = pres.dropna(subset=["stranieri"]).tail(24)
        for _, r in s.iterrows():
            d = r["date"]
            serie_x.append(f"{MESI_IT[d.month - 1]} {str(d.year)[2:]}")
            serie_y.append(float(r["stranieri"]))
        if serie_y:
            ultimo_mese = serie_y[-1]

    # spesa e posizione in classifica
    sp = region_spend(code)
    if sp is None:
        spesa_M, rank, n_reg = None, None, None
    else:
        spesa_M, rank, n_reg = sp

    # top mercati esteri (presenze, ultimo anno disponibile)
    mkt = estero_markets(code, top=top_mercati)
    mercati_top = ([] if mkt is None
                   else [{"nome": r["nome"], "valore": float(r["valore"])} for _, r in mkt.iterrows()])
    anni = estero_years(code)
    anno_mkt = anni[-1] if anni else None
    n_mercati_tot = estero_markets(code)
    n_mercati = 0 if n_mercati_tot is None else len(n_mercati_tot)

    if RG.is_national(code):
        rank_label = "Totale Italia"
    elif rank and n_reg:
        rank_label = f"{rank}ª su {n_reg} regioni"
    else:
        rank_label = "—"

    return {
        "code": code,
        "nome": info["nome"],
        "titolo": f"{info['nome']} — quadro turistico",
        # KPI (stringhe formattate, pronte per la UI)
        "kpi_presenze": _it_int(ultimo_mese),
        "kpi_presenze_periodo": (serie_x[-1] if serie_x else "—"),
        "kpi_letti": _it_int(ov["letti"]),
        "kpi_letti_anno": (f"capacità {ov['anno_letti']}" if ov["anno_letti"] else "capacità"),
        "kpi_spesa": (f"{_it_int(spesa_M)} M€" if spesa_M is not None else "—"),
        "kpi_spesa_rank": rank_label,
        "kpi_mercati": str(n_mercati),
        "kpi_mercati_anno": (f"paesi di origine · {anno_mkt}" if anno_mkt else "paesi di origine"),
        # serie e classifiche (dati grezzi per i grafici)
        "serie_mesi": serie_x,
        "serie_presenze": serie_y,
        "mercati_top": mercati_top,
        "mercati_anno": anno_mkt,
    }


REGIONI_SELECT = [(info["nome"], code) for code, info in RG.REGIONS.items()]


# ── self-check: `python tdh_data.py` stampa numeri REALI per alcune regioni ──
if __name__ == "__main__":
    for _c in ("ITE1", "ITC4", "ITF1", "ITALIA"):
        try:
            s = regione_snapshot(_c)
        except Exception as e:  # noqa: BLE001
            print(f"{_c}: ERRORE {type(e).__name__}: {e}")
            continue
        print(f"\n== {s['nome']} ({_c}) ==")
        print(f"  presenze straniere ultimo mese ({s['kpi_presenze_periodo']}): {s['kpi_presenze']}")
        print(f"  posti letto: {s['kpi_letti']} ({s['kpi_letti_anno']})")
        print(f"  spesa straniera: {s['kpi_spesa']}  [{s['kpi_spesa_rank']}]")
        print(f"  mercati esteri: {s['kpi_mercati']} ({s['kpi_mercati_anno']})")
        print(f"  serie: {len(s['serie_presenze'])} mesi; top mercati: "
              + ", ".join(f"{m['nome']} {m['valore']:,.0f}" for m in s["mercati_top"]))
