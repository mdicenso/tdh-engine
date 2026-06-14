"""
Proof-of-concept GIS con Plotly — mappa dei mercati esteri per Abruzzo (dati reali).

Genera un file HTML autonomo (poc_map.html) con Plotly.js INCORPORATO:
si apre nel browser offline, senza scaricare tile o script da CDN (a prova di proxy).
La mappa usa una GeoJSON dei confini in cache (.cache/world_countries.geojson),
quindi NON dipende dal topojson di plot.ly.

    python poc_map.py   ->   poc_map.html  (doppio click per aprirlo)
"""
import json
import math

import plotly.graph_objects as go

from tourism_wedge.engine_aggregate import assemble_real, rank_markets

# centroidi (lat, lon) dei mercati + destinazione Abruzzo
CENTROID = {
    "DE": (51.2, 10.4), "AT": (47.6, 14.1), "GB": (54.0, -2.0),
    "NL": (52.1, 5.3), "CH": (46.8, 8.2), "US": (39.5, -98.5),
}
ISO3 = {"DE": "DEU", "AT": "AUT", "GB": "GBR", "NL": "NLD", "CH": "CHE", "US": "USA"}
ABRUZZO = (42.35, 13.4)

# raccomandazione -> (colore, etichetta categoria)
def reco_style(reco: str) -> tuple[str, str]:
    if reco.startswith("Aumentare"):
        return "#16a34a", "Aumentare"
    if reco.startswith("Ridurre"):
        return "#dc2626", "Ridurre"
    if reco.startswith("Monitorare"):
        return "#f59e0b", "Monitorare"
    return "#2563eb", "Mantenere"


def build_figure() -> go.Figure:
    gj = json.load(open(".cache/world_countries.geojson", encoding="utf-8"))
    all_ids = [f.get("id") for f in gj["features"] if f.get("id")]
    cards = rank_markets(assemble_real(start="2019-01"))
    max_score = max((c["score"] for c in cards), default=1) or 1

    fig = go.Figure()

    # 1) base: tutti i paesi in grigio (geometria inline, offline)
    fig.add_trace(go.Choropleth(
        geojson=gj, featureidkey="id", locations=all_ids, z=[0] * len(all_ids),
        colorscale=[[0, "#e6e8eb"], [1, "#e6e8eb"]], showscale=False,
        marker_line_color="#ffffff", marker_line_width=0.4, hoverinfo="skip"))

    # 2) linee origine -> Abruzzo (richiamo visivo del flusso)
    lon_l, lat_l = [], []
    for c in cards:
        la, lo = CENTROID[c["code"]]
        lon_l += [lo, ABRUZZO[1], None]
        lat_l += [la, ABRUZZO[0], None]
    fig.add_trace(go.Scattergeo(lon=lon_l, lat=lat_l, mode="lines",
                                line=dict(width=0.8, color="rgba(120,120,120,0.45)"),
                                hoverinfo="skip", showlegend=False))

    # 3) bolle per mercato, una traccia per categoria (per la legenda)
    by_cat: dict[str, list] = {}
    for c in cards:
        color, cat = reco_style(c["raccomandazione"])
        by_cat.setdefault((cat, color), []).append(c)
    for (cat, color), group in by_cat.items():
        fig.add_trace(go.Scattergeo(
            lon=[CENTROID[c["code"]][1] for c in group],
            lat=[CENTROID[c["code"]][0] for c in group],
            mode="markers+text",
            text=[c["market"] for c in group], textposition="top center",
            textfont=dict(size=11, color="#111827"),
            marker=dict(
                size=[14 + 46 * math.sqrt(max(c["score"], 1) / max_score) for c in group],
                color=color, opacity=0.85, line=dict(width=1.2, color="white")),
            name=cat,
            customdata=[[c["rank"], c["raccomandazione"], c["forza_anticipatrice"],
                         c["momentum_search_pct"], round(c["score"])] for c in group],
            hovertemplate="<b>%{text}</b><br>#%{customdata[0]} · %{customdata[1]}"
                          "<br>Forza anticipatrice: %{customdata[2]:+.2f}"
                          "<br>Momentum ricerca: %{customdata[3]:+.0f}%"
                          "<br>Score: %{customdata[4]:,}<extra></extra>"))

    # 4) destinazione Abruzzo
    fig.add_trace(go.Scattergeo(lon=[ABRUZZO[1]], lat=[ABRUZZO[0]], mode="markers+text",
                                text=["ABRUZZO"], textposition="bottom center",
                                textfont=dict(size=12, color="#7c2d12"),
                                marker=dict(size=16, color="#7c2d12", symbol="star"),
                                name="Destinazione", hoverinfo="text"))

    fig.update_layout(
        title=dict(text="TDH Engine — Mercati esteri per Abruzzo (dati reali)<br>"
                        "<span style='font-size:13px;color:#6b7280'>colore = raccomandazione · "
                        "dimensione bolla = score · linea = flusso verso Abruzzo</span>", x=0.02),
        geo=dict(projection_type="natural earth", showland=False, showcountries=False,
                 showcoastlines=False, showframe=False, showocean=True, oceancolor="#eaf2fb",
                 bgcolor="rgba(0,0,0,0)", lataxis_range=[22, 66], lonaxis_range=[-120, 32]),
        legend=dict(title="Raccomandazione", orientation="h", yanchor="bottom", y=-0.05, x=0.02),
        margin=dict(l=0, r=0, t=70, b=0), height=620, paper_bgcolor="white")
    return fig


if __name__ == "__main__":
    fig = build_figure()
    out = "poc_map.html"
    fig.write_html(out, include_plotlyjs=True, full_html=True)
    print(f"Mappa generata: {out} (apri con doppio click; Plotly.js incorporato, offline).")
