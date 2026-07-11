"""
Controllo aggiornamenti delle fonti dati del TDH.

Due livelli:
  • status_all()  -> istantaneo, SENZA rete: per ogni fonte legge dalla cache
    l'ultimo periodo presente e calcola un giudizio di freschezza (verde/giallo/
    rosso) confrontando l'età del dato con la cadenza tipica della fonte.
  • live_check()  -> CON rete: riscarica in una cartella temporanea le fonti
    "refreshabili" (ISTAT, Trends) e confronta l'ultimo periodo con la cache,
    dicendo se c'è davvero un dato nuovo.
  • apply_update(key) -> dà il nulla osta: riscarica nella cache reale.

Riusabile sia dall'app Streamlit sia da uno schedulatore (vedi __main__).
"""
from __future__ import annotations

import glob
import json
import os
import tempfile

import pandas as pd

from tourism_wedge import real_sources as RS
from tourism_wedge import candidate_sources as CS

CACHE = ".cache"
STATE_PATH = "data/update_state.json"
STATE_CAND = "data/candidates_state.json"  # fonti candidate approvate (da tenere aggiornate)

# soglie: oltre questo "ritardo" dell'ultimo dato rispetto a oggi, vale la pena
# controllare se la fonte ha pubblicato qualcosa di nuovo (giudizio euristico).
_MAX_GAP_DAYS = {"mensile": 130, "trimestrale": 210, "annuale": 480}


# ── lettura ultimo periodo da un file di cache ──────────────────────────────
def _last_period(path: str):
    """(ultimo_timestamp, n_righe) leggendo una colonna 'date' o 'anno'. None se assente."""
    if not path or not os.path.exists(path):
        return None
    try:
        d = pd.read_csv(path)
    except Exception:  # noqa: BLE001
        return None
    if "date" in d.columns:
        t = pd.to_datetime(d["date"], errors="coerce").dropna()
        return (t.max(), len(d)) if len(t) else (None, len(d))
    if "anno" in d.columns:
        y = pd.to_numeric(d["anno"], errors="coerce").dropna()
        return (pd.Timestamp(f"{int(y.max())}-12-31"), len(d)) if len(y) else (None, len(d))
    if "TIME_PERIOD" in d.columns:  # cache "lunga" ISTAT _9 (anno per riga)
        y = pd.to_numeric(d["TIME_PERIOD"], errors="coerce").dropna()
        return (pd.Timestamp(f"{int(y.max())}-12-31"), len(d)) if len(y) else (None, len(d))
    return (None, len(d))


def _first_existing(paths: list[str]) -> str | None:
    for p in paths:
        if os.path.exists(p):
            return p
    return None


# ── registro delle fonti ────────────────────────────────────────────────────
# kind: come si legge l'ultimo periodo. live: funzione di confronto/aggiornamento
# disponibile in questa fase (Fase 1). 'manual' = refresh non ancora implementato.
SOURCES = [
    {"key": "istat_presenze", "label": "Presenze straniere (ISTAT)", "cadence": "mensile",
     "paths": [f"{CACHE}/istat_presenze_straniere_abruzzo.csv"], "live": "istat_presenze"},
    {"key": "istat_province", "label": "Presenze province (ISTAT)", "cadence": "mensile",
     "paths": sorted(glob.glob(f"{CACHE}/istat_ITF1?_*.csv")) or [f"{CACHE}/istat_ITF13_NI_ALL_WORLD.csv"],
     "live": "istat_glob"},
    {"key": "trends", "label": "Google Trends (per mercato)", "cadence": "mensile",
     "paths": sorted(glob.glob(f"{CACHE}/trends_abruzzo_*.csv")) or [f"{CACHE}/trends_abruzzo_DE.csv"],
     "live": "trends"},
    {"key": "ecb", "label": "Cambio valute (ECB)", "cadence": "mensile",
     "paths": [], "live": "ecb"},
    {"key": "istat_capacita", "label": "Capacità posti letto (ISTAT)", "cadence": "annuale",
     "paths": [f"{CACHE}/istat_capacity_letti_ITF1.csv"], "live": "istat_capacita"},
    {"key": "istat_estero", "label": "Esteri per paese×regione (ISTAT)", "cadence": "annuale",
     "paths": [f"{CACHE}/istat_estero_regione_prov_annuale.csv"], "live": "istat_estero"},
    {"key": "astat", "label": "Alto Adige · flussi e capacità (ASTAT)", "cadence": "mensile",
     "paths": [f"{CACHE}/astat_bolzano_flussi_mensili.csv"], "live": "astat"},
    {"key": "lombardia", "label": "Lombardia · flussi provincia × mercato (Open Data)", "cadence": "annuale",
     "paths": [f"{CACHE}/lombardia_flussi_provincia_mese.csv"], "live": "lombardia"},
    {"key": "toscana", "label": "Toscana · movimento per comune (Open Data)", "cadence": "annuale",
     "paths": [f"{CACHE}/toscana_movimento_comune_anno.csv"], "live": "toscana"},
    {"key": "sardegna", "label": "Sardegna · movimento mensile comune × mercato (Osservatorio)", "cadence": "manuale",
     "paths": [f"{CACHE}/sardegna_flussi_comune_mese.csv"], "live": "sardegna"},
    {"key": "turnot", "label": "ISTAT Viaggi e Vacanze · notti residenti per scopo", "cadence": "annuale",
     "paths": [f"{CACHE}/istat_turnot_scopo_regione.csv"], "live": "turnot"},
    {"key": "wikipedia", "label": "Wikipedia pageviews", "cadence": "mensile",
     "paths": sorted(glob.glob(f"{CACHE}/wiki_*.csv")) or [f"{CACHE}/wiki_de.csv"], "live": "wikipedia"},
    {"key": "bdi", "label": "Spesa turisti (Banca d'Italia)", "cadence": "trimestrale",
     "paths": [f"{CACHE}/bdi_turismo_ts.xlsx"], "live": "manual"},
    {"key": "eurostat", "label": "Voli verso Pescara (Eurostat)", "cadence": "annuale",
     "paths": [f"{CACHE}/eurostat_pescara_flights.csv"], "live": "manual"},
]


def _verdict(last: pd.Timestamp | None, cadence: str) -> tuple[str, int | None]:
    """Giudizio di freschezza dal ritardo dell'ultimo dato. Ritorna (emoji, gap_giorni)."""
    if last is None:
        return "⚪", None
    gap = (pd.Timestamp.today().normalize() - last.normalize()).days
    soglia = _MAX_GAP_DAYS.get(cadence, 130)
    if gap <= soglia:
        return "🟢", gap
    if gap <= soglia * 2:
        return "🟡", gap
    return "🔴", gap


# ── status istantaneo (no rete) ─────────────────────────────────────────────
def status_all() -> list[dict]:
    out = []
    for s in SOURCES:
        if s["key"] == "ecb":  # sempre live, niente file
            out.append({"key": s["key"], "fonte": s["label"], "cadenza": s["cadence"],
                        "ultimo_dato": "live (sempre aggiornato)", "righe": "—",
                        "scaricato": "—", "stato": "🟢", "live": True})
            continue
        path = _first_existing(s["paths"])
        lp = _last_period(path) if path else None
        last, nrows = (lp if lp else (None, None))
        emoji, _gap = _verdict(last, s["cadence"])
        mtime = (pd.Timestamp(os.path.getmtime(path), unit="s").strftime("%Y-%m-%d")
                 if path else "assente")
        out.append({
            "key": s["key"], "fonte": s["label"], "cadenza": s["cadence"],
            "ultimo_dato": (last.strftime("%Y-%m") if isinstance(last, pd.Timestamp) else "—"),
            "righe": (nrows if nrows is not None else "—"),
            "scaricato": mtime, "stato": emoji, "live": s["live"] != "manual",
        })
    return out


# ── confronto live (con rete) ───────────────────────────────────────────────
def _fresh_last_period(source: dict) -> pd.Timestamp | None:
    """Riscarica in temp la fonte e restituisce l'ultimo periodo disponibile alla fonte."""
    kind = source["live"]
    tmp = tempfile.mkdtemp(prefix="tdh_chk_")
    if kind == "istat_presenze":
        df = RS.fetch_presences_foreign_monthly(cache_dir=tmp, refresh=True)
        return pd.to_datetime(df["date"]).max()
    if kind == "istat_glob":
        # serie rappresentativa: province di Pescara, presenze totali
        df = RS.fetch_istat_presences(area="ITF13", data_type="NI", accom="ALL",
                                      country="WORLD", cache_dir=tmp, refresh=True)
        return pd.to_datetime(df["date"]).max()
    if kind == "trends":
        df = RS.fetch_search_monthly("DE", cache_dir=tmp, refresh=True)
        return pd.to_datetime(df["date"]).max()
    if kind == "wikipedia":
        df = RS.fetch_wikipedia_monthly("de", cache_dir=tmp, refresh=True)
        return pd.to_datetime(df["date"]).max()
    if kind == "istat_capacita":
        df = RS.fetch_istat_capacity(cache_dir=tmp, refresh=True)
        return pd.Timestamp(f"{int(df['anno'].max())}-12-31")
    if kind == "istat_estero":  # probe leggero: solo l'anno più recente disponibile
        y = RS.fetch_estero_latest_year()
        return pd.Timestamp(f"{int(y)}-12-31") if y else None
    if kind == "astat":  # probe leggero: mese più recente pubblicato da ASTAT
        p = RS.fetch_astat_latest_period()
        return pd.Timestamp(f"{p}-01") if p else None
    if kind == "lombardia":  # probe leggero: anno più recente su Socrata
        y = RS.fetch_lombardia_latest_year()
        return pd.Timestamp(f"{int(y)}-12-31") if y else None
    if kind == "toscana":  # probe leggero: anno più recente dei dataset CKAN
        y = RS.fetch_toscana_latest_year()
        return pd.Timestamp(f"{int(y)}-12-31") if y else None
    if kind == "sardegna":  # export manuale: ultimo anno dai CSV locali
        y = RS.fetch_sardegna_latest_year()
        return pd.Timestamp(f"{int(y)}-12-31") if y else None
    if kind == "turnot":  # probe leggero: anno più recente V&V (una sola serie)
        y = RS.fetch_turnot_latest_year()
        return pd.Timestamp(f"{int(y)}-12-31") if y else None
    if kind == "ecb":
        df = RS.fetch_fx_monthly("USD")
        return pd.to_datetime(df["date"]).max()
    return None


def live_check(keys: list[str] | None = None) -> list[dict]:
    """Per le fonti refreshabili confronta cache vs fonte. Ritorna esiti e salva lo stato."""
    res = []
    for s in SOURCES:
        if s["live"] == "manual":
            continue
        if keys and s["key"] not in keys:
            continue
        path = _first_existing(s["paths"])
        cache_last = (_last_period(path) or (None, None))[0] if path else None
        try:
            fresh_last = _fresh_last_period(s)
            if s["key"] == "ecb":
                status, msg = "🟢", f"live · ultimo {fresh_last:%Y-%m}" if fresh_last is not None else "live"
            elif fresh_last is None:
                status, msg = "⚪", "nessun dato ricevuto"
            elif cache_last is None or fresh_last > cache_last:
                status = "🟡"
                msg = f"NUOVO dato fino a {fresh_last:%Y-%m} (in cache: " \
                      f"{cache_last:%Y-%m})" if cache_last is not None else f"nuovo: {fresh_last:%Y-%m}"
            else:
                status, msg = "🟢", f"invariato (fino a {cache_last:%Y-%m})"
        except Exception as e:  # noqa: BLE001
            status, msg, fresh_last = "🔴", f"errore: {type(e).__name__}", None
        res.append({"key": s["key"], "fonte": s["label"], "stato": status, "esito": msg,
                    "cache_last": (cache_last.strftime("%Y-%m") if isinstance(cache_last, pd.Timestamp) else None),
                    "fresh_last": (fresh_last.strftime("%Y-%m") if isinstance(fresh_last, pd.Timestamp) else None),
                    "nuovo": status == "🟡"})
    _save_state(res)
    return res


# ── applica aggiornamento (nulla osta) ──────────────────────────────────────
def apply_update(key: str) -> dict:
    """Riscarica nella cache REALE la fonte indicata. Ritorna {ok, msg}."""
    src = next((s for s in SOURCES if s["key"] == key), None)
    if not src:
        return {"ok": False, "msg": "fonte sconosciuta"}
    kind = src["live"]
    try:
        if kind == "istat_presenze":
            df = RS.fetch_presences_foreign_monthly(refresh=True)
            return {"ok": True, "msg": f"ISTAT presenze aggiornate · fino a {pd.to_datetime(df['date']).max():%Y-%m}"}
        if kind == "istat_glob":
            n = 0
            for p in sorted(glob.glob(f"{CACHE}/istat_ITF1?_*.csv")):
                parts = os.path.basename(p)[:-4].split("_")  # istat_<area>_<dt>_<accom>_<country>
                if len(parts) == 5:
                    _, area, dt, accom, country = parts
                    RS.fetch_istat_presences(area=area, data_type=dt, accom=accom,
                                             country=country, refresh=True)
                    n += 1
            return {"ok": True, "msg": f"ISTAT province aggiornate · {n} serie"}
        if kind == "trends":
            geos = [os.path.basename(p)[:-4].split("_")[-1]
                    for p in sorted(glob.glob(f"{CACHE}/trends_abruzzo_*.csv"))]
            for g in geos:
                RS.fetch_search_monthly(g, refresh=True)
            return {"ok": True, "msg": f"Google Trends aggiornati · {len(geos)} mercati"}
        if kind == "wikipedia":
            langs = [os.path.basename(p)[:-4].split("_")[-1]
                     for p in sorted(glob.glob(f"{CACHE}/wiki_*.csv"))]
            for lg in langs:
                RS.fetch_wikipedia_monthly(lg, refresh=True)
            return {"ok": True, "msg": f"Wikipedia aggiornata · {len(langs)} lingue"}
        if kind == "istat_capacita":
            df = RS.fetch_istat_capacity(refresh=True)
            return {"ok": True, "msg": f"ISTAT capacità aggiornata · fino al {int(df['anno'].max())}"}
        if kind == "istat_estero":
            # dato ANNUALE + download pesante (131 territori): riscarica TUTTO solo se ISTAT
            # ha pubblicato un anno più recente di quello già in cache (probe leggero prima).
            fresh = RS.fetch_estero_latest_year()
            cache_path = f"{CACHE}/istat_estero_regione_prov_annuale.csv"
            cache_year = None
            if os.path.exists(cache_path):
                try:
                    y = pd.to_numeric(pd.read_csv(cache_path)["TIME_PERIOD"], errors="coerce").dropna()
                    cache_year = int(y.max()) if len(y) else None
                except Exception:  # noqa: BLE001
                    pass
            if fresh and cache_year and cache_year >= fresh:
                return {"ok": True, "msg": f"già aggiornato (anno {cache_year}); nessun anno nuovo pubblicato"}
            df = RS.fetch_estero_country_region_annual(refresh=True)
            yy = pd.to_numeric(df["TIME_PERIOD"], errors="coerce").dropna()
            return {"ok": True, "msg": f"ISTAT esteri paese×regione aggiornati · fino al {int(yy.max())}"}
        if kind == "astat":
            # download leggero (2 query): riscarica solo se ASTAT ha un mese più recente della cache
            fresh = RS.fetch_astat_latest_period()
            cache_path = f"{CACHE}/astat_bolzano_flussi_mensili.csv"
            cache_last = (_last_period(cache_path) or (None, None))[0] if os.path.exists(cache_path) else None
            fresh_ts = pd.Timestamp(f"{fresh}-01") if fresh else None
            if fresh_ts is not None and cache_last is not None and fresh_ts <= cache_last:
                return {"ok": True, "msg": f"già aggiornato (fino a {cache_last:%Y-%m}); nessun mese nuovo"}
            d = RS.fetch_astat_bolzano(refresh=True)
            last = pd.to_datetime(d["flussi"]["date"]).max()
            return {"ok": True, "msg": f"ASTAT Alto Adige aggiornato · flussi fino a {last:%Y-%m}"}
        if kind == "lombardia":
            # dato annuale via Socrata: riscarica solo se è stato pubblicato un anno più recente
            fresh = RS.fetch_lombardia_latest_year()
            cache_path = f"{CACHE}/lombardia_flussi_provincia_mese.csv"
            cache_year = None
            if os.path.exists(cache_path):
                try:
                    y = pd.to_numeric(pd.read_csv(cache_path, usecols=["anno"])["anno"], errors="coerce").dropna()
                    cache_year = int(y.max()) if len(y) else None
                except Exception:  # noqa: BLE001
                    pass
            if fresh and cache_year and cache_year >= fresh:
                return {"ok": True, "msg": f"già aggiornato (anno {cache_year}); nessun anno nuovo"}
            df = RS.fetch_lombardia_flussi(refresh=True)
            return {"ok": True, "msg": f"Lombardia aggiornata · fino al {int(pd.to_numeric(df['anno']).max())}"}
        if kind == "toscana":
            # dato annuale via CKAN: riscarica solo se è stato pubblicato un anno più recente
            fresh = RS.fetch_toscana_latest_year()
            cache_path = f"{CACHE}/toscana_movimento_comune_anno.csv"
            cache_year = None
            if os.path.exists(cache_path):
                try:
                    y = pd.to_numeric(pd.read_csv(cache_path, usecols=["anno"])["anno"], errors="coerce").dropna()
                    cache_year = int(y.max()) if len(y) else None
                except Exception:  # noqa: BLE001
                    pass
            if fresh and cache_year and cache_year >= fresh:
                return {"ok": True, "msg": f"già aggiornato (anno {cache_year}); nessun anno nuovo"}
            df = RS.fetch_toscana_movimento(refresh=True)
            return {"ok": True, "msg": f"Toscana aggiornata · fino al {int(pd.to_numeric(df['anno']).max())}"}
        if kind == "sardegna":
            # export MANUALE: ricostruisce le cache dai CSV in dati_manuali/sardegna/
            df_cm, _ = RS.fetch_sardegna_manual(refresh=True)
            if df_cm is None or df_cm.empty:
                return {"ok": False, "msg": "nessun CSV movimento in dati_manuali/sardegna/"}
            return {"ok": True, "msg": f"Sardegna ricostruita dai file locali · fino al {int(df_cm['anno'].max())}"}
        if kind == "turnot":
            fresh = RS.fetch_turnot_latest_year()
            cache_path = f"{CACHE}/istat_turnot_scopo_regione.csv"
            cache_year = None
            if os.path.exists(cache_path):
                try:
                    y = pd.to_numeric(pd.read_csv(cache_path, usecols=["anno"])["anno"], errors="coerce").dropna()
                    cache_year = int(y.max()) if len(y) else None
                except Exception:  # noqa: BLE001
                    pass
            if fresh and cache_year and cache_year >= fresh:
                return {"ok": True, "msg": f"già aggiornato (anno {cache_year}); nessun anno nuovo"}
            df = RS.fetch_turnot_purpose(refresh=True)
            return {"ok": True, "msg": f"ISTAT V&V aggiornato · fino al {int(pd.to_numeric(df['anno']).max())}"}
        if kind == "ecb":
            return {"ok": True, "msg": "ECB è sempre live: nessuna cache da aggiornare"}
        return {"ok": False, "msg": "refresh non ancora disponibile per questa fonte (Fase 2)"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "msg": f"errore: {type(e).__name__}: {e}"}


# ── stato persistente ───────────────────────────────────────────────────────
def _save_state(results: list[dict]):
    os.makedirs("data", exist_ok=True)
    state = {"last_run": pd.Timestamp.now().isoformat(timespec="seconds"),
             "sources": {r["key"]: {"stato": r["stato"], "esito": r["esito"],
                                    "fresh_last": r.get("fresh_last")} for r in results}}
    json.dump(state, open(STATE_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


def last_run_info() -> dict | None:
    if not os.path.exists(STATE_PATH):
        return None
    try:
        return json.load(open(STATE_PATH, encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def refresh_approved_candidates() -> list[dict]:
    """Rinfresca le fonti candidate APPROVATE (lette da data/candidates_state.json),
    così le fonti 'prese in carico dal motore' restano aggiornate. Senza dipendere da Streamlit."""
    out = []
    if not os.path.exists(STATE_CAND):
        return out
    try:
        state = json.load(open(STATE_CAND, encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return out
    for cid, info in state.items():
        if not info.get("approved"):
            continue
        fn = CS.CANDIDATE_LOADERS.get(cid)
        if not fn:
            continue
        try:
            r = fn()
            out.append({"fonte": f"candidata:{cid}", "ok": True, "msg": r.get("msg", "ok")})
        except Exception as e:  # noqa: BLE001
            out.append({"fonte": f"candidata:{cid}", "ok": False, "msg": f"{type(e).__name__}"})
    return out


def refresh_all(skip_live: set | None = None) -> list[dict]:
    """Riscarica nella cache REALE le fonti refreshabili (per lo schedulatore, modalità B):
    fonti core + candidate APPROVATE. Le fonti 'manual' (BdI, Eurostat) e 'ecb' sono sempre
    saltate; `skip_live` aggiunge altri tipi da saltare (es. Trends/Wikipedia in modalità fast)."""
    skip = {"manual", "ecb"} | (skip_live or set())  # ecb è sempre live, non ha cache
    out = []
    for s in SOURCES:
        if s["live"] in skip:
            continue
        r = apply_update(s["key"])
        out.append({"fonte": s["label"], **r})
    out.extend(refresh_approved_candidates())
    return out


# ── uso da schedulatore ─────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    try:
        import truststore
        truststore.inject_into_ssl()
    except Exception:  # noqa: BLE001
        pass
    if "--apply" in sys.argv:
        # modalità B: riscarica davvero nella cache (lo schedulatore poi committa le modifiche)
        # --fast (per lo scheduler): aggiorna SOLO le fonti territoriali con "skip intelligente"
        # su server veloci/affidabili — astat (ASTAT SDMX), lombardia (Socrata), toscana (CKAN):
        # probe leggero + download solo se c'è davvero un anno/mese nuovo. Salta TUTTE le fonti
        # ISTAT (esploradati.istat.it è lento/appeso per chiamate automatiche) e trends/wikipedia
        # (rate-limited). Quelle restano aggiornabili a mano da «Gestione dati».
        fast = "--fast" in sys.argv
        skip = {"trends", "wikipedia", "istat_glob", "istat_presenze",
                "istat_capacita", "istat_estero", "sardegna", "turnot"} if fast else None
        print("Riscarico le fonti refreshabili nella cache…"
              + (" (modalità fast: escludo Trends/Wikipedia)" if fast else ""))
        ok = 0
        for r in refresh_all(skip_live=skip):
            flag = "✓" if r.get("ok") else "✗"
            print(f"  {flag} {r['fonte']}: {r['msg']}")
            ok += int(bool(r.get("ok")))
        print(f"\n{ok} fonti riscaricate.")
        sys.exit(0)

    print("Controllo aggiornamenti fonti TDH…")
    results = live_check()
    nuovi = [r for r in results if r["nuovo"]]
    for r in results:
        print(f"  {r['stato']} {r['fonte']}: {r['esito']}")
    print(f"\n{len(nuovi)} fonti con dati nuovi." if nuovi else "\nNessun aggiornamento.")
    # exit code 10 se ci sono novità (utile allo schedulatore per decidere)
    sys.exit(10 if nuovi else 0)
