"""
Adattatori dati per il motore 'wedge' (allocazione budget promo per mercato estero).

Principio di architettura: ogni fonte sta dietro un'interfaccia (PanelProvider).
Oggi è alimentata da un provider SINTETICO; domani sostituisci l'adattatore reale
(Google Trends, ISTAT, Banca d'Italia, ECB, Eurostat) senza toccare il motore.

Contratto dati per mercato (DataFrame mensile):
    date       -> primo giorno del mese
    presences  -> presenze per provenienza        [target, lagging]   fonte reale: ISTAT
    search     -> interesse di ricerca 0..100      [segnale leading]   fonte reale: Google Trends
    fx         -> indice del cambio (1.0 = media)  [driver]            fonte reale: ECB SDW
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Market:
    code: str                 # "DE", "US", ...
    name: str                 # "Germania", ...
    currency: str             # "EUR", "USD", "GBP", "CHF"
    spend_per_visitor: float  # peso valore economico (EUR/visitatore)  fonte: Banca d'Italia
    capacity_ok: bool         # headroom capacità voli (True) o vincolo  fonte: Eurostat avia


DEFAULT_MARKETS = [
    Market("DE", "Germania",     "EUR", 95.0,  True),
    Market("AT", "Austria",      "EUR", 88.0,  True),
    Market("GB", "Regno Unito",  "GBP", 140.0, True),
    Market("US", "Stati Uniti",  "USD", 220.0, False),  # alto valore ma capacità voli vincolata
    Market("NL", "Paesi Bassi",  "EUR", 110.0, True),
    Market("CH", "Svizzera",     "CHF", 175.0, True),
]


class PanelProvider(Protocol):
    """Interfaccia che ogni adattatore (sintetico o reale) deve implementare."""
    def monthly_panel(self, market: Market) -> pd.DataFrame: ...


@dataclass
class SyntheticProvider:
    """Pannello mensile con segnale 'piantato' a fini di collaudo:
    - stagionalità esplicita (profilo per mese),
    - un lead-lag VERO noto: il search anticipa le presenze di `true_lag` mesi,
    - un effetto cambio VERO per i mercati non-Euro (euro debole -> piu' arrivi).
    Se il motore e' corretto, RECUPERA questi coefficienti e li sa spiegare.
    """
    start: str = "2019-01"
    months: int = 72
    true_lag: int = 2
    beta_search: float = 9.0    # +1 punto di search (al lag) -> +9 presenze/mese
    beta_fx: float = 1500.0     # euro piu' debole (fx sotto 1.0) -> piu' arrivi non-Euro
    seed: int = 7

    def monthly_panel(self, market: Market) -> pd.DataFrame:
        rng = np.random.default_rng(self.seed + (abs(hash(market.code)) % 1000))
        dates = pd.period_range(self.start, periods=self.months, freq="M").to_timestamp()
        month = dates.month.to_numpy()
        t = np.arange(self.months)

        # --- segnale leading: interesse di ricerca (0..100) ---
        search = (50
                  + 9 * np.sin(2 * np.pi * (t + 1) / 12)   # ciclo annuale (anticipa la stagione)
                  + 0.04 * t                               # leggero trend di notorieta'
                  + rng.normal(0, 4, self.months))
        # spinta recente per-mercato (es. campagna/notorieta'): genera varieta'
        # di raccomandazioni a fini di collaudo della logica decisionale.
        recent_boost = {"DE": 14, "US": 16, "AT": 7, "GB": 2, "NL": -6, "CH": -9}.get(market.code, 0)
        search[-4:] += recent_boost
        search = np.clip(search, 0, 100)

        # --- driver: cambio (solo non-Euro) attorno a 1.0 ---
        if market.currency == "EUR":
            fx = np.ones(self.months)
        else:
            fx = 1.0 + np.cumsum(rng.normal(0, 0.008, self.months))

        # --- stagionalita' esplicita (estate forte) e scala per-mercato ---
        season_profile = np.array([0.40, 0.45, 0.60, 0.75, 0.90, 1.10,
                                   1.45, 1.55, 1.00, 0.70, 0.50, 0.55])
        level = {"DE": 4200, "AT": 1300, "GB": 2600, "US": 1700, "NL": 1500, "CH": 950}[market.code]
        season = level * season_profile[month - 1]

        # --- presenze = stagione + effetto(search al lag) + effetto(cambio) + trend + rumore ---
        search_lag = np.concatenate([np.full(self.true_lag, np.nan), search[:-self.true_lag]]) \
            if self.true_lag > 0 else search.copy()
        fx_term = self.beta_fx * (1.0 - fx) if market.currency != "EUR" else np.zeros(self.months)

        presences = (season
                     + self.beta_search * (np.nan_to_num(search_lag, nan=50.0) - 50.0)
                     + fx_term
                     + 6.0 * t
                     + rng.normal(0, level * 0.06, self.months))
        presences = np.clip(presences, 0, None)

        return pd.DataFrame({"date": dates, "presences": presences,
                             "search": search, "fx": fx})


# --------------------------------------------------------------------------
# STUB ADATTATORI REALI -- da implementare nel tuo ambiente (rete aperta).
# La firma e' identica a SyntheticProvider: si sostituisce e basta.
# --------------------------------------------------------------------------
class RealPanelProvider:
    """Scheletro dell'adattatore di produzione. Ogni metodo punta all'endpoint reale.

    presences -> ISTAT 'Movimento dei clienti' per provenienza, regione, mese (SDMX).
    search    -> Google Trends via pytrends, geo=paese di origine, settimanale->mensile.
    fx        -> ECB Statistical Data Warehouse (EXR), giornaliero->medio mensile.
    Allinea tutto a granularita' mensile e restituisci lo stesso schema del sintetico.
    """
    def monthly_panel(self, market: Market) -> pd.DataFrame:  # pragma: no cover
        raise NotImplementedError(
            "Collega qui ISTAT (presences) + Google Trends (search) + ECB (fx). "
            "Restituisci un DataFrame con colonne: date, presences, search, fx."
        )
