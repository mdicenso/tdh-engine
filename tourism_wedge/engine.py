"""
Motore analitico del wedge.

Modello del PRIMO GIRO (volutamente trasparente, leggibile in sala):

    presenze_t = beta0
               + beta_search * search_{t-L}      <- segnale leading, lag L mesi
               + beta_fx     * fx_t               <- driver cambio (solo non-Euro)
               + somma(effetti_mese)              <- stagionalita' ESPLICITA (11 dummy)
               + beta_t * t                       <- trend
               + errore

Ogni coefficiente ha un significato in italiano corrente. Niente scatole nere.
La barriera di onesta': il modello deve BATTERE la naive stagionale, altrimenti
non si forecasta quel mercato (si etichetta 'segnale insufficiente').
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

from .data import Market


# --------------------------------------------------------------------------
def estimate_lag(panel: pd.DataFrame, max_lag: int = 4) -> int:
    """Stima di quanti mesi il search anticipa le presenze.
    Correlazione search.shift(L) vs presenze, dopo aver tolto le medie di mese
    da entrambe (per non scambiare la stagionalita' comune per causalita')."""
    df = panel.copy()
    df["month"] = df["date"].dt.month
    pres_dev = df["presences"] - df.groupby("month")["presences"].transform("mean")
    srch_dev = df["search"] - df.groupby("month")["search"].transform("mean")
    best_lag, best_corr = 0, -np.inf
    for L in range(0, max_lag + 1):
        c = srch_dev.shift(L).corr(pres_dev)
        if pd.notna(c) and c > best_corr:
            best_lag, best_corr = L, c
    return best_lag


def _design(panel: pd.DataFrame, lag: int, market: Market) -> tuple[pd.DataFrame, str]:
    """Costruisce il DataFrame con la feature laggata e la formula del modello."""
    df = panel.copy()
    df["month"] = df["date"].dt.month
    df["t"] = np.arange(len(df))
    df["search_lag"] = df["search"].shift(lag)
    terms = ["search_lag", "C(month)", "t"]
    if market.currency != "EUR":
        terms.insert(1, "fx")
    formula = "presences ~ " + " + ".join(terms)
    return df, formula


@dataclass
class FitResult:
    market: Market
    lag: int
    formula: str
    model: object
    df: pd.DataFrame
    beats_naive: bool
    mae_model: float
    mae_naive: float
    mape_model: float

    def coefficient_reading(self) -> list[str]:
        """Traduce i coefficienti in frasi leggibili da un assessore."""
        p = self.model.params
        out = [
            f"Search (lag {self.lag} mesi): ogni +1 punto di interesse di ricerca "
            f"{self.lag} mesi fa ~ {p.get('search_lag', float('nan')):+.0f} presenze/mese."
        ]
        if "fx" in p.index:
            verso = "deprime" if p["fx"] < 0 else "favorisce"
            out.append(
                f"Cambio: un euro piu' forte {verso} gli arrivi "
                f"(beta_fx = {p['fx']:+.0f}); euro debole = piu' visitatori."
            )
        month_eff = {int(k.split('.')[-1].rstrip('])')): v
                     for k, v in p.items() if k.startswith("C(month)")}
        if month_eff:
            top = max(month_eff, key=month_eff.get)
            out.append(
                f"Stagionalita': il mese piu' forte (effetto al netto del resto) "
                f"e' il mese {top} (+{month_eff[top]:,.0f} vs mese base)."
            )
        out.append(f"Trend: {p.get('t', float('nan')):+.0f} presenze/mese di deriva di fondo.")
        return out


def fit_market(panel: pd.DataFrame, market: Market, holdout: int = 12) -> FitResult:
    """Stima il modello, lo confronta con la naive stagionale su un holdout."""
    lag = estimate_lag(panel)
    df, formula = _design(panel, lag, market)
    df = df.dropna(subset=["search_lag"]).reset_index(drop=True)

    train, test = df.iloc[:-holdout], df.iloc[-holdout:]
    model = smf.ols(formula, data=train).fit()

    pred = model.predict(test)
    naive = test["presences"].to_numpy() * np.nan
    # naive stagionale: presenze dello stesso mese 12 periodi prima (dalla serie completa)
    full = df.set_index("date")["presences"]
    naive = np.array([full.get(d - pd.DateOffset(years=1), np.nan) for d in test["date"]])

    mask = ~np.isnan(naive)
    actual = test["presences"].to_numpy()
    mae_model = float(np.mean(np.abs(actual - pred.to_numpy())))
    mae_naive = float(np.mean(np.abs(actual[mask] - naive[mask]))) if mask.any() else float("nan")
    mape_model = float(np.mean(np.abs((actual - pred.to_numpy()) / np.clip(actual, 1, None))) * 100)

    beats = (not np.isnan(mae_naive)) and (mae_model < mae_naive)

    # rifit su tutta la serie per il forecast finale
    full_model = smf.ols(formula, data=df).fit()
    return FitResult(market, lag, formula, full_model, df,
                     beats, mae_model, mae_naive, mape_model)


@dataclass
class Forecast:
    dates: list
    mean: np.ndarray
    lo: np.ndarray      # estremo inferiore intervallo di previsione (80%)
    hi: np.ndarray
    lastyear: np.ndarray  # stesse mensilita' un anno prima (riferimento)


def forecast_within_lead(fit: FitResult, market: Market) -> Forecast:
    """Forecast a orizzonte H = lag: usa SOLO il search gia' osservato.
    Oltre il lead-time servirebbe prevedere anche il search (piu' incertezza)."""
    df, lag = fit.df, max(fit.lag, 1)
    last_date = df["date"].iloc[-1]
    last_t = int(df["t"].iloc[-1])

    fut_dates = [last_date + pd.DateOffset(months=h) for h in range(1, lag + 1)]
    rows = []
    raw_search = df["search"].to_numpy()
    for h, d in enumerate(fut_dates, start=1):
        # search al lag per il mese futuro d = search osservato a (d - lag mesi)
        src_idx = len(df) - lag + (h - 1)
        rows.append({
            "month": d.month,
            "t": last_t + h,
            "search_lag": raw_search[src_idx] if 0 <= src_idx < len(raw_search) else raw_search[-1],
            "fx": float(df["fx"].iloc[-1]),  # near-term: tieni il cambio corrente
        })
    fut = pd.DataFrame(rows)

    pr = fit.model.get_prediction(fut).summary_frame(alpha=0.20)  # PI 80%
    lastyear = np.array([
        df.set_index("date")["presences"].get(d - pd.DateOffset(years=1), np.nan)
        for d in fut_dates
    ])
    return Forecast(fut_dates, pr["mean"].to_numpy(),
                    pr["obs_ci_lower"].to_numpy(), pr["obs_ci_upper"].to_numpy(), lastyear)


def confidence_label(fit: FitResult) -> tuple[str, str]:
    """Confidenza DERIVATA (non dichiarata): da backtest + barriera naive."""
    if not fit.beats_naive:
        return "bassa", "non batte la naive stagionale: uso solo riferimento storico"
    if fit.mape_model < 8:
        return "alta", f"batte la naive; errore di backtest ~{fit.mape_model:.0f}%"
    if fit.mape_model < 15:
        return "media", f"batte la naive; errore di backtest ~{fit.mape_model:.0f}%"
    return "bassa", f"batte la naive ma errore elevato ~{fit.mape_model:.0f}%"
