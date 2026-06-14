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

import io
import json
import os
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
    import truststore
    truststore.inject_into_ssl()  # CA aziendale Indra anche per requests (idempotente)
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
