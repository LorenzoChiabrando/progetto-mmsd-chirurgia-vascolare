@echo off
rem Avvio da sorgente: crea (o ripara) l'ambiente virtuale in source\venv, installa le
rem dipendenze e avvia l'applicazione. Il Python del sistema serve solo a creare l'ambiente:
rem non installa nulla nel sistema e non chiede permessi di amministratore.
setlocal EnableExtensions

set "QUI=%~dp0"
set "SOURCE=%QUI%source"
set "VENV=%SOURCE%\venv"
set "VPY=%VENV%\Scripts\python.exe"

rem Python del sistema: prima il launcher py dell'installer di python.org, poi python.
rem Il "python" finto del Microsoft Store non esegue nulla e viene scartato.
set "PY="
py -3 -c "import sys" >nul 2>&1 && set "PY=py -3"
if not defined PY python -c "import sys" >nul 2>&1 && set "PY=python"
if not defined PY call :errore "Python non trovato. Installa Python 3.10 o superiore da https://www.python.org/downloads/ e spunta 'Add Python to PATH'." & exit /b 1

set "VER_SIS="
for /f "usebackq delims=" %%v in (`%PY% -c "import sys; print('.'.join(map(str, sys.version_info[:2])))"`) do set "VER_SIS=%%v"
%PY% -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>&1
if errorlevel 1 call :errore "serve Python 3.10 o superiore, trovato Python %VER_SIS%." & exit /b 1

rem requirements.txt sceglie le versioni delle dipendenze in base alla versione di Python.
rem Un ambiente creato a meta' non ha pip, e uno creato con un'altra versione di Python
rem (aggiornamento, cartella copiata da un altro PC) ha le dipendenze sbagliate: in entrambi
rem i casi va ricreato.
set "RICREA="
if not exist "%VPY%" set "RICREA=1"
if not defined RICREA "%VPY%" -c "import sys; sys.exit('.'.join(map(str, sys.version_info[:2])) != sys.argv[1])" %VER_SIS% >nul 2>&1 || set "RICREA=1"
if not defined RICREA "%VPY%" -m pip --version >nul 2>&1 || set "RICREA=1"
if not defined RICREA goto :dipendenze

if exist "%VENV%" rmdir /s /q "%VENV%"
echo [setup] Creo l'ambiente virtuale in source\venv con Python %VER_SIS%...
%PY% -m venv "%VENV%"
if errorlevel 1 (
    if exist "%VENV%" rmdir /s /q "%VENV%"
    call :errore "creazione dell'ambiente virtuale non riuscita, vedi i messaggi sopra."
    exit /b 1
)

:dipendenze
rem Le dipendenze si reinstallano se requirements.txt cambia o se non si importano.
set "TIMBRO=%VENV%\.requirements.sha256"
set "ATTESO="
for /f "usebackq delims=" %%h in (`%PY% -c "import hashlib, sys; print(hashlib.sha256(open(sys.argv[1], 'rb').read()).hexdigest())" "%SOURCE%\requirements.txt"`) do set "ATTESO=%%h"
set "ATTUALE="
if exist "%TIMBRO%" set /p ATTUALE=<"%TIMBRO%"
set "INSTALLA="
if not "%ATTUALE%"=="%ATTESO%" set "INSTALLA=1"
"%VPY%" -c "import PySide6, pyomo, highspy" >nul 2>&1 || set "INSTALLA=1"
if not defined INSTALLA goto :avvio

echo [setup] Installo le dipendenze, la prima volta puo' richiedere qualche minuto...
"%VPY%" -m pip install --quiet --upgrade pip
if errorlevel 1 call :errore "aggiornamento di pip non riuscito. Serve la connessione a internet." & exit /b 1
"%VPY%" -m pip install --quiet -r "%SOURCE%\requirements.txt"
if errorlevel 1 call :errore "installazione delle dipendenze non riuscita. Serve la connessione a internet." & exit /b 1
>"%TIMBRO%" echo %ATTESO%

:avvio
rem Senza console stdout e stderr non esistono e il solver HiGHS fallirebbe: avvio.py li
rem collega a os.devnull e poi esegue main.py.
cd /d "%SOURCE%"
start "" "%VENV%\Scripts\pythonw.exe" "%QUI%packaging\windows\avvio.py" %*
exit /b 0

:errore
echo.
echo ERRORE: %~1
echo.
pause
exit /b 1
