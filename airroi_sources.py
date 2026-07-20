"""Reader AirROI (affitti brevi, metriche di mercato REALI) — SOLO USO INTERNO.

⚠️  LICENZA (AirROI ToS, verificati 20-07-2026 su airroi.com/tos):
    - §5.2(a) licenza Commercial = uso INTERNO (analisi/ricerca di mercato).
    - §5.4 vietato distribuire/pubblicare/mostrare i dati "in whole or substantial
      part, in raw or minimally processed form" a terzi.
    - §10/§32 cache API MAX 30 giorni + cancellazione a fine accesso/su richiesta.
    - Per VENDERE un portale che mostra questi dati a clienti serve un
      "Redistribution Addendum" scritto con AirROI (§5.9). Qui NON lo facciamo:
      questo modulo è per uso interno.
    Conseguenze tecniche rispettate qui:
    - la chiave sta in una VARIABILE D'AMBIENTE (`TDH_AIRROI_KEY`), mai nel codice;
    - la cache va in `airroi_cache/` che è GITIGNORATA (dati NON committati);
    - la cache non viene MAI servita se più vecchia di 30 giorni (hard cap ToS).

Senza chiave il modulo NON fa chiamate e degrada in modo pulito (is_configured()
== False, fetch_airroi_markets() -> DataFrame vuoto), così l'app resta su dati
sintetici / Inside Airbnb.

Stile: urllib (stdlib) come real_sources.py; truststore iniettato lazy per il
proxy aziendale Indra.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

import pandas as pd

API_BASE = "https://api.airroi.com"
_ROOT = os.path.dirname(os.path.abspath(__file__))
_CACHE_DIR = os.path.join(_ROOT, "airroi_cache")          # GITIGNORATA
_CACHE_FILE = os.path.join(_CACHE_DIR, "airroi_markets.json")
_MAX_AGE_DAYS_HARD = 30                                    # cap di licenza: non servire oltre

# Mercati italiani coperti da AirROI, mappati alle regioni TDH (NUTS2).
# AirROI usa regione/città in INGLESE. Lista di partenza estendibile: passare `markets=`
# a fetch_airroi_markets() per coprirne altri (uno snapshot ~100 mercati ≈ $5-10).
AIRROI_MARKETS = [
    {"tdh": "ITE1", "country": "italy", "region": "Tuscany",  "locality": "Florence"},
    {"tdh": "ITC4", "country": "italy", "region": "Lombardy", "locality": "Milan"},
    {"tdh": "ITF1", "country": "italy", "region": "Abruzzo",  "locality": "Pescara"},
    {"tdh": "ITG2", "country": "italy", "region": "Sardinia", "locality": "Cagliari"},
    {"tdh": "ITI4", "country": "italy", "region": "Lazio",    "locality": "Rome"},
    {"tdh": "ITF3", "country": "italy", "region": "Campania", "locality": "Naples"},
    {"tdh": "ITH3", "country": "italy", "region": "Veneto",   "locality": "Venice"},
]


def _api_key() -> str | None:
    k = os.environ.get("TDH_AIRROI_KEY", "").strip()
    return k or None


def is_configured() -> bool:
    """True se è presente una chiave API (env `TDH_AIRROI_KEY`)."""
    return _api_key() is not None


def _inject_truststore() -> None:
    """CA aziendale Indra anche per urllib (idempotente). Silenzioso se assente."""
    try:
        import truststore
        truststore.inject_into_ssl()
    except Exception:  # noqa: BLE001
        pass


def _post(path: str, payload: dict, timeout: int = 30) -> dict:
    """POST JSON autenticato all'API AirROI. Alza urllib.error.HTTPError sugli errori."""
    key = _api_key()
    if not key:
        raise RuntimeError("TDH_AIRROI_KEY non impostata: nessuna chiamata AirROI.")
    _inject_truststore()
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{API_BASE}{path}", data=data, method="POST",
        headers={"X-API-KEY": key, "Content-Type": "application/json",
                 "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "ignore"))


def fetch_market_summary(country: str, region: str, locality: str,
                         currency: str = "eur", num_months: int = 12,
                         timeout: int = 30) -> dict:
    """Scheda sintetica di un mercato: occupancy, ADR, RevPAR, revenue, active
    listings, ALOS, lead time (+ breakdown mensile). Torna il JSON GREZZO di AirROI
    (parsing dei singoli campi rimandato: lo rifiniamo sul primo response reale)."""
    payload = {"market": {"country": country, "region": region, "locality": locality},
               "currency": currency, "num_months": num_months}
    return _post("/markets/summary", payload, timeout=timeout)


# ── estrazione difensiva dei campi dal JSON grezzo (chiavi ancora da confermare) ──
_FIELD_ALIASES = {
    "occupancy":       ("occupancy", "avg_occupancy", "occupancy_rate", "occ"),
    "adr":             ("adr", "avg_rate", "average_daily_rate", "avg_adr"),
    "revpar":          ("revpar", "rev_par"),
    "revenue":         ("revenue", "avg_revenue", "annual_revenue", "revenue_per_listing"),
    "active_listings": ("active_listings", "listings", "num_listings", "active_listing_count"),
    "alos":            ("avg_length_of_stay", "alos", "length_of_stay"),
    "lead_time":       ("booking_lead_time", "lead_time"),
}


def _pick(d: dict, aliases: tuple):
    """Primo alias presente (anche annidato un livello sotto 'summary'/'metrics')."""
    for scope in (d, d.get("summary") or {}, d.get("metrics") or {}, d.get("data") or {}):
        if isinstance(scope, dict):
            for a in aliases:
                if a in scope and scope[a] is not None:
                    return scope[a]
    return None


def _normalize(raw: dict) -> dict:
    """Da JSON grezzo a metriche piatte. Difensivo: None sui campi non trovati."""
    out = {k: _pick(raw, al) for k, al in _FIELD_ALIASES.items()}
    return out


def _cache_age_days() -> float | None:
    if not os.path.exists(_CACHE_FILE):
        return None
    try:
        obj = json.load(open(_CACHE_FILE, encoding="utf-8"))
        return (time.time() - float(obj.get("fetched_at", 0))) / 86400.0
    except Exception:  # noqa: BLE001
        return None


def cache_status() -> dict:
    """Stato della cache AirROI per la UI/diagnostica."""
    age = _cache_age_days()
    return {"configured": is_configured(), "has_cache": os.path.exists(_CACHE_FILE),
            "age_days": (round(age, 1) if age is not None else None),
            "expired": (age is not None and age > _MAX_AGE_DAYS_HARD)}


def fetch_airroi_markets(markets: list | None = None, currency: str = "eur",
                         num_months: int = 12, refresh: bool = False,
                         max_age_days: int = 7) -> pd.DataFrame:
    """DataFrame delle metriche di mercato AirROI per i mercati richiesti.

    - Senza chiave → DataFrame vuoto (nessuna chiamata).
    - Usa la cache locale se fresca (< max_age_days) e non `refresh`; MAI se > 30gg (ToS).
    - Salva JSON grezzo + metriche normalizzate in `airroi_cache/` (gitignorata)."""
    cols = ["tdh", "country", "region", "locality", "occupancy", "adr", "revpar",
            "revenue", "active_listings", "alos", "lead_time", "currency", "num_months"]
    if not is_configured():
        return pd.DataFrame(columns=cols)

    markets = markets or AIRROI_MARKETS

    # cache valida?
    age = _cache_age_days()
    if (not refresh and age is not None and age <= min(max_age_days, _MAX_AGE_DAYS_HARD)):
        try:
            obj = json.load(open(_CACHE_FILE, encoding="utf-8"))
            df = pd.DataFrame(obj.get("rows", []))
            if not df.empty:
                return df.reindex(columns=cols)
        except Exception:  # noqa: BLE001
            pass

    rows, raws = [], []
    for m in markets:
        try:
            raw = fetch_market_summary(m["country"], m["region"], m["locality"],
                                       currency=currency, num_months=num_months)
        except urllib.error.HTTPError as e:
            raws.append({"market": m, "error": f"HTTP {e.code}"})
            continue
        except Exception as e:  # noqa: BLE001
            raws.append({"market": m, "error": f"{type(e).__name__}: {e}"})
            continue
        norm = _normalize(raw)
        rows.append({"tdh": m["tdh"], "country": m["country"], "region": m["region"],
                     "locality": m["locality"], "currency": currency,
                     "num_months": num_months, **norm})
        raws.append({"market": m, "raw": raw})

    os.makedirs(_CACHE_DIR, exist_ok=True)
    json.dump({"fetched_at": time.time(), "rows": rows, "raws": raws},
              open(_CACHE_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return pd.DataFrame(rows).reindex(columns=cols)


# ── self-check / probe: `python airroi_sources.py [--probe "Rome,Lazio"]` ──
if __name__ == "__main__":
    import sys
    print("AirROI configurato:", is_configured(), "· cache:", cache_status())
    if not is_configured():
        print("Imposta TDH_AIRROI_KEY per fare una chiamata di prova.")
        sys.exit(0)
    if "--probe" in sys.argv:
        arg = sys.argv[sys.argv.index("--probe") + 1]
        loc, reg = [s.strip() for s in arg.split(",")]
        print(f"\nProbe {loc}, {reg} (JSON grezzo — serve a fissare i nomi dei campi):")
        raw = fetch_market_summary("italy", reg, loc)
        print(json.dumps(raw, ensure_ascii=False, indent=2)[:3000])
        print("\nNormalizzato:", _normalize(raw))
    else:
        df = fetch_airroi_markets(refresh=True)
        print(f"\n{len(df)} mercati:")
        print(df.to_string(index=False))
