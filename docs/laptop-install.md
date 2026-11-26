# Laptop installation checks

The README's browser path needs no Python installation. For capture and
replay, use Python 3.9 or newer from the repository root. No board extras
are needed for the virtual bench.

Linux and macOS:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install '.[test]'
```

Windows PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install '.[test]'
```

If local policy prevents activating a PowerShell script, run the
environment's executables directly, for example
`.\.venv\Scripts\python.exe -m pip install '.[test]'` and
`.\.venv\Scripts\commoncause.exe diagnose --last`.

Then follow the [virtual bench guide](virtual-bench.md), using new output
paths. Timed scenarios work without an interactive terminal. The virtual
console has Windows-specific nonblocking key handling; the Linux I2C
capture path still needs a Pi and its board packages.

The **Laptop install** workflow creates a fresh environment on hosted
macOS and Windows machines, installs a non-editable package without board
extras, runs the tests, and follows the diagnose/explain/impact, virtual
F1, scoring, replay, and benchmark commands. Linux's corresponding checks
run in the main CI matrix. The Mac job additionally installs the Relate
CLI and checks export and MCP. The Windows job does not claim CLI export
coverage; the Python replay and browser import paths remain available.

Results from hosted machines establish compatibility for their recorded
runner images and Python version, not every desktop configuration. CI
artifacts retain the fresh recording and replay store for inspection.
