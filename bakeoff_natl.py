"""
Bake-off NAZIONALE per-paese (Banca d'Italia TS1-N-S: notti per paese di origine,
trimestrale) + variabili economiche PER PAESE (cambio ECB, fiducia Eurostat).

Domanda: a livello per-paese (dove le economiche mappano 1:1), battono la naive
stagionale e guadagnano importanza? Se sì la direzione "economiche" è validata.
"""
from __future__ import annotations

import re

import numpy as np
import openpyxl
import pandas as pd
from sklearn.ensemble import RandomForestRegressor, HistGradientBoostingRegressor
from sklearn.linear_model import LinearRegression

from tourism_wedge import real_sources as RS
import econ_sources as E

COLMAP = {4: "DE", 5: "FR", 6: "AT", 7: "ES", 9: "GB", 10: "CH", 11: "RU", 13: "US"}
KEEP = {"DE", "AT", "GB", "CH", "US", "FR", "ES"}
CUR = {"DE": "EUR", "AT": "EUR", "FR": "EUR", "ES": "EUR", "GB": "GBP", "CH": "CHF", "US": "USD"}


def parse_bdi_nights() -> pd.DataFrame:
    ws = openpyxl.load_workbook(".cache/bdi_turismo_ts.xlsx", read_only=True, data_only=True)["TS1-N-S"]
    rows = list(ws.iter_rows(values_only=True))
    recs, year = [], None
    for r in rows[11:127]:
        if r[0] is not None:
            year = int(r[0])
        m = re.match(r"\s*(\d)", str(r[1] or r[2] or ""))
        if not (year and m):
            continue
        q = int(m.group(1))
        date = pd.Timestamp(year, q * 3 - 2, 1)
        for col, code in COLMAP.items():
            if code in KEEP and r[col] is not None:
                recs.append((date, code, float(r[col])))
    return pd.DataFrame(recs, columns=["date", "country", "nights"])


def build() -> tuple[pd.DataFrame, list[str]]:
    pan = parse_bdi_nights()
    pan = pan[pan["date"] >= "2005-01-01"].copy()
    def to_q(s):
        return pd.to_datetime(s).dt.to_period("Q").dt.to_timestamp()
    # cambio trimestrale per valuta
    fxq = {}
    for cur in set(CUR.values()):
        m = RS.fetch_fx_monthly(cur, start="2005-01")
        m["q"] = to_q(m["date"])
        fxq[cur] = m.groupby("q")["fx"].mean()
    # fiducia trimestrale per paese (DE/AT disponibili)
    conf = E.build_confidence_panel(start="2005-01")   # colonne: date, mercato, confidence
    if not conf.empty:
        conf["q"] = to_q(conf["date"])
        confq = conf.groupby(["mercato", "q"])["confidence"].mean().reset_index()
        cmap = {(r["mercato"], r["q"]): r["confidence"] for _, r in confq.iterrows()}
    else:
        cmap = {}

    blocks = []
    for c, g in pan.groupby("country"):
        g = g.sort_values("date").copy()
        s = g["nights"]
        g["lag_4"] = s.shift(4)      # naive stagionale (anno prima)
        g["lag_1"] = s.shift(1)
        g["lag_8"] = s.shift(8)
        g["roll4"] = s.shift(1).rolling(4).mean()
        g["fx"] = g["date"].map(fxq[CUR[c]])
        g["conf"] = [cmap.get((c, d), np.nan) for d in g["date"]]
        blocks.append(g)
    df = pd.concat(blocks, ignore_index=True)
    df["t"] = (df["date"].dt.year - 2005) * 4 + (df["date"].dt.quarter - 1)
    df["quarter"] = df["date"].dt.quarter
    df["covid"] = ((df["date"] >= "2020-03-01") & (df["date"] <= "2021-09-01")).astype(int)
    cat = pd.get_dummies(df[["country", "quarter"]], columns=["country", "quarter"], dtype=float)
    df = pd.concat([df, cat], axis=1)
    NUM = ["lag_4", "lag_1", "lag_8", "roll4", "fx", "conf", "t", "covid"]
    return df, NUM + list(cat.columns)


def mae(a, p):
    m = ~(np.isnan(a) | np.isnan(p)); return float(np.mean(np.abs(a[m] - p[m])))


def main():
    df, Xcols = build()
    NUM = ["lag_4", "lag_1", "lag_8", "roll4", "fx", "conf", "t", "covid"]
    df[NUM] = df[NUM].replace([np.inf, -np.inf], np.nan)
    # gli alberi tollerano NaN in conf; per lineare riempio conf con la media
    df = df.dropna(subset=["lag_4", "lag_8", "roll4", "fx", "nights"]).reset_index(drop=True)
    tr = df[df["date"] <= "2022-10-01"]
    te = df[df["date"] >= "2023-01-01"]
    print(f"train {len(tr)} | test {len(te)} | paesi {sorted(df['country'].unique())} | "
          f"periodo {df['date'].min():%Y-%m}->{df['date'].max():%Y-%m}")
    yte = te["nights"].to_numpy()

    res = {"Naive stagionale": te["lag_4"].to_numpy()}
    rf = RandomForestRegressor(n_estimators=500, min_samples_leaf=2, n_jobs=-1, random_state=0)
    rf.fit(tr[Xcols], tr["nights"]); res["Random Forest"] = rf.predict(te[Xcols])
    gb = HistGradientBoostingRegressor(max_iter=500, learning_rate=0.05, random_state=0)
    gb.fit(tr[Xcols], tr["nights"]); res["Gradient Boosting"] = gb.predict(te[Xcols])
    Xlin = [c for c in Xcols if c != "conf"]            # lineare: evito i NaN di conf
    lin = LinearRegression().fit(tr[Xlin], tr["nights"]); res["Lineare"] = lin.predict(te[Xlin])

    base = mae(yte, res["Naive stagionale"])
    print("\nMODELLO                 MAE     skill vs naive")
    for n, p in res.items():
        m = mae(yte, p); sk = (1 - m / base) * 100
        print(f"{n:22} {m:8.0f}" + ("   (baseline)" if "Naive" in n else f"   {sk:+5.1f}%  {'MEGLIO' if sk>0 else 'peggio'}"))

    print("\nQuota paesi in cui il modello batte la naive (Random Forest):")
    te2 = te.assign(pred=res["Random Forest"], nv=te["lag_4"].to_numpy())
    w = te2.groupby("country").apply(
        lambda x: mae(x["nights"].to_numpy(), x["pred"].to_numpy())
        < mae(x["nights"].to_numpy(), x["nv"].to_numpy()), include_groups=False)
    print("  ", {k: bool(v) for k, v in w.items()}, f"-> {int(w.sum())}/{len(w)}")

    imp = pd.Series(rf.feature_importances_, index=Xcols).sort_values(ascending=False)
    print("\nFeature importance (Random Forest, top 10):")
    for k, v in imp.head(10).items():
        print(f"  {v*100:5.1f}%  {k}")
    print(f"  [economiche]  fx={imp.get('fx',0)*100:.1f}%  conf={imp.get('conf',0)*100:.1f}%")


if __name__ == "__main__":
    try:
        import truststore; truststore.inject_into_ssl()
    except Exception:  # noqa: BLE001
        pass
    main()
