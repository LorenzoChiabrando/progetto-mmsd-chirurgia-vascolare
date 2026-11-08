@echo off
rem Ricompila ScadenzarioCV.exe da source\ con PyInstaller, in un ambiente virtuale dedicato
rem (packaging\windows\venv). Serve Python 3.10-3.13: come l'eseguibile Linux, che usa
rem Python 3.11 e PySide6 6.9.3 (con Python 3.14 requirements.txt installa un altro PySide6).
rem
rem   packaging\windows\build.bat                         usa py -3.11
rem   packaging\windows\build.bat C:\percorso\python.exe  usa quel Python
setlocal EnableExtensions

set "QUI=%~dp0"
for %%r in ("%QUI%..\..") do set "RADICE=%%~fr"
set "VENV=%QUI%venv"

if "%~1"=="" (set "PY=py -3.11") else (set "PY="%~1"")
%PY% -c "import sys; sys.exit(not (3, 10) <= sys.version_info[:2] < (3, 14))"
if errorlevel 1 (
    echo ERRORE: serve Python 3.10-3.13. Passa il percorso di python.exe come argomento.
    exit /b 1
)

if exist "%VENV%" rmdir /s /q "%VENV%"
%PY% -m venv "%VENV%" || exit /b 1
"%VENV%\Scripts\python.exe" -m pip install --quiet --upgrade pip || exit /b 1
"%VENV%\Scripts\python.exe" -m pip install --quiet -r "%RADICE%\source\requirements.txt" ^
    pyinstaller==6.22.3 pyinstaller-hooks-contrib==2026.8 || exit /b 1

"%VENV%\Scripts\python.exe" -m PyInstaller --noconfirm --clean ^
    --distpath "%QUI%dist" --workpath "%QUI%build" "%QUI%ScadenzarioCV.spec" || exit /b 1

copy /y "%QUI%dist\ScadenzarioCV.exe" "%RADICE%\ScadenzarioCV.exe" >nul || exit /b 1
echo Eseguibile aggiornato: %RADICE%\ScadenzarioCV.exe
