"""
Turism Data Hub — App multi-pagina (Streamlit + Plotly).

Avvio:
    C:\\Users\\mcenso\\tdh_venv\\Scripts\\streamlit run app.py

Due pilastri: "Cosa è successo" (descrittivo) e "Cosa fare" (prescrittivo).
Fonti reali: ISTAT · ECB · Google Trends · Banca d'Italia · Eurostat · Wikipedia.
La modalità Sintetico/Reale (barra laterale) riguarda il MOTORE dei mercati;
le viste descrittive (provincia, struttura, occupazione, spesa) usano sempre i dati reali.
"""
from __future__ import annotations

try:  # CA aziendale Indra per le chiamate HTTPS (in cloud non serve: certifi basta)
    import truststore
    truststore.inject_into_ssl()
except Exception:  # noqa: BLE001
    pass

import pandas as pd
import streamlit as st

import tdhlib as L
import update_check as U

st.set_page_config(page_title="Turism Data Hub", page_icon="⛰️", layout="wide",
                   initial_sidebar_state="expanded")
L.inject_css()

# ──────────────────────────── GATE D'ACCESSO (opzionale) ────────────────────────────
# Attivo solo se è impostato il secret APP_PASSWORD (Streamlit Cloud → Settings → Secrets).
# In locale, senza secret, non chiede nulla. Per l'accesso "su invito" vero si usa
# invece la condivisione privata di Streamlit Cloud (solo email autorizzate).
if not L.check_access():
    st.stop()

# ──────────────────────────── BARRA LATERALE (controlli) ────────────────────────────
with st.sidebar:
    st.markdown("### :material/landscape: Turism Data Hub")
    st.caption("Strumento ad uso interno · Indra")
    _regn = L.RG.region_names()
    st.selectbox("Regione", list(_regn), format_func=lambda c: _regn[c],
                 key="region_code", index=list(_regn).index(L.RG.DEFAULT_REGION),
                 help="Seleziona la regione. La pagina «Regione» mostra i dati ISTAT reali; "
                      "le altre viste sono in migrazione al multi-regione.")
    st.radio("Modalità dati", [L.MODE_REAL, L.MODE_SYN], key="mode", index=0,
             help="Riguarda il motore dei mercati (pilastro «Cosa fare»). "
                  "Le viste descrittive usano sempre i dati reali ISTAT/BdI.")
    st.slider("Periodo (viste storiche)", 2019, 2025, (2019, 2024), key="yr_range")
    bc = st.columns(2)
    if bc[0].button(":material/sync: Dati", use_container_width=True):
        for _fn in (L.compute_real, L.compute_synthetic, L.compute_provinces,
                    L.compute_structure, L.compute_occupancy):
            _fn.clear()
        st.rerun()
    if bc[1].button(":material/delete: Chat", use_container_width=True):
        st.session_state.messages = []; st.rerun()
    st.caption("Indra Italia S.p.A. · prototipo")

# ──────────────────────────── DATI DELLA MODALITÀ ────────────────────────────
try:
    ctx = L.get_context()
except Exception as e:  # noqa: BLE001
    st.error(f"Dati reali non disponibili: {type(e).__name__}: {e}\n\n"
             "Passa a **Sintetico** dalla barra laterale, o verifica le cache in `.cache/`.")
    st.stop()

summary = L.markets_summary(ctx)
is_real = ctx["mode"] == "real"


def search_panel() -> pd.DataFrame | None:
    """Pannello date × search_<code> per le pagine Timing/Analisi (entrambe le modalità)."""
    if is_real:
        return ctx["R"]["panel"]
    rows = ctx["rows"]
    df = None
    for code, r in rows.items():
        s = r["history"][["date", "search"]].rename(columns={"search": f"search_{code}"})
        df = s if df is None else df.merge(s, on="date", how="outer")
    return df.sort_values("date") if df is not None else None


# ──────────────────────────── PAGINE ────────────────────────────
def page_sintesi():
    st.subheader("Sintesi")
    if is_real:
        k = L.kpi_real(ctx["R"])
        c1, c2, c3, c4 = st.columns(4)
        c1.metric(f"Presenze straniere {k['anno']}", f"{k['presenze_anno']:,.0f}".replace(",", "."),
                  delta=f"{k['yoy']:+.0f}% vs anno prec.")
        c2.metric("Mercato top", k["top"])
        c3.metric("Mercati da spingere", k["n_aumentare"])
        c4.metric("Anticipo del segnale", f"{ctx['R']['agg']['lag']} mesi")
    else:
        st.info("Modalità sintetica (collaudo). Passa a **Reale** per i KPI sui dati veri.")

    st.markdown("#### Top mercati")
    top = summary[:3]
    for col, s in zip(st.columns(len(top)), top):
        score_txt = f"{round(s['score']):,}".replace(",", ".")
        col.markdown(f"""
        <div style="background:#fff;border:1px solid #e5e7eb;border-radius:14px;padding:16px 18px;
                    box-shadow:0 1px 3px rgba(15,23,42,.06)">
          <div style="font-size:.8rem;color:#94a3b8;font-weight:700">#{s['rank']}</div>
          <div style="font-size:1.18rem;font-weight:700;color:#0f172a;margin:2px 0 10px">{s['market']}</div>
          {L.badge_html(s['reco'])}
          <div style="color:#64748b;font-size:.85rem;margin-top:10px">score {score_txt}</div>
        </div>""", unsafe_allow_html=True)

    st.markdown("#### Ranking (opportunità per mercato)")
    st.plotly_chart(L.chart_ranking_bar(summary), use_container_width=True)


def page_regione():
    code = st.session_state.get("region_code", L.RG.DEFAULT_REGION)
    info = L.RG.region(code)
    st.header(f":material/public: {info['nome']} — quadro regionale")
    st.caption("**Multi-regione (pilota)**: dati ISTAT reali per la regione selezionata nella barra "
               "laterale. Le altre pagine sono ancora calibrate sull'Abruzzo (migrazione in corso).")
    try:
        ov = L.region_overview(code)
    except Exception as e:  # noqa: BLE001
        st.error(f"ISTAT non disponibile ora per {info['nome']} ({type(e).__name__}). "
                 "ISTAT è instabile: riprova tra poco.")
        return
    df = ov["presenze"]
    obs = df.dropna(subset=["stranieri"])
    c1, c2, c3, c4 = st.columns(4)
    if len(obs):
        c1.metric("Presenze straniere (ultimo mese)",
                  f"{int(obs['stranieri'].iloc[-1]):,}".replace(",", "."))
    if ov["letti"]:
        c2.metric(f"Posti letto ({ov['anno_letti']})", f"{ov['letti']:,}".replace(",", "."))
    sp = L.region_spend(code)
    if sp:
        c3.metric("Spesa straniera 2024 (BdI)", f"{sp[0]:,.0f} M€".replace(",", "."),
                  delta=f"#{sp[1]} su {sp[2]} regioni", delta_color="off")
    c4.metric("Aeroporti", ", ".join(info["airports"]) if info["airports"] else "—")
    st.plotly_chart(L.chart_region_presences(df), use_container_width=True)
    st.caption(f"NUTS2 **{info['code']}** · keyword Trends «{info['trends_kw']}» · "
               f"Wikipedia «{info['wiki'].get('it')}» · BdI «{info['bdi']}»")


def page_confronto_regioni():
    st.header(":material/bar_chart: Confronto tra regioni")
    st.caption("Posizionamento di **tutte le regioni** per spesa dei turisti stranieri (Banca d'Italia 2024). "
               "La regione selezionata è evidenziata. Vista nazionale del portale multi-regione.")
    code = st.session_state.get("region_code", L.RG.DEFAULT_REGION)
    st.plotly_chart(L.chart_regions_ranking(highlight=code), use_container_width=True)
    rk = L.regions_spend_ranking()
    df = pd.DataFrame([{"#": r["rank"], "Regione": r["regione"],
                        "Spesa straniera 2024 (M€)": round(r["spesa_M"])} for r in rk])
    st.dataframe(df, hide_index=True, use_container_width=True)
    st.caption("Nota BdI: Bolzano e Trento sono aggregati come «Trentino Alto Adige».")


def page_mappa():
    st.header(":material/map: Mappa dei mercati")
    st.caption("Colore = raccomandazione · dimensione bolla = score · linea = flusso verso Abruzzo")
    st.plotly_chart(L.chart_map(summary), use_container_width=True)
    with st.expander("Ranking in forma di barre"):
        st.plotly_chart(L.chart_ranking_bar(summary), use_container_width=True)


def page_ranking():
    st.header(":material/leaderboard: Ranking mercati")
    st.caption("Ordinamento per opportunità: dove conviene concentrare il budget.")
    tbl = pd.DataFrame([{"#": s["rank"], "Mercato": s["market"], "Raccomandazione": s["reco"],
                         **({"Forza": s["forza"], "Momentum %": s["momentum"]} if is_real else {}),
                         "Score": round(s["score"])} for s in summary])
    L.aggrid_table(tbl, height=300, reco_col="Raccomandazione", key="rank_grid")
    st.plotly_chart(L.chart_ranking_bar(summary), use_container_width=True)
    if is_real:
        st.subheader("Valore economico per mercato")
        st.caption("Spesa media per viaggiatore (Banca d'Italia, 2024) — peso economico reale usato nel ranking.")
        st.plotly_chart(L.chart_value_bar(summary), use_container_width=True)
        fig_conn = L.chart_connectivity()
        if fig_conn is not None:
            st.subheader("Connettività aerea diretta su Pescara")
            st.caption("Passeggeri 2024 (Eurostat avia_par) — fattibilità reale nel ranking. 0 = nessun volo diretto.")
            st.plotly_chart(fig_conn, use_container_width=True)

        st.subheader(":material/thermostat: Salute dei mercati e accessibilità — contesto decisionale")
        st.caption("Criteri di **contesto** per pesare il giudizio, **non** predittori del forecast: "
                   "il bake-off mostra che non battono la stagionalità. Vanno letti con incertezza.")
        hc1, hc2 = st.columns(2)
        with hc1:
            health = L.market_health()
            if health:
                st.markdown("**Salute mercato** · fiducia dei consumatori")
                hdf = pd.DataFrame([{"Mercato": k, "Fiducia (saldo)": v["conf"],
                                     "Trend ~6 mesi": v["label"]} for k, v in health.items()])
                st.dataframe(hdf, hide_index=True, use_container_width=True)
                st.caption("DE/AT/NL (Eurostat). Saldo negativo = pessimismo; conta soprattutto il trend.")
        with hc2:
            fig_fl = L.chart_flights_monthly()
            if fig_fl is not None:
                st.markdown("**Accessibilità aerea nel tempo** · Pescara")
                st.plotly_chart(fig_fl, use_container_width=True)


def page_forecast():
    if is_real:
        R = ctx["R"]; agg = R["agg"]
        st.header(":material/trending_up: Forecast presenze straniere totali (Abruzzo)")
        m1, m2, m3 = st.columns(3)
        m1.metric("Lag segnale", f"{agg['lag']} mesi")
        m2.metric("Batte la naive?", "Sì" if agg["beats_naive"] else "No")
        m3.metric("Errore backtest (MAPE)", f"{agg['mape_model']:.0f}%")
        if not agg["beats_naive"]:
            st.info("A livello aggregato la stagionalità domina: il modello non batte la naive. "
                    "Per il **numero** si usa il riferimento stagionale (confidenza bassa); "
                    "il valore decisionale è nel **ranking**.")
        st.plotly_chart(L.chart_forecast(R["history"], R["forecast"], "presenze straniere"),
                        use_container_width=True)
        with st.expander("Lettura dei coefficienti del modello aggregato"):
            for line in agg["coeff_reading"]:
                st.markdown(f"- {line}")
    else:
        rows = ctx["rows"]
        st.header(":material/trending_up: Forecast per mercato")
        sel = st.selectbox("Mercato:", [s["market"] for s in summary])
        code = next(c for c, r in rows.items() if r["name"] == sel)
        Rr = rows[code]
        st.plotly_chart(L.chart_forecast(Rr["history"][["date", "presences"]], Rr["forecast"], "presenze"),
                        use_container_width=True)
        with st.expander("Lettura dei coefficienti"):
            for line in Rr["coeff_reading"]:
                st.markdown(f"- {line}")


def page_dettaglio():
    st.header(":material/search: Dettaglio mercato")
    names = [s["market"] for s in summary]
    sel = st.selectbox("Mercato:", names)
    if is_real:
        s = next(x for x in summary if x["market"] == sel)
        st.markdown(L.badge_html(s["reco"]) + f"&nbsp;&nbsp;<b>{s['reco']}</b>", unsafe_allow_html=True)
        ext = L.bdi_extended()
        stay = (ext.get("durata_media_2024", {}) if ext else {}).get(s["code"])
        d1, d2, d3, d4 = st.columns(4)
        d1.metric("Forza anticipatrice", f"{s['forza']:+.2f}")
        d2.metric("Momentum ricerca", f"{s['momentum']:+.0f}%")
        d3.metric("Valore €/viaggiatore", f"{s['valore']:.0f}")
        d4.metric("Durata media", f"{stay:.1f} notti" if stay else "—")
        h = L.market_health().get(s["code"])
        if h:
            st.caption(f":material/thermostat: **Salute mercato** (fiducia consumatori {s['code']}): saldo {h['conf']:+.1f} "
                       f"· {h['label']} — contesto decisionale, non previsione.")
        else:
            st.caption(":material/thermostat: Salute mercato: fiducia consumatori non disponibile per questo mercato (solo DE/AT/NL).")
        st.plotly_chart(L.chart_search(ctx["R"]["panel"], s["code"]), use_container_width=True)
    else:
        rows = ctx["rows"]
        code = next(c for c, r in rows.items() if r["name"] == sel)
        card = rows[code]["card"]
        m1, m2 = st.columns(2)
        m1.metric("Raccomandazione", card["raccomandazione"])
        m2.metric("Confidenza", card["confidenza"])
        st.markdown(f"**Effetto atteso** · {card['effetto_atteso']}")
        with st.expander("Evidenza · meccanismo · rischio", expanded=True):
            for e in card["evidenza"]:
                st.markdown(f"- {e}")
            st.markdown(f"**Meccanismo** · {card['meccanismo']}")
            st.markdown(f"**Rischio** · {card['rischio']}")


def page_allocatore():
    st.header(":material/savings: Allocatore di budget")
    st.caption("Ripartizione proporzionale allo score. NON è una stima causale: indica dove conviene "
               "concentrare, non quanto renderà.")
    c1, c2 = st.columns([1, 2])
    total = c1.number_input("Budget promo totale (€)", min_value=0, value=500000, step=50000)
    cats = c2.multiselect("Includi raccomandazioni:", ["Aumentare", "Mantenere", "Monitorare"],
                          default=["Aumentare"])
    alloc = L.allocate_budget(summary, float(total), set(cats))
    tcol, gcol = st.columns([1, 1])
    with tcol:
        adf = pd.DataFrame([{"Mercato": a["market"], "Raccomandazione": a["reco"],
                             "Quota %": round(a["quota_pct"]), "€": round(a["quota_eur"])}
                            for a in alloc if a["quota_eur"] > 0])
        L.aggrid_table(adf, height=300, reco_col="Raccomandazione", key="alloc_grid")
    with gcol:
        any_alloc = any(a["quota_eur"] > 0 for a in alloc)
        if any_alloc:
            st.plotly_chart(L.chart_allocation(alloc), use_container_width=True)
        else:
            st.warning("Nessun mercato idoneo con le categorie selezionate.")


def page_timing():
    st.header(":material/calendar_month: Timing stagionale")
    st.caption("Quando l'interesse di ricerca di ogni mercato è al massimo → quando anticipare la campagna "
               "(il search precede gli arrivi).")
    panel = search_panel()
    if panel is None:
        st.info("Dati di ricerca non disponibili.")
        return
    st.plotly_chart(L.chart_seasonal_heatmap(panel, summary), use_container_width=True)
    st.caption("Più scuro = mese di picco dell'interesse per quel mercato (normalizzato per riga).")


def page_assistente():
    st.header(":material/forum: Assistente")
    st.caption(f"Claude · {L.MODEL} · modalità {'REALE' if is_real else 'sintetica'} · "
               "risponde sui numeri del motore")
    L.render_assistant(ctx)


def page_gestione_dati():
    st.header(":material/database: Gestione dati")
    st.caption("Dati presenti, candidati in valutazione (con nulla osta), copertura temporale e caricamento file.")

    st.subheader(":material/table: Tabella Dati Presenti")
    st.caption("Tutte le fonti attualmente in uso dal motore: reali, candidati approvati e file caricati.")
    L.aggrid_table(pd.DataFrame(L.present_sources(), columns=L.SRC_COLS), height=320, key="present_grid")

    st.subheader(":material/science: Tabella dei Dati in Valutazione")
    st.caption("Fonti candidate proposte per il TDH. Verifica la disponibilità, valida la descrizione "
               "e dai il **nulla osta** per caricarle.")
    pend = L.pending_candidates()
    if not pend:
        st.success("Nessun candidato in attesa: tutte le fonti proposte sono già state approvate.")
    else:
        L.aggrid_table(pd.DataFrame(pend, columns=L.SRC_COLS), height=150, key="pending_grid")
        approved_ids = {cid for cid, s in L.candidates_state().items() if s.get("approved")}
        for c in L.CANDIDATES:
            if c["id"] in approved_ids:
                continue
            with st.container(border=True):
                st.markdown(f"**{c['nome']}** · {c['fonte']} · "
                            f"<a href='{c['url']}' target='_blank'>{c['url']}</a> · {c['frequenza']}",
                            unsafe_allow_html=True)
                descr = st.text_area("Descrizione (valida o modifica)", value=c["descrizione"],
                                     key="desc_" + c["id"], height=70)
                colv, cola = st.columns([1, 1])
                if colv.button(":material/search: Verifica disponibilità", key="probe_" + c["id"], use_container_width=True):
                    with st.spinner("Verifica in corso…"):
                        st.session_state["pr_" + c["id"]] = c["probe"]()
                pr = st.session_state.get("pr_" + c["id"])
                if pr:
                    (st.success if pr["ok"] else st.error)(pr["msg"])
                    if pr.get("preview"):
                        st.caption("Anteprima: " + pr["preview"])
                if cola.button(":material/check_circle: Approva e carica", key="appr_" + c["id"], type="primary",
                               use_container_width=True):
                    with st.spinner("Caricamento dei dati…"):
                        res = L.approve_candidate(c["id"], descr)
                    if res.get("ok"):
                        st.success(f"Caricato: {res.get('msg', 'ok')}")
                        st.rerun()
                    else:
                        st.error(res.get("msg", "caricamento fallito"))

    st.subheader(":material/grid_view: Copertura dati — Nazionale · Regionale · Provinciale")
    st.caption("Cosa abbiamo a ciascun livello geografico (✅ disponibile · 🟡 parziale · ❌ assente). "
               "Serve a vedere i **buchi** da coprire per il portale multi-regione.")
    st.dataframe(pd.DataFrame(L.coverage_matrix(), columns=L.COVERAGE_COLS),
                 hide_index=True, use_container_width=True)
    st.caption("🔴 Buchi principali: presenze **per paese a livello regionale**, **anagrafica strutture**, "
               "spesa per paese regionale, accessibilità ferroviaria regionale.")

    st.subheader(":material/sync: Stato e aggiornamento delle fonti")
    lr = U.last_run_info()
    cap = ("Giudizio istantaneo dalla cache — 🟢 fresco · 🟡 da controllare · "
           "🔴 probabile dato nuovo · ⚪ ignoto. Il controllo *live* riscarica e conferma cosa è cambiato.")
    if lr:
        cap += f"  ·  Ultimo controllo live: {lr['last_run'][:16].replace('T', ' ')}"
    st.caption(cap)
    _stat = U.status_all()
    st.dataframe(
        pd.DataFrame(_stat)[["stato", "fonte", "cadenza", "ultimo_dato", "righe", "scaricato"]]
        .rename(columns={"stato": "Stato", "fonte": "Fonte", "cadenza": "Cadenza",
                         "ultimo_dato": "Ultimo dato", "righe": "Righe", "scaricato": "Scaricato"}),
        hide_index=True, use_container_width=True)

    if st.button(":material/sync: Controlla aggiornamenti (live)",
                 help="Riscarica le fonti aggiornabili (ISTAT, Trends, ECB) e confronta con la cache. "
                      "Può richiedere 1–2 minuti (ISTAT è lento)."):
        with st.spinner("Controllo live in corso… (ISTAT può essere lento)"):
            st.session_state["upd_live"] = U.live_check()

    _live = st.session_state.get("upd_live")
    if _live:
        st.markdown("**Esito ultimo controllo live**")
        for r in _live:
            box = st.warning if r["nuovo"] else (st.error if r["stato"] == "🔴" else st.success)
            box(f"{r['stato']} {r['fonte']}: {r['esito']}")
            if r["nuovo"]:
                if st.button(f"⬇️ Aggiorna «{r['fonte']}» nella cache (nulla osta)",
                             key="apply_" + r["key"], type="primary"):
                    with st.spinner("Riscarico e aggiorno la cache…"):
                        ar = U.apply_update(r["key"])
                    if ar["ok"]:
                        st.cache_data.clear()
                        st.success(ar["msg"] + " · cache rigenerata.")
                        st.rerun()
                    else:
                        st.error(ar["msg"])
        st.caption("In locale l'aggiornamento resta sul tuo PC. Per portarlo anche sull'app online "
                   "serve un `git push` (oppure ci penserà la schedulazione automatica — Fase 2).")

    st.subheader("Copertura temporale delle serie")
    st.caption("Le serie hanno archi temporali diversi: ecco da quando a quando ciascuna è disponibile.")
    st.plotly_chart(L.chart_coverage(L.series_coverage()), use_container_width=True)

    st.subheader("Carica un nuovo file")
    with st.form("upload_dati", clear_on_submit=True):
        up = st.file_uploader("File dati", type=["csv", "xlsx", "xls", "json", "geojson", "txt"])
        c1, c2 = st.columns(2)
        nome = c1.text_input("Nome dataset")
        fonte = c2.text_input("Fonte", placeholder="Ente di provenienza")
        url = st.text_input("URL", placeholder="https://… (dove è stato preso)")
        descr = st.text_area("Descrizione", placeholder="Cosa contiene, periodo, granularità, note…")
        ok = st.form_submit_button("💾 Salva file e metadati")
    if ok:
        if not up:
            st.warning("Seleziona un file da caricare.")
        else:
            rec = L.save_upload(up, nome, descr, fonte, url)
            st.success(f"Caricato **{rec['nome']}** · {rec['dimensione_kb']} KB"
                       + (f" · {rec['righe']} righe" if rec["righe"] is not None else ""))
            st.rerun()

    st.subheader("File caricati")
    reg = L.load_registry()
    if not reg:
        st.info("Nessun file caricato finora.")
    else:
        for r in reversed(reg):
            c1, c2 = st.columns([8, 1])
            with c1:
                righe = f"{r['righe']} righe · " if r.get("righe") is not None else ""
                st.markdown(f"**{r['nome']}**  ·  <span style='color:#64748b'>{r['file']} · "
                            f"{righe}{r['dimensione_kb']} KB · {r['caricato']}</span>", unsafe_allow_html=True)
                if r.get("descrizione"):
                    st.caption("📝 " + r["descrizione"])
                if r.get("fonte"):
                    st.caption("🔗 " + r["fonte"])
            if c2.button(":material/delete:", key="del_" + r["id"], help="Elimina"):
                L.delete_upload(r["id"]); st.rerun()
            st.divider()


def page_azioni():
    st.header(":material/ads_click: Azioni raccomandate")
    st.caption("Suggerimenti operativi dai dati: dove e quando agire. "
               "Stime d'opportunità, non garanzie di ritorno.")
    if not is_real:
        st.info("Le azioni sfruttano i dati reali (forza anticipatrice, momentum, stagionalità). "
                "Passa a modalità **Reale** per indicazioni complete.")
    pr_color = {"Alta": "#dc2626", "Media": "#f59e0b", "Bassa": "#94a3b8"}
    for a in L.recommended_actions(ctx):
        with st.container(border=True):
            c1, c2 = st.columns([5, 1])
            with c1:
                st.markdown(
                    f"<span style='background:{pr_color[a['priorita']]}1f;color:{pr_color[a['priorita']]};"
                    f"padding:2px 10px;border-radius:999px;font-size:.72rem;font-weight:700'>"
                    f"PRIORITÀ {a['priorita'].upper()}</span>&nbsp;&nbsp;{L.badge_html(a['reco'])}"
                    f"&nbsp;&nbsp;<b style='font-size:1.05rem'>{a['market']}</b>", unsafe_allow_html=True)
                bits = []
                if a["forza"] is not None:
                    bits.append(f"forza {a['forza']:+.2f}")
                if a["momentum"] is not None:
                    bits.append(f"momentum {a['momentum']:+.0f}%")
                if a["valore"] is not None:
                    bits.append(f"valore €{a['valore']:.0f}/visit.")
                if a["picco_mese"]:
                    bits.append(f"picco ricerca {L.MONTHS_IT[a['picco_mese'] - 1]}")
                st.caption(" · ".join(bits))
            if c2.button(":material/edit: Crea campagna", key="camp_" + str(a["code"]), use_container_width=True):
                st.session_state["camp_open"] = a["code"]
            if st.session_state.get("camp_open") == a["code"]:
                br = L.campaign_brief(ctx, a["code"])
                if br:
                    st.markdown(f"**Bozza campagna — {br['mercato']}** · priorità {br['priorita']}")
                    st.markdown(f"- **Azione**: {br['azione']}")
                    st.markdown(f"- **Finestra temporale**: {br['finestra']}")
                    st.markdown(f"- **Leva / messaggio**: {br['leva']}")
                    st.markdown(f"- **KPI da monitorare**: {br['kpi']}")
                    st.caption("⚠️ " + br["nota"])


def page_architettura():
    st.header(":material/account_tree: Architettura & sorgenti dati")
    st.caption("La visione completa del Turism Data Hub e lo stato delle sorgenti.")
    A = L.tdh_architecture()
    st.subheader("Architettura a 5 livelli")
    for nome, desc in A["livelli"]:
        st.markdown(f"**{nome}** — {desc}")
    st.subheader("Sorgenti dati")
    L.aggrid_table(pd.DataFrame(A["sorgenti"]), height=360, key="arch_src")
    st.caption("🟢 Attiva (già nel motore) · 🟡 Pianificata · ⚪ Da valutare")
    cR, cP = st.columns(2)
    with cR:
        st.subheader("Roadmap")
        for r in A["roadmap"]:
            st.markdown(f"- {r}")
    with cP:
        st.subheader("Principi guida")
        for p in A["principi"]:
            st.markdown(f"- {p}")


def page_province():
    st.header(":material/place: Presenze per provincia")
    st.caption("Distribuzione territoriale delle presenze in Abruzzo — dati ISTAT, ultimi 12 mesi.")
    try:
        P = L.compute_provinces()
    except Exception as e:  # noqa: BLE001
        st.error(f"Dati province non disponibili: {type(e).__name__}: {e}")
        return
    st.plotly_chart(L.chart_province_map(P["rows"]), use_container_width=True)
    st.subheader("Riepilogo per provincia")
    tbl = pd.DataFrame([{"Provincia": r["provincia"], "Presenze": round(r["presenze"]),
                         "Stranieri": round(r["stranieri"]),
                         "Quota stranieri %": round(r["quota_stranieri"])} for r in P["rows"]])
    L.aggrid_table(tbl, height=190, key="prov_grid")
    st.plotly_chart(L.chart_province_bar(P["rows"]), use_container_width=True)

    yr = st.session_state.get("yr_range", (2019, 2024))
    panel = P["panel"]
    last = panel["date"].max()
    preset = st.selectbox("Periodo del trend:",
                          ["Slider barra laterale", "Ultimo mese", "Ultimi 12 mesi",
                           "Ultimi 2 anni", "Ultimi 5 anni"], index=2)
    _mesi = {"Ultimo mese": 1, "Ultimi 12 mesi": 12, "Ultimi 2 anni": 24, "Ultimi 5 anni": 60}
    if preset in _mesi:
        cutoff = last - pd.DateOffset(months=_mesi[preset] - 1)
        pf, label = panel[panel["date"] >= cutoff], preset.lower()
    else:
        pf, label = L.filter_years(panel, yr), f"{yr[0]}–{yr[1]}"
    st.subheader(f"Trend mensile per provincia · {label}")
    st.plotly_chart(L.chart_province_trend(pf, rangeslider=True), use_container_width=True)
    st.caption("Usa il menu per i preset rapidi, oppure trascina la barra/il cursore sul grafico "
               "per restringere l'intervallo a mano.")


def page_struttura():
    st.header(":material/hotel: Presenze per tipologia di struttura")
    st.caption("Alberghiero vs extra-alberghiero in Abruzzo — dati ISTAT, ultimi 12 mesi.")
    try:
        S = L.compute_structure()
    except Exception as e:  # noqa: BLE001
        st.error(f"Dati struttura non disponibili: {type(e).__name__}: {e}")
        return
    tot = S["alberghiero"] + S["extra"]
    c1, c2, c3 = st.columns(3)
    c1.metric("Alberghiero (12 mesi)", f"{S['alberghiero']:,.0f}".replace(",", "."))
    c2.metric("Extra-alberghiero", f"{S['extra']:,.0f}".replace(",", "."))
    c3.metric("Quota alberghiero", f"{S['alberghiero'] / tot * 100:.0f}%" if tot else "—")
    st.plotly_chart(L.chart_structure_donut(S), use_container_width=True)
    yr = st.session_state.get("yr_range", (2019, 2024))
    st.subheader(f"Trend mensile · {yr[0]}–{yr[1]}")
    st.plotly_chart(L.chart_structure_trend(L.filter_years(S["panel"], yr)), use_container_width=True)


def page_occupazione():
    st.header(":material/king_bed: Tasso di occupazione (reale)")
    st.caption("Indice di utilizzazione lorda dei posti letto = presenze ÷ (posti letto × giorni del mese). Dati ISTAT.")
    try:
        O = L.compute_occupancy()
    except Exception as e:  # noqa: BLE001
        st.error(f"Dati occupazione non disponibili: {type(e).__name__}: {e}")
        return
    if not O["available"]:
        st.info("⏳ In attesa dei dati di **capacità ricettiva** ISTAT (posti letto): il download è in corso "
                "(ISTAT è temporaneamente lento). Ricarica tra qualche minuto, o premi **:material/sync: Dati** nella barra laterale.")
        return
    c1, c2, c3 = st.columns(3)
    c1.metric("Occupazione media (12 mesi)", f"{O['occ_media12']:.0f}%")
    c2.metric("Posti letto (Abruzzo)", f"{O['letti_ultimo']:,}".replace(",", "."))
    c3.metric("Anno capacità", O["anno_letti"])
    yr = st.session_state.get("yr_range", (2019, 2024))
    pan = L.filter_years(O["panel"], yr)
    st.caption(f"Periodo selezionato: {yr[0]}–{yr[1]}")
    st.plotly_chart(L.chart_occupancy(pan), use_container_width=True)
    st.subheader("Stagionalità dell'occupazione")
    st.plotly_chart(L.chart_occupancy_season(pan), use_container_width=True)
    st.caption("Indice di utilizzazione lorda: presenze rapportate alla capacità teorica (posti letto × giorni del mese).")


def page_operatori():
    st.header(":material/badge: Vista operatori (demo)")
    L.demo_banner()
    prov = st.selectbox("Filtra per provincia:", ["Tutte", "L'Aquila", "Teramo", "Pescara", "Chieti"])
    d = L.demo_operators(prov)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Tasso occupazione", f"{d['occupazione']}%")
    c2.metric("Prezzo medio (ADR)", f"€ {d['adr']}")
    c3.metric("Punteggio qualità", f"{d['qualita']}/5")
    c4.metric("Tasso conversione", f"{d['conversione']}%")
    a, b = st.columns(2)
    with a:
        st.subheader("Canali di acquisizione")
        st.plotly_chart(L.chart_demo_channels(d["canali"]), use_container_width=True)
    with b:
        st.subheader("Funnel di prenotazione")
        st.plotly_chart(L.chart_demo_funnel(d["funnel"]), use_container_width=True)
    st.subheader("Affluenza prevista — prossimi 7 giorni")
    st.plotly_chart(L.chart_demo_weekly(d["weekly"]), use_container_width=True)
    e, f = st.columns(2)
    with e:
        st.subheader("Recensioni")
        st.plotly_chart(L.chart_demo_reviews(d["recensioni"]), use_container_width=True)
    with f:
        st.subheader("Cosa cercano i turisti")
        chips = " ".join(
            f"<span style='background:#e0f2fe;color:#0e7490;padding:5px 12px;border-radius:999px;"
            f"font-size:.85rem;margin:3px;display:inline-block'>{q}</span>" for q in d["queries"])
        st.markdown(chips, unsafe_allow_html=True)
    st.caption("Dati simulati · Indra Italia · prototipo. In produzione: Registro ricettivo · OTA/booking · GA4 portale.")


def page_spesa():
    st.header(":material/payments: Spesa turistica (Banca d'Italia)")
    st.caption("Spesa dei turisti stranieri — Abruzzo e contesto nazionale. Indagine turismo internazionale, 2024.")
    ext = L.bdi_extended()
    if not ext:
        st.info("Dati Banca d'Italia non disponibili.")
        return
    a = ext["abruzzo"]
    sp, notti, viagg = a["spesa"][-1], a["notti"][-1], a["viaggiatori"][-1]
    durata = notti / viagg if viagg else 0
    spnotte = sp * 1e6 / (notti * 1e3) if notti else 0
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Spesa straniera Abruzzo 2024", f"{sp:.0f} M€")
    c2.metric("Pernottamenti", f"{notti / 1000:.1f} mln")
    c3.metric("Durata media", f"{durata:.1f} notti")
    c4.metric("Spesa per notte", f"€ {spnotte:.0f}")
    yr = st.session_state.get("yr_range", (2019, 2024))
    st.subheader(f"Spesa straniera in Abruzzo · {yr[0]}–{yr[1]}")
    st.plotly_chart(L.chart_abruzzo_spend(ext, yr), use_container_width=True)
    st.subheader("Confronto regioni — spesa turisti stranieri 2024")
    st.plotly_chart(L.chart_regions_spend(ext), use_container_width=True)
    cA, cB = st.columns(2)
    with cA:
        st.subheader("Per motivo del viaggio")
        st.caption("Dato nazionale (turisti stranieri in Italia)")
        st.plotly_chart(L.chart_bdi_motivo(ext), use_container_width=True)
    with cB:
        st.subheader("Per tipo di struttura")
        st.caption("Dato nazionale (turisti stranieri in Italia)")
        st.plotly_chart(L.chart_bdi_struttura(ext), use_container_width=True)


def page_mercati_paese():
    st.header(":material/public: Mercati per paese (Banca d'Italia)")
    st.caption("Quali mercati esteri contano e come si muovono nel tempo — dato **nazionale** (Italia) per "
               "paese di origine, indagine BdI. Contesto strategico per leggere i mercati; non è il dato "
               "regionale dell'Abruzzo (che ISTAT non espone per singolo paese).")
    g = L.bdi_country_annual()
    if g is None or g.empty:
        st.info("Dati Banca d'Italia per paese non disponibili.")
        return
    metric = st.radio("Metrica:", ["notti", "spesa", "viaggiatori"], horizontal=True)
    st.plotly_chart(L.chart_bdi_country(metric), use_container_width=True)
    last = int(g["anno"].max())
    cur = g[g["anno"] == last].set_index("code")
    prev = g[g["anno"] == last - 1].set_index("code")
    rows = []
    for code in L.BDI_MARKETS:
        if code in cur.index:
            v = cur.loc[code, metric]
            p = prev.loc[code, metric] if code in prev.index else None
            yoy = (v / p - 1) * 100 if (p and p != 0) else None
            rows.append({"Mercato": code, f"{metric.capitalize()} {last}": round(v),
                         "var. % a/a": (f"{yoy:+.0f}%" if yoy is not None else "—")})
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    st.caption("Unità BdI: notti e viaggiatori in migliaia, spesa in milioni di €. "
               "Mercati: Germania, Austria, Regno Unito, Svizzera, USA, Francia, Spagna.")


def page_online():
    st.header(":material/language: Interesse online (segnali anticipatori)")
    st.caption("Google Trends (per paese) e Wikipedia pageviews (per lingua) anticipano gli arrivi. "
               "Wikipedia corrobora il segnale; è per LINGUA, quindi DE/AT/CH condividono il tedesco e GB/US l'inglese.")
    yr = st.session_state.get("yr_range", (2019, 2024))
    st.subheader(f"Wikipedia — interesse per «Abruzzo» per lingua · {yr[0]}–{yr[1]}")
    st.plotly_chart(L.chart_wiki(yr), use_container_width=True)
    st.subheader("Corroborazione del segnale per mercato")
    if is_real:
        L.aggrid_table(pd.DataFrame(L.online_interest(summary)), height=240, key="online_grid")
        st.caption("Concordanza = Google Trends e Wikipedia indicano la stessa direzione → segnale più robusto.")
    else:
        st.info("La corroborazione con Google Trends è disponibile in modalità **Reale**.")


def page_home():
    uri = L.home_hero_datauri()
    bg = (f"linear-gradient(120deg, rgba(15,23,42,.62), rgba(124,45,18,.28) 55%, rgba(8,145,178,.52)), url('{uri}')"
          if uri else "linear-gradient(120deg,#0f172a,#7c2d12 55%,#0e7490)")
    st.markdown(f"""
    <div style="position:relative;border-radius:18px;overflow:hidden;height:430px;
                background-image:{bg};background-size:cover;background-position:center;
                box-shadow:0 12px 34px rgba(2,6,23,.35);display:flex;align-items:center;
                justify-content:center;text-align:center;color:#fff">
      <div style="max-width:760px;padding:24px">
        <div style="display:inline-flex;align-items:center;gap:14px;background:rgba(255,255,255,.13);
                    border:1px solid rgba(255,255,255,.28);padding:12px 20px;border-radius:16px">
          {L.LOGO_SVG}
          <div style="text-align:left">
            <div style="font-size:1.9rem;font-weight:800;line-height:1.05">Turism Data Hub</div>
            <div style="font-size:.78rem;letter-spacing:.16em;opacity:.92">REGIONE ABRUZZO</div>
          </div>
        </div>
        <div style="font-size:1.18rem;margin-top:22px;opacity:.96;text-shadow:0 1px 10px rgba(0,0,0,.45)">
          Dove e quando investire il budget promozionale sui mercati esteri —<br>
          con dati reali e segnali che anticipano gli arrivi.
        </div>
      </div>
    </div>""", unsafe_allow_html=True)

    _, cmid, _ = st.columns([1, 1, 1])
    if cmid.button("Entra nel cruscotto  →", use_container_width=True, type="primary"):
        st.switch_page(SINTESI_PAGE)

    st.write("")
    h1, h2, h3 = st.columns(3)
    h1.markdown("##### 🌍 Mercati esteri\nRanking dei paesi per opportunità, da **ISTAT · ECB · Google Trends**.")
    h2.markdown("##### 📈 Segnali anticipatori\nL'interesse di ricerca precede gli arrivi: agisci **prima** della stagione.")
    h3.markdown("##### 🎯 Azioni & budget\nDove concentrare la spesa e **bozze di campagna** pronte.")
    st.caption("Prototipo dimostrativo · Indra Italia S.p.A. per Regione Abruzzo")


# ──────────────────── NAVIGAZIONE A DUE PILASTRI (st.navigation) + DISPATCH ────────────────────
SINTESI_PAGE = st.Page(page_sintesi, title="Sintesi", icon=":material/dashboard:")
pg = st.navigation({
    "Panoramica": [
        st.Page(page_home, title="Home", icon=":material/home:", default=True),
        SINTESI_PAGE,
        st.Page(page_regione, title="Regione", icon=":material/public:"),
        st.Page(page_confronto_regioni, title="Confronto regioni", icon=":material/bar_chart:"),
    ],
    "Cosa è successo": [
        st.Page(page_province, title="Per provincia", icon=":material/place:"),
        st.Page(page_struttura, title="Per struttura", icon=":material/hotel:"),
        st.Page(page_occupazione, title="Occupazione", icon=":material/king_bed:"),
        st.Page(page_spesa, title="Spesa turistica", icon=":material/payments:"),
        st.Page(page_mercati_paese, title="Mercati per paese", icon=":material/public:"),
        st.Page(page_operatori, title="Operatori (demo)", icon=":material/person:"),
    ],
    "Cosa fare": [
        st.Page(page_ranking, title="Ranking mercati", icon=":material/leaderboard:"),
        st.Page(page_mappa, title="Mappa", icon=":material/map:"),
        st.Page(page_dettaglio, title="Dettaglio mercato", icon=":material/search:"),
        st.Page(page_forecast, title="Forecast presenze", icon=":material/trending_up:"),
        st.Page(page_timing, title="Timing", icon=":material/calendar_month:"),
        st.Page(page_online, title="Interesse online", icon=":material/language:"),
        st.Page(page_azioni, title="Azioni", icon=":material/ads_click:"),
        st.Page(page_allocatore, title="Allocatore", icon=":material/savings:"),
    ],
    "Sistema": [
        st.Page(page_assistente, title="Assistente", icon=":material/forum:"),
        st.Page(page_architettura, title="Architettura", icon=":material/account_tree:"),
        st.Page(page_gestione_dati, title="Gestione dati", icon=":material/database:"),
    ],
})
if pg.title != "Home":
    L.hero("Allocazione del budget promozionale tra i mercati esteri",
           "Dati reali" if is_real else "Dati sintetici")
pg.run()
