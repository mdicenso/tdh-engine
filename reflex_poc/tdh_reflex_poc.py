"""TDH — POC UI in Reflex (Python → React). Pagina 'Regione', design 'Istituzionale'.
Dati di ESEMPIO (sintetici). Serve a valutare la resa reale vs Streamlit."""
import reflex as rx
import plotly.graph_objects as go

# ── design tokens (Istituzionale) ──
ACCENT = "#0e6b70"; ACCENT_INK = "#0a4f53"; INK = "#10262a"; MUT = "#5c7176"
FAINT = "#8aa0a4"; LINE = "#e4ebec"; BG = "#f5f7f7"; PANEL = "#ffffff"; GOOD = "#15803d"; WARN = "#b45309"
MESI = ["Gen", "Feb", "Mar", "Apr", "Mag", "Giu", "Lug", "Ago", "Set", "Ott", "Nov", "Dic"]

DATA = {
    "Toscana": dict(pres="2.418.905", letti="540.312", spesa="6.842 M€", rank="3ª regione per spesa", mercati="61",
                    serie=[820, 860, 1010, 1280, 1620, 2050, 2380, 2419, 1780, 1240, 760, 900],
                    mkt=[("Germania", 2.72), ("Francia", 1.32), ("Svizzera", 0.91), ("Regno Unito", 0.71), ("Paesi Bassi", 0.55)]),
    "Lazio": dict(pres="3.980.120", letti="410.500", spesa="8.601 M€", rank="1ª regione per spesa", mercati="70",
                  serie=[1600, 1650, 1900, 2300, 2700, 3100, 3400, 3980, 3000, 2400, 1700, 1750],
                  mkt=[("Stati Uniti", 3.10), ("Germania", 1.62), ("Francia", 1.40), ("Regno Unito", 1.18), ("Spagna", 0.92)]),
    "Lombardia": dict(pres="3.210.700", letti="360.200", spesa="9.988 M€", rank="2ª regione per spesa", mercati="66",
                      serie=[1500, 1550, 1800, 2100, 2300, 2600, 2500, 2400, 2700, 2600, 1900, 1700],
                      mkt=[("Germania", 1.80), ("Francia", 1.10), ("Stati Uniti", 1.02), ("Regno Unito", 0.90), ("Svizzera", 0.82)]),
}
RANK = [("Germania", "▲ +14%", "694 €", "3 rotte", "Aumentare"),
        ("Paesi Bassi", "▲ +9%", "512 €", "1 rotta", "Aumentare"),
        ("Regno Unito", "▲ +3%", "729 €", "2 rotte", "Mantenere"),
        ("Stati Uniti", "▼ −2%", "1.566 €", "0 dirette", "Mantenere")]


class State(rx.State):
    region: str = "Toscana"

    @rx.event
    def set_region(self, value: str):
        self.region = value

    @rx.var
    def pres(self) -> str: return DATA[self.region]["pres"]
    @rx.var
    def letti(self) -> str: return DATA[self.region]["letti"]
    @rx.var
    def spesa(self) -> str: return DATA[self.region]["spesa"]
    @rx.var
    def rank(self) -> str: return DATA[self.region]["rank"]
    @rx.var
    def mercati(self) -> str: return DATA[self.region]["mercati"]
    @rx.var
    def titolo(self) -> str: return f"{self.region} — quadro turistico"

    @rx.var
    def presenze_fig(self) -> go.Figure:
        s = DATA[self.region]["serie"]
        fig = go.Figure(go.Scatter(x=MESI, y=s, mode="lines", line=dict(color=ACCENT, width=2.6),
                                   fill="tozeroy", fillcolor="rgba(14,107,112,.12)"))
        fig.update_layout(height=300, margin=dict(l=8, r=8, t=8, b=8), paper_bgcolor="rgba(0,0,0,0)",
                          plot_bgcolor="#ffffff", font=dict(color=MUT, size=12), showlegend=False)
        fig.update_xaxes(showgrid=False, linecolor=LINE)
        fig.update_yaxes(gridcolor="#eef3f3", zeroline=False, title="presenze (migliaia)")
        return fig

    @rx.var
    def mercati_fig(self) -> go.Figure:
        m = DATA[self.region]["mkt"][::-1]
        fig = go.Figure(go.Bar(x=[v for _, v in m], y=[n for n, _ in m], orientation="h", marker_color=ACCENT))
        fig.update_layout(height=300, margin=dict(l=8, r=8, t=8, b=8), paper_bgcolor="rgba(0,0,0,0)",
                          plot_bgcolor="#ffffff", font=dict(color=MUT, size=12))
        fig.update_xaxes(gridcolor="#eef3f3", title="presenze (milioni)")
        fig.update_yaxes(showgrid=False)
        return fig


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


def pill(text: str, kind: str) -> rx.Component:
    return rx.badge(text, color_scheme="grass" if kind == "a" else "amber", variant="soft", radius="full")


def ranking_table() -> rx.Component:
    return rx.table.root(
        rx.table.header(rx.table.row(
            *[rx.table.column_header_cell(h) for h in ["Mercato", "Momentum", "Valore €/turista", "Voli diretti", "Raccomandazione"]])),
        rx.table.body(*[
            rx.table.row(
                rx.table.cell(r[0]), rx.table.cell(r[1]), rx.table.cell(r[2]), rx.table.cell(r[3]),
                rx.table.cell(pill(r[4], "a" if r[4] == "Aumentare" else "m")))
            for r in RANK]),
        variant="surface", size="2", width="100%")


def nav_group(label: str) -> rx.Component:
    return rx.text(label, font_size="0.64rem", letter_spacing="0.14em", color=FAINT,
                   font_weight="600", margin="16px 10px 4px", style={"text-transform": "uppercase"})


def nav_item(icon: str, label: str, active: bool = False) -> rx.Component:
    return rx.hstack(
        rx.icon(icon, size=18, color=(ACCENT if active else MUT)),
        rx.text(label, font_size="0.87rem", font_weight=("600" if active else "500"),
                color=(ACCENT_INK if active else MUT)),
        spacing="3", align="center", width="100%", padding="8px 10px", border_radius="8px",
        background=("rgba(14,107,112,0.10)" if active else "transparent"),
        border_left=(f"3px solid {ACCENT}" if active else "3px solid transparent"),
        cursor="pointer", _hover={"background": "#eef3f3"})


def sidebar() -> rx.Component:
    return rx.vstack(
        rx.box(logo(), padding_bottom="16px", margin_bottom="6px",
               border_bottom=f"1px solid {LINE}", width="100%"),
        nav_group("Panoramica"),
        nav_item("layout-dashboard", "Regione", active=True),
        nav_item("map", "Italia · mappa"),
        nav_item("globe", "Mercati d'origine"),
        nav_group("Cosa è successo"),
        nav_item("map-pin", "Per provincia"),
        nav_item("house", "Affitti brevi"),
        nav_item("database", "Base dati regionale"),
        nav_item("banknote", "Spesa turistica"),
        nav_group("Cosa fare"),
        nav_item("trophy", "Ranking mercati"),
        nav_item("target", "Azioni & budget"),
        nav_group("Sistema"),
        nav_item("messages-square", "Assistente"),
        spacing="1", align_items="start", width="264px", min_width="264px",
        height="100vh", position="sticky", top="0px",
        background=PANEL, border_right=f"1px solid {LINE}", padding="20px 14px")


def main_area() -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.box(
                rx.hstack(
                    rx.text("Panoramica  ›  Regione", font_size="0.8rem", color=MUT),
                    rx.spacer(),
                    rx.select(list(DATA.keys()), value=State.region, on_change=State.set_region, width="200px"),
                    align="center", width="100%"),
                border_bottom=f"1px solid {LINE}", padding_bottom="12px", width="100%"),
            rx.box(
                rx.heading(State.titolo, size="7", color=INK, weight="bold"),
                rx.text("Presenze, capacità ricettiva e mercati esteri della regione. Fonti ISTAT · Banca d'Italia · Eurostat.",
                        color=MUT, font_size="0.9rem", margin_top="4px"),
                width="100%"),
            rx.box(
                kpi("Presenze straniere", State.pres, "ultimo mese"),
                kpi("Posti letto", State.letti, "capacità 2024"),
                kpi("Spesa straniera", State.spesa, State.rank),
                kpi("Mercati esteri", State.mercati, "paesi di origine"),
                display="grid", grid_template_columns="repeat(4, 1fr)", gap="14px", width="100%"),
            rx.box(
                panel("Presenze mensili", rx.plotly(data=State.presenze_fig, width="100%")),
                panel("Top mercati esteri", rx.plotly(data=State.mercati_fig, width="100%")),
                display="grid", grid_template_columns="3fr 2fr", gap="18px", width="100%"),
            panel("Ranking mercati — dove investire", ranking_table()),
            rx.text("POC in Reflex · dati di esempio · design «Istituzionale»", color=FAINT, font_size="0.75rem"),
            spacing="4", width="100%", max_width="1180px"),
        flex="1", min_height="100vh", background=BG, padding="24px 34px",
        display="flex", justify_content="center")


def index() -> rx.Component:
    return rx.hstack(sidebar(), main_area(), spacing="0", align="start", width="100%")


app = rx.App(theme=rx.theme(appearance="light", accent_color="teal", gray_color="slate"))
app.add_page(index, title="TDH · Regione (POC Reflex)")
