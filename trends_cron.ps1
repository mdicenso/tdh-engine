# Esecuzione schedulata: scarica un lotto di Google Trends per le regioni mancanti,
# poi committa e pusha le nuove cache. Resumibile: quando sono tutte presenti non fa nulla.
$ErrorActionPreference = "Continue"
$proj = "C:\Users\mcenso\OneDrive - Indra\@_Desktop_ OLD\@@@_Appoggio AI\Work_Area\Programma Abruzzo\Motore Tourism Data HUB\TDH_Engine"
$py = "C:\Users\mcenso\tdh_venv\Scripts\python.exe"
Set-Location -LiteralPath $proj

# 1) scarica un lotto
$env:PYTHONUTF8 = "1"
& $py "_trends_precache.py" 2>&1 | Out-File -Append -Encoding utf8 "$proj\trends_cron.log"

# 2) pulizia desktop.ini che OneDrive infila in .git
Get-ChildItem -LiteralPath "$proj\.git" -Recurse -Filter "desktop.ini" -Force -ErrorAction SilentlyContinue |
    Remove-Item -Force -ErrorAction SilentlyContinue

# 3) committa e pusha le nuove cache (solo se ce ne sono)
git add .cache/trends_*.csv 2>$null
git diff --cached --quiet
if ($LASTEXITCODE -ne 0) {
    git commit -m "Trends pre-cache: lotto schedulato" | Out-Null
    git pull --no-edit origin main 2>&1 | Out-Null
    git push 2>&1 | Out-Null
    "$(Get-Date -Format s)  commit+push eseguito" | Out-File -Append -Encoding utf8 "$proj\trends_cron.log"
} else {
    "$(Get-Date -Format s)  nessuna nuova cache" | Out-File -Append -Encoding utf8 "$proj\trends_cron.log"
}
