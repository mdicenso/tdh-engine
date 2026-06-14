"""
Esecuzione end-to-end del wedge su dati sintetici.
    python run_wedge.py
Sostituisci SyntheticProvider con RealPanelProvider per girare sui dati veri.
"""
import json
from pathlib import Path

from tourism_wedge import (DEFAULT_MARKETS, SyntheticProvider,
                           fit_market, forecast_within_lead, build_card, portfolio)


def main() -> None:
    provider = SyntheticProvider()   # <- qui si innesta l'adattatore reale
    cards = []
    readings = {}

    for mk in DEFAULT_MARKETS:
        panel = provider.monthly_panel(mk)
        fit = fit_market(panel, mk)
        fc = forecast_within_lead(fit, mk)
        cards.append(build_card(fit, fc, mk))
        readings[mk.name] = {
            "lag_mesi": fit.lag,
            "batte_naive": fit.beats_naive,
            "mae_modello": round(fit.mae_model, 0),
            "mae_naive": round(fit.mae_naive, 0),
            "lettura_coefficienti": fit.coefficient_reading(),
        }

    ranked = portfolio(cards)

    # ---------- output leggibile in sala ----------
    print("\n================  ALLOCAZIONE BUDGET PROMO — RANKING MERCATI  ================\n")
    for r in ranked:
        print(f"[{r['rank']}] {r['market']:<14}  ->  {r['raccomandazione']:<32} "
              f"(opportunity {r['opportunity_score']:,.0f}, confidenza {r['confidenza']})")
    print()

    top = ranked[0]
    print(f"--- Scheda decisionale: {top['market']} ---")
    print(f"  Raccomandazione : {top['raccomandazione']}")
    print( "  Evidenza        :")
    for e in top["evidenza"]:
        print(f"      - {e}")
    print(f"  Effetto atteso  : {top['effetto_atteso']}")
    print(f"  Confidenza      : {top['confidenza']} ({top['confidenza_perche']})")
    print(f"  Meccanismo      : {top['meccanismo']}")
    print(f"  Rischio         : {top['rischio']}")

    print(f"\n--- Lettura per l'assessore (coefficienti): {top['market']} ---")
    for line in readings[top["market"]]["lettura_coefficienti"]:
        print(f"  - {line}")
    print(f"  (lag stimato {readings[top['market']]['lag_mesi']} mesi; "
          f"MAE modello {readings[top['market']]['mae_modello']:,.0f} vs naive "
          f"{readings[top['market']]['mae_naive']:,.0f})")

    # ---------- output strutturato (JSON) ----------
    out = Path("decision_output.json")
    out.write_text(json.dumps({"portfolio": ranked, "diagnostica": readings},
                              ensure_ascii=False, indent=2))
    print(f"\nOutput strutturato salvato in: {out.resolve()}")


if __name__ == "__main__":
    main()
