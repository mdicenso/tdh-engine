"""
Adattatori dati REALI per il motore wedge (rete aperta, dietro proxy aziendale).

Usa urllib (stdlib): sfrutta il trust store di Windows, quindi passa l'ispezione
TLS del proxy Indra senza configurazione extra (httpx/certifi invece fallirebbe).

Pezzi implementati:
    fetch_fx_monthly(currency, start, end)  -> cambio mensile, indice (media = 1.0)   [ECB SDW]

Da implementare nei prossimi giri (vedi note in fondo):
    fetch_presences_foreign_monthly(...)    -> presenze straniere aggregate Abruzzo    [ISTAT SDMX]
    fetch_search_monthly(...)               -> interesse di ricerca per paese          [Google Trends]
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import time
import urllib.request
import urllib.error

import numpy as np
import pandas as pd

# Convenzione del motore: fx è un INDICE attorno a 1.0 (1.0 = media del periodo);
# euro più forte (fx > 1.0) deprime gli arrivi non-Euro, euro debole (fx < 1.0) li favorisce.
ECB_EXR = "https://data-api.ecb.europa.eu/service/data/EXR/M.{cur}.EUR.SP00.A"


def _http_json(url: str, timeout: int = 30) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def fetch_fx_monthly(currency: str, start: str = "2019-01", end: str | None = None) -> pd.DataFrame:
    """Cambio mensile come indice (media periodo = 1.0).

    currency: "USD", "GBP", "CHF", ... oppure "EUR" (mercato Euro -> fx costante 1.0).
    Ritorna DataFrame con colonne: date (primo giorno mese), fx.
    Per i mercati Euro restituisce 1.0 su tutto l'arco temporale richiesto.
    """
    cur = currency.upper()
    rng_end = end or pd.Timestamp.today().strftime("%Y-%m")
    months = pd.period_range(start, rng_end, freq="M").to_timestamp()

    if cur == "EUR":
        return pd.DataFrame({"date": months, "fx": np.ones(len(months))})

    url = ECB_EXR.format(cur=cur) + f"?format=jsondata&startPeriod={start}&endPeriod={rng_end}"
    try:
        data = _http_json(url)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"ECB EXR per {cur}: HTTP {e.code} {e.reason}") from e

    # struttura SDMX-JSON: periodi in structure.dimensions.observation[0].values,
    # valori in dataSets[0].series[<chiave>].observations[<indice>][0]
    obs_dim = data["structure"]["dimensions"]["observation"][0]["values"]
    periods = [v["id"] for v in obs_dim]              # es. "2019-01"
    series = data["dataSets"][0]["series"]
    key = next(iter(series))                          # unica serie: M.CUR.EUR.SP00.A
    obs = series[key]["observations"]

    rows = []
    for idx_str, val in obs.items():
        i = int(idx_str)
        v = val[0]
        if v is None:
            continue
        rows.append((pd.Timestamp(periods[i] + "-01"), float(v)))  # CUR per 1 EUR
    df = pd.DataFrame(rows, columns=["date", "rate"]).sort_values("date").reset_index(drop=True)

    # normalizzo a indice media=1.0 (alta = euro forte = sfavorevole agli arrivi)
    df["fx"] = df["rate"] / df["rate"].mean()
    return df[["date", "fx"]]


# --------------------------------------------------------------------------
# ISTAT — presenze straniere AGGREGATE di Abruzzo, mensili (target del motore, Opzione A).
# NB: ISTAT NON espone le presenze mensili per singolo paese a livello regionale,
# solo IT / WRL_X_ITA / WORLD. Vedi memoria 'istat-tourism-data-constraint'.
# L'endpoint dati ISTAT è lento/instabile: usiamo timeout ampio, host alternativo e cache su disco.
# --------------------------------------------------------------------------
ISTAT_HOSTS = [
    "https://esploradati.istat.it/SDMXWS/rest",
    "http://sdmx.istat.it/SDMXWS/rest",   # mirror storico (a volte più reattivo)
]
# dataflow 'Movimento dei clienti'; chiave nell'ordine delle 11 dimensioni DCSC_TUR:
# FREQ.REF_AREA.DATA_TYPE.ADJUSTMENT.TYPE_ACCOMMODATION.ECON.COUNTRY.LOCALITY.URBANIZ.COASTAL.SIZE
ISTAT_DATAFLOW = "122_54_DF_DCSC_TUR_7"
ISTAT_KEY_PRESENZE_STRANIERE = "M.ITF1.NI..ALL..WRL_X_ITA...."  # NI=presenze, ALL=tutti gli alloggi, WRL_X_ITA=stranieri


def fetch_presences_foreign_monthly(start: str = "2019-01", end: str | None = None,
                                    cache_dir: str = ".cache", timeout: int = 300,
                                    refresh: bool = False) -> pd.DataFrame:
    """Presenze straniere aggregate mensili di Abruzzo (target ISTAT reale).

    Ritorna DataFrame con colonne: date, presences.
    Con cache su disco (CSV): la prima fetch è lenta (ISTAT), le successive sono istantanee.
    Passa refresh=True per forzare il riscarico.
    """
    os.makedirs(cache_dir, exist_ok=True)
    cache_path = os.path.join(cache_dir, "istat_presenze_straniere_abruzzo.csv")
    if os.path.exists(cache_path) and not refresh:
        df = pd.read_csv(cache_path, parse_dates=["date"])
        return df

    rng_end = end or pd.Timestamp.today().strftime("%Y-%m")
    qs = f"?startPeriod={start}&endPeriod={rng_end}&detail=full"
    last_err = None
    for host in ISTAT_HOSTS:
        url = f"{host}/data/{ISTAT_DATAFLOW}/{ISTAT_KEY_PRESENZE_STRANIERE}{qs}"
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/vnd.sdmx.data+json;version=1.0.0-wd"})
            raw = urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", "ignore")
            df = _parse_sdmx_json_presences(raw)
            df.to_csv(cache_path, index=False)
            return df
        except Exception as e:  # noqa: BLE001 (host lento/irraggiungibile: provo il successivo)
            last_err = e
            continue
    raise RuntimeError(f"ISTAT non raggiungibile su nessun host (ultimo errore: {type(last_err).__name__}: {last_err})")


def _parse_sdmx_json_presences(raw: str) -> pd.DataFrame:
    """Estrae date/presences da SDMX-JSON 2.0 (ISTAT esploradati: tutto sotto 'data')."""
    d = json.loads(raw)["data"]
    periods = [v["id"] for v in d["structure"]["dimensions"]["observation"][0]["values"]]
    series = d["dataSets"][0]["series"]
    obs = series[next(iter(series))]["observations"]
    rows = [(pd.Timestamp(periods[int(i)] + "-01"), float(o[0]))
            for i, o in obs.items() if o and o[0] is not None]
    return pd.DataFrame(sorted(rows), columns=["date", "presences"])


# Province d'Abruzzo (NUTS3) per le viste territoriali
ISTAT_PROVINCES = {"ITF11": "L'Aquila", "ITF12": "Teramo", "ITF13": "Pescara", "ITF14": "Chieti"}


def fetch_istat_presences(area: str = "ITF1", data_type: str = "NI", accom: str = "ALL",
                          country: str = "WRL_X_ITA", start: str = "2019-01", end: str | None = None,
                          cache_dir: str = ".cache", timeout: int = 120, refresh: bool = False) -> pd.DataFrame:
    """Adattatore ISTAT generale (DCSC_TUR), con cache su disco per ogni combinazione.

    area   : REF_AREA — ITF1 (Abruzzo) o province ITF11..ITF14
    data_type : NI (presenze) | AR (arrivi)
    accom  : TYPE_ACCOMMODATION — ALL | HOTELLIKE | OTHER
    country: COUNTRY_RES_GUESTS — WORLD (totale) | IT (italiani) | WRL_X_ITA (stranieri)
    Ritorna DataFrame con colonne: date, presences (il valore della metrica scelta).
    """
    os.makedirs(cache_dir, exist_ok=True)
    cache_path = os.path.join(cache_dir, f"istat_{area}_{data_type}_{accom}_{country}.csv")
    if os.path.exists(cache_path) and not refresh:
        return pd.read_csv(cache_path, parse_dates=["date"])
    rng_end = end or pd.Timestamp.today().strftime("%Y-%m")
    key = f"M.{area}.{data_type}..{accom}..{country}...."
    qs = f"?startPeriod={start}&endPeriod={rng_end}&detail=full"
    last_err = None
    for _att in range(3):  # ISTAT dà 404/timeout transitori: ritento
        for host in ISTAT_HOSTS:
            try:
                req = urllib.request.Request(f"{host}/data/{ISTAT_DATAFLOW}/{key}{qs}",
                                             headers={"Accept": "application/vnd.sdmx.data+json;version=1.0.0-wd"})
                raw = urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", "ignore")
                df = _parse_sdmx_json_presences(raw)
                df.to_csv(cache_path, index=False)
                return df
            except Exception as e:  # noqa: BLE001
                last_err = e
                continue
        import time
        time.sleep(3)
    raise RuntimeError(f"ISTAT non raggiungibile per {key} ({type(last_err).__name__}: {last_err})")


# --------------------------------------------------------------------------
# GOOGLE TRENDS — interesse di ricerca per paese (segnale leading per-mercato).
# Nota di metodo: Trends normalizza 0..100 SEPARATAMENTE per ogni query/geo, quindi
# i livelli NON sono confrontabili tra paesi in assoluto; va benissimo come segnale di
# MOMENTUM per-mercato (variazione nel tempo dentro lo stesso paese), che è l'uso del motore.
# geo = codice ISO paese: DE, AT, GB, US, NL, CH (coincide con Market.code).
# requests/pytrends usano certifi -> serve truststore per il proxy Indra (iniettato lazy qui).
# --------------------------------------------------------------------------
def fetch_search_monthly(geo: str, keyword: str = "Abruzzo", start: str = "2019-01",
                         end: str | None = None, cache_dir: str = ".cache",
                         pause: float = 2.0, refresh: bool = False) -> pd.DataFrame:
    """Interesse di ricerca mensile per `keyword` nel paese `geo` (Google Trends).

    Ritorna DataFrame con colonne: date, search (0..100, media mensile).
    Con cache su disco per-geo: una fetch a mercato, poi istantaneo (riduce i 429 di Google).
    """
    os.makedirs(cache_dir, exist_ok=True)
    safe_kw = "".join(c if c.isalnum() else "_" for c in keyword.lower())
    cache_path = os.path.join(cache_dir, f"trends_{safe_kw}_{geo}.csv")
    if os.path.exists(cache_path) and not refresh:
        return pd.read_csv(cache_path, parse_dates=["date"])

    import time
    try:
        import truststore
        truststore.inject_into_ssl()  # CA aziendale Indra anche per requests (idempotente)
    except Exception:  # noqa: BLE001 — in cloud/CI senza proxy non serve
        pass
    from pytrends.request import TrendReq

    rng_end = end or pd.Timestamp.today().strftime("%Y-%m")
    end_day = (pd.Period(rng_end, freq="M").to_timestamp(how="end")).strftime("%Y-%m-%d")
    timeframe = f"{start}-01 {end_day}"

    if pause:
        time.sleep(pause)  # cortesia: riduce il rischio di 429
    py = TrendReq(hl="it-IT", tz=60, timeout=(10, 25))
    py.build_payload([keyword], timeframe=timeframe, geo=geo)
    raw = py.interest_over_time()
    if raw.empty:
        raise RuntimeError(f"Google Trends: nessun dato per '{keyword}' geo={geo}")
    if "isPartial" in raw.columns:
        raw = raw[~raw["isPartial"].astype(bool)] if raw["isPartial"].dtype != object else raw
        raw = raw.drop(columns=["isPartial"])

    monthly = raw[[keyword]].resample("MS").mean().round(1)  # settimanale -> media mensile (mese inizio)
    out = monthly.reset_index().rename(columns={"index": "date", keyword: "search"})
    out = out.rename(columns={out.columns[0]: "date"})
    out.to_csv(cache_path, index=False)
    return out


# --------------------------------------------------------------------------
# ISTAT — CAPACITÀ ricettiva (posti letto) annuale, dataflow DCSC_TUR_1, DATA_TYPE=BEDS.
# Stessa infrastruttura SDMX delle presenze (host alternativi + cache). Chiave a 11
# dimensioni: A.<area>.BEDS..ALL...... (annuale, tutti gli alloggi).
# --------------------------------------------------------------------------
ISTAT_DATAFLOW_CAPACITY = "122_54_DF_DCSC_TUR_1"


def fetch_istat_capacity(area: str = "ITF1", start: str = "2002", cache_dir: str = ".cache",
                         timeout: int = 120, refresh: bool = False) -> pd.DataFrame:
    """Posti letto annuali (capacità ricettiva totale) per area ISTAT.

    Ritorna DataFrame con colonne: anno, letti. Con cache su disco.
    """
    os.makedirs(cache_dir, exist_ok=True)
    cache_path = os.path.join(cache_dir, f"istat_capacity_letti_{area}.csv")
    if os.path.exists(cache_path) and not refresh:
        return pd.read_csv(cache_path)
    key = ".".join(["A", area, "BEDS", "", "ALL", "", "", "", "", "", ""])
    qs = f"?startPeriod={start}&detail=full"
    last_err = None
    for _att in range(3):
        for host in ISTAT_HOSTS:
            try:
                req = urllib.request.Request(f"{host}/data/{ISTAT_DATAFLOW_CAPACITY}/{key}{qs}",
                                             headers={"Accept": "application/vnd.sdmx.data+json;version=1.0.0-wd"})
                raw = urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", "ignore")
                d = json.loads(raw)["data"]
                periods = [v["id"] for v in d["structure"]["dimensions"]["observation"][0]["values"]]
                series = d["dataSets"][0]["series"]
                obs = series[next(iter(series))]["observations"]
                rows = sorted((int(periods[int(i)]), float(o[0]))
                              for i, o in obs.items() if o and o[0] is not None)
                df = pd.DataFrame(rows, columns=["anno", "letti"])
                df.to_csv(cache_path, index=False)
                return df
            except Exception as e:  # noqa: BLE001
                last_err = e
                continue
        import time
        time.sleep(3)
    raise RuntimeError(f"ISTAT capacità non raggiungibile ({type(last_err).__name__}: {last_err})")


# --------------------------------------------------------------------------
# ISTAT — ESTERI per PAESE × territorio (regione/provincia), ANNUALE, dataflow
# DCSC_TUR_9. Scarica per-territorio (richieste piccole, retry sui 502/timeout)
# e scrive un unico CSV lungo: REF_AREA,DATA_TYPE,COUNTRY_RES_GUESTS,TIME_PERIOD,OBS_VALUE.
# Dimensioni secondarie fissate (ALL/TOT) per evitare righe doppie.
# --------------------------------------------------------------------------
ISTAT_DATAFLOW_ESTERO = "122_54_DF_DCSC_TUR_9"
ISTAT_ESTERO_CACHE = "istat_estero_regione_prov_annuale.csv"
_ESTERO_FIELDS = ["REF_AREA", "DATA_TYPE", "COUNTRY_RES_GUESTS", "TIME_PERIOD", "OBS_VALUE"]
# nazionale + 22 regioni NUTS2 storiche + province NUTS3
ISTAT_ESTERO_TERR = [
    "IT", "ITC1", "ITC2", "ITC3", "ITC4", "ITD1", "ITD2", "ITDA", "ITD3", "ITD4", "ITD5",
    "ITE1", "ITE2", "ITE3", "ITE4", "ITF1", "ITF2", "ITF3", "ITF4", "ITF5", "ITF6", "ITG1", "ITG2",
    "IT108", "IT109", "IT110", "IT111",
    "ITC11", "ITC12", "ITC13", "ITC14", "ITC15", "ITC16", "ITC17", "ITC18", "ITC20",
    "ITC31", "ITC32", "ITC33", "ITC34", "ITC41", "ITC42", "ITC43", "ITC44", "ITC45", "ITC46",
    "ITC47", "ITC48", "ITC49", "ITC4A", "ITC4B",
    "ITD10", "ITD20", "ITD31", "ITD32", "ITD33", "ITD34", "ITD35", "ITD36", "ITD37",
    "ITD41", "ITD42", "ITD43", "ITD44", "ITD51", "ITD52", "ITD53", "ITD54", "ITD55", "ITD56",
    "ITD57", "ITD58", "ITD59",
    "ITE11", "ITE12", "ITE13", "ITE14", "ITE15", "ITE16", "ITE17", "ITE18", "ITE19", "ITE1A",
    "ITE21", "ITE22", "ITE31", "ITE32", "ITE33", "ITE34", "ITE41", "ITE42", "ITE43", "ITE44", "ITE45",
    "ITF11", "ITF12", "ITF13", "ITF14", "ITF21", "ITF22", "ITF31", "ITF32", "ITF33", "ITF34", "ITF35",
    "ITF41", "ITF42", "ITF43", "ITF44", "ITF45", "ITF51", "ITF52", "ITF61", "ITF62", "ITF63",
    "ITF64", "ITF65",
    "ITG11", "ITG12", "ITG13", "ITG14", "ITG15", "ITG16", "ITG17", "ITG18", "ITG19",
    "ITG25", "ITG26", "ITG27", "ITG28"]


def _fetch_estero_territory(terr: str, start: str = "2008", end: str = "2026",
                            timeout: int = 90, tries: int = 3) -> list[dict]:
    """Righe (dict) di un territorio: AR+NI, tutti i paesi, annuale. [] se 404 (senza dati)."""
    key = f"A.{terr}.AR+NI.N.ALL.551_553..ALL.ALL.ALL.TOT"
    qs = (f"?detail=dataonly&startPeriod={start}&endPeriod={end}"
          f"&dimensionAtObservation=TIME_PERIOD")
    last_err = None
    for _att in range(tries):
        for host in ISTAT_HOSTS:
            try:
                url = f"{host}/data/IT1,{ISTAT_DATAFLOW_ESTERO},1.0/{key}/ALL/{qs}"
                req = urllib.request.Request(
                    url, headers={"Accept": "application/vnd.sdmx.data+csv;version=1.0.0"})
                raw = urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", "replace")
                rows = list(csv.DictReader(io.StringIO(raw)))
                return [{k: r.get(k, "") for k in _ESTERO_FIELDS} for r in rows if r.get("OBS_VALUE")]
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    return []
                last_err = e
            except Exception as e:  # noqa: BLE001
                last_err = e
        time.sleep(4)
    raise RuntimeError(f"ISTAT estero {terr}: {type(last_err).__name__}")


def fetch_estero_country_region_annual(start: str = "2008", end: str = "2026",
                                       cache_dir: str = ".cache", timeout: int = 90,
                                       refresh: bool = False, progress=None) -> pd.DataFrame:
    """Turisti esteri per PAESE × territorio (naz/regione/provincia), ANNUALE (DCSC_TUR_9).
    Scarica per-territorio con retry; i territori che falliscono mantengono le righe già in
    cache (nessuna perdita dati su refresh parziale). Scrive un unico CSV lungo e lo ritorna."""
    os.makedirs(cache_dir, exist_ok=True)
    cache_path = os.path.join(cache_dir, ISTAT_ESTERO_CACHE)
    if os.path.exists(cache_path) and not refresh:
        return pd.read_csv(cache_path)
    existing: dict[str, list[dict]] = {}
    if os.path.exists(cache_path):
        try:
            old = pd.read_csv(cache_path, dtype=str)
            for terr, grp in old.groupby("REF_AREA"):
                existing[terr] = grp[_ESTERO_FIELDS].to_dict("records")
        except Exception:  # noqa: BLE001
            pass
    data: dict[str, list[dict]] = {}
    for i, terr in enumerate(ISTAT_ESTERO_TERR, 1):
        try:
            data[terr] = _fetch_estero_territory(terr, start, end, timeout)
        except Exception:  # noqa: BLE001 — refresh fallito: tieni il vecchio (no perdita dati)
            data[terr] = existing.get(terr, [])
        if progress:
            progress(i, len(ISTAT_ESTERO_TERR), terr)
    allrows = [r for terr in data for r in data[terr]]
    df = pd.DataFrame(allrows, columns=_ESTERO_FIELDS)
    df.to_csv(cache_path, index=False)
    return df


def fetch_estero_latest_year(timeout: int = 60) -> int | None:
    """Anno più recente disponibile alla fonte — probe LEGGERO (un solo territorio, ITF1).
    Serve al controllo settimanale per decidere se vale la pena riscaricare tutto."""
    try:
        rows = _fetch_estero_territory("ITF1", start="2020", end="2026", timeout=timeout, tries=2)
    except Exception:  # noqa: BLE001
        return None
    yrs = [int(r["TIME_PERIOD"]) for r in rows if str(r.get("TIME_PERIOD", "")).isdigit()]
    return max(yrs) if yrs else None


# --------------------------------------------------------------------------
# ASTAT — Provincia Autonoma di Bolzano / Alto Adige (SDMX proprio, host astatsdmxservices).
# Dataflow DF_TOUR_ACC_CAP_TOURASS_MONTHLY_1: capacità ricettiva + flussi turistici, MENSILE.
# Fonte COMPLEMENTARE (una sola provincia): non è una base multi-regione e non ha il paese
# di origine, ma dà mensilità recente (fino 2026) e il LATO OFFERTA (esercizi/posti letto per
# categoria) che le basi ISTAT nazionali non danno. Ordine dimensioni della key:
#   FREQ . TYPE_PERIOD . TYPE_GEO . TOUR_GEO . CATEGORY . INDICATOR
# Nessun proxy/auth: risponde in SDMX-CSV direttamente.
# --------------------------------------------------------------------------
ASTAT_BASE = "https://astatsdmxservices.prov.bz.it/dsm/NSI_WS/rest/data"
ASTAT_DATAFLOW = "ITH1,DF_TOUR_ACC_CAP_TOURASS_MONTHLY_1,1.0"
ASTAT_FLOWS_CACHE = "astat_bolzano_flussi_mensili.csv"
ASTAT_CAP_CACHE = "astat_bolzano_capacita_categoria.csv"
# categorie ricettive (codice ASTAT -> etichetta italiana), ordine di presentazione
ASTAT_CATEGORIES = {
    "TOTAL": "Totale", "A": "Alberghiero", "01_03": "4-5 stelle", "05": "3 stelle",
    "07_09": "1-2 stelle", "11": "Residence", "E": "Extralberghiero", "17": "Campeggi",
    "21": "Alloggi privati", "23": "Agriturismi", "99": "Altri esercizi"}


def _astat_fetch(key: str, start: str, end: str, timeout: int = 120,
                 tries: int = 3) -> list[dict]:
    """Righe grezze (dict SDMX-CSV) del dataflow ASTAT per una key. [] se 404."""
    qs = (f"?detail=dataonly&startPeriod={start}&endPeriod={end}"
          f"&dimensionAtObservation=TIME_PERIOD")
    url = f"{ASTAT_BASE}/{ASTAT_DATAFLOW}/{key}/ALL/{qs}"
    last_err = None
    for _att in range(tries):
        try:
            req = urllib.request.Request(
                url, headers={"Accept": "application/vnd.sdmx.data+csv;version=1.0.0"})
            raw = urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", "replace")
            return list(csv.DictReader(io.StringIO(raw), delimiter=";"))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return []
            last_err = e
        except Exception as e:  # noqa: BLE001
            last_err = e
        time.sleep(4)
    raise RuntimeError(f"ASTAT {key}: {type(last_err).__name__}")


def fetch_astat_flussi_mensili(start: str = "1990-01-01", end: str = "2026-12-31",
                               cache_dir: str = ".cache", timeout: int = 120,
                               refresh: bool = False) -> pd.DataFrame:
    """Flussi turistici MENSILI dell'intero Alto Adige (arrivi + presenze).
    Colonne: date (primo giorno mese), arrivi, presenze. Cache CSV."""
    os.makedirs(cache_dir, exist_ok=True)
    cache_path = os.path.join(cache_dir, ASTAT_FLOWS_CACHE)
    if os.path.exists(cache_path) and not refresh:
        return pd.read_csv(cache_path, parse_dates=["date"])
    key = "M.CALENDER_YEAR.TOUR_FEDERATION.TOTAL.TOTAL.ARRIVALS_N+OVERNIGHTS_N"
    rows = _astat_fetch(key, start, end, timeout)
    rec: dict[str, dict] = {}
    for r in rows:
        v = r.get("OBS_VALUE")
        if not v:
            continue
        tp = r.get("TIME_PERIOD", "")
        d = rec.setdefault(tp, {"date": tp})
        if r.get("INDICATOR") == "ARRIVALS_N":
            d["arrivi"] = float(v)
        elif r.get("INDICATOR") == "OVERNIGHTS_N":
            d["presenze"] = float(v)
    df = pd.DataFrame(sorted(rec.values(), key=lambda x: x["date"]))
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"] + "-01")
    df.to_csv(cache_path, index=False)
    return df


def fetch_astat_capacita_categoria(start: str = "2010", end: str = "2026",
                                   cache_dir: str = ".cache", timeout: int = 120,
                                   refresh: bool = False) -> pd.DataFrame:
    """Capacità ricettiva ANNUALE dell'Alto Adige per categoria (esercizi + posti letto).
    Colonne: anno, cat_code, categoria, esercizi, posti_letto. Cache CSV."""
    os.makedirs(cache_dir, exist_ok=True)
    cache_path = os.path.join(cache_dir, ASTAT_CAP_CACHE)
    if os.path.exists(cache_path) and not refresh:
        return pd.read_csv(cache_path)
    cats = "+".join(ASTAT_CATEGORIES.keys())
    key = f"A.CALENDER_YEAR.TOUR_FEDERATION.TOTAL.{cats}.ESTABLISHMENTS_N+BEDS_N"
    rows = _astat_fetch(key, start, end, timeout)
    rec: dict[tuple, dict] = {}
    for r in rows:
        v = r.get("OBS_VALUE")
        if not v:
            continue
        yr = r.get("TIME_PERIOD", ""); cc = r.get("CATEGORY", "")
        d = rec.setdefault((yr, cc), {
            "anno": yr, "cat_code": cc, "categoria": ASTAT_CATEGORIES.get(cc, cc)})
        if r.get("INDICATOR") == "ESTABLISHMENTS_N":
            d["esercizi"] = float(v)
        elif r.get("INDICATOR") == "BEDS_N":
            d["posti_letto"] = float(v)
    df = pd.DataFrame(rec.values())
    if not df.empty:
        df = df.sort_values(["anno", "cat_code"]).reset_index(drop=True)
    df.to_csv(cache_path, index=False)
    return df


def fetch_astat_bolzano(cache_dir: str = ".cache", refresh: bool = False,
                        timeout: int = 120) -> dict:
    """Comodità: assicura entrambe le cache ASTAT (flussi + capacità) e le ritorna.
    Ritorna {'flussi': df, 'capacita': df}."""
    return {
        "flussi": fetch_astat_flussi_mensili(cache_dir=cache_dir, refresh=refresh, timeout=timeout),
        "capacita": fetch_astat_capacita_categoria(cache_dir=cache_dir, refresh=refresh, timeout=timeout),
    }


def fetch_astat_latest_period(timeout: int = 60) -> str | None:
    """Mese più recente disponibile alla fonte (probe leggero) — es. '2026-05'.
    Serve al controllo settimanale per decidere se riscaricare."""
    try:
        rows = _astat_fetch("M.CALENDER_YEAR.TOUR_FEDERATION.TOTAL.TOTAL.OVERNIGHTS_N",
                            "2025-01-01", "2026-12-31", timeout=timeout, tries=2)
    except Exception:  # noqa: BLE001
        return None
    tps = [r.get("TIME_PERIOD", "") for r in rows if r.get("OBS_VALUE")]
    return max(tps) if tps else None


# --------------------------------------------------------------------------
# OPEN DATA LOMBARDIA — Socrata (dati.lombardia.it). Fonte COMPLEMENTARE regionale ricca:
# flussi turistici MENSILI per PROVINCIA × PROVENIENZA (regioni IT + paesi esteri) ×
# alberghiero/extra, arrivi + presenze (dataset xzck-giqt, 2019-2024). A differenza di ASTAT
# ha il MERCATO ESTERO mensile a livello sub-nazionale (colonna provenienza_turisti).
# API SODA: JSON/CSV con $select/$where/$limit, nessun proxy/auth.
# --------------------------------------------------------------------------
LOMB_SOCRATA = "https://www.dati.lombardia.it/resource/xzck-giqt.json"
LOMB_CACHE = "lombardia_flussi_provincia_mese.csv"
LOMB_FIELDS = ["anno", "provincia", "mese", "provenienza_turisti",
               "arrivi_totale", "presenze_totale",
               "arrivi_alberghiero", "presenze_alberghiero",
               "arrivi_extra_alberghiero", "presenze_extra_alberghiero"]
# normalizzazioni note (dati sporchi alla fonte)
_LOMB_FIX_PROV = {"Monza Brianza": "Monza e Brianza", "Monza E Brianza": "Monza e Brianza"}
_LOMB_FIX_PROV_NIENZA = {"Austrialia": "Australia", "Israel": "Israele"}


def _lomb_get(params: dict, timeout: int = 90) -> list[dict]:
    import urllib.parse
    url = LOMB_SOCRATA + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    raw = urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", "replace")
    return json.loads(raw)


def fetch_lombardia_flussi(cache_dir: str = ".cache", timeout: int = 120,
                           refresh: bool = False) -> pd.DataFrame:
    """Flussi turistici MENSILI per provincia lombarda × provenienza × categoria (Socrata).
    Colonne LOMB_FIELDS, valori numerici come float. Cache CSV. Scarica a pagine da 50k."""
    os.makedirs(cache_dir, exist_ok=True)
    cache_path = os.path.join(cache_dir, LOMB_CACHE)
    if os.path.exists(cache_path) and not refresh:
        return pd.read_csv(cache_path)
    rows, offset, page = [], 0, 50000
    while True:
        batch = _lomb_get({"$limit": page, "$offset": offset,
                           "$order": "anno,provincia,mese"}, timeout)
        rows.extend(batch)
        if len(batch) < page:
            break
        offset += page
    df = pd.DataFrame(rows)
    for c in LOMB_FIELDS:
        if c not in df.columns:
            df[c] = None
    df = df[LOMB_FIELDS].copy()
    df["provincia"] = df["provincia"].replace(_LOMB_FIX_PROV)
    df["provenienza_turisti"] = df["provenienza_turisti"].replace(_LOMB_FIX_PROV_NIENZA)
    for c in [c for c in LOMB_FIELDS if c.startswith(("arrivi", "presenze"))]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df.to_csv(cache_path, index=False)
    return df


def fetch_lombardia_latest_year(timeout: int = 60) -> int | None:
    """Anno più recente disponibile alla fonte (probe leggero)."""
    try:
        r = _lomb_get({"$select": "max(anno) as b"}, timeout)
        return int(r[0]["b"]) if r and r[0].get("b") else None
    except Exception:  # noqa: BLE001
        return None


# --------------------------------------------------------------------------
# OPEN DATA REGIONE TOSCANA — CKAN (dati.toscana.it). Fonte COMPLEMENTARE regionale:
# movimento clienti ANNUALE a livello COMUNALE (~272 comuni) con split italiani/stranieri,
# 2018-2025. Punto di forza: granularità COMUNE + ambito turistico (unica tra le fonti
# locali). Un dataset CKAN per anno ("Movimento dei clienti ... Anno YYYY"), enumerati via
# package_search + risorsa CSV "movimento". Formati eterogenei fra anni (wide 2024-25;
# long ; oppure TAB 2018-23; provenienza "Italiani/Stranieri" o "ITA/STR") normalizzati a
# uno schema unico TOSC_FIELDS. Encoding cp1252, separatori ; o \t.
# --------------------------------------------------------------------------
TOSC_CKAN = "https://dati.toscana.it/api/3/action/package_search"
TOSC_QUERY = "movimento clienti offerta ricettiva toscana"
TOSC_CACHE = "toscana_movimento_comune_anno.csv"
TOSC_FIELDS = ["anno", "sigla_provincia", "comune", "cod_istat", "ambito",
               "arrivi_italiani", "arrivi_stranieri",
               "presenze_italiane", "presenze_straniere"]
_TOSC_ITA = {"italiani", "italia", "ita", "residenti", "italiane", "italiano"}
_TOSC_STR = {"stranieri", "estero", "str", "esteri", "straniere", "nonresidenti", "straniero"}


def _tosc_norm(s: str) -> str:
    return re.sub(r"[^a-z]", "", (s or "").lower())


def _tosc_canonkey(h: str) -> str:
    """Riconduce le intestazioni eterogenee dei file annuali a chiavi canoniche."""
    n = _tosc_norm(h)
    if n == "anno":
        return "anno"
    if n == "comune":
        return "comune"
    if "istat" in n:
        return "cod_istat"
    if "ambito" in n:
        return "ambito"
    if "provincia" in n:
        return "prov"
    if "provenienza" in n or "italianostraniero" in n:
        return "provM"
    if n == "arriviitaliani":
        return "arr_ita"
    if n == "arrivistranieri":
        return "arr_str"
    if n == "presenzeitaliane":
        return "pres_ita"
    if n == "presenzestraniere":
        return "pres_str"
    if n == "arrivi":
        return "arrivi"
    if n == "presenze":
        return "presenze"
    return n


def _tosc_int(s: str) -> int:
    s = (s or "").strip().replace(" ", "")
    return int(s) if s.lstrip("-").isdigit() else 0


def _tosc_movimento_urls(timeout: int = 60) -> dict:
    """Enumera i dataset annuali via CKAN → {anno: url_csv_movimento}."""
    import urllib.parse
    url = TOSC_CKAN + "?" + urllib.parse.urlencode({"q": TOSC_QUERY, "rows": 50})
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    data = json.loads(urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8"))
    out: dict[int, str] = {}
    for pkg in data.get("result", {}).get("results", []):
        title = pkg.get("title", "")
        if "movimento" not in title.lower():
            continue
        m = re.search(r"(20\d{2})", title)
        if not m:
            continue
        anno = int(m.group(1))
        for r in pkg.get("resources", []):
            if (r.get("format") or "").lower() != "csv":
                continue
            tag = ((r.get("name") or "") + " " + (r.get("url") or "")).lower()
            if "movimento" in tag and "consistenza" not in tag:
                out[anno] = r.get("url", "")
                break
    return dict(sorted(out.items()))


def _tosc_parse(url: str, timeout: int = 90) -> list:
    """Scarica e normalizza un singolo file annuale a record per (anno, comune)."""
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    raw = urllib.request.urlopen(req, timeout=timeout).read()
    txt = raw.decode("cp1252", "replace")
    lines = txt.splitlines()
    if not lines:
        return []
    delim = max([";", "\t", ","], key=lines[0].count)
    rows = list(csv.reader(io.StringIO(txt), delimiter=delim))
    if len(rows) < 2:
        return []
    hdr = [_tosc_canonkey(h) for h in rows[0]]
    recs = [dict(zip(hdr, r)) for r in rows[1:] if any(c.strip() for c in r)]
    wide = "arr_ita" in hdr
    agg: dict = {}
    for r in recs:
        key = (r.get("anno", ""), r.get("cod_istat", ""), r.get("comune", ""))
        d = agg.setdefault(key, {
            "anno": (r.get("anno", "") or "").strip(),
            "sigla_provincia": (r.get("prov", "") or "").strip(),
            "comune": (r.get("comune", "") or "").strip(),
            "cod_istat": (r.get("cod_istat", "") or "").strip(),
            "ambito": (r.get("ambito", "") or "").strip(),
            "arrivi_italiani": 0, "arrivi_stranieri": 0,
            "presenze_italiane": 0, "presenze_straniere": 0})
        if wide:
            d["arrivi_italiani"] += _tosc_int(r.get("arr_ita"))
            d["arrivi_stranieri"] += _tosc_int(r.get("arr_str"))
            d["presenze_italiane"] += _tosc_int(r.get("pres_ita"))
            d["presenze_straniere"] += _tosc_int(r.get("pres_str"))
        else:
            pv = _tosc_norm(r.get("provM"))
            a, p = _tosc_int(r.get("arrivi")), _tosc_int(r.get("presenze"))
            if pv in _TOSC_ITA:
                d["arrivi_italiani"] += a
                d["presenze_italiane"] += p
            elif pv in _TOSC_STR:
                d["arrivi_stranieri"] += a
                d["presenze_straniere"] += p
    return list(agg.values())


def fetch_toscana_movimento(cache_dir: str = ".cache", timeout: int = 120,
                            refresh: bool = False) -> pd.DataFrame:
    """Movimento clienti ANNUALE per COMUNE toscano (arrivi/presenze italiani+stranieri),
    2018-2025. Normalizza i formati annuali eterogenei a TOSC_FIELDS. Cache CSV."""
    os.makedirs(cache_dir, exist_ok=True)
    cache_path = os.path.join(cache_dir, TOSC_CACHE)
    if os.path.exists(cache_path) and not refresh:
        return pd.read_csv(cache_path)
    urls = _tosc_movimento_urls(timeout=min(timeout, 60))
    recs: list = []
    for _anno, url in urls.items():
        try:
            recs.extend(_tosc_parse(url, timeout))
        except Exception:  # noqa: BLE001
            continue
    df = pd.DataFrame(recs, columns=TOSC_FIELDS)
    numcols = ["anno"] + [c for c in TOSC_FIELDS if c.startswith(("arrivi", "presenze"))]
    for c in numcols:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["anno"]).copy()
    df["anno"] = df["anno"].astype(int)
    df = df.sort_values(["anno", "sigla_provincia", "comune"]).reset_index(drop=True)
    df.to_csv(cache_path, index=False)
    return df


def fetch_toscana_latest_year(timeout: int = 60) -> int | None:
    """Anno più recente disponibile (dalla lista CKAN dei dataset annuali)."""
    try:
        urls = _tosc_movimento_urls(timeout)
        return max(urls) if urls else None
    except Exception:  # noqa: BLE001
        return None


# --------------------------------------------------------------------------
# WIKIPEDIA — pageviews mensili per articolo (secondo segnale anticipatore, per lingua).
# Wikimedia REST: filtro agent='user' (esclude bot) e titolo articolo per lingua
# (la regione in tedesco/olandese è 'Abruzzen'). UA obbligatorio.
# --------------------------------------------------------------------------
WIKI_PROJECT = {"de": "de.wikipedia", "en": "en.wikipedia", "nl": "nl.wikipedia", "it": "it.wikipedia"}
WIKI_ARTICLE = {"de": "Abruzzen", "en": "Abruzzo", "nl": "Abruzzen", "it": "Abruzzo"}
_WIKI_UA = {"User-Agent": "TDH-Engine/1.0 (Regione Abruzzo prototype; contact marco.dicenso@gmail.com)"}


def fetch_wikipedia_monthly(lang: str, article: str | None = None, start: str = "20190101",
                            end: str | None = None, cache_dir: str = ".cache",
                            cache_name: str | None = None, refresh: bool = False) -> pd.DataFrame:
    """Pageviews mensili (agent=user) di un articolo Wikipedia per lingua.

    lang: de | en | nl | it. article: titolo (default = articolo Abruzzo).
    cache_name: nome file cache (default wiki_<lang>.csv). Ritorna date, views.
    """
    os.makedirs(cache_dir, exist_ok=True)
    cache_path = os.path.join(cache_dir, cache_name or f"wiki_{lang}.csv")
    if os.path.exists(cache_path) and not refresh:
        return pd.read_csv(cache_path, parse_dates=["date"])
    proj, art = WIKI_PROJECT[lang], (article or WIKI_ARTICLE[lang])
    end = end or pd.Timestamp.today().strftime("%Y%m01")
    url = (f"https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/{proj}"
           f"/all-access/user/{art}/monthly/{start}/{end}")
    raw = urllib.request.urlopen(urllib.request.Request(url, headers=_WIKI_UA), timeout=40).read()
    items = json.loads(raw)["items"]
    rows = [(pd.Timestamp(it["timestamp"][:6] + "01"), int(it["views"])) for it in items]
    df = pd.DataFrame(rows, columns=["date", "views"])
    df.to_csv(cache_path, index=False)
    return df
