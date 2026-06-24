"""
Registro delle REGIONI italiane — rende "la regione una variabile".

IMPORTANTE: i codici NUTS2 sono quelli che ISTAT (DCSC_TUR / CL_ITTER107) accetta,
cioè la codifica NUTS *storica*: Centro = ITE (Toscana ITE1…), Nord-Est = ITD
(Veneto ITD3…). NON la NUTS 2021 (ITI/ITH). Le presenze ISTAT funzionano solo con questi.

Campi:
  code(chiave) NUTS2 ISTAT · nome · latlon capoluogo · airports ICAO ·
  trends_kw · wiki(it/en/de/nl) · bdi (etichetta Banca d'Italia).
Le province (NUTS3) vengono da assets/nuts3_provinces.json (estratte da CL_ITTER107).
"""
from __future__ import annotations

import functools
import json
import os

DEFAULT_REGION = "ITF1"  # Abruzzo (pilota)

# Sentinella "tutta Italia": vista d'insieme nazionale (non è un NUTS2).
NATIONAL = "ITALIA"
NATIONAL_LABEL = "🇮🇹 Italia (tutte le regioni)"

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
    "ITD1": {"nome": "Provincia Autonoma di Bolzano", "latlon": (46.50, 11.35), "airports": ["LIPB"],
             "trends_kw": "Alto Adige", "bdi": "Trentino Alto Adige",
             "wiki": {"it": "Sudtirolo", "en": "South Tyrol", "de": "Südtirol", "nl": "Zuid-Tirol"}},
    "ITD2": {"nome": "Provincia Autonoma di Trento", "latlon": (46.07, 11.12), "airports": [],
             "trends_kw": "Trentino", "bdi": "Trentino Alto Adige",
             "wiki": {"it": "Trentino", "en": "Trentino", "de": "Trentino", "nl": "Trentino"}},
    "ITD3": {"nome": "Veneto", "latlon": (45.44, 12.32), "airports": ["LIPZ", "LIPX", "LIPH"],
             "trends_kw": "Veneto", "bdi": "Veneto",
             "wiki": {"it": "Veneto", "en": "Veneto", "de": "Venetien", "nl": "Veneto"}},
    "ITD4": {"nome": "Friuli-Venezia Giulia", "latlon": (45.65, 13.78), "airports": ["LIPQ"],
             "trends_kw": "Friuli Venezia Giulia", "bdi": "Friuli Venezia Giulia",
             "wiki": {"it": "Friuli-Venezia Giulia", "en": "Friuli-Venezia Giulia",
                      "de": "Friaul-Julisch Venetien", "nl": "Friuli-Venezia Giulia"}},
    "ITD5": {"nome": "Emilia-Romagna", "latlon": (44.49, 11.34), "airports": ["LIPE", "LIPR", "LIMP"],
             "trends_kw": "Emilia Romagna", "bdi": "Emilia Romagna",
             "wiki": {"it": "Emilia-Romagna", "en": "Emilia-Romagna", "de": "Emilia-Romagna", "nl": "Emilia-Romagna"}},
    "ITE1": {"nome": "Toscana", "latlon": (43.77, 11.26), "airports": ["LIRP", "LIRQ"],
             "trends_kw": "Toscana", "bdi": "Toscana",
             "wiki": {"it": "Toscana", "en": "Tuscany", "de": "Toskana", "nl": "Toscane"}},
    "ITE2": {"nome": "Umbria", "latlon": (43.11, 12.39), "airports": ["LIRZ"],
             "trends_kw": "Umbria", "bdi": "Umbria",
             "wiki": {"it": "Umbria", "en": "Umbria", "de": "Umbrien", "nl": "Umbrië"}},
    "ITE3": {"nome": "Marche", "latlon": (43.62, 13.51), "airports": ["LIPY"],
             "trends_kw": "Marche", "bdi": "Marche",
             "wiki": {"it": "Marche", "en": "Marche", "de": "Marken", "nl": "Marche"}},
    "ITE4": {"nome": "Lazio", "latlon": (41.90, 12.50), "airports": ["LIRF", "LIRA"],
             "trends_kw": "Lazio", "bdi": "Lazio",
             "wiki": {"it": "Lazio", "en": "Lazio", "de": "Latium", "nl": "Lazio"}},
    "ITF1": {"nome": "Abruzzo", "latlon": (42.35, 13.40), "airports": ["LIBP"],
             "trends_kw": "Abruzzo", "bdi": "Abruzzo",
             "wiki": {"it": "Abruzzo", "en": "Abruzzo", "de": "Abruzzen", "nl": "Abruzzen"}},
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

# Nome regione nel geojson (openpolis) → per la mappa d'Italia.
GEO_NAME = {
    "ITC1": "Piemonte", "ITC2": "Valle d'Aosta/Vallée d'Aoste", "ITC3": "Liguria", "ITC4": "Lombardia",
    "ITD1": "Trentino-Alto Adige/Südtirol", "ITD2": "Trentino-Alto Adige/Südtirol", "ITD3": "Veneto",
    "ITD4": "Friuli-Venezia Giulia", "ITD5": "Emilia-Romagna", "ITE1": "Toscana", "ITE2": "Umbria",
    "ITE3": "Marche", "ITE4": "Lazio", "ITF1": "Abruzzo", "ITF2": "Molise", "ITF3": "Campania",
    "ITF4": "Puglia", "ITF5": "Basilicata", "ITF6": "Calabria", "ITG1": "Sicilia", "ITG2": "Sardegna",
}


def code_for_geo(reg_name: str | None):
    """Nome regione del geojson → codice NUTS2 (primo match)."""
    return next((c for c, n in GEO_NAME.items() if n == reg_name), None)


@functools.lru_cache(maxsize=1)
def _prov_map() -> dict:
    p = "assets/nuts3_provinces.json"
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}


def provinces(code: str | None = None) -> dict:
    """{NUTS3: nome} delle province della regione (da CL_ITTER107). {} se ignota."""
    return _prov_map().get(code or DEFAULT_REGION, {})


def is_national(code: str | None) -> bool:
    """True se il codice è la sentinella «tutta Italia»."""
    return code == NATIONAL


def istat_area(code: str | None) -> str:
    """Codice REF_AREA per ISTAT: «IT» (totale Italia) per la sentinella nazionale,
    altrimenti il NUTS2 della regione. (Verificato: ISTAT accetta area='IT'.)"""
    return "IT" if code == NATIONAL else (code or DEFAULT_REGION)


def region(code: str | None = None) -> dict:
    """Dict della regione (default Abruzzo). Aggiunge sempre 'code'.
    Con la sentinella NATIONAL ritorna una pseudo-regione «Italia»."""
    if code == NATIONAL:
        return {"code": NATIONAL, "nome": "Italia", "latlon": (41.90, 12.50),
                "airports": [], "trends_kw": "Italia", "bdi": "Italia",
                "wiki": {"it": "Italia", "en": "Italy", "de": "Italien", "nl": "Italië"}}
    code = code if code in REGIONS else DEFAULT_REGION
    r = dict(REGIONS[code])
    r["code"] = code
    return r


def region_names(include_national: bool = True) -> dict:
    """code -> nome, ordinato per nome (per i selettori).
    Con include_national, «Italia» è la PRIMA voce."""
    names = {NATIONAL: NATIONAL_LABEL} if include_national else {}
    for c in sorted(REGIONS, key=lambda c: REGIONS[c]["nome"]):
        names[c] = REGIONS[c]["nome"]
    return names
