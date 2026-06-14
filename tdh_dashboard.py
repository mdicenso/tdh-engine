"""
Cruscotto TDH Engine — dashboard visiva + assistente Claude con tool sul motore.

Avvio:
    streamlit run tdh_dashboard.py

Due modalità:
  • Sintetico — il motore per-mercato su dati di collaudo (engine.py).
  • Reale — Opzione A su dati veri (ECB cambio · ISTAT presenze straniere · Google Trends),
    con engine_aggregate.py: un target aggregato + ranking per-mercato.

L'assistente usa l'API Anthropic (claude-sonnet-4-6). Serve ANTHROPIC_API_KEY
(variabile d'ambiente oppure incollata nel campo password).
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict

# Ambiente aziendale con ispezione TLS (proxy Indra): l'SDK Anthropic (httpx) e pytrends
# (requests) si fidano solo di certifi e rifiutano la CA radice aziendale. truststore fa
# usare a Python il trust store di Windows. Deve avvenire prima di qualsiasi chiamata HTTPS.
import truststore
truststore.inject_into_ssl()

import pandas as pd
import streamlit as st

from tourism_wedge import (DEFAULT_MARKETS, SyntheticProvider,
                           fit_market, forecast_within_lead, build_card, portfolio)
from tourism_wedge.engine_aggregate import (assemble_real, fit_aggregate,
                                            forecast_aggregate, rank_markets)

MODEL = "claude-sonnet-4-6"

st.set_page_config(page_title="TDH Engine — Cruscotto", page_icon="🧭", layout="wide")


# ════════════════════════════════════════════════════════════════════════════
# STRATO MOTORE — SINTETICO (per-mercato) e REALE (aggregato, Opzione A)
# ════════════════════════════════════════════════════════════════════════════
@st.cache_data(show_spinner="Calcolo il motore (sintetico)…")
def compute_all() -> tuple[list[dict], dict]:
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
            "card": asdict(card),
            "lag": int(fit.lag), "beats_naive": bool(fit.beats_naive),
            "mae_model": float(fit.mae_model), "mae_naive": float(fit.mae_naive),
            "mape_model": float(fit.mape_model),
            "coeff_reading": fit.coefficient_reading(),
            "history": fit.df[["date", "presences", "search", "fx"]].copy(),
            "forecast": {
                "dates": [pd.Timestamp(d) for d in fc.dates],
                "mean": [float(x) for x in fc.mean],
                "lo": [float(x) for x in fc.lo],
                "hi": [float(x) for x in fc.hi],
                "lastyear": [None if pd.isna(x) else float(x) for x in fc.lastyear],
            },
        }
    ranked = portfolio(cards)
    return ranked, rows


@st.cache_data(show_spinner="Carico i dati reali (ECB · ISTAT · Google Trends)…")
def compute_real() -> dict:
    df = assemble_real(start="2019-01")
    fit = fit_aggregate(df)
    fc = forecast_aggregate(fit)
    ranked = rank_markets(df)
    obs = df.dropna(subset=["presences"])[["date", "presences"]].reset_index(drop=True)
    return {
        "ranked": ranked,
        "agg": {
            "lag": int(fit.lag), "beats_naive": bool(fit.beats_naive),
            "mae_model": float(fit.mae_model), "mae_naive": float(fit.mae_naive),
            "mape_model": float(fit.mape_model),
            "coeff_reading": fit.coefficient_reading(),
        },
        "forecast": {
            "dates": [pd.Timestamp(d) for d in fc.dates],
            "mean": [float(x) for x in fc.mean],
            "lo": [float(x) for x in fc.lo],
            "hi": [float(x) for x in fc.hi],
            "lastyear": [None if pd.isna(x) else float(x) for x in fc.lastyear],
        },
        "history": obs,
        "panel": df,
    }


# ════════════════════════════════════════════════════════════════════════════
# TOOL per l'assistente — consapevoli della modalità (ctx)
# ════════════════════════════════════════════════════════════════════════════
def _syn_code(rows, key):
    key = (key or "").strip().lower()
    return next((c for c, r in rows.items() if key in (c.lower(), r["name"].lower())), None)


def _syn_run_engine(rows, ranked):
    return json.dumps({"ranking": [
        {"rank": r["rank"], "mercato": r["market"], "raccomandazione": r["raccomandazione"],
         "opportunity_score": round(r["opportunity_score"]), "confidenza": r["confidenza"],
         "effetto_atteso": r["effetto_atteso"]} for r in ranked],
        "diagnostica": {r["name"]: {"lag_mesi": r["lag"], "batte_naive": r["beats_naive"],
                        "mape_modello_pct": round(r["mape_model"], 1)} for r in rows.values()}},
        ensure_ascii=False)


def _syn_get_market(rows, market):
    code = _syn_code(rows, market)
    if not code:
        return json.dumps({"errore": f"mercato '{market}' non trovato",
                           "mercati_validi": [r["name"] for r in rows.values()]}, ensure_ascii=False)
    r = rows[code]; fc = r["forecast"]
    return json.dumps({"mercato": r["name"], "valuta": r["currency"],
        "valore_eur_per_visitatore": r["spend_per_visitor"], "capacita_voli_ok": r["capacity_ok"],
        "scheda": r["card"], "forecast_lead_time": {
            "mesi": [str(d.date()) for d in fc["dates"]], "media": [round(x) for x in fc["mean"]],
            "intervallo80_basso": [round(x) for x in fc["lo"]], "intervallo80_alto": [round(x) for x in fc["hi"]]}},
        ensure_ascii=False)


def _syn_explain(rows, market):
    code = _syn_code(rows, market)
    if not code:
        return json.dumps({"errore": f"mercato '{market}' non trovato",
                           "mercati_validi": [r["name"] for r in rows.values()]}, ensure_ascii=False)
    r = rows[code]
    return json.dumps({"mercato": r["name"], "lag_mesi": r["lag"], "batte_naive": r["beats_naive"],
        "mape_modello_pct": round(r["mape_model"], 1), "lettura_coefficienti": r["coeff_reading"]},
        ensure_ascii=False)


def _real_card(R, market):
    key = (market or "").strip().lower()
    return next((c for c in R["ranked"] if key in (c["code"].lower(), c["market"].lower())), None)


def _real_run_engine(R):
    agg = R["agg"]
    return json.dumps({"ranking": [
        {"rank": c["rank"], "mercato": c["market"], "raccomandazione": c["raccomandazione"],
         "forza_anticipatrice": c["forza_anticipatrice"], "momentum_search_pct": c["momentum_search_pct"],
         "valore_eur_per_visitatore": c["valore_eur_per_visitatore"], "score": c["score"]}
        for c in R["ranked"]],
        "forecast_aggregato": {
            "modello": "presenze straniere totali Abruzzo ~ basket search (lag) + stagionalità + trend + dummy COVID",
            "lag_mesi": agg["lag"], "batte_naive": agg["beats_naive"],
            "mape_modello_pct": round(agg["mape_model"], 1),
            "nota": "A livello aggregato la stagionalità domina: il modello NON batte la naive, "
                    "quindi per il numero ci si appoggia al riferimento stagionale (confidenza bassa). "
                    "Il valore decisionale è nel ranking per-mercato."}},
        ensure_ascii=False)


def _real_get_market(R, market):
    c = _real_card(R, market)
    if not c:
        return json.dumps({"errore": f"mercato '{market}' non trovato",
                           "mercati_validi": [x["market"] for x in R["ranked"]]}, ensure_ascii=False)
    return json.dumps({
        "mercato": c["market"], "rank": c["rank"], "raccomandazione": c["raccomandazione"],
        "forza_anticipatrice": c["forza_anticipatrice"],
        "spiegazione_forza": f"il search '{c['market']}' anticipa gli arrivi stranieri totali di "
                             f"~{c['lag_mesi']} mesi con correlazione {c['forza_anticipatrice']} (deseasonalizzata)",
        "momentum_search_pct": c["momentum_search_pct"], "search_recente": c["search_recente"],
        "valore_eur_per_visitatore": c["valore_eur_per_visitatore"], "capacita_voli_ok": c["capacita_voli_ok"],
        "score": c["score"]}, ensure_ascii=False)


def _real_explain(R, market):
    agg = R["agg"]
    out = {"modello_aggregato": "presenze straniere totali Abruzzo (ISTAT) ~ basket search per-mercato (al lag) "
           "+ stagionalità (dummy mese) + trend + dummy COVID 2020-2021",
           "lag_mesi": agg["lag"], "batte_naive": agg["beats_naive"],
           "mape_modello_pct": round(agg["mape_model"], 1),
           "lettura_coefficienti": agg["coeff_reading"]}
    c = _real_card(R, market) if market else None
    if c:
        out["dettaglio_mercato"] = {"mercato": c["market"], "forza_anticipatrice": c["forza_anticipatrice"],
                                    "lag_mesi": c["lag_mesi"], "momentum_search_pct": c["momentum_search_pct"]}
    return json.dumps(out, ensure_ascii=False)


def run_tool(name, args, ctx):
    if ctx["mode"] == "real":
        R = ctx["R"]
        if name == "run_engine":
            return _real_run_engine(R)
        if name == "get_market":
            return _real_get_market(R, args.get("market", ""))
        if name == "explain_coefficients":
            return _real_explain(R, args.get("market", ""))
    else:
        rows, ranked = ctx["rows"], ctx["ranked"]
        if name == "run_engine":
            return _syn_run_engine(rows, ranked)
        if name == "get_market":
            return _syn_get_market(rows, args.get("market", ""))
        if name == "explain_coefficients":
            return _syn_explain(rows, args.get("market", ""))
    return json.dumps({"errore": f"tool sconosciuto: {name}"}, ensure_ascii=False)


TOOLS_SCHEMA = [
    {"name": "run_engine",
     "description": "Restituisce il ranking dei mercati e la diagnostica del forecast. "
                    "Usalo per domande di confronto tra mercati o sull'ordinamento.",
     "input_schema": {"type": "object", "properties": {}, "required": []}},
    {"name": "get_market",
     "description": "Restituisce la scheda di un singolo mercato (raccomandazione e numeri chiave). "
                    "Usalo per domande su un mercato specifico.",
     "input_schema": {"type": "object",
                      "properties": {"market": {"type": "string", "description": "Nome o codice, es. 'Germania' o 'DE'."}},
                      "required": ["market"]}},
    {"name": "explain_coefficients",
     "description": "Restituisce la lettura in italiano dei coefficienti del modello e gli errori di backtest. "
                    "Usalo quando si chiede il 'perché' o di spiegare il modello.",
     "input_schema": {"type": "object",
                      "properties": {"market": {"type": "string", "description": "Opzionale: nome o codice del mercato."}},
                      "required": []}},
]

SYSTEM_BASE = """\
Sei l'assistente del cruscotto del TDH Engine, un motore che ordina i mercati esteri \
per allocare il budget promozionale turistico della Regione Abruzzo.

Confine da rispettare SEMPRE: il motore NON stima l'effetto causale della spesa promo \
('metti X € → +Y presenze'). Ordina 'dove tira il vento e dove conviene agire', non \
promette ritorni causali. Non inventare numeri causali.

Regole: usa SEMPRE i tool per fondare le risposte sui numeri reali del motore (non a memoria); \
rispondi in italiano, conciso e orientato alla decisione come a un assessore; dai la risposta \
finale diretta senza ragionamento esplorativo visibile.
"""

SYSTEM_SYN = """
MODALITÀ ATTIVA: SINTETICO (dati di collaudo). Modello per-mercato: presenze = stagionalità \
+ search laggato + cambio + trend. Barriera di onestà: un mercato si forecasta solo se batte \
la naive stagionale. Puoi dire che i dati sono sintetici se rilevante.
"""

SYSTEM_REAL = """
MODALITÀ ATTIVA: REALE (dati veri — ECB cambio, ISTAT presenze straniere Abruzzo, Google Trends).
Disegno (Opzione A): ISTAT dà solo le presenze straniere AGGREGATE mensili (non per paese), quindi:
 • Forecast: un solo modello sulle presenze straniere totali (basket di search per-mercato al lag \
   + stagionalità + trend + dummy COVID). A livello aggregato la stagionalità domina e il modello \
   NON batte la naive: per il NUMERO ci si appoggia al riferimento stagionale (confidenza bassa, dichiarata).
 • Ranking budget: per ogni mercato = forza anticipatrice (quanto il suo search anticipa gli arrivi \
   totali) × momentum (search in salita) × valore economico × fattibilità (vincolo voli). QUI sta il \
   valore decisionale. Sii onesto su questa distinzione tra forecast (debole) e ranking (utile).
"""


# ════════════════════════════════════════════════════════════════════════════
# UI
# ════════════════════════════════════════════════════════════════════════════
st.title("🧭 TDH Engine — Allocazione budget promo per mercato estero")
mode = st.radio("Modalità dati",
                ["🧪 Sintetico (collaudo)", "🌍 Reale (ECB · ISTAT · Google Trends)"],
                horizontal=True, label_visibility="collapsed")
is_real = "Reale" in mode

if is_real:
    try:
        R = compute_real()
    except Exception as e:  # noqa: BLE001
        st.error(f"Dati reali non disponibili: {type(e).__name__}: {e}\n\n"
                 "Verifica le cache in `.cache/` (ISTAT e Google Trends) e la raggiungibilità ECB.")
        st.stop()
    ctx = {"mode": "real", "R": R}
    system_prompt = SYSTEM_BASE + SYSTEM_REAL
    st.caption("Dati REALI · presenze straniere Abruzzo (ISTAT) · cambio (ECB) · ricerca (Google Trends) · "
               "ranking = forza anticipatrice × momentum × valore × fattibilità")
else:
    ranked, rows = compute_all()
    ctx = {"mode": "synthetic", "rows": rows, "ranked": ranked}
    system_prompt = SYSTEM_BASE + SYSTEM_SYN
    st.caption("Dati SINTETICI di collaudo · modello per-mercato · "
               "ranking = momentum × valore economico × fattibilità")

col_dash, col_chat = st.columns([3, 2], gap="large")

# ──────────────────────────────── COLONNA SINISTRA ────────────────────────────────
with col_dash:
    try:
        import altair as alt
        HAVE_ALT = True
    except Exception:
        HAVE_ALT = False

    if is_real:
        # ---------- RANKING (reale) ----------
        st.subheader("Ranking mercati — dove allocare il budget")
        rank_df = pd.DataFrame([
            {"#": c["rank"], "Mercato": c["market"], "Raccomandazione": c["raccomandazione"],
             "Forza": c["forza_anticipatrice"], "Momentum %": c["momentum_search_pct"],
             "Score": round(c["score"])} for c in R["ranked"]])
        st.dataframe(rank_df, hide_index=True, use_container_width=True)

        # ---------- FORECAST AGGREGATO ----------
        agg = R["agg"]; fc = R["forecast"]
        st.subheader("Forecast presenze straniere totali (Abruzzo)")
        m1, m2, m3 = st.columns(3)
        m1.metric("Lag segnale", f"{agg['lag']} mesi")
        m2.metric("Batte la naive?", "Sì" if agg["beats_naive"] else "No")
        m3.metric("Errore backtest (MAPE)", f"{agg['mape_model']:.0f}%")
        if not agg["beats_naive"]:
            st.info("A livello aggregato la stagionalità domina: il modello non batte la naive stagionale. "
                    "Per il **numero** ci si appoggia al riferimento stagionale (confidenza bassa). "
                    "Il valore decisionale è nel **ranking** qui sopra.")

        hist = R["history"].rename(columns={"presences": "valore"}).copy()
        hist["serie"] = "storico"
        fc_mean = pd.DataFrame({"date": fc["dates"], "valore": fc["mean"], "serie": "forecast"})
        line_df = pd.concat([hist.tail(24), fc_mean], ignore_index=True)
        band_df = pd.DataFrame({"date": fc["dates"], "basso": fc["lo"], "alto": fc["hi"]})
        ly = [v for v in fc["lastyear"] if v is not None]
        ref_df = pd.DataFrame({"date": [d for d, v in zip(fc["dates"], fc["lastyear"]) if v is not None],
                               "valore": ly})
        if HAVE_ALT:
            band = alt.Chart(band_df).mark_area(opacity=0.22, color="#f59e0b").encode(
                x=alt.X("date:T", title=None), y=alt.Y("basso:Q", title="presenze straniere"), y2="alto:Q")
            lines = alt.Chart(line_df).mark_line(point=True).encode(
                x="date:T", y="valore:Q",
                color=alt.Color("serie:N", title=None, scale=alt.Scale(
                    domain=["storico", "forecast"], range=["#2563eb", "#f59e0b"])))
            layers = band + lines
            if not ref_df.empty:
                layers += alt.Chart(ref_df).mark_point(color="#16a34a", size=70, filled=True).encode(
                    x="date:T", y="valore:Q")
            st.altair_chart(layers, use_container_width=True)
            st.caption("🟦 storico · 🟧 forecast (banda 80%) · 🟢 stesso mese anno prima (riferimento)")
        else:
            st.line_chart(line_df.pivot(index="date", columns="serie", values="valore"))

        with st.expander("Lettura dei coefficienti del modello aggregato"):
            for line in agg["coeff_reading"]:
                st.markdown(f"- {line}")

        # ---------- DETTAGLIO MERCATO ----------
        st.subheader("Dettaglio mercato")
        names = [c["market"] for c in R["ranked"]]
        sel = st.selectbox("Mercato:", names, index=0)
        c = next(x for x in R["ranked"] if x["market"] == sel)
        d1, d2, d3, d4 = st.columns(4)
        d1.metric("Raccomandazione", c["raccomandazione"])
        d2.metric("Forza anticipatrice", f"{c['forza_anticipatrice']:+.2f}")
        d3.metric("Momentum ricerca", f"{c['momentum_search_pct']:+.0f}%")
        d4.metric("Valore €/visitatore", f"{c['valore_eur_per_visitatore']:.0f}")
        st.markdown(f"Il search di **{sel}** anticipa gli arrivi stranieri totali di "
                    f"~**{c['lag_mesi']} mesi** (correlazione {c['forza_anticipatrice']:+.2f}); "
                    f"interesse recente {c['search_recente']:.0f}/100, "
                    f"{'in salita' if c['momentum_search_pct'] > 0 else 'in calo'} "
                    f"({c['momentum_search_pct']:+.0f}% su anno prima).")
        scode = f"search_{c['code']}"
        s_df = R["panel"][["date", scode]].rename(columns={scode: "search"}).dropna()
        if HAVE_ALT:
            st.altair_chart(alt.Chart(s_df).mark_line(color="#7c3aed").encode(
                x=alt.X("date:T", title=None), y=alt.Y("search:Q", title="interesse di ricerca")),
                use_container_width=True)
        else:
            st.line_chart(s_df.set_index("date"))

    else:
        # ---------- SINTETICO (per-mercato) ----------
        st.subheader("Ranking mercati")
        rank_df = pd.DataFrame([
            {"#": r["rank"], "Mercato": r["market"], "Raccomandazione": r["raccomandazione"],
             "Opportunity": round(r["opportunity_score"]), "Confidenza": r["confidenza"]} for r in ranked])
        st.dataframe(rank_df, hide_index=True, use_container_width=True)

        names = [r["market"] for r in ranked]
        sel_name = st.selectbox("Scheda decisionale del mercato:", names, index=0)
        sel_code = next(c for c, r in rows.items() if r["name"] == sel_name)
        Rr = rows[sel_code]; card = Rr["card"]

        c1, c2, c3 = st.columns(3)
        c1.metric("Raccomandazione", card["raccomandazione"])
        c2.metric("Confidenza", card["confidenza"])
        c3.metric("Opportunity score", f"{round(card['opportunity_score']):,}".replace(",", "."))

        st.markdown(f"**Effetto atteso** · {card['effetto_atteso']}")
        with st.expander("Evidenza · meccanismo · rischio", expanded=True):
            st.markdown("**Evidenza**")
            for e in card["evidenza"]:
                st.markdown(f"- {e}")
            st.markdown(f"**Meccanismo** · {card['meccanismo']}")
            st.markdown(f"**Rischio** · {card['rischio']}")
            st.caption(f"Confidenza: {card['confidenza']} — {card['confidenza_perche']}")

        st.markdown("**Forecast nel lead-time (intervallo 80%)**")
        hist = Rr["history"][["date", "presences"]].rename(columns={"presences": "valore"})
        hist["serie"] = "storico"
        fc = Rr["forecast"]
        fc_mean = pd.DataFrame({"date": fc["dates"], "valore": fc["mean"], "serie": "forecast"})
        line_df = pd.concat([hist.tail(24), fc_mean], ignore_index=True)
        band_df = pd.DataFrame({"date": fc["dates"], "basso": fc["lo"], "alto": fc["hi"]})
        if HAVE_ALT:
            band = alt.Chart(band_df).mark_area(opacity=0.25, color="#f59e0b").encode(
                x=alt.X("date:T", title=None), y=alt.Y("basso:Q", title="presenze"), y2="alto:Q")
            lines = alt.Chart(line_df).mark_line(point=True).encode(
                x="date:T", y="valore:Q",
                color=alt.Color("serie:N", title=None, scale=alt.Scale(
                    domain=["storico", "forecast"], range=["#2563eb", "#f59e0b"])))
            st.altair_chart(band + lines, use_container_width=True)
        else:
            st.line_chart(line_df.pivot(index="date", columns="serie", values="valore"))

        with st.expander("Lettura dei coefficienti (per l'assessore)"):
            for line in Rr["coeff_reading"]:
                st.markdown(f"- {line}")
            st.caption(f"lag {Rr['lag']} mesi · MAPE {Rr['mape_model']:.0f}%")

    if st.button("🔄 Ricalcola motore"):
        (compute_real if is_real else compute_all).clear()
        st.rerun()


# ──────────────────────────────── COLONNA DESTRA: assistente ────────────────────────────────
with col_chat:
    st.subheader("💬 Assistente")
    cc1, cc2 = st.columns([3, 1])
    cc1.caption(f"Claude · {MODEL} · modalità {'REALE' if is_real else 'sintetica'}")
    if cc2.button("🗑 Pulisci"):
        st.session_state.messages = []
        st.rerun()

    env_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if "api_key" not in st.session_state:
        st.session_state.api_key = env_key
    if not st.session_state.api_key:
        st.session_state.api_key = st.text_input(
            "ANTHROPIC_API_KEY", type="password",
            help="A consumo, separata da Claude Code. Oppure imposta la variabile d'ambiente.")

    if "messages" not in st.session_state:
        st.session_state.messages = []

    chat_box = st.container(height=420)
    with chat_box:
        for m in st.session_state.messages:
            if m["role"] == "user" and isinstance(m["content"], str):
                with st.chat_message("user"):
                    st.markdown(m["content"])
            elif m["role"] == "assistant":
                with st.chat_message("assistant"):
                    for b in m["content"]:
                        if getattr(b, "type", None) == "text" or (isinstance(b, dict) and b.get("type") == "text"):
                            st.markdown(b.text if hasattr(b, "text") else b["text"])
                        elif getattr(b, "type", None) == "tool_use" or (isinstance(b, dict) and b.get("type") == "tool_use"):
                            nm = b.name if hasattr(b, "name") else b["name"]
                            inp = b.input if hasattr(b, "input") else b["input"]
                            st.caption(f"🔧 {nm}({', '.join(f'{k}={v}' for k, v in inp.items())})")

    prompt = st.chat_input("Chiedi all'assistente… (es. perché i Paesi Bassi sono primi?)")
    if prompt:
        if not st.session_state.api_key:
            st.warning("Inserisci una API key Anthropic per usare l'assistente.")
            st.stop()

        import anthropic
        client = anthropic.Anthropic(api_key=st.session_state.api_key)
        st.session_state.messages.append({"role": "user", "content": prompt})
        with chat_box:
            with st.chat_message("user"):
                st.markdown(prompt)

        try:
            with chat_box:
                with st.chat_message("assistant"):
                    for _ in range(6):  # guardia anti-loop sul ciclo agentico
                        placeholder = st.empty()
                        acc = ""
                        with client.messages.stream(
                            model=MODEL, max_tokens=2000, system=system_prompt,
                            thinking={"type": "disabled"},
                            tools=TOOLS_SCHEMA, messages=st.session_state.messages) as stream:
                            for delta in stream.text_stream:
                                acc += delta
                                placeholder.markdown(acc + " ▌")
                            resp = stream.get_final_message()
                        placeholder.markdown(acc) if acc else placeholder.empty()
                        st.session_state.messages.append({"role": "assistant", "content": resp.content})

                        tool_calls = [b for b in resp.content if b.type == "tool_use"]
                        for b in tool_calls:
                            st.caption(f"🔧 {b.name}({', '.join(f'{k}={v}' for k, v in b.input.items())})")
                        if resp.stop_reason != "tool_use":
                            break
                        results = []
                        for b in tool_calls:
                            out = run_tool(b.name, b.input, ctx)
                            results.append({"type": "tool_result", "tool_use_id": b.id, "content": out})
                        st.session_state.messages.append({"role": "user", "content": results})
        except anthropic.AuthenticationError:
            st.error("API key non valida.")
        except anthropic.APIError as e:
            st.error(f"Errore API: {e}")
