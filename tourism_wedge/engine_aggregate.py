"""
Motore — OPZIONE A (dati reali): un target AGGREGATO + ranking per-mercato.

Perché Opzione A: ISTAT espone le presenze mensili di Abruzzo solo come stranieri
AGGREGATI (non per singolo paese). Quindi:
  • Forecast: un solo OLS difendibile sulle presenze straniere totali, guidato da un
    'basket' di interesse di ricerca per-mercato (pesato per valore) al lag, più
    stagionalità esplicita e trend. Barriera di onestà: deve battere la naive stagionale.
  • Ranking budget: decomposizione trasparente per mercato =
        forza_anticipatrice × momentum × valore_economico × fattibilità
    NON è una stima causale della spesa promo (resta il confine del motore).

Tutti i dati vengono dagli adattatori reali in real_sources.py (ECB, ISTAT, Trends).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

from .data import Market, DEFAULT_MARKETS
from .real_sources import (fetch_presences_foreign_monthly, fetch_istat_presences,
                           fetch_search_monthly, fetch_fx_monthly)


# --------------------------------------------------------------------------
def assemble_real(start: str = "2019-01", end: str | None = None,
                  markets: list[Market] = DEFAULT_MARKETS,
                  region_code: str = "ITF1", trends_kw: str = "Abruzzo") -> pd.DataFrame:
    """Costruisce il pannello reale mensile PER REGIONE.

    Colonne: date, presences (stranieri della regione, ISTAT),
             search_<code> (Google Trends per paese, keyword = nome regione),
             fx_<code> (ECB per valuta).
    Tollerante ai 429 di Trends: se un mercato non torna, la sua colonna resta NaN.
    """
    # target: presenze straniere della REGIONE selezionata (NUTS2, con retry)
    target = fetch_istat_presences(area=region_code, data_type="NI", accom="ALL",
                                   country="WRL_X_ITA", start=start, end=end)[["date", "presences"]]
    smax = target["date"].max()
    cols = {}
    for mk in markets:
        try:
            s = fetch_search_monthly(mk.code, keyword=trends_kw, start=start, end=end)
        except Exception:  # noqa: BLE001 — Google Trends 429/instabile: colonna NaN
            s = pd.DataFrame({"date": pd.Series(dtype="datetime64[ns]"), "search": pd.Series(dtype=float)})
        cols[mk.code] = s
        if len(s):
            smax = max(smax, s["date"].max())
    spine = pd.DataFrame({"date": pd.date_range(f"{start}-01", smax, freq="MS")})

    df = spine.merge(target, on="date", how="left")
    for mk in markets:
        s = cols[mk.code].rename(columns={"search": f"search_{mk.code}"})
        fx = fetch_fx_monthly(mk.currency, start=start, end=end).rename(columns={"fx": f"fx_{mk.code}"})
        df = df.merge(s, on="date", how="left").merge(fx, on="date", how="left")
    return df


def _deseason(x: pd.Series, month: pd.Series) -> pd.Series:
    """Toglie la media di mese (per non scambiare la stagionalità comune per segnale)."""
    return x - x.groupby(month).transform("mean")


def lead_corr(presences: pd.Series, search: pd.Series, month: pd.Series,
              max_lag: int = 4) -> tuple[int, float]:
    """Lag (mesi) a cui il search anticipa al meglio le presenze, e relativa correlazione,
    entrambi su serie deseasonalizzate. Restituisce (lag, corr)."""
    p = _deseason(presences, month)
    s = _deseason(search, month)
    best = (0, -np.inf)
    for L in range(0, max_lag + 1):
        c = s.shift(L).corr(p)
        if pd.notna(c) and c > best[1]:
            best = (L, float(c))
    return best


# --------------------------------------------------------------------------
@dataclass
class AggregateFit:
    model: object
    df: pd.DataFrame          # righe di training (presences osservate) + colonne costruite
    lag: int
    beats_naive: bool
    mae_model: float
    mae_naive: float
    mape_model: float
    basket_weights: dict      # code -> peso usato nel basket

    def coefficient_reading(self) -> list[str]:
        p = self.model.params
        out = [
            f"Basket search (lag {self.lag} mesi): +1 punto dell'indice di ricerca pesato "
            f"{self.lag} mesi fa ~ {p.get('basket_lag', float('nan')):+.0f} presenze straniere/mese."
        ]
        month_eff = {int(k.split('.')[-1].rstrip('])')): v
                     for k, v in p.items() if k.startswith("C(month)")}
        if month_eff:
            top = max(month_eff, key=month_eff.get)
            out.append(f"Stagionalità: mese più forte (netto) = mese {top} "
                       f"(+{month_eff[top]:,.0f} vs mese base).")
        if "covid" in p.index:
            out.append(f"COVID (2020-2021): {p['covid']:+,.0f} presenze/mese nei mesi pandemici "
                       f"(anomalia isolata, non inquina stagionalità e trend).")
        out.append(f"Trend: {p.get('t', float('nan')):+.0f} presenze/mese di deriva di fondo.")
        return out


def fit_aggregate(df: pd.DataFrame, markets: list[Market] = DEFAULT_MARKETS,
                  holdout: int = 12, covid_start: str = "2020-03",
                  covid_end: str = "2021-12") -> AggregateFit:
    """Stima il modello aggregato e lo confronta con la naive stagionale su un holdout.

    covid_start/covid_end: finestra mensile trattata come anomala (dummy COVID), per non
    far distorcere stagionalità/trend/segnale dal crollo e rimbalzo pandemici.
    """
    d = df.copy()
    d["month"] = d["date"].dt.month
    d["t"] = np.arange(len(d))
    d["covid"] = ((d["date"] >= pd.Timestamp(covid_start + "-01")) &
                  (d["date"] <= pd.Timestamp(covid_end + "-01"))).astype(int)

    # basket: media dei search per-mercato pesata per valore economico (normalizzato)
    w = np.array([mk.spend_per_visitor for mk in markets], float)
    w = w / w.sum()
    weights = {mk.code: float(wi) for mk, wi in zip(markets, w)}
    d["basket"] = sum(weights[mk.code] * d[f"search_{mk.code}"] for mk in markets)

    # se Google Trends non è disponibile per la regione (basket vuoto/scarso),
    # ripiego su un modello SOLO stagionale (niente segnale anticipatore).
    tr = d.dropna(subset=["presences"]).reset_index(drop=True)
    has_basket = tr["basket"].notna().sum() >= 24
    if has_basket:
        lag, _ = lead_corr(tr["presences"], tr["basket"], tr["month"])
        d["basket_lag"] = d["basket"].shift(lag)
        fit_df = d.dropna(subset=["presences", "basket_lag"]).reset_index(drop=True)
        formula = "presences ~ basket_lag + C(month) + t + covid"
    else:
        lag = 1
        d["basket_lag"] = np.nan
        fit_df = d.dropna(subset=["presences"]).reset_index(drop=True)
        formula = "presences ~ C(month) + t + covid"

    train, test = fit_df.iloc[:-holdout], fit_df.iloc[-holdout:]
    model = smf.ols(formula, data=train).fit()
    pred = model.predict(test).to_numpy()
    actual = test["presences"].to_numpy()

    full = fit_df.set_index("date")["presences"]
    naive = np.array([full.get(dt - pd.DateOffset(years=1), np.nan) for dt in test["date"]])
    mask = ~np.isnan(naive)
    mae_model = float(np.mean(np.abs(actual - pred)))
    mae_naive = float(np.mean(np.abs(actual[mask] - naive[mask]))) if mask.any() else float("nan")
    mape_model = float(np.mean(np.abs((actual - pred) / np.clip(actual, 1, None))) * 100)
    beats = (not np.isnan(mae_naive)) and (mae_model < mae_naive)

    full_model = smf.ols(formula, data=fit_df).fit()
    # tengo anche le righe future (presences NaN) per il forecast nel lead-time
    d["basket_lag"] = d["basket"].shift(lag) if has_basket else np.nan
    return AggregateFit(full_model, d, lag, beats, mae_model, mae_naive, mape_model, weights)


@dataclass
class AggregateForecast:
    dates: list
    mean: np.ndarray
    lo: np.ndarray
    hi: np.ndarray
    lastyear: np.ndarray


def forecast_aggregate(fit: AggregateFit) -> AggregateForecast:
    """Forecast delle presenze straniere totali entro l'orizzonte = lag, usando il
    basket di search GIÀ osservato (nessuna previsione del search)."""
    d, lag = fit.df, max(fit.lag, 1)
    last_obs = d.dropna(subset=["presences"])["date"].max()
    last_t = int(d.loc[d["date"] == last_obs, "t"].iloc[0])

    fut_dates = [last_obs + pd.DateOffset(months=h) for h in range(1, lag + 1)]
    rows = []
    for h, dt in enumerate(fut_dates, start=1):
        src = d.loc[d["date"] == dt - pd.DateOffset(months=lag), "basket"]
        bk = d["basket"].dropna()
        basket_lag = (float(src.iloc[0]) if len(src) and pd.notna(src.iloc[0])
                      else (float(bk.iloc[-1]) if len(bk) else 0.0))
        rows.append({"month": dt.month, "t": last_t + h, "basket_lag": basket_lag, "covid": 0})
    fut = pd.DataFrame(rows)
    pr = fit.model.get_prediction(fut).summary_frame(alpha=0.20)  # PI 80%
    hist = d.set_index("date")["presences"]
    lastyear = np.array([hist.get(dt - pd.DateOffset(years=1), np.nan) for dt in fut_dates])
    return AggregateForecast(fut_dates, pr["mean"].to_numpy(),
                             pr["obs_ci_lower"].to_numpy(), pr["obs_ci_upper"].to_numpy(), lastyear)


# --------------------------------------------------------------------------
def rank_markets(df: pd.DataFrame, markets: list[Market] = DEFAULT_MARKETS,
                 value_override: dict | None = None,
                 feas_override: dict | None = None) -> list[dict]:
    """Decomposizione trasparente del 'dove conviene agire':
        score = max(forza_anticipatrice,0) × momentum × valore_economico × fattibilità
    value_override: {code: €/visitatore} reali (Banca d'Italia) al posto di mk.spend_per_visitor.
    feas_override:  {code: peso 0..1} di fattibilità reale (es. connettività voli Eurostat) al
    posto del flag statico mk.capacity_ok. Restituisce schede ordinate."""
    vov = value_override or {}
    fov = feas_override or {}
    d = df.copy()
    d["month"] = d["date"].dt.month
    tr = d.dropna(subset=["presences"]).reset_index(drop=True)

    cards = []
    for mk in markets:
        valore = float(vov.get(mk.code, mk.spend_per_visitor))
        scode = f"search_{mk.code}"
        lag, corr = lead_corr(tr["presences"], tr[scode], tr["month"])
        if not np.isfinite(corr):  # mercato senza Trends per la regione: forza 0
            corr = 0.0

        s = d[scode].dropna()
        recent = s.tail(3).mean()
        yoy = s.tail(15).head(3).mean() if len(s) >= 15 else np.nan   # stessi 3 mesi un anno prima
        momentum = (recent - yoy) / yoy * 100.0 if (np.isfinite(yoy) and yoy != 0) else 0.0

        feas = float(fov.get(mk.code, 1.0 if mk.capacity_ok else 0.5))
        connected = feas >= 0.6
        score = max(corr, 0.0) * momentum * valore * feas

        if not connected:
            reco = "Mantenere (voli diretti limitati)"
        elif corr < 0.15:
            reco = "Monitorare (segnale anticipatore debole)"
        elif momentum > 6:
            reco = "Aumentare"
        elif momentum < -6:
            reco = "Ridurre"
        else:
            reco = "Mantenere"

        cards.append({
            "market": mk.name, "code": mk.code,
            "raccomandazione": reco,
            "forza_anticipatrice": round(corr, 2),
            "lag_mesi": lag,
            "momentum_search_pct": round(momentum, 1),
            "valore_eur_per_visitatore": round(valore),
            "capacita_voli_ok": connected,
            "fattibilita": round(feas, 2),
            "search_recente": round(float(recent), 0),
            "score": round(score, 0),
        })
    ranked = sorted(cards, key=lambda c: c["score"], reverse=True)
    for i, c in enumerate(ranked):
        c["rank"] = i + 1
    return ranked
