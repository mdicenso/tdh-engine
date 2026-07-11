@echo off
REM ============================================================================
REM  TDH Engine - aggiornamento automatico delle fonti dati.
REM  1) update_check.py --apply  -> scarica nella cache SOLO i dati nuovi
REM     (skip intelligente: se non c'e' nulla di nuovo non riscarica).
REM  2) se la cache e' cambiata -> git commit + push  (il cruscotto su
REM     Streamlit Cloud si aggiorna da solo).
REM  Lanciabile a mano (doppio click) o dal Task Scheduler (task settimanale).
REM  Log completo in: data\update_scheduler.log
REM ============================================================================
setlocal enableextensions
set "PROJ=C:\Users\mcenso\OneDrive - Indra\@_Desktop_ OLD\@@@_Appoggio AI\Work_Area\Programma Abruzzo\Motore Tourism Data HUB\TDH_Engine"
set "PY=C:\Users\mcenso\tdh_venv\Scripts\python.exe"
set "GIT=C:\Program Files\Git\cmd\git.exe"
cd /d "%PROJ%"
if not exist "data" mkdir "data"
set "LOG=%PROJ%\data\update_scheduler.log"

echo.>>"%LOG%"
echo ==================================================>>"%LOG%"
echo [%DATE% %TIME%] TDH - aggiornamento automatico fonti>>"%LOG%"
echo TDH: controllo e scarico eventuali dati nuovi nella cache...

"%PY%" update_check.py --apply >>"%LOG%" 2>&1

REM pulizia del junk OneDrive che a volte disturba git
del /f /s /q ".git\refs\desktop.ini" >nul 2>&1

"%GIT%" add .cache >>"%LOG%" 2>&1
"%GIT%" diff --cached --quiet
set "CHANGED=%errorlevel%"

if "%CHANGED%"=="1" echo TDH: dati nuovi trovati - committo e pusho sul cloud...
if "%CHANGED%"=="1" "%GIT%" commit -m "auto: aggiornamento cache fonti %DATE%" >>"%LOG%" 2>&1
if "%CHANGED%"=="1" "%GIT%" push origin main >>"%LOG%" 2>&1
if "%CHANGED%"=="1" echo [%DATE% %TIME%] Push completato.>>"%LOG%"
if "%CHANGED%"=="1" echo TDH: fatto - cloud aggiornato.
if "%CHANGED%"=="0" echo [%DATE% %TIME%] Nessuna novita: cache invariata, niente commit.>>"%LOG%"
if "%CHANGED%"=="0" echo TDH: nessuna novita - cache gia' aggiornata.

echo [%DATE% %TIME%] Fine.>>"%LOG%"
echo TDH: log completo in "%LOG%"
endlocal
