# MMSD CV — Demo Chirurgia Vascolare

Applicazione desktop per la gestione dei medici specializzandi in Chirurgia Vascolare (UNITO):
scadenzario dei turni, libretti, lista pazienti e pianificazione delle sale operatorie
(Pyomo + HiGHS).

---

## Quick start (Linux x86-64)

### Step 0 — Get the Linux demo

```bash
git clone -b linux-demo --single-branch https://github.com/LorenzoChiabrando/progetto-mmsd-chirurgia-vascolare.git
cd progetto-mmsd-chirurgia-vascolare
```

(`-b linux-demo` matters: the default branch does not contain the Linux executable.)

### Option 1 — Executable (recommended, nothing to install)

```bash
chmod +x ScadenzarioCV
./ScadenzarioCV
```

Or double-click `ScadenzarioCV` in the file manager. The first start takes a few seconds
longer while the program unpacks itself.

Works on any x86-64 Linux with **glibc 2.28 or newer** — Ubuntu 20.04+, Linux Mint 20+,
Debian 10+, Fedora, RHEL / AlmaLinux / Rocky 8+ — on both X11 and Wayland desktops. Python
is not needed, and neither are extra Qt libraries: they are inside the executable.

Your data is kept in `~/.local/share/ScadenzarioCV/v2/dati` (logs in
`~/.local/share/ScadenzarioCV/v2/logs`). On the first start it is filled with the demo
data; delete the `dati` folder to start again from the demo data. If you started an
earlier version of the executable, delete or rename that folder to load the current demo.

The demo covers September–December 2026 with 120 synthetic patients, as of 27 October
2026. The operating-room weeks up to 23 October have Previsto and Effettivo confirmed, with
the interventions recorded in the logbooks; the week of 26–30 October has the Effettivo
still in draft. November and December are drafts.

---

### Option 2 — From source

**Requirements:** Python 3.10 or newer with the `venv` module, internet connection on
the first run. On Ubuntu / Debian:

```bash
sudo apt install python3-venv libxcb-cursor0
```

On Fedora / RHEL: `sudo dnf install xcb-util-cursor`.

Then:

```bash
chmod +x run.sh
./run.sh
```

`run.sh` creates a virtual environment in `source/venv` with the system `python3`, installs
the dependencies there and starts the application. It installs nothing into the system
Python and never needs `sudo`: do not install the dependencies with `sudo pip install`.

The dependency versions follow the Python version: from 3.10 to 3.13 the same versions as
the executable (PySide6 6.9.3); on Python 3.14 and newer, where PySide6 6.9 does not exist,
the most recent compatible PySide6 6.x. When the system Python changes, the next
`./run.sh` recreates `source/venv` by itself.

---

## If it does not start

| Message | Fix |
|---|---|
| `version 'GLIBC_2.xx' not found` | The system is older than Ubuntu 20.04 / Debian 10. Use Option 2. |
| `ModuleNotFoundError: No module named 'PySide6'` | Start with `./run.sh`, not `python3 main.py`. It also repairs an environment left half-created. |
| `manca il modulo venv di Python` | `sudo apt install python3-venv`, then `./run.sh` again. |
| `Could not load the Qt platform plugin "xcb"` (from source) | `sudo apt install libxcb-cursor0` (Fedora: `sudo dnf install xcb-util-cursor`), or use the executable. |
| `Permission denied` | `chmod +x ScadenzarioCV run.sh` |

---

## Repository structure

```
ScadenzarioCV      compiled executable (Linux x86-64, glibc ≥ 2.28)
run.sh             run from source
source/            Python source code of the application
packaging/linux/   recipe to rebuild the executable
```

## Rebuilding the executable

The executable is built with PyInstaller inside an AlmaLinux 8 container (glibc 2.28), so
it starts on every newer distribution. Docker is required:

```bash
packaging/linux/build.sh      # rebuilds ./ScadenzarioCV from source/
packaging/linux/verifica.sh   # starts it in clean Ubuntu, Debian and Fedora containers
```

---

## Technical notes

- GUI: PySide6 6.9 (Qt 6.9); optimization: Pyomo with the HiGHS solver (`highspy`)
- Executable tested in clean containers: Ubuntu 20.04, 22.04 and 24.04, Debian 12, Fedora 42
  (X11) and Ubuntu 24.04 (Wayland); the HiGHS solver was checked inside the executable too
- From source tested on Ubuntu 22.04 with Python 3.10
- The executable does not require Python installed on the system
