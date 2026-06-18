"""
Bake-off onesto sul PANNELLO (provincia x origine x mese, dal 2008).

Confronta, su holdout temporale 2023-2024 (no leakage):
  naive stagionale  vs  Random Forest  vs  Gradient Boosting  vs  panel effetti fissi
Target: presenze (livello), ma gli alberi sono ANCORATI a lag-12 come feature
(così non devono estrapolare il trend). Stampa errori e feature importance.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor, HistGradientBoostingRegressor
from sklearn.linear_model import LinearRegression

import panel as P
import econ_sources as E


# ── dati ─────────────────────────────────────────────────────────────────────
def load_features() -> pd.DataFrame:
    pan = P.load_panel().copy()
    pan["cell"] = pan["provincia"] + " / " + pan["origine"]
    # esogene region-level, allineate per data
    fl = E.fetch_pescara_flights_monthly().rename(columns={"pax": "flights"})
    conf = E.build_confidence_panel()
    conf_avg = (conf.groupby("date")["confidence"].mean().rename("conf").reset_index())
    pan = pan.merge(fl, on="date", how="left").merge(conf_avg, on="date", how="left")

    rows = []
    for cell, g in pan.groupby("cell"):
        g = g.sort_values("date").copy()
        s = g["presenze"]
        g["lag_1"] = s.shift(1)
        g["lag_12"] = s.shift(12)        # = naive stagionale
        g["lag_13"] = s.shift(13)
        g["lag_24"] = s.shift(24)
        g["roll3"] = s.shift(1).rolling(3).mean()
        g["roll12"] = s.shift(1).rolling(12).mean()
        g["yoy_lag"] = g["lag_12"] / g["lag_24"]      # momentum dell'anno scorso
        g["flights_l1"] = g["flights"].shift(1)
        g["conf_l1"] = g["conf"].shift(1)
        rows.append(g)
    df = pd.concat(rows, ignore_index=True)
    df["t"] = (df["date"].dt.year - 2008) * 12 + (df["date"].dt.month - 1)
    df["month"] = df["date"].dt.month
    df["covid"] = ((df["date"] >= "2020-03-01") & (df["date"] <= "2021-12-01")).astype(int)
    df["quake"] = ((df["date"] >= "2009-04-01") & (df["date"] <= "2010-12-01")).astype(int)
    return df


NUM = ["lag_1", "lag_12", "lag_13", "lag_24", "roll3", "roll12", "yoy_lag",
       "flights_l1", "conf_l1", "t", "covid", "quake"]


def mae(a, p):
    m = ~(np.isnan(a) | np.isnan(p)); return float(np.mean(np.abs(a[m] - p[m])))


def mape(a, p):
    m = ~(np.isnan(a) | np.isnan(p)) & (a > 0); return float(np.mean(np.abs((a[m] - p[m]) / a[m])) * 100)


def main():
    df = load_features().reset_index(drop=True)
    cat = pd.get_dummies(df[["provincia", "origine", "month"]],
                         columns=["provincia", "origine", "month"], dtype=float)
    df = pd.concat([df, cat], axis=1)
    Xcols = NUM + list(cat.columns)

    df[NUM] = df[NUM].replace([np.inf, -np.inf], np.nan)
    df = df.dropna(subset=NUM + ["presenze"]).reset_index(drop=True)
    tr = df[df["date"] <= "2022-12-01"]
    te = df[df["date"] >= "2023-01-01"]
    print(f"train: {len(tr)} righe (<=2022-12) | test: {len(te)} righe (2023-2024) | celle: {df['cell'].nunique()}")
    yte = te["presenze"].to_numpy()

    res = {}
    # 0) naive stagionale
    res["Naive stagionale"] = te["lag_12"].to_numpy()
    # 1) Random Forest
    rf = RandomForestRegressor(n_estimators=400, min_samples_leaf=3, n_jobs=-1, random_state=0)
    rf.fit(tr[Xcols], tr["presenze"]); res["Random Forest"] = rf.predict(te[Xcols])
    # 2) Gradient Boosting
    gb = HistGradientBoostingRegressor(max_iter=500, learning_rate=0.05, random_state=0)
    gb.fit(tr[Xcols], tr["presenze"]); res["Gradient Boosting"] = gb.predict(te[Xcols])
    # 3) lineare di pannello (stesse feature: lag + esogene + dummy provincia/origine/mese)
    lin = LinearRegression().fit(tr[Xcols], tr["presenze"])
    res["Lineare (pannello)"] = lin.predict(te[Xcols])

    base = mae(yte, res["Naive stagionale"])
    print("\nMODELLO                 MAE      MAPE    skill vs naive")
    for name, pred in res.items():
        m, mp = mae(yte, pred), mape(yte, pred)
        skill = (1 - m / base) * 100
        tag = "  (baseline)" if name.startswith("Naive") else f"  {skill:+5.1f}%  {'MEGLIO' if skill>0 else 'peggio'}"
        print(f"{name:22} {m:8.0f}  {mp:6.1f}%{tag}")

    # quota di celle in cui ogni modello batte la naive
    print("\nQuota celle in cui il modello batte la naive:")
    for name, pred in res.items():
        if name.startswith("Naive"):
            continue
        te2 = te.assign(pred=pred, nv=te["lag_12"].to_numpy())
        wins = te2.groupby("cell").apply(
            lambda x: mae(x["presenze"].to_numpy(), x["pred"].to_numpy())
            < mae(x["presenze"].to_numpy(), x["nv"].to_numpy()), include_groups=False)
        print(f"  {name:22} {int(wins.sum())}/{len(wins)} celle")

    # feature importance (Random Forest)
    imp = pd.Series(rf.feature_importances_, index=Xcols).sort_values(ascending=False)
    print("\nFeature importance (Random Forest, top 12):")
    for k, v in imp.head(12).items():
        print(f"  {v*100:5.1f}%  {k}")


if __name__ == "__main__":
    main()
