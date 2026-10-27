"""Regenerate the demo notebooks in examples/ with nbformat.

Each notebook mirrors the self-checks of the matching layerN_*.py script.
Notebooks are written without outputs and validated against the nbformat
schema.

Usage:
    python examples/build_notebooks.py
"""

from __future__ import annotations

from pathlib import Path

import nbformat
from nbformat.v4 import new_code_cell, new_markdown_cell, new_notebook

HERE = Path(__file__).resolve().parent

LOAD_PATH = '''\
# Data file: set CMSOPEN_DATA_FILE to the absolute path of a NanoAOD ROOT file
# before starting Jupyter, e.g. the 2012C DoubleMuParked file described in DATA.md.
import os
from pathlib import Path

if not os.environ.get("CMSOPEN_DATA_FILE"):
    raise RuntimeError(
        "CMSOPEN_DATA_FILE is not set. Start Jupyter with "
        "CMSOPEN_DATA_FILE=/absolute/path/to/file.root jupyter lab ..."
    )
DATA_FILE = Path(os.environ["CMSOPEN_DATA_FILE"])
if not DATA_FILE.exists():
    raise FileNotFoundError(f"CMSOPEN_DATA_FILE points to a missing file: {DATA_FILE}")
print(f"Data file: {DATA_FILE}")'''

CHECKS_CLASS = '''\
class Checks:
    """Collects self-check results and prints one OK/FAIL/SKIP line each."""

    def __init__(self):
        self.failures = []

    def check(self, name, ok, detail):
        print(f"{'OK' if ok else 'FAIL'}: {name} ({detail})")
        if not ok:
            self.failures.append(name)

    def skip(self, name, reason):
        print(f"SKIP: {name} ({reason})")'''

FINISH = '''\
if checks.failures:
    raise AssertionError(f"{len(checks.failures)} check(s) failed: {', '.join(checks.failures)}")
print("All checks passed")'''


def layer1() -> nbformat.NotebookNode:
    cells = [
        new_code_cell(LOAD_PATH),
        new_markdown_cell(
            "# Layer 1: reading CMS NanoAOD with `cmsopen.ingestion`\n\n"
            "A NanoAOD file stores one row per collision *event* and one column (branch) per quantity. "
            "Particle quantities such as `Muon_pt` are *jagged*: each event holds a list whose length is "
            "that event's number of muons. `open_events` opens the file lazily: only metadata is read "
            "until we ask for specific branches."
        ),
        new_code_cell(
            "import numpy as np\n\n"
            "import cmsopen\n"
            "from cmsopen import open_events\n"
            "from cmsopen.ingestion import DIMUON_TRIGGERS_2012\n\n"
            'print(f"cmsopen imported from: {cmsopen.__file__}")\n'
            "events = open_events(DATA_FILE)\n"
            "print(events.summary())"
        ),
        new_markdown_cell(
            "## Raw muons in the first three events\n\n"
            "`pt` is the transverse momentum in GeV and `charge` is ±1. No cuts are applied, so soft and "
            "poorly measured muons appear alongside the energetic ones."
        ),
        new_code_cell(
            "muons = events.muons(entry_stop=3)\n"
            "for i in range(3):\n"
            '    print(f"event {i}: Muon_pt     = {muons.pt[i].to_numpy().astype(float).round(5).tolist()}")\n'
            '    print(f"         Muon_charge = {muons.charge[i].tolist()}")'
        ),
        new_markdown_cell(
            "## Dimuon trigger fraction\n\n"
            "The High Level Trigger decides online which collisions to keep. An event counts as triggered "
            "if either 2012 double-muon path fired."
        ),
        new_code_cell(
            "N_TRIGGER_EVENTS = 100_000\n"
            "fired = events.trigger(*DIMUON_TRIGGERS_2012, entry_stop=N_TRIGGER_EVENTS)\n"
            "fraction = float(fired.mean())\n"
            "print(f\"Dimuon trigger ({' OR '.join(DIMUON_TRIGGERS_2012)}) fraction, \"\n"
            '      f"first {len(fired):,} events: {fraction:.4f}")'
        ),
        new_markdown_cell(
            "## Self-checks\n\n"
            "These compare against numbers measured on the 2012C DoubleMuParked file "
            "(`45F7AE81-7A79-4CB1-998E-7BD156490294.root`). For any other file they are skipped."
        ),
        new_code_cell(CHECKS_CLASS),
        new_code_cell(
            'KNOWN_FILE = "45F7AE81-7A79-4CB1-998E-7BD156490294.root"\n'
            "KNOWN_N_EVENTS = 396_766\n"
            "KNOWN_FIRST_PTS = [71.24144, 25.51886, 3.74997]\n"
            "KNOWN_TRIGGER_FRACTION = 0.5212\n\n"
            "checks = Checks()\n"
            "if DATA_FILE.name != KNOWN_FILE:\n"
            '    reason = f"{DATA_FILE.name} is not the known 2012C file {KNOWN_FILE}"\n'
            '    checks.skip("event count", reason)\n'
            '    checks.skip("first-event muon pts", reason)\n'
            '    checks.skip("dimuon trigger fraction", reason)\n'
            "else:\n"
            '    checks.check("event count", len(events) == KNOWN_N_EVENTS, f"{len(events):,}, expected {KNOWN_N_EVENTS:,}")\n'
            "    pts = muons.pt[0].to_numpy().astype(float)\n"
            "    checks.check(\n"
            '        "first-event muon pts",\n'
            "        len(pts) == len(KNOWN_FIRST_PTS) and np.allclose(pts, KNOWN_FIRST_PTS, rtol=0, atol=1e-5),\n"
            '        f"{pts.round(5).tolist()}, expected {KNOWN_FIRST_PTS}",\n'
            "    )\n"
            "    checks.check(\n"
            '        "dimuon trigger fraction",\n'
            "        abs(fraction - KNOWN_TRIGGER_FRACTION) <= 0.002,\n"
            '        f"{fraction:.4f}, expected {KNOWN_TRIGGER_FRACTION} +/- 0.002",\n'
            "    )\n"
            "events.close()\n\n" + FINISH
        ),
    ]
    return _notebook(cells)


def _notebook(cells: list) -> nbformat.NotebookNode:
    nb = new_notebook(cells=cells)
    nb.metadata["kernelspec"] = {"name": "python3", "display_name": "Python 3", "language": "python"}
    nb.metadata["language_info"] = {"name": "python"}
    return nb


NOTEBOOKS = {
    "layer1_ingestion.ipynb": layer1,
}


def main() -> None:
    for name, build in NOTEBOOKS.items():
        nb = build()
        nbformat.validate(nb)
        nbformat.write(nb, HERE / name)
        print(f"wrote {HERE / name}")


if __name__ == "__main__":
    main()
