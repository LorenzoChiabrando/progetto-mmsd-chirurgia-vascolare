# MMSD CV — Demo Chirurgia Vascolare

Applicazione desktop per la gestione dei medici specializzandi in Chirurgia Vascolare (UNITO).

---

## Quick start (Windows x64)

### Step 0 — Clone the repository

```cmd
git clone https://github.com/LorenzoChiabrando/progetto-mmsd-chirurgia-vascolare.git
cd progetto-mmsd-chirurgia-vascolare
git checkout windows-demo
```

---

### Option 1 — Executable (recommended, no dependencies required)

Double-click `ScadenzarioCV.exe`.

> User data is saved automatically in `%APPDATA%\ScadenzarioCV\`.

---

### Option 2 — From source

**Requirements:** Python 3.10 or higher, download from [python.org](https://www.python.org/downloads/).
During installation, make sure to check **"Add Python to PATH"**.

Double-click `run.bat`, or from the command prompt:

```cmd
run.bat
```

The script automatically creates a virtual environment and installs dependencies on first run. Subsequent launches start directly.

> If Windows Defender shows a warning, click **"More info" → "Run anyway"**.

---

## Repository structure

```
ScadenzarioCV.exe  compiled executable (Windows x64)
run.bat            run from source script
source\            Python source code
```

---

## Technical notes

- GUI framework: PySide6 (Qt6)
- Tested on Windows 10/11 x64
- The executable does not require Python installed on the system
