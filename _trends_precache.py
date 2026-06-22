"""Pre-scarica Google Trends per TUTTE le regioni × mercati, A PICCOLI LOTTI.
Resumibile (salta i cache esistenti). Pensato per girare schedulato più volte al
giorno: ogni esecuzione prende fino a MAX_OK risultati e si ferma se Google blocca
(così non spreca tempo), poi riprende al run successivo. Quando 'da fare' = 0, è completo."""
import os
import time

MAX_OK = 15          # quante regioni-mercato scaricare al massimo per esecuzione
MAX_CONSEC_FAIL = 4  # se Google blocca per N volte di fila, mi fermo e riprovo dopo
RETRIES = 2          # tentativi per singolo fetch (poi lo lascio al prossimo run)

try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

import regions as RG
from tourism_wedge import DEFAULT_MARKETS
from tourism_wedge import real_sources as RS

GEOS = [mk.code for mk in DEFAULT_MARKETS]


def safe(kw):
    return "".join(c if c.isalnum() else "_" for c in kw.lower())


jobs = []
for code, info in RG.REGIONS.items():
    for geo in GEOS:
        if not os.path.exists(f".cache/trends_{safe(info['trends_kw'])}_{geo}.csv"):
            jobs.append((info["trends_kw"], geo))

print(f"da fare: {len(jobs)}", flush=True)
ok = consec_fail = 0
for kw, geo in jobs:
    if ok >= MAX_OK:
        print(f"raggiunto limite per run ({MAX_OK}).", flush=True)
        break
    if consec_fail >= MAX_CONSEC_FAIL:
        print("Google sta bloccando: mi fermo, riprovo al prossimo run.", flush=True)
        break
    got = False
    for att in range(RETRIES):
        try:
            RS.fetch_search_monthly(geo, keyword=kw, pause=4)
            ok += 1
            consec_fail = 0
            got = True
            print(f"OK {kw}/{geo}", flush=True)
            break
        except Exception as e:
            print(f"{type(e).__name__} {kw}/{geo} att{att + 1}", flush=True)
            time.sleep(30 * (att + 1))
    if not got:
        consec_fail += 1
    time.sleep(5)
print(f"FINE run: scaricati {ok}. Restano da fare: {len(jobs) - ok}.", flush=True)
