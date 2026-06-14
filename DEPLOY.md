# Deploy su Streamlit Community Cloud (accesso su invito)

L'app è già pronta: `app.py` è il file di avvio, `requirements.txt` elenca le
dipendenze, e i dati delle 8 fonti sono in `.cache/` (l'app gira senza rifare
le fetch). Restano 3 passi.

## 1 — Pubblica il codice su GitHub

**Opzione A — GitHub Desktop (consigliata, senza comandi)**
1. Apri GitHub Desktop → *File ▸ Add local repository* → scegli questa cartella.
2. *Publish repository* → spunta **Keep this code private** → *Publish*.

**Opzione B — da terminale** (incolla nel prompt di Claude Code col prefisso `!`)
1. Crea un repo **vuoto e privato** su https://github.com/new (es. `tdh-engine`),
   senza README/licenza.
2. Poi:
   ```
   git remote add origin https://github.com/<tuo-utente>/tdh-engine.git
   git push -u origin main
   ```
   (al primo push si apre il browser per autorizzare GitHub.)

## 2 — Crea l'app su Streamlit Cloud

1. Vai su https://share.streamlit.io → *Create app* → *Deploy a public app from GitHub*.
2. Repository: il repo appena pubblicato · Branch: `main` · Main file: `app.py`.
3. *Deploy*. Il primo avvio installa le dipendenze (qualche minuto).

## 3 — Limita l'accesso "su invito"

Nel cruscotto dell'app: **Settings ▸ Sharing**
- imposta l'app come **privata**;
- aggiungi gli **indirizzi email** di colleghi/amici autorizzati (entreranno
  con il login Google/GitHub). Solo loro potranno aprirla.

### (Opzionale) Password unica condivisa
In alternativa/aggiunta all'invito, puoi proteggere con una sola password:
**Settings ▸ Secrets** e incolla
```
APP_PASSWORD = "scegli-una-password"
```
Comparirà una schermata di login all'apertura. Senza questo secret, nessuna
password viene richiesta (vale l'accesso su invito del punto 3).

## Note
- **Assistente IA (chat):** ogni utente incolla la **propria** API key Anthropic
  nel campo della chat → non consuma i tuoi crediti. Senza key, tutto il resto
  dell'app funziona lo stesso.
- **Fonti candidate:** in cloud le approvazioni valgono per la sessione (il disco
  è effimero); le 8 fonti principali sono già nel repo e sempre disponibili.
- **Aggiornamenti:** ogni `git push` su `main` ridistribuisce l'app in automatico.
