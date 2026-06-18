"""
Adattatori per le FONTI CANDIDATE (in valutazione): ogni fonte ha
  probe()  -> {ok, msg, preview}   verifica di disponibilità (leggera)
  load()   -> {ok, msg, path, rows} scarica in .cache/ dopo il nulla osta
Usa urllib (a prova di proxy Indra). Nessun caricamento avviene senza approvazione.
"""
from __future__ import annotations

import json
import os
import re
import urllib.request

import pandas as pd

UA = {"User-Agent": "TDH-Engine/1.0 (Regione Abruzzo prototype)"}
PESCARA = (42.46, 14.21)
ISTAT_BASE = "https://esploradati.istat.it/SDMXWS/rest"


def _get_json(url: str, timeout: int = 40):
    return json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout).read())


# ── Open-Meteo (meteo storico Pescara) ──────────────────────────────────────
def probe_open_meteo() -> dict:
    try:
        d = _get_json(f"https://archive-api.open-meteo.com/v1/archive?latitude={PESCARA[0]}"
                      f"&longitude={PESCARA[1]}&start_date=2024-06-01&end_date=2024-06-15"
                      f"&daily=temperature_2m_mean&timezone=Europe%2FRome", 30)
        t = d["daily"]["temperature_2m_mean"]
        return {"ok": True, "msg": f"API raggiungibile · {len(t)} giorni di prova",
                "preview": f"giugno 2024: temp media {round(sum(t) / len(t), 1)}°C"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "msg": f"non raggiungibile: {type(e).__name__}", "preview": ""}


def load_open_meteo(start: str = "2019-01-01", end: str | None = None) -> dict:
    end = end or pd.Timestamp.today().strftime("%Y-%m-%d")
    d = _get_json(f"https://archive-api.open-meteo.com/v1/archive?latitude={PESCARA[0]}"
                  f"&longitude={PESCARA[1]}&start_date={start}&end_date={end}"
                  f"&daily=temperature_2m_mean,precipitation_sum&timezone=Europe%2FRome", 90)["daily"]
    df = pd.DataFrame({"date": pd.to_datetime(d["time"]), "temp": d["temperature_2m_mean"],
                       "precip": d["precipitation_sum"]})
    m = df.set_index("date").resample("MS").agg({"temp": "mean", "precip": "sum"}).round(1).reset_index()
    os.makedirs(".cache", exist_ok=True)
    p = ".cache/openmeteo_pescara.csv"
    m.to_csv(p, index=False)
    return {"ok": True, "msg": f"{len(m)} mesi (temp media, precipitazioni)", "path": p, "rows": len(m)}


# ── Nager.Date (festività per paese) ────────────────────────────────────────
HOL_COUNTRIES = ["DE", "AT", "GB", "US", "NL", "CH"]


def probe_holidays() -> dict:
    try:
        d = _get_json("https://date.nager.at/api/v3/PublicHolidays/2025/DE", 30)
        return {"ok": True, "msg": f"API raggiungibile · {len(d)} festività DE 2025",
                "preview": ", ".join(h["localName"] for h in d[:4]) + "…"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "msg": f"non raggiungibile: {type(e).__name__}", "preview": ""}


def load_holidays(years=(2024, 2025, 2026)) -> dict:
    rows = []
    for y in years:
        for c in HOL_COUNTRIES:
            try:
                for h in _get_json(f"https://date.nager.at/api/v3/PublicHolidays/{y}/{c}", 30):
                    rows.append({"code": c, "date": h["date"], "name": h["localName"]})
            except Exception:  # noqa: BLE001
                continue
    df = pd.DataFrame(rows)
    os.makedirs(".cache", exist_ok=True)
    p = ".cache/holidays.csv"
    df.to_csv(p, index=False)
    return {"ok": True, "msg": f"{len(df)} festività · {len(years)} anni × {len(HOL_COUNTRIES)} paesi",
            "path": p, "rows": len(df)}


# ── ISTAT viaggi/notti dei residenti per destinazione (DCCV_TURNOT) ──────────
_DF_VIAGGI = "68_381_DF_DCCV_TURNOT_2"
_DIMS_VIAGGI = ["FREQ", "REF_AREA", "DATA_TYPE", "DESTINATION", "TYPE_TRIP", "TYPE_ACCOMMODATION",
                "SEX", "AGE", "LABPROF_STATUS_C"]


def probe_istat_viaggi() -> dict:
    try:
        key = ".".join(["A", "ITF1"] + [""] * 7)
        url = f"{ISTAT_BASE}/data/{_DF_VIAGGI}/{key}?detail=serieskeysonly"
        t = urllib.request.urlopen(urllib.request.Request(
            url, headers={"Accept": "application/vnd.sdmx.structurespecificdata+xml;version=2.1"}),
            timeout=70).read().decode("utf-8", "ignore")
        n = len(re.findall(r"<Series ", t))
        return {"ok": n > 0, "msg": f"ISTAT raggiungibile · {n} serie (residenti Abruzzo)" if n
                else "ISTAT raggiungibile ma nessuna serie",
                "preview": "viaggi/notti dei residenti abruzzesi per destinazione (IT/estero)"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "msg": f"ISTAT non raggiungibile ora ({type(e).__name__}) — riprovare", "preview": ""}


def load_istat_viaggi() -> dict:
    key = ".".join(["A", "ITF1"] + [""] * 7)
    t = urllib.request.urlopen(urllib.request.Request(
        f"{ISTAT_BASE}/data/{_DF_VIAGGI}/{key}?detail=serieskeysonly",
        headers={"Accept": "application/vnd.sdmx.structurespecificdata+xml;version=2.1"}),
        timeout=150).read().decode("utf-8", "ignore")
    series = []
    for m in re.finditer(r"<(?:\w+:)?Series ([^>]*?)/?>", t):
        d = {k: v for k, v in re.findall(r'(\w+)="([^"]*)"', m.group(1))}
        if "DATA_TYPE" in d:
            series.append(d)
    if not series:
        raise RuntimeError("nessuna serie disponibile")
    totals = {"TOTAL", "T", "9", "TOT", "WORLD", "ALL"}
    chosen = max(series, key=lambda d: sum(1 for v in d.values() if v in totals))
    key2 = ".".join(chosen.get(dim, "") for dim in _DIMS_VIAGGI)
    raw = urllib.request.urlopen(urllib.request.Request(
        f"{ISTAT_BASE}/data/{_DF_VIAGGI}/{key2}?detail=full",
        headers={"Accept": "application/vnd.sdmx.data+json;version=1.0.0-wd"}),
        timeout=150).read().decode("utf-8", "ignore")
    dd = json.loads(raw)["data"]
    periods = [v["id"] for v in dd["structure"]["dimensions"]["observation"][0]["values"]]
    ser = dd["dataSets"][0]["series"]
    obs = ser[next(iter(ser))]["observations"]
    rows = []
    for i, o in obs.items():
        if o and o[0] is not None:
            rows.append((periods[int(i)], float(o[0])))
    df = pd.DataFrame(sorted(rows), columns=["periodo", "valore"])
    os.makedirs(".cache", exist_ok=True)
    p = ".cache/istat_viaggi_abruzzo.csv"
    df.to_csv(p, index=False)
    return {"ok": True, "msg": f"{len(df)} periodi (serie rappresentativa dei residenti, da rifinire)",
            "path": p, "rows": len(df)}


# ── Caricatore CSV generico (open data dati.gov.it / portali regionali) ──────
# Riusabile e multi-regione: scarica un CSV pubblico in .cache e ne conta righe/colonne.
def _csv_probe(url: str, sep: str = ";") -> dict:
    try:
        raw = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40).read(3000)
        lines = [l for l in raw.decode("utf-8", "ignore").splitlines() if l.strip()]
        cols = lines[0].split(sep) if lines else []
        return {"ok": len(cols) > 1, "msg": f"raggiungibile · {len(cols)} colonne",
                "preview": " · ".join(c.strip() for c in cols[:6])[:130]}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "msg": f"non raggiungibile: {type(e).__name__}", "preview": ""}


def _csv_load(url: str, cache_name: str, sep: str = ";") -> dict:
    raw = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120).read()
    os.makedirs(".cache", exist_ok=True)
    p = os.path.join(".cache", cache_name)
    with open(p, "wb") as f:
        f.write(raw)
    df = pd.read_csv(p, sep=sep, engine="python", on_bad_lines="skip")
    return {"ok": True, "msg": f"{len(df)} righe · {len(df.columns)} colonne (scaricato in cache)",
            "path": p, "rows": len(df)}


# ── Dataset open data nazionali (validi per TUTTE le regioni, filtrabili per territorio) ──
URL_MUSEI = ("https://dati.comune.milano.it/dataset/0e119e7d-ef26-4094-a45d-6d01f694e6ab/"
             "resource/8f361917-c6da-40fb-8902-bb7eb6049ab7/download/"
             "ds513_musei_statali_visitatori_introiti.csv")
URL_AEROPORTI = ("https://bdt.autorita-trasporti.it/wp-content/uploads/dcat/"
                 "D16-Mappa-degli-aeroporti-aperti-al-traffico-commerciale-2022.csv")
URL_FERROVIA = ("https://bdt.autorita-trasporti.it/wp-content/uploads/dcat/"
                "D10-Andamento-traffico-passeggeri-pax-2022.csv")


def probe_musei():
    return _csv_probe(URL_MUSEI)


def load_musei():
    return _csv_load(URL_MUSEI, "musei_statali_visitatori.csv")


def probe_aeroporti():
    return _csv_probe(URL_AEROPORTI)


def load_aeroporti():
    return _csv_load(URL_AEROPORTI, "aeroporti_italia.csv")


def probe_ferrovia():
    return _csv_probe(URL_FERROVIA)


def load_ferrovia():
    return _csv_load(URL_FERROVIA, "ferrovia_passeggeri_nazionale.csv")


# Registro id -> funzione di load: usato dall'auto-aggiornamento (update_check) per
# rinfrescare le fonti candidate APPROVATE, senza dipendere da Streamlit/tdhlib.
CANDIDATE_LOADERS = {
    "openmeteo": load_open_meteo,
    "holidays": load_holidays,
    "istat_viaggi": load_istat_viaggi,
    "musei": load_musei,
    "aeroporti": load_aeroporti,
    "ferrovia": load_ferrovia,
}
