"""
Variabili ECONOMICHE dei mercati d'origine (feature esogene per il motore).

Fonte: Eurostat (JSON-stat, urllib a prova di proxy). Mensili dove possibile.
  • fetch_consumer_confidence(geo) -> fiducia dei consumatori (saldo, mensile)  [ei_bsco_m]

Copertura geo Eurostat: DE, AT, NL, UK (GB). CH e US non sono in ei_bsco_m
(servirebbe OCSE): per quei mercati la feature resterà mancante (gestibile).
"""
from __future__ import annotations

import json
import os
import urllib.request

import pandas as pd

EUROSTAT = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"
_UA = {"User-Agent": "TDH-Engine/1.0 (Regione Abruzzo prototype)"}

# mercato del motore -> codice geo Eurostat (UK = Regno Unito)
MARKET_GEO = {"DE": "DE", "AT": "AT", "NL": "NL", "GB": "UK"}


def _jsonstat_series(url: str, value_name: str, timeout: int = 40) -> pd.DataFrame:
    """Estrae una serie temporale mensile da una risposta JSON-stat Eurostat a una dimensione tempo."""
    d = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=_UA), timeout=timeout).read())
    idx = d["dimension"]["time"]["category"]["index"]      # {"2008-01": 0, ...}
    inv = {v: k for k, v in idx.items()}
    rows = [(pd.Timestamp(inv[int(i)] + "-01"), float(v)) for i, v in d["value"].items()]
    return pd.DataFrame(sorted(rows), columns=["date", value_name])


def fetch_consumer_confidence(geo: str, start: str = "2008-01", cache_dir: str = ".cache",
                              refresh: bool = False) -> pd.DataFrame:
    """Fiducia dei consumatori (indicatore BS-CSMCI, destag., saldo) mensile per paese.

    Ritorna DataFrame con colonne: date, confidence. Con cache su disco.
    """
    os.makedirs(cache_dir, exist_ok=True)
    cache_path = os.path.join(cache_dir, f"econ_confidence_{geo}.csv")
    if os.path.exists(cache_path) and not refresh:
        return pd.read_csv(cache_path, parse_dates=["date"])
    url = (f"{EUROSTAT}/ei_bsco_m?format=JSON&lang=EN&indic=BS-CSMCI&s_adj=SA"
           f"&unit=BAL&geo={geo}&sinceTimePeriod={start}")
    df = _jsonstat_series(url, "confidence")
    df.to_csv(cache_path, index=False)
    return df


def fetch_pescara_flights_monthly(start: str = "2008-01", cache_dir: str = ".cache",
                                  refresh: bool = False) -> pd.DataFrame:
    """Passeggeri mensili da/per l'aeroporto di Pescara (ICAO LIBP), Eurostat avia_par_it.

    Somma tutte le rotte che coinvolgono Pescara (entrambe le direzioni). Ritorna
    DataFrame con colonne: date, pax (totale mese). Cache su disco.
    """
    os.makedirs(cache_dir, exist_ok=True)
    cache_path = os.path.join(cache_dir, "econ_flights_pescara_monthly.csv")
    if os.path.exists(cache_path) and not refresh:
        return pd.read_csv(cache_path, parse_dates=["date"])
    base = f"{EUROSTAT}/avia_par_it"
    # 1) scopro le coppie aeroportuali che coinvolgono LIBP (da un mese recente)
    probe = json.loads(urllib.request.urlopen(urllib.request.Request(
        f"{base}?format=JSON&lang=EN&freq=M&tra_meas=PAS_CRD&unit=PAS&time=2024-07",
        headers=_UA), timeout=60).read())
    libp_pairs = [k for k in probe["dimension"]["airp_pr"]["category"]["index"] if "LIBP" in k]
    # 2) interrogo solo quelle coppie su tutto l'arco temporale
    qp = "".join(f"&airp_pr={p}" for p in libp_pairs)
    url = f"{base}?format=JSON&lang=EN&freq=M&tra_meas=PAS_CRD&unit=PAS&sinceTimePeriod={start}{qp}"
    d = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=_UA), timeout=90).read())
    t_idx = {v: k for k, v in d["dimension"]["time"]["category"]["index"].items()}
    p_idx = {v: k for k, v in d["dimension"]["airp_pr"]["category"]["index"].items()}
    n_time = len(t_idx)
    # valore lineare: indice = pair_pos * n_time + time_pos (ordine dimensioni: airp_pr, time)
    tot: dict[str, float] = {}
    for flat, val in d["value"].items():
        i = int(flat)
        tpos = i % n_time
        period = t_idx.get(tpos)
        if period:
            tot[period] = tot.get(period, 0.0) + float(val)
    df = pd.DataFrame(sorted((pd.Timestamp(p + "-01"), v) for p, v in tot.items()),
                      columns=["date", "pax"])
    df.to_csv(cache_path, index=False)
    return df


def build_confidence_panel(start: str = "2008-01", refresh: bool = False) -> pd.DataFrame:
    """Pannello LONG della fiducia per i mercati coperti: date, mercato, confidence."""
    blocks = []
    for mk, geo in MARKET_GEO.items():
        try:
            d = fetch_consumer_confidence(geo, start=start, refresh=refresh).copy()
            d["mercato"] = mk
            blocks.append(d[["date", "mercato", "confidence"]])
        except Exception as e:  # noqa: BLE001
            print(f"  fiducia {mk} ({geo}) non disponibile: {type(e).__name__}")
    return pd.concat(blocks, ignore_index=True) if blocks else pd.DataFrame()


if __name__ == "__main__":
    try:
        import truststore
        truststore.inject_into_ssl()
    except Exception:  # noqa: BLE001
        pass
    p = build_confidence_panel()
    print(f"Fiducia consumatori: {len(p)} righe, mercati {sorted(p['mercato'].unique())}")
    for mk in sorted(p["mercato"].unique()):
        s = p[p["mercato"] == mk]
        print(f"  {mk}: {len(s)} mesi {s['date'].min():%Y-%m}->{s['date'].max():%Y-%m} "
              f"| ultimo saldo {s['confidence'].iloc[-1]:+.1f}")
