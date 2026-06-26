"""
TIER 2 (strutturale) — analisi su dati REALI, eseguibile come bakeoff.py.

Due esperimenti, dallo studio sui modelli:
  1) PARTIAL POOLING tra regioni: stima il trend annuo di OGNI regione e poi lo
     RESTRINGE verso la media nazionale (empirical-Bayes / James-Stein), di più dove
     la stima della singola regione è incerta. Risponde al problema "serie corte per cella".
  2) RICONCILIAZIONE gerarchica Italia↔regioni: confronta la previsione nazionale diretta
     (top-down) con la somma delle previsioni regionali (bottom-up, coerente per costruzione)
     e ne misura lo scostamento.

Usa le funzioni riusabili di tdhlib (annual_slope_se, partial_pool_slopes, reconcile_bottom_up,
project_var) e i pannelli annuali per regione. Cache-first: la prima esecuzione può scaricare
le regioni mancanti da ISTAT (lenta), poi è veloce. Salva un artefatto in .cache/.
"""
from __future__ import annotations

import json
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import numpy as np

import regions as RG
import tdhlib as L

WINDOW = 10          # anni recenti su cui stimare il trend (regime recente)
DROP_COVID = True    # esclude il 2020 dal calcolo
VARS = ["presenze_str", "spesa", "viaggiatori", "presenze_tot"]


def series_for(panel, key, n_years=WINDOW):
    """(anni, valori) della variabile `key` negli ultimi n_years, 2020 escluso."""
    if panel is None or panel.empty or key not in panel:
        return None
    s = panel[key].dropna()
    s.index = s.index.astype(int)
    if DROP_COVID and 2020 in s.index:
        s = s.drop(index=2020)
    s = s.tail(n_years)
    return (s.index.values, s.values) if len(s) >= 3 else None


def load_panels():
    panels = {}
    codes = list(RG.REGIONS.keys())
    for i, c in enumerate(codes, 1):
        try:
            p = L.region_annual_panel(c)
            panels[c] = p
            print(f"  [{i:02d}/{len(codes)}] {RG.REGIONS[c]['nome']:28} anni={len(p)}")
        except Exception as e:  # noqa: BLE001
            print(f"  [{i:02d}/{len(codes)}] {RG.REGIONS[c]['nome']:28} ERR {type(e).__name__}")
    try:
        panels[RG.NATIONAL] = L.region_annual_panel(RG.NATIONAL)
    except Exception:  # noqa: BLE001
        panels[RG.NATIONAL] = None
    return panels


def experiment_pooling(panels, key):
    # pooling sul TASSO DI CRESCITA RELATIVO (%/anno): pendenza ÷ livello medio. Così serie
    # di taglia molto diversa (Lazio vs Molise) diventano comparabili e il pooling non degenera.
    slopes = {}
    for c in RG.REGIONS:
        ser = series_for(panels.get(c), key)
        if not ser:
            slopes[c] = None
            continue
        yrs, vals = ser
        lvl = float(np.mean(vals))
        sl = L.annual_slope_se(yrs, vals / lvl) if lvl else None  # frazione/anno
        slopes[c] = (sl[0] * 100, sl[1] * 100) if sl else None    # %/anno
    res = L.partial_pool_slopes(slopes)
    print(f"\n=== PARTIAL POOLING · {L.REGION_VAR_LABEL.get(key, key)} "
          f"— crescita %/anno (ultimi {WINDOW} anni, 2020 escluso) ===")
    if not res["by_code"]:
        print("  dati insufficienti per il pooling.")
        return res
    print(f"  media nazionale mu = {res['mu']:+.1f}%/anno · "
          f"varianza tra regioni tau2 = {res['tau2']:.1f} · regioni usate = {res['n']}")
    print(f"  {'Regione':28} {'grezza':>9} {'ristretta':>10} {'peso w':>8}  spostamento")
    rows = sorted(res["by_code"].items(), key=lambda kv: kv[1]["weight"])
    for c, v in rows:
        move = v["shrunk"] - v["raw"]
        print(f"  {RG.REGIONS[c]['nome']:28} {v['raw']:+8.1f}% {v['shrunk']:+9.1f}% "
              f"{v['weight']:8.2f}  {move:+.1f}")
    # quanto pooling: peso medio basso = molto restringimento
    wmean = float(np.mean([v["weight"] for v in res["by_code"].values()]))
    print(f"  → peso medio sulla singola regione = {wmean:.2f} "
          f"({'molto' if wmean < 0.5 else 'poco'} restringimento verso la media nazionale)")
    return res


def experiment_reconciliation(panels, key="presenze_str", horizon=1):
    print(f"\n=== RICONCILIAZIONE gerarchica · {L.REGION_VAR_LABEL.get(key, key)} "
          f"(proiezione +{horizon} anno) ===")
    region_fc = {}
    for c in RG.REGIONS:
        try:
            pr = L.project_var(panels.get(c), key, horizon=horizon,
                               drop_covid=DROP_COVID, n_years=WINDOW)
            if pr:
                region_fc[c] = pr["fc_mean"][-1]
        except Exception:  # noqa: BLE001
            pass
    nat = None
    try:
        prn = L.project_var(panels.get(RG.NATIONAL), key, horizon=horizon,
                            drop_covid=DROP_COVID, n_years=WINDOW)
        nat = prn["fc_mean"][-1] if prn else None
    except Exception:  # noqa: BLE001
        nat = None
    rec = L.reconcile_bottom_up(region_fc, nat)
    _n = lambda v: f"{v:,.0f}".replace(",", ".")  # noqa: E731
    print(f"  somma regioni (bottom-up, coerente)  = {_n(rec['bottom_up_total'])}")
    if nat:
        print(f"  nazionale diretto (top-down)         = {_n(nat)}")
        print(f"  scostamento (incoerenza)             = {rec['gap_pct']:+.1f}%")
        print("  → la vista coerente da pubblicare è il bottom-up: i totali tornano per "
              "costruzione (somma delle regioni).")
    else:
        print("  (nazionale diretto non disponibile: uso il bottom-up come totale coerente)")
    print(f"  regioni incluse: {rec['n_regioni']}/{len(RG.REGIONS)}")
    return rec


def main():
    print("Carico i pannelli annuali per regione (cache-first)…")
    panels = load_panels()
    pooled = {}
    for key in VARS:
        res = experiment_pooling(panels, key)
        if res["by_code"]:
            pooled[key] = {"mu": res["mu"], "tau2": res["tau2"],
                           "by_code": {c: {"raw": v["raw"], "shrunk": v["shrunk"],
                                           "weight": v["weight"]}
                                       for c, v in res["by_code"].items()}}
    rec = experiment_reconciliation(panels, "presenze_str", horizon=1)

    artifact = {"window": WINDOW, "drop_covid": DROP_COVID,
                "pooled_trends": pooled,
                "reconciliation_presenze_str": {"bottom_up_total": rec["bottom_up_total"],
                                                "national_top_down": rec["national_top_down"],
                                                "gap_pct": rec["gap_pct"]}}
    out = ".cache/tier2_pooled_trends.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(artifact, f, ensure_ascii=False, indent=2)
    print(f"\nArtefatto salvato: {out}")


if __name__ == "__main__":
    try:
        import truststore
        truststore.inject_into_ssl()
    except Exception:  # noqa: BLE001
        pass
    main()
