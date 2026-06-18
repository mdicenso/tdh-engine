"""
Pannello delle presenze ISTAT per la modellazione (multilivello / Random Forest).

Struttura LONG: una riga per (mese × provincia × origine), dal 2008.
  date · provincia · origine(estero/italiani) · presenze
≈ 4 province × 2 origini × ~200 mesi ≈ 1.600 righe — abbastanza per un modello a
pannello, molto più dei 72 mesi della singola serie aggregata.

Espandibile in seguito con la dimensione struttura (hotel/extra-alberghiero).
"""
from __future__ import annotations

import os
import time

import pandas as pd

from tourism_wedge import real_sources as RS

PANEL_PATH = ".cache/panel_presenze.csv"
PROVINCE = {"ITF11": "L'Aquila", "ITF12": "Teramo", "ITF13": "Pescara", "ITF14": "Chieti"}
ORIGINE = {"WRL_X_ITA": "estero", "IT": "italiani"}


def build_panel(start: str = "2008-01", refresh: bool = False, timeout: int = 180) -> pd.DataFrame:
    """Scarica/assembla il pannello LONG e lo salva in cache. refresh=True riscarica da ISTAT."""
    if os.path.exists(PANEL_PATH) and not refresh:
        return pd.read_csv(PANEL_PATH, parse_dates=["date"])
    blocks = []
    for area, prov in PROVINCE.items():
        for code, orig in ORIGINE.items():
            df = None
            for attempt in range(4):  # ISTAT è instabile: 404/timeout transitori -> ritento
                try:
                    df = RS.fetch_istat_presences(area=area, data_type="NI", accom="ALL",
                                                  country=code, start=start, timeout=timeout,
                                                  refresh=refresh)
                    break
                except Exception as e:  # noqa: BLE001
                    print(f"    {prov}/{orig} tentativo {attempt + 1} fallito ({type(e).__name__}), ritento…")
                    time.sleep(4)
            if df is None:
                raise RuntimeError(f"ISTAT: {prov}/{orig} non recuperabile dopo 4 tentativi")
            d = df.rename(columns={"presences": "presenze"}).copy()
            d["provincia"], d["origine"] = prov, orig
            blocks.append(d[["date", "provincia", "origine", "presenze"]])
            print(f"    ok {prov}/{orig}: {len(d)} mesi")
    panel = (pd.concat(blocks, ignore_index=True)
             .sort_values(["provincia", "origine", "date"]).reset_index(drop=True))
    os.makedirs(".cache", exist_ok=True)
    panel.to_csv(PANEL_PATH, index=False)
    return panel


def load_panel() -> pd.DataFrame | None:
    if not os.path.exists(PANEL_PATH):
        return None
    return pd.read_csv(PANEL_PATH, parse_dates=["date"])


if __name__ == "__main__":
    import sys
    try:
        import truststore
        truststore.inject_into_ssl()
    except Exception:  # noqa: BLE001
        pass
    print("Costruisco il pannello presenze (ISTAT, dal 2008)…")
    p = build_panel(refresh="--refresh" in sys.argv)
    print(f"  righe: {len(p)} | celle: {p.groupby(['provincia','origine']).ngroups}")
    print(f"  periodo: {p['date'].min():%Y-%m} -> {p['date'].max():%Y-%m}")
    print(p.groupby(["provincia", "origine"])["presenze"].agg(["count", "mean"]).round(0))
