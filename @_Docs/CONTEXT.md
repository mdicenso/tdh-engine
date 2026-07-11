# TDH Engine — Contesto UI Redesign

## Situazione attuale
App Streamlit multi-pagina (20+ pagine) con dati reali ISTAT/BdI/Trends.
Il CSS base esiste già in `tdhlib.py` (variabile `CSS`, funzione `inject_css()`).
Il problema non è l'assenza di stile ma la mancanza di profondità visiva e gerarchia.

## Diagnosi dei problemi
1. **Tipografia piatta** — h1/h2/h3 hanno tutti lo stesso peso visivo
2. **Metric card piatte** — bordo #e5e7eb su sfondo bianco non ha contrasto su #f1f5f9
3. **Grafici** — paper_bgcolor:"white" crea riquadri bianchi che galleggiano sul #f1f5f9
4. **Nessuna gerarchia visiva** tra sezioni — tutto si appiattisce
5. **Bottoni primary** senza distinzione visiva dai bottoni secondari

---

## INTERVENTO 1 — Sostituire la variabile CSS in tdhlib.py

Trova la variabile `CSS = f"""<style>` e sostituiscila interamente con:

```python
CSS = f"""<style>
  html, body, [class*="css"] {{ font-family: {FONT_STACK}; }}
  .block-container {{ padding-top: 2.2rem; max-width: 1320px; }}

  /* Tipografia gerarchica */
  h1 {{ color: #0f172a; font-weight: 800; font-size: 1.6rem; letter-spacing: -0.02em; }}
  h2 {{ color: #0f172a; font-weight: 700; font-size: 1.15rem; letter-spacing: -0.01em;
        border-left: 3px solid #0e7490; padding-left: 10px; margin-top: 1.4rem; }}
  h3 {{ color: #334155; font-weight: 600; font-size: 1rem; }}

  /* Sfondo */
  .stApp {{ background-color: #f1f5f9; }}

  /* Sidebar scura */
  [data-testid="stSidebar"] {{ background-color: #1e293b; border-right: 1px solid #0f172a; }}
  [data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3,
  [data-testid="stSidebar"] p, [data-testid="stSidebar"] label,
  [data-testid="stSidebar"] [data-testid="stCaptionContainer"],
  [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] {{ color: #f1f5f9 !important; }}
  [data-testid="stSidebarNav"] a, [data-testid="stSidebarNav"] a span,
  [data-testid="stSidebarNav"] a p {{ color: #cbd5e1 !important; opacity: 1 !important; }}
  [data-testid="stSidebarNav"] span[data-testid="stIconMaterial"] {{ color: #cbd5e1 !important; }}
  [data-testid="stSidebarNav"] a:hover {{ background: rgba(14,116,144,.18); border-radius: 8px; }}
  [data-testid="stSidebarNav"] a:hover span,
  [data-testid="stSidebarNav"] a:hover p {{ color: #5eead4 !important; }}
  [data-testid="stSidebarNav"] a[aria-current="page"] {{
    background: rgba(14,116,144,.22); border-radius: 8px;
    border-left: 3px solid #0e7490; }}
  [data-testid="stSidebarNav"] a[aria-current="page"] span,
  [data-testid="stSidebarNav"] a[aria-current="page"] p {{ color: #5eead4 !important; font-weight: 700; }}
  [data-testid="stSidebar"] .stButton > button {{
    background: #334155; border: 1px solid #475569; color: #e2e8f0;
    border-radius: 8px; font-weight: 500; }}
  [data-testid="stSidebar"] .stButton > button:hover {{ border-color: #0e7490; color: #5eead4; }}

  /* Metric card con ombra e accent top */
  [data-testid="stMetric"] {{
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-top: 3px solid #0e7490;
    border-radius: 12px;
    padding: 16px 18px;
    box-shadow: 0 2px 8px rgba(15,23,42,.07);
    transition: box-shadow .15s;
  }}
  [data-testid="stMetric"]:hover {{ box-shadow: 0 4px 16px rgba(15,23,42,.12); }}
  [data-testid="stMetricLabel"] {{ color: #64748b; font-weight: 600; font-size: .8rem;
    text-transform: uppercase; letter-spacing: .04em; }}
  [data-testid="stMetricValue"] {{ color: #0f172a; font-weight: 800; }}

  /* Grafici: contenitore con ombra e bordi arrotondati */
  [data-testid="stPlotlyChart"] > div {{ border-radius: 14px;
    box-shadow: 0 2px 8px rgba(15,23,42,.06); overflow: hidden; }}

  /* Tabelle */
  [data-testid="stDataFrame"] {{ border-radius: 10px; overflow: hidden;
    box-shadow: 0 1px 4px rgba(15,23,42,.05); }}

  /* Bottoni */
  .stButton > button {{
    border-radius: 10px; border: 1px solid #e2e8f0;
    font-weight: 500; transition: all .15s; }}
  .stButton > button:hover {{ border-color: #0e7490; color: #0e7490;
    box-shadow: 0 2px 8px rgba(14,116,144,.15); }}
  .stButton > button[kind="primary"] {{
    background: linear-gradient(135deg, #0e7490, #0891b2);
    border: none; color: white; }}
  .stButton > button[kind="primary"]:hover {{
    background: linear-gradient(135deg, #0c6578, #0782a0);
    box-shadow: 0 4px 12px rgba(14,116,144,.3); }}

  /* Expander */
  [data-testid="stExpander"] {{ border-radius: 12px; border: 1px solid #e2e8f0;
    box-shadow: 0 1px 3px rgba(15,23,42,.04); }}

  /* Alert box */
  [data-testid="stAlert"] {{ border-radius: 10px; border-left-width: 4px; }}

  /* Selectbox e slider */
  [data-testid="stSelectbox"] > div > div {{ border-radius: 8px; border-color: #e2e8f0; }}
  [data-testid="stSlider"] [data-testid="stThumbValue"] {{ color: #0e7490; font-weight: 700; }}
</style>"""
```

---

## INTERVENTO 2 — Modificare la funzione _layout() in tdhlib.py

Trova la funzione `def _layout(fig: go.Figure, h: int = 420, title: str | None = None)` e sostituiscila con:

```python
def _layout(fig: go.Figure, h: int = 420, title: str | None = None) -> go.Figure:
    fig.update_layout(
        height=h,
        margin=dict(l=10, r=10, t=44 if title else 16, b=10),
        paper_bgcolor="rgba(255,255,255,0.0)",   # trasparente: si integra con sfondo #f1f5f9
        plot_bgcolor="rgba(255,255,255,0.95)",    # quasi bianco nell'area grafico
        title=(title or ""),
        font=dict(family=FONT_STACK, size=13, color="#334155"),
        colorway=["#0e7490", "#f59e0b", "#16a34a", "#7c3aed", "#dc2626", "#0891b2"],
        legend=dict(orientation="h", y=-0.18, font=dict(size=12),
                    bgcolor="rgba(255,255,255,0)", bordercolor="rgba(0,0,0,0)"),
        hoverlabel=dict(bgcolor="white", bordercolor="#e5e7eb",
                        font_size=12, font_family=FONT_STACK))
    fig.update_xaxes(showgrid=False, color="#64748b", linecolor="#e2e8f0")
    fig.update_yaxes(gridcolor="#f1f5f9", color="#64748b", zeroline=False)
    return fig
```

---

## INTERVENTO 3 — Aggiungere funzione section_header() in tdhlib.py

Aggiungi questa funzione subito dopo la funzione `hero()` in tdhlib.py:

```python
def section_header(title: str, subtitle: str = "", icon: str = ""):
    """Intestazione di sezione con linea accent — sostituisce st.subheader() nelle pagine."""
    st.markdown(f"""
    <div style="display:flex;align-items:center;gap:10px;margin:1.4rem 0 .6rem;
                padding-bottom:.6rem;border-bottom:1px solid #e2e8f0">
      {"<span style='font-size:1.2rem'>"+icon+"</span>" if icon else ""}
      <div>
        <div style="font-size:1.05rem;font-weight:700;color:#0f172a">{title}</div>
        {"<div style='font-size:.8rem;color:#64748b;margin-top:1px'>"+subtitle+"</div>" if subtitle else ""}
      </div>
    </div>""", unsafe_allow_html=True)
```

Uso in app.py (opzionale, sostituisce st.subheader):
```python
L.section_header("Ranking dei mercati", "ordinati per opportunità", "📊")
```

---

## Note importanti
- I file principali sono `app.py` (pagine) e `tdhlib.py` (logica + stile)
- `inject_css()` in tdhlib.py viene chiamata una volta sola in app.py subito dopo set_page_config
- La palette principale è: #0e7490 (teal primario), #f59e0b (amber), #f1f5f9 (sfondo)
- NON modificare app.py per gli interventi 1 e 2 — bastano le modifiche a tdhlib.py
- L'intervento 3 è opzionale: section_header() va aggiunta a tdhlib.py e poi usata in app.py
- Dopo le modifiche riavviare con: `streamlit run app.py`
