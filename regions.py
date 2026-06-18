"""
Registro delle REGIONI italiane — rende "la regione una variabile".

Ogni regione mappa i parametri che le fonti del TDH usano:
  code      : NUTS2 ISTAT (REF_AREA per DCSC_TUR)
  nome      : nome esteso (UI)
  latlon    : coord. del capoluogo (per meteo)
  airports  : ICAO degli aeroporti commerciali (Eurostat avia_par)
  trends_kw : keyword Google Trends (di norma il nome regione)
  wiki      : articolo Wikipedia per lingua (it/en/de/nl) — segnale culturale
  bdi       : etichetta regione come appare nei dati Banca d'Italia (TS2 / regioni_2024)

NB: le province (NUTS3) si ricavano da ISTAT; qui le elenchiamo dove già note
(Abruzzo) e si completano in fase 2 con discovery verificata.
"""
from __future__ import annotations

DEFAULT_REGION = "ITF1"  # Abruzzo (pilota)

REGIONS = {
    "ITC1": {"nome": "Piemonte", "latlon": (45.07, 7.69), "airports": ["LIMF"],
             "trends_kw": "Piemonte", "bdi": "Piemonte",
             "wiki": {"it": "Piemonte", "en": "Piedmont", "de": "Piemont", "nl": "Piëmont"}},
    "ITC2": {"nome": "Valle d'Aosta", "latlon": (45.74, 7.32), "airports": [],
             "trends_kw": "Valle d'Aosta", "bdi": "Valle d'Aosta",
             "wiki": {"it": "Valle d'Aosta", "en": "Aosta Valley", "de": "Aostatal", "nl": "Valle d'Aosta"}},
    "ITC3": {"nome": "Liguria", "latlon": (44.41, 8.93), "airports": ["LIMJ"],
             "trends_kw": "Liguria", "bdi": "Liguria",
             "wiki": {"it": "Liguria", "en": "Liguria", "de": "Ligurien", "nl": "Ligurië"}},
    "ITC4": {"nome": "Lombardia", "latlon": (45.46, 9.19), "airports": ["LIMC", "LIML", "LIME"],
             "trends_kw": "Lombardia", "bdi": "Lombardia",
             "wiki": {"it": "Lombardia", "en": "Lombardy", "de": "Lombardei", "nl": "Lombardije"}},
    "ITH1": {"nome": "Provincia Autonoma di Bolzano", "latlon": (46.50, 11.35), "airports": ["LIPB"],
             "trends_kw": "Alto Adige", "bdi": "Trentino Alto Adige",
             "wiki": {"it": "Sudtirolo", "en": "South Tyrol", "de": "Südtirol", "nl": "Zuid-Tirol"}},
    "ITH2": {"nome": "Provincia Autonoma di Trento", "latlon": (46.07, 11.12), "airports": [],
             "trends_kw": "Trentino", "bdi": "Trentino Alto Adige",
             "wiki": {"it": "Trentino", "en": "Trentino", "de": "Trentino", "nl": "Trentino"}},
    "ITH3": {"nome": "Veneto", "latlon": (45.44, 12.32), "airports": ["LIPZ", "LIPX", "LIPH"],
             "trends_kw": "Veneto", "bdi": "Veneto",
             "wiki": {"it": "Veneto", "en": "Veneto", "de": "Venetien", "nl": "Veneto"}},
    "ITH4": {"nome": "Friuli-Venezia Giulia", "latlon": (45.65, 13.78), "airports": ["LIPQ"],
             "trends_kw": "Friuli Venezia Giulia", "bdi": "Friuli Venezia Giulia",
             "wiki": {"it": "Friuli-Venezia Giulia", "en": "Friuli-Venezia Giulia",
                      "de": "Friaul-Julisch Venetien", "nl": "Friuli-Venezia Giulia"}},
    "ITH5": {"nome": "Emilia-Romagna", "latlon": (44.49, 11.34), "airports": ["LIPE", "LIPR", "LIMP"],
             "trends_kw": "Emilia Romagna", "bdi": "Emilia Romagna",
             "wiki": {"it": "Emilia-Romagna", "en": "Emilia-Romagna", "de": "Emilia-Romagna", "nl": "Emilia-Romagna"}},
    "ITI1": {"nome": "Toscana", "latlon": (43.77, 11.26), "airports": ["LIRP", "LIRQ"],
             "trends_kw": "Toscana", "bdi": "Toscana",
             "wiki": {"it": "Toscana", "en": "Tuscany", "de": "Toskana", "nl": "Toscane"}},
    "ITI2": {"nome": "Umbria", "latlon": (43.11, 12.39), "airports": ["LIRZ"],
             "trends_kw": "Umbria", "bdi": "Umbria",
             "wiki": {"it": "Umbria", "en": "Umbria", "de": "Umbrien", "nl": "Umbrië"}},
    "ITI3": {"nome": "Marche", "latlon": (43.62, 13.51), "airports": ["LIPY"],
             "trends_kw": "Marche", "bdi": "Marche",
             "wiki": {"it": "Marche", "en": "Marche", "de": "Marken", "nl": "Marche"}},
    "ITI4": {"nome": "Lazio", "latlon": (41.90, 12.50), "airports": ["LIRF", "LIRA"],
             "trends_kw": "Lazio", "bdi": "Lazio",
             "wiki": {"it": "Lazio", "en": "Lazio", "de": "Latium", "nl": "Lazio"}},
    "ITF1": {"nome": "Abruzzo", "latlon": (42.35, 13.40), "airports": ["LIBP"],
             "trends_kw": "Abruzzo", "bdi": "Abruzzo",
             "wiki": {"it": "Abruzzo", "en": "Abruzzo", "de": "Abruzzen", "nl": "Abruzzen"},
             "province": {"ITF11": "L'Aquila", "ITF12": "Teramo", "ITF13": "Pescara", "ITF14": "Chieti"}},
    "ITF2": {"nome": "Molise", "latlon": (41.56, 14.66), "airports": [],
             "trends_kw": "Molise", "bdi": "Molise",
             "wiki": {"it": "Molise", "en": "Molise", "de": "Molise", "nl": "Molise"}},
    "ITF3": {"nome": "Campania", "latlon": (40.84, 14.25), "airports": ["LIRN", "LIRI"],
             "trends_kw": "Campania", "bdi": "Campania",
             "wiki": {"it": "Campania", "en": "Campania", "de": "Kampanien", "nl": "Campanië"}},
    "ITF4": {"nome": "Puglia", "latlon": (41.13, 16.87), "airports": ["LIBD", "LIBR"],
             "trends_kw": "Puglia", "bdi": "Puglia",
             "wiki": {"it": "Puglia", "en": "Apulia", "de": "Apulien", "nl": "Apulië"}},
    "ITF5": {"nome": "Basilicata", "latlon": (40.64, 15.81), "airports": [],
             "trends_kw": "Basilicata", "bdi": "Basilicata",
             "wiki": {"it": "Basilicata", "en": "Basilicata", "de": "Basilikata", "nl": "Basilicata"}},
    "ITF6": {"nome": "Calabria", "latlon": (38.91, 16.59), "airports": ["LICA", "LICR", "LIBC"],
             "trends_kw": "Calabria", "bdi": "Calabria",
             "wiki": {"it": "Calabria", "en": "Calabria", "de": "Kalabrien", "nl": "Calabrië"}},
    "ITG1": {"nome": "Sicilia", "latlon": (38.12, 13.36), "airports": ["LICC", "LICJ", "LICT", "LICB"],
             "trends_kw": "Sicilia", "bdi": "Sicilia",
             "wiki": {"it": "Sicilia", "en": "Sicily", "de": "Sizilien", "nl": "Sicilië"}},
    "ITG2": {"nome": "Sardegna", "latlon": (39.22, 9.12), "airports": ["LIEE", "LIEO", "LIEA"],
             "trends_kw": "Sardegna", "bdi": "Sardegna",
             "wiki": {"it": "Sardegna", "en": "Sardinia", "de": "Sardinien", "nl": "Sardinië"}},
}


# Nome regione come appare nel geojson (openpolis) → per agganciare la mappa d'Italia.
# Bolzano e Trento condividono il poligono "Trentino-Alto Adige".
GEO_NAME = {
    "ITC1": "Piemonte", "ITC2": "Valle d'Aosta/Vallée d'Aoste", "ITC3": "Liguria", "ITC4": "Lombardia",
    "ITH1": "Trentino-Alto Adige/Südtirol", "ITH2": "Trentino-Alto Adige/Südtirol", "ITH3": "Veneto",
    "ITH4": "Friuli-Venezia Giulia", "ITH5": "Emilia-Romagna", "ITI1": "Toscana", "ITI2": "Umbria",
    "ITI3": "Marche", "ITI4": "Lazio", "ITF1": "Abruzzo", "ITF2": "Molise", "ITF3": "Campania",
    "ITF4": "Puglia", "ITF5": "Basilicata", "ITF6": "Calabria", "ITG1": "Sicilia", "ITG2": "Sardegna",
}


def code_for_geo(reg_name: str | None):
    """Nome regione del geojson → codice NUTS2 (primo match)."""
    return next((c for c, n in GEO_NAME.items() if n == reg_name), None)


def region(code: str | None = None) -> dict:
    """Restituisce il dict della regione (default Abruzzo). Aggiunge sempre 'code'."""
    code = code or DEFAULT_REGION
    r = dict(REGIONS.get(code, REGIONS[DEFAULT_REGION]))
    r["code"] = code if code in REGIONS else DEFAULT_REGION
    return r


def region_names() -> dict:
    """code -> nome, ordinato per nome (per i selettori)."""
    return {c: REGIONS[c]["nome"] for c in sorted(REGIONS, key=lambda c: REGIONS[c]["nome"])}
