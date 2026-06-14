"""
Strato decisionale: trasforma il forecast in una RACCOMANDAZIONE difendibile.

Formato (lo stesso per ogni mercato):
    raccomandazione | evidenza | effetto atteso (range) | confidenza (+perche')
    | meccanismo | rischio
Piu' una vista portafoglio con opportunity-score TRASPARENTE.

Confine onesto (vedi spec): qui si ORDINA per 'momento x valore x fattibilita''.
NON si stima l'effetto causale della spesa promo (servirebbe un disegno
quasi-sperimentale). La raccomandazione dice 'dove tira il vento e dove conviene
agire', non 'spendi X e ottieni Y'.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np

from .data import Market
from .engine import FitResult, Forecast, confidence_label

CONF_WEIGHT = {"alta": 1.0, "media": 0.6, "bassa": 0.3}


@dataclass
class DecisionCard:
    market: str
    raccomandazione: str
    evidenza: list
    effetto_atteso: str
    confidenza: str
    confidenza_perche: str
    meccanismo: str
    rischio: str
    opportunity_score: float


def _momentum_pct(fc: Forecast) -> float:
    base = np.nansum(fc.lastyear)
    if not np.isfinite(base) or base == 0:
        return 0.0
    return (np.nansum(fc.mean) - base) / base * 100.0


def build_card(fit: FitResult, fc: Forecast, market: Market) -> DecisionCard:
    conf, why = confidence_label(fit)
    mom = _momentum_pct(fc)

    # --- raccomandazione (regole trasparenti) ---
    if conf == "bassa":
        reco = "Monitorare"
    elif mom > 6 and market.capacity_ok:
        reco = "Aumentare"
    elif mom > 6 and not market.capacity_ok:
        reco = "Mantenere (vincolo capacita' voli)"
    elif mom < -6:
        reco = "Ridurre"
    else:
        reco = "Mantenere"

    # --- evidenza ---
    recent_search = fit.df["search"].iloc[-1]
    yoy_search = fit.df["search"].iloc[-13] if len(fit.df) > 13 else np.nan
    search_delta = (recent_search - yoy_search) if np.isfinite(yoy_search) else np.nan
    evid = [f"Forecast a {len(fc.mean)} mesi: {mom:+.0f}% vs stesse mensilita' anno prima."]
    if np.isfinite(search_delta):
        evid.append(f"Interesse di ricerca: {recent_search:.0f}/100 ({search_delta:+.0f} su anno prima).")
    if market.currency != "EUR":
        fx = fit.df["fx"].iloc[-1]
        evid.append(f"Cambio {market.currency}: indice {fx:.3f} ({'euro debole, favorevole' if fx < 1 else 'euro forte, sfavorevole'}).")

    # --- effetto atteso come RANGE (mai punto) ---
    tot_lo, tot_hi = float(np.nansum(fc.lo)), float(np.nansum(fc.hi))
    effetto = f"{tot_lo:,.0f}–{tot_hi:,.0f} presenze attese nel lead-time (intervallo 80%)."

    # --- meccanismo ---
    mecc = (f"Il search anticipa gli arrivi di ~{fit.lag} mesi (booking window). "
            f"Si previene la stagione usando un segnale gia' osservato, non una scommessa.")

    # --- rischio ---
    risks = []
    if not market.capacity_ok:
        risks.append("tetto di capacita' voli sullo scalo")
    if conf == "bassa":
        risks.append("segnale debole: trattare come ipotesi, non come certezza")
    risks.append("dati ISTAT pubblicati con ~3 mesi di ritardo")
    rischio = "; ".join(risks)

    # --- opportunity score (trasparente) ---
    incremental = max(np.nansum(fc.mean) - np.nansum(fc.lastyear), 0.0)
    score = incremental * market.spend_per_visitor * CONF_WEIGHT[conf]

    return DecisionCard(market.name, reco, evid, effetto, conf, why, mecc, rischio, round(score, 0))


def portfolio(cards: list[DecisionCard]) -> list[dict]:
    """Classifica i mercati per opportunity-score e suggerisce dove spostare budget."""
    ranked = sorted(cards, key=lambda c: c.opportunity_score, reverse=True)
    return [{"rank": i + 1, **asdict(c)} for i, c in enumerate(ranked)]
