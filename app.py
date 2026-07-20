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
# Logo in testa (sopra il menu della sidebar) + icona quando la sidebar è chiusa.
try:
    st.logo("assets/tdh_logo.svg", size="large", icon_image="assets/tdh_icon.svg")
except Exception:  # noqa: BLE001 (versioni Streamlit senza st.logo)
    pass

# Regione attiva: sempre presente in session_state (default «Italia» = vista d'insieme).
st.session_state.setdefault("region_code", L.RG.NATIONAL)
# Riconcilia un'eventuale selezione regione fatta cliccando la mappa d'Italia:
# va applicata PRIMA che il selectbox «region_code» venga istanziato.
if st.session_state.get("_map_region"):
    st.session_state["region_code"] = st.session_state.pop("_map_region")

# ──────────────────────────── GATE D'ACCESSO (opzionale) ────────────────────────────
# Attivo solo se è impostato il secret APP_PASSWORD (Streamlit Cloud → Settings → Secrets).
# In locale, senza secret, non chiede nulla. Per l'accesso "su invito" vero si usa
# invece la condivisione privata di Streamlit Cloud (solo email autorizzate).
if not L.check_access():
    st.stop()

# ──────────────────────────── BARRA LATERALE (controlli) ────────────────────────────
with st.sidebar:
    # Il logo è in testa via st.logo() (sopra il menu). Qui restano i controlli.
    st.caption("CONTROLLI")
    # NB: il selettore Regione è nella TOPBAR (in alto a destra).
    st.radio("Modalità dati", [L.MODE_REAL, L.MODE_SYN], key="mode", index=0,
             help="Riguarda il motore dei mercati (pilastro «Cosa fare»). "
                  "Le viste descrittive usano sempre i dati reali ISTAT/BdI.")
    st.slider("Periodo (viste storiche)", 2019, 2025, (2019, 2024), key="yr_range")
    bc = st.columns(2)
    if bc[0].button(":material/sync: Dati", use_container_width=True):
        for _fn in (L.compute_real, L.compute_synthetic, L.compute_provinces,
                    L.compute_structure, L.compute_occupancy):
            _fn.clear()
        L.clear_data_caches()  # svuota anche le lru_cache del data-layer tdh_data
        st.rerun()
    if bc[1].button(":material/delete: Chat", use_container_width=True):
        st.session_state.messages = []; st.rerun()
    st.caption("Indra Italia S.p.A. · prototipo")
    st.caption("Powered by MDC")

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
    L.page_header("Sintesi", group="Panoramica", emoji="📊",
                  region_code=st.session_state.get("region_code", L.RG.DEFAULT_REGION),
                  subtitle="I numeri chiave della regione e i mercati su cui conviene agire.")
    if is_real:
        k = L.kpi_real(ctx["R"])
        yoy = k["yoy"]
        L.kpi_row([
            {"label": f"Presenze straniere {k['anno']}",
             "value": f"{k['presenze_anno']:,.0f}".replace(",", "."),
             "delta": f"{yoy:+.0f}% vs anno prec.",
             "delta_dir": "up" if yoy > 0 else ("down" if yoy < 0 else "flat")},
            {"label": "Mercato top", "value": k["top"]},
            {"label": "Mercati da spingere", "value": k["n_aumentare"]},
            {"label": "Anticipo del segnale", "value": f"{ctx['R']['agg']['lag']} mesi"},
        ])
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
    st.subheader("Grafico 1 — Ranking dei mercati")
    st.plotly_chart(L.chart_ranking_bar(summary), use_container_width=True)


def page_italia():
    L.page_header("Italia", group="Panoramica", emoji="🇮🇹",
                  subtitle="Seleziona la regione: clicca la mappa o usa il menu. Il colore indica la spesa "
                           "dei turisti stranieri (Banca d'Italia); scegli l'anno qui sotto.")
    code = st.session_state.get("region_code", L.RG.DEFAULT_REGION)
    last3 = L.bdi_region_years()[-3:]          # ultimi 3 anni completi (4 trimestri)
    opzioni = list(reversed(last3)) or [2024]  # più recente in cima
    sel_year = st.selectbox("📅 Anno di riferimento", opzioni, index=0, key="italia_anno",
                            help="Colora la mappa con la spesa straniera dell'anno scelto (BdI).")
    st.subheader(f"Grafico 1 — Mappa d'Italia (spesa straniera per regione · {sel_year})")
    ev = st.plotly_chart(L.chart_italy_map(highlight=code, year=sel_year), use_container_width=True,
                         on_select="rerun", selection_mode="points", key="italy_map_home")
    sel = None
    try:
        pts = ev["selection"]["points"]
        if pts:
            cd = pts[0].get("customdata")
            sel = (cd[0] if isinstance(cd, (list, tuple)) else cd) or L.RG.code_for_geo(pts[0].get("location"))
    except Exception:  # noqa: BLE001
        sel = None
    if sel and sel in L.RG.REGIONS and sel != code:
        st.session_state["_map_region"] = sel
        st.rerun()
    st.success(f"Regione attiva: **{L.RG.region(code)['nome']}** ({code}) — clicca un'altra regione "
               "sulla mappa o usa il **menu 📍 Regione** nella barra laterale (vale per tutte le pagine).")


@st.cache_data(show_spinner="Confronto i modelli di proiezione (OLS · ETS · SARIMAX · stato latente)…")
def _seasonal_proj_cached(code: str, fvar: str, horizon: int):
    """Proiezione stagionale con selezione del modello, in cache: i 4 modelli (di cui due
    state-space) vengono rifittati solo quando cambiano regione/variabile/orizzonte."""
    return L.project_seasonal_best(L.region_monthly_series(code, fvar), horizon)


def page_regione():
    code = st.session_state.get("region_code", L.RG.DEFAULT_REGION)
    info = L.RG.region(code)
    nazionale = L.RG.is_national(code)
    L.page_header(f"{info['nome']} — quadro {'nazionale' if nazionale else 'regionale'}",
                  subtitle=("Vista d'insieme nazionale: totale Italia da ISTAT (area «IT»). "
                            "Scegli una regione dal selettore per il dettaglio territoriale."
                            if nazionale else
                            "Multi-regione: dati ISTAT reali per la regione selezionata."),
                  group="Panoramica", emoji="📍", region_code=code)
    try:
        ov = L.region_overview(code)
    except Exception as e:  # noqa: BLE001
        st.error(f"ISTAT non disponibile ora per {info['nome']} ({type(e).__name__}). "
                 "ISTAT è instabile: riprova tra poco.")
        return
    df = ov["presenze"]
    obs = df.dropna(subset=["stranieri"])
    kpis = []
    if len(obs):
        kpis.append({"label": "Presenze straniere (ultimo mese)",
                     "value": f"{int(obs['stranieri'].iloc[-1]):,}".replace(",", ".")})
    if ov["letti"]:
        kpis.append({"label": f"Posti letto ({ov['anno_letti']})",
                     "value": f"{ov['letti']:,}".replace(",", ".")})
    sp = L.region_spend(code)
    if sp:
        kpis.append({"label": "Spesa straniera 2024 (BdI)",
                     "value": f"{sp[0]:,.0f} M€".replace(",", "."),
                     "hint": "totale Italia" if sp[1] is None else f"#{sp[1]} su {sp[2]} regioni"})
    kpis.append({"label": "Regioni coperte" if nazionale else "Aeroporti",
                 "value": f"{len(L.RG.REGIONS)}" if nazionale else
                          (", ".join(info["airports"]) if info["airports"] else "—")})
    L.kpi_row(kpis)
    # ── Periodo: UNA dropdown condivisa, filtra sia le presenze sia l'analisi pluriennale ──
    win = st.selectbox("Periodo", ["Ultimo anno", "Ultimi 2 anni", "Ultimi 3 anni",
                                   "Ultimi 5 anni", "Tutti gli anni"], index=3, key="reg_win",
                       help="Filtra sia il grafico delle presenze sia la tabella/indici qui sotto.")
    _nwin = {"Ultimo anno": 1, "Ultimi 2 anni": 2, "Ultimi 3 anni": 3, "Ultimi 5 anni": 5}
    if win == "Tutti gli anni" or df.empty:
        dfm = df
    else:
        dfm = df[df["date"] >= df["date"].max() - pd.DateOffset(years=_nwin[win])]
    st.subheader("Grafico 1 — Presenze mensili (totale e straniere)")
    st.plotly_chart(L.chart_region_presences(dfm), use_container_width=True)
    if nazionale:
        st.caption("Totale Italia (ISTAT area «IT») · spesa BdI = somma delle regioni visitate")
    else:
        st.caption(f"NUTS2 **{info['code']}** · keyword Trends «{info['trends_kw']}» · "
                   f"Wikipedia «{info['wiki'].get('it')}» · BdI «{info['bdi']}»")

    # ── Analisi pluriennale: tabella valori assoluti + grafico a indici, variabili on/off ──
    st.divider()
    st.subheader(":material/insights: Analisi pluriennale")
    st.caption("Accendi/spegni le variabili: la **tabella** mostra i valori assoluti per anno, il "
               "**grafico a indici** (base 100 = primo anno) confronta i trend — così vedi se, *a parità "
               "di turisti, la spesa per turista è salita o scesa*. Usa la **dropdown «Periodo» qui sopra** "
               "per la finestra temporale. Base per le proiezioni.")
    panel = L.region_annual_panel(code)
    if panel is None or panel.empty:
        st.info("Serie annuali non ancora disponibili (ISTAT/BdI).")
        return
    avail = [k for k in panel.columns if panel[k].notna().any()]
    default_sel = [k for k in ("presenze_tot", "spesa_per_viagg") if k in avail] or avail[:2]
    sel = st.multiselect(
        "Variabili da confrontare", avail, default=default_sel, key="reg_vars",
        format_func=lambda k: L.REGION_VAR_LABEL[k] + (f" ({L.REGION_VAR_UNIT[k]})"
                                                       if L.REGION_VAR_UNIT[k] != "n" else ""))
    if not sel:
        st.info("Seleziona almeno una variabile dal menu qui sopra.")
        return
    dfp = panel if win == "Tutti gli anni" else panel.tail(_nwin[win])
    show = pd.DataFrame({"Anno": dfp.index.astype(int)})
    for k in sel:
        dec = L.REGION_VAR_DEC[k]
        show[L.REGION_VAR_LABEL[k]] = [("—" if pd.isna(v) else f"{v:,.{dec}f}".replace(",", "."))
                                       for v in dfp[k]]
    st.subheader("Tabella 1 — Valori annuali per variabile")
    st.dataframe(show, hide_index=True, use_container_width=True)
    deltas = []
    for k in sel:
        s = dfp[k].dropna()
        if len(s) >= 2 and s.iloc[0]:
            deltas.append(f"**{L.REGION_VAR_LABEL[k]}** {(s.iloc[-1] / s.iloc[0] - 1) * 100:+.0f}% "
                          f"({int(s.index[0])}→{int(s.index[-1])})")
    if deltas:
        st.caption("Variazione nel periodo — " + " · ".join(deltas))
    st.subheader("Grafico 2 — Indici (base 100)")
    st.plotly_chart(L.chart_region_indexed(dfp, sel), use_container_width=True)
    st.caption("⚠️ Spesa, pernottamenti e viaggiatori = **solo turisti stranieri** (Banca d'Italia); "
               "le presenze sono **totali** (ISTAT). La spesa per turista è quindi sul perimetro straniero.")

    # ── Proiezione: motore STAGIONALE (mensile) o TREND lineare (annuale) ──
    st.divider()
    st.subheader(":material/trending_up: Proiezione")
    pc1, pc2 = st.columns([2, 1])
    fvar = pc1.selectbox("Variabile da proiettare", sel, key="reg_fc_var",
                         format_func=lambda k: L.REGION_VAR_LABEL[k])
    horizon = pc2.selectbox("Orizzonte", [1, 2, 3], index=1, key="reg_fc_h",
                            format_func=lambda h: f"{h} anno" if h == 1 else f"{h} anni")
    seasonal_ok = fvar in L.MONTHLY_VARS
    if seasonal_ok:
        method = st.radio("Metodo", ["Stagionale (mensile)", "Trend lineare (annuale)"],
                          index=0, horizontal=True, key="reg_fc_method",
                          help="Stagionale: C(mese) + trend + dummy COVID sui dati mensili ISTAT "
                               "(cattura la stagionalità delle presenze). Trend: retta sugli annuali.")
    else:
        method = "Trend lineare (annuale)"
        st.caption("Per questa variabile è disponibile il **trend lineare annuale** "
                   "(il motore stagionale richiede una serie mensile: presenze ISTAT).")

    _fmt = lambda v: f"{v:,.0f}".replace(",", ".")  # noqa: E731
    if method.startswith("Stagionale"):
        proj = _seasonal_proj_cached(code, fvar, horizon)
        if proj is None:
            st.info("Serie mensile insufficiente per il modello stagionale (servono ~2 anni).")
        else:
            st.subheader("Grafico 3 — Proiezione")
            st.plotly_chart(L.chart_projection_monthly(proj, L.REGION_VAR_LABEL[fvar],
                            L.REGION_VAR_UNIT[fvar]), use_container_width=True)
            if proj["fc_ann"]:
                ny = max(proj["fc_ann"]); m, lo, hi = proj["fc_ann"][ny]
                last_y = max(proj["hist_ann"]) if proj["hist_ann"] else None
                base_v = proj["hist_ann"].get(last_y) if last_y else None
                vp = f" · {(m / base_v - 1) * 100:+.0f}% vs {last_y}" if base_v else ""
                st.success(f"**{L.REGION_VAR_LABEL[fvar]}** — proiezione **{ny}** (somma 12 mesi): "
                           f"~**{_fmt(m)}** (intervallo {_fmt(lo)}–{_fmt(hi)}, 80%){vp}")
            # esito della gara fra 6 motori (barriera di onestà vs naive, backtest a ritroso)
            bt = proj.get("backtest") or {}
            naive_tag = ("batte la naive stagionale" if proj.get("beats_naive")
                         else "NON batte la naive: scelto come miglior approssimazione")
            _r2 = proj.get("r2")
            r2s = f", R²={_r2:.2f}" if isinstance(_r2, (int, float)) and _r2 == _r2 else ""
            nfolds = bt.get("_folds")
            st.caption(f"Modello scelto automaticamente: **{proj.get('method', 'OLS stagionale')}** "
                       f"({naive_tag}){r2s}, intervallo 80%. La banda annuale è la somma dei mesi (indicativa).")
            if bt:
                win = proj.get("method")
                rows = [{"Scelto": "✓" if k == win else "",
                         "Modello": k,
                         "MAE (medio)": round(v["mae"]),
                         "Skill vs naive": (f"{v['skill']:+.1f}%" if v.get("skill") == v.get("skill") else "—"),
                         "Finestre vinte": (f"{v.get('wins', 0)}/{nfolds}" if nfolds else "—"),
                         "Batte naive": "sì" if v.get("beats_naive") else "no"}
                        for k, v in bt.items() if not k.startswith("_") and v.get("mae") == v.get("mae")]
                rows.sort(key=lambda r: r["MAE (medio)"])
                with st.expander(f"🏆 Classifica modelli (backtest a ritroso · {nfolds or 1} finestre)"):
                    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
                    st.caption("Backtest *rolling-origin*: ogni motore prevede a ritroso più finestre da "
                               "12 mesi; si tiene quello con l'errore medio (MAE) più basso, serie per serie. "
                               f"Naive stagionale = stesso mese dell'anno prima (MAE {round(bt.get('_naive_mae', float('nan')))}). "
                               "«Skill» = riduzione % dell'errore vs naive; «Finestre vinte» = in quante finestre quel motore è stato il migliore.")
    else:
        bc1, bc2, bc3 = st.columns([1.3, 1, 1])
        _base = {"Ultimi 5 anni": 5, "Ultimi 10 anni": 10, "Tutto lo storico": None}
        base_lbl = bc1.selectbox("Base del trend", list(_base), index=0, key="reg_fc_base",
                                 help="Su quanti anni stimare la retta. «Ultimi 5» segue il regime recente.")
        drop_covid = bc2.checkbox("Escludi 2020", value=True, key="reg_fc_covid",
                                  help="Esclude l'anomalia COVID dal calcolo del trend.")
        robust = bc3.checkbox("Robusto", value=False, key="reg_fc_robust",
                              help="Regressione robusta di Huber: pesa di meno gli anni anomali "
                                   "(outlier) invece di farli inclinare la retta. Utile se non escludi il 2020.")
        proj = L.project_var(panel, fvar, horizon, drop_covid, n_years=_base[base_lbl], robust=robust)
        if proj is None:
            st.info("Servono almeno 3 anni di dati per proiettare questa variabile.")
        else:
            st.subheader("Grafico 3 — Proiezione")
            st.plotly_chart(L.chart_projection(proj, L.REGION_VAR_LABEL[fvar], L.REGION_VAR_UNIT[fvar]),
                            use_container_width=True)
            dec = L.REGION_VAR_DEC[fvar]
            ny, nv = proj["fut_years"][-1], proj["fc_mean"][-1]
            lo, hi = proj["fc_lo"][-1], proj["fc_hi"][-1]
            base_v = proj["hist_vals"][-1]
            var_pct = (nv / base_v - 1) * 100 if base_v else float("nan")
            fdec = lambda v: f"{v:,.{dec}f}".replace(",", ".")  # noqa: E731
            st.success(f"**{L.REGION_VAR_LABEL[fvar]}** — proiezione **{ny}**: ~**{fdec(nv)}** "
                       f"{L.REGION_VAR_UNIT[fvar] if L.REGION_VAR_UNIT[fvar] != 'n' else ''} "
                       f"(intervallo {fdec(lo)}–{fdec(hi)}, 80%) · {var_pct:+.0f}% vs {proj['hist_years'][-1]}")
            _kind = "regressione robusta di Huber" if proj.get("robust") else "minimi quadrati (OLS)"
            st.caption(f"Trend stimato sugli anni {proj['hist_years'][0]}–{proj['hist_years'][-1]} "
                       f"con {_kind} (R²={proj['r2']:.2f}{' · 2020 escluso' if drop_covid else ''}). "
                       "R² alto = trend regolare; R² basso = serie più rumorosa, proiezione più incerta.")

    # ── Tier 2 · stabilizzazione tra regioni + coerenza (artefatto precalcolato, istantaneo) ──
    pooled = L.pooled_trend_for(code, fvar)
    if pooled and pooled["raw"] is not None:
        with st.expander("📊 Confronto tra regioni — trend stabilizzato (Tier 2)"):
            raw, shr, w, mu = pooled["raw"], pooled["shrunk"], pooled["weight"], pooled["mu"]
            st.markdown(
                f"**Crescita storica annua** (ultimi {pooled['window']} anni, in %/anno):\n\n"
                f"- grezza, solo questa regione: **{raw:+.1f}%**\n"
                f"- **stabilizzata tra regioni: {shr:+.1f}%**  ·  media nazionale {mu:+.1f}%")
            if w >= 0.66:
                nota = (f"Serie di questa regione solida (peso {w:.2f}): il trend stabilizzato "
                        "resta vicino a quello grezzo.")
            elif w >= 0.33:
                nota = (f"Serie parzialmente rumorosa (peso {w:.2f}): il trend viene tirato un po' "
                        "verso la media nazionale.")
            else:
                nota = (f"Serie corta/rumorosa (peso {w:.2f}): il trend grezzo è poco affidabile e "
                        "viene tirato quasi del tutto verso la media nazionale.")
            st.caption("Partial pooling (empirical-Bayes): condivide il segnale fra le 21 regioni e "
                       "restringe il trend di ciascuna verso la media nazionale, di più dove la stima è "
                       "incerta. " + nota)
            rec = pooled.get("recon")
            if rec and isinstance(rec.get("gap_pct"), (int, float)) and rec["gap_pct"] == rec["gap_pct"]:
                st.caption(f"**Coerenza Italia↔regioni** (presenze straniere, +1 anno): la somma delle "
                           f"proiezioni regionali (bottom-up) è **{rec['gap_pct']:+.1f}%** rispetto al "
                           "nazionale diretto (top-down). La vista coerente da pubblicare è il bottom-up "
                           "(i totali tornano per costruzione).")
            st.caption("Valori precalcolati dallo script `tier2_structural.py` (lettura istantanea).")


def page_mercati_origine():
    L.page_header("Mercati d'origine — i 10 paesi", group="Panoramica", emoji="🌍",
                  subtitle="Da dove arrivano i turisti stranieri: quanto spendono in Italia, quanti sono "
                           "e quanto vale il loro mercato (spesa per turismo all'estero). Dato nazionale.")
    rows = L.origin_markets_table()
    if not rows:
        st.info("Dati Banca d'Italia per paese non disponibili.")
        return
    cov = L.origin_markets_coverage()
    _kpi = [{"label": "Spesa dei 10 paesi in Italia",
             "value": f"{cov['sum10_M'] / 1000:.1f} mld €".replace(".", ",")}]
    if cov.get("quota_pct"):
        _kpi.append({"label": f"Copertura sul totale stranieri ({cov['anno']})",
                     "value": f"{cov['quota_pct']:.0f}%",
                     "hint": "quota della spesa straniera nazionale coperta dai 10 paesi"})
    _kpi.append({"label": "Turisti (somma 10 paesi)",
                 "value": f"{sum(r['turisti_k'] for r in rows) / 1000:.1f} mln".replace(".", ",")})
    L.kpi_row(_kpi)

    st.subheader("Tabella 1 — I 10 mercati d'origine")
    tbl = pd.DataFrame([{
        "Paese": r["paese"],
        "Spesa in Italia (M€)": f"{r['spesa_it_M']:,.0f}".replace(",", "."),
        "Turisti (mln)": f"{r['turisti_k'] / 1000:.1f}".replace(".", ","),
        "Spesa/turista (€)": (f"{r['spesa_per_turista']:,.0f}".replace(",", ".") if r["spesa_per_turista"] else "—"),
        "Spesa estero (mld €)": (f"{r['out_eur_mld']:,.0f}".replace(",", ".") + f" ({r['out_anno']})"
                                 if r["out_eur_mld"] else "n/d"),
        "Quota Italia %": (f"{r['quota_pct']:.1f}".replace(".", ",") if r["quota_pct"] is not None else "n/d"),
    } for r in rows])
    st.dataframe(tbl, hide_index=True, use_container_width=True)
    st.caption(f"Spesa in Italia, turisti, spesa/turista: **Banca d'Italia** (ultimo anno completo, {rows[0]['anno_bdi']}). "
               "Spesa estero (taglia del mercato): **Eurostat** BoP «travel» lato debiti per i paesi UE/EFTA "
               "(in M€, fino al 2025) e **World Bank** per gli extra-UE (USA, Canada, Giappone, Russia; "
               "convertito in €, ~2020). Quota Italia = spesa in Italia ÷ spesa estero sullo stesso anno.")

    st.subheader("Grafico 1 — Spesa dei turisti in Italia, per paese")
    st.plotly_chart(L.chart_origin_spesa_italia(rows), use_container_width=True)

    st.subheader("Grafico 2 — Taglia del mercato vs quota catturata dall'Italia")
    st.plotly_chart(L.chart_origin_share(rows), use_container_width=True)
    st.caption("Bolla = spesa in Italia. In alto = l'Italia cattura una quota alta del mercato (es. Austria, "
               "Svizzera, vicinanza); a destra = mercati grandi su cui c'è margine di crescita.")

    if cov.get("quota_pct"):
        st.info(f"🔎 I 10 paesi coprono il **{cov['quota_pct']:.0f}%** della spesa straniera totale in Italia "
                f"({cov['sum10_M'] / 1000:.1f} mld € su {cov['naz_M'] / 1000:.1f} mld €, {cov['anno']}); "
                "il restante ~36% sono altri mercati (Paesi Bassi, Belgio, Nordici, Cina…).")

    # ── Trend storico per singolo mercato d'origine ──
    st.divider()
    st.subheader(":material/timeline: Trend storico per mercato")
    st.caption("Come si muove nel tempo un singolo paese: spesa in Italia, turisti, spesa per turista e "
               "quota catturata dall'Italia. La **tabella** dà i valori assoluti, il **grafico a indici** "
               "(base 100) confronta i trend a prescindere dall'unità.")
    nomi = {r["code"]: r["paese"] for r in rows}
    mc1, mc2 = st.columns([1.4, 1])
    sel_code = mc1.selectbox("Paese", [r["code"] for r in rows],
                             format_func=lambda c: nomi[c], key="orig_mk_code")
    win = mc2.selectbox("Periodo", ["Ultimi 5 anni", "Ultimi 10 anni", "Tutti gli anni"],
                        index=1, key="orig_mk_win")
    mp = L.origin_market_panel(sel_code)
    if mp.empty:
        st.info("Serie storica non disponibile per questo paese.")
    else:
        _nw = {"Ultimi 5 anni": 5, "Ultimi 10 anni": 10}
        dfm = mp if win == "Tutti gli anni" else mp.tail(_nw[win])
        avail = [k for k in mp.columns if mp[k].notna().any()]
        default_sel = [k for k in ("spesa_it_M", "spesa_per_turista") if k in avail] or avail[:2]
        sel = st.multiselect("Variabili da confrontare", avail, default=default_sel, key="orig_mk_vars",
                             format_func=lambda k: L.MARKET_VAR_LABEL[k] + (f" ({L.MARKET_VAR_UNIT[k]})"
                                                                            if L.MARKET_VAR_UNIT[k] != "n" else ""))
        if sel:
            st.subheader(f"Tabella 2 — {nomi[sel_code]}: serie storica")
            show = pd.DataFrame({"Anno": dfm.index.astype(int)})
            for k in sel:
                dec = L.MARKET_VAR_DEC[k]
                show[L.MARKET_VAR_LABEL[k]] = [("—" if pd.isna(v) else f"{v:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", "."))
                                               for v in dfm[k]]
            st.dataframe(show, hide_index=True, use_container_width=True)
            deltas = []
            for k in sel:
                s = dfm[k].dropna()
                if len(s) >= 2 and s.iloc[0]:
                    deltas.append(f"**{L.MARKET_VAR_LABEL[k]}** {(s.iloc[-1] / s.iloc[0] - 1) * 100:+.0f}% "
                                  f"({int(s.index[0])}→{int(s.index[-1])})")
            if deltas:
                st.caption("Variazione nel periodo — " + " · ".join(deltas))
            st.subheader(f"Grafico 3 — {nomi[sel_code]}: andamento (indici base 100)")
            st.plotly_chart(L.chart_region_indexed(dfm, sel, labels=L.MARKET_VAR_LABEL),
                            use_container_width=True)
            st.caption("Spesa, turisti e spesa/turista = Banca d'Italia; spesa all'estero e quota = Eurostat/World Bank. "
                       "La quota può fermarsi prima (outbound di UK ed extra-UE meno recente).")


def page_confronto_regioni():
    code = st.session_state.get("region_code", L.RG.DEFAULT_REGION)
    L.page_header("Confronto tra regioni", group="Panoramica", emoji="📊", region_code=code,
                  subtitle="Classifica di tutte le regioni per spesa dei turisti stranieri (Banca d'Italia). "
                           "Scegli l'anno qui sotto; la regione attiva è evidenziata.")

    last3 = L.bdi_region_years()[-3:]          # ultimi 3 anni completi (4 trimestri)
    opzioni = list(reversed(last3)) or [2024]  # più recente in cima
    sel_year = st.selectbox("📅 Anno di riferimento", opzioni, index=0, key="cfr_anno",
                            help="Sono disponibili gli ultimi 3 anni con tutti i trimestri completi.")

    st.subheader(f"Grafico 1 — Classifica regioni per spesa straniera · {sel_year}")
    st.plotly_chart(L.chart_regions_ranking(highlight=code, year=sel_year), use_container_width=True)
    rk = L.regions_spend_ranking_year(sel_year)
    df = pd.DataFrame([{"#": r["rank"], "Regione": r["regione"],
                        f"Spesa straniera {sel_year} (M€)": round(r["spesa_M"])} for r in rk])
    st.subheader(f"Tabella 1 — Spesa straniera per regione · {sel_year}")
    st.dataframe(df, hide_index=True, use_container_width=True)
    st.caption("Nota BdI: Bolzano e Trento sono aggregati come «Trentino Alto Adige».")


def page_mappa():
    L.page_header("Mappa dei mercati", group="Cosa fare", emoji="🗺️",
                  region_code=st.session_state.get("region_code", L.RG.DEFAULT_REGION),
                  subtitle="Colore = raccomandazione · dimensione bolla = score · linea = flusso verso la destinazione.")
    st.subheader("Grafico 1 — Mappa dei mercati")
    st.plotly_chart(L.chart_map(summary), use_container_width=True)
    with st.expander("Ranking in forma di barre"):
        st.subheader("Grafico 2 — Ranking in barre")
        st.plotly_chart(L.chart_ranking_bar(summary), use_container_width=True)


def page_ranking():
    L.page_header("Ranking mercati", group="Cosa fare", emoji="🏆",
                  region_code=st.session_state.get("region_code", L.RG.DEFAULT_REGION),
                  subtitle="Ordinamento per opportunità: dove conviene concentrare il budget promozionale.")
    tbl = pd.DataFrame([{"#": s["rank"], "Mercato": s["market"], "Raccomandazione": s["reco"],
                         **({"Forza": s["forza"], "Momentum %": s["momentum"]} if is_real else {}),
                         "Score": round(s["score"])} for s in summary])
    st.subheader("Tabella 1 — Ranking mercati")
    L.aggrid_table(tbl, height=300, reco_col="Raccomandazione", key="rank_grid")
    st.subheader("Grafico 1 — Ranking in barre")
    st.plotly_chart(L.chart_ranking_bar(summary), use_container_width=True)
    if is_real:
        _rcw = st.session_state.get("region_code", L.RG.DEFAULT_REGION)
        fig_w = L.chart_region_weight_bar(summary)
        if fig_w is not None:
            st.subheader(f"Grafico 2 — Valore economico dei mercati in {L.RG.region(_rcw)['nome']}")
            st.caption("Peso economico **reale della regione** usato nel ranking: presenze del mercato "
                       "nella regione (ISTAT, cube _9) × spesa media a notte (Banca d'Italia). "
                       "Sostituisce il vecchio €/viaggiatore **nazionale** (uguale per tutte le regioni).")
            st.plotly_chart(fig_w, use_container_width=True)
        else:
            st.subheader("Grafico 2 — Valore economico per mercato")
            st.caption("Spesa media per viaggiatore (Banca d'Italia) — dato nazionale "
                       "(il peso regionale ISTAT _9 non è disponibile).")
            st.plotly_chart(L.chart_value_bar(summary), use_container_width=True)
        _rc = st.session_state.get("region_code", L.RG.DEFAULT_REGION)
        fig_conn = L.chart_connectivity(_rc)
        if fig_conn is not None:
            st.subheader(f"Grafico 3 — Connettività aerea diretta — {L.RG.region(_rc)['nome']}")
            st.caption("Passeggeri 2024 verso gli aeroporti della regione (Eurostat avia_par) — "
                       "fattibilità reale nel ranking. 0 = nessun volo diretto da quel mercato.")
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
                st.subheader("Tabella 2 — Salute dei mercati")
                st.dataframe(hdf, hide_index=True, use_container_width=True)
                st.caption("DE/AT/NL (Eurostat). Saldo negativo = pessimismo; conta soprattutto il trend.")
        with hc2:
            _rc2 = st.session_state.get("region_code", L.RG.DEFAULT_REGION)
            fig_fl = L.chart_flights_monthly() if _rc2 == L.RG.DEFAULT_REGION else None
            if fig_fl is not None:
                st.markdown("**Accessibilità aerea nel tempo** · Pescara")
                st.subheader("Grafico 4 — Voli per mercato")
                st.plotly_chart(fig_fl, use_container_width=True)
            else:
                st.markdown("**Accessibilità per mercato** (vedi grafico sopra)")
                st.caption("La serie *mensile* dell'aeroporto è disponibile per la regione pilota (Pescara).")


def page_forecast():
    if is_real:
        R = ctx["R"]; agg = R["agg"]
        L.page_header("Forecast presenze straniere", group="Cosa fare", emoji="📈",
                      region_code=ctx.get("region", L.RG.DEFAULT_REGION),
                      subtitle="Proiezione delle presenze straniere con banda di incertezza; "
                               "a livello aggregato la stagionalità domina.")
        L.kpi_row([
            {"label": "Lag segnale", "value": f"{agg['lag']} mesi"},
            {"label": "Batte la naive?", "value": "Sì" if agg["beats_naive"] else "No"},
            {"label": "Errore backtest (MAPE)", "value": f"{agg['mape_model']:.0f}%"},
        ])
        if not agg["beats_naive"]:
            st.info("A livello aggregato la stagionalità domina: il modello non batte la naive. "
                    "Per il **numero** si usa il riferimento stagionale (confidenza bassa); "
                    "il valore decisionale è nel **ranking**.")
        st.subheader("Grafico 1 — Forecast presenze")
        st.plotly_chart(L.chart_forecast(R["history"], R["forecast"], "presenze straniere"),
                        use_container_width=True)
        with st.expander("Lettura dei coefficienti del modello aggregato"):
            for line in agg["coeff_reading"]:
                st.markdown(f"- {line}")
    else:
        rows = ctx["rows"]
        L.page_header("Forecast per mercato", group="Cosa fare", emoji="📈",
                      subtitle="Proiezione per singolo mercato (modalità sintetica).")
        sel = st.selectbox("Mercato:", [s["market"] for s in summary])
        code = next(c for c, r in rows.items() if r["name"] == sel)
        Rr = rows[code]
        st.subheader("Grafico 1 — Forecast presenze")
        st.plotly_chart(L.chart_forecast(Rr["history"][["date", "presences"]], Rr["forecast"], "presenze"),
                        use_container_width=True)
        with st.expander("Lettura dei coefficienti"):
            for line in Rr["coeff_reading"]:
                st.markdown(f"- {line}")


def page_dettaglio():
    L.page_header("Dettaglio mercato", group="Cosa fare", emoji="🔎",
                  region_code=st.session_state.get("region_code", L.RG.DEFAULT_REGION),
                  subtitle="Scheda per singolo mercato: raccomandazione, forza del segnale, valore e accessibilità.")
    names = [s["market"] for s in summary]
    sel = st.selectbox("Mercato:", names)
    if is_real:
        s = next(x for x in summary if x["market"] == sel)
        st.markdown(L.badge_html(s["reco"]) + f"&nbsp;&nbsp;<b>{s['reco']}</b>", unsafe_allow_html=True)
        ext = L.bdi_extended()
        stay = (ext.get("durata_media_2024", {}) if ext else {}).get(s["code"])
        L.kpi_row([
            {"label": "Forza anticipatrice", "value": f"{s['forza']:+.2f}"},
            {"label": "Momentum ricerca", "value": f"{s['momentum']:+.0f}%"},
            {"label": "Valore €/viaggiatore", "value": f"{s['valore']:.0f}"},
            {"label": "Durata media", "value": f"{stay:.1f} notti" if stay else "—"},
        ])
        h = L.market_health().get(s["code"])
        if h:
            st.caption(f":material/thermostat: **Salute mercato** (fiducia consumatori {s['code']}): saldo {h['conf']:+.1f} "
                       f"· {h['label']} — contesto decisionale, non previsione.")
        else:
            st.caption(":material/thermostat: Salute mercato: fiducia consumatori non disponibile per questo mercato (solo DE/AT/NL).")
        st.subheader("Grafico 1 — Interesse di ricerca")
        st.plotly_chart(L.chart_search(ctx["R"]["panel"], s["code"]), use_container_width=True)
    else:
        rows = ctx["rows"]
        code = next(c for c, r in rows.items() if r["name"] == sel)
        card = rows[code]["card"]
        L.kpi_row([
            {"label": "Raccomandazione", "value": card["raccomandazione"]},
            {"label": "Confidenza", "value": card["confidenza"]},
        ])
        st.markdown(f"**Effetto atteso** · {card['effetto_atteso']}")
        with st.expander("Evidenza · meccanismo · rischio", expanded=True):
            for e in card["evidenza"]:
                st.markdown(f"- {e}")
            st.markdown(f"**Meccanismo** · {card['meccanismo']}")
            st.markdown(f"**Rischio** · {card['rischio']}")


def page_allocatore():
    L.page_header("Allocatore di budget", group="Cosa fare", emoji="💰",
                  region_code=st.session_state.get("region_code", L.RG.DEFAULT_REGION),
                  subtitle="Ripartizione proporzionale allo score. NON è una stima causale: indica dove "
                           "conviene concentrare, non quanto renderà.")
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
        st.subheader("Tabella 1 — Allocazione del budget")
        L.aggrid_table(adf, height=300, reco_col="Raccomandazione", key="alloc_grid")
    with gcol:
        any_alloc = any(a["quota_eur"] > 0 for a in alloc)
        if any_alloc:
            st.subheader("Grafico 1 — Ripartizione del budget")
            st.plotly_chart(L.chart_allocation(alloc), use_container_width=True)
        else:
            st.warning("Nessun mercato idoneo con le categorie selezionate.")


def page_timing():
    L.page_header("Timing stagionale", group="Cosa fare", emoji="📅",
                  region_code=st.session_state.get("region_code", L.RG.DEFAULT_REGION),
                  subtitle="Quando l'interesse di ricerca di ogni mercato è al massimo → quando anticipare "
                           "la campagna (il search precede gli arrivi).")
    panel = search_panel()
    if panel is None:
        st.info("Dati di ricerca non disponibili.")
        return
    st.subheader("Grafico 1 — Stagionalità per mercato")
    st.plotly_chart(L.chart_seasonal_heatmap(panel, summary), use_container_width=True)
    st.caption("Più scuro = mese di picco dell'interesse per quel mercato (normalizzato per riga).")


def page_assistente():
    L.page_header("Assistente", group="Sistema", emoji="💬",
                  subtitle=f"Claude · {L.MODEL} · modalità {'REALE' if is_real else 'sintetica'} · "
                           "risponde sui numeri del motore.")
    L.render_assistant(ctx)


def page_gestione_dati():
    L.page_header("Gestione dati", group="Sistema", emoji="🗄️",
                  subtitle="Dati presenti, candidati in valutazione (con nulla osta), copertura temporale "
                           "e caricamento file.")

    st.subheader(":material/table: Tabella 1 — Dati Presenti")
    st.caption("Tutte le fonti attualmente in uso dal motore: reali, candidati approvati e file caricati.")
    L.aggrid_table(L.fmt_count_col(pd.DataFrame(L.present_sources(), columns=L.SRC_COLS)),
                   height=320, key="present_grid")

    st.subheader(":material/science: Tabella 2 — Dati in Valutazione")
    st.caption("Fonti candidate proposte per il TDH. Verifica la disponibilità, valida la descrizione "
               "e dai il **nulla osta** per caricarle.")
    pend = L.pending_candidates()
    if not pend:
        st.success("Nessun candidato in attesa: tutte le fonti proposte sono già state approvate.")
    else:
        L.aggrid_table(L.fmt_count_col(pd.DataFrame(pend, columns=L.SRC_COLS)),
                       height=320, key="pending_grid")
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

    st.subheader(":material/grid_view: Tabella 3 — Copertura dati (Nazionale · Regionale · Provinciale)")
    st.caption("Cosa abbiamo a ciascun livello geografico (✅ disponibile · 🟡 parziale · ❌ assente). "
               "Serve a vedere i **buchi** da coprire per il portale multi-regione.")
    st.dataframe(pd.DataFrame(L.coverage_matrix(), columns=L.COVERAGE_COLS),
                 hide_index=True, use_container_width=True)
    st.caption("🔴 Buchi principali: presenze **per paese a livello regionale**, **anagrafica strutture**, "
               "spesa per paese regionale, accessibilità ferroviaria regionale.")

    st.subheader(":material/sync: Tabella 4 — Stato e aggiornamento delle fonti")
    lr = U.last_run_info()
    cap = ("Giudizio istantaneo dalla cache — 🟢 fresco · 🟡 da controllare · "
           "🔴 probabile dato nuovo · ⚪ ignoto. Il controllo *live* riscarica e conferma cosa è cambiato.")
    if lr:
        cap += f"  ·  Ultimo controllo live: {lr['last_run'][:16].replace('T', ' ')}"
    st.caption(cap)
    _stat = U.status_all()
    st.dataframe(
        L.fmt_count_col(
            pd.DataFrame(_stat)[["stato", "fonte", "cadenza", "ultimo_dato", "righe", "scaricato"]]
            .rename(columns={"stato": "Stato", "fonte": "Fonte", "cadenza": "Cadenza",
                             "ultimo_dato": "Ultimo dato", "righe": "Righe", "scaricato": "Scaricato"})),
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
                        L.clear_data_caches()  # svuota anche le lru_cache di tdh_data
                        st.success(ar["msg"] + " · cache rigenerata.")
                        st.rerun()
                    else:
                        st.error(ar["msg"])
        st.caption("In locale l'aggiornamento resta sul tuo PC. Per portarlo anche sull'app online "
                   "serve un `git push` (oppure ci penserà la schedulazione automatica — Fase 2).")

    st.subheader("Grafico 1 — Copertura temporale delle serie")
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

    st.subheader("Tabella 5 — File caricati")
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
    L.page_header("Azioni raccomandate", group="Cosa fare", emoji="🎯",
                  region_code=st.session_state.get("region_code", L.RG.DEFAULT_REGION),
                  subtitle="Suggerimenti operativi dai dati: dove e quando agire. "
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
    L.page_header("Architettura & sorgenti dati", group="Sistema", emoji="🧩",
                  subtitle="La visione completa del Turism Data Hub e lo stato delle sorgenti.")
    A = L.tdh_architecture()
    st.subheader("Architettura a 5 livelli")
    for nome, desc in A["livelli"]:
        st.markdown(f"**{nome}** — {desc}")
    st.subheader("Tabella 1 — Sorgenti dati")
    L.aggrid_table(pd.DataFrame(A["sorgenti"]), height=360, key="arch_src")
    st.caption("🟢 Attiva (già nel motore) · 🟡 Pianificata · ⚪ Da valutare")
    st.subheader("Motore statistico")
    for m in A["motore_statistico"]:
        st.markdown(f"- {m}")
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
    code = st.session_state.get("region_code", L.RG.DEFAULT_REGION)
    if L.RG.is_national(code):  # le province non esistono per «tutta Italia»: mostro la regione di default
        code = L.RG.DEFAULT_REGION
        st.info(f"La vista per provincia è **regionale**: sto mostrando **{L.RG.region(code)['nome']}**. "
                "Scegli un'altra regione dal selettore 📍 in alto a sinistra.")
    nome = L.RG.region(code)["nome"]
    L.page_header("Presenze per provincia", group="Cosa è successo", emoji="📍", region_code=code,
                  subtitle="Quadro territoriale (ISTAT): dove si concentra il turismo, come sta "
                           "cambiando e quando lavora ciascuna provincia.")
    try:
        P = L.compute_provinces(code)
    except Exception as e:  # noqa: BLE001
        st.error(f"Dati province non disponibili: {type(e).__name__}: {e}")
        return
    if not P["rows"]:
        st.warning(f"ISTAT non ha restituito dati provinciali per {nome} (può essere instabilità ISTAT: riprova).")
        return

    # ─────────── DOVE: mappa + tabella con peso % e concentrazione ───────────
    fig_map = L.chart_province_map(P["rows"])
    if fig_map is not None:
        st.subheader("Grafico 1 — Mappa delle presenze per provincia")
        st.plotly_chart(fig_map, use_container_width=True)

    tot_reg = sum(r["presenze"] for r in P["rows"]) or 1
    st.subheader("Tabella 1 — Riepilogo per provincia (ultimi 12 mesi)")
    tbl = pd.DataFrame([{
        "Provincia": r["provincia"],
        "Presenze": round(r["presenze"]),
        "Peso %": round(r["presenze"] / tot_reg * 100, 1),
        "Stranieri": (round(r["stranieri"]) if pd.notna(r["stranieri"]) else None),
        "Quota stranieri %": (round(r["quota_stranieri"]) if pd.notna(r["quota_stranieri"]) else None),
    } for r in P["rows"]])
    L.aggrid_table(tbl, height=190, key="prov_grid")
    top = P["rows"][0]
    topn = min(3, len(P["rows"]))
    share_top = sum(r["presenze"] for r in P["rows"][:topn]) / tot_reg * 100
    st.caption(f"Concentrazione: **{top['provincia']}** da sola vale **{top['presenze'] / tot_reg * 100:.0f}%** "
               f"del totale regionale; le prime {topn} province insieme **{share_top:.0f}%**.")

    # ─────────── COSA È CAMBIATO: variazione % anno su anno ───────────
    yoy = L.province_yoy(P["panel"])
    if yoy:
        st.subheader("Grafico 2 — Variazione % anno su anno per provincia")
        st.caption("Presenze degli ultimi 12 mesi rispetto ai 12 precedenti. 🟢 crescita · 🔴 calo.")
        st.plotly_chart(L.chart_province_yoy(yoy), use_container_width=True)
    else:
        st.info("Serie troppo corta per la variazione anno su anno (servono almeno 24 mesi).")

    # ─────────── QUANDO: stagionalità (heatmap mese × provincia) ───────────
    st.subheader("Grafico 3 — Stagionalità per provincia")
    st.caption("Per ogni provincia il **mese di picco = 100%**: si confronta *quando* lavora ciascuna "
               "(es. costa d'estate vs montagna d'inverno), a parità di scala e indipendentemente dalla dimensione.")
    st.plotly_chart(L.chart_province_seasonality(P["panel"]), use_container_width=True)

    # ─────────── Trend mensile (totali o straniere) ───────────
    st.subheader("Grafico 4 — Trend mensile per provincia")
    src = st.radio("Presenze:", ["Totali", "Straniere"], horizontal=True, key="prov_trend_src")
    panel_src = P["panel"] if src == "Totali" else P.get("panel_str")
    if src == "Straniere" and (panel_src is None or panel_src.empty or len(panel_src.columns) <= 1):
        st.info("ISTAT non espone la serie mensile **straniera** per le province di questa regione. "
                "Gli stranieri restano disponibili come totale a 12 mesi (Tabella 1).")
    else:
        yr = st.session_state.get("yr_range", (2019, 2024))
        last = panel_src["date"].max()
        preset = st.selectbox("Periodo del trend:",
                              ["Slider barra laterale", "Ultimo mese", "Ultimi 12 mesi",
                               "Ultimi 2 anni", "Ultimi 5 anni"], index=2, key="prov_trend_preset")
        _mesi = {"Ultimo mese": 1, "Ultimi 12 mesi": 12, "Ultimi 2 anni": 24, "Ultimi 5 anni": 60}
        if preset in _mesi:
            cutoff = last - pd.DateOffset(months=_mesi[preset] - 1)
            pf = panel_src[panel_src["date"] >= cutoff]
        else:
            pf = L.filter_years(panel_src, yr)
        st.plotly_chart(L.chart_province_trend(pf, rangeslider=True), use_container_width=True)
        st.caption(("Serie **straniera**. " if src == "Straniere" else "")
                   + "Usa il menu per i preset rapidi, oppure trascina la barra/il cursore sul grafico "
                   "per restringere l'intervallo a mano.")


def page_struttura():
    code = st.session_state.get("region_code", L.RG.DEFAULT_REGION)
    nome = L.RG.region(code)["nome"]
    L.page_header("Presenze per tipologia di struttura", group="Cosa è successo", emoji="🏨",
                  region_code=code,
                  subtitle="Composizione dell'offerta (ISTAT): com'è composta, come sta cambiando "
                           "e quando lavora ciascun segmento.")
    try:
        S = L.compute_structure(code)
    except Exception as e:  # noqa: BLE001
        st.error(f"Dati struttura non disponibili per {nome}: {type(e).__name__} (ISTAT instabile: riprova).")
        return

    # etichette leggibili per i grafici generici (yoy + stagionalità)
    pretty = S["panel"].rename(columns={"alberghiero": "Alberghiero", "extra": "Extra-alberghiero"})

    # ─────────── COM'È COMPOSTO: metriche + donut ───────────
    tot = S["alberghiero"] + S["extra"]
    L.kpi_row([
        {"label": "Alberghiero (12 mesi)", "value": f"{S['alberghiero']:,.0f}".replace(",", ".")},
        {"label": "Extra-alberghiero", "value": f"{S['extra']:,.0f}".replace(",", ".")},
        {"label": "Quota alberghiero", "value": f"{S['alberghiero'] / tot * 100:.0f}%" if tot else "—"},
    ])
    st.subheader("Grafico 1 — Alberghiero vs extra-alberghiero (ultimi 12 mesi)")
    st.plotly_chart(L.chart_structure_donut(S), use_container_width=True)

    # ─────────── COSA È CAMBIATO: variazione % anno su anno per segmento ───────────
    yoy = L.province_yoy(pretty)
    if yoy:
        st.subheader("Grafico 2 — Variazione % anno su anno per segmento")
        st.caption("Presenze degli ultimi 12 mesi rispetto ai 12 precedenti, per segmento. 🟢 crescita · 🔴 calo.")
        st.plotly_chart(L.chart_province_yoy(yoy), use_container_width=True)
    else:
        st.info("Serie troppo corta per la variazione anno su anno (servono almeno 24 mesi).")

    # ─────────── QUANDO: stagionalità per segmento ───────────
    st.subheader("Grafico 3 — Stagionalità per segmento")
    st.caption("Per ogni segmento il **mese di picco = 100%**: si confronta *quando* lavora l'alberghiero "
               "rispetto all'extra-alberghiero, a parità di scala.")
    st.plotly_chart(L.chart_province_seasonality(pretty), use_container_width=True)

    # ─────────── Trend mensile ───────────
    yr = st.session_state.get("yr_range", (2019, 2024))
    st.subheader(f"Grafico 4 — Trend mensile · {yr[0]}–{yr[1]}")
    st.plotly_chart(L.chart_structure_trend(L.filter_years(S["panel"], yr)), use_container_width=True)


def page_occupazione():
    code = st.session_state.get("region_code", L.RG.DEFAULT_REGION)
    nome = L.RG.region(code)["nome"]
    L.page_header("Tasso di occupazione (reale)", group="Cosa è successo", emoji="🛏️",
                  region_code=code,
                  subtitle="Utilizzazione lorda dei posti letto = presenze ÷ (posti letto × giorni del mese). "
                           "Dati ISTAT: quant'è, come sta cambiando e quando.")
    try:
        O = L.compute_occupancy(code)
    except Exception as e:  # noqa: BLE001
        st.error(f"Dati occupazione non disponibili: {type(e).__name__}: {e}")
        return
    if not O["available"]:
        st.info(f"⏳ Dati di **capacità ricettiva** ISTAT per {nome} non ancora disponibili (ISTAT lento/instabile). "
                "Ricarica tra poco, o premi **:material/sync: Dati** nella barra laterale.")
        return

    # ─────────── QUANT'È: livello attuale + variazione a/a in punti percentuali ───────────
    p = O["panel"].sort_values("date")
    occ_cur = O["occ_media12"]
    occ_prev = float(p.iloc[-24:-12]["occ"].mean()) if len(p) >= 24 else None
    occ_delta = occ_dir = None
    if occ_prev is not None:
        diff = occ_cur - occ_prev
        occ_delta = f"{diff:+.1f} p.p. a/a"
        occ_dir = "up" if diff > 0 else ("down" if diff < 0 else "flat")
    L.kpi_row([
        {"label": "Occupazione media (12 mesi)", "value": f"{occ_cur:.0f}%",
         "delta": occ_delta, "delta_dir": occ_dir},
        {"label": f"Posti letto ({nome})", "value": f"{O['letti_ultimo']:,}".replace(",", ".")},
        {"label": "Anno capacità", "value": O["anno_letti"]},
    ])
    if occ_prev is not None:
        st.caption(f"**Cosa è cambiato**: {occ_cur - occ_prev:+.1f} punti percentuali rispetto ai 12 mesi "
                   f"precedenti ({occ_prev:.0f}% → {occ_cur:.0f}%).")

    yr = st.session_state.get("yr_range", (2019, 2024))
    pan = L.filter_years(O["panel"], yr)
    st.caption(f"Periodo selezionato: {yr[0]}–{yr[1]}")
    st.subheader("Grafico 1 — Come sta cambiando: occupazione lorda mese per mese")
    st.plotly_chart(L.chart_occupancy(pan), use_container_width=True)
    st.subheader("Grafico 2 — Quando: stagionalità dell'occupazione")
    st.plotly_chart(L.chart_occupancy_season(pan), use_container_width=True)
    st.caption("Indice di utilizzazione lorda: presenze rapportate alla capacità teorica (posti letto × giorni del mese).")


def page_operatori():
    L.page_header("Vista operatori (demo)", group="Cosa è successo", emoji="👤",
                  subtitle="Dati simulati a scopo dimostrativo (non reali).")
    L.demo_banner()
    prov = st.selectbox("Filtra per provincia:", ["Tutte", "L'Aquila", "Teramo", "Pescara", "Chieti"])
    d = L.demo_operators(prov)
    L.kpi_row([
        {"label": "Tasso occupazione", "value": f"{d['occupazione']}%"},
        {"label": "Prezzo medio (ADR)", "value": f"€ {d['adr']}"},
        {"label": "Punteggio qualità", "value": f"{d['qualita']}/5"},
        {"label": "Tasso conversione", "value": f"{d['conversione']}%"},
    ])
    a, b = st.columns(2)
    with a:
        st.subheader("Grafico 1 — Canali di acquisizione")
        st.plotly_chart(L.chart_demo_channels(d["canali"]), use_container_width=True)
    with b:
        st.subheader("Grafico 2 — Funnel di prenotazione")
        st.plotly_chart(L.chart_demo_funnel(d["funnel"]), use_container_width=True)
    st.subheader("Grafico 3 — Affluenza prevista (prossimi 7 giorni)")
    st.plotly_chart(L.chart_demo_weekly(d["weekly"]), use_container_width=True)
    e, f = st.columns(2)
    with e:
        st.subheader("Grafico 4 — Recensioni")
        st.plotly_chart(L.chart_demo_reviews(d["recensioni"]), use_container_width=True)
    with f:
        st.subheader("Cosa cercano i turisti")
        chips = " ".join(
            f"<span style='background:#e0f2fe;color:#0e6b70;padding:5px 12px;border-radius:999px;"
            f"font-size:.85rem;margin:3px;display:inline-block'>{q}</span>" for q in d["queries"])
        st.markdown(chips, unsafe_allow_html=True)
    st.caption("Dati simulati · Indra Italia · prototipo. In produzione: Registro ricettivo · OTA/booking · GA4 portale.")


def page_affitti_brevi():
    L.page_header("Affitti brevi (STR)", group="Cosa è successo", emoji="🏠",
                  subtitle="Mercato REALE degli affitti brevi (Inside Airbnb): prezzi e numero di annunci "
                           "per territorio. Dato a livello di città/regione — indipendente dalla regione selezionata.")
    df = L.str_territori()
    if df.empty:
        st.warning("Cache Inside Airbnb non disponibile. Ricostruisci la fonte «Affitti brevi (STR)» "
                   "(update_check → apply_update(\"str\") o fetch_str_market(refresh=True)).")
        return
    # selettore territorio (7 città + 3 regioni), ordinato per n. annunci
    opts = {f"{r.territorio} ({r.tipo})": r.slug for r in df.itertuples()}
    scelta = st.selectbox("Territorio", list(opts.keys()), key="str_terr")
    slug = opts[scelta]
    k = L.str_kpi(slug)
    st.caption(f"Fonte: **Inside Airbnb** · snapshot **{k.get('snapshot','—')}** · licenza CC BY 4.0. "
               f"Prezzo = ADR dell'*annuncio* (non prenotazioni reali); occupazione = *proxy*.")
    L.kpi_row([
        {"label": "Annunci attivi", "value": _it_num(k.get("n_annunci"))},
        {"label": "ADR mediano", "value": f"€ {_it_num(k.get('adr_mediano'))}", "hint": "prezzo/notte"},
        {"label": "ADR medio", "value": f"€ {_it_num(k.get('adr_medio'))}"},
        {"label": "Tipo", "value": (k.get("tipo") or "—").capitalize()},
    ])
    st.markdown("**Grafico 1 — ADR mediano a confronto tra i territori**")
    fig = L.chart_str_adr_territori(sel_slug=slug)
    if fig:
        st.plotly_chart(fig, use_container_width=True)
    c1, c2 = st.columns([3, 2])
    with c1:
        st.markdown(f"**Grafico 2 — Zone con più annunci ({k.get('territorio')})**")
        fig = L.chart_str_zone(slug, top=12)
        if fig:
            st.plotly_chart(fig, use_container_width=True)
    with c2:
        st.markdown("**Grafico 3 — Per tipo di alloggio**")
        fig = L.chart_str_roomtype(slug)
        if fig:
            st.plotly_chart(fig, use_container_width=True)
    st.divider()
    st.subheader("Struttura del mercato")
    L.kpi_row([
        {"label": "Intero alloggio", "value": f"{k.get('pct_intero'):.0f}%" if k.get("pct_intero") is not None else "—",
         "hint": "vs stanze"},
        {"label": "Operatori professionali", "value": f"{k.get('pct_multihost'):.0f}%" if k.get("pct_multihost") is not None else "—",
         "hint": "host multi-annuncio"},
        {"label": "Con licenza/CIR", "value": f"{k.get('pct_licenza'):.0f}%" if k.get("pct_licenza") is not None else "—",
         "hint": "regolarità"},
        {"label": "Occupazione (proxy)", "value": f"{k.get('occ_proxy'):.0f}%" if k.get("occ_proxy") is not None else "—",
         "hint": f"rating medio {k.get('rating_medio')}"},
    ])
    st.markdown("**Grafico 4 — Struttura del mercato a confronto tra i territori**")
    fig = L.chart_str_struttura()
    if fig:
        st.plotly_chart(fig, use_container_width=True)
    st.caption("«Operatori professionali» = host con più di un annuncio (indizio di gestione non amatoriale). "
               "«Con licenza/CIR» = annunci che espongono un codice identificativo (regolarità). "
               "Occupazione = *proxy* dalla disponibilità del calendario, non da prenotazioni reali.")

    st.divider()
    st.subheader("Andamento nel tempo")
    st.markdown(f"**Grafico 5 — Attività nel tempo: recensioni per mese ({k.get('territorio')})**")
    fig = L.chart_str_reviews(slug)
    if fig:
        st.plotly_chart(fig, use_container_width=True)
    st.caption("Recensioni datate (Inside Airbnb, dal 2009) come **proxy dell'attività/domanda** nel tempo: "
               "si vede la crescita del mercato e il crollo COVID-2020. Limiti: solo annunci ancora online oggi "
               "(bias di sopravvivenza) e non tutte le notti generano una recensione.")

    st.markdown("**Tabella 1 — Zone per numero di annunci**")
    z = L.str_zone(slug, top=25)
    if z is not None and not z.empty:
        show = z.rename(columns={"zona": "Zona", "n_annunci": "Annunci", "adr_mediano": "ADR mediano €"})[
            ["Zona", "Annunci", "ADR mediano €"]].copy()
        show["Annunci"] = show["Annunci"].map(_it_num)
        show["ADR mediano €"] = show["ADR mediano €"].map(_it_num)
        st.dataframe(show, hide_index=True, use_container_width=True)
    st.caption("Fonte: Inside Airbnb (insideairbnb.com) · CC BY 4.0 · 7 città + 3 regioni intere (Puglia, "
               "Sicilia, Trentino-A.A.) · niente Abruzzo. Universo: annunci Airbnb, non l'intero comparto extra-alberghiero.")


def page_str_nazionale():
    L.page_header("STR Italia — anteprima (AirROI/AirDNA)", group="Cosa è successo", emoji="🇮🇹",
                  subtitle="Come sarebbe il mercato affitti brevi a COPERTURA NAZIONALE con metriche reali "
                           "(occupazione, ADR, RevPAR, ricavi). Prototipo di front-end su schema AirROI/AirDNA.")
    L.demo_banner()
    st.info("**Dati di ESEMPIO** (sintetici, realistici) — servono a costruire e valutare il front-end. Nel "
            "prodotto **privato** i valori arrivano dalle API a pagamento (AirROI `/markets/metrics/*`): "
            "occupazione/ricavi **reali**, ~100 mercati italiani, tutte le regioni. I dati veri **non** vanno "
            "committati (licenza) → chiamata a runtime con chiave nel deploy privato.", icon=":material/science:")
    df = L.str_nat_sample()

    metriche = {"Ricavo annuo/annuncio": "revenue", "RevPAR": "revpar", "ADR": "adr",
                "Occupazione": "occ_pct", "Annunci attivi": "listings"}
    sel = st.selectbox("Classifica i mercati per:", list(metriche.keys()), key="strnat_metric")
    st.markdown(f"**Grafico 1 — Mercati italiani per {sel.lower()} (esempio)**")
    fig = L.chart_str_nat_ranking(metriche[sel], top=15)
    if fig:
        st.plotly_chart(fig, use_container_width=True)

    st.divider()
    market = st.selectbox("Dettaglio mercato:", df["market"].tolist(), key="strnat_market")
    r = df[df["market"] == market].iloc[0]
    st.caption(f"**{market}** · {r['regione']} — schema AirROI: occupancy, avg_rate (ADR), revpar, revenue, "
               "active_listings_count, avg_length_of_stay.")
    L.kpi_row([
        {"label": "Occupazione", "value": f"{r['occ_pct']:.0f}%"},
        {"label": "ADR", "value": f"€ {_it_num(r['adr'])}", "hint": "prezzo/notte"},
        {"label": "RevPAR", "value": f"€ {r['revpar']:.0f}", "hint": "ricavo/notte disponibile"},
        {"label": "Ricavo annuo/annuncio", "value": f"€ {_it_num(r['revenue'])}"},
    ])
    L.kpi_row([
        {"label": "Annunci attivi", "value": _it_num(r["listings"])},
        {"label": "Permanenza media", "value": f"{r['alos']:.1f} notti"},
    ])
    st.markdown(f"**Grafico 2 — Stagionalità (occupazione e ADR per mese) · {market} (esempio)**")
    fig = L.chart_str_nat_seasonality(market)
    if fig:
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("**Tabella 1 — Tutti i mercati (esempio)**")
    show = df.rename(columns={"market": "Mercato", "regione": "Regione", "occ_pct": "Occ. %",
                              "adr": "ADR €", "revpar": "RevPAR €", "revenue": "Ricavo/anno €",
                              "listings": "Annunci", "alos": "Perm. media"})[
        ["Mercato", "Regione", "Occ. %", "ADR €", "RevPAR €", "Ricavo/anno €", "Annunci", "Perm. media"]].copy()
    for c in ["ADR €", "Ricavo/anno €", "Annunci"]:
        show[c] = show[c].map(_it_num)
    st.dataframe(show, hide_index=True, use_container_width=True)
    st.caption("⚠️ Valori SINTETICI di esempio (non dati reali). Schema compatibile con AirROI e AirDNA. "
               "Copertura reale prevista: ~100 mercati italiani su tutte le regioni (AirROI, ~$5-10 per snapshot).")


def page_spesa():
    code = st.session_state.get("region_code", L.RG.DEFAULT_REGION)
    nome = L.RG.region(code)["nome"]
    L.page_header("Spesa turistica", group="Cosa è successo", emoji="💶", region_code=code,
                  subtitle="Spesa dei turisti stranieri nella regione + contesto nazionale "
                           "(Banca d'Italia, indagine turismo internazionale).")
    g = L.bdi_region_annual(code)
    if g is None or g.empty:
        st.info(f"Dati Banca d'Italia per {nome} non disponibili.")
        return
    full = g[g["trimestri"] >= 4]  # ultimo anno completo (esclude l'anno in corso parziale)
    last = (full if not full.empty else g).iloc[-1]
    sp, notti, viagg, anno = last["spesa"], last["notti"], last["viaggiatori"], int(last["anno"])
    durata = notti / viagg if viagg else 0
    spnotte = sp * 1e6 / (notti * 1e3) if notti else 0
    L.kpi_row([
        {"label": f"Spesa straniera {anno}", "value": f"{sp:,.0f} M€".replace(",", ".")},
        {"label": "Pernottamenti", "value": f"{notti / 1000:.1f} mln"},
        {"label": "Durata media", "value": f"{durata:.1f} notti"},
        {"label": "Spesa per notte", "value": f"€ {spnotte:.0f}"},
    ])
    yr = st.session_state.get("yr_range", (2019, 2024))
    st.subheader(f"Grafico 1 — Spesa straniera in {nome} · {yr[0]}–{yr[1]}")
    fig_sp = L.chart_region_spend(code, yr)
    if fig_sp is not None:
        st.plotly_chart(fig_sp, use_container_width=True)
    # Confronto tra regioni — anno selezionabile (ultimi 3 completi), regione attiva evidenziata
    last3 = L.bdi_region_years()[-3:]
    opzioni = list(reversed(last3)) or [2024]
    sel_year = st.selectbox("📅 Anno per il confronto tra regioni", opzioni, index=0, key="spesa_anno",
                            help="Vale per il Grafico 2 (classifica regioni per spesa straniera, BdI).")
    st.subheader(f"Grafico 2 — Confronto regioni (spesa stranieri · {sel_year})")
    st.plotly_chart(L.chart_regions_ranking(highlight=code, year=sel_year), use_container_width=True)
    ext = L.bdi_extended()
    if ext:
        cA, cB = st.columns(2)
        with cA:
            st.subheader("Grafico 3 — Per motivo del viaggio")
            st.caption("Dato nazionale (turisti stranieri in Italia)")
            st.plotly_chart(L.chart_bdi_motivo(ext), use_container_width=True)
        with cB:
            st.subheader("Grafico 4 — Per tipo di struttura")
            st.caption("Dato nazionale (turisti stranieri in Italia)")
            st.plotly_chart(L.chart_bdi_struttura(ext), use_container_width=True)

    # Spesa STIMATA per mercato × regione: notti reali ISTAT (cube _9) × spesa/notte BdI
    st.divider()
    st.subheader(f"Grafico 5 — Spesa stimata dei turisti stranieri per mercato in {nome}")
    d_est = L.estero_spesa_stimata(code)
    if d_est is None or d_est.empty:
        st.info("⏳ Stima non ancora disponibile: richiede il dato ISTAT «Paese di origine» per regione "
                "(cube DCSC_TUR_9), in fase di download. Riapparirà appena la cache è pronta.")
    else:
        anno_est = d_est.attrs.get("anno", "—")
        tot = d_est["spesa_m"].sum()
        st.caption(f"**Stima** (anno {anno_est}): notti reali per mercato in {nome} (ISTAT) × spesa media a "
                   f"notte del mercato a livello nazionale (Banca d'Italia). **Non è un dato ufficiale**: è una "
                   f"decomposizione trasparente, utile come ordine di grandezza. "
                   f"Totale stimato dei mercati noti: **{tot:,.0f} M€**".replace(",", "."))
        st.plotly_chart(L.chart_estero_spesa_stimata(code), use_container_width=True)
        tab = pd.DataFrame({
            "Mercato": d_est["nome"],
            "Notti (ISTAT)": d_est["notti"].round(0).astype("int64"),
            "€/notte (BdI)": d_est["eur_notte"].round(0).astype("int64"),
            "Spesa stimata (M€)": d_est["spesa_m"].round(1),
        })
        st.subheader("Tabella 1 — Spesa stimata per mercato")
        st.dataframe(tab, hide_index=True, use_container_width=True)


def page_mercati_paese():
    code = st.session_state.get("region_code", L.RG.DEFAULT_REGION)
    nome = L.RG.region(code)["nome"]
    L.page_header("Mercati esteri per paese", group="Cosa è successo", emoji="🌍", region_code=code,
                  subtitle="Da quali paesi arrivano davvero i turisti stranieri nella regione (dato reale "
                           "ISTAT) e come si muovono nel tempo. Sotto, il contesto nazionale (Banca d'Italia).")

    # ── A) MERCATI REALI DELLA REGIONE (ISTAT cube _9, annuale) ──────────────
    c1, c2 = st.columns([2, 1])
    metric_lbl = c1.radio("Metrica (dato reale regionale):", ["Presenze", "Arrivi"],
                          horizontal=True, key="mp_metric")
    dt = "NI" if metric_lbl == "Presenze" else "AR"
    unit = metric_lbl.lower()
    years = L.estero_years(code, dt)
    tbl = None
    if years:
        yr = c2.selectbox("📅 Anno", list(reversed(years)), index=0, key="mp_anno")
        tbl = L.estero_markets_table(code, datatype=dt, year=yr, top=15)
    if tbl is None or tbl.empty:
        st.info("⏳ Dati ISTAT «Paese di origine» per regione (cube _9) non disponibili: "
                "in download o assenti per questo territorio.")
    else:
        st.subheader(f"Grafico 1 — Top mercati esteri in {nome} · {unit} {yr}")
        st.plotly_chart(L.chart_estero_markets(code, datatype=dt, year=yr, top=12),
                        use_container_width=True)
        disp = pd.DataFrame({
            "Mercato": tbl["nome"],
            f"{metric_lbl} {yr}": tbl["valore"].round(0).astype("int64"),
            "Quota % esteri": tbl["quota"].round(1),
            "var. % a/a": tbl["yoy"].map(lambda v: f"{v:+.0f}%" if pd.notna(v) else "—"),
        })
        st.subheader(f"Tabella 1 — Mercati esteri in {nome} · {yr}")
        st.dataframe(disp, hide_index=True, use_container_width=True)
        st.caption("Fonte: ISTAT movimento clienti per paese di residenza (cube _9), dato **reale** per "
                   "regione. «Quota % esteri» = peso del mercato sul totale dei turisti stranieri della regione.")
        opts = dict(zip(tbl["country"], tbl["nome"]))
        default = list(tbl["country"].head(5))
        sel = st.multiselect("Mercati da confrontare nel tempo:", list(opts),
                             default=default, format_func=lambda c: opts.get(c, c), key="mp_trend")
        st.subheader(f"Grafico 2 — Trend storico dei mercati in {nome} (2008→)")
        fig_tr = L.chart_estero_trend(code, sel, datatype=dt)
        if fig_tr is not None:
            st.plotly_chart(fig_tr, use_container_width=True)
        else:
            st.caption("Seleziona almeno un mercato per vedere il trend.")

    # ── B) CONTESTO NAZIONALE (Banca d'Italia: spesa/notti/viaggiatori) ──────
    st.divider()
    st.markdown("#### Contesto nazionale (Banca d'Italia)")
    g = L.bdi_country_annual()
    if g is None or g.empty:
        st.info("Dati Banca d'Italia per paese non disponibili.")
        return
    metric = st.radio("Metrica (dato nazionale BdI):", ["notti", "spesa", "viaggiatori"],
                      horizontal=True, key="mp_bdi_metric")
    st.subheader("Grafico 3 — Mercati per paese nel tempo (Italia)")
    st.plotly_chart(L.chart_bdi_country(metric), use_container_width=True)
    last = int(g["anno"].max())
    cur = g[g["anno"] == last].set_index("code")
    prev = g[g["anno"] == last - 1].set_index("code")
    rows = []
    for c in L.BDI_MARKETS:
        if c in cur.index:
            v = cur.loc[c, metric]
            p = prev.loc[c, metric] if c in prev.index else None
            yoy = (v / p - 1) * 100 if (p and p != 0) else None
            rows.append({"Mercato": c, f"{metric.capitalize()} {last}": round(v),
                         "var. % a/a": (f"{yoy:+.0f}%" if yoy is not None else "—")})
    st.subheader("Tabella 2 — Mercati per paese, Italia (ultimo anno)")
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    st.caption("Unità BdI: notti e viaggiatori in migliaia, spesa in milioni di €. "
               "Mercati: Germania, Austria, Regno Unito, Svizzera, USA, Francia, Spagna.")


def page_online():
    code = st.session_state.get("region_code", L.RG.DEFAULT_REGION)
    nome = L.RG.region(code)["nome"]
    L.page_header("Interesse online (segnali anticipatori)", group="Cosa fare", emoji="🌐",
                  region_code=code,
                  subtitle="Google Trends (per paese) e Wikipedia pageviews (per lingua) anticipano gli arrivi. "
                           "Wikipedia è per LINGUA: DE/AT/CH condividono il tedesco, GB/US l'inglese.")
    yr = st.session_state.get("yr_range", (2019, 2024))
    st.subheader(f"Grafico 1 — Wikipedia — interesse per «{nome}» per lingua · {yr[0]}–{yr[1]}")
    st.plotly_chart(L.chart_wiki(yr, code), use_container_width=True)
    st.subheader("Tabella 1 — Corroborazione del segnale per mercato")
    if is_real:
        L.aggrid_table(pd.DataFrame(L.online_interest(summary, code)), height=240, key="online_grid")
        st.caption("Concordanza = Google Trends e Wikipedia indicano la stessa direzione → segnale più robusto.")
    else:
        st.info("La corroborazione con Google Trends è disponibile in modalità **Reale**.")


def page_home():
    uri = L.home_hero_datauri()
    bg = (f"linear-gradient(120deg, rgba(15,23,42,.62), rgba(124,45,18,.28) 55%, rgba(8,145,178,.52)), url('{uri}')"
          if uri else "linear-gradient(120deg,#0f172a,#7c2d12 55%,#0e6b70)")
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
            <div style="font-size:.78rem;letter-spacing:.16em;opacity:.92">PORTALE NAZIONALE DEL TURISMO</div>
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
    st.caption("Prototipo dimostrativo · Indra Italia S.p.A. — scala nazionale")
    st.caption("Foto: Sassongher (Dolomiti, Alta Badia) · Tiia Monto, CC BY-SA 3.0 · Wikimedia Commons")


def page_advisor_operatori():
    L.page_header("Advisor Operatori", group="Sistema", emoji="🧭",
                  subtitle="Fonti per i dati REALI degli affitti brevi (STR). Riscontri VERIFICATI a luglio 2026.")
    st.success("**Aggiornamento (lug 2026).** ✅ **Inside Airbnb integrata** (pagine «Affitti brevi (STR)» + "
               "«STR Italia — anteprima»). 🔄 Contesto cambiato: il TDH sarà un **prodotto privato da vendere** "
               "→ le fonti a pagamento tornano ammissibili. **AirROI** verificata: copre **~100 mercati italiani** "
               "(città/comune, tutte le regioni, Abruzzo incluso) con metriche reali, a **~$5-10 per snapshot "
               "nazionale**. Dettaglio completo (costi, licenza, lista feed acquistabili) nel file "
               "`dati_manuali/AIRROI e AIRDNA/`.", icon=":material/verified:")
    st.caption("Le tre fonti coprono il **mercato degli affitti brevi** (prezzo, occupazione, ricavi, recensioni). "
               "I dati *proprietari* della demo Operatori (canali di vendita, funnel, conversione, affluenza/giorno) "
               "restano nei gestionali dei singoli operatori e **non esistono come dato acquistabile**.")
    st.markdown("**Vincoli del progetto (aggiornati):** multi-regione, tutta Italia (la regione è una variabile) · "
                "granularità città/comune · serie storica · deploy **privato** → **fonti a pagamento ammesse** "
                "(attenzione alla **licenza di redistribuzione** se il portale è venduto a terzi).")

    st.subheader("Verdetto a colpo d'occhio")
    v1, v2, v3 = st.columns(3)
    with v1.container(border=True):
        st.markdown("#### 🟢 Inside Airbnb")
        st.success("Integrata — base gratuita")
        st.markdown("Dati reali, aperti, senza chiave. 7 città + 3 regioni (no Abruzzo), occupazione *proxy*. "
                    "**Già nel TDH.**")
        st.caption("Costo: gratuito · CC BY 4.0")
    with v2.container(border=True):
        st.markdown("#### 🟢 AirROI")
        st.success("Miglior costo/beneficio nazionale")
        st.markdown("~100 mercati italiani (città/comune, tutte le regioni) con metriche **reali** (occ/ADR/RevPAR/"
                    "ricavi). API pay-as-you-go. **Vincolo: licenza** (no redistribuzione, cache 30gg → deploy privato).")
        st.caption("Costo: ~$5-10 per snapshot Italia · $0,01-0,10/chiamata")
    with v3.container(border=True):
        st.markdown("#### 🟡 AirDNA")
        st.warning("Solo con budget / enterprise")
        st.markdown("La più completa (copertura + storico + benchmarking) ma abbonamento/enterprise e licenza chiusa. "
                    "Conviene solo per esigenze enterprise.")
        st.caption("Costo: $125-600/mese · API enterprise su preventivo")

    st.subheader("Tabella 1 — Matrice comparativa (verificata)")
    matrix = [
        {"Criterio": "Copertura Italia", "Inside Airbnb": "🟢 Integrata — 7 città + 3 regioni (no Abruzzo)",
         "AirROI": "🟢 ~100 mercati (città/comune), tutte le regioni", "AirDNA": "🟢 Ampia + storico profondo"},
        {"Criterio": "Granularità", "Inside Airbnb": "🟡 Annuncio → città/quartiere",
         "AirROI": "🟢 Città/comune (mercato)", "AirDNA": "🟢 Mercato/sottomercato, coordinate"},
        {"Criterio": "Serie storica", "Inside Airbnb": "🟢 via recensioni datate (2009→)",
         "AirROI": "🟡 storico via API (mensile/pacing)", "AirDNA": "🟢 12–60 mesi (mensile)"},
        {"Criterio": "Metriche", "Inside Airbnb": "🟡 grezze + occupazione *proxy*",
         "AirROI": "🟢 reali: occ/ADR/RevPAR/ricavi/ALOS", "AirDNA": "🟢 reali + benchmarking + forecast"},
        {"Criterio": "Accesso", "Inside Airbnb": "🟢 CSV liberi (no chiave)",
         "AirROI": "🟢 API pay-as-you-go + web", "AirDNA": "🟡 SaaS + API enterprise"},
        {"Criterio": "Costo", "Inside Airbnb": "🟢 Gratuito",
         "AirROI": "🟢 ~$5-10 per snapshot Italia", "AirDNA": "🔴 $125-600/mese o enterprise"},
        {"Criterio": "Licenza / redistribuzione", "Inside Airbnb": "🟢 CC BY 4.0 (aperta)",
         "AirROI": "🔴 proprietaria — no redistrib., cache 30gg", "AirDNA": "🔴 proprietaria / chiusa"},
        {"Criterio": "Deploy pubblico?", "Inside Airbnb": "🟢 Sì (committabile)",
         "AirROI": "🔴 No — solo deploy privato", "AirDNA": "🔴 No — solo deploy privato"},
        {"Criterio": "Adatta a Italia intera + reale", "Inside Airbnb": "🟡 parziale (no occ. reale)",
         "AirROI": "🟢 sì (miglior costo/beneficio)", "AirDNA": "🟢 sì (con budget)"},
    ]
    st.dataframe(pd.DataFrame(matrix)[["Criterio", "Inside Airbnb", "AirROI", "AirDNA"]],
                 hide_index=True, use_container_width=True)
    st.caption("🟢 buono · 🟡 parziale · 🔴 debole / vincolo — valutazione rispetto ai vincoli del TDH (prodotto privato).")

    st.subheader("Approfondimento per fonte")
    with st.expander("1 · Inside Airbnb — gratuita, aperta ✅ INTEGRATA"):
        st.markdown(
            "Progetto no-profit che pubblica gli annunci Airbnb città per città. **Già integrata nel TDH** "
            "(pagine «Affitti brevi (STR)» + reader `fetch_str_market`).\n\n"
            "- **Copre in Italia**: 7 città (Roma, Milano, Napoli, Firenze, Venezia, Bologna, Bergamo) + 3 "
            "regioni intere (Puglia, Sicilia, Trentino-A.A.) — **niente Abruzzo**\n"
            "- **Livello**: singolo annuncio (lat/lon, quartiere) → aggregato a città/zona\n"
            "- **Metriche**: n. annunci, prezzo, tipo alloggio, recensioni/qualità, licenza/CIR; occupazione = *proxy*\n"
            "- **Storia**: serie di attività dalle recensioni datate (2009→)\n"
            "- **Licenza**: CC BY 4.0 (aperta, committabile nel repo)")
        pc1, pc2 = st.columns(2)
        pc1.success("**Pro**\n\n- Gratis e ridistribuibile (CC BY)\n- CSV diretto, deploy pubblico ok\n"
                    "- Dato reale e granulare (qualità/licenze)\n- Serie storica via recensioni")
        pc2.error("**Contro**\n\n- Solo 7 città + 3 regioni (no Abruzzo)\n- Occupancy stimata (proxy)\n"
                  "- Solo Airbnb (no Vrbo/Booking)\n- Un solo snapshot corrente (no storico prezzi)")
    with st.expander("2 · AirROI — copertura nazionale reale, low-cost 🟢 (deploy privato)"):
        st.markdown(
            "Miglior **rapporto costo/beneficio** per la copertura nazionale con metriche reali. API "
            "**pay-as-you-go** economica.\n\n"
            "- **Copre in Italia (verificato)**: **~100 mercati** a livello città/comune, **tutte le regioni** "
            "(Abruzzo incluso: es. Atri, Scanno)\n"
            "- **Metriche reali**: occupancy, ADR, RevPAR, revenue, active listings, length of stay, "
            "booking lead time, future pacing, stagionalità (endpoint `markets/metrics/*`)\n"
            "- **Costo**: endpoint di mercato $0,05-0,10/chiamata → **~$5-10 per snapshot di tutta Italia** "
            "(trim. ~$20-40/anno; deposito minimo $10; «Preferred Partner» −50%)\n"
            "- **Licenza (ToS)**: proprietaria — **vietata pubblicazione/redistribuzione**, **cache max 30 giorni**, "
            "licenza Commercial = uso **interno** → utilizzabile **solo nel deploy privato**")
        pc1, pc2 = st.columns(2)
        pc1.success("**Pro**\n\n- 100 mercati IT, tutte le regioni (Abruzzo!)\n- Metriche REALI (occ/ADR/RevPAR/ricavi)\n"
                    "- Costo irrisorio (~$5-10 Italia)\n- API REST pulita, pay-as-you-go")
        pc2.error("**Contro**\n\n- Licenza restrittiva: no repo pubblico, cache 30gg\n- Serve chiave + micro-costo\n"
                  "- Per la VENDITA a terzi serve licenza OEM/redistribuzione\n- Solo Airbnb")
    with st.expander("3 · AirDNA — completa ma cara / enterprise 🟡"):
        st.markdown(
            "Piattaforma commerciale di riferimento (Airbnb+Vrbo+Booking), metriche pronte + benchmarking + "
            "forecast, ma pensata come SaaS per host/gestori; la copertura dati via API è **enterprise**.\n\n"
            "- **Piani (verificati)**: Free $0 · **Research $125/mese** ($400/anno) · **Host $150/mese** "
            "($600/anno) · Property Manager su richiesta · **Enterprise/API su preventivo** (~$250-500/mese o a volume)\n"
            "- **Metriche**: occupancy, ADR, RevPAR, revenue, lead time, LoS, active listings, stagionalità, forecast\n"
            "- **Storia**: 12–60 mesi (mensile)\n"
            "- **Licenza**: proprietaria/chiusa — non redistribuibile")
        pc1, pc2 = st.columns(2)
        pc1.success("**Pro**\n\n- Copertura + storico più profondi\n- Metriche pronte + benchmarking + forecast\n"
                    "- Multi-piattaforma (Airbnb+Vrbo+Booking)")
        pc2.error("**Contro**\n\n- Costo alto; API solo enterprise (preventivo)\n- Licenza chiusa\n"
                  "- Non conveniente vs AirROI per un semplice snapshot nazionale")

    st.subheader("Raccomandazione per il TDH")
    st.markdown(
        "Il TDH sarà un **prodotto privato da vendere** → le fonti a pagamento sono ammesse. Percorso:\n\n"
        "1. **Base gratuita (fatta)** — **Inside Airbnb** integrata per le città/regioni coperte + ISTAT/Trends "
        "per il fondamento multi-regione.\n"
        "2. **Copertura nazionale reale → AirROI** — miglior costo/beneficio (~$5-10 per tutta Italia, "
        "occupazione/ricavi reali). Front-end **già prototipato** nella pagina «STR Italia (anteprima)» con dati "
        "d'esempio, pronto a ricevere l'API reale.\n"
        "3. **AirDNA** — solo se servono storico profondo/benchmarking enterprise e c'è budget dedicato.\n\n"
        "**Prima di attivare AirROI in produzione**: (a) chiave API; (b) reader `markets/metrics/*` che sostituisce "
        "i dati d'esempio (cache ≤30 giorni, chiave nei *secrets*, **dato non committato**, solo deploy privato); "
        "(c) **chiarire con AirROI la licenza di redistribuzione/OEM** se il portale è venduto a clienti terzi.")
    st.info("Dettaglio completo (costi per endpoint, ToS verbatim, **lista dei feed acquistabili** da AirROI e "
            "AirDNA con prezzi e URL) nel file locale `dati_manuali/AIRROI e AIRDNA/` "
            "(`AIRROI_e_AIRDNA.html` + `feed_acquistabili.csv`).", icon=":material/description:")
    st.warning("**Da togliere o marcare “simulato”** nella pagina Operatori: canali, funnel, conversione, "
               "affluenza per giorno — dati proprietari non disponibili apertamente.")

    st.caption("Fonti verificate (lug 2026): Inside Airbnb insideairbnb.com/get-the-data · "
               "AirROI airroi.com/api/pricing + airroi.com/airbnb-data/italy · AirDNA airdna.co/pricing.")


def _it_num(v) -> str:
    """Numero intero con separatore migliaia all'italiana (12.187)."""
    if v is None:
        return "n/d"
    return f"{v:,.0f}".replace(",", ".")


def _render_astat_local_block():
    """Dettaglio locale ricco per la Provincia di Bolzano (fonte ASTAT). Numerazione grafici
    prosegue quella della pagina (Grafico 5-7, Tabella 2)."""
    k = L.astat_kpi()
    if k.get("anno"):
        yoy = k.get("yoy")
        L.kpi_row([
            {"label": f"Presenze {k['anno']}", "value": _it_num(k["presenze_anno"]),
             "delta": (f"{yoy:+.1f}% su {k['anno']-1}" if yoy is not None else None),
             "delta_dir": ("up" if (yoy or 0) >= 0 else "down"),
             "hint": "ultimo anno solare completo"},
            {"label": f"Arrivi {k['anno']}", "value": _it_num(k["arrivi_anno"])},
            {"label": "Esercizi ricettivi", "value": _it_num(k["esercizi"]), "hint": "totale, ultimo anno"},
            {"label": "Posti letto", "value": _it_num(k["posti_letto"])},
            {"label": "Ultimo mese dato", "value": k.get("mese_ultimo") or "n/d"},
        ])
    else:
        st.warning("Cache ASTAT non disponibile. Lancia l'aggiornamento dati (fonte «Alto Adige · ASTAT»).")
        return
    c1, c2 = st.columns([1, 1])
    ind_lbl = c1.radio("Indicatore", ["Presenze", "Arrivi"], horizontal=True, key="astat_ind")
    ind = "presenze" if ind_lbl == "Presenze" else "arrivi"
    anno_da = c2.slider("Dall'anno", 2000, 2025, 2015, key="astat_da")
    st.markdown(f"**Grafico 5 — {ind_lbl} mensili (dal {anno_da})**")
    fig = L.chart_astat_flussi(ind, start_year=anno_da)
    if fig:
        st.plotly_chart(fig, use_container_width=True)
    st.markdown("**Grafico 6 — Profilo stagionale (media mensile, ultimi 3 anni)**")
    fig = L.chart_astat_stagionalita(ind, years=3)
    if fig:
        st.plotly_chart(fig, use_container_width=True)
    st.caption("Stagionalità bimodale (picco estivo + picco neve invernale): benchmark di destinazione matura.")
    cap = L.astat_capacita()
    anno_cap = int(cap["anno"].max()) if not cap.empty else None
    st.markdown(f"**Grafico 7 — Posti letto per categoria ricettiva{f' · {anno_cap}' if anno_cap else ''}**")
    fig = L.chart_astat_capacita()
    if fig:
        st.plotly_chart(fig, use_container_width=True)
    st.markdown("**Tabella 2 — Esercizi e posti letto per categoria**")
    tcap = L.astat_capacita_table()
    if tcap is not None and not tcap.empty:
        show = tcap.rename(columns={"categoria": "Categoria", "esercizi": "Esercizi",
                                    "posti_letto": "Posti letto"}).copy()
        show["Esercizi"] = show["Esercizi"].map(_it_num)
        show["Posti letto"] = show["Posti letto"].map(_it_num)
        st.dataframe(show, hide_index=True, use_container_width=True)
    st.caption("Fonte: ASTAT · Provincia autonoma di Bolzano · SDMX DF_TOUR_ACC_CAP_TOURASS_MONTHLY_1 "
               "(categorie di dettaglio, esclusi gli aggregati per non contare due volte).")


def _render_lombardia_local_block():
    """Dettaglio locale per la Lombardia (Open Data Lombardia): flussi mensili per provincia +
    mercato estero mensile sub-nazionale. Numerazione: Grafico 5-6, Tabella 2."""
    provs = ["Tutta la Lombardia"] + L.lomb_provinces()
    prov = st.selectbox("Provincia", provs, key="lomb_prov")
    scope = None if prov == "Tutta la Lombardia" else prov
    k = L.lomb_kpi(scope)
    if not k.get("anno"):
        st.warning("Cache Open Data Lombardia non disponibile. Lancia l'aggiornamento (fonte «Lombardia»).")
        return
    L.kpi_row([
        {"label": f"Presenze {k['anno']}", "value": _it_num(k["presenze"])},
        {"label": f"Arrivi {k['anno']}", "value": _it_num(k["arrivi"])},
        {"label": "Quota estero", "value": f"{k['quota_estero']:.0f}%" if k["quota_estero"] is not None else "—",
         "hint": "su presenze totali"},
        {"label": "Top mercato estero", "value": k.get("top_estero") or "—"},
    ])
    st.markdown(f"**Grafico 5 — Presenze mensili ({prov})**")
    fig = L.chart_lomb_flussi_mensili(scope)
    if fig:
        st.plotly_chart(fig, use_container_width=True)
    st.markdown(f"**Grafico 6 — Top mercati esteri ({prov}, {k['anno']})**")
    fig = L.chart_lomb_markets(scope, year=k["anno"], top=12)
    if fig:
        st.plotly_chart(fig, use_container_width=True)
    st.markdown("**Tabella 2 — Mercati esteri per presenze**")
    mk = L.lomb_markets_table(scope, year=k["anno"], top=15)
    if mk is not None and not mk.empty:
        show = mk.rename(columns={"nome": "Mercato estero", "presenze": "Presenze",
                                  "arrivi": "Arrivi", "quota": "Quota %"}).copy()
        show["Presenze"] = show["Presenze"].map(_it_num)
        show["Arrivi"] = show["Arrivi"].map(_it_num)
        show["Quota %"] = show["Quota %"].map(lambda v: f"{v:.1f}%")
        st.dataframe(show, hide_index=True, use_container_width=True)
    st.caption("Fonte: Open Data Regione Lombardia (Socrata, dataset xzck-giqt) · mensile 2019-2024 · "
               "provenienza = paese estero (escluse regioni italiane e «non specificato»).")


def _render_toscana_local_block():
    """Dettaglio locale per la Toscana (Open Data Regione Toscana): movimento ANNUALE per
    COMUNE × ambito, split italiani/stranieri. Numerazione: Grafico 5-7, Tabella 2."""
    provs = ["Tutta la Toscana"] + L.tosc_provinces()
    prov = st.selectbox("Provincia", provs, key="tosc_prov")
    scope = None if prov == "Tutta la Toscana" else prov
    k = L.tosc_kpi(scope)
    if not k.get("anno"):
        st.warning("Cache Open Data Toscana non disponibile. Lancia l'aggiornamento (fonte «Toscana»).")
        return
    L.kpi_row([
        {"label": f"Presenze {k['anno']}", "value": _it_num(k["presenze"])},
        {"label": f"Arrivi {k['anno']}", "value": _it_num(k["arrivi"])},
        {"label": "Quota estero", "value": f"{k['quota_estero']:.0f}%" if k["quota_estero"] is not None else "—",
         "hint": "su presenze totali"},
        {"label": "Comune n.1", "value": k.get("top_comune") or "—", "hint": "quota su presenze"},
    ])
    st.markdown(f"**Grafico 5 — Presenze annuali per origine ({prov})**")
    fig = L.chart_tosc_yearly(scope)
    if fig:
        st.plotly_chart(fig, use_container_width=True)
    st.markdown(f"**Grafico 6 — Comuni per presenze ({prov}, {k['anno']})**")
    fig = L.chart_tosc_top_comuni(scope, year=k["anno"], top=12)
    if fig:
        st.plotly_chart(fig, use_container_width=True)
    st.markdown(f"**Grafico 7 — Presenze per ambito turistico ({prov}, {k['anno']})**")
    fig = L.chart_tosc_ambiti(scope, year=k["anno"], top=12)
    if fig:
        st.plotly_chart(fig, use_container_width=True)
    st.markdown("**Tabella 2 — Comuni per presenze**")
    tc = L.tosc_top_comuni(scope, year=k["anno"], top=20)
    if tc is not None and not tc.empty:
        show = tc.rename(columns={"nome": "Comune", "presenze": "Presenze", "arrivi": "Arrivi",
                                  "quota_estero": "Quota estero %", "quota": "Quota %"}).copy()
        show["Presenze"] = show["Presenze"].map(_it_num)
        show["Arrivi"] = show["Arrivi"].map(_it_num)
        show["Quota estero %"] = show["Quota estero %"].map(lambda v: f"{v:.0f}%")
        show["Quota %"] = show["Quota %"].map(lambda v: f"{v:.1f}%")
        st.dataframe(show, hide_index=True, use_container_width=True)
    st.caption("Fonte: Open Data Regione Toscana (CKAN, dati.toscana.it) · annuale 2018-2025 · "
               "movimento per comune × ambito, split italiani/stranieri (escluse locazioni brevi).")


def _render_sardegna_local_block():
    """Dettaglio locale per la Sardegna (Osservatorio, export manuale): movimento MENSILE per
    comune × mercato estero. La fonte più ricca del motore. Numerazione: Grafico 5-7, Tabella 2."""
    provs = ["Tutta la Sardegna"] + L.sard_provinces()
    prov = st.selectbox("Zona/Provincia", provs, key="sard_prov")
    scope = None if prov == "Tutta la Sardegna" else prov
    k = L.sard_kpi(scope)
    if not k.get("anno"):
        st.warning("Cache Osservatorio Sardegna non disponibile. Servono i CSV in "
                   "`dati_manuali/sardegna/` e la ricostruzione (fonte «Sardegna»).")
        return
    L.kpi_row([
        {"label": f"Presenze {k['anno']}", "value": _it_num(k["presenze"])},
        {"label": f"Arrivi {k['anno']}", "value": _it_num(k["arrivi"])},
        {"label": "Quota estero", "value": f"{k['quota_estero']:.0f}%" if k["quota_estero"] is not None else "—",
         "hint": "su presenze totali"},
        {"label": "Comune n.1", "value": k.get("top_comune") or "—", "hint": "quota su presenze"},
    ])
    st.markdown(f"**Grafico 5 — Presenze mensili ({prov})**")
    fig = L.chart_sard_flussi_mensili(scope)
    if fig:
        st.plotly_chart(fig, use_container_width=True)
    st.markdown(f"**Grafico 6 — Top mercati esteri ({prov}, {k['anno']})**")
    fig = L.chart_sard_markets(scope, year=k["anno"], top=12)
    if fig:
        st.plotly_chart(fig, use_container_width=True)
    st.markdown(f"**Grafico 7 — Comuni per presenze ({prov}, {k['anno']})**")
    fig = L.chart_sard_top_comuni(scope, year=k["anno"], top=12)
    if fig:
        st.plotly_chart(fig, use_container_width=True)
    st.markdown("**Tabella 2 — Mercati esteri per presenze**")
    mk = L.sard_markets_table(scope, year=k["anno"], top=15)
    if mk is not None and not mk.empty:
        show = mk.rename(columns={"nome": "Mercato estero", "presenze": "Presenze",
                                  "arrivi": "Arrivi", "quota": "Quota %"}).copy()
        show["Presenze"] = show["Presenze"].map(_it_num)
        show["Arrivi"] = show["Arrivi"].map(_it_num)
        show["Quota %"] = show["Quota %"].map(lambda v: f"{v:.1f}%")
        st.dataframe(show, hide_index=True, use_container_width=True)
    st.caption("Fonte: Osservatorio del Turismo Sardegna (SIRED, CC-BY) · mensile 2021-2025 · "
               "movimento per comune × macro-tipologia × mercato di provenienza; export manuale. "
               "Zone = raggruppamento provinciale dell'anno più recente.")


def page_base_dati_regionale():
    code = st.session_state.get("region_code", L.RG.DEFAULT_REGION)
    info = L.RG.region(code)
    L.page_header("Base Dati Regionale", group="Cosa è successo", emoji="🗃️",
                  region_code=code,
                  subtitle="Quali dati coprono la regione selezionata (catalogo), sintesi ISTAT e "
                           "dettaglio locale dove esiste una fonte territoriale ricca.")
    st.caption("Segue il **selettore di regione** in alto a sinistra. Il catalogo dice cosa abbiamo e "
               "con che granularità; la sintesi mostra la realtà ISTAT; il dettaglio locale aggiunge le "
               "fonti territoriali (oggi: ASTAT/Bolzano, Lombardia, Toscana, Osservatorio Sardegna).")

    # Snapshot ISTAT (chiamate live): se ISTAT è giù, catalogo e dati offline restano comunque
    ov = None
    try:
        ov = L.region_overview(code)
    except Exception as e:  # noqa: BLE001
        st.warning(f"ISTAT non raggiungibile ora per {info['nome']} ({type(e).__name__}): "
                   "il catalogo e le fonti offline restano disponibili; presenze/capacità live possono mancare.")

    # ── CATALOGO ──────────────────────────────────────────────────
    st.subheader("Tabella 1 — Fonti dati che coprono questa regione")
    st.dataframe(pd.DataFrame(L.region_data_catalog(code, ov=ov)),
                 hide_index=True, use_container_width=True)
    st.caption("🟢 presente · 🟡 parziale / da scaricare · 🔴 non disponibile per questo territorio. "
               "«Ultimo» = periodo più recente in cache.")

    # ── SINTESI ISTAT ─────────────────────────────────────────────
    st.subheader("Sintesi ISTAT della regione")
    kpis = []
    if ov is not None and isinstance(ov.get("presenze"), pd.DataFrame):
        obs = ov["presenze"].dropna(subset=["stranieri"]) if "stranieri" in ov["presenze"] else ov["presenze"]
        if not obs.empty:
            kpis.append({"label": "Presenze straniere (ultimo mese)",
                         "value": _it_num(int(obs["stranieri"].iloc[-1])),
                         "hint": obs["date"].max().strftime("%m/%Y")})
    if ov is not None and ov.get("letti"):
        kpis.append({"label": f"Posti letto ({ov['anno_letti']})", "value": _it_num(ov["letti"])})
    sp = L.region_spend(code)
    if sp:
        kpis.append({"label": "Spesa straniera (BdI)", "value": f"{sp[0]:,.0f} M€".replace(",", "."),
                     "hint": "totale Italia" if sp[1] is None else f"#{sp[1]} su {sp[2]} regioni"})
    yrs = L.estero_years(code)
    if yrs:
        mk = L.estero_markets(code, year=max(yrs))
        kpis.append({"label": f"Mercati esteri ({max(yrs)})",
                     "value": f"{len(mk)} paesi" if mk is not None else "—",
                     "hint": "da ISTAT _9"})
    if kpis:
        L.kpi_row(kpis)

    g1, g2 = st.columns([3, 2])
    with g1:
        if ov is not None and isinstance(ov.get("presenze"), pd.DataFrame) and not ov["presenze"].empty:
            st.markdown("**Grafico 1 — Presenze mensili (totale e straniere)**")
            st.plotly_chart(L.chart_region_presences(ov["presenze"]), use_container_width=True)
    with g2:
        st.markdown("**Grafico 2 — Top mercati esteri per paese (ISTAT _9)**")
        mfig = L.chart_estero_markets(code, top=12)
        if mfig:
            st.plotly_chart(mfig, use_container_width=True)
        else:
            st.info("ISTAT _9 non ha il dettaglio per singolo paese per questo territorio.")
    lfig = L.chart_region_letti(code)
    if lfig:
        st.markdown("**Grafico 3 — Posti letto per anno (ISTAT capacità)**")
        st.plotly_chart(lfig, use_container_width=True)

    # ── DOMANDA DEI RESIDENTI (scopo del viaggio) — ISTAT Viaggi e Vacanze, tutte le regioni ──
    tk = L.turnot_kpi(code)
    if tk.get("anno"):
        st.markdown("**🧳 Domanda dei residenti — perché si viaggia** (ISTAT Viaggi e Vacanze, "
                    "notti dei residenti per regione di destinazione)")
        L.kpi_row([
            {"label": f"Notti residenti ({tk['anno']})", "value": _it_num(tk["notti"])},
            {"label": "Quota vacanza lunga",
             "value": f"{tk['quota_vac_lunga']:.0f}%" if tk["quota_vac_lunga"] is not None else "—",
             "hint": "4+ notti"},
            {"label": "Quota lavoro",
             "value": f"{tk['quota_lavoro']:.0f}%" if tk["quota_lavoro"] is not None else "—",
             "hint": "vs vacanza"},
        ])
        st.markdown("**Grafico 4 — Notti dei residenti per scopo del viaggio (per anno)**")
        tfig = L.chart_turnot_purpose(code)
        if tfig:
            st.plotly_chart(tfig, use_container_width=True)
        st.caption("Fonte: ISTAT · Viaggi e Vacanze (DCCV_TURNOT) · indagine campionaria (valori stimati) · "
                   "notti dei RESIDENTI in Italia per regione di destinazione e scopo. Universo diverso "
                   "dal movimento negli esercizi (lato domanda).")

    # ── DETTAGLIO LOCALE ──────────────────────────────────────────
    st.divider()
    st.subheader("Dettaglio locale (fonte territoriale ricca)")
    if code == "ITD1":
        st.caption("**Provincia di Bolzano · ASTAT** — flussi mensili recenti + lato offerta per categoria, "
                   "dettaglio che le basi ISTAT nazionali non danno.")
        _render_astat_local_block()
    elif code == "ITC4":
        st.caption("**Open Data Lombardia** — flussi mensili per **provincia** e, novità, il **mercato estero "
                   "mensile** a livello sub-nazionale (che ISTAT dà solo annuale).")
        _render_lombardia_local_block()
    elif code == "ITE1":
        st.caption("**Open Data Regione Toscana** — movimento clienti a livello **comunale** (~272 comuni) "
                   "per ambito turistico, con split italiani/stranieri: un dettaglio sotto il livello "
                   "provinciale che le basi ISTAT non danno.")
        _render_toscana_local_block()
    elif code == "ITG2":
        st.caption("**Osservatorio del Turismo Sardegna** — la base dati più ricca del motore: movimento "
                   "**mensile** per **comune** e **mercato estero** di provenienza (SIRED, CC-BY, export manuale).")
        _render_sardegna_local_block()
    else:
        st.info("Per questa regione non è ancora agganciata una fonte locale ricca (mensile + dettaglio). "
                "Oggi disponibili: **Bolzano** (ASTAT), **Lombardia**, **Toscana** e **Sardegna** "
                "(Open Data regionali).")


def render_topbar():
    """Barra superiore: contesto a sinistra, selettore Regione a destra (design Istituzionale)."""
    left, right = st.columns([3.4, 1.15], vertical_alignment="center")
    with left:
        st.markdown("<div style='font-size:.7rem;letter-spacing:.16em;text-transform:uppercase;"
                    "color:#8aa0a4;font-weight:600;padding-top:6px'>Strumento ad uso interno · scala nazionale</div>",
                    unsafe_allow_html=True)
    with right:
        _regn = L.RG.region_names()
        st.selectbox("📍 Regione", list(_regn), format_func=lambda c: _regn[c], key="region_code",
                     help="Regione attiva su tutte le pagine multi-regione (anche cliccando la mappa in «Italia»).")
    st.markdown("<div style='border-bottom:1px solid #e4ebec;margin:.1rem 0 1.1rem'></div>",
                unsafe_allow_html=True)


# ──────────────────── NAVIGAZIONE A DUE PILASTRI (st.navigation) + DISPATCH ────────────────────
SINTESI_PAGE = st.Page(page_sintesi, title="Sintesi", icon=":material/dashboard:")
pg = st.navigation({
    "Panoramica": [
        st.Page(page_home, title="Home", icon=":material/home:", default=True),
        st.Page(page_italia, title="Italia", icon=":material/map:"),
        st.Page(page_regione, title="Regione", icon=":material/public:"),
        st.Page(page_mercati_origine, title="Mercati d'origine", icon=":material/travel_explore:"),
        SINTESI_PAGE,
        st.Page(page_confronto_regioni, title="Confronto regioni", icon=":material/bar_chart:"),
    ],
    "Cosa è successo": [
        st.Page(page_province, title="Per provincia", icon=":material/place:"),
        st.Page(page_struttura, title="Per struttura", icon=":material/hotel:"),
        st.Page(page_occupazione, title="Occupazione", icon=":material/king_bed:"),
        st.Page(page_spesa, title="Spesa turistica", icon=":material/payments:"),
        st.Page(page_mercati_paese, title="Mercati per paese", icon=":material/public:"),
        st.Page(page_base_dati_regionale, title="Base Dati Regionale", icon=":material/dataset:"),
        st.Page(page_affitti_brevi, title="Affitti brevi (STR)", icon=":material/home:"),
        st.Page(page_str_nazionale, title="STR Italia (anteprima)", icon=":material/insights:"),
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
        st.Page(page_advisor_operatori, title="Advisor Operatori", icon=":material/support_agent:"),
    ],
})
# Pagine che hanno senso a livello NAZIONALE (vista d'insieme «Italia») senza una regione.
# Step B: le descrittive Regione/Struttura/Occupazione/Spesa usano il totale Italia (ISTAT area="IT").
NATIONAL_OK = {"Home", "Italia", "Confronto regioni", "Mercati per paese", "Mercati d'origine",
               "Operatori (demo)", "Affitti brevi (STR)", "STR Italia (anteprima)", "Assistente", "Architettura", "Gestione dati", "Advisor Operatori",
               "Base Dati Regionale",
               "Regione", "Per provincia", "Per struttura", "Occupazione", "Spesa turistica"}

# Ogni pagina (tranne Home) ha il proprio page_header con breadcrumb + badge regione:
# nessun hero globale (evita il doppio banner). hero() resta disponibile ma non è più usato qui.
if pg.title != "Home":
    render_topbar()
_rc = st.session_state.get("region_code", L.RG.NATIONAL)

if L.RG.is_national(_rc) and pg.title not in NATIONAL_OK:
    # In modalità «Italia» le pagine di dettaglio per regione non mostrano di nascosto
    # una regione di default: invitano a sceglierne una o a usare le viste d'insieme.
    st.info(
        "🇮🇹 **Stai vedendo l'Italia.** Questa pagina mostra il **dettaglio per regione**.\n\n"
        "• Scegli una **regione** dal selettore in alto a sinistra per vedere i suoi dati, **oppure**\n"
        "• resta sulla vista d'insieme con **Italia** (mappa cliccabile) e **Confronto regioni**.",
        icon=":material/travel_explore:")
    st.caption("La vista nazionale **aggregata** di questa pagina (presenze/struttura/occupazione Italia) "
               "arriverà nello Step B.")
else:
    pg.run()
