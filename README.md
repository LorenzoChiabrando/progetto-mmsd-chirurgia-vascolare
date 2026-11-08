# MMSD CV — Demo Chirurgia Vascolare

Applicazione desktop per la gestione dei medici specializzandi in Chirurgia Vascolare (UNITO):
scadenzario dei turni, libretti, lista pazienti e pianificazione delle sale operatorie
(Pyomo + HiGHS).

---

## Quick start (Windows 10 / 11 x64)

### Step 0 — Get the Windows demo

```cmd
git clone -b windows-demo --single-branch https://github.com/LorenzoChiabrando/progetto-mmsd-chirurgia-vascolare.git
cd progetto-mmsd-chirurgia-vascolare
```

(`-b windows-demo` matters: the default branch does not contain the Windows executable.)

### Option 1 — Executable (recommended, nothing to install)

Double-click `ScadenzarioCV.exe`. The first start takes a few seconds longer while the
program unpacks itself.

If Windows SmartScreen shows "Windows protected your PC", click **More info → Run anyway**:
the executable is not digitally signed.

Your data is kept in `%APPDATA%\ScadenzarioCV\v2\dati` (logs in
`%APPDATA%\ScadenzarioCV\v2\logs`). On the first start it is filled with the demo data;
delete the `dati` folder to start again from the demo data. If you started an earlier
version of the executable, its data stays in `%APPDATA%\ScadenzarioCV` and is not used:
you can delete it.

The demo covers September–December 2026 with 120 synthetic patients, as of 27 October
2026. The operating-room weeks up to 23 October have Previsto and Effettivo confirmed, with
the interventions recorded in the logbooks; the week of 26–30 October has the Effettivo
still in draft. November and December are drafts.

---

### Option 2 — From source

**Requirements:** Python 3.10 or newer from [python.org](https://www.python.org/downloads/)
(during installation check **"Add Python to PATH"**), internet connection on the first run.

Double-click `run.bat`, or from the command prompt:

```cmd
run.bat
```

`run.bat` creates a virtual environment in `source\venv` with the system Python, installs
the dependencies there and starts the application. It installs nothing into the system
Python and never needs administrator rights.

The dependency versions follow the Python version: from 3.10 to 3.13 the same versions as
the executable (PySide6 6.9.3); on Python 3.14 and newer, where PySide6 6.9 does not exist,
the most recent compatible PySide6 6.x. When the system Python changes, the next `run.bat`
recreates `source\venv` by itself.

---

## If it does not start

| Message | Fix |
|---|---|
| "Windows protected your PC" | **More info → Run anyway** (the executable is not signed). |
| `Python non trovato` | Install Python from python.org with **"Add Python to PATH"**, then `run.bat` again. The Microsoft Store `python` alias is not enough. |
| `serve Python 3.10 o superiore` | Install a newer Python from python.org, or use the executable. |
| `ModuleNotFoundError: No module named 'PySide6'` | Start with `run.bat`, not `python main.py`. It also repairs an environment left half-created. |
| `installazione delle dipendenze non riuscita` | Check the internet connection (and proxy), then `run.bat` again. |

---

## Repository structure

```
ScadenzarioCV.exe   compiled executable (Windows x64)
run.bat             run from source
source\             Python source code of the application
packaging\windows\  recipe to rebuild the executable
```

## Rebuilding the executable

The executable is built with PyInstaller from Python 3.11, like the Linux one, in a
dedicated virtual environment:

```cmd
packaging\windows\build.bat                          :: uses py -3.11
packaging\windows\build.bat C:\path\to\python.exe    :: or a given Python 3.10–3.13
powershell -ExecutionPolicy Bypass -File packaging\windows\verifica.ps1
```

`build.bat` rebuilds `ScadenzarioCV.exe` from `source\`; `verifica.ps1` starts it with an
empty user folder and checks that the window opens and the demo data is created.

---

## Technical notes

- GUI: PySide6 6.9 (Qt 6.9); optimization: Pyomo with the HiGHS solver (`highspy`)
- The executable does not require Python installed on the system
- `source\` is the same code as the `linux-demo` branch and `dev-env`
