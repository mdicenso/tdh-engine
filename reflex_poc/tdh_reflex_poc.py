"""TDH — UI in Reflex (Python → React). Design 'Istituzionale', DATI REALI.

Legge dal data-layer puro `tdh_data` (ISTAT presenze/capacità, Banca d'Italia spesa,
ISTAT esteri per paese) — gli stessi numeri del cruscotto Streamlit. Multi-regione
(20 regioni + Italia). Multi-pagina: "/" Regione · "/ranking" Ranking regioni.
Migrazione TDH → Reflex, Fase 1-2 (11/12-07-2026).
"""
import os
import sys

import reflex as rx
import plotly.graph_objects as go

# ── aggancio al data-layer ───────────────────────────────────────────────────
# Cerca il data-layer in ordine: (1) override via env, (2) TDH_Engine LIVE (dev
# locale: gli edit si riflettono subito), (3) bundle auto-contenuto `tdh_engine/`
# accanto a questo file (usato in DEPLOY, dove il path locale non esiste).
_HERE = os.path.dirname(os.path.abspath(__file__))
_CANDIDATES = [
    os.environ.get("TDH_ENGINE_DIR"),
    r"C:/Users/mcenso/OneDrive - Indra/@_Desktop_ OLD/@@@_Appoggio AI/Work_Area/"
    r"Programma Abruzzo/Motore Tourism Data HUB/TDH_Engine",
    os.path.join(_HERE, "tdh_engine"),
]
D = None
_IMPORT_ERR = ""
try:
    _TDH_ENGINE = next((p for p in _CANDIDATES
                        if p and os.path.exists(os.path.join(p, "tdh_data.py"))), None)
    if _TDH_ENGINE and _TDH_ENGINE not in sys.path:
        sys.path.insert(0, _TDH_ENGINE)
    if _TDH_ENGINE is None:
        _IMPORT_ERR = ("data-layer non trovato. Candidati provati:\n"
                       + "\n".join(f"- {c}" for c in _CANDIDATES if c)
                       + f"\n_HERE={_HERE}\ncontenuto _HERE: " + repr(sorted(os.listdir(_HERE))[:40]))
    else:
        import tdh_data as D  # noqa: E402
except Exception as _e:  # noqa: BLE001
    import traceback as _tb
    _IMPORT_ERR = _tb.format_exc()
    D = None

# ── design tokens (Istituzionale) ──
ACCENT = "#0e6b70"; ACCENT_INK = "#0a4f53"; INK = "#10262a"; MUT = "#5c7176"
FAINT = "#8aa0a4"; LINE = "#e4ebec"; BG = "#f5f7f7"; PANEL = "#ffffff"; MUTED_BAR = "#a9c3c5"

# elenco regioni per il selettore: Italia + le 20 regioni (nome → codice NUTS2)
REGIONI = ([("Italia", "ITALIA")] + list(D.REGIONI_SELECT)) if D is not None else [("Italia", "ITALIA")]
NOMI = [n for n, _ in REGIONI]
NAME2CODE = {n: c for n, c in REGIONI}

# territori STR (Inside Airbnb) — indipendenti dalla regione
STR_TERRITORI = D.str_territori_list() if D is not None else []
STR_NOMI = [n for n, _ in STR_TERRITORI]
STR_NAME2SLUG = {n: s for n, s in STR_TERRITORI}

# contenuto statico della pagina Architettura
ARCH = D.architettura_content() if D is not None else {
    "livelli": [], "sorgenti": [], "roadmap": [], "principi": [], "motore_statistico": []}

# ── cancello di accesso (username/password) — credenziali da env TDH_LOGINS ──
# Formato: "user1:pass1;user2:pass2". Se la variabile NON è impostata → gate APERTO
# (comodo in locale). Le password NON stanno nel codice (repo pubblico).
import hashlib  # noqa: E402
_LOGINS_RAW = os.environ.get("TDH_LOGINS", "")


def _parse_logins(raw):
    d = {}
    for pair in raw.split(";"):
        if ":" in pair:
            u, p = pair.split(":", 1)
            if u.strip():
                d[u.strip()] = p.strip()
    return d


LOGINS = _parse_logins(_LOGINS_RAW)
AUTH_REQUIRED = bool(LOGINS)
# token del cookie derivato dal segreto (chi non ha la password non può falsificarlo)
_COOKIE_TOKEN = (hashlib.sha256(("tdh-gate::" + _LOGINS_RAW).encode()).hexdigest()[:24]
                 if AUTH_REQUIRED else "open")


class AuthState(rx.State):
    auth_cookie: str = rx.Cookie("")
    auth_error: str = ""

    @rx.var
    def is_authed(self) -> bool:
        return (not AUTH_REQUIRED) or (self.auth_cookie == _COOKIE_TOKEN)

    @rx.event
    def login(self, form_data: dict):
        u = (form_data.get("username") or "").strip()
        p = form_data.get("password") or ""
        if p and LOGINS.get(u) == p:
            self.auth_cookie = _COOKIE_TOKEN
            self.auth_error = ""
        else:
            self.auth_error = "Credenziali non valide."

    @rx.event
    def logout(self):
        self.auth_cookie = ""


def login_view() -> rx.Component:
    return rx.center(
        rx.vstack(
            logo(),
            rx.heading("Accesso riservato", size="6", color=INK, margin_top="6px"),
            rx.text("Turism Data Hub — inserisci le credenziali per continuare.",
                    color=MUT, font_size="0.88rem", text_align="center"),
            rx.form(
                rx.vstack(
                    rx.input(placeholder="Username", name="username", width="100%", size="3"),
                    rx.input(placeholder="Password", name="password", type="password",
                             width="100%", size="3"),
                    rx.cond(AuthState.auth_error != "",
                            rx.text(AuthState.auth_error, color="#dc2626", font_size="0.82rem"),
                            rx.box()),
                    rx.button("Entra", type="submit", width="100%", size="3",
                              background=ACCENT, color="white"),
                    spacing="3", width="100%"),
                on_submit=AuthState.login, width="100%"),
            spacing="3", width="360px", align="center", background=PANEL,
            border=f"1px solid {LINE}", border_radius="18px", padding="34px 30px"),
        height="100vh", width="100%", background=BG)


class State(rx.State):
    boot_error: str = ""           # se non vuoto: mostra un banner con l'errore di caricamento
    region_code: str = "ITE1"      # default: Toscana
    region_name: str = "Toscana"
    titolo: str = "Toscana — quadro turistico"
    kpi_presenze: str = "—"; kpi_presenze_periodo: str = "—"
    kpi_letti: str = "—"; kpi_letti_anno: str = "—"
    kpi_spesa: str = "—"; kpi_spesa_rank: str = "—"
    kpi_mercati: str = "—"; kpi_mercati_anno: str = "—"
    serie_mesi: list[str] = []
    serie_presenze: list[float] = []
    mercati_nomi: list[str] = []
    mercati_valori: list[float] = []
    mercati_rows: list[dict] = []
    # ranking regioni (indipendente dalla regione; l'evidenziazione dipende da region_code)
    rank_regioni: list[dict] = []
    italia_spesa: str = "—"
    it_presenze: str = "—"; it_mercati: str = "—"
    home_top: list[dict] = []
    # confronto regioni (indipendente dalla regione; evidenzia quella selezionata)
    cf_rows: list[dict] = []
    cf_n: str = "—"; cf_top_spesa: str = "—"; cf_top_occ: str = "—"
    _cf_names: list = []; _cf_codes: list = []; _cf_spesa: list = []; _cf_occ: list = []; _cf_letti: list = []
    # gestione dati (inventario sorgenti, indipendente dalla regione)
    ges_rows: list[dict] = []
    ges_n: str = "—"; ges_ok: str = "—"; ges_live: str = "—"
    # base dati regionale (pannello pluriennale, dipende dalla regione).
    # Le serie numeriche hanno "buchi" (None) → backend vars (_): consumate solo lato
    # server nei grafici, non serializzate al client.
    _bd_years: list = []
    _bd_pres_tot: list = []
    _bd_pres_str: list = []
    _bd_spesa: list = []
    bd_rows: list[dict] = []
    bd_k_sviagg: str = "—"; bd_k_sviagg_a: str = "—"
    bd_k_snotte: str = "—"; bd_k_snotte_a: str = "—"
    bd_k_occ: str = "—"; bd_k_occ_a: str = "—"
    bd_k_quota: str = "—"; bd_k_quota_a: str = "—"
    # mappa d'Italia (caricata una volta; l'evidenziazione dipende da region_code).
    # geojson pesante → backend vars (_): finisce solo dentro la figura, non nello stato client.
    _map_geojson: dict = {}
    _map_names: list = []
    _map_codes: list = []
    _map_z: list = []
    # mercati d'origine (dipende dalla regione)
    _me_bar_nomi: list = []
    _me_bar_val: list = []
    _me_line_years: list = []
    _me_line_series: list = []
    me_rows: list[dict] = []
    me_anno: str = "—"; me_n: str = "—"; me_primo: str = "—"; me_primo_val: str = "—"
    # affitti brevi / STR (Inside Airbnb) — indipendente dalla regione (selettore proprio)
    str_slug: str = "rome"
    str_terr_nome: str = "Roma"; str_tipo: str = "—"
    str_k_annunci: str = "—"; str_k_adr: str = "—"; str_k_intero: str = "—"
    str_k_multihost: str = "—"; str_k_licenza: str = "—"; str_k_rating: str = "—"
    _str_adr_nomi: list = []; _str_adr_val: list = []; _str_adr_slugs: list = []
    _str_zone_nomi: list = []; _str_zone_val: list = []
    _str_room_nomi: list = []; _str_room_val: list = []
    _str_rev_x: list = []; _str_rev_y: list = []
    # spesa turistica (dipende dalla regione)
    _sp_years: list = []; _sp_spesa: list = []; _sp_viagg_val: list = []
    sp_rows: list[dict] = []
    sp_k_anno: str = "—"; sp_k_spesa: str = "—"; sp_k_viagg: str = "—"
    sp_k_notte: str = "—"; sp_k_permanenza: str = "—"
    # per provincia (solo-cache, dipende dalla regione)
    prov_has_region: bool = True
    prov_has_data: bool = False
    prov_has_note: bool = False
    prov_note: str = ""
    prov_n: str = "0"
    prov_top_nome: str = "—"; prov_top_presenze: str = "—"; prov_top_peso: str = "—"; prov_share3: str = "—"
    _prov_bar_nomi: list = []; _prov_bar_val: list = []
    prov_rows: list[dict] = []
    # per struttura (alberghiero vs extra, dipende dalla regione)
    st_has_data: bool = False
    st_alberghiero: str = "—"; st_extra: str = "—"; st_quota_alb: str = "—"; st_quota_ext: str = "—"
    _st_x: list = []; _st_alb: list = []; _st_ext: list = []
    # azioni & budget (allocatore, dipende dalla regione)
    azioni_rows: list[dict] = []
    az_n_alta: str = "—"; az_n_aumentare: str = "—"; az_picco_top: str = "—"
    az_region: str = "—"; az_has_national: bool = False; az_error: str = ""
    # interesse online (Google Trends)
    _ie_series: list = []
    ie_rows: list[dict] = []
    ie_keyword: str = "—"; ie_n: str = "—"; ie_top_nome: str = "—"; ie_top_mom: str = "—"
    # forecast presenze (motore statistico)
    _fc_hist_x: list = []; _fc_hist_y: list = []
    _fc_x: list = []; _fc_mean: list = []; _fc_lo: list = []; _fc_hi: list = []
    fc_region: str = "—"; fc_has_national: bool = False; fc_error: str = ""
    fc_mape: str = "—"; fc_beats: str = "—"; fc_lag: str = "—"
    fc_reading: list[str] = []

    def _load(self):
        s = D.regione_snapshot(self.region_code)
        self.region_name = s["nome"]
        self.titolo = s["titolo"]
        self.kpi_presenze = s["kpi_presenze"]
        self.kpi_presenze_periodo = s["kpi_presenze_periodo"]
        self.kpi_letti = s["kpi_letti"]
        self.kpi_letti_anno = s["kpi_letti_anno"]
        self.kpi_spesa = s["kpi_spesa"]
        self.kpi_spesa_rank = s["kpi_spesa_rank"]
        self.kpi_mercati = s["kpi_mercati"]
        self.kpi_mercati_anno = s["kpi_mercati_anno"]
        self.serie_mesi = s["serie_mesi"]
        self.serie_presenze = s["serie_presenze"]
        self.mercati_nomi = [m["nome"] for m in s["mercati_top"]]
        self.mercati_valori = [m["valore"] for m in s["mercati_top"]]
        tot = sum(m["valore"] for m in s["mercati_top"]) or 1.0
        self.mercati_rows = [
            {"nome": m["nome"],
             "presenze": f"{int(round(m['valore'])):,}".replace(",", "."),
             "quota": f"{m['valore'] / tot * 100:.1f}%"}
            for m in s["mercati_top"]
        ]
        # base dati regionale (pannello pluriennale)
        b = D.base_dati_snapshot(self.region_code)
        self._bd_years = b["years"]
        self._bd_pres_tot = b["pres_tot"]
        self._bd_pres_str = b["pres_str"]
        self._bd_spesa = b["spesa"]
        self.bd_rows = b["rows"]
        k = b["kpi"]
        self.bd_k_sviagg, self.bd_k_sviagg_a = k["spesa_per_viagg"]["val"], "anno " + k["spesa_per_viagg"]["anno"]
        self.bd_k_snotte, self.bd_k_snotte_a = k["spesa_per_notte"]["val"], "anno " + k["spesa_per_notte"]["anno"]
        self.bd_k_occ, self.bd_k_occ_a = k["occ"]["val"], "anno " + k["occ"]["anno"]
        self.bd_k_quota, self.bd_k_quota_a = k["quota_str"]["val"], "anno " + k["quota_str"]["anno"]
        # spesa turistica
        sp = D.spesa_snapshot(self.region_code)
        self._sp_years, self._sp_spesa, self._sp_viagg_val = sp["years"], sp["spesa"], sp["sp_viagg"]
        self.sp_rows = sp["rows"]
        kk = sp["kpi"]
        self.sp_k_anno = kk.get("anno", "—")
        self.sp_k_spesa = kk.get("spesa", "—")
        self.sp_k_viagg = kk.get("sp_viagg", "—")
        self.sp_k_notte = kk.get("sp_notte", "—")
        self.sp_k_permanenza = kk.get("permanenza", "—")
        # per provincia (solo-cache)
        pv = D.province_snapshot(self.region_code)
        self.prov_has_region = pv["has_region"]
        self.prov_has_data = pv["n"] > 0
        self.prov_n = str(pv["n"])
        self._prov_bar_nomi, self._prov_bar_val = pv["bar_nomi"], pv["bar_val"]
        self.prov_rows = pv["rows"]
        self.prov_top_nome, self.prov_top_presenze = pv["top_nome"], pv["top_presenze"]
        self.prov_top_peso, self.prov_share3 = pv["top_peso"], pv["share_top3"]
        man = pv["n_mancanti"]
        self.prov_has_note = man > 0
        self.prov_note = (f"{man} province non ancora in cache (prefetch dati in corso — "
                          "ricarica tra poco per vederle)." if man else "")
        # per struttura (alberghiero vs extra)
        stt = D.struttura_snapshot(self.region_code)
        self.st_has_data = stt["has_data"]
        self.st_alberghiero, self.st_extra = stt["alberghiero"], stt["extra"]
        self.st_quota_alb, self.st_quota_ext = stt["quota_alb"], stt["quota_ext"]
        self._st_x, self._st_alb, self._st_ext = stt["x"], stt["alb"], stt["ext"]
        # azioni & budget (allocatore)
        az = D.azioni_snapshot(self.region_code)
        self.azioni_rows = az["actions"]
        self.az_n_alta, self.az_n_aumentare = str(az["n_alta"]), str(az["n_aumentare"])
        self.az_picco_top, self.az_region = az["picco_top"], az["region"]
        self.az_has_national, self.az_error = az["has_national"], az["error"]
        # interesse online (Google Trends)
        ie = D.interesse_snapshot(self.region_code)
        self._ie_series = ie["series"]
        self.ie_rows = ie["rows"]
        self.ie_keyword, self.ie_n = ie["keyword"], str(ie["n"])
        self.ie_top_nome, self.ie_top_mom = ie["top_nome"], ie["top_mom"]
        # forecast presenze (motore statistico)
        fcs = D.forecast_snapshot(self.region_code)
        self._fc_hist_x, self._fc_hist_y = fcs["hist_x"], fcs["hist_y"]
        self._fc_x, self._fc_mean = fcs["fc_x"], fcs["fc_mean"]
        self._fc_lo, self._fc_hi = fcs["fc_lo"], fcs["fc_hi"]
        self.fc_region, self.fc_has_national, self.fc_error = fcs["region"], fcs["has_national"], fcs["error"]
        self.fc_mape, self.fc_beats, self.fc_lag = fcs["mape"], fcs["beats"], fcs["lag"]
        self.fc_reading = fcs["reading"]
        # mercati d'origine
        me = D.mercati_snapshot(self.region_code)
        self._me_bar_nomi, self._me_bar_val = me["bar_nomi"], me["bar_val"]
        self._me_line_years, self._me_line_series = me["line_years"], me["line_series"]
        self.me_rows = me["rows"]
        self.me_anno = str(me["anno"]) if me["anno"] else "—"
        self.me_n, self.me_primo, self.me_primo_val = str(me["n"]), me["primo"], me["primo_val"]

    @rx.event
    def on_load(self):
        if D is None:
            self.boot_error = "Data-layer non caricato (import fallito):\n\n" + _IMPORT_ERR[-1800:]
            return
        try:
            self._load()
            if not self.rank_regioni:
                self.rank_regioni = [dict(r) for r in D.regions_spend_ranking()]
                tot = D.region_spend("ITALIA")
                self.italia_spesa = f"{D._it_int(tot[0])} M€" if tot else "—"
                it = D.regione_snapshot("ITALIA")
                self.it_presenze, self.it_mercati = it["kpi_presenze"], it["kpi_mercati"]
                self.home_top = [{"regione": r["regione"], "spesa": f"{D._it_int(r['spesa_M'])} M€"}
                                 for r in list(D.regions_spend_ranking())[:6]]
            if not self._map_codes:
                m = D.mappa_snapshot()
                self._map_geojson = m["geojson"] or {}
                self._map_names, self._map_codes, self._map_z = m["names"], m["codes"], m["z"]
            if not self.cf_rows:
                cf = D.confronto_snapshot()
                self.cf_rows = cf["rows"]
                self.cf_n, self.cf_top_spesa, self.cf_top_occ = str(cf["n"]), cf["top_spesa"], cf["top_occ"]
                self._cf_names, self._cf_codes = cf["sc_names"], cf["sc_codes"]
                self._cf_spesa, self._cf_occ, self._cf_letti = cf["sc_spesa"], cf["sc_occ"], cf["sc_letti"]
            if not self.ges_rows:
                g = D.gestione_snapshot()
                self.ges_rows = g["rows"]
                self.ges_n, self.ges_ok, self.ges_live = str(g["n_fonti"]), str(g["n_ok"]), str(g["n_live"])
            if not self._str_adr_slugs:
                self._load_str()
            self.boot_error = ""
        except Exception as e:  # noqa: BLE001
            import traceback
            self.boot_error = f"Errore nel caricamento dati: {type(e).__name__}: {e}\n\n" + traceback.format_exc()[-1800:]

    def _load_str(self):
        s = D.str_snapshot(self.str_slug)
        self.str_terr_nome, self.str_tipo = s["territorio"], s["tipo"]
        self.str_k_annunci, self.str_k_adr = s["k_annunci"], s["k_adr"]
        self.str_k_intero, self.str_k_multihost = s["k_intero"], s["k_multihost"]
        self.str_k_licenza, self.str_k_rating = s["k_licenza"], s["k_rating"]
        self._str_adr_nomi, self._str_adr_val, self._str_adr_slugs = s["adr_nomi"], s["adr_val"], s["adr_slugs"]
        self._str_zone_nomi, self._str_zone_val = s["zone_nomi"], s["zone_val"]
        self._str_room_nomi, self._str_room_val = s["room_nomi"], s["room_val"]
        self._str_rev_x, self._str_rev_y = s["rev_x"], s["rev_y"]

    @rx.event
    def set_str_territorio(self, nome: str):
        self.str_slug = STR_NAME2SLUG.get(nome, self.str_slug)
        self._load_str()

    @rx.event
    def set_region(self, name: str):
        self.region_code = NAME2CODE.get(name, self.region_code)
        self._load()

    @rx.var
    def presenze_fig(self) -> go.Figure:
        fig = go.Figure(go.Scatter(x=self.serie_mesi, y=self.serie_presenze, mode="lines",
                                   line=dict(color=ACCENT, width=2.6), fill="tozeroy",
                                   fillcolor="rgba(14,107,112,.12)",
                                   hovertemplate="%{x}<br>%{y:,.0f} presenze<extra></extra>"))
        fig.update_layout(height=300, margin=dict(l=8, r=8, t=8, b=8), paper_bgcolor="rgba(0,0,0,0)",
                          plot_bgcolor="#ffffff", font=dict(color=MUT, size=12), showlegend=False)
        fig.update_xaxes(showgrid=False, linecolor=LINE)
        fig.update_yaxes(gridcolor="#eef3f3", zeroline=False, title="presenze straniere (mese)")
        return fig

    @rx.var
    def mercati_fig(self) -> go.Figure:
        n = self.mercati_nomi[::-1]
        v = self.mercati_valori[::-1]
        fig = go.Figure(go.Bar(x=v, y=n, orientation="h", marker_color=ACCENT,
                               hovertemplate="<b>%{y}</b><br>%{x:,.0f} presenze<extra></extra>"))
        fig.update_layout(height=300, margin=dict(l=8, r=8, t=8, b=8), paper_bgcolor="rgba(0,0,0,0)",
                          plot_bgcolor="#ffffff", font=dict(color=MUT, size=12))
        fig.update_xaxes(gridcolor="#eef3f3", title="presenze (anno)")
        fig.update_yaxes(showgrid=False)
        return fig

    @rx.var
    def ranking_fig(self) -> go.Figure:
        rows = sorted(self.rank_regioni, key=lambda r: r["spesa_M"])
        names = [r["regione"] for r in rows]
        vals = [r["spesa_M"] for r in rows]
        colors = [ACCENT if r["code"] == self.region_code else MUTED_BAR for r in rows]
        fig = go.Figure(go.Bar(x=vals, y=names, orientation="h", marker_color=colors,
                               hovertemplate="<b>%{y}</b><br>%{x:,.0f} M€<extra></extra>"))
        fig.update_layout(height=620, margin=dict(l=8, r=8, t=8, b=8), paper_bgcolor="rgba(0,0,0,0)",
                          plot_bgcolor="#ffffff", font=dict(color=MUT, size=12), showlegend=False)
        fig.update_xaxes(gridcolor="#eef3f3", title="spesa turisti stranieri 2024 (M€)")
        fig.update_yaxes(showgrid=False)
        return fig

    @rx.var
    def bd_presenze_fig(self) -> go.Figure:
        # solo gli anni con dati di presenze (ISTAT parte dal 2019)
        xs, yt, ys = [], [], []
        for i, y in enumerate(self._bd_years):
            if self._bd_pres_tot[i] is not None or self._bd_pres_str[i] is not None:
                xs.append(y); yt.append(self._bd_pres_tot[i]); ys.append(self._bd_pres_str[i])
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=xs, y=yt, name="totale", mode="lines+markers",
                                 line=dict(color=ACCENT, width=2.4)))
        fig.add_trace(go.Scatter(x=xs, y=ys, name="straniere", mode="lines+markers",
                                 line=dict(color="#f59e0b", width=2.4)))
        fig.update_layout(height=320, margin=dict(l=8, r=8, t=8, b=8), paper_bgcolor="rgba(0,0,0,0)",
                          plot_bgcolor="#ffffff", font=dict(color=MUT, size=12),
                          legend=dict(orientation="h", y=1.14, x=0))
        fig.update_xaxes(showgrid=False, linecolor=LINE, dtick=1)
        fig.update_yaxes(gridcolor="#eef3f3", zeroline=False, title="presenze (anno)")
        return fig

    @rx.var
    def bd_spesa_fig(self) -> go.Figure:
        fig = go.Figure(go.Bar(x=self._bd_years, y=self._bd_spesa, marker_color=ACCENT,
                               hovertemplate="%{x}: %{y:,.0f} M€<extra></extra>"))
        fig.update_layout(height=320, margin=dict(l=8, r=8, t=8, b=8), paper_bgcolor="rgba(0,0,0,0)",
                          plot_bgcolor="#ffffff", font=dict(color=MUT, size=12), showlegend=False)
        fig.update_xaxes(showgrid=False, linecolor=LINE)
        fig.update_yaxes(gridcolor="#eef3f3", title="spesa straniera (M€)")
        return fig

    @rx.event
    def on_map_click(self, points: list[dict]):
        """Click su una regione della mappa → la seleziona (aggiorna KPI e altre pagine)."""
        if not points:
            return
        idx = points[0].get("pointIndex")
        if idx is None:
            idx = points[0].get("pointNumber")
        if idx is None or idx < 0 or idx >= len(self._map_codes):
            return
        code = self._map_codes[idx]
        if code:
            self.region_code = code
            self._load()

    @rx.var
    def map_fig(self) -> go.Figure:
        gj = self._map_geojson
        if not gj:
            return go.Figure()
        fig = go.Figure(go.Choropleth(
            geojson=gj, featureidkey="properties.reg_name",
            locations=self._map_names, z=self._map_z, customdata=self._map_codes,
            colorscale="Teal", marker_line_color="white", marker_line_width=0.6,
            colorbar=dict(title=dict(text="spesa straniera<br>2024 (M€)", side="right")),
            hovertemplate="<b>%{location}</b><br>spesa %{z:,.0f} M€<extra></extra>"))
        fig.update_geos(fitbounds="locations", visible=False, projection_type="mercator",
                        bgcolor="rgba(0,0,0,0)")
        fig.update_layout(height=760, margin=dict(l=0, r=0, t=0, b=0), autosize=True,
                          paper_bgcolor="rgba(0,0,0,0)", font=dict(color=MUT, size=12),
                          dragmode=False)
        return fig

    @rx.var
    def me_bar_fig(self) -> go.Figure:
        n = self._me_bar_nomi[::-1]
        v = self._me_bar_val[::-1]
        fig = go.Figure(go.Bar(x=v, y=n, orientation="h", marker_color=ACCENT,
                               hovertemplate="<b>%{y}</b><br>%{x:,.0f} presenze<extra></extra>"))
        fig.update_layout(height=430, margin=dict(l=8, r=8, t=8, b=8), paper_bgcolor="rgba(0,0,0,0)",
                          plot_bgcolor="#ffffff", font=dict(color=MUT, size=12), showlegend=False)
        fig.update_xaxes(gridcolor="#eef3f3", title="presenze straniere (anno)")
        fig.update_yaxes(showgrid=False)
        return fig

    @rx.var
    def me_lines_fig(self) -> go.Figure:
        palette = ["#0e6b70", "#f59e0b", "#7c3aed", "#059669", "#dc2626", "#2563eb"]
        fig = go.Figure()
        for i, s in enumerate(self._me_line_series):
            fig.add_trace(go.Scatter(x=self._me_line_years, y=s["values"], name=s["nome"],
                                     mode="lines+markers",
                                     line=dict(color=palette[i % len(palette)], width=2.2)))
        fig.update_layout(height=430, margin=dict(l=8, r=8, t=8, b=8), paper_bgcolor="rgba(0,0,0,0)",
                          plot_bgcolor="#ffffff", font=dict(color=MUT, size=12),
                          legend=dict(orientation="h", y=1.13, x=0))
        fig.update_xaxes(showgrid=False, linecolor=LINE)
        fig.update_yaxes(gridcolor="#eef3f3", zeroline=False, title="presenze (anno)")
        return fig

    @rx.var
    def str_adr_fig(self) -> go.Figure:
        colors = ["#f59e0b" if sl == self.str_slug else ACCENT for sl in self._str_adr_slugs]
        fig = go.Figure(go.Bar(x=self._str_adr_val, y=self._str_adr_nomi, orientation="h",
                               marker_color=colors,
                               hovertemplate="<b>%{y}</b><br>ADR mediano € %{x:,.0f}<extra></extra>"))
        fig.update_layout(height=430, margin=dict(l=8, r=8, t=8, b=8), paper_bgcolor="rgba(0,0,0,0)",
                          plot_bgcolor="#ffffff", font=dict(color=MUT, size=12), showlegend=False)
        fig.update_xaxes(gridcolor="#eef3f3", title="ADR mediano (€/notte)")
        fig.update_yaxes(showgrid=False)
        return fig

    @rx.var
    def str_rev_fig(self) -> go.Figure:
        fig = go.Figure(go.Scatter(x=self._str_rev_x, y=self._str_rev_y, mode="lines",
                                   line=dict(color=ACCENT, width=1.8), fill="tozeroy",
                                   fillcolor="rgba(14,107,112,.10)",
                                   hovertemplate="%{x}<br>%{y:,.0f} recensioni<extra></extra>"))
        fig.update_layout(height=430, margin=dict(l=8, r=8, t=8, b=8), paper_bgcolor="rgba(0,0,0,0)",
                          plot_bgcolor="#ffffff", font=dict(color=MUT, size=12), showlegend=False)
        fig.update_xaxes(showgrid=False, linecolor=LINE)
        fig.update_yaxes(gridcolor="#eef3f3", zeroline=False, title="recensioni / mese")
        return fig

    @rx.var
    def str_zone_fig(self) -> go.Figure:
        n = self._str_zone_nomi[::-1]
        v = self._str_zone_val[::-1]
        fig = go.Figure(go.Bar(x=v, y=n, orientation="h", marker_color=ACCENT,
                               hovertemplate="<b>%{y}</b><br>%{x:,.0f} annunci<extra></extra>"))
        fig.update_layout(height=430, margin=dict(l=8, r=8, t=8, b=8), paper_bgcolor="rgba(0,0,0,0)",
                          plot_bgcolor="#ffffff", font=dict(color=MUT, size=12), showlegend=False)
        fig.update_xaxes(gridcolor="#eef3f3", title="numero di annunci")
        fig.update_yaxes(showgrid=False)
        return fig

    @rx.var
    def str_room_fig(self) -> go.Figure:
        n = self._str_room_nomi
        v = self._str_room_val
        fig = go.Figure(go.Bar(x=v, y=n, orientation="h", marker_color="#16a34a",
                               hovertemplate="<b>%{y}</b><br>%{x:,.0f} annunci<extra></extra>"))
        fig.update_layout(height=300, margin=dict(l=8, r=8, t=8, b=8), paper_bgcolor="rgba(0,0,0,0)",
                          plot_bgcolor="#ffffff", font=dict(color=MUT, size=12), showlegend=False)
        fig.update_xaxes(gridcolor="#eef3f3", title="numero di annunci")
        fig.update_yaxes(showgrid=False)
        return fig

    @rx.var
    def sp_spesa_fig(self) -> go.Figure:
        fig = go.Figure(go.Bar(x=self._sp_years, y=self._sp_spesa, marker_color=ACCENT,
                               hovertemplate="%{x}: %{y:,.0f} M€<extra></extra>"))
        fig.update_layout(height=340, margin=dict(l=8, r=8, t=8, b=8), paper_bgcolor="rgba(0,0,0,0)",
                          plot_bgcolor="#ffffff", font=dict(color=MUT, size=12), showlegend=False)
        fig.update_xaxes(showgrid=False, linecolor=LINE)
        fig.update_yaxes(gridcolor="#eef3f3", title="spesa straniera (M€)")
        return fig

    @rx.var
    def sp_yield_fig(self) -> go.Figure:
        fig = go.Figure(go.Scatter(x=self._sp_years, y=self._sp_viagg_val, mode="lines+markers",
                                   line=dict(color="#f59e0b", width=2.4),
                                   hovertemplate="%{x}: € %{y:,.0f}/viaggiatore<extra></extra>"))
        fig.update_layout(height=340, margin=dict(l=8, r=8, t=8, b=8), paper_bgcolor="rgba(0,0,0,0)",
                          plot_bgcolor="#ffffff", font=dict(color=MUT, size=12), showlegend=False)
        fig.update_xaxes(showgrid=False, linecolor=LINE)
        fig.update_yaxes(gridcolor="#eef3f3", zeroline=False, title="spesa per viaggiatore (€)")
        return fig

    @rx.var
    def prov_bar_fig(self) -> go.Figure:
        n = self._prov_bar_nomi[::-1]
        v = self._prov_bar_val[::-1]
        fig = go.Figure(go.Bar(x=v, y=n, orientation="h", marker_color=ACCENT,
                               hovertemplate="<b>%{y}</b><br>%{x:,.0f} presenze (12 mesi)<extra></extra>"))
        fig.update_layout(height=430, margin=dict(l=8, r=8, t=8, b=8), paper_bgcolor="rgba(0,0,0,0)",
                          plot_bgcolor="#ffffff", font=dict(color=MUT, size=12), showlegend=False)
        fig.update_xaxes(gridcolor="#eef3f3", title="presenze (ultimi 12 mesi)")
        fig.update_yaxes(showgrid=False)
        return fig

    @rx.var
    def struttura_fig(self) -> go.Figure:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=self._st_x, y=self._st_alb, name="alberghiero", mode="lines",
                                 line=dict(color=ACCENT, width=2)))
        fig.add_trace(go.Scatter(x=self._st_x, y=self._st_ext, name="extra-alberghiero", mode="lines",
                                 line=dict(color="#f59e0b", width=2)))
        fig.update_layout(height=400, margin=dict(l=8, r=8, t=8, b=8), paper_bgcolor="rgba(0,0,0,0)",
                          plot_bgcolor="#ffffff", font=dict(color=MUT, size=12),
                          legend=dict(orientation="h", y=1.13, x=0))
        fig.update_xaxes(showgrid=False, linecolor=LINE)
        fig.update_yaxes(gridcolor="#eef3f3", zeroline=False, title="presenze / mese")
        return fig

    @rx.var
    def ie_lines_fig(self) -> go.Figure:
        palette = ["#0e6b70", "#f59e0b", "#7c3aed", "#059669", "#dc2626", "#2563eb"]
        fig = go.Figure()
        for i, s in enumerate(self._ie_series):
            fig.add_trace(go.Scatter(x=s["dates"], y=s["values"], name=s["nome"], mode="lines",
                                     line=dict(color=palette[i % len(palette)], width=1.8)))
        fig.update_layout(height=430, margin=dict(l=8, r=8, t=8, b=8), paper_bgcolor="rgba(0,0,0,0)",
                          plot_bgcolor="#ffffff", font=dict(color=MUT, size=12),
                          legend=dict(orientation="h", y=1.13, x=0))
        fig.update_xaxes(showgrid=False, linecolor=LINE)
        fig.update_yaxes(gridcolor="#eef3f3", zeroline=False, title="interesse di ricerca (0-100)")
        return fig

    @rx.var
    def forecast_fig(self) -> go.Figure:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=self._fc_hist_x, y=self._fc_hist_y, name="storico", mode="lines",
                                 line=dict(color=MUT, width=1.8)))
        if self._fc_x:
            fig.add_trace(go.Scatter(x=self._fc_x, y=self._fc_hi, mode="lines", line=dict(width=0),
                                     showlegend=False, hoverinfo="skip"))
            fig.add_trace(go.Scatter(x=self._fc_x, y=self._fc_lo, name="intervallo 80%", mode="lines",
                                     line=dict(width=0), fill="tonexty", fillcolor="rgba(14,107,112,.15)",
                                     hoverinfo="skip"))
            fig.add_trace(go.Scatter(x=self._fc_x, y=self._fc_mean, name="previsione",
                                     mode="lines+markers", line=dict(color=ACCENT, width=2.6)))
        fig.update_layout(height=430, margin=dict(l=8, r=8, t=8, b=8), paper_bgcolor="rgba(0,0,0,0)",
                          plot_bgcolor="#ffffff", font=dict(color=MUT, size=12),
                          legend=dict(orientation="h", y=1.13, x=0))
        fig.update_xaxes(showgrid=False, linecolor=LINE)
        fig.update_yaxes(gridcolor="#eef3f3", zeroline=False, title="presenze straniere / mese")
        return fig

    @rx.var
    def cf_scatter_fig(self) -> go.Figure:
        colors = ["#f59e0b" if c == self.region_code else ACCENT for c in self._cf_codes]
        mx = max(self._cf_letti) if self._cf_letti else 1.0
        sizes = [10 + 34 * ((l / mx) ** 0.5) for l in self._cf_letti]
        fig = go.Figure(go.Scatter(
            x=self._cf_spesa, y=self._cf_occ, mode="markers+text", text=self._cf_names,
            textposition="top center", textfont=dict(size=9, color=MUT), customdata=self._cf_letti,
            marker=dict(size=sizes, color=colors, opacity=0.85, line=dict(width=1, color="white")),
            hovertemplate="<b>%{text}</b><br>spesa %{x:,.0f} M€<br>occupazione %{y:.1f}%"
                          "<br>posti letto %{customdata:,.0f}<extra></extra>"))
        fig.update_layout(height=470, margin=dict(l=8, r=8, t=8, b=8), paper_bgcolor="rgba(0,0,0,0)",
                          plot_bgcolor="#ffffff", font=dict(color=MUT, size=12), showlegend=False)
        fig.update_xaxes(gridcolor="#eef3f3", title="spesa straniera (M€)")
        fig.update_yaxes(gridcolor="#eef3f3", title="occupazione media (%)")
        return fig


# ════════════════════════════════════════════════════════════════════════════
# componenti condivisi (design-system)
# ════════════════════════════════════════════════════════════════════════════
def logo(height: str = "40px") -> rx.Component:
    return rx.image(src="/tdh_logo.svg", height=height, width="auto", alt="Turism Data Hub")


def kpi(label: str, value, hint) -> rx.Component:
    return rx.box(
        rx.text(label, font_size="0.72rem", font_weight="600", color=MUT,
                text_transform="uppercase", letter_spacing="0.05em"),
        rx.text(value, font_size="1.7rem", font_weight="700", color=INK, margin_top="6px"),
        rx.text(hint, font_size="0.75rem", color=FAINT, margin_top="3px"),
        background=PANEL, border=f"1px solid {LINE}", border_radius="14px", padding="16px 18px")


def panel(title: str, body: rx.Component) -> rx.Component:
    return rx.box(
        rx.text(title, font_size="0.95rem", font_weight="600", color=INK, margin_bottom="10px"),
        body,
        background=PANEL, border=f"1px solid {LINE}", border_radius="16px", padding="18px 20px",
        width="100%")


def nav_group(label: str) -> rx.Component:
    return rx.text(label, font_size="0.64rem", letter_spacing="0.14em", color=FAINT,
                   font_weight="600", margin="16px 10px 4px", style={"text-transform": "uppercase"})


def nav_item(icon: str, label: str, active: bool = False, href: str | None = None) -> rx.Component:
    row = rx.hstack(
        rx.icon(icon, size=18, color=(ACCENT if active else MUT)),
        rx.text(label, font_size="0.87rem", font_weight=("600" if active else "500"),
                color=(ACCENT_INK if active else MUT)),
        spacing="3", align="center", width="100%", padding="8px 10px", border_radius="8px",
        background=("rgba(14,107,112,0.10)" if active else "transparent"),
        border_left=(f"3px solid {ACCENT}" if active else "3px solid transparent"),
        cursor=("pointer" if href else "default"),
        opacity=("1" if (href or active) else "0.55"),
        _hover=({"background": "#eef3f3"} if href else {}))
    if href:
        return rx.link(row, href=href, width="100%", text_decoration="none",
                       style={"text-decoration": "none"})
    return row


def sidebar(active: str = "regione") -> rx.Component:
    return rx.vstack(
        rx.box(logo(), padding_bottom="16px", margin_bottom="6px",
               border_bottom=f"1px solid {LINE}", width="100%"),
        nav_group("Panoramica"),
        nav_item("house", "Home", active=(active == "home"), href="/"),
        nav_item("layout-dashboard", "Regione", active=(active == "regione"), href="/regione"),
        nav_item("map", "Italia · mappa", active=(active == "mappa"), href="/mappa"),
        nav_item("globe", "Mercati d'origine", active=(active == "mercati"), href="/mercati"),
        nav_item("git-compare", "Confronto regioni", active=(active == "confronto"), href="/confronto"),
        nav_group("Cosa è successo"),
        nav_item("map-pin", "Per provincia", active=(active == "province"), href="/per-provincia"),
        nav_item("building-2", "Per struttura", active=(active == "struttura"), href="/per-struttura"),
        nav_item("bed-double", "Affitti brevi", active=(active == "str"), href="/affitti-brevi"),
        nav_item("database", "Base dati regionale", active=(active == "basedati"), href="/base-dati"),
        nav_item("banknote", "Spesa turistica", active=(active == "spesa"), href="/spesa"),
        nav_group("Cosa fare"),
        nav_item("trophy", "Ranking regioni", active=(active == "ranking"), href="/ranking"),
        nav_item("target", "Azioni & budget", active=(active == "azioni"), href="/azioni"),
        nav_item("trending-up", "Interesse online", active=(active == "interesse"), href="/interesse-online"),
        nav_item("activity", "Forecast presenze", active=(active == "forecast"), href="/forecast"),
        nav_group("Sistema"),
        nav_item("layers", "Architettura", active=(active == "architettura"), href="/architettura"),
        nav_item("database", "Gestione dati", active=(active == "gestione"), href="/gestione-dati"),
        nav_item("messages-square", "Assistente"),
        spacing="1", align_items="start", width="264px", min_width="264px",
        height="100vh", position="sticky", top="0px", overflow_y="auto",
        background=PANEL, border_right=f"1px solid {LINE}", padding="20px 14px")


def topbar(breadcrumb: str) -> rx.Component:
    right = [rx.select(NOMI, value=State.region_name, on_change=State.set_region, width="220px")]
    if AUTH_REQUIRED:
        right.append(rx.button("Esci", on_click=AuthState.logout, variant="soft",
                               color_scheme="gray", size="1"))
    return rx.box(
        rx.hstack(
            rx.text(breadcrumb, font_size="0.8rem", color=MUT),
            rx.spacer(),
            *right,
            align="center", spacing="3", width="100%"),
        border_bottom=f"1px solid {LINE}", padding_bottom="12px", width="100%")


def error_banner() -> rx.Component:
    return rx.cond(
        State.boot_error != "",
        rx.box(
            rx.text("⚠️ Diagnostica caricamento dati", font_weight="700", color="#b91c1c",
                    margin_bottom="6px"),
            rx.text(State.boot_error, font_family="monospace", font_size="0.72rem", color="#7f1d1d",
                    white_space="pre-wrap"),
            background="#fef2f2", border="1px solid #fecaca", border_radius="12px",
            padding="14px 16px", width="100%"),
        rx.box())


def page_shell(active: str, breadcrumb: str, *content) -> rx.Component:
    shell = rx.hstack(
        sidebar(active),
        rx.box(
            rx.vstack(topbar(breadcrumb), error_banner(), *content,
                      spacing="4", width="100%", max_width="1180px"),
            flex="1", min_height="100vh", background=BG, padding="24px 34px",
            display="flex", justify_content="center"),
        spacing="0", align="start", width="100%")
    return rx.cond(AuthState.is_authed, shell, login_view())


# ════════════════════════════════════════════════════════════════════════════
# pagina: Regione ("/")
# ════════════════════════════════════════════════════════════════════════════
def mercati_table() -> rx.Component:
    return rx.table.root(
        rx.table.header(rx.table.row(
            rx.table.column_header_cell("Mercato estero"),
            rx.table.column_header_cell("Presenze (anno)"),
            rx.table.column_header_cell("Quota sui top 5"))),
        rx.table.body(rx.foreach(State.mercati_rows, lambda r: rx.table.row(
            rx.table.cell(r["nome"]),
            rx.table.cell(r["presenze"]),
            rx.table.cell(rx.badge(r["quota"], color_scheme="teal", variant="soft", radius="full"))))),
        variant="surface", size="2", width="100%")


def index() -> rx.Component:
    return page_shell(
        "regione", "Panoramica  ›  Regione",
        rx.box(
            rx.heading(State.titolo, size="7", color=INK, weight="bold"),
            rx.text("Presenze, capacità ricettiva e mercati esteri della regione. Fonti: ISTAT · Banca d'Italia.",
                    color=MUT, font_size="0.9rem", margin_top="4px"),
            width="100%"),
        rx.box(
            kpi("Presenze straniere", State.kpi_presenze, State.kpi_presenze_periodo),
            kpi("Posti letto", State.kpi_letti, State.kpi_letti_anno),
            kpi("Spesa straniera", State.kpi_spesa, State.kpi_spesa_rank),
            kpi("Mercati esteri", State.kpi_mercati, State.kpi_mercati_anno),
            display="grid", grid_template_columns="repeat(4, 1fr)", gap="14px", width="100%"),
        rx.box(
            panel("Presenze straniere mensili", rx.plotly(data=State.presenze_fig, width="100%")),
            panel("Top mercati esteri", rx.plotly(data=State.mercati_fig, width="100%")),
            display="grid", grid_template_columns="3fr 2fr", gap="18px", width="100%"),
        panel("Top 5 mercati esteri — dettaglio", mercati_table()),
        rx.text("Reflex · DATI REALI (ISTAT · Banca d'Italia) · design «Istituzionale»",
                color=FAINT, font_size="0.75rem"))


# ════════════════════════════════════════════════════════════════════════════
# pagina: Ranking regioni ("/ranking")
# ════════════════════════════════════════════════════════════════════════════
def ranking_page() -> rx.Component:
    return page_shell(
        "ranking", "Cosa fare  ›  Ranking regioni",
        rx.box(
            rx.heading("Spesa turistica straniera per regione — 2024", size="7", color=INK, weight="bold"),
            rx.text("Classifica di tutte le regioni italiane per spesa dei turisti stranieri. Barra "
                    "evidenziata = regione selezionata (cambiala dal menu in alto a destra). Fonte: Banca d'Italia.",
                    color=MUT, font_size="0.9rem", margin_top="4px"),
            width="100%"),
        rx.box(
            kpi("Totale Italia", State.italia_spesa, "spesa straniera 2024"),
            kpi("Regione selezionata", State.kpi_spesa, State.region_name),
            kpi("Posizione", State.kpi_spesa_rank, "nella classifica"),
            display="grid", grid_template_columns="repeat(3, 1fr)", gap="14px", width="100%"),
        panel("Classifica regioni per spesa straniera", rx.plotly(data=State.ranking_fig, width="100%")),
        rx.text("Reflex · DATI REALI (Banca d'Italia) · design «Istituzionale»",
                color=FAINT, font_size="0.75rem"))


# ════════════════════════════════════════════════════════════════════════════
# pagina: Base dati regionale ("/base-dati")
# ════════════════════════════════════════════════════════════════════════════
def base_dati_table() -> rx.Component:
    return rx.box(
        rx.table.root(
            rx.table.header(rx.table.row(
                rx.table.column_header_cell("Anno"),
                rx.table.column_header_cell("Presenze totali"),
                rx.table.column_header_cell("Presenze straniere"),
                rx.table.column_header_cell("Quota str."),
                rx.table.column_header_cell("Spesa straniera"),
                rx.table.column_header_cell("Occupazione"))),
            rx.table.body(rx.foreach(State.bd_rows, lambda r: rx.table.row(
                rx.table.cell(r["anno"]),
                rx.table.cell(r["pres_tot"]),
                rx.table.cell(r["pres_str"]),
                rx.table.cell(r["quota"]),
                rx.table.cell(r["spesa"]),
                rx.table.cell(r["occ"])))),
            variant="surface", size="1", width="100%"),
        max_height="360px", overflow_y="auto", width="100%")


def base_dati_page() -> rx.Component:
    return page_shell(
        "basedati", "Cosa è successo  ›  Base dati regionale",
        rx.box(
            rx.heading(State.region_name + " — base dati pluriennale", size="7", color=INK, weight="bold"),
            rx.text("Quadro annuale che unisce ISTAT (presenze, capacità) e Banca d'Italia "
                    "(spesa, notti, viaggiatori) con le derivate (quota stranieri, spesa/turista, "
                    "occupazione). Celle «—» = anno senza quel dato.",
                    color=MUT, font_size="0.9rem", margin_top="4px"),
            width="100%"),
        rx.box(
            kpi("Spesa / viaggiatore", State.bd_k_sviagg, State.bd_k_sviagg_a),
            kpi("Spesa / notte", State.bd_k_snotte, State.bd_k_snotte_a),
            kpi("Occupazione", State.bd_k_occ, State.bd_k_occ_a),
            kpi("Quota stranieri", State.bd_k_quota, State.bd_k_quota_a),
            display="grid", grid_template_columns="repeat(4, 1fr)", gap="14px", width="100%"),
        rx.box(
            panel("Presenze annuali (totale vs straniere)", rx.plotly(data=State.bd_presenze_fig, width="100%")),
            panel("Spesa straniera annuale", rx.plotly(data=State.bd_spesa_fig, width="100%")),
            display="grid", grid_template_columns="repeat(2, 1fr)", gap="18px", width="100%"),
        panel("Serie annuale — dettaglio", base_dati_table()),
        rx.text("Reflex · DATI REALI (ISTAT · Banca d'Italia) · design «Istituzionale»",
                color=FAINT, font_size="0.75rem"))


# ════════════════════════════════════════════════════════════════════════════
# pagina: Italia · mappa ("/mappa")
# ════════════════════════════════════════════════════════════════════════════
def map_page() -> rx.Component:
    return page_shell(
        "mappa", "Panoramica  ›  Italia · mappa",
        rx.box(
            rx.heading("Italia — spesa turistica straniera per regione (2024)", size="7", color=INK, weight="bold"),
            rx.text("Mappa colorata per spesa dei turisti stranieri (Banca d'Italia). "
                    "Clicca una regione per selezionarla: KPI e altre pagine si aggiornano. "
                    "La regione selezionata è a piena intensità, le altre attenuate.",
                    color=MUT, font_size="0.9rem", margin_top="4px"),
            width="100%"),
        rx.box(
            kpi("Totale Italia", State.italia_spesa, "spesa straniera 2024"),
            kpi("Regione selezionata", State.kpi_spesa, State.region_name),
            kpi("Posizione", State.kpi_spesa_rank, "nella classifica"),
            display="grid", grid_template_columns="repeat(3, 1fr)", gap="14px", width="100%"),
        rx.box(
            panel("Mappa della spesa straniera",
                  rx.plotly(data=State.map_fig, on_click=State.on_map_click,
                            width="100%", height="740px")),
            width="100%", max_width="780px", margin="0 auto"),
        rx.text("Reflex · DATI REALI (Banca d'Italia) · clic per selezionare · design «Istituzionale»",
                color=FAINT, font_size="0.75rem"))


# ════════════════════════════════════════════════════════════════════════════
# pagina: Mercati d'origine ("/mercati")
# ════════════════════════════════════════════════════════════════════════════
def mercati_dettaglio_table() -> rx.Component:
    return rx.box(
        rx.table.root(
            rx.table.header(rx.table.row(
                rx.table.column_header_cell("Mercato estero"),
                rx.table.column_header_cell("Presenze (anno)"),
                rx.table.column_header_cell("Quota su tutti i mercati"))),
            rx.table.body(rx.foreach(State.me_rows, lambda r: rx.table.row(
                rx.table.cell(r["nome"]),
                rx.table.cell(r["valore"]),
                rx.table.cell(rx.badge(r["quota"], color_scheme="teal", variant="soft", radius="full"))))),
            variant="surface", size="1", width="100%"),
        max_height="360px", overflow_y="auto", width="100%")


def mercati_page() -> rx.Component:
    return page_shell(
        "mercati", "Panoramica  ›  Mercati d'origine",
        rx.box(
            rx.heading(State.region_name + " — mercati esteri d'origine", size="7", color=INK, weight="bold"),
            rx.text("Da quali paesi arrivano i turisti stranieri (presenze, ISTAT). Classifica "
                    "dell'ultimo anno e andamento storico dei primi 5 mercati (visibile il crollo 2020).",
                    color=MUT, font_size="0.9rem", margin_top="4px"),
            width="100%"),
        rx.box(
            kpi("Mercati esteri", State.me_n, "paesi di origine"),
            kpi("Primo mercato", State.me_primo, State.me_primo_val + " presenze"),
            kpi("Anno", State.me_anno, "ultimo disponibile"),
            display="grid", grid_template_columns="repeat(3, 1fr)", gap="14px", width="100%"),
        rx.box(
            panel("Top mercati (ultimo anno)", rx.plotly(data=State.me_bar_fig, width="100%")),
            panel("Andamento storico — primi 5 mercati", rx.plotly(data=State.me_lines_fig, width="100%")),
            display="grid", grid_template_columns="repeat(2, 1fr)", gap="18px", width="100%"),
        panel("Classifica mercati — dettaglio", mercati_dettaglio_table()),
        rx.text("Reflex · DATI REALI (ISTAT esteri per paese) · design «Istituzionale»",
                color=FAINT, font_size="0.75rem"))


# ════════════════════════════════════════════════════════════════════════════
# pagina: Affitti brevi / STR ("/affitti-brevi")
# ════════════════════════════════════════════════════════════════════════════
def affitti_page() -> rx.Component:
    return page_shell(
        "str", "Cosa è successo  ›  Affitti brevi (STR)",
        rx.box(
            rx.hstack(
                rx.vstack(
                    rx.heading("Affitti brevi — " + State.str_terr_nome, size="7", color=INK, weight="bold"),
                    rx.text("Struttura del mercato Airbnb (fonte: Inside Airbnb): annunci, prezzi, "
                            "operatori, licenze e domanda nel tempo. Copertura: 7 città + 3 regioni — "
                            "vista NAZIONALE, indipendente dalla regione selezionata in alto.",
                            color=MUT, font_size="0.9rem", margin_top="4px"),
                    align_items="start", spacing="1"),
                rx.spacer(),
                rx.vstack(
                    rx.text("Territorio", font_size="0.7rem", color=MUT, font_weight="600"),
                    rx.select(STR_NOMI, value=State.str_terr_nome, on_change=State.set_str_territorio,
                              width="220px"),
                    spacing="1", align_items="end"),
                align="start", width="100%"),
            width="100%"),
        rx.box(
            kpi("Annunci attivi", State.str_k_annunci, "snapshot Inside Airbnb"),
            kpi("ADR mediano", State.str_k_adr, "€/notte"),
            kpi("Soddisfazione ★", State.str_k_rating, "rating medio Airbnb (su 5)"),
            kpi("Operatori professionali", State.str_k_multihost, "host con più annunci"),
            kpi("Con licenza / CIR", State.str_k_licenza, "% degli annunci"),
            display="grid", grid_template_columns="repeat(5, 1fr)", gap="12px", width="100%"),
        rx.box(
            panel("ADR mediano — confronto territori", rx.plotly(data=State.str_adr_fig, width="100%")),
            panel("Recensioni / mese (proxy della domanda)", rx.plotly(data=State.str_rev_fig, width="100%")),
            display="grid", grid_template_columns="repeat(2, 1fr)", gap="18px", width="100%"),
        rx.box(
            panel("Zone / quartieri per numero di annunci", rx.plotly(data=State.str_zone_fig, width="100%")),
            panel("Tipologia di alloggio", rx.plotly(data=State.str_room_fig, width="100%")),
            display="grid", grid_template_columns="repeat(2, 1fr)", gap="18px", width="100%"),
        rx.text("Reflex · DATI REALI (Inside Airbnb) · «Soddisfazione» = rating medio, primo segnale "
                "di sentiment (Tier 0) · design «Istituzionale»",
                color=FAINT, font_size="0.75rem"))


def spesa_table() -> rx.Component:
    return rx.box(
        rx.table.root(
            rx.table.header(rx.table.row(
                rx.table.column_header_cell("Anno"),
                rx.table.column_header_cell("Spesa"),
                rx.table.column_header_cell("Viaggiatori"),
                rx.table.column_header_cell("Pernottamenti"),
                rx.table.column_header_cell("Spesa/viaggiatore"),
                rx.table.column_header_cell("Permanenza (notti)"))),
            rx.table.body(rx.foreach(State.sp_rows, lambda r: rx.table.row(
                rx.table.cell(r["anno"]),
                rx.table.cell(r["spesa"]),
                rx.table.cell(r["viaggiatori"]),
                rx.table.cell(r["notti"]),
                rx.table.cell(r["sp_viagg"]),
                rx.table.cell(r["permanenza"])))),
            variant="surface", size="1", width="100%"),
        max_height="340px", overflow_y="auto", width="100%")


# ════════════════════════════════════════════════════════════════════════════
# pagina: Spesa turistica ("/spesa")
# ════════════════════════════════════════════════════════════════════════════
def spesa_page() -> rx.Component:
    return page_shell(
        "spesa", "Cosa è successo  ›  Spesa turistica",
        rx.box(
            rx.heading(State.region_name + " — spesa turistica straniera", size="7", color=INK, weight="bold"),
            rx.text("Quanto spendono i turisti stranieri (Banca d'Italia) e quanto vale ogni visitatore: "
                    "spesa totale, spesa per viaggiatore/notte e permanenza media. Solo anni completi.",
                    color=MUT, font_size="0.9rem", margin_top="4px"),
            width="100%"),
        rx.box(
            kpi("Spesa straniera", State.sp_k_spesa, "anno " + State.sp_k_anno),
            kpi("Spesa / viaggiatore", State.sp_k_viagg, "€ per viaggiatore"),
            kpi("Spesa / notte", State.sp_k_notte, "€ per pernottamento"),
            kpi("Permanenza media", State.sp_k_permanenza, "notti per viaggiatore"),
            display="grid", grid_template_columns="repeat(4, 1fr)", gap="14px", width="100%"),
        rx.box(
            panel("Spesa straniera annuale", rx.plotly(data=State.sp_spesa_fig, width="100%")),
            panel("Spesa per viaggiatore (yield)", rx.plotly(data=State.sp_yield_fig, width="100%")),
            display="grid", grid_template_columns="repeat(2, 1fr)", gap="18px", width="100%"),
        panel("Serie annuale — dettaglio", spesa_table()),
        rx.text("Reflex · DATI REALI (Banca d'Italia) · design «Istituzionale»",
                color=FAINT, font_size="0.75rem"))


# ════════════════════════════════════════════════════════════════════════════
# pagina: Per provincia ("/per-provincia")
# ════════════════════════════════════════════════════════════════════════════
def _note(txt) -> rx.Component:
    return rx.box(rx.text(txt, color="#b45309", font_size="0.85rem"),
                  background="#fff7ed", border="1px solid #fed7aa", border_radius="10px",
                  padding="10px 14px", width="100%")


def province_table() -> rx.Component:
    return rx.box(
        rx.table.root(
            rx.table.header(rx.table.row(
                rx.table.column_header_cell("Provincia"),
                rx.table.column_header_cell("Presenze (12 mesi)"),
                rx.table.column_header_cell("Peso %"),
                rx.table.column_header_cell("Stranieri"),
                rx.table.column_header_cell("Quota str."))),
            rx.table.body(rx.foreach(State.prov_rows, lambda r: rx.table.row(
                rx.table.cell(r["provincia"]),
                rx.table.cell(r["presenze"]),
                rx.table.cell(r["peso"]),
                rx.table.cell(r["stranieri"]),
                rx.table.cell(r["quota"])))),
            variant="surface", size="1", width="100%"),
        max_height="340px", overflow_y="auto", width="100%")


def province_page() -> rx.Component:
    body_dati = rx.vstack(
        rx.box(
            kpi("Province con dati", State.prov_n, "presenti in cache"),
            kpi("Provincia n.1", State.prov_top_nome,
                State.prov_top_presenze + " presenze · " + State.prov_top_peso),
            kpi("Concentrazione top 3", State.prov_share3, "del totale regionale"),
            display="grid", grid_template_columns="repeat(3, 1fr)", gap="14px", width="100%"),
        rx.cond(State.prov_has_note, _note(State.prov_note), rx.box()),
        panel("Presenze per provincia (ultimi 12 mesi)", rx.plotly(data=State.prov_bar_fig, width="100%")),
        panel("Dettaglio per provincia", province_table()),
        spacing="4", width="100%")
    return page_shell(
        "province", "Cosa è successo  ›  Per provincia",
        rx.box(
            rx.heading(State.region_name + " — presenze per provincia", size="7", color=INK, weight="bold"),
            rx.text("Dove si concentra il turismo regionale: presenze degli ultimi 12 mesi per "
                    "provincia (ISTAT), con quota di stranieri.", color=MUT, font_size="0.9rem", margin_top="4px"),
            width="100%"),
        rx.cond(
            State.prov_has_region,
            rx.cond(State.prov_has_data, body_dati,
                    _note("Nessun dato provinciale in cache per questa regione. " + State.prov_note)),
            _note("Le province sono un concetto regionale: scegli una regione (non «Italia») dal menu in alto a destra.")),
        rx.text("Reflex · DATI REALI (ISTAT) · solo province già in cache · design «Istituzionale»",
                color=FAINT, font_size="0.75rem"))


# ════════════════════════════════════════════════════════════════════════════
# pagina: Azioni & budget ("/azioni") — l'allocatore
# ════════════════════════════════════════════════════════════════════════════
def azione_card(r: rx.Var) -> rx.Component:
    return rx.box(
        rx.hstack(
            rx.badge("Priorità ", r["priorita"],
                     color_scheme=rx.match(r["priorita"], ("Alta", "red"), ("Media", "amber"), "gray"),
                     variant="soft", radius="full"),
            rx.badge(r["reco"],
                     color_scheme=rx.match(r["cat"], ("Aumentare", "grass"), ("Ridurre", "red"),
                                           ("Monitorare", "amber"), "gray"),
                     variant="soft", radius="full"),
            rx.text(r["market"], font_weight="700", font_size="1.02rem", color=INK),
            rx.spacer(),
            rx.text("score ", r["score"], font_size="0.8rem", color=FAINT),
            align="center", width="100%", spacing="3"),
        rx.text("forza anticipatrice ", r["forza"], "  ·  momentum ricerca ", r["momentum"],
                "  ·  valore ", r["valore"], "/visitatore  ·  picco ricerca ", r["picco"],
                color=MUT, font_size="0.8rem", margin_top="6px"),
        background=PANEL, border=f"1px solid {LINE}", border_radius="12px", padding="14px 16px", width="100%")


def azioni_page() -> rx.Component:
    return page_shell(
        "azioni", "Cosa fare  ›  Azioni & budget",
        rx.box(
            rx.heading("Azioni raccomandate — " + State.az_region, size="7", color=INK, weight="bold"),
            rx.text("Dove e quando agire: i mercati esteri ordinati per opportunità = forza "
                    "anticipatrice × momentum di ricerca × peso economico × fattibilità. "
                    "Stime d'opportunità, non garanzie di ritorno.", color=MUT, font_size="0.9rem",
                    margin_top="4px"),
            width="100%"),
        rx.cond(State.az_has_national,
                _note("Vista «Italia»: il motore per-regione mostra " + State.az_region
                      + " come esempio. Scegli una regione dal menu in alto per le sue azioni."),
                rx.box()),
        rx.cond(State.az_error != "", _note("Motore non disponibile: " + State.az_error), rx.box()),
        rx.box(
            kpi("Priorità alta", State.az_n_alta, "mercati su cui agire ora"),
            kpi("Mercati da aumentare", State.az_n_aumentare, "segnale + momentum positivi"),
            kpi("Picco ricerca n.1", State.az_picco_top, "quando presidiare la domanda"),
            display="grid", grid_template_columns="repeat(3, 1fr)", gap="14px", width="100%"),
        rx.vstack(rx.foreach(State.azioni_rows, azione_card), spacing="3", width="100%"),
        rx.text("Reflex · MOTORE REALE (ISTAT · Google Trends · Banca d'Italia) · "
                "stime d'opportunità · design «Istituzionale»", color=FAINT, font_size="0.75rem"))


# ════════════════════════════════════════════════════════════════════════════
# pagina: Per struttura ("/per-struttura")
# ════════════════════════════════════════════════════════════════════════════
def struttura_page() -> rx.Component:
    dati = rx.vstack(
        rx.box(
            kpi("Alberghiero (12 mesi)", State.st_alberghiero, State.st_quota_alb + " del totale"),
            kpi("Extra-alberghiero (12 mesi)", State.st_extra, State.st_quota_ext + " del totale"),
            kpi("Quota alberghiero", State.st_quota_alb, "sul totale presenze"),
            display="grid", grid_template_columns="repeat(3, 1fr)", gap="14px", width="100%"),
        panel("Presenze mensili per tipo di struttura", rx.plotly(data=State.struttura_fig, width="100%")),
        spacing="4", width="100%")
    return page_shell(
        "struttura", "Cosa è successo  ›  Per struttura",
        rx.box(
            rx.heading(State.region_name + " — presenze per tipo di struttura", size="7", color=INK, weight="bold"),
            rx.text("Alberghiero (hotel e strutture assimilate) vs extra-alberghiero (B&B, agriturismi, "
                    "case vacanza, campeggi…). ISTAT: ultimi 12 mesi e andamento mensile.",
                    color=MUT, font_size="0.9rem", margin_top="4px"),
            width="100%"),
        rx.cond(State.st_has_data, dati,
                _note("Dati per tipo di struttura non ancora in cache per questa regione (prefetch in "
                      "corso — ricarica tra poco). Disponibili subito per Abruzzo e Italia.")),
        rx.text("Reflex · DATI REALI (ISTAT) · alberghiero vs extra · design «Istituzionale»",
                color=FAINT, font_size="0.75rem"))


# ════════════════════════════════════════════════════════════════════════════
# pagina: Architettura ("/architettura") — contenuto statico di prodotto
# ════════════════════════════════════════════════════════════════════════════
def _arch_level(nome: str, desc: str) -> rx.Component:
    return rx.box(
        rx.text(nome, font_weight="700", color=ACCENT_INK, font_size="0.92rem"),
        rx.text(desc, color=MUT, font_size="0.84rem", margin_top="3px"),
        background=PANEL, border=f"1px solid {LINE}", border_radius="12px", padding="12px 16px",
        width="100%")


def _sorgenti_table() -> rx.Component:
    return rx.box(
        rx.table.root(
            rx.table.header(rx.table.row(
                rx.table.column_header_cell("Sorgente"),
                rx.table.column_header_cell("Tipo"),
                rx.table.column_header_cell("Frequenza"),
                rx.table.column_header_cell("Stato"))),
            rx.table.body(*[rx.table.row(
                rx.table.cell(rx.text(s["Sorgente"], font_weight="600", color=INK)),
                rx.table.cell(s["Tipo"]),
                rx.table.cell(s["Frequenza"]),
                rx.table.cell(s["Stato"])) for s in ARCH["sorgenti"]]),
            variant="surface", size="1", width="100%"),
        width="100%")


def architettura_page() -> rx.Component:
    return page_shell(
        "architettura", "Sistema  ›  Architettura",
        rx.box(
            rx.heading("Architettura & sorgenti — la visione del TDH", size="7", color=INK, weight="bold"),
            rx.text("Come è pensato il Turism Data Hub: dai dati grezzi ai servizi, il motore "
                    "statistico, la roadmap e i principi guida.", color=MUT, font_size="0.9rem",
                    margin_top="4px"),
            width="100%"),
        panel("Architettura a 5 livelli",
              rx.vstack(*[_arch_level(n, d) for n, d in ARCH["livelli"]], spacing="2", width="100%")),
        panel("Sorgenti dati",
              rx.vstack(_sorgenti_table(),
                        rx.text("🟢 Attiva (già nel motore) · 🟡 Pianificata · ⚪ Da valutare",
                                color=FAINT, font_size="0.75rem"),
                        spacing="2", width="100%")),
        panel("Il motore statistico",
              rx.vstack(*[rx.markdown(m) for m in ARCH["motore_statistico"]], spacing="0", width="100%")),
        rx.box(
            panel("Roadmap", rx.vstack(*[rx.markdown(r) for r in ARCH["roadmap"]], spacing="0", width="100%")),
            panel("Principi guida", rx.vstack(*[rx.markdown(p) for p in ARCH["principi"]], spacing="0", width="100%")),
            display="grid", grid_template_columns="repeat(2, 1fr)", gap="18px", width="100%"),
        rx.text("Turism Data Hub · visione di prodotto · design «Istituzionale»",
                color=FAINT, font_size="0.75rem"))


# ════════════════════════════════════════════════════════════════════════════
# pagina: Gestione dati / inventario sorgenti ("/gestione-dati")
# ════════════════════════════════════════════════════════════════════════════
def gestione_table() -> rx.Component:
    return rx.box(
        rx.table.root(
            rx.table.header(rx.table.row(
                rx.table.column_header_cell(""),
                rx.table.column_header_cell("Sorgente"),
                rx.table.column_header_cell("Ente"),
                rx.table.column_header_cell("Frequenza"),
                rx.table.column_header_cell("Copertura"),
                rx.table.column_header_cell("Ultimo dato"),
                rx.table.column_header_cell("Aggiornabilità"))),
            rx.table.body(rx.foreach(State.ges_rows, lambda r: rx.table.row(
                rx.table.cell(r["stato"]),
                rx.table.cell(rx.text(r["nome"], font_weight="600", color=INK)),
                rx.table.cell(r["ente"]),
                rx.table.cell(r["freq"]),
                rx.table.cell(r["livello"]),
                rx.table.cell(r["ultimo"]),
                rx.table.cell(rx.badge(r["agg"],
                              color_scheme=rx.match(r["agg"], ("live", "grass"), "gray"),
                              variant="soft", radius="full"))))),
            variant="surface", size="1", width="100%"),
        width="100%")


def gestione_page() -> rx.Component:
    return page_shell(
        "gestione", "Sistema  ›  Gestione dati",
        rx.box(
            rx.heading("Gestione dati — sorgenti", size="7", color=INK, weight="bold"),
            rx.text("Le basi dati che alimentano il motore, con stato letto DALLA CACHE reale. "
                    "«live» = re-interrogabile in automatico (ISTAT · Google Trends · ECB); "
                    "«manuale» = da aggiornare a mano (Banca d'Italia · Inside Airbnb · export regionali).",
                    color=MUT, font_size="0.9rem", margin_top="4px"),
            width="100%"),
        rx.box(
            kpi("Sorgenti collegate", State.ges_n, "al motore"),
            kpi("Attive (in cache)", State.ges_ok, "dati presenti"),
            kpi("Ri-aggiornabili live", State.ges_live, "ISTAT · Trends · ECB"),
            display="grid", grid_template_columns="repeat(3, 1fr)", gap="14px", width="100%"),
        panel("Inventario delle sorgenti", gestione_table()),
        _note("Vista in sola lettura. Le funzioni «admin» dello Streamlit (caricare file, approvare "
              "candidati, lanciare il controllo live) verranno portate come pannello a parte."),
        rx.text("Reflex · stato letto dalla cache · design «Istituzionale»",
                color=FAINT, font_size="0.75rem"))


# ════════════════════════════════════════════════════════════════════════════
# pagina: Confronto regioni ("/confronto")
# ════════════════════════════════════════════════════════════════════════════
def confronto_table() -> rx.Component:
    return rx.box(
        rx.table.root(
            rx.table.header(rx.table.row(
                rx.table.column_header_cell("Regione"),
                rx.table.column_header_cell("Spesa straniera"),
                rx.table.column_header_cell("Presenze str."),
                rx.table.column_header_cell("Posti letto"),
                rx.table.column_header_cell("Occupazione"),
                rx.table.column_header_cell("€/viaggiatore"),
                rx.table.column_header_cell("Quota str."))),
            rx.table.body(rx.foreach(State.cf_rows, lambda r: rx.table.row(
                rx.table.cell(r["regione"]),
                rx.table.cell(r["spesa"]),
                rx.table.cell(r["presenze"]),
                rx.table.cell(r["letti"]),
                rx.table.cell(r["occ"]),
                rx.table.cell(r["sp_viagg"]),
                rx.table.cell(r["quota"]),
                background=rx.cond(r["code"] == State.region_code, "#eef3f3", "transparent")))),
            variant="surface", size="1", width="100%"),
        max_height="420px", overflow_y="auto", width="100%")


def confronto_page() -> rx.Component:
    return page_shell(
        "confronto", "Panoramica  ›  Confronto regioni",
        rx.box(
            rx.heading("Confronto tra regioni", size="7", color=INK, weight="bold"),
            rx.text("Tutte le regioni a confronto sulle metriche chiave (ultimo anno disponibile). "
                    "La regione selezionata dal menu in alto è evidenziata nella tabella e nel grafico.",
                    color=MUT, font_size="0.9rem", margin_top="4px"),
            width="100%"),
        rx.box(
            kpi("Regioni", State.cf_n, "a confronto"),
            kpi("Leader per spesa", State.cf_top_spesa, "spesa straniera"),
            kpi("Leader per occupazione", State.cf_top_occ, "posti letto occupati"),
            display="grid", grid_template_columns="repeat(3, 1fr)", gap="14px", width="100%"),
        panel("Posizionamento: spesa × occupazione (bolla = posti letto)",
              rx.plotly(data=State.cf_scatter_fig, width="100%")),
        panel("Tabella comparativa", confronto_table()),
        rx.text("Reflex · DATI REALI (ISTAT · Banca d'Italia) · design «Istituzionale»",
                color=FAINT, font_size="0.75rem"))


# ════════════════════════════════════════════════════════════════════════════
# pagina: Forecast presenze ("/forecast")
# ════════════════════════════════════════════════════════════════════════════
def forecast_page() -> rx.Component:
    return page_shell(
        "forecast", "Cosa fare  ›  Forecast presenze",
        rx.box(
            rx.heading(State.fc_region + " — previsione presenze straniere", size="7", color=INK, weight="bold"),
            rx.text("Il motore statistico usa l'interesse di ricerca (con l'anticipo tipico del mercato), "
                    "la stagionalità e il trend per prevedere le presenze straniere dei prossimi mesi. "
                    "Orizzonte breve, entro l'anticipo del segnale.", color=MUT, font_size="0.9rem",
                    margin_top="4px"),
            width="100%"),
        rx.cond(State.fc_has_national,
                _note("Vista «Italia»: mostro " + State.fc_region + " come esempio. Scegli una regione "
                      "per la sua previsione."), rx.box()),
        rx.cond(State.fc_error != "", _note("Motore non disponibile: " + State.fc_error), rx.box()),
        rx.box(
            kpi("Errore medio (MAPE)", State.fc_mape, "più basso = più affidabile"),
            kpi("Batte il modello «ingenuo»?", State.fc_beats, "vs ripetere l'anno prima"),
            kpi("Anticipo del segnale", State.fc_lag, "mesi (ricerca → arrivi)"),
            display="grid", grid_template_columns="repeat(3, 1fr)", gap="14px", width="100%"),
        panel("Storico e previsione (con intervallo 80%)", rx.plotly(data=State.forecast_fig, width="100%")),
        panel("Come il modello legge i dati",
              rx.vstack(rx.foreach(State.fc_reading, lambda t: rx.hstack(
                  rx.icon("dot", size=18, color=ACCENT),
                  rx.text(t, color=MUT, font_size="0.85rem"),
                  align="start", spacing="1", width="100%")), spacing="2", width="100%")),
        _note("Stima d'opportunità, non garanzia: il modello coglie il segnale anticipatore, non "
              "l'effetto causale della spesa promozionale."),
        rx.text("Reflex · MOTORE STATISTICO (ISTAT · Google Trends) · design «Istituzionale»",
                color=FAINT, font_size="0.75rem"))


# ════════════════════════════════════════════════════════════════════════════
# pagina: Interesse online / Google Trends ("/interesse-online")
# ════════════════════════════════════════════════════════════════════════════
def interesse_table() -> rx.Component:
    return rx.box(
        rx.table.root(
            rx.table.header(rx.table.row(
                rx.table.column_header_cell("Mercato"),
                rx.table.column_header_cell("Interesse recente (media 3 mesi)"),
                rx.table.column_header_cell("Momentum (vs anno prima)"))),
            rx.table.body(rx.foreach(State.ie_rows, lambda r: rx.table.row(
                rx.table.cell(r["nome"]),
                rx.table.cell(r["recente"]),
                rx.table.cell(rx.badge(r["momentum"], color_scheme="teal", variant="soft", radius="full"))))),
            variant="surface", size="1", width="100%"),
        width="100%")


def interesse_page() -> rx.Component:
    return page_shell(
        "interesse", "Cosa fare  ›  Interesse online",
        rx.box(
            rx.heading(State.region_name + " — interesse di ricerca online", size="7", color=INK, weight="bold"),
            rx.text("Quanto si cerca la destinazione su Google, mercato per mercato (Google Trends). "
                    "È un segnale «leading»: l'interesse online anticipa gli arrivi di alcuni mesi.",
                    color=MUT, font_size="0.9rem", margin_top="4px"),
            width="100%"),
        rx.box(
            kpi("Parola chiave", State.ie_keyword, "termine cercato"),
            kpi("Mercati monitorati", State.ie_n, "paesi · Google Trends"),
            kpi("In maggior crescita", State.ie_top_nome, State.ie_top_mom + " sull'anno prima"),
            display="grid", grid_template_columns="repeat(3, 1fr)", gap="14px", width="100%"),
        panel("Interesse di ricerca nel tempo", rx.plotly(data=State.ie_lines_fig, width="100%")),
        panel("Dettaglio per mercato", interesse_table()),
        _note("Metodo: Google Trends normalizza l'interesse 0-100 SEPARATAMENTE per ciascun paese → i "
              "livelli non sono confrontabili tra paesi in assoluto; il segnale utile è il MOMENTUM "
              "(la variazione nel tempo dentro lo stesso paese)."),
        rx.text("Reflex · Google Trends · segnale leading · design «Istituzionale»",
                color=FAINT, font_size="0.75rem"))


# ════════════════════════════════════════════════════════════════════════════
# pagina: Home / landing ("/")
# ════════════════════════════════════════════════════════════════════════════
def entry_card(icon: str, title: str, desc: str, href: str) -> rx.Component:
    return rx.link(
        rx.box(
            rx.hstack(rx.icon(icon, size=22, color=ACCENT),
                      rx.text(title, font_weight="700", font_size="1rem", color=INK),
                      spacing="3", align="center"),
            rx.text(desc, color=MUT, font_size="0.82rem", margin_top="6px"),
            background=PANEL, border=f"1px solid {LINE}", border_radius="14px", padding="16px 18px",
            height="100%", _hover={"border_color": ACCENT, "box_shadow": "0 2px 12px rgba(14,107,112,0.10)"}),
        href=href, width="100%", text_decoration="none", style={"text-decoration": "none"})


def home_page() -> rx.Component:
    return page_shell(
        "home", "Home",
        rx.box(
            logo(),
            rx.heading("Dal dato turistico all'azione.", size="8", color=INK, weight="bold",
                       margin_top="16px"),
            rx.text("Intelligence turistica multi-regione: presenze, spesa, mercati esteri, affitti "
                    "brevi e un motore che indica dove e quando investire il budget promozionale. "
                    "Tutte le 20 regioni italiane, dati reali — ISTAT · Banca d'Italia · Google Trends · "
                    "Inside Airbnb.", color=MUT, font_size="1rem", max_width="840px", margin_top="8px"),
            background=PANEL, border=f"1px solid {LINE}", border_radius="18px", padding="28px 30px",
            width="100%"),
        rx.box(
            kpi("Spesa straniera · Italia", State.italia_spesa, "Banca d'Italia 2024"),
            kpi("Presenze straniere", State.it_presenze, "ultimo mese · ISTAT"),
            kpi("Regioni coperte", "20", "l'intera Italia"),
            kpi("Mercati esteri", State.it_mercati, "paesi di origine"),
            display="grid", grid_template_columns="repeat(4, 1fr)", gap="14px", width="100%"),
        rx.text("Esplora", font_size="0.7rem", letter_spacing="0.14em", color=FAINT,
                font_weight="600", style={"text-transform": "uppercase"}),
        rx.box(
            entry_card("layout-dashboard", "Regione", "Quadro sintetico: presenze, capacità, mercati, spesa.", "/regione"),
            entry_card("map", "Italia · mappa", "La spesa straniera regione per regione, cliccabile.", "/mappa"),
            entry_card("globe", "Mercati d'origine", "Da quali paesi arrivano i turisti e come cambia nel tempo.", "/mercati"),
            entry_card("bed-double", "Affitti brevi", "Il mercato Airbnb: annunci, prezzi, operatori, licenze.", "/affitti-brevi"),
            entry_card("banknote", "Spesa turistica", "Quanto vale ogni visitatore: yield e permanenza.", "/spesa"),
            entry_card("target", "Azioni & budget", "Il motore: dove e quando investire il budget promozionale.", "/azioni"),
            display="grid", grid_template_columns="repeat(3, 1fr)", gap="14px", width="100%"),
        panel("Top regioni per spesa turistica straniera (2024)",
              rx.vstack(
                  rx.foreach(State.home_top, lambda r: rx.hstack(
                      rx.text(r["regione"], color=INK, font_size="0.9rem"),
                      rx.spacer(),
                      rx.text(r["spesa"], color=ACCENT_INK, font_weight="600", font_size="0.9rem"),
                      width="100%")),
                  spacing="2", width="100%")),
        rx.text("Turism Data Hub · Reflex · dati reali · design «Istituzionale»",
                color=FAINT, font_size="0.75rem"))


app = rx.App(theme=rx.theme(appearance="light", accent_color="teal", gray_color="slate"))
app.add_page(azioni_page, route="/azioni", title="TDH · Azioni & budget", on_load=State.on_load)
app.add_page(interesse_page, route="/interesse-online", title="TDH · Interesse online", on_load=State.on_load)
app.add_page(forecast_page, route="/forecast", title="TDH · Forecast presenze", on_load=State.on_load)
app.add_page(confronto_page, route="/confronto", title="TDH · Confronto regioni", on_load=State.on_load)
app.add_page(gestione_page, route="/gestione-dati", title="TDH · Gestione dati", on_load=State.on_load)
app.add_page(architettura_page, route="/architettura", title="TDH · Architettura", on_load=State.on_load)
app.add_page(struttura_page, route="/per-struttura", title="TDH · Per struttura", on_load=State.on_load)
app.add_page(home_page, route="/", title="TDH · Turism Data Hub", on_load=State.on_load)
app.add_page(index, route="/regione", title="TDH · Regione", on_load=State.on_load)
app.add_page(map_page, route="/mappa", title="TDH · Italia mappa", on_load=State.on_load)
app.add_page(mercati_page, route="/mercati", title="TDH · Mercati d'origine", on_load=State.on_load)
app.add_page(affitti_page, route="/affitti-brevi", title="TDH · Affitti brevi (STR)", on_load=State.on_load)
app.add_page(spesa_page, route="/spesa", title="TDH · Spesa turistica", on_load=State.on_load)
app.add_page(province_page, route="/per-provincia", title="TDH · Per provincia", on_load=State.on_load)
app.add_page(ranking_page, route="/ranking", title="TDH · Ranking regioni", on_load=State.on_load)
app.add_page(base_dati_page, route="/base-dati", title="TDH · Base dati regionale", on_load=State.on_load)
