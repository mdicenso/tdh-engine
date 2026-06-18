"""
Libreria condivisa del cruscotto multi-pagina TDH Engine.

Contiene: calcolo dati (sintetico/reale, in cache), costruttori di grafici Plotly,
allocatore di budget, KPI, e il componente assistente Claude (chat con tool).
Le pagine (app.py) usano queste funzioni; la logica del motore resta in tourism_wedge/.
"""
from __future__ import annotations

import datetime
import glob
import io
import json
import math
import os
import time
from dataclasses import asdict

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from tourism_wedge import (DEFAULT_MARKETS, SyntheticProvider,
                           fit_market, forecast_within_lead, build_card, portfolio)
from tourism_wedge.engine_aggregate import (assemble_real, fit_aggregate,
                                            forecast_aggregate, rank_markets)
from tourism_wedge import candidate_sources as CS
from tourism_wedge import real_sources as RS
import regions as RG

MODEL = "claude-sonnet-4-6"
MODE_SYN = "🧪 Sintetico (collaudo)"
MODE_REAL = "🌍 Reale (ECB · ISTAT · Google Trends)"

# geografia per la mappa
CENTROID = {"DE": (51.2, 10.4), "AT": (47.6, 14.1), "GB": (54.0, -2.0),
            "NL": (52.1, 5.3), "CH": (46.8, 8.2), "US": (39.5, -98.5)}
ABRUZZO = (42.35, 13.4)
MONTHS_IT = ["Gen", "Feb", "Mar", "Apr", "Mag", "Giu", "Lug", "Ago", "Set", "Ott", "Nov", "Dic"]


def reco_color(reco: str) -> str:
    if reco.startswith("Aumentare"):
        return "#16a34a"
    if reco.startswith("Ridurre"):
        return "#dc2626"
    if reco.startswith("Monitorare"):
        return "#f59e0b"
    return "#2563eb"


def reco_cat(reco: str) -> str:
    for k in ("Aumentare", "Ridurre", "Monitorare"):
        if reco.startswith(k):
            return k
    return "Mantenere"


# ════════════════════════════════════════════════════════════════════════════
# STILE / UI (direzione A — moderno/pulito; CSS puro, a prova di proxy)
# ════════════════════════════════════════════════════════════════════════════
FONT_STACK = "-apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"
CSS = f"""<style>
  html, body, [class*="css"] {{ font-family: {FONT_STACK}; }}
  .block-container {{ padding-top: 2.8rem; max-width: 1320px; }}
  h1, h2, h3 {{ color: #0f172a; font-weight: 700; letter-spacing: -0.01em; }}
  .stApp {{ background-color: #f1f5f9; }}
  /* sidebar scura (schiarita per leggibilità) */
  [data-testid="stSidebar"] {{ background-color: #334155; border-right: 1px solid #1e293b; }}
  [data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3,
  [data-testid="stSidebar"] p, [data-testid="stSidebar"] label,
  [data-testid="stSidebar"] [data-testid="stCaptionContainer"],
  [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] {{ color: #f1f5f9 !important; }}
  /* voci di navigazione (link + icone): chiare e leggibili */
  [data-testid="stSidebarNav"] a, [data-testid="stSidebarNav"] a span,
  [data-testid="stSidebarNav"] a p {{ color: #f1f5f9 !important; opacity: 1 !important; }}
  [data-testid="stSidebarNav"] span[data-testid="stIconMaterial"] {{ color: #f1f5f9 !important; opacity: 1 !important; }}
  [data-testid="stSidebarNav"] a:hover {{ background: rgba(94,234,212,.12); }}
  [data-testid="stSidebarNav"] a:hover span, [data-testid="stSidebarNav"] a:hover p {{ color: #5eead4 !important; }}
  [data-testid="stSidebarNav"] a[aria-current="page"] {{ background: rgba(94,234,212,.16); border-radius: 8px; }}
  [data-testid="stSidebarNav"] a[aria-current="page"] span, [data-testid="stSidebarNav"] a[aria-current="page"] p {{ color: #5eead4 !important; font-weight: 600; }}
  /* etichette dei gruppi (Cosa è successo, ...) ben visibili */
  [data-testid="stSidebarNav"] [class*="nav-section"], [data-testid="stSidebarNav"] summary {{ color: #cbd5e1 !important; }}
  [data-testid="stSidebar"] .stButton > button {{ background: #475569; border: 1px solid #64748b; color: #f1f5f9; }}
  [data-testid="stSidebar"] .stButton > button:hover {{ border-color: #5eead4; color: #5eead4; }}
  /* metric -> card */
  [data-testid="stMetric"] {{ background: #ffffff; border: 1px solid #e5e7eb; border-radius: 14px;
       padding: 14px 16px; box-shadow: 0 1px 3px rgba(15,23,42,.06); }}
  [data-testid="stMetricLabel"] {{ color: #64748b; font-weight: 600; }}
  /* tabelle e pulsanti */
  [data-testid="stDataFrame"] {{ border-radius: 10px; overflow: hidden; }}
  .stButton > button {{ border-radius: 10px; border: 1px solid #e2e8f0; font-weight: 500; }}
  .stButton > button:hover {{ border-color: #0e7490; color: #0e7490; }}
  /* expander */
  [data-testid="stExpander"] {{ border-radius: 12px; border: 1px solid #e5e7eb; }}
</style>"""


def inject_css():
    st.markdown(CSS, unsafe_allow_html=True)


def check_access() -> bool:
    """Gate d'accesso leggero. Attivo solo se esiste il secret APP_PASSWORD
    (Streamlit Cloud → Settings → Secrets). Senza secret non blocca nulla.
    Ritorna True se l'utente può procedere."""
    try:
        pwd = st.secrets.get("APP_PASSWORD")
    except Exception:  # noqa: BLE001 — nessun file secrets in locale
        pwd = None
    if not pwd:
        return True
    if st.session_state.get("_auth_ok"):
        return True

    _, c, _ = st.columns([1, 1.4, 1])
    with c:
        st.markdown(LOGO_SVG, unsafe_allow_html=True)
        st.markdown("#### Turism Data Hub — accesso riservato")
        st.caption("Prototipo Indra · accesso riservato. Inserisci la password ricevuta.")
        entered = st.text_input("Password", type="password", label_visibility="collapsed",
                                placeholder="Password")
        if st.button("Entra", type="primary", use_container_width=True):
            if entered == pwd:
                st.session_state["_auth_ok"] = True
                st.rerun()
            else:
                st.error("Password non corretta.")
    return False


def hero(subtitle: str = "", mode_label: str = ""):
    chip = (f"<span style='background:rgba(255,255,255,.18);padding:3px 12px;border-radius:999px;"
            f"font-size:.8rem;font-weight:600'>{mode_label}</span>") if mode_label else ""
    st.markdown(f"""
    <div style="background:linear-gradient(120deg,#0e7490 0%,#0891b2 55%,#06b6d4 100%);
                border-radius:16px;padding:34px 26px 22px;margin:10px 0 18px;color:#fff;
                box-shadow:0 6px 18px rgba(8,145,178,.25);display:flex;align-items:center;
                justify-content:space-between;flex-wrap:wrap;gap:8px;overflow:visible">
      <div>
        <div style="font-size:.72rem;letter-spacing:.08em;opacity:.85;font-weight:600;line-height:1.5">
             STRUMENTO AD USO INTERNO · SCALA NAZIONALE</div>
        <div style="font-size:1.5rem;font-weight:800;letter-spacing:.01em;margin-top:2px">⛰️ Turism Data Hub</div>
        <div style="opacity:.92;font-size:.92rem;margin-top:2px">{subtitle}</div>
      </div>{chip}
    </div>""", unsafe_allow_html=True)


def badge_html(reco: str) -> str:
    c = reco_color(reco)
    return (f"<span style='background:{c}1f;color:{c};padding:3px 11px;border-radius:999px;"
            f"font-size:.8rem;font-weight:600;white-space:nowrap'>{reco_cat(reco)}</span>")


def _reco_css(val: str) -> str:
    return f"color:{reco_color(str(val))}; font-weight:600;"


def style_reco(df, col: str = "Raccomandazione"):
    """Styler che colora la colonna Raccomandazione come un semaforo."""
    return df.style.map(_reco_css, subset=[col]) if col in df.columns else df


def aggrid_table(df, height: int = 320, reco_col: str | None = None, key: str | None = None):
    """Tabella interattiva (ordinabile/filtrabile) con st_aggrid; fallback a st.dataframe.
    Se reco_col è indicato, colora quella colonna come semaforo della raccomandazione."""
    try:
        from st_aggrid import AgGrid, GridOptionsBuilder, JsCode
    except Exception:
        st.dataframe(df, hide_index=True, use_container_width=True)
        return
    gb = GridOptionsBuilder.from_dataframe(df)
    gb.configure_default_column(resizable=True, sortable=True, filter=True)
    if reco_col and reco_col in df.columns:
        js = JsCode("function(p){var v=String(p.value||'');var c='#2563eb';"
                    "if(v.indexOf('Aumentare')===0)c='#16a34a';"
                    "else if(v.indexOf('Ridurre')===0)c='#dc2626';"
                    "else if(v.indexOf('Monitorare')===0)c='#f59e0b';"
                    "return {color:c,fontWeight:'600'};}")
        gb.configure_column(reco_col, cellStyle=js)
    try:
        AgGrid(df, gridOptions=gb.build(), height=height, theme="streamlit",
               allow_unsafe_jscode=True, fit_columns_on_grid_load=True, key=key)
    except Exception:
        st.dataframe(df, hide_index=True, use_container_width=True)


# Logo "inventato" del Turism Data Hub: sole + montagne + lago con riflesso.
LOGO_SVG = """<svg width="54" height="54" viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
  <circle cx="44" cy="20" r="9" fill="#fbbf24"/>
  <path d="M4 44 L22 16 L34 34 L44 22 L60 44 Z" fill="#0e7490"/>
  <path d="M4 44 L22 16 L30 28 L20 44 Z" fill="#0c5566"/>
  <rect x="4" y="44" width="56" height="2.6" rx="1" fill="#7dd3fc"/>
  <path d="M11 49 H53 M17 53 H47" stroke="#bae6fd" stroke-width="1.6" stroke-linecap="round" opacity="0.75"/>
</svg>"""


@st.cache_data(show_spinner=False)
def home_hero_datauri() -> str | None:
    """Foto della homepage come data URI base64 (offline, niente CDN al render)."""
    import base64
    p = "assets/home_hero.jpg"
    if not os.path.exists(p):
        return None
    return "data:image/jpeg;base64," + base64.b64encode(open(p, "rb").read()).decode()


# ════════════════════════════════════════════════════════════════════════════
# DATI (in cache)
# ════════════════════════════════════════════════════════════════════════════
@st.cache_data(show_spinner="Calcolo il motore (sintetico)…")
def compute_synthetic() -> tuple[list[dict], dict]:
    provider = SyntheticProvider()
    cards, rows = [], {}
    for mk in DEFAULT_MARKETS:
        panel = provider.monthly_panel(mk)
        fit = fit_market(panel, mk)
        fc = forecast_within_lead(fit, mk)
        card = build_card(fit, fc, mk)
        cards.append(card)
        rows[mk.code] = {
            "code": mk.code, "name": mk.name, "currency": mk.currency,
            "spend_per_visitor": mk.spend_per_visitor, "capacity_ok": mk.capacity_ok,
            "card": asdict(card), "lag": int(fit.lag), "beats_naive": bool(fit.beats_naive),
            "mape_model": float(fit.mape_model), "coeff_reading": fit.coefficient_reading(),
            "history": fit.df[["date", "presences", "search", "fx"]].copy(),
            "forecast": {"dates": [pd.Timestamp(d) for d in fc.dates],
                         "mean": [float(x) for x in fc.mean], "lo": [float(x) for x in fc.lo],
                         "hi": [float(x) for x in fc.hi],
                         "lastyear": [None if pd.isna(x) else float(x) for x in fc.lastyear]},
        }
    return portfolio(cards), rows


@st.cache_data(show_spinner="Carico i dati reali (ECB · ISTAT · Google Trends)…")
def compute_real() -> dict:
    df = assemble_real(start="2019-01")
    fit = fit_aggregate(df)
    fc = forecast_aggregate(fit)
    ranked = rank_markets(df, value_override=bdi_spend_per_market() or None,
                          feas_override=feas_weights() or None)
    obs = df.dropna(subset=["presences"])[["date", "presences"]].reset_index(drop=True)
    return {
        "ranked": ranked,
        "agg": {"lag": int(fit.lag), "beats_naive": bool(fit.beats_naive),
                "mape_model": float(fit.mape_model), "coeff_reading": fit.coefficient_reading()},
        "forecast": {"dates": [pd.Timestamp(d) for d in fc.dates],
                     "mean": [float(x) for x in fc.mean], "lo": [float(x) for x in fc.lo],
                     "hi": [float(x) for x in fc.hi],
                     "lastyear": [None if pd.isna(x) else float(x) for x in fc.lastyear]},
        "history": obs, "panel": df,
    }


# --- Banca d'Italia: valore economico reale (spesa €/viaggiatore per mercato) ---
@st.cache_data(show_spinner=False)
def bdi_spend_per_market() -> dict:
    p = ".cache/bdi_spend_per_market.csv"
    if not os.path.exists(p):
        return {}
    df = pd.read_csv(p)
    return {str(r["code"]): float(r["eur_per_viaggiatore"])
            for _, r in df.iterrows() if pd.notna(r["eur_per_viaggiatore"])}


@st.cache_data(show_spinner=False)
def bdi_abruzzo_spend():
    p = ".cache/bdi_abruzzo.json"
    if not os.path.exists(p):
        return None
    return json.load(open(p, encoding="utf-8")).get("abruzzo_spesa_M_2024")


# --- Banca d'Italia per PAESE di origine (nazionale, trimestrale 1997-2025) ---
_BDI_COLMAP = {4: "DE", 5: "FR", 6: "AT", 7: "ES", 9: "GB", 10: "CH", 11: "RU", 13: "US"}
_BDI_SHEETS = {"notti": "TS1-N-S", "spesa": "TS1-S-S", "viaggiatori": "TS1-V-S"}
BDI_MARKETS = ["DE", "AT", "GB", "CH", "US", "FR", "ES"]


@st.cache_data(show_spinner=False)
def bdi_country_long():
    """Flussi nazionali BdI per paese di origine: DataFrame date·code·notti·spesa·viaggiatori
    (trimestrale). Sorgente: fogli TS1 dell'xlsx BdI. None se il file manca."""
    import re
    p = ".cache/bdi_turismo_ts.xlsx"
    if not os.path.exists(p):
        return None
    import openpyxl
    wb = openpyxl.load_workbook(p, read_only=True, data_only=True)
    recs = []
    for metric, sheet in _BDI_SHEETS.items():
        rows = list(wb[sheet].iter_rows(values_only=True))
        h = next((i for i, r in enumerate(rows) if r and any(c == "Germania" for c in r if c)), None)
        if h is None:
            continue
        year = None
        for r in rows[h + 1:]:
            if r[0] is not None:
                year = int(r[0])
            m = re.match(r"\s*(\d)", str(r[1] or r[2] or ""))
            if not (year and m):
                continue
            q = int(m.group(1))
            date = pd.Timestamp(year, q * 3 - 2, 1)
            for col, code in _BDI_COLMAP.items():
                if col < len(r) and r[col] is not None:
                    recs.append((date, code, metric, float(r[col])))
    if not recs:
        return None
    df = pd.DataFrame(recs, columns=["date", "code", "metric", "value"])
    return df.pivot_table(index=["date", "code"], columns="metric", values="value").reset_index()


def bdi_country_annual():
    """Aggregato ANNUALE per paese (notti/viaggiatori = somma, spesa = somma). Per le viste descrittive."""
    df = bdi_country_long()
    if df is None or df.empty:
        return None
    df = df.copy(); df["anno"] = df["date"].dt.year
    g = df.groupby(["anno", "code"]).agg(
        notti=("notti", "sum"), spesa=("spesa", "sum"), viaggiatori=("viaggiatori", "sum")).reset_index()
    return g[g["code"].isin(BDI_MARKETS)]


def chart_bdi_country(metric: str = "notti") -> go.Figure | None:
    g = bdi_country_annual()
    if g is None or g.empty:
        return None
    names = {mk.code: mk.name for mk in DEFAULT_MARKETS}
    fig = go.Figure()
    for code in BDI_MARKETS:
        d = g[g["code"] == code].sort_values("anno")
        if not d.empty:
            fig.add_trace(go.Scatter(x=d["anno"], y=d[metric], name=names.get(code, code),
                                     mode="lines+markers"))
    fig.update_yaxes(title=metric)
    return _layout(fig, h=380)


def chart_value_bar(summary: list[dict]) -> go.Figure:
    s = sorted([x for x in summary if x.get("valore")], key=lambda x: x["valore"])
    fig = go.Figure(go.Bar(x=[x["valore"] for x in s], y=[x["market"] for x in s], orientation="h",
                           marker_color="#0e7490",
                           hovertemplate="<b>%{y}</b><br>%{x:,.0f} €/viaggiatore<extra></extra>"))
    fig.update_layout(xaxis_title="spesa €/viaggiatore")
    return _layout(fig, h=300)


# --- Eurostat avia_par: connettività aerea diretta su Pescara (fattibilità reale) ---
@st.cache_data(show_spinner=False)
def pescara_connectivity() -> dict:
    p = ".cache/eurostat_pescara_flights.csv"
    if not os.path.exists(p):
        return {}
    df = pd.read_csv(p)
    return {str(r["code"]): int(r["pax"]) for _, r in df.iterrows()}


def feas_weights() -> dict:
    """Peso di fattibilità 0.4..1.0 dalla connettività voli (0 voli → 0.4; più connesso → 1.0)."""
    pax = pescara_connectivity()
    if not pax:
        return {}
    mx = max(pax.values()) or 1
    return {k: round(0.4 + 0.6 * min(v / mx, 1.0), 3) for k, v in pax.items()}


def chart_connectivity():
    pax = pescara_connectivity()
    if not pax:
        return None
    names = {mk.code: mk.name for mk in DEFAULT_MARKETS}
    items = sorted(pax.items(), key=lambda x: x[1])
    fig = go.Figure(go.Bar(x=[v for _, v in items], y=[names.get(k, k) for k, _ in items], orientation="h",
                           marker_color=["#16a34a" if v > 0 else "#cbd5e1" for _, v in items],
                           hovertemplate="<b>%{y}</b><br>%{x:,.0f} passeggeri 2024<extra></extra>"))
    fig.update_xaxes(title="passeggeri diretti su Pescara (2024)")
    return _layout(fig, h=260)


# --- Salute mercato (fiducia consumatori) e accessibilità nel tempo (voli Pescara) ---
# Criteri DECISIONALI di contesto (non predittori del forecast: vedi bake-off).
HEALTH_GEO = {"DE": "DE", "AT": "AT", "NL": "NL"}   # fiducia disponibile (Eurostat)


@st.cache_data(show_spinner=False)
def market_health() -> dict:
    """Trend della fiducia dei consumatori per mercato: {code: {conf, delta, label, series}}.
    Disponibile per DE/AT/NL; per gli altri mercati non c'è dato Eurostat."""
    out = {}
    for code, geo in HEALTH_GEO.items():
        p = f".cache/econ_confidence_{geo}.csv"
        if not os.path.exists(p):
            continue
        df = pd.read_csv(p, parse_dates=["date"]).sort_values("date")
        if df.empty:
            continue
        s = df["confidence"].astype(float)
        latest = float(s.iloc[-1])
        prev = float(s.iloc[-7]) if len(s) >= 7 else float(s.iloc[0])   # ~6 mesi prima
        delta = latest - prev
        label = "📈 in ripresa" if delta >= 3 else "📉 in calo" if delta <= -3 else "➡️ stabile"
        out[code] = {"conf": round(latest, 1), "delta": round(delta, 1), "label": label,
                     "series": df[["date", "confidence"]]}
    return out


@st.cache_data(show_spinner=False)
def flights_monthly_df():
    p = ".cache/econ_flights_pescara_monthly.csv"
    return pd.read_csv(p, parse_dates=["date"]).sort_values("date") if os.path.exists(p) else None


def chart_flights_monthly():
    df = flights_monthly_df()
    if df is None or df.empty:
        return None
    df = df.copy(); df["roll12"] = df["pax"].rolling(12).mean()
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df["date"], y=df["pax"], name="passeggeri/mese",
                             line=dict(color="#cbd5e1", width=1)))
    fig.add_trace(go.Scatter(x=df["date"], y=df["roll12"], name="media 12 mesi",
                             line=dict(color="#0e7490", width=3)))
    fig.update_yaxes(title="passeggeri Pescara")
    return _layout(fig, h=280)


def chart_confidence(health: dict):
    """Mini-serie della fiducia per i mercati con dato."""
    if not health:
        return None
    fig = go.Figure()
    for code, h in health.items():
        s = h["series"]
        fig.add_trace(go.Scatter(x=s["date"], y=s["confidence"], name=code, mode="lines"))
    fig.update_yaxes(title="fiducia (saldo)")
    return _layout(fig, h=260)


# --- Wikipedia pageviews: secondo segnale anticipatore (per LINGUA, corroborazione) ---
WIKI_LANG = {"DE": "de", "AT": "de", "CH": "de", "GB": "en", "US": "en", "NL": "nl"}
WIKI_LABEL = {"de": "Tedesco (DE/AT/CH)", "en": "Inglese (GB/US)", "nl": "Olandese (NL)",
              "it": "Italiano (domestico)"}


@st.cache_data(show_spinner=False)
def wiki_series(lang: str):
    p = f".cache/wiki_{lang}.csv"
    if not os.path.exists(p):
        return None
    df = pd.read_csv(p, parse_dates=["date"])
    today = pd.Timestamp.today()
    cutoff = pd.Timestamp(today.year, today.month, 1)  # scarta il mese corrente (incompleto)
    return df[df["date"] < cutoff].reset_index(drop=True)


def wiki_momentum(lang: str):
    df = wiki_series(lang)
    if df is None or df.empty:
        return None
    s = df.sort_values("date")["views"]
    recent = s.tail(3).mean()
    yoy = s.tail(15).head(3).mean() if len(s) >= 15 else None
    return round((recent - yoy) / yoy * 100, 1) if (yoy and yoy != 0) else None


def online_interest(summary: list[dict]) -> list[dict]:
    out = []
    for m in summary:
        lang = WIKI_LANG.get(m["code"])
        wmom = wiki_momentum(lang)
        tmom = m.get("momentum")
        conc = "—"
        if tmom is not None and wmom is not None:
            conc = "✓ concorde" if (tmom >= 0) == (wmom >= 0) else "✗ discorde"
        out.append({"Mercato": m["market"], "Wikipedia": WIKI_LABEL.get(lang, lang or "—"),
                    "Trends mom %": (round(tmom) if tmom is not None else None),
                    "Wikipedia mom %": wmom, "Concordanza": conc})
    return out


def chart_wiki(yr_range=None) -> go.Figure:
    colors = {"de": "#0e7490", "en": "#f59e0b", "nl": "#16a34a"}
    fig = go.Figure()
    for lang in ["de", "en", "nl"]:
        df = wiki_series(lang)
        if df is None:
            continue
        if yr_range:
            df = df[(df["date"].dt.year >= yr_range[0]) & (df["date"].dt.year <= yr_range[1])]
        fig.add_trace(go.Scatter(x=df["date"], y=df["views"], name=WIKI_LABEL[lang],
                                 line=dict(color=colors[lang], width=2)))
    fig.update_yaxes(title="visualizzazioni pagina (per lingua)")
    return _layout(fig, h=360)


def get_context() -> dict:
    """Ritorna il contesto della modalità corrente (dati + ctx per i tool)."""
    mode = st.session_state.get("mode", MODE_REAL)
    if MODE_REAL in mode or "Reale" in mode:
        R = compute_real()
        return {"mode": "real", "R": R}
    ranked, rows = compute_synthetic()
    return {"mode": "synthetic", "ranked": ranked, "rows": rows}


def markets_summary(ctx: dict) -> list[dict]:
    """Lista normalizzata per grafici/mappa: code, market, reco, score, forza, momentum, valore, capacity_ok, rank."""
    if ctx["mode"] == "real":
        return [{"code": c["code"], "market": c["market"], "reco": c["raccomandazione"],
                 "score": c["score"], "forza": c["forza_anticipatrice"],
                 "momentum": c["momentum_search_pct"], "valore": c["valore_eur_per_visitatore"],
                 "capacity_ok": c["capacita_voli_ok"], "rank": c["rank"]} for c in ctx["R"]["ranked"]]
    rows = ctx["rows"]; name2code = {r["name"]: c for c, r in rows.items()}
    out = []
    for r in ctx["ranked"]:
        code = name2code.get(r["market"]); rr = rows.get(code, {})
        out.append({"code": code, "market": r["market"], "reco": r["raccomandazione"],
                    "score": r["opportunity_score"], "forza": None, "momentum": None,
                    "valore": rr.get("spend_per_visitor"), "capacity_ok": rr.get("capacity_ok"),
                    "rank": r["rank"]})
    return out


# ════════════════════════════════════════════════════════════════════════════
# GRAFICI PLOTLY
# ════════════════════════════════════════════════════════════════════════════
def _layout(fig: go.Figure, h: int = 420, title: str | None = None) -> go.Figure:
    fig.update_layout(height=h, margin=dict(l=10, r=10, t=44 if title else 12, b=10),
                      paper_bgcolor="white", plot_bgcolor="white", title=(title or ""),
                      font=dict(family=FONT_STACK, size=13, color="#334155"),
                      colorway=["#0e7490", "#f59e0b", "#16a34a", "#7c3aed", "#dc2626", "#0891b2"],
                      legend=dict(orientation="h", y=-0.18, font=dict(size=12)),
                      hoverlabel=dict(bgcolor="white", bordercolor="#e5e7eb", font_size=12))
    fig.update_xaxes(showgrid=False, color="#64748b", linecolor="#e5e7eb")
    fig.update_yaxes(gridcolor="#eef2f7", color="#64748b", zeroline=False)
    return fig


def chart_map(summary: list[dict]) -> go.Figure:
    gj = json.load(open(".cache/world_countries.geojson", encoding="utf-8"))
    all_ids = [f.get("id") for f in gj["features"] if f.get("id")]
    max_s = max((s["score"] for s in summary), default=1) or 1
    fig = go.Figure()
    fig.add_trace(go.Choropleth(geojson=gj, featureidkey="id", locations=all_ids,
                                z=[0] * len(all_ids), colorscale=[[0, "#e6e8eb"], [1, "#e6e8eb"]],
                                showscale=False, marker_line_color="#fff", marker_line_width=0.4,
                                hoverinfo="skip"))
    lon_l, lat_l = [], []
    for s in summary:
        if s["code"] not in CENTROID:
            continue
        la, lo = CENTROID[s["code"]]; lon_l += [lo, ABRUZZO[1], None]; lat_l += [la, ABRUZZO[0], None]
    fig.add_trace(go.Scattergeo(lon=lon_l, lat=lat_l, mode="lines",
                                line=dict(width=0.8, color="rgba(120,120,120,0.4)"),
                                hoverinfo="skip", showlegend=False))
    by_cat: dict = {}
    for s in summary:
        by_cat.setdefault(reco_cat(s["reco"]), []).append(s)
    for cat, grp in by_cat.items():
        grp = [g for g in grp if g["code"] in CENTROID]
        if not grp:
            continue
        fig.add_trace(go.Scattergeo(
            lon=[CENTROID[g["code"]][1] for g in grp], lat=[CENTROID[g["code"]][0] for g in grp],
            mode="markers+text", text=[g["market"] for g in grp], textposition="top center",
            textfont=dict(size=11, color="#111827"),
            marker=dict(size=[14 + 44 * math.sqrt(max(g["score"], 1) / max_s) for g in grp],
                        color=reco_color(grp[0]["reco"]), opacity=0.85, line=dict(width=1.2, color="white")),
            name=cat,
            customdata=[[g["rank"], g["reco"], round(g["score"])] for g in grp],
            hovertemplate="<b>%{text}</b><br>#%{customdata[0]} · %{customdata[1]}"
                          "<br>Score: %{customdata[2]:,}<extra></extra>"))
    fig.add_trace(go.Scattergeo(lon=[ABRUZZO[1]], lat=[ABRUZZO[0]], mode="markers+text",
                                text=["ABRUZZO"], textposition="bottom center",
                                textfont=dict(size=12, color="#7c2d12"),
                                marker=dict(size=16, color="#7c2d12", symbol="star"),
                                name="Destinazione", hoverinfo="text"))
    fig.update_layout(height=560, margin=dict(l=0, r=0, t=10, b=0), paper_bgcolor="white", title_text="",
                      legend=dict(title="Raccomandazione", orientation="h", y=-0.02, x=0.02),
                      geo=dict(projection_type="natural earth", showland=False, showcountries=False,
                               showcoastlines=False, showframe=False, showocean=True, oceancolor="#eaf2fb",
                               bgcolor="rgba(0,0,0,0)", lataxis_range=[22, 66], lonaxis_range=[-120, 32]))
    return fig


def chart_ranking_bar(summary: list[dict]) -> go.Figure:
    s = sorted(summary, key=lambda x: x["score"])  # crescente -> #1 in alto
    fig = go.Figure(go.Bar(
        x=[x["score"] for x in s], y=[x["market"] for x in s], orientation="h",
        marker_color=[reco_color(x["reco"]) for x in s],
        customdata=[[x["reco"], x["rank"]] for x in s],
        hovertemplate="<b>%{y}</b><br>#%{customdata[1]} · %{customdata[0]}<br>Score: %{x:,.0f}<extra></extra>"))
    fig.update_layout(xaxis_title="Score (opportunità)")
    return _layout(fig, h=360)


def chart_forecast(history: pd.DataFrame, fc: dict, ylabel: str = "presenze") -> go.Figure:
    hist = history.tail(24)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=fc["dates"], y=fc["hi"], line=dict(width=0), showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=fc["dates"], y=fc["lo"], fill="tonexty", fillcolor="rgba(245,158,11,0.18)",
                             line=dict(width=0), name="intervallo 80%", hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=hist["date"], y=hist[hist.columns[1]], name="storico",
                             line=dict(color="#2563eb", width=2)))
    fig.add_trace(go.Scatter(x=fc["dates"], y=fc["mean"], name="forecast",
                             line=dict(color="#f59e0b", width=2), mode="lines+markers"))
    ref_x = [d for d, v in zip(fc["dates"], fc["lastyear"]) if v is not None]
    ref_y = [v for v in fc["lastyear"] if v is not None]
    if ref_y:
        fig.add_trace(go.Scatter(x=ref_x, y=ref_y, name="anno prima", mode="markers",
                                 marker=dict(color="#16a34a", size=9)))
    fig.update_yaxes(title=ylabel)
    return _layout(fig, h=380)


def chart_search(panel: pd.DataFrame, code: str) -> go.Figure:
    col = f"search_{code}"
    d = panel[["date", col]].dropna()
    fig = go.Figure(go.Scatter(x=d["date"], y=d[col], line=dict(color="#7c3aed", width=2),
                               name="interesse di ricerca"))
    fig.update_yaxes(title="interesse di ricerca (0–100)")
    return _layout(fig, h=300)


def chart_seasonal_heatmap(panel: pd.DataFrame, summary: list[dict]) -> go.Figure:
    """Heatmap mese×mercato del profilo stagionale di ricerca (normalizzato per riga):
    mostra QUANDO l'interesse di ogni mercato è al massimo (timing campagne)."""
    order = [s["code"] for s in summary if f"search_{s['code']}" in panel.columns]
    names = {s["code"]: s["market"] for s in summary}
    d = panel.copy(); d["m"] = d["date"].dt.month
    z, ytxt = [], []
    for code in order:
        prof = d.groupby("m")[f"search_{code}"].mean().reindex(range(1, 13))
        mn, mx = prof.min(), prof.max()
        norm = (prof - mn) / (mx - mn) if mx > mn else prof * 0
        z.append(norm.tolist()); ytxt.append(names[code])
    fig = go.Figure(go.Heatmap(z=z, x=MONTHS_IT, y=ytxt, colorscale="YlOrRd",
                               colorbar=dict(title="interesse<br>(per mercato)"),
                               hovertemplate="%{y} · %{x}<br>intensità %{z:.0%}<extra></extra>"))
    return _layout(fig, h=320)


# ════════════════════════════════════════════════════════════════════════════
# ALLOCATORE BUDGET
# ════════════════════════════════════════════════════════════════════════════
def allocate_budget(summary: list[dict], total: float, categorie: set[str]) -> list[dict]:
    """Ripartisce il budget proporzionalmente allo score, tra i mercati la cui categoria
    di raccomandazione è in `categorie`. I mercati esclusi/score<=0 ricevono 0."""
    elig = [s for s in summary if reco_cat(s["reco"]) in categorie and s["score"] > 0]
    tot_w = sum(s["score"] for s in elig) or 1
    out = []
    for s in summary:
        w = s["score"] if s in elig else 0
        quota = total * w / tot_w if w > 0 else 0.0
        out.append({**s, "quota_eur": quota, "quota_pct": (w / tot_w * 100 if w > 0 else 0.0)})
    return sorted(out, key=lambda x: x["quota_eur"], reverse=True)


def chart_allocation(alloc: list[dict]) -> go.Figure:
    a = [x for x in alloc if x["quota_eur"] > 0]
    fig = go.Figure(go.Bar(x=[x["quota_eur"] for x in a][::-1], y=[x["market"] for x in a][::-1],
                           orientation="h", marker_color=[reco_color(x["reco"]) for x in a][::-1],
                           customdata=[[x["quota_pct"]] for x in a][::-1],
                           hovertemplate="<b>%{y}</b><br>€ %{x:,.0f} (%{customdata[0]:.0f}%)<extra></extra>"))
    fig.update_layout(xaxis_title="budget allocato (€)")
    return _layout(fig, h=340)


# ════════════════════════════════════════════════════════════════════════════
# KPI (modalità reale)
# ════════════════════════════════════════════════════════════════════════════
def kpi_real(R: dict) -> dict:
    h = R["history"].sort_values("date")
    last12 = h.tail(12)["presences"].sum()
    prev12 = h.tail(24).head(12)["presences"].sum()
    yoy = (last12 - prev12) / prev12 * 100 if prev12 else float("nan")
    top = R["ranked"][0]["market"] if R["ranked"] else "—"
    anno = h["date"].max().year if not h.empty else "—"
    return {"presenze_anno": last12, "anno": anno, "yoy": yoy, "top": top,
            "n_aumentare": sum(1 for c in R["ranked"] if c["raccomandazione"].startswith("Aumentare"))}


# ════════════════════════════════════════════════════════════════════════════
# ASSISTENTE (chat con tool, mode-aware)
# ════════════════════════════════════════════════════════════════════════════
def _name_match(items, key, getname, getcode):
    key = (key or "").strip().lower()
    return next((x for x in items if key in (str(getcode(x)).lower(), getname(x).lower())), None)


def run_tool(name, args, ctx) -> str:
    if ctx["mode"] == "real":
        R = ctx["R"]
        if name == "run_engine":
            agg = R["agg"]
            return json.dumps({"ranking": [
                {"rank": c["rank"], "mercato": c["market"], "raccomandazione": c["raccomandazione"],
                 "forza_anticipatrice": c["forza_anticipatrice"], "momentum_search_pct": c["momentum_search_pct"],
                 "score": c["score"]} for c in R["ranked"]],
                "forecast_aggregato": {"lag_mesi": agg["lag"], "batte_naive": agg["beats_naive"],
                "mape_pct": round(agg["mape_model"], 1),
                "nota": "A livello aggregato la stagionalità domina: il modello NON batte la naive; "
                        "per il numero ci si appoggia al riferimento stagionale. Il valore è nel ranking."}},
                ensure_ascii=False)
        if name == "get_market":
            c = _name_match(R["ranked"], args.get("market", ""), lambda x: x["market"], lambda x: x["code"])
            if not c:
                return json.dumps({"errore": "mercato non trovato",
                                   "validi": [x["market"] for x in R["ranked"]]}, ensure_ascii=False)
            return json.dumps({"mercato": c["market"], "rank": c["rank"], "raccomandazione": c["raccomandazione"],
                "forza_anticipatrice": c["forza_anticipatrice"], "lag_mesi": c["lag_mesi"],
                "momentum_search_pct": c["momentum_search_pct"], "search_recente": c["search_recente"],
                "valore_eur_per_visitatore": c["valore_eur_per_visitatore"],
                "capacita_voli_ok": c["capacita_voli_ok"], "score": c["score"]}, ensure_ascii=False)
        if name == "explain_coefficients":
            return json.dumps({"modello": "presenze straniere totali Abruzzo ~ basket search (lag) + "
                "stagionalità + trend + dummy COVID", "lag_mesi": R["agg"]["lag"],
                "batte_naive": R["agg"]["beats_naive"], "mape_pct": round(R["agg"]["mape_model"], 1),
                "lettura_coefficienti": R["agg"]["coeff_reading"]}, ensure_ascii=False)
    else:
        rows, ranked = ctx["rows"], ctx["ranked"]
        if name == "run_engine":
            return json.dumps({"ranking": [
                {"rank": r["rank"], "mercato": r["market"], "raccomandazione": r["raccomandazione"],
                 "opportunity_score": round(r["opportunity_score"]), "confidenza": r["confidenza"]}
                for r in ranked]}, ensure_ascii=False)
        if name in ("get_market", "explain_coefficients"):
            code = _name_match(list(rows.values()), args.get("market", ""),
                               lambda r: r["name"], lambda r: r["code"])
            if not code:
                return json.dumps({"errore": "mercato non trovato",
                                   "validi": [r["name"] for r in rows.values()]}, ensure_ascii=False)
            if name == "get_market":
                return json.dumps({"mercato": code["name"], "scheda": code["card"]}, ensure_ascii=False)
            return json.dumps({"mercato": code["name"], "lag_mesi": code["lag"],
                "batte_naive": code["beats_naive"], "lettura_coefficienti": code["coeff_reading"]},
                ensure_ascii=False)
    return json.dumps({"errore": f"tool sconosciuto: {name}"}, ensure_ascii=False)


TOOLS_SCHEMA = [
    {"name": "run_engine", "description": "Ranking dei mercati + diagnostica del forecast. "
     "Per confronti tra mercati o ordinamento.",
     "input_schema": {"type": "object", "properties": {}, "required": []}},
    {"name": "get_market", "description": "Scheda di un singolo mercato (raccomandazione e numeri chiave).",
     "input_schema": {"type": "object", "properties": {"market": {"type": "string",
                      "description": "Nome o codice, es. 'Germania' o 'DE'."}}, "required": ["market"]}},
    {"name": "explain_coefficients", "description": "Lettura dei coefficienti del modello + backtest. "
     "Per il 'perché' o spiegare il modello.",
     "input_schema": {"type": "object", "properties": {"market": {"type": "string",
                      "description": "Opzionale: nome o codice del mercato."}}, "required": []}},
]

SYSTEM_BASE = ("Sei l'assistente del cruscotto del TDH Engine, che ordina i mercati esteri per allocare "
    "il budget promo turistico regionale. Confine SEMPRE: il motore NON stima l'effetto "
    "causale della spesa ('metti X€ → +Y presenze'); ordina 'dove conviene agire'. Usa SEMPRE i tool "
    "per i numeri (non a memoria); rispondi in italiano, conciso e orientato alla decisione; risposta "
    "finale diretta senza ragionamento visibile.")
SYSTEM_REAL = (" MODALITÀ REALE: un solo modello sulle presenze straniere totali (ISTAT, non per paese); a "
    "livello aggregato la stagionalità domina e NON batte la naive (per il numero si usa il riferimento "
    "stagionale). Il valore è nel RANKING per-mercato = forza anticipatrice (Google Trends) × momentum × "
    "valore economico (spesa €/viaggiatore Banca d'Italia) × fattibilità (voli diretti su Pescara, Eurostat). "
    "Wikipedia (per lingua) corrobora il segnale ma non entra nello score. Sii onesto su queste distinzioni.")
SYSTEM_SYN = (" MODALITÀ SINTETICA (dati di collaudo): modello per-mercato con barriera di onestà (forecast "
    "solo se batte la naive). Puoi dire che i dati sono sintetici.")


def system_prompt_for(ctx: dict) -> str:
    return SYSTEM_BASE + (SYSTEM_REAL if ctx["mode"] == "real" else SYSTEM_SYN)


def render_assistant(ctx: dict, height: int = 460):
    """Componente chat con Claude (streaming + tool sul motore)."""
    if "messages" not in st.session_state:
        st.session_state.messages = []
    env_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if "api_key" not in st.session_state:
        st.session_state.api_key = env_key
    if not st.session_state.api_key:
        st.session_state.api_key = st.text_input("ANTHROPIC_API_KEY", type="password",
            help="A consumo, separata da Claude Code. Oppure imposta la variabile d'ambiente.")

    chat_box = st.container(height=height)
    with chat_box:
        for m in st.session_state.messages:
            if m["role"] == "user" and isinstance(m["content"], str):
                with st.chat_message("user"):
                    st.markdown(m["content"])
            elif m["role"] == "assistant":
                with st.chat_message("assistant"):
                    for b in m["content"]:
                        bt = getattr(b, "type", None) or (isinstance(b, dict) and b.get("type"))
                        if bt == "text":
                            st.markdown(b.text if hasattr(b, "text") else b["text"])
                        elif bt == "tool_use":
                            nm = b.name if hasattr(b, "name") else b["name"]
                            inp = b.input if hasattr(b, "input") else b["input"]
                            st.caption(f"🔧 {nm}({', '.join(f'{k}={v}' for k, v in inp.items())})")

    prompt = st.chat_input("Chiedi all'assistente…")
    if not prompt:
        return
    if not st.session_state.api_key:
        st.warning("Inserisci una API key Anthropic per usare l'assistente."); st.stop()

    import anthropic
    client = anthropic.Anthropic(api_key=st.session_state.api_key)
    st.session_state.messages.append({"role": "user", "content": prompt})
    with chat_box:
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            try:
                for _ in range(6):
                    ph = st.empty(); acc = ""
                    with client.messages.stream(model=MODEL, max_tokens=2000,
                            system=system_prompt_for(ctx), thinking={"type": "disabled"},
                            tools=TOOLS_SCHEMA, messages=st.session_state.messages) as stream:
                        for delta in stream.text_stream:
                            acc += delta; ph.markdown(acc + " ▌")
                        resp = stream.get_final_message()
                    ph.markdown(acc) if acc else ph.empty()
                    st.session_state.messages.append({"role": "assistant", "content": resp.content})
                    calls = [b for b in resp.content if b.type == "tool_use"]
                    for b in calls:
                        st.caption(f"🔧 {b.name}({', '.join(f'{k}={v}' for k, v in b.input.items())})")
                    if resp.stop_reason != "tool_use":
                        break
                    res = [{"type": "tool_result", "tool_use_id": b.id,
                            "content": run_tool(b.name, b.input, ctx)} for b in calls]
                    st.session_state.messages.append({"role": "user", "content": res})
            except anthropic.AuthenticationError:
                st.error("API key non valida.")
            except anthropic.APIError as e:
                st.error(f"Errore API: {e}")


# ════════════════════════════════════════════════════════════════════════════
# GESTIONE DATI — fonti in uso, upload di file con descrizione/fonte, registro
# ════════════════════════════════════════════════════════════════════════════
DATA_DIR = "data"
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
REGISTRY_PATH = os.path.join(DATA_DIR, "registry.json")


def _fmt_mtime(path: str) -> str:
    try:
        return datetime.datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d %H:%M")
    except OSError:
        return "—"


def _csv_rows(path: str):
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            return max(sum(1 for _ in f) - 1, 0)
    except OSError:
        return None


# Schema colonne UNIFICATO per le due tabelle (Presenti e in Valutazione)
SRC_COLS = ["Dataset", "Descrizione", "Fonte", "URL", "Frequenza", "Stato", "Righe", "Aggiornato"]


def _row(dataset, descr, fonte, url, freq, stato, righe, agg):
    return {"Dataset": dataset, "Descrizione": descr, "Fonte": fonte, "URL": url,
            "Frequenza": freq, "Stato": stato, "Righe": righe, "Aggiornato": agg}


def builtin_sources() -> list[dict]:
    """Fonti dati GIÀ in uso dal motore (cache + live), colonne unificate con URL."""
    A = "🟢 Attiva"
    rows = []
    istat = ".cache/istat_presenze_straniere_abruzzo.csv"
    if os.path.exists(istat):
        rows.append(_row("Presenze straniere Abruzzo", "Presenze di stranieri al mese in Abruzzo (movimento clienti)",
                         "ISTAT", "https://esploradati.istat.it/", "mensile", A, _csv_rows(istat), _fmt_mtime(istat)))
    trends = sorted(glob.glob(".cache/trends_*.csv"))
    if trends:
        rows.append(_row(f"Google Trends — {len(trends)} mercati", "Interesse di ricerca «Abruzzo» per paese (leading)",
                         "Google Trends", "https://trends.google.com/", "mensile", A,
                         sum((_csv_rows(t) or 0) for t in trends), _fmt_mtime(trends[0])))
    rows.append(_row("Cambio valute", "Indice del cambio EUR vs USD/GBP/CHF (driver economico)",
                     "ECB Statistical Data Warehouse", "https://data.ecb.europa.eu/", "mensile", A, "—", "live"))
    bdi = ".cache/bdi_spend_per_market.csv"
    if os.path.exists(bdi):
        rows.append(_row("Spesa turisti stranieri", "Spesa €/viaggiatore per paese + per regione (valore economico)",
                         "Banca d'Italia · turismo internazionale",
                         "https://www.bancaditalia.it/statistiche/tematiche/rapporti-estero/turismo-internazionale/",
                         "trimestrale", A, _csv_rows(bdi), _fmt_mtime(bdi)))
    cap = ".cache/istat_capacity_letti_ITF1.csv"
    if os.path.exists(cap):
        rows.append(_row("Capacità ricettiva (posti letto)", "Posti letto Abruzzo per anno (per l'occupazione)",
                         "ISTAT · Capacità esercizi ricettivi", "https://esploradati.istat.it/", "annuale", A,
                         _csv_rows(cap), _fmt_mtime(cap)))
    eu = ".cache/eurostat_pescara_flights.csv"
    if os.path.exists(eu):
        rows.append(_row("Connettività aerea Pescara", "Passeggeri voli diretti per paese verso Pescara (fattibilità)",
                         "Eurostat · avia_par", "https://ec.europa.eu/eurostat/", "annuale", A,
                         _csv_rows(eu), _fmt_mtime(eu)))
    wk = ".cache/wiki_de.csv"
    if os.path.exists(wk):
        rows.append(_row("Wikipedia pageviews", "Visualizzazioni pagina «Abruzzo» per lingua (2° segnale leading)",
                         "Wikimedia · Pageviews API", "https://wikimedia.org/api/rest_v1/", "mensile", A,
                         _csv_rows(wk), _fmt_mtime(wk)))
    geo = ".cache/world_countries.geojson"
    if os.path.exists(geo):
        rows.append(_row("Confini paesi (mappa)", "Geometrie dei confini per la mappa GIS (offline)",
                         "openpolis / johan world.geo.json", "https://github.com/openpolis/geojson-italy",
                         "statico", A, "—", _fmt_mtime(geo)))
    return rows


def load_registry() -> list[dict]:
    if os.path.exists(REGISTRY_PATH):
        try:
            return json.load(open(REGISTRY_PATH, encoding="utf-8"))
        except (OSError, ValueError):
            return []
    return []


def _save_registry(reg: list[dict]):
    os.makedirs(DATA_DIR, exist_ok=True)
    json.dump(reg, open(REGISTRY_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


def save_upload(uploaded_file, nome: str, descrizione: str, fonte: str, url: str = "") -> dict:
    """Salva un file caricato in data/uploads/ e ne registra i metadati (nome, descrizione, fonte, URL)."""
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in uploaded_file.name)
    fid = f"{int(time.time())}_{safe}"
    path = os.path.join(UPLOAD_DIR, fid)
    data = uploaded_file.getvalue()
    with open(path, "wb") as f:
        f.write(data)
    righe = None
    if safe.lower().endswith(".csv"):
        try:
            righe = max(sum(1 for _ in io.StringIO(data.decode("utf-8", "ignore"))) - 1, 0)
        except ValueError:
            righe = None
    rec = {"id": fid, "nome": (nome or "").strip() or uploaded_file.name, "file": uploaded_file.name,
           "descrizione": (descrizione or "").strip(), "fonte": (fonte or "").strip(),
           "url": (url or "").strip(), "path": path,
           "caricato": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
           "dimensione_kb": round(len(data) / 1024, 1), "righe": righe}
    reg = load_registry(); reg.append(rec); _save_registry(reg)
    return rec


def delete_upload(rec_id: str):
    keep = []
    for r in load_registry():
        if r["id"] == rec_id:
            try:
                os.remove(r["path"])
            except OSError:
                pass
        else:
            keep.append(r)
    _save_registry(keep)


# ════════════════════════════════════════════════════════════════════════════
# FONTI CANDIDATE — scoperta con NULLA OSTA umano (Livello 1)
# ════════════════════════════════════════════════════════════════════════════
CAND_STATE_PATH = os.path.join(DATA_DIR, "candidates_state.json")

CANDIDATES = [
    {"id": "openmeteo", "nome": "Meteo Pescara (storico)",
     "descrizione": "Temperatura media e precipitazioni mensili a Pescara — driver della domanda balneare/montana.",
     "fonte": "Open-Meteo", "url": "https://open-meteo.com/", "frequenza": "mensile",
     "probe": CS.probe_open_meteo, "load": CS.load_open_meteo},
    {"id": "holidays", "nome": "Festività per paese",
     "descrizione": "Festività nazionali dei mercati (DE/AT/GB/US/NL/CH) — per il timing delle campagne.",
     "fonte": "Nager.Date", "url": "https://date.nager.at/", "frequenza": "annuale",
     "probe": CS.probe_holidays, "load": CS.load_holidays},
    {"id": "istat_viaggi", "nome": "Viaggi dei residenti abruzzesi",
     "descrizione": "Viaggi/notti dei residenti dell'Abruzzo per destinazione (le «partenze»).",
     "fonte": "ISTAT · DCCV_TURNOT", "url": "https://esploradati.istat.it/", "frequenza": "annuale",
     "probe": CS.probe_istat_viaggi, "load": CS.load_istat_viaggi},
    {"id": "musei", "nome": "Musei statali — visitatori e introiti",
     "descrizione": "Visitatori e introiti dei musei statali per istituto (1996-2024). NAZIONALE, "
                    "filtrabile per regione → segnale di domanda culturale del territorio.",
     "fonte": "MiC · dati.gov.it", "frequenza": "annuale",
     "url": "https://www.dati.gov.it/opendata/dataset/musei-statali-visitatori-ed-introiti-1996-2024",
     "probe": CS.probe_musei, "load": CS.load_musei},
    {"id": "aeroporti", "nome": "Mappa aeroporti commerciali italiani",
     "descrizione": "Anagrafica degli aeroporti italiani aperti al traffico (coord., IATA, località). "
                    "NAZIONALE → base per la mappa regione→aeroporto (accessibilità multi-regione).",
     "fonte": "Autorità Trasporti · dati.gov.it", "frequenza": "annuale",
     "url": "https://www.dati.gov.it/opendata/dataset/mappa-degli-aeroporti-aperti-al-traffico-commerciale",
     "probe": CS.probe_aeroporti, "load": CS.load_aeroporti},
    {"id": "ferrovia", "nome": "Traffico passeggeri ferroviario (nazionale)",
     "descrizione": "Passeggeri ferroviari per anno (totale nazionale). Indicatore di contesto "
                    "sull'accessibilità ferroviaria; non disaggregato per regione.",
     "fonte": "Autorità Trasporti · dati.gov.it", "frequenza": "annuale",
     "url": "https://www.dati.gov.it/opendata/dataset/evoluzione-del-traffico-passeggeri-per-ferrovia",
     "probe": CS.probe_ferrovia, "load": CS.load_ferrovia},
]


def candidates_state() -> dict:
    if os.path.exists(CAND_STATE_PATH):
        try:
            return json.load(open(CAND_STATE_PATH, encoding="utf-8"))
        except (OSError, ValueError):
            return {}
    return {}


def _save_candidates_state(s: dict):
    os.makedirs(DATA_DIR, exist_ok=True)
    json.dump(s, open(CAND_STATE_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


def candidate_by_id(cid: str):
    return next((c for c in CANDIDATES if c["id"] == cid), None)


def approve_candidate(cid: str, descrizione: str) -> dict:
    """Carica (load) la fonte candidata DOPO il nulla osta e la marca approvata."""
    c = candidate_by_id(cid)
    if not c:
        return {"ok": False, "msg": "candidato sconosciuto"}
    try:
        res = c["load"]()
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "msg": f"caricamento fallito: {type(e).__name__}: {str(e)[:120]}"}
    st_ = candidates_state()
    st_[cid] = {"approved": True, "descrizione": (descrizione or c["descrizione"]).strip(),
                "caricato": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                "righe": res.get("rows"), "path": res.get("path")}
    _save_candidates_state(st_)
    return res


def revoke_candidate(cid: str):
    st_ = candidates_state()
    st_.pop(cid, None)
    _save_candidates_state(st_)


def present_sources() -> list[dict]:
    """Tabella DATI PRESENTI: fonti in uso + file caricati + candidati approvati (colonne unificate)."""
    rows = list(builtin_sources())
    for u in load_registry():
        url = u.get("url") or (u.get("fonte", "") if str(u.get("fonte", "")).startswith("http") else "")
        rows.append(_row(u.get("nome"), u.get("descrizione", ""), u.get("fonte", "caricato manualmente"),
                         url, "—", "📤 Caricato", u.get("righe"), u.get("caricato")))
    state = candidates_state()
    for c in CANDIDATES:
        s = state.get(c["id"])
        if s and s.get("approved"):
            rows.append(_row(c["nome"], s.get("descrizione", c["descrizione"]), c["fonte"], c["url"],
                             c["frequenza"], "🟢 Attiva (approvata)", s.get("righe"), s.get("caricato")))
    return rows


def pending_candidates() -> list[dict]:
    """Tabella DATI IN VALUTAZIONE: candidati non ancora approvati (colonne unificate)."""
    state = candidates_state()
    rows = []
    for c in CANDIDATES:
        if state.get(c["id"], {}).get("approved"):
            continue
        rows.append(_row(c["nome"], state.get(c["id"], {}).get("descrizione", c["descrizione"]),
                         c["fonte"], c["url"], c["frequenza"], "⏳ In valutazione", "—", "—"))
    return rows


COVERAGE_COLS = ["Informazione", "Nazionale", "Regionale", "Provinciale", "Fonte", "Note / buco da coprire"]


def coverage_matrix() -> list[dict]:
    """Mappa cosa abbiamo per LIVELLO geografico (nazionale/regionale/provinciale).
    ✅ disponibile · 🟡 parziale · ❌ assente. Serve a vedere i buchi per il multi-regione."""
    M = [
        ("Presenze turistiche (totali)", "✅", "✅", "✅", "ISTAT DCSC_TUR", "completo per tutte le regioni"),
        ("Presenze straniere (aggregato)", "✅", "✅", "✅", "ISTAT DCSC_TUR", "stranieri totali, non per singolo paese"),
        ("Presenze per PAESE di origine", "✅", "❌", "❌", "BdI TS1 / ISTAT naz.", "🔴 BUCO chiave: a livello regionale ISTAT non lo espone → si stima dalle quote nazionali"),
        ("Capacità ricettiva (posti letto)", "✅", "✅", "🟡", "ISTAT DCSC_TUR_1", "regionale ok; provinciale solo alcune"),
        ("Anagrafica strutture ricettive", "🟡", "❌", "❌", "registri regionali", "🔴 BUCO: registri non federati come open data"),
        ("Spesa turistica per paese", "✅", "🟡", "❌", "Banca d'Italia", "regionale solo TOTALE (TS2), non per paese"),
        ("Accessibilità aerea (voli/pax)", "✅", "✅", "—", "Eurostat avia_par", "regionale via mappa regione→aeroporto"),
        ("Accessibilità ferroviaria", "✅", "❌", "❌", "Aut. Trasporti", "🟡 solo totale nazionale; manca il dettaglio regionale"),
        ("Interesse online — Google Trends", "✅", "✅", "—", "Google Trends", "per regione: keyword = nome regione"),
        ("Interesse online — Wikipedia", "✅", "✅", "—", "Wikimedia", "per regione: articolo della regione"),
        ("Cambio valute (FX mercati)", "✅", "—", "—", "ECB", "nazionale per i mercati esteri (non è dato regionale)"),
        ("Fiducia consumatori (mercati)", "✅", "—", "—", "Eurostat", "per paese estero (DE/AT/NL); GB/CH/US via OCSE"),
        ("Domanda culturale (musei)", "✅", "✅", "🟡", "MiC (candidato)", "per istituto → filtrabile per regione"),
        ("Meteo destinazione", "✅", "✅", "✅", "Open-Meteo (candidato)", "per coordinate: qualunque capoluogo/comune"),
        ("Festività mercati esteri", "✅", "—", "—", "Nager.Date (candidato)", "per paese estero (timing campagne)"),
        ("Eventi / POI turistici", "🟡", "🟡", "🟡", "open data regionali", "🟡 alcune regioni pubblicano, molte no (Abruzzo scarso)"),
        ("Viaggi residenti per regione d'origine", "✅", "❌", "❌", "ISTAT Viaggi&Vacanze", "🔴 open data solo nazionale/macro-area; il dettaglio regionale è solo MICRODATI (richiesta istituzionale ISTAT)"),
        ("Confini amministrativi (geojson)", "✅", "✅", "✅", "openpolis / RNDT", "completo: usato per la mappa d'Italia"),
    ]
    return [dict(zip(COVERAGE_COLS, r)) for r in M]


# ════════════════════════════════════════════════════════════════════════════
# AZIONI RACCOMANDATE + BOZZA CAMPAGNA  (ispirate al "Suggerimento AI" del POC)
# ════════════════════════════════════════════════════════════════════════════
def peak_search_month(panel, code: str):
    col = f"search_{code}"
    if panel is None or col not in panel.columns:
        return None
    d = panel.copy(); d["m"] = d["date"].dt.month
    prof = d.groupby("m")[col].mean()
    return int(prof.idxmax()) if not prof.empty else None


def recommended_actions(ctx: dict) -> list[dict]:
    """Trasforma il ranking in azioni operative con priorità (Alta/Media/Bassa)."""
    s = markets_summary(ctx)
    panel = ctx["R"]["panel"] if ctx["mode"] == "real" else None
    acts = []
    for m in s:
        cat = reco_cat(m["reco"])
        forza, mom = m.get("forza") or 0, m.get("momentum") or 0
        if cat == "Aumentare" and forza >= 0.4 and mom > 20:
            prio = "Alta"
        elif cat == "Aumentare":
            prio = "Media"
        elif cat == "Ridurre":
            prio = "Media"
        else:
            prio = "Bassa"
        acts.append({"market": m["market"], "code": m["code"], "reco": m["reco"], "cat": cat,
                     "priorita": prio, "forza": m.get("forza"), "momentum": m.get("momentum"),
                     "valore": m.get("valore"), "score": m["score"], "rank": m["rank"],
                     "picco_mese": peak_search_month(panel, m["code"])})
    order = {"Alta": 0, "Media": 1, "Bassa": 2}
    return sorted(acts, key=lambda a: (order[a["priorita"]], -a["score"]))


def campaign_brief(ctx: dict, code: str) -> dict | None:
    a = next((x for x in recommended_actions(ctx) if x["code"] == code), None)
    if not a:
        return None
    pk = MONTHS_IT[a["picco_mese"] - 1] if a["picco_mese"] else "—"
    lag = ctx["R"]["agg"]["lag"] if ctx["mode"] == "real" else 2
    leva = []
    if a["valore"]:
        leva.append(f"alto valore economico (~€{a['valore']:.0f}/visitatore)")
    if a["momentum"] and a["momentum"] > 0:
        leva.append(f"interesse di ricerca in crescita ({a['momentum']:+.0f}% su anno prima)")
    if a["forza"] and a["forza"] > 0.3:
        leva.append(f"segnale anticipatore solido (forza {a['forza']:+.2f})")
    return {
        "mercato": a["market"], "priorita": a["priorita"], "azione": a["reco"],
        "finestra": f"presidiare il picco di ricerca (~{pk}); il search anticipa gli arrivi di ~{lag} mesi, "
                    f"quindi avviare la campagna prima del picco di presenze",
        "leva": "; ".join(leva) or "monitorare il segnale prima di investire",
        "kpi": "presenze straniere dal mercato · costo per arrivo · quota di ricerca 'Abruzzo' nel paese",
        "nota": "Stima d'opportunità (dove e quando conviene agire), NON una garanzia di ritorno: "
                "il motore non modella l'effetto causale della spesa promozionale.",
    }


# ════════════════════════════════════════════════════════════════════════════
# ARCHITETTURA & SORGENTI (dal documento tecnico TDH — vision + stato attuale)
# ════════════════════════════════════════════════════════════════════════════
def tdh_architecture() -> dict:
    return {
        "livelli": [
            ("1 · Sorgenti dati", "Portali regionali, MaaS, registri ricettivi, Hub nazionale PDND"),
            ("2 · Ingestion", "Batch ETL · Streaming · API connectors · connettore PDND"),
            ("3 · Data Lake (Medallion)", "Bronze (grezzo) → Silver (normalizzato/anonimizzato GDPR) → Gold (KPI)"),
            ("4 · Governance & processing", "Trasformazioni · GDPR engine · identity resolution · Auth/ACL (SPID/CIE)"),
            ("5 · Servizi di output", "Cruscotto Regione · API Operatori · Analytics ML · integrazione MaaS"),
        ],
        "sorgenti": [
            {"Sorgente": "ISTAT — movimento clienti", "Tipo": "Presenze per provenienza",
             "Frequenza": "Mensile", "Stato": "🟢 Attiva"},
            {"Sorgente": "ECB — cambio valute", "Tipo": "Driver economico (FX)",
             "Frequenza": "Mensile", "Stato": "🟢 Attiva"},
            {"Sorgente": "Google Trends", "Tipo": "Segnale leading di ricerca",
             "Frequenza": "Mensile", "Stato": "🟢 Attiva"},
            {"Sorgente": "Banca d'Italia — turismo internazionale", "Tipo": "Spesa per paese/regione (valore economico)",
             "Frequenza": "Trimestrale", "Stato": "🟢 Attiva"},
            {"Sorgente": "Eurostat — trasporto aereo (avia_par)", "Tipo": "Connettività voli per paese (fattibilità)",
             "Frequenza": "Annuale", "Stato": "🟢 Attiva"},
            {"Sorgente": "Wikipedia (Wikimedia Pageviews)", "Tipo": "Interesse per lingua (2° segnale leading)",
             "Frequenza": "Mensile", "Stato": "🟢 Attiva"},
            {"Sorgente": "PDND — Ministero Turismo SIT/CIR", "Tipo": "Statistiche turismo nazionali",
             "Frequenza": "Periodica", "Stato": "🟡 Pianificata"},
            {"Sorgente": "PDND — ANPR", "Tipo": "Presenze cittadini",
             "Frequenza": "Periodica", "Stato": "🟡 Pianificata"},
            {"Sorgente": "Portale Regionale (GA4)", "Tipo": "Web analytics, funnel visitatori",
             "Frequenza": "Giornaliera", "Stato": "🟡 Pianificata"},
            {"Sorgente": "MaaS4Abruzzo (GTFS-RT)", "Tipo": "Mobilità, percorsi, viaggi",
             "Frequenza": "Real-time", "Stato": "🟡 Pianificata"},
            {"Sorgente": "Registro Ricettivo (~2.800 strutture)", "Tipo": "Offerta ricettiva",
             "Frequenza": "Batch", "Stato": "🟡 Pianificata"},
            {"Sorgente": "App TUA", "Tipo": "Ticketing / transiti",
             "Frequenza": "Real-time", "Stato": "⚪ Da valutare"},
            {"Sorgente": "Meteo ARPAM", "Tipo": "Dati territoriali",
             "Frequenza": "Oraria", "Stato": "⚪ Da valutare"},
        ],
        "roadmap": [
            "Fase 1 — Fondamenta: sorgenti nazionali (PDND/ISTAT) + primo motore decisionale. "
            "*Questo MVP è il primo mattone reale.*",
            "Fase 2 — Integrazione regionale: portale GA4, MaaS4Abruzzo, registro ricettivo.",
            "Fase 3 — Analytics ML: forecasting flussi, segmentazione turisti, alerting anomalie.",
            "Fase 4 — Servizi: cruscotto Regione, API operatori, integrazione MaaS in tempo reale.",
        ],
        "principi": [
            "**GDPR by design** — anonimizzazione PII nelle zone Silver/Gold, nessun dato nominale.",
            "**Cloud PA-first** — infrastruttura su provider qualificato ACN (PSNC), dati nell'UE.",
            "**Non sostitutivo** — il TDH si appoggia sopra i sistemi esistenti come layer di integrazione.",
            "**PDND** — sorgenti nazionali senza convenzioni bilaterali (art. 50-ter CAD).",
        ],
    }


# ════════════════════════════════════════════════════════════════════════════
# VISTE TERRITORIALI — per Provincia e per tipologia di Struttura (dati ISTAT reali)
# ════════════════════════════════════════════════════════════════════════════
@st.cache_data(show_spinner="Carico le presenze per provincia (ISTAT)…")
def compute_provinces(code: str | None = None) -> dict:
    """Presenze per provincia (NUTS3) della regione richiesta. Multi-regione: le
    province vengono dal registro; le serie che ISTAT non espone vengono saltate."""
    from tourism_wedge.real_sources import fetch_istat_presences
    code = code or RG.DEFAULT_REGION
    rows, wide = [], None
    for area, nome in RG.provinces(code).items():
        try:
            tot = fetch_istat_presences(area=area, country="WORLD").rename(columns={"presences": nome})
            est = fetch_istat_presences(area=area, country="WRL_X_ITA")
        except Exception:  # noqa: BLE001 — provincia non esposta/abolita: salto
            continue
        wide = tot if wide is None else wide.merge(tot, on="date", how="outer")
        t12 = float(tot.sort_values("date").tail(12)[nome].sum())
        e12 = float(est.sort_values("date").tail(12)["presences"].sum())
        rows.append({"provincia": nome, "presenze": t12, "stranieri": e12,
                     "quota_stranieri": (e12 / t12 * 100 if t12 else 0.0)})
    if wide is None:
        return {"rows": [], "panel": pd.DataFrame({"date": []})}
    return {"rows": sorted(rows, key=lambda r: -r["presenze"]), "panel": wide.sort_values("date")}


@st.cache_data(show_spinner="Carico le presenze per struttura (ISTAT)…")
def compute_structure() -> dict:
    from tourism_wedge.real_sources import fetch_istat_presences
    hot = fetch_istat_presences(area="ITF1", accom="HOTELLIKE", country="WORLD").rename(columns={"presences": "alberghiero"})
    oth = fetch_istat_presences(area="ITF1", accom="OTHER", country="WORLD").rename(columns={"presences": "extra"})
    panel = hot.merge(oth, on="date", how="outer").sort_values("date")
    return {"alberghiero": float(hot.tail(12)["alberghiero"].sum()),
            "extra": float(oth.tail(12)["extra"].sum()), "panel": panel}


@st.cache_data(show_spinner=False)
def _italy_provinces_geojson():
    p = "assets/italy_provinces.geojson"
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None


def chart_province_map(rows: list[dict]) -> go.Figure | None:
    gj = _italy_provinces_geojson()
    if gj is None or not rows:
        return None
    names = [r["provincia"] for r in rows]
    fig = go.Figure(go.Choropleth(
        geojson=gj, featureidkey="properties.prov_name", locations=names, name="presenze",
        z=[r["presenze"] for r in rows], colorscale="Teal", marker_line_color="white", marker_line_width=1,
        colorbar=dict(title=dict(text="presenze (12 mesi)", side="right")),
        customdata=[[r["stranieri"], r["quota_stranieri"]] for r in rows],
        hovertemplate="<b>%{location}</b><br>presenze %{z:,.0f}"
                      "<br>di cui stranieri %{customdata[0]:,.0f} (%{customdata[1]:.0f}%)<extra></extra>"))
    fig.update_geos(fitbounds="locations", visible=False, projection_type="mercator", bgcolor="rgba(0,0,0,0)")
    fig.update_layout(height=460, margin=dict(l=0, r=0, t=10, b=0), paper_bgcolor="white",
                      title_text="", font=dict(family=FONT_STACK))
    return fig


def chart_province_bar(rows: list[dict]) -> go.Figure:
    prov = [r["provincia"] for r in rows]
    fig = go.Figure()
    fig.add_trace(go.Bar(x=prov, y=[r["presenze"] - r["stranieri"] for r in rows],
                         name="italiani", marker_color="#0e7490"))
    fig.add_trace(go.Bar(x=prov, y=[r["stranieri"] for r in rows], name="stranieri", marker_color="#f59e0b"))
    fig.update_layout(barmode="stack")
    fig.update_yaxes(title="presenze (12 mesi)")
    return _layout(fig, h=340)


def chart_province_trend(panel, rangeslider: bool = False) -> go.Figure:
    fig = go.Figure()
    for col in [c for c in panel.columns if c != "date"]:
        d = panel[["date", col]].dropna()
        fig.add_trace(go.Scatter(x=d["date"], y=d[col], name=col, mode="lines+markers"))
    fig.update_yaxes(title="presenze")
    if rangeslider:
        fig.update_xaxes(rangeslider_visible=True, rangeslider_thickness=0.08)
    return _layout(fig, h=400 if rangeslider else 360)


def chart_structure_donut(s: dict) -> go.Figure:
    fig = go.Figure(go.Pie(labels=["Alberghiero", "Extra-alberghiero"],
                           values=[s["alberghiero"], s["extra"]], hole=0.55,
                           marker=dict(colors=["#0e7490", "#f59e0b"])))
    return _layout(fig, h=320)


def chart_structure_trend(panel) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=panel["date"], y=panel["alberghiero"], name="Alberghiero",
                             line=dict(color="#0e7490", width=2)))
    fig.add_trace(go.Scatter(x=panel["date"], y=panel["extra"], name="Extra-alberghiero",
                             line=dict(color="#f59e0b", width=2)))
    fig.update_yaxes(title="presenze")
    return _layout(fig, h=340)


# ════════════════════════════════════════════════════════════════════════════
# OCCUPAZIONE REALE — indice di utilizzazione lorda dei posti letto (ISTAT)
#   occ = presenze ÷ (posti letto × giorni del mese)
# presenze totali Abruzzo = somma delle 4 province (WORLD); posti letto: dataset Capacità.
# ════════════════════════════════════════════════════════════════════════════
@st.cache_data(show_spinner="Calcolo l'occupazione (ISTAT)…")
def compute_occupancy() -> dict:
    beds_path = ".cache/istat_capacity_letti_ITF1.csv"
    if not os.path.exists(beds_path):
        return {"available": False}
    beds = pd.read_csv(beds_path)
    beds_map = dict(zip(beds["anno"].astype(int), beds["letti"].astype(float)))
    if not beds_map:
        return {"available": False}
    P = compute_provinces()
    panel = P["panel"].copy()
    prov_cols = [c for c in panel.columns if c != "date"]
    panel["presenze"] = panel[prov_cols].sum(axis=1)
    panel = panel[["date", "presenze"]].dropna().copy()
    last_year = max(beds_map)
    panel["letti"] = panel["date"].dt.year.map(lambda y: beds_map.get(int(y), beds_map[last_year]))
    panel["giorni"] = panel["date"].dt.daysinmonth
    panel["occ"] = panel["presenze"] / (panel["letti"] * panel["giorni"]) * 100
    occ12 = float(panel.sort_values("date").tail(12)["occ"].mean())
    return {"available": True, "panel": panel.sort_values("date"), "occ_media12": occ12,
            "letti_ultimo": int(beds_map[last_year]), "anno_letti": int(last_year)}


def chart_occupancy(panel) -> go.Figure:
    fig = go.Figure(go.Scatter(x=panel["date"], y=panel["occ"], line=dict(color="#0e7490", width=2),
                               name="occupazione", fill="tozeroy", fillcolor="rgba(14,116,144,.12)"))
    fig.update_yaxes(title="occupazione lorda", ticksuffix="%")
    return _layout(fig, h=360)


# ── MULTI-REGIONE: quadro ISTAT per qualunque regione (NUTS2) ─────────────────
@st.cache_data(show_spinner="Carico i dati ISTAT della regione…")
def region_overview(code: str) -> dict:
    """Presenze mensili (totale + stranieri) e capacità della regione richiesta.
    Funziona per tutte le 20 regioni (ISTAT per NUTS2). Cache per-regione."""
    info = RG.region(code)
    area = info["code"]
    stran = RS.fetch_istat_presences(area=area, country="WRL_X_ITA", start="2019-01")
    tot = RS.fetch_istat_presences(area=area, country="WORLD", start="2019-01")
    df = (stran.rename(columns={"presences": "stranieri"})
          .merge(tot.rename(columns={"presences": "totale"}), on="date", how="outer")
          .sort_values("date").reset_index(drop=True))
    letti = anno = None
    try:
        cap = RS.fetch_istat_capacity(area=area)
        letti, anno = int(cap["letti"].iloc[-1]), int(cap["anno"].iloc[-1])
    except Exception:  # noqa: BLE001
        pass
    return {"info": info, "presenze": df, "letti": letti, "anno_letti": anno}


def chart_region_presences(df) -> go.Figure:
    fig = go.Figure()
    if "totale" in df:
        fig.add_trace(go.Scatter(x=df["date"], y=df["totale"], name="totale",
                                 mode="lines", line=dict(color="#0e7490", width=2)))
    fig.add_trace(go.Scatter(x=df["date"], y=df["stranieri"], name="stranieri",
                             mode="lines", line=dict(color="#f59e0b", width=2)))
    fig.update_yaxes(title="presenze (mese)")
    return _layout(fig, h=360)


def regions_spend_ranking() -> list[dict]:
    """Classifica delle regioni per spesa turistica straniera 2024 (Banca d'Italia).
    code (NUTS2) · regione · spesa_M · rank. Multi-regione by construction."""
    ext = bdi_extended()
    spese = (ext or {}).get("regioni_2024", {})
    if not spese:
        return []
    rows = []
    for code, info in RG.REGIONS.items():
        sp = spese.get(info["bdi"])
        if sp is not None:
            rows.append({"code": code, "regione": info["nome"], "spesa_M": float(sp)})
    rows.sort(key=lambda r: r["spesa_M"], reverse=True)
    for i, r in enumerate(rows):
        r["rank"] = i + 1
    return rows


def region_spend(code: str):
    """(spesa_M, rank, totale_regioni) per la regione richiesta, o None."""
    rk = regions_spend_ranking()
    bdi = RG.region(code)["bdi"]
    hit = next((r for r in rk if RG.REGIONS[r["code"]]["bdi"] == bdi), None)
    return (hit["spesa_M"], hit["rank"], len(rk)) if hit else None


@st.cache_data(show_spinner=False)
def _italy_regions_geojson():
    return json.load(open("assets/italy_regions.geojson", encoding="utf-8"))


def chart_italy_map(highlight: str | None = None) -> go.Figure:
    """Mappa d'Italia delle regioni, colorata per spesa straniera (BdI). La regione
    `highlight` ha il bordo rosso. Cliccabile come selettore (gestito in app)."""
    gj = _italy_regions_geojson()
    spend = {RG.REGIONS[r["code"]]["bdi"]: r["spesa_M"] for r in regions_spend_ranking()}
    names, z = [], []
    for f in gj["features"]:
        nm = f["properties"]["reg_name"]
        code = RG.code_for_geo(nm)
        names.append(nm)
        z.append(spend.get(RG.region(code)["bdi"]) if code else None)
    fig = go.Figure(go.Choropleth(
        geojson=gj, featureidkey="properties.reg_name", locations=names, z=z, name="spesa",
        colorscale="Teal", marker_line_color="white", marker_line_width=0.6,
        selected=dict(marker=dict(opacity=1.0)), unselected=dict(marker=dict(opacity=1.0)),
        colorbar=dict(title=dict(text="spesa straniera<br>2024 (M€)", side="right")),
        hovertemplate="<b>%{location}</b><br>spesa %{z:,.0f} M€<extra></extra>"))
    hn = RG.GEO_NAME.get(highlight) if highlight else None
    if hn:
        fig.add_trace(go.Choropleth(
            geojson=gj, featureidkey="properties.reg_name", locations=[hn], z=[0], showscale=False,
            colorscale=[[0, "rgba(0,0,0,0)"], [1, "rgba(0,0,0,0)"]],
            marker_line_color="#dc2626", marker_line_width=2.5, hoverinfo="skip"))
    fig.update_geos(fitbounds="locations", visible=False, projection_type="mercator",
                    bgcolor="rgba(0,0,0,0)")
    fig.update_layout(height=620, margin=dict(l=0, r=0, t=10, b=0), paper_bgcolor="white",
                      title_text="", font=dict(family=FONT_STACK))
    return fig


def chart_regions_ranking(highlight: str | None = None) -> go.Figure:
    rk = regions_spend_ranking()
    if not rk:
        return _layout(go.Figure(), h=300)
    rk = sorted(rk, key=lambda r: r["spesa_M"])
    hi_bdi = RG.region(highlight)["bdi"] if highlight else None
    colors = ["#f59e0b" if RG.REGIONS[r["code"]]["bdi"] == hi_bdi else "#0e7490" for r in rk]
    fig = go.Figure(go.Bar(x=[r["spesa_M"] for r in rk], y=[r["regione"] for r in rk],
                           orientation="h", marker_color=colors,
                           hovertemplate="<b>%{y}</b><br>%{x:,.0f} M€<extra></extra>"))
    fig.update_xaxes(title="spesa turisti stranieri 2024 (M€)")
    return _layout(fig, h=560)


def chart_occupancy_season(panel) -> go.Figure:
    d = panel.copy(); d["m"] = d["date"].dt.month
    prof = d.groupby("m")["occ"].mean().reindex(range(1, 13))
    fig = go.Figure(go.Bar(x=MONTHS_IT, y=prof.values, marker_color="#0e7490"))
    fig.update_yaxes(title="occupazione media", ticksuffix="%")
    return _layout(fig, h=300)


# ════════════════════════════════════════════════════════════════════════════
# VISTA OPERATORI — DEMO (dati SIMULATI, etichettati): parità col POC su feature
# che richiedono sorgenti non ancora collegate (Registro ricettivo, OTA, GA4).
# ════════════════════════════════════════════════════════════════════════════
def demo_banner():
    st.markdown("""<div style="background:#fffbeb;border:1px solid #fcd34d;border-radius:12px;
        padding:12px 16px;margin-bottom:14px;color:#92400e">
        <b>⚠️ DEMO · dati simulati</b> a scopo illustrativo — anticipa funzionalità che richiedono
        sorgenti non ancora collegate (Registro ricettivo, booking/OTA, analytics del portale).
        I numeri NON sono reali.</div>""", unsafe_allow_html=True)


def demo_operators(provincia: str = "Tutte") -> dict:
    """Dati SIMULATI ma deterministici (seed dalla provincia) per la vista operatori demo."""
    import random
    rng = random.Random(sum(ord(c) for c in provincia) + 7)
    base = {"Organico": 32, "OTA (Booking/Expedia)": 27, "Social": 17,
            "Diretto": 13, "Email": 8, "Referral": 3}
    ch = {k: max(1, v + rng.randint(-4, 4)) for k, v in base.items()}
    tot = sum(ch.values()); ch = {k: round(v / tot * 100, 1) for k, v in ch.items()}
    ric = rng.randint(80, 140) * 1000
    sch = int(ric * rng.uniform(0.40, 0.50))
    clk = int(sch * rng.uniform(0.22, 0.30))
    pren = int(clk * rng.uniform(0.24, 0.32))
    base_w = [0.72, 0.70, 0.76, 0.86, 1.02, 1.22, 1.12]
    scale = rng.randint(900, 1600)
    weekly = {g: int(scale * w * rng.uniform(0.92, 1.08))
              for g, w in zip(["Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom"], base_w)}
    rev = {"5★": rng.randint(120, 320), "4★": rng.randint(80, 200), "3★": rng.randint(20, 70),
           "2★": rng.randint(5, 25), "1★": rng.randint(2, 15)}
    queries = ["Costa dei Trabocchi", "Gran Sasso trekking", "Rocca Calascio", "borghi Abruzzo",
               "Parco della Majella", "spiagge Abruzzo", "agriturismo Abruzzo", "Lago di Scanno"]
    rng.shuffle(queries)
    return {"occupazione": rng.randint(48, 78), "adr": rng.randint(62, 118),
            "qualita": round(rng.uniform(3.8, 4.6), 1), "conversione": round(rng.uniform(1.8, 4.2), 1),
            "canali": ch, "funnel": {"Ricerche": ric, "Schede viste": sch,
            'Click "prenota"': clk, "Prenotazioni": pren},
            "weekly": weekly, "recensioni": rev, "queries": queries[:6]}


def chart_demo_channels(ch: dict) -> go.Figure:
    return _layout(go.Figure(go.Pie(labels=list(ch), values=list(ch.values()), hole=0.55)), h=320)


def chart_demo_funnel(f: dict) -> go.Figure:
    fig = go.Figure(go.Funnel(y=list(f), x=list(f.values()), textinfo="value+percent initial",
                              marker={"color": ["#0e7490", "#0891b2", "#38bdf8", "#f59e0b"]}))
    return _layout(fig, h=320)


def chart_demo_weekly(w: dict) -> go.Figure:
    fig = go.Figure(go.Bar(x=list(w), y=list(w.values()), marker_color="#0e7490"))
    fig.update_yaxes(title="presenze previste")
    return _layout(fig, h=290)


def chart_demo_reviews(r: dict) -> go.Figure:
    keys = list(r)[::-1]  # 1★..5★ dal basso
    fig = go.Figure(go.Bar(x=[r[k] for k in keys], y=keys, orientation="h",
                           marker_color=["#dc2626", "#f59e0b", "#eab308", "#84cc16", "#16a34a"]))
    fig.update_xaxes(title="recensioni")
    return _layout(fig, h=260)


# ════════════════════════════════════════════════════════════════════════════
# SLICING STORICO — filtro periodo + mappa di copertura delle serie
# ════════════════════════════════════════════════════════════════════════════
def filter_years(df, yr_range, date_col: str = "date"):
    """Ritaglia un DataFrame all'intervallo di anni [a, b]."""
    if df is None or date_col not in df.columns:
        return df
    a, b = yr_range
    return df[(df[date_col].dt.year >= a) & (df[date_col].dt.year <= b)]


def series_coverage() -> list[dict]:
    """Inizio-fine di ogni serie storica in cache (coperture diverse)."""
    def rng(path):
        if not os.path.exists(path):
            return None
        d = pd.read_csv(path)
        if "date" in d.columns:
            t = pd.to_datetime(d["date"]); return t.min(), t.max()
        if "anno" in d.columns:
            return pd.Timestamp(f"{int(d['anno'].min())}-01-01"), pd.Timestamp(f"{int(d['anno'].max())}-12-31")
        return None
    items = [
        ("Presenze straniere (ISTAT)", ".cache/istat_presenze_straniere_abruzzo.csv", "mensile"),
        ("Presenze province (ISTAT)", ".cache/istat_ITF13_NI_ALL_WORLD.csv", "mensile"),
        ("Capacità posti letto (ISTAT)", ".cache/istat_capacity_letti_ITF1.csv", "annuale"),
        ("Google Trends (per mercato)", ".cache/trends_abruzzo_DE.csv", "mensile"),
        ("Wikipedia (per lingua)", ".cache/wiki_de.csv", "mensile"),
    ]
    cov = []
    for name, path, freq in items:
        r = rng(path)
        if r:
            cov.append({"serie": name, "start": r[0], "end": r[1], "freq": freq})
    cov.append({"serie": "Cambio ECB (live)", "start": pd.Timestamp("2019-01-01"),
                "end": pd.Timestamp.today().normalize(), "freq": "mensile"})
    if os.path.exists(".cache/bdi_turismo_ts.xlsx"):
        cov.append({"serie": "Spesa BdI (turismo internaz.)", "start": pd.Timestamp("1997-01-01"),
                    "end": pd.Timestamp("2025-12-31"), "freq": "trimestrale"})
    eu = ".cache/eurostat_pescara_flights.csv"
    if os.path.exists(eu):
        try:
            y = int(pd.read_csv(eu)["anno"].iloc[0])
        except Exception:  # noqa: BLE001
            y = 2024
        cov.append({"serie": "Voli Pescara (Eurostat)", "start": pd.Timestamp(f"{y}-01-01"),
                    "end": pd.Timestamp(f"{y}-12-31"), "freq": "annuale"})
    return cov


def chart_coverage(cov: list[dict]) -> go.Figure:
    import plotly.express as px
    df = pd.DataFrame(cov)
    fig = px.timeline(df, x_start="start", x_end="end", y="serie", color="freq",
                      color_discrete_sequence=["#0e7490", "#f59e0b", "#16a34a"])
    fig.update_yaxes(autorange="reversed", title=None)
    fig.update_layout(height=300, margin=dict(l=10, r=10, t=10, b=10), paper_bgcolor="white",
                      plot_bgcolor="white", title_text="", legend_title="frequenza", font=dict(family=FONT_STACK))
    return fig


# ════════════════════════════════════════════════════════════════════════════
# BANCA D'ITALIA — vista estesa (spesa Abruzzo, regioni, motivo, struttura, durata)
# ════════════════════════════════════════════════════════════════════════════
@st.cache_data(show_spinner=False)
def bdi_extended():
    p = ".cache/bdi_extended.json"
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None


def chart_abruzzo_spend(ext: dict, yr_range=None) -> go.Figure:
    a = ext["abruzzo"]; anni, sp = a["anni"], a["spesa"]
    if yr_range:
        keep = [i for i, y in enumerate(anni) if yr_range[0] <= y <= yr_range[1]]
        anni, sp = [anni[i] for i in keep], [sp[i] for i in keep]
    fig = go.Figure(go.Bar(x=anni, y=sp, marker_color="#0e7490",
                           hovertemplate="%{x}: %{y:.0f} M€<extra></extra>"))
    fig.update_yaxes(title="spesa straniera (M€)")
    return _layout(fig, h=320)


def chart_regions_spend(ext: dict) -> go.Figure:
    items = sorted(ext["regioni_2024"].items(), key=lambda x: x[1])
    colors = ["#f59e0b" if k == "Abruzzo" else "#0e7490" for k, _ in items]
    fig = go.Figure(go.Bar(x=[v for _, v in items], y=[k for k, _ in items], orientation="h",
                           marker_color=colors, hovertemplate="<b>%{y}</b><br>%{x:,.0f} M€<extra></extra>"))
    fig.update_xaxes(title="spesa turisti stranieri 2024 (M€)")
    return _layout(fig, h=470)


def chart_bdi_motivo(ext: dict) -> go.Figure:
    m = ext["motivo_2024"]
    return _layout(go.Figure(go.Pie(labels=list(m), values=list(m.values()), hole=0.55,
                   marker=dict(colors=["#0e7490", "#38bdf8", "#f59e0b"]))), h=320)


def chart_bdi_struttura(ext: dict) -> go.Figure:
    items = sorted(ext["struttura_2024"].items(), key=lambda x: x[1])
    fig = go.Figure(go.Bar(x=[v for _, v in items], y=[k for k, _ in items], orientation="h",
                           marker_color="#0e7490", hovertemplate="<b>%{y}</b><br>%{x:,.0f} M€<extra></extra>"))
    fig.update_xaxes(title="spesa nazionale 2024 (M€)")
    return _layout(fig, h=300)
