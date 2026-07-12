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

# ── aggancio al data-layer condiviso (TDH_Engine) ───────────────────────────
_TDH_ENGINE = os.environ.get(
    "TDH_ENGINE_DIR",
    r"C:/Users/mcenso/OneDrive - Indra/@_Desktop_ OLD/@@@_Appoggio AI/Work_Area/"
    r"Programma Abruzzo/Motore Tourism Data HUB/TDH_Engine",
)
if _TDH_ENGINE not in sys.path:
    sys.path.insert(0, _TDH_ENGINE)
import tdh_data as D  # noqa: E402

# ── design tokens (Istituzionale) ──
ACCENT = "#0e6b70"; ACCENT_INK = "#0a4f53"; INK = "#10262a"; MUT = "#5c7176"
FAINT = "#8aa0a4"; LINE = "#e4ebec"; BG = "#f5f7f7"; PANEL = "#ffffff"; MUTED_BAR = "#a9c3c5"

# elenco regioni per il selettore: Italia + le 20 regioni (nome → codice NUTS2)
REGIONI = [("Italia", "ITALIA")] + list(D.REGIONI_SELECT)
NOMI = [n for n, _ in REGIONI]
NAME2CODE = {n: c for n, c in REGIONI}


class State(rx.State):
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

    @rx.event
    def on_load(self):
        self._load()
        if not self.rank_regioni:
            self.rank_regioni = [dict(r) for r in D.regions_spend_ranking()]
            tot = D.region_spend("ITALIA")
            self.italia_spesa = f"{D._it_int(tot[0])} M€" if tot else "—"
        if not self._map_codes:
            m = D.mappa_snapshot()
            self._map_geojson = m["geojson"] or {}
            self._map_names, self._map_codes, self._map_z = m["names"], m["codes"], m["z"]

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
        sel = [i for i, c in enumerate(self._map_codes) if c == self.region_code]
        fig = go.Figure(go.Choropleth(
            geojson=gj, featureidkey="properties.reg_name",
            locations=self._map_names, z=self._map_z, customdata=self._map_codes,
            colorscale="Teal", marker_line_color="white", marker_line_width=0.6,
            selectedpoints=(sel or None),
            selected=dict(marker=dict(opacity=1.0)),
            unselected=dict(marker=dict(opacity=0.5)),
            colorbar=dict(title=dict(text="spesa straniera<br>2024 (M€)", side="right")),
            hovertemplate="<b>%{location}</b><br>spesa %{z:,.0f} M€<extra></extra>"))
        fig.update_geos(fitbounds="locations", visible=False, projection_type="mercator",
                        bgcolor="rgba(0,0,0,0)")
        fig.update_layout(height=640, margin=dict(l=0, r=0, t=6, b=0),
                          paper_bgcolor="rgba(0,0,0,0)", font=dict(color=MUT, size=12))
        return fig


# ════════════════════════════════════════════════════════════════════════════
# componenti condivisi (design-system)
# ════════════════════════════════════════════════════════════════════════════
def logo() -> rx.Component:
    svg = ('<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="white" '
           'stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 20l6-14 4 9 3-5 5 10"/></svg>')
    return rx.hstack(
        rx.box(rx.html(svg), background=ACCENT, border_radius="10px", width="40px", height="40px",
               display="flex", align_items="center", justify_content="center"),
        rx.vstack(
            rx.text("Turism Data Hub", font_size="1.05rem", font_weight="700", color=INK, line_height="1.1"),
            rx.text("PORTALE NAZIONALE DEL TURISMO", font_size="0.62rem", letter_spacing="0.16em", color=FAINT),
            spacing="0", align_items="start"),
        spacing="3", align="center")


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
        background=PANEL, border=f"1px solid {LINE}", border_radius="16px", padding="18px 20px")


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
        nav_item("layout-dashboard", "Regione", active=(active == "regione"), href="/"),
        nav_item("map", "Italia · mappa", active=(active == "mappa"), href="/mappa"),
        nav_item("globe", "Mercati d'origine"),
        nav_group("Cosa è successo"),
        nav_item("map-pin", "Per provincia"),
        nav_item("house", "Affitti brevi"),
        nav_item("database", "Base dati regionale", active=(active == "basedati"), href="/base-dati"),
        nav_item("banknote", "Spesa turistica"),
        nav_group("Cosa fare"),
        nav_item("trophy", "Ranking regioni", active=(active == "ranking"), href="/ranking"),
        nav_item("target", "Azioni & budget"),
        nav_group("Sistema"),
        nav_item("messages-square", "Assistente"),
        spacing="1", align_items="start", width="264px", min_width="264px",
        height="100vh", position="sticky", top="0px",
        background=PANEL, border_right=f"1px solid {LINE}", padding="20px 14px")


def topbar(breadcrumb: str) -> rx.Component:
    return rx.box(
        rx.hstack(
            rx.text(breadcrumb, font_size="0.8rem", color=MUT),
            rx.spacer(),
            rx.select(NOMI, value=State.region_name, on_change=State.set_region, width="220px"),
            align="center", width="100%"),
        border_bottom=f"1px solid {LINE}", padding_bottom="12px", width="100%")


def page_shell(active: str, breadcrumb: str, *content) -> rx.Component:
    return rx.hstack(
        sidebar(active),
        rx.box(
            rx.vstack(topbar(breadcrumb), *content, spacing="4", width="100%", max_width="1180px"),
            flex="1", min_height="100vh", background=BG, padding="24px 34px",
            display="flex", justify_content="center"),
        spacing="0", align="start", width="100%")


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
        panel("Mappa della spesa straniera",
              rx.plotly(data=State.map_fig, on_click=State.on_map_click, width="100%")),
        rx.text("Reflex · DATI REALI (Banca d'Italia) · clic per selezionare · design «Istituzionale»",
                color=FAINT, font_size="0.75rem"))


app = rx.App(theme=rx.theme(appearance="light", accent_color="teal", gray_color="slate"))
app.add_page(index, route="/", title="TDH · Regione", on_load=State.on_load)
app.add_page(map_page, route="/mappa", title="TDH · Italia mappa", on_load=State.on_load)
app.add_page(ranking_page, route="/ranking", title="TDH · Ranking regioni", on_load=State.on_load)
app.add_page(base_dati_page, route="/base-dati", title="TDH · Base dati regionale", on_load=State.on_load)
