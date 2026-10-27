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


def layer2() -> nbformat.NotebookNode:
    cells = [
        new_code_cell(LOAD_PATH),
        new_markdown_cell(
            "# Layer 2: muons as physics objects with `cmsopen.objects`\n\n"
            "The detector reports each muon as transverse momentum $p_T$, pseudorapidity "
            "$\\eta = -\\ln\\tan(\\theta/2)$, azimuthal angle $\\phi$ and an assigned mass "
            "$m_\\mu = 0.1057$ GeV. From these follow the Cartesian components\n\n"
            "$$p_x = p_T\\cos\\phi,\\quad p_y = p_T\\sin\\phi,\\quad p_z = p_T\\sinh\\eta,\\quad "
            "E = \\sqrt{p^2 + m^2},\\ p = p_T\\cosh\\eta.$$\n\n"
            "A `Muon` object holds *all* muons in a set of events as jagged arrays: one list per event."
        ),
        new_code_cell(
            "import awkward as ak\n"
            "import numpy as np\n\n"
            "import cmsopen\n"
            "from cmsopen import Muon, open_events\n\n"
            "try:\n"
            "    import vector\n"
            "except ImportError:\n"
            "    vector = None\n\n"
            'print(f"cmsopen imported from: {cmsopen.__file__}")\n'
            "print(f\"vector library: {vector.__version__ if vector else 'not installed (pip install vector to enable the cross-check)'}\")"
        ),
        new_markdown_cell("## Load the first 100,000 events as a `Muon` collection"),
        new_code_cell(
            "N_EVENTS = 100_000\n"
            "with open_events(DATA_FILE) as events:\n"
            "    muons = Muon.from_events(events, entry_stop=N_EVENTS)\n"
            "p4 = muons.p4\n\n"
            "print(repr(muons))\n"
            'print(f"events: {len(muons):,}   muons: {int(ak.sum(muons.num)):,}")\n'
            'print(f"muons per event, first 5 events (.num): {muons.num[:5].tolist()}")'
        ),
        new_markdown_cell(
            "## Kinematics of the muons in event 0\n\n"
            "Note how $|p_z|$ exceeds $p_T$ for $|\\eta| > 0.88$ (where $\\sinh\\eta > 1$), and how $E \\approx p$ "
            "because these muons are far from rest."
        ),
        new_code_cell(
            'print("event 0 muons (GeV, radians):")\n'
            "columns = {\n"
            '    "pt": p4.pt[0], "eta": p4.eta[0], "phi": p4.phi[0], "charge": muons.charge[0],\n'
            '    "E": p4.energy[0], "px": p4.px[0], "py": p4.py[0], "pz": p4.pz[0],\n'
            "}\n"
            'print("  #  " + "".join(f"{name:>11}" for name in columns))\n'
            "for j in range(int(muons.num[0])):\n"
            "    cells = \"\".join(\n"
            '        f"{int(v[j]):>11d}" if name == "charge" else f"{float(v[j]):>11.5f}" for name, v in columns.items()\n'
            "    )\n"
            '    print(f"  {j:<3}{cells}")'
        ),
        new_markdown_cell(
            "## Self-checks\n\n"
            "1. **Mass shell.** $E^2 - |\\vec p|^2 = m^2$ for every muon. $E^2$ and $|\\vec p|^2$ are large and nearly "
            "equal, so their difference is exact only to a few float64 rounding units of $E^2$; the tolerance is "
            "relative to $E^2$.\n"
            "2. **Known values** of the first event's muon $p_T$ (2012C file only).\n"
            "3. **Independent implementation:** agreement with the `vector` library, if installed.\n"
            "4. **Structure:** the four-momentum arrays have the same particle count per event as `.num`."
        ),
        new_code_cell(CHECKS_CLASS),
        new_code_cell(
            'KNOWN_FILE = "45F7AE81-7A79-4CB1-998E-7BD156490294.root"\n'
            "KNOWN_FIRST_PTS = [71.24144, 25.51886, 3.74997]\n"
            "SHELL_TOLERANCE = 16 * np.finfo(np.float64).eps\n\n\n"
            "def flat(x):\n"
            "    return ak.to_numpy(ak.flatten(x, axis=None))\n\n\n"
            "checks = Checks()\n\n"
            "px, py, pz, e = (flat(c) for c in p4.as_cartesian())\n"
            "e2 = e**2\n"
            "residual = e2 - (px**2 + py**2 + pz**2) - flat(p4.mass) ** 2\n"
            "rel = np.abs(residual) / e2\n"
            "checks.check(\n"
            '    f"E^2 - |p|^2 = m^2 for all {len(e):,} muons",\n'
            "    bool(np.all(rel <= SHELL_TOLERANCE)),\n"
            '    f"max abs error {np.abs(residual).max():.3g} GeV^2, max error relative to E^2 {rel.max():.3g}, "\n'
            '    f"tolerance {SHELL_TOLERANCE:.3g}",\n'
            ")\n\n"
            "if DATA_FILE.name == KNOWN_FILE:\n"
            "    pts = p4.pt[0].to_numpy()\n"
            "    checks.check(\n"
            '        "first-event muon pts",\n'
            "        len(pts) == len(KNOWN_FIRST_PTS) and np.allclose(pts, KNOWN_FIRST_PTS, rtol=0, atol=1e-5),\n"
            '        f"{pts.round(5).tolist()}, expected {KNOWN_FIRST_PTS}",\n'
            "    )\n"
            "else:\n"
            '    checks.skip("first-event muon pts", f"{DATA_FILE.name} is not the known 2012C file {KNOWN_FILE}")\n\n'
            "if vector is None:\n"
            '    checks.skip("agreement with vector library", "vector is not installed")\n'
            "else:\n"
            '    v = vector.zip({"pt": p4.pt, "eta": p4.eta, "phi": p4.phi, "mass": p4.mass})\n'
            "    worst = 0.0\n"
            "    ok = True\n"
            "    for ours, theirs in [(px, v.px), (py, v.py), (pz, v.pz), (e, v.E)]:\n"
            "        theirs = flat(theirs)\n"
            "        ok &= bool(np.allclose(ours, theirs, rtol=1e-12, atol=1e-9))\n"
            "        worst = max(worst, float(np.max(np.abs(ours - theirs) / np.maximum(np.abs(theirs), 1e-300))))\n"
            "    checks.check(\n"
            '        f"agreement with vector {vector.__version__} for all muons (px, py, pz, E)",\n'
            "        ok,\n"
            '        f"max relative difference {worst:.3g}",\n'
            "    )\n\n"
            "same = bool(ak.all(ak.num(p4.pt, axis=1) == muons.num)) and len(p4.pt) == len(muons.num)\n"
            'checks.check("p4.pt counts per event equal .num", same, f"{len(muons):,} events compared")\n\n' + FINISH
        ),
    ]
    return _notebook(cells)


def _notebook(cells: list) -> nbformat.NotebookNode:
    for i, cell in enumerate(cells):
        cell.id = f"cell-{i:02d}"  # deterministic ids so rebuilds give identical files
    nb = new_notebook(cells=cells)
    nb.metadata["kernelspec"] = {"name": "python3", "display_name": "Python 3", "language": "python"}
    nb.metadata["language_info"] = {"name": "python"}
    return nb


NOTEBOOKS = {
    "layer1_ingestion.ipynb": layer1,
    "layer2_objects.ipynb": layer2,
}


def main() -> None:
    for name, build in NOTEBOOKS.items():
        nb = build()
        nbformat.validate(nb)
        nbformat.write(nb, HERE / name)
        print(f"wrote {HERE / name}")


if __name__ == "__main__":
    main()
