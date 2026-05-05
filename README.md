# MMSD CV — Demo Chirurgia Vascolare

Applicazione desktop per la gestione dei medici specializzandi in Chirurgia Vascolare (UNITO).

---

## Quick start (Linux x86-64)

### Step 0 — Clone the repository

```bash
git clone https://github.com/LorenzoChiabrando/progetto-mmsd-chirurgia-vascolare.git
cd progetto-mmsd-chirurgia-vascolare
```

### Option 1 — Executable (recommended, no dependencies required)

If needed, grant execution permission first:

```bash
chmod +x ScadenzarioCV
```

Then run:

```bash
./ScadenzarioCV
```

Or double-click `ScadenzarioCV` in the file manager.

> User data is saved automatically in `~/.local/share/ScadenzarioCV/`.

---

### Option 2 — From source

**Requirements:** Python 3.10 or higher, internet connection on first run.

If needed, grant execution permission first:

```bash
chmod +x run.sh
```

Then run:

```bash
./run.sh
```

The script automatically creates a virtual environment and installs dependencies on first run. Subsequent launches start directly.

---

## Repository structure

```
ScadenzarioCV      compiled executable (Linux x86-64)
run.sh             run from source script
source/            Python source code
```

---

## Technical notes

- GUI framework: PySide6 (Qt6)
- Tested on Ubuntu 22.04+ and Linux distributions with glibc ≥ 2.14
- The executable does not require Python installed on the system
