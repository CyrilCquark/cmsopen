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


def layer3() -> nbformat.NotebookNode:
    cells = [
        new_code_cell(LOAD_PATH),
        new_markdown_cell(
            "# Layer 3: selecting Z muons with `cmsopen.selection`\n\n"
            "The raw muon collection is mostly background: soft muons from hadron decays, muons inside jets, "
            "and badly reconstructed candidates. Each cut removes one kind:\n\n"
            "| cut | removes |\n"
            "|---|---|\n"
            "| dimuon trigger (`HLT_Mu17_Mu8` OR `HLT_Mu17_TkMu8`) | events outside a well-understood trigger |\n"
            "| $p_T > 20$ GeV | soft muons from decays and noise; keeps the trigger on its plateau |\n"
            "| $\\lvert\\eta\\rvert < 2.4$ | candidates outside the muon chambers and tracker |\n"
            "| tight ID | punch-through hadrons, decays in flight, poorly measured tracks |\n"
            "| relative isolation $< 0.12$ | muons from b and c decays inside jets |\n"
            "| at least 2 muons | events that cannot contain a $Z\\to\\mu^+\\mu^-$ candidate |\n\n"
            "All cuts are strict: a value exactly at the threshold fails. A `Selection` is immutable and "
            "chainable, and it records a *cutflow*: how many muons and events survive each step."
        ),
        new_code_cell(
            "import awkward as ak\n"
            "import matplotlib.pyplot as plt\n"
            "import numpy as np\n"
            "import uproot\n\n"
            "import cmsopen\n"
            "from cmsopen import invariant_mass, open_events, select_muons\n"
            "from cmsopen.ingestion import DIMUON_TRIGGERS_2012\n\n"
            'print(f"cmsopen imported from: {cmsopen.__file__}")'
        ),
        new_markdown_cell(
            "## The cutflow over all events in the file\n\n"
            "`prev` is the efficiency relative to the previous row (what that cut alone removed), `start` is "
            "relative to row 0. Particle cuts remove muons but not events, so the last column only moves at "
            "the trigger and at `require(>= 2)`."
        ),
        new_code_cell(
            "PT_MIN = 20.0  # GeV\n"
            "ETA_MAX = 2.4\n"
            "ISO_MAX = 0.12\n\n"
            "with open_events(DATA_FILE) as events:\n"
            "    everything = select_muons(events)\n"
            "    triggered = everything.require_trigger(*DIMUON_TRIGGERS_2012)\n"
            "# The particle cuts below are cmsopen.ZMUMU_MUON_CUTS, written out step by step.\n"
            "final = (\n"
            "    triggered\n"
            "    .min_pt(PT_MIN)\n"
            "    .max_eta(ETA_MAX)\n"
            '    .quality_id("tight")\n'
            "    .max_rel_iso(ISO_MAX)\n"
            "    .require(2)\n"
            ")\n"
            "cutflow = final.cutflow()\n"
            "print(repr(final))\n"
            "print()\n"
            "print(cutflow)"
        ),
        new_markdown_cell(
            "## The junk is gone\n\n"
            "The raw collection has candidates far outside the detector ($|\\eta|$ near 12) and with "
            "unphysical momenta. After the selection every muon sits inside the acceptance and above threshold."
        ),
        new_code_cell(
            "raw, sel = everything.particles, final.particles\n"
            "raw_pt, raw_eta = ak.flatten(raw.p4.pt), ak.flatten(raw.p4.eta)\n"
            "sel_pt, sel_eta = ak.flatten(sel.p4.pt), ak.flatten(sel.p4.eta)\n"
            'print(f"  {\'\':12}{\'muons\':>12}{\'max |eta|\':>12}{\'max pt [GeV]\':>15}{\'min pt [GeV]\':>15}")\n'
            'for label, pt, eta in (("before", raw_pt, raw_eta), ("after", sel_pt, sel_eta)):\n'
            '    print(f"  {label:12}{len(pt):>12,}{float(ak.max(abs(eta))):>12.4f}{float(ak.max(pt)):>15.1f}{float(ak.min(pt)):>15.4f}")'
        ),
        new_markdown_cell(
            "## Dimuon mass: full selection vs the crude layer 5 selection\n\n"
            "In each selected event we take the two highest-$p_T$ surviving muons and keep them if their charges "
            "are opposite. (Proper pairing is layer 4; here it is a plain awkward mask.) The *crude* selection is "
            "the one from the layer 5 demo: the two leading muons of all muons, opposite charge, "
            "$p_T > 20$ GeV and $|\\eta| < 2.4$, with no trigger, ID or isolation."
        ),
        new_code_cell(
            "def leading_pair_mass(muons):\n"
            '    """Invariant mass of the two highest-pT muons in each event with opposite charges."""\n'
            "    muons = muons[ak.argsort(muons.p4.pt, axis=1, ascending=False)]\n"
            "    muons = muons[muons.num >= 2]\n"
            "    lead, sub = muons[:, 0], muons[:, 1]\n"
            "    opposite = ak.to_numpy(lead.charge * sub.charge < 0)\n"
            "    return ak.to_numpy(invariant_mass(lead[opposite].p4, sub[opposite].p4))\n\n\n"
            "def crude_layer5_mass(muons):\n"
            '    """The layer 5 demo selection: leading two muons, opposite charge, pt > 20 GeV, |eta| < 2.4."""\n'
            "    muons = muons[ak.argsort(muons.p4.pt, axis=1, ascending=False)]\n"
            "    muons = muons[muons.num >= 2]\n"
            "    lead, sub = muons[:, 0], muons[:, 1]\n"
            "    selected = ak.to_numpy(\n"
            "        (lead.charge * sub.charge < 0)\n"
            "        & (lead.p4.pt > PT_MIN) & (sub.p4.pt > PT_MIN)\n"
            "        & (np.abs(lead.p4.eta) < ETA_MAX) & (np.abs(sub.p4.eta) < ETA_MAX)\n"
            "    )\n"
            "    return ak.to_numpy(invariant_mass(lead[selected].p4, sub[selected].p4))\n\n\n"
            "crude = crude_layer5_mass(raw)\n"
            "selected = leading_pair_mass(sel)\n"
            'print(f"crude layer 5 selection:   {len(crude):,} opposite-charge leading pairs")\n'
            'print(f"full layer 3 selection:    {len(selected):,} opposite-charge leading pairs "\n'
            '      f"(of {final.n_events:,} events with >= 2 selected muons)")\n\n'
            "BINS = np.arange(60.0, 122.0, 2.0)\n"
            "c_counts, edges = np.histogram(crude, bins=BINS)\n"
            "s_counts, _ = np.histogram(selected, bins=BINS)"
        ),
        new_markdown_cell(
            "The upper panel shows both spectra as step histograms. The lower panel is the ratio of the two "
            "counts in each bin. (It is not strictly a survival fraction: the full selection picks its leading "
            "pair after the cuts, so its pairs are not always a subset of the crude ones.) The ratio is highest "
            "under the Z peak and lower in the sidebands, because the trigger, ID and isolation remove "
            "background pairs more than Z pairs."
        ),
        new_code_cell(
            "fig, (ax, rax) = plt.subplots(\n"
            "    2, 1, figsize=(7.5, 6.5), sharex=True, gridspec_kw={\"height_ratios\": [3, 1], \"hspace\": 0.05}\n"
            ")\n"
            'ax.stairs(c_counts, edges, linewidth=1.5, color="tab:gray", label=f"crude layer 5 selection ({int(c_counts.sum()):,} pairs)")\n'
            'ax.stairs(s_counts, edges, linewidth=1.8, color="tab:blue", label=f"full layer 3 selection ({int(s_counts.sum()):,} pairs)")\n'
            'ax.axvline(91.1876, color="tab:red", linestyle="--", linewidth=1, label="PDG Z mass 91.1876 GeV")\n'
            'ax.set_ylabel("Opposite-charge pairs / 2 GeV")\n'
            "ax.set_xlim(edges[0], edges[-1])\n"
            "ax.set_ylim(0, 1.3 * max(c_counts.max(), s_counts.max()))\n"
            'ax.legend(loc="upper right", fontsize=9, frameon=False)\n'
            'ax.text(0.99, 1.01, "CMS Open Data, 2012C DoubleMuParked, 8 TeV", transform=ax.transAxes, ha="right", va="bottom", fontsize=9)\n'
            "with np.errstate(divide=\"ignore\", invalid=\"ignore\"):\n"
            "    ratio = np.where(c_counts > 0, s_counts / c_counts, np.nan)\n"
            'rax.stairs(ratio, edges, baseline=None, color="tab:blue", linewidth=1.5)\n'
            'rax.axvline(91.1876, color="tab:red", linestyle="--", linewidth=1)\n'
            'rax.set_ylabel("full / crude")\n'
            "rax.set_ylim(0, 1)\n"
            'rax.set_xlabel("Dimuon invariant mass $M_{\\\\mu\\\\mu}$ [GeV]")\n'
            "plt.show()"
        ),
        new_markdown_cell(
            "## Self-checks\n\n"
            "1. The cutflow never increases from one row to the next, in any of its three counts.\n"
            "2. Every cutflow number equals an independent recomputation that reads the branches with uproot and "
            "applies the cuts with plain awkward, without calling any cmsopen cut.\n"
            "3. After the cuts, max $|\\eta| < 2.4$ and min $p_T > 20$ GeV.\n"
            "4. After selection, the highest bin between 70 and 110 GeV lies within 88 to 94 GeV.\n"
            "5. Peak fraction: the fraction of 60-120 GeV pairs that lie in 85-97 GeV is higher after the full "
            "selection than for the crude one. This is a rough measure of how concentrated the spectrum is "
            "around the Z, not a true purity, which would need the background under the peak to be modelled "
            "and subtracted."
        ),
        new_code_cell(CHECKS_CLASS),
        new_code_cell(
            "PEAK_SEARCH = (70.0, 110.0)\n"
            "PEAK_WINDOW = (88.0, 94.0)\n"
            "WIDE = (60.0, 120.0)\n"
            "CORE = (85.0, 97.0)\n\n\n"
            "def independent_cutflow(path):\n"
            '    """Recompute every cutflow row with uproot and plain awkward, without cmsopen."""\n'
            "    with uproot.open(path) as f:\n"
            "        a = f[\"Events\"].arrays(\n"
            '            ["Muon_pt", "Muon_eta", "Muon_tightId", "Muon_pfRelIso04_all", *DIMUON_TRIGGERS_2012]\n'
            "        )\n"
            "    fired = np.logical_or.reduce([ak.to_numpy(a[name]) for name in DIMUON_TRIGGERS_2012])\n\n"
            "    def row(mask, events):\n"
            "        per_event = ak.sum(mask, axis=1)[events]\n"
            "        return int(ak.sum(per_event)), int(ak.sum(per_event > 0)), int(np.sum(events))\n\n"
            "    everything = ak.ones_like(a.Muon_pt, dtype=bool)\n"
            "    m_pt = a.Muon_pt > PT_MIN\n"
            "    m_eta = m_pt & (abs(a.Muon_eta) < ETA_MAX)\n"
            "    m_id = m_eta & a.Muon_tightId\n"
            "    m_iso = m_id & (a.Muon_pfRelIso04_all < ISO_MAX)\n"
            "    two = fired & ak.to_numpy(ak.sum(m_iso, axis=1) >= 2)\n"
            "    all_events = np.ones(len(a), dtype=bool)\n"
            "    return [\n"
            "        row(everything, all_events),\n"
            "        row(everything, fired),\n"
            "        row(m_pt, fired),\n"
            "        row(m_eta, fired),\n"
            "        row(m_id, fired),\n"
            "        row(m_iso, fired),\n"
            "        row(m_iso, two),\n"
            "    ]\n\n\n"
            "def fraction_in(mass, inner, outer):\n"
            "    n_outer = int(np.sum((mass >= outer[0]) & (mass < outer[1])))\n"
            "    n_inner = int(np.sum((mass >= inner[0]) & (mass < inner[1])))\n"
            '    return (n_inner / n_outer if n_outer else float("nan")), n_inner, n_outer\n\n\n'
            "checks = Checks()\n"
            "d = cutflow.to_dict()\n"
            'columns = ("n_particles", "n_events_with_particles", "n_events")\n'
            "increases = [(c, i) for c in columns for i in range(1, len(cutflow)) if d[c][i] > d[c][i - 1]]\n"
            "checks.check(\n"
            '    "cutflow is monotonically non-increasing in particles, events with >= 1 particle and events",\n'
            "    not increases,\n"
            '    f"{len(cutflow)} rows; increases found: {increases}" if increases else f"{len(cutflow)} rows x 3 columns",\n'
            ")\n\n"
            "ours = [tuple(d[c][i] for c in columns) for i in range(len(cutflow))]\n"
            "theirs = independent_cutflow(DATA_FILE)\n"
            "pairs = \"; \".join(f\"{d['cut'][i]}: {o[0]:,}/{o[1]:,}/{o[2]:,} vs {t[0]:,}/{t[1]:,}/{t[2]:,}\"\n"
            "                  for i, (o, t) in enumerate(zip(ours, theirs)))\n"
            "checks.check(\n"
            '    "cutflow agrees with an independent uproot + plain awkward recomputation",\n'
            "    ours == theirs,\n"
            '    f"particles/events>=1/events, cmsopen vs independent: {pairs}",\n'
            ")\n\n"
            "max_abs_eta, min_pt = float(ak.max(abs(sel_eta))), float(ak.min(sel_pt))\n"
            "checks.check(\n"
            '    f"after the cuts: max |eta| < {ETA_MAX} and min pt > {PT_MIN:.0f} GeV",\n'
            "    max_abs_eta < ETA_MAX and min_pt > PT_MIN,\n"
            '    f"max |eta| = {max_abs_eta:.4f}, min pt = {min_pt:.4f} GeV over {len(sel_pt):,} muons",\n'
            ")\n\n"
            "in_search = (edges[:-1] >= PEAK_SEARCH[0]) & (edges[1:] <= PEAK_SEARCH[1])\n"
            "peak = int(np.flatnonzero(in_search)[np.argmax(s_counts[in_search])])\n"
            "peak_lo, peak_hi = edges[peak], edges[peak + 1]\n"
            "checks.check(\n"
            '    f"Z peak after selection: highest bin in {PEAK_SEARCH[0]:.0f}-{PEAK_SEARCH[1]:.0f} GeV lies within "\n'
            '    f"{PEAK_WINDOW[0]:.0f}-{PEAK_WINDOW[1]:.0f} GeV",\n'
            "    bool(peak_lo >= PEAK_WINDOW[0] and peak_hi <= PEAK_WINDOW[1]),\n"
            '    f"peak bin {peak_lo:.0f}-{peak_hi:.0f} GeV with {s_counts[peak]:,} pairs",\n'
            ")\n\n"
            "f_sel, n_core_s, n_wide_s = fraction_in(selected, CORE, WIDE)\n"
            "f_crude, n_core_c, n_wide_c = fraction_in(crude, CORE, WIDE)\n"
            "checks.check(\n"
            '    f"peak fraction: fraction of {WIDE[0]:.0f}-{WIDE[1]:.0f} GeV pairs inside {CORE[0]:.0f}-{CORE[1]:.0f} GeV "\n'
            '    "is higher after the full selection than for the crude selection",\n'
            "    f_sel > f_crude,\n"
            '    f"full {f_sel:.4f} ({n_core_s:,}/{n_wide_s:,}) vs crude {f_crude:.4f} ({n_core_c:,}/{n_wide_c:,})",\n'
            ")\n\n" + FINISH
        ),
    ]
    return _notebook(cells)


LAYER4_CHECKS = '''\
PEAK_SEARCH = (70.0, 110.0)
PEAK_WINDOW = (88.0, 94.0)
SS_MAX_FRACTION = 0.10


def independent_pair_counts(path):
    """Recompute the selection and per-event pair counts with uproot and numpy, without cmsopen."""
    with uproot.open(path) as f:
        a = f["Events"].arrays(
            ["Muon_pt", "Muon_eta", "Muon_tightId", "Muon_pfRelIso04_all", "Muon_charge", *DIMUON_TRIGGERS_2012]
        )
    fired = np.logical_or.reduce([ak.to_numpy(a[name]) for name in DIMUON_TRIGGERS_2012])
    good = (a.Muon_pt > 20.0) & (abs(a.Muon_eta) < 2.4) & a.Muon_tightId & (a.Muon_pfRelIso04_all < 0.12)
    n_plus = ak.to_numpy(ak.sum(good & (a.Muon_charge > 0), axis=1))
    n_minus = ak.to_numpy(ak.sum(good & (a.Muon_charge < 0), axis=1))
    n = ak.to_numpy(ak.sum(good, axis=1))
    rows = np.flatnonzero(fired & (n >= 2))
    n_plus, n_minus, n = n_plus[rows], n_minus[rows], n[rows]
    return rows, n_plus * n_minus, n_plus * (n_plus - 1) // 2 + n_minus * (n_minus - 1) // 2, n * (n - 1) // 2


def in_window(mass, window):
    return int(np.sum((mass >= window[0]) & (mass < window[1])))


checks = Checks()
n_os, n_ss, n_all = (ak.to_numpy(p.num) for p in (os_pairs, ss_pairs, every))
bad = np.flatnonzero(n_os + n_ss != n_all)
checks.check(
    "n_OS + n_SS == n_all in every event",
    bad.size == 0,
    f"{len(n_all):,} events; {n_os.sum():,} + {n_ss.sum():,} = {n_all.sum():,}"
    + (f"; mismatches at rows {sel.event_index[bad[:5]].tolist()}" if bad.size else ""),
)

rows, e_os, e_ss, e_all = independent_pair_counts(DATA_FILE)
same = (
    np.array_equal(rows, sel.event_index)
    and np.array_equal(e_os, n_os) and np.array_equal(e_ss, n_ss) and np.array_equal(e_all, n_all)
)
checks.check(
    "pair counts agree with an independent uproot + numpy recomputation, event by event",
    same,
    f"events {len(sel.event_index):,} vs {len(rows):,}; OS {n_os.sum():,} vs {e_os.sum():,}; "
    f"SS {n_ss.sum():,} vs {e_ss.sum():,}; all {n_all.sum():,} vs {e_all.sum():,}",
)

os_q, ss_q = ak.flatten(os_pairs.charge_product), ak.flatten(ss_pairs.charge_product)
checks.check(
    "all OS pairs have charge product -1 and all SS pairs +1",
    bool(ak.all(os_q == -1) and ak.all(ss_q == 1)),
    f"OS products {sorted(set(ak.to_list(os_q)))} over {len(os_q):,} pairs; "
    f"SS products {sorted(set(ak.to_list(ss_q)))} over {len(ss_q):,} pairs",
)

reuse = int(ak.sum(every.index1 == every.index2))
misordered = int(ak.sum(every.leg1.p4.pt < every.leg2.p4.pt))
checks.check(
    "no pair reuses a muon and leg1.pt >= leg2.pt",
    reuse == 0 and misordered == 0,
    f"{every.n_pairs:,} pairs: {reuse} with index1 == index2, {misordered} with leg1.pt < leg2.pt",
)

max_best = int(ak.max(best.num)) if len(best) else 0
checks.check(
    "best_pair returns at most one pair per event",
    max_best <= 1 and len(best) == len(os_pairs),
    f"max {max_best} per event; {int(ak.sum(best.num == 1)):,} events with one pair, "
    f"{int(ak.sum(best.num == 0)):,} with none",
)

in_search = (edges[:-1] >= PEAK_SEARCH[0]) & (edges[1:] <= PEAK_SEARCH[1])
peak = int(np.flatnonzero(in_search)[np.argmax(os_counts[in_search])])
peak_lo, peak_hi = edges[peak], edges[peak + 1]
checks.check(
    f"OS peak: highest bin in {PEAK_SEARCH[0]:.0f}-{PEAK_SEARCH[1]:.0f} GeV lies within "
    f"{PEAK_WINDOW[0]:.0f}-{PEAK_WINDOW[1]:.0f} GeV",
    bool(peak_lo >= PEAK_WINDOW[0] and peak_hi <= PEAK_WINDOW[1]),
    f"peak bin {peak_lo:.0f}-{peak_hi:.0f} GeV with {os_counts[peak]:,} OS pairs",
)

os_win, ss_win = in_window(m_os, PEAK_WINDOW), in_window(m_ss, PEAK_WINDOW)
checks.check(
    f"SS pairs in {PEAK_WINDOW[0]:.0f}-{PEAK_WINDOW[1]:.0f} GeV are fewer than "
    f"{100 * SS_MAX_FRACTION:.0f}% of OS pairs there",
    ss_win < SS_MAX_FRACTION * os_win,
    f"SS {ss_win:,} vs OS {os_win:,} (limit {SS_MAX_FRACTION * os_win:,.1f})",
)

''' + FINISH


def layer4() -> nbformat.NotebookNode:
    cells = [
        new_code_cell(LOAD_PATH),
        new_markdown_cell(
            "# Layer 4: muon pairs with `cmsopen.combinatorics`\n\n"
            "The Z boson is electrically neutral and charge is conserved, so $Z\\to\\mu^+\\mu^-$ always gives "
            "one $\\mu^+$ and one $\\mu^-$: an **opposite-sign (OS)** pair, charge product $q_1 q_2 = -1$. "
            "A **same-sign (SS)** pair has total charge $\\pm 2$ and cannot come from a Z. SS pairs come from "
            "the backgrounds, such as two unrelated muons in one collision or a misidentified hadron, which give "
            "OS and SS pairs at similar rates. The SS spectrum therefore estimates the combinatorial background "
            "under the OS spectrum, and a peak in OS with none in SS shows that the peak is a real neutral particle.\n\n"
            "An event with $n$ muons has $n(n-1)/2$ pairs; with $n_+$ positive and $n_-$ negative muons, "
            "$n_+ n_-$ of them are OS and $n_+(n_+-1)/2 + n_-(n_--1)/2$ are SS. Each pair is ordered so that "
            "`leg1` is the higher-$p_T$ muon (a convention: the mass does not depend on it)."
        ),
        new_code_cell(
            "import awkward as ak\n"
            "import matplotlib.pyplot as plt\n"
            "import numpy as np\n"
            "import uproot\n\n"
            "import cmsopen\n"
            "from cmsopen import (\n"
            "    ZMUMU_MUON_CUTS,\n"
            "    all_pairs,\n"
            "    best_pair,\n"
            "    multiplicity,\n"
            "    open_events,\n"
            "    opposite_sign_pairs,\n"
            "    same_sign_pairs,\n"
            ")\n"
            "from cmsopen.ingestion import DIMUON_TRIGGERS_2012\n\n"
            'print(f"cmsopen imported from: {cmsopen.__file__}")'
        ),
        new_markdown_cell(
            "## Select Z muons and form pairs\n\n"
            "The layer 3 selection on every event of the file: `ZMUMU_MUON_CUTS` ($p_T > 20$ GeV, "
            "$|\\eta| < 2.4$, tight ID, relative isolation $< 0.12$), the dimuon trigger "
            "(`HLT_Mu17_Mu8` OR `HLT_Mu17_TkMu8`) and at least two selected muons. Then every OS pair, every "
            "SS pair and every pair regardless of charge."
        ),
        new_code_cell(
            "with open_events(DATA_FILE) as events:\n"
            "    n_file = events.n_events\n"
            "    sel = events.muons(**ZMUMU_MUON_CUTS).require_trigger(*DIMUON_TRIGGERS_2012).require(2)\n"
            'print(f"{DATA_FILE.name}: {n_file:,} events")\n'
            "print(repr(sel))\n\n"
            "os_pairs, ss_pairs, every = opposite_sign_pairs(sel), same_sign_pairs(sel), all_pairs(sel)\n"
            'best = best_pair(os_pairs, "highest_pt_sum")\n'
            "n_muons = ak.to_numpy(sel.particles.num)\n"
            'print("Selected muons per event:  " + ", ".join(f"{k}: {c:,}" for k, c in enumerate(np.bincount(n_muons)) if c))'
        ),
        new_markdown_cell(
            "## How many candidates per event?\n\n"
            "Only events with two or more candidate pairs need a choice of candidate. `best_pair` with the "
            "default strategy `\"highest_pt_sum\"` keeps the pair with the largest $p_{T,1} + p_{T,2}$. That rule "
            "never looks at the mass. Choosing the pair closest to 91 GeV would instead carve a fake peak out of "
            "background."
        ),
        new_code_cell(
            'for label, pairs in (("opposite-sign", os_pairs), ("same-sign", ss_pairs), ("all", every)):\n'
            '    print(f"Pair multiplicity, {label} pairs:")\n'
            "    print(multiplicity(pairs))\n"
            "    print()\n"
            'print(f"Pair counts: {os_pairs.n_pairs:,} OS + {ss_pairs.n_pairs:,} SS = {every.n_pairs:,} all; "\n'
            '      f"best_pair(OS, highest_pt_sum) keeps {best.n_pairs:,}")'
        ),
        new_markdown_cell(
            "## Mass spectra, 60 to 120 GeV\n\n"
            "OS pairs (all candidates and one per event) and SS pairs, in 2 GeV bins."
        ),
        new_code_cell(
            "m_os = ak.to_numpy(ak.flatten(os_pairs.mass))\n"
            "m_best = ak.to_numpy(ak.flatten(best.mass))\n"
            "m_ss = ak.to_numpy(ak.flatten(ss_pairs.mass))\n"
            "BINS = np.arange(60.0, 122.0, 2.0)\n"
            "os_counts, edges = np.histogram(m_os, bins=BINS)\n"
            "best_counts, _ = np.histogram(m_best, bins=BINS)\n"
            "ss_counts, _ = np.histogram(m_ss, bins=BINS)\n"
            'print(f"  {\'GeV\':11}{\'OS all\':>10}{\'OS best\':>10}{\'SS\':>6}")\n'
            "for lo, hi, a, b, s in zip(edges[:-1], edges[1:], os_counts, best_counts, ss_counts):\n"
            '    print(f"  {lo:5.0f}-{hi:<5.0f}{a:>10,}{b:>10,}{s:>6,}")\n'
            'print(f"  {\'total\':11}{os_counts.sum():>10,}{best_counts.sum():>10,}{ss_counts.sum():>6,}")'
        ),
        new_markdown_cell(
            "OS and SS pairs on the same axes, with a logarithmic vertical scale so that a small SS "
            "contribution would still be visible. After tight ID and isolation the SS sample is tiny: "
            "these cuts remove almost all of the misidentified and non-isolated muons that make same-sign "
            "pairs, so what remains is a nearly background-free Z peak in the OS pairs."
        ),
        new_code_cell(
            "fig, ax = plt.subplots(figsize=(7.5, 5.0))\n"
            'ax.stairs(os_counts, edges, linewidth=1.8, color="tab:blue", label=f"opposite-sign pairs ({int(os_counts.sum()):,})")\n'
            'ax.stairs(ss_counts, edges, linewidth=1.8, color="tab:orange", label=f"same-sign pairs ({int(ss_counts.sum()):,})")\n'
            'ax.axvline(91.1876, color="tab:red", linestyle="--", linewidth=1, label="PDG Z mass 91.1876 GeV")\n'
            'ax.set_yscale("log")\n'
            "ax.set_ylim(0.5, 30 * max(os_counts.max(), 1))\n"
            "ax.set_xlim(edges[0], edges[-1])\n"
            'ax.set_xlabel("Dimuon invariant mass $M_{\\\\mu\\\\mu}$ [GeV]")\n'
            'ax.set_ylabel("Muon pairs / 2 GeV")\n'
            'ax.legend(loc="upper right", fontsize=9, frameon=False)\n'
            'ax.text(0.99, 1.01, "CMS Open Data, 2012C DoubleMuParked, 8 TeV", transform=ax.transAxes, ha="right", va="bottom", fontsize=9)\n'
            "plt.show()"
        ),
        new_markdown_cell(
            "## Self-checks\n\n"
            "1. $n_{OS} + n_{SS} = n_{all}$ in every event.\n"
            "2. The per-event pair counts equal an independent recomputation with uproot and numpy that "
            "selects the muons by hand and counts pairs as $n_+ n_-$ and $n_+(n_+-1)/2 + n_-(n_--1)/2$.\n"
            "3. Every OS pair has charge product $-1$ and every SS pair $+1$.\n"
            "4. No pair uses the same muon twice, and `leg1` always has the higher $p_T$.\n"
            "5. `best_pair` keeps at most one pair per event.\n"
            "6. The highest OS bin between 70 and 110 GeV lies within 88 to 94 GeV.\n"
            "7. SS pairs in 88 to 94 GeV are fewer than 10% of OS pairs there: the peak is made of "
            "opposite-sign pairs."
        ),
        new_code_cell(CHECKS_CLASS),
        new_code_cell(LAYER4_CHECKS),
    ]
    return _notebook(cells)


def layer5() -> nbformat.NotebookNode:
    cells = [
        new_code_cell(LOAD_PATH),
        new_markdown_cell(
            "# Layer 5: a first look at the Z peak with `cmsopen.kinematics`\n\n"
            "Four-momentum is conserved in a decay, so the summed four-vector of the two muons from "
            "$Z\\to\\mu^+\\mu^-$ is the Z four-vector. Its Minkowski length, the invariant mass\n\n"
            "$$M^2 = (E_1+E_2)^2 - |\\vec p_1 + \\vec p_2|^2 \\quad (c = 1),$$\n\n"
            "is the same in every frame and equals the parent's rest mass. Muon pairs from Z decays therefore "
            "pile up near 91.19 GeV, while background pairs spread smoothly.\n\n"
            "**This is not the final analysis.** Selection (layer 3) and pairing (layer 4) do not exist yet, so a "
            "simple selection is written here with plain awkward masks: at least two muons; the two highest-$p_T$ "
            "muons have opposite charge, $p_T > 20$ GeV and $|\\eta| < 2.4$."
        ),
        new_code_cell(
            "import awkward as ak\n"
            "import matplotlib.pyplot as plt\n"
            "import numpy as np\n\n"
            "import cmsopen\n"
            "from cmsopen import FourMomentum, Muon, invariant_mass, open_events\n\n"
            "try:\n"
            "    import vector\n"
            "except ImportError:\n"
            "    vector = None\n\n"
            'print(f"cmsopen imported from: {cmsopen.__file__}")\n'
            "print(f\"vector library: {vector.__version__ if vector else 'not installed (pip install vector to enable the cross-check)'}\")"
        ),
        new_markdown_cell("## Select the leading muon pair in each event"),
        new_code_cell(
            "PT_MIN = 20.0  # GeV\n"
            "ETA_MAX = 2.4\n\n"
            "with open_events(DATA_FILE) as events:\n"
            "    n_total = len(events)\n"
            '    muons = Muon.from_events(events, fields=("pt", "eta", "phi", "mass", "charge"))\n\n'
            "muons = muons[ak.argsort(muons.p4.pt, axis=1, ascending=False)]\n"
            "muons = muons[muons.num >= 2]\n"
            "lead, sub = muons[:, 0], muons[:, 1]\n"
            "selected = (\n"
            "    (lead.charge * sub.charge < 0)\n"
            "    & (lead.p4.pt > PT_MIN) & (sub.p4.pt > PT_MIN)\n"
            "    & (np.abs(lead.p4.eta) < ETA_MAX) & (np.abs(sub.p4.eta) < ETA_MAX)\n"
            ")\n"
            "lead, sub = lead[selected], sub[selected]\n"
            "mass = ak.to_numpy(invariant_mass(lead.p4, sub.p4))\n\n"
            'print(f"events in file:                         {n_total:,}")\n'
            'print(f"events with >= 2 muons:                 {len(muons):,}")\n'
            'print(f"events used (leading pair passes cuts): {len(mass):,}")'
        ),
        new_markdown_cell("## Text histogram, 60 to 120 GeV in 2 GeV bins"),
        new_code_cell(
            "BINS = np.arange(60.0, 122.0, 2.0)\n"
            "counts, edges = np.histogram(mass, bins=BINS)\n"
            'print(f"pairs with 60 <= M < 120 GeV: {int(counts.sum()):,}")\n'
            'print("Dimuon invariant mass (GeV), 2 GeV bins:")\n'
            "scale = 50 / counts.max() if counts.max() else 0\n"
            "for lo, hi, n in zip(edges[:-1], edges[1:], counts):\n"
            "    print(f\"  {lo:5.0f}-{hi:<5.0f} {n:7d} {'#' * int(round(n * scale))}\")"
        ),
        new_markdown_cell(
            "## The same spectrum with matplotlib\n\n"
            "A plain histogram; publication styling comes in layer 7. The peak width combines the Z's natural "
            "width (2.4952 GeV) with the detector's momentum resolution."
        ),
        new_code_cell(
            "fig, ax = plt.subplots(figsize=(7, 4.5))\n"
            'ax.hist(mass, bins=BINS, histtype="step", linewidth=1.5, label="opposite-charge leading muon pairs")\n'
            'ax.axvline(91.1876, color="gray", linestyle="--", linewidth=1, label="PDG Z mass 91.1876 GeV")\n'
            'ax.set_xlabel("Dimuon invariant mass $M_{\\\\mu\\\\mu}$ [GeV]")\n'
            'ax.set_ylabel("Pairs / 2 GeV")\n'
            'ax.set_title("CMS Open Data 2012C DoubleMuParked (first look)")\n'
            "ax.legend()\n"
            "plt.show()"
        ),
        new_markdown_cell(
            "## Self-checks\n\n"
            "1. All masses are finite and non-negative.\n"
            "2. The highest bin between 70 and 110 GeV lies within 88 to 94 GeV: a Z peak is visible.\n"
            "3. A Z at rest decaying to two back-to-back muons gives back 91.1876 GeV.\n"
            "4. The masses agree with the independent `vector` library on the real pairs, if installed."
        ),
        new_code_cell(CHECKS_CLASS),
        new_code_cell(
            "Z_MASS = 91.1876\n"
            "MU_MASS = 0.10566\n"
            "PEAK_SEARCH = (70.0, 110.0)\n"
            "PEAK_WINDOW = (88.0, 94.0)\n\n"
            "checks = Checks()\n"
            "checks.check(\n"
            '    "all masses finite and non-negative",\n'
            "    bool(np.all(np.isfinite(mass)) and np.all(mass >= 0)),\n"
            '    f"{len(mass):,} masses, min {mass.min():.4g} GeV, max {mass.max():.4g} GeV" if len(mass) else "no pairs",\n'
            ")\n\n"
            "in_search = (edges[:-1] >= PEAK_SEARCH[0]) & (edges[1:] <= PEAK_SEARCH[1])\n"
            "peak = int(np.flatnonzero(in_search)[np.argmax(counts[in_search])])\n"
            "peak_lo, peak_hi = edges[peak], edges[peak + 1]\n"
            "checks.check(\n"
            '    f"Z peak: highest bin in {PEAK_SEARCH[0]:.0f}-{PEAK_SEARCH[1]:.0f} GeV lies within "\n'
            '    f"{PEAK_WINDOW[0]:.0f}-{PEAK_WINDOW[1]:.0f} GeV",\n'
            "    bool(peak_lo >= PEAK_WINDOW[0] and peak_hi <= PEAK_WINDOW[1]),\n"
            '    f"peak bin {peak_lo:.0f}-{peak_hi:.0f} GeV with {counts[peak]:,} pairs",\n'
            ")\n\n"
            "p = np.sqrt((Z_MASS / 2) ** 2 - MU_MASS**2)  # two-body decay momentum\n"
            "leg1 = FourMomentum.from_arrays([p], [0.0], [0.0], [MU_MASS])\n"
            "leg2 = FourMomentum.from_arrays([p], [0.0], [np.pi], [MU_MASS])\n"
            "m_rest = float(invariant_mass(leg1, leg2)[0])\n"
            "checks.check(\n"
            '    "Z at rest -> mu+ mu- gives back the Z mass",\n'
            "    abs(m_rest - Z_MASS) <= 1e-9 * Z_MASS,\n"
            '    f"{m_rest:.10f} GeV, expected {Z_MASS}",\n'
            ")\n\n"
            "if vector is None:\n"
            '    checks.skip("agreement with vector library on the real pairs", "vector is not installed")\n'
            "else:\n"
            '    v1, v2 = (vector.zip({"pt": q.pt, "eta": q.eta, "phi": q.phi, "mass": q.mass}) for q in (lead.p4, sub.p4))\n'
            "    theirs = ak.to_numpy((v1 + v2).mass)\n"
            "    rel = np.abs(mass - theirs) / np.maximum(theirs, 1e-300)\n"
            "    checks.check(\n"
            '        f"agreement with vector {vector.__version__} on all {len(mass):,} real pairs",\n'
            "        bool(np.allclose(mass, theirs, rtol=1e-9, atol=1e-9)),\n"
            '        f"max relative difference {rel.max():.3g}",\n'
            "    )\n\n" + FINISH
        ),
    ]
    return _notebook(cells)


LAYER6_CHECKS = r'''checks = Checks()
fits = {m: r for m, r in results.items() if not isinstance(r, Exception)}
finite = {m: bool(np.all(np.isfinite(r.errors)) and np.all(r.errors > 0)) for m, r in fits.items()}
checks.check(
    "both fits converge with finite uncertainties",
    len(fits) == len(MODELS) and all(finite.values()),
    "; ".join(
        f"{m}: " + (f"{len(r.errors)} parameters, max relative error {np.max(r.errors / np.abs(r.values)):.3g}"
                    if m in fits else f"FitError ({r})")
        for m, r in results.items()
    ),
)
for m, r in fits.items():
    c = compare_to_pdg(r)
    checks.check(
        f"{m}: fitted mass within 1.0 GeV of the PDG value (sanity only, not agreement within errors)",
        abs(c.difference) < 1.0,
        f"{c.fitted:.4f} +- {c.fitted_error:.4f} GeV vs PDG {c.pdg_mass:.4f}; offset {c.difference:+.4f} GeV, "
        f"pull {c.pull:+.1f} (statistical error only)",
    )
for m, r in fits.items():
    s, se = r.resolution
    checks.check(f"{m}: fitted resolution between 0.5 and 4 GeV", 0.5 < s < 4.0, f"sigma = {s:.4f} +- {se:.4f} GeV")
for m, r in fits.items():
    checks.check(
        f"{m}: chi2/ndf is finite (reported, no threshold)",
        math.isfinite(r.chi2_ndf),
        f"chi2/ndf = {r.chi2:.1f}/{r.ndf} = {r.chi2_ndf:.3f}, p-value {r.p_value:.3g}",
    )
checks.check(
    "stability spread (std of the fitted mass) is below 0.5 GeV",
    math.isfinite(stability.std) and stability.std < 0.5,
    f"std {stability.std:.4f} GeV over {len(stability.rows)} converged fits ({len(stability.failed)} failed); "
    f"mean {stability.mean:.4f}, range {stability.min:.4f}-{stability.max:.4f} GeV",
)
for m, r in fits.items():
    sy, sye = r.signal_yield
    checks.check(
        f"{m}: signal yield positive and smaller than the number of entries",
        0 < sy < r.n_entries,
        f"signal {sy:,.0f} +- {sye:,.0f} of {r.n_entries:,} entries in {r.fit_range[0]:g}-{r.fit_range[1]:g} GeV",
    )
checks.check(
    "toy pull test: mean within +-0.2 and standard deviation within 0.8-1.2",
    pulls.n_failed == 0 and abs(pulls.mean) < 0.2 and 0.8 < pulls.std < 1.2,
    f"{len(pulls.pulls)} toys, mean {pulls.mean:+.3f}, std {pulls.std:.3f}",
)

''' + FINISH


def layer6() -> nbformat.NotebookNode:
    cells = [
        new_code_cell(LOAD_PATH),
        new_markdown_cell(
            r"""# Layer 6: fitting the Z peak with `cmsopen.fitting`

The dimuon mass spectrum is a **peak** (Z bosons: every $Z\to\mu^+\mu^-$ pair has a mass near the Z mass) on a
smooth, falling **background** (Drell-Yan pairs from a virtual photon, heavy-flavour decays, fakes), which has no
preferred mass. To measure the peak we fit a model with a term for each: a peak plus a polynomial background.

The width of the peak has two sources. The Z is unstable, so its mass is spread over a Breit-Wigner of full width
$\Gamma_Z \approx 2.5$ GeV (the **natural width**). The detector measures each muon momentum with a finite
**resolution**, which smears the mass by a roughly Gaussian $\sigma$ of 1-2 GeV. The two combine by convolution
into a **Voigt** profile. A single Gaussian lumps both into one effective width.

The fit minimises $\chi^2 = \sum (N - \mu)^2/\sigma^2$ over the bins, with Poisson errors $\sigma = \sqrt{N}$
($\sqrt{\max(N,1)}$ so empty bins keep a finite weight), and compares counts with the model integrated over each bin.
$\chi^2/\mathrm{ndf} \approx 1$ and a p-value that is not tiny mean the model describes the data within the
statistical errors; they do not prove it is right. A tiny p-value with 26,000 events says the model misses some
feature of the shape."""
        ),
        new_code_cell(
            r"""import math

import awkward as ak
import matplotlib.pyplot as plt
import numpy as np

import cmsopen
from cmsopen import (
    ZMUMU_MUON_CUTS,
    FitError,
    best_pair,
    compare_to_pdg,
    fit_mass_peak,
    fit_stability,
    make_histogram,
    open_events,
    opposite_sign_pairs,
    same_sign_pairs,
)
from cmsopen.fitting import pdg_mass_width, pull_test
from cmsopen.ingestion import DIMUON_TRIGGERS_2012

print(f"cmsopen imported from: {cmsopen.__file__}")
pdg_mass, pdg_mass_err, pdg_width, pdg_width_err = pdg_mass_width("Z")
print(f"PDG Z (from the particle package): mass {pdg_mass:.4f} +- {pdg_mass_err:.4f} GeV, "
      f"width {pdg_width:.4f} +- {pdg_width_err:.4f} GeV")"""
        ),
        new_markdown_cell(
            r"""## The data: one Z candidate per event

The layer 3 selection (`ZMUMU_MUON_CUTS`, the dimuon trigger, at least two muons), opposite-sign pairs (layer 4)
and one pair per event with `best_pair(..., "highest_pt_sum")`, which never looks at the mass. Masses are
histogrammed in 1 GeV bins over 60-120 GeV."""
        ),
        new_code_cell(
            r"""with open_events(DATA_FILE) as events:
    n_file = events.n_events
    sel = events.muons(**ZMUMU_MUON_CUTS).require_trigger(*DIMUON_TRIGGERS_2012).require(2)
best = best_pair(opposite_sign_pairs(sel), "highest_pt_sum")
masses = best.mass
h = make_histogram(masses, bins=60, range=(60.0, 120.0))
print(f"{DATA_FILE.name}: {n_file:,} events")
print(repr(sel))
print(f"{best.n_pairs:,} opposite-sign pairs (one per event)")
print(repr(h))"""
        ),
        new_markdown_cell(
            r"""## Two fits over 70-110 GeV, each with a quadratic background

`gauss_poly`: Gaussian peak. `voigt_poly`: Voigt peak with the Breit-Wigner half width fixed to $\Gamma_Z/2$ from
the `particle` package, so $\sigma$ is the detector resolution alone. `compare_to_pdg` gives the offset from the PDG
mass and the pull (offset / statistical error). The open data have no muon momentum-scale corrections and the
fitted peak position is not the PDG pole mass, so an offset is expected: it measures systematic effects, not a
disagreement with the PDG."""
        ),
        new_code_cell(
            r"""FIT_RANGE = (70.0, 110.0)
MODELS = {"gauss_poly": "Gaussian + quadratic", "voigt_poly": "Voigt + quadratic"}
results = {}
for model, label in MODELS.items():
    print(f"== {label} ==")
    try:
        r = fit_mass_peak(h, model=model, fit_range=FIT_RANGE, poly_degree=2)
    except FitError as exc:
        print(f"  FitError: {exc}")
        results[model] = exc
        continue
    results[model] = r
    print(r.table())
    print(f"  compare_to_pdg: {compare_to_pdg(r)}")
    print()"""
        ),
        new_markdown_cell(
            r"""### A quick look at the fits

A plain matplotlib figure (publication styling is layer 7): the data with Poisson error bars, each fitted total
curve, each fitted polynomial background (dashed), and the PDG Z mass. Curves are densities multiplied by the 1 GeV
bin width, so they compare directly with the counts."""
        ),
        new_code_cell(
            r"""x = np.linspace(*FIT_RANGE, 801)
fig, ax = plt.subplots(figsize=(8, 5))
ax.errorbar(h.centers, h.counts, yerr=h.errors, xerr=h.widths / 2, fmt="o", ms=3, color="black", label="data")
colors = {"gauss_poly": "tab:blue", "voigt_poly": "tab:orange"}
for model, r in results.items():
    if isinstance(r, Exception):
        continue
    ax.plot(x, r.model(x) * h.widths[0], color=colors[model], label=f"{MODELS[model]}: total")
    ax.plot(x, r.background(x) * h.widths[0], color=colors[model], linestyle="--", label=f"{MODELS[model]}: background")
ax.axvline(pdg_mass, color="tab:red", linestyle=":", label=f"PDG Z mass {pdg_mass:.4f} GeV")
ax.set_xlabel("Dimuon invariant mass [GeV]")
ax.set_ylabel("Pairs / 1 GeV")
ax.set_xlim(60, 120)
ax.legend(fontsize=8)
ax.set_title("CMS Open Data 2012C DoubleMuParked: Z peak fits (quick plot)", fontsize=10)
plt.show()"""
        ),
        new_markdown_cell(
            r"""## How much does the answer depend on the fit choices?

The same masses refitted for every combination of fit range (70-110, 75-105, 80-100 GeV), bin width (0.5, 1,
2 GeV), polynomial degree (1, 2, 3) and peak model: 54 fits. Each choice is defensible, so the spread of the
fitted mass is a rough, honest estimate of the systematic uncertainty from the fit itself. With 2 GeV bins the
75-105 window becomes 76-104 GeV, because only whole bins are fitted. The spread does not cover effects that every
variation shares, such as the muon momentum scale."""
        ),
        new_code_cell(r"""stability = fit_stability(masses)
print(stability)"""),
        new_markdown_cell(
            r"""## Cross-check (report only): same-sign pairs in the sidebands

With the full selection there are almost no same-sign pairs (layer 4). Here a **loose** selection ($p_T > 20$ GeV,
$|\eta| < 2.4$, dimuon trigger, no ID or isolation) keeps more background, and we count all opposite-sign (OS) and
same-sign (SS) pair candidates in the sidebands 60-80 and 100-120 GeV, and under the peak for comparison.

What it shows: SS pairs cannot come from a Z, so they measure the combinatorial and misidentified-muon background.
What it does not show: the rest of the OS sideband pairs is not signal. Drell-Yan pairs and the Z line-shape tails are
real OS pairs with no SS partner, and some backgrounds favour OS. SS/OS is not a background fraction, and these counts
do not test the polynomial in the fit. This is not a pass/fail check."""
        ),
        new_code_cell(
            r"""def count_in(mass, window):
    return int(np.sum((mass >= window[0]) & (mass < window[1])))


with open_events(DATA_FILE) as events:
    loose = events.muons(min_pt=20.0, max_eta=2.4).require_trigger(*DIMUON_TRIGGERS_2012).require(2)
m_os = ak.to_numpy(ak.flatten(opposite_sign_pairs(loose).mass))
m_ss = ak.to_numpy(ak.flatten(same_sign_pairs(loose).mass))
print(repr(loose))
print(f"  {'window [GeV]':<16}{'opposite-sign':>15}{'same-sign':>12}{'SS / OS':>10}")
for lo, hi in ((60.0, 80.0), (100.0, 120.0), (80.0, 100.0)):
    n_os, n_ss = count_in(m_os, (lo, hi)), count_in(m_ss, (lo, hi))
    label = f"{lo:g}-{hi:g}" + (" (peak)" if lo == 80.0 else "")
    print(f"  {label:<16}{n_os:>15,}{n_ss:>12,}{n_ss / n_os:>10.3f}")
os_side = count_in(m_os, (60.0, 80.0)) + count_in(m_os, (100.0, 120.0))
ss_side = count_in(m_ss, (60.0, 80.0)) + count_in(m_ss, (100.0, 120.0))
print(f"  {'both sidebands':<16}{os_side:>15,}{ss_side:>12,}{ss_side / os_side:>10.3f}")"""
        ),
        new_markdown_cell(
            r"""## Are the quoted errors right? A toy pull test

300 toy histograms with known truth (a Gaussian peak at 91.0 GeV, $\sigma = 2$ GeV, on a falling exponential),
Poisson-fluctuated and fitted like the data. If the fit is unbiased and its errors are right, the pulls
(fitted $-$ true) / error have mean 0 and standard deviation 1. A small positive mean (about +0.1) comes from
describing the exponential background with a quadratic: a shift of about 5 MeV, far below the 0.4 GeV offset from
the PDG mass."""
        ),
        new_code_cell(
            r"""pulls = pull_test(n_toys=300)
print(f"{pulls.n_toys} toys, {pulls.n_failed} failed; pull mean {pulls.mean:+.3f}, std {pulls.std:.3f}")"""
        ),
        new_markdown_cell(
            r"""## Self-checks

1. Both fits converge with finite uncertainties.
2. The fitted mass is within 1.0 GeV of the PDG value. This is a sanity check only: the offset and pull are reported,
   and agreement within the statistical errors is not claimed.
3. The fitted resolution is between 0.5 and 4 GeV.
4. $\chi^2/\mathrm{ndf}$ is finite (reported, no threshold).
5. The standard deviation of the fitted mass over the 54 fit choices is below 0.5 GeV.
6. The signal yield is positive and smaller than the number of entries in the fit range.
7. The toy pull test: mean within $\pm 0.2$, standard deviation within 0.8-1.2."""
        ),
        new_code_cell(CHECKS_CLASS),
        new_code_cell(LAYER6_CHECKS),
    ]
    return _notebook(cells)


LAYER7_CHECKS = r"""import re
import struct

from cmsopen.plotting import LAYOUT_DPI, layout_overlaps

MIN_BYTES = 20_000


def png_size(path):
    data = path.read_bytes()[:24]
    return struct.unpack(">II", data[16:24])


def annotated_peak(fig):
    for text in fig.axes[0].texts:
        if text.get_gid() == "annotation":
            m = re.search(r"m_\{\\mathrm\{peak\}\}\$ = ([0-9.]+) \$\\pm\$ ([0-9.]+) GeV", text.get_text())
            return (m.group(1), m.group(2)) if m else None
    return None


checks = Checks()
expected = [outdir / f"{name}.{fmt}" for name, fmts in make_figures.EXPECTED.items() for fmt in fmts]
sizes = {p.name: (p.stat().st_size if p.exists() else 0) for p in expected}
checks.check(
    f"every expected file exists and is larger than {MIN_BYTES:,} bytes",
    all(size > MIN_BYTES for size in sizes.values()),
    ", ".join(f"{name} {size:,}" for name, size in sizes.items()),
)

dims = []
for name, fig in figs.figures.items():
    w_in, h_in = fig.get_size_inches()
    dims.append((name, png_size(outdir / f"{name}.png"), (round(w_in * LAYOUT_DPI), round(h_in * LAYOUT_DPI))))
checks.check(
    f"PNG pixel size equals figsize x {LAYOUT_DPI} dpi",
    all(got == want for _, got, want in dims),
    "; ".join(f"{n} {g[0]}x{g[1]} (expected {w[0]}x{w[1]})" for n, g, w in dims),
)

problems = {name: layout_overlaps(fig) for name, fig in figs.figures.items()}
checks.check(
    "no legend or annotation overlaps data, error bars or curves, and no text is clipped (real-data figures)",
    not any(problems.values()),
    "; ".join(f"{n}: {len(p)} problems" + (f" ({p[0]})" if p else "") for n, p in problems.items()),
)

shown = annotated_peak(figs.figures["z_peak_fit"])
m, me = main_fit.peak_position
if shown is None:
    checks.check("annotated peak position equals the fit to the displayed precision", False, "no peak line found")
else:
    digits = len(shown[0].split(".")[1]) if "." in shown[0] else 0
    checks.check(
        "annotated peak position equals the fit to the displayed precision",
        float(shown[0]) == round(m, digits) and float(shown[1]) == round(me, digits),
        f"annotation {shown[0]} +- {shown[1]} GeV, fit {m:.6f} +- {me:.6f} GeV rounded to {digits} decimals",
    )

again = Path(tempfile.mkdtemp(prefix="cmsopen-figures-again-"))
figs2 = make_figures.write(make_figures.build(DATA_FILE), again)
pairs = [(a, again / a.name) for files in figs.files.values() for a in files]
pairs += [(outdir / n, again / n) for n in ("z_peak_fit_caption.md", "README.md")]
differ = [a.name for a, b in pairs if a.read_bytes() != b.read_bytes()]
checks.check(
    "regenerating every figure from the data gives byte-identical files",
    not differ and len(figs2.files) == len(figs.files),
    f"{len(pairs) - len(differ)} of {len(pairs)} files identical" + (f"; differ: {differ}" if differ else ""),
)

""" + FINISH


def layer7() -> nbformat.NotebookNode:
    cells = [
        new_code_cell(LOAD_PATH),
        new_markdown_cell(
            r"""# Layer 7: publication-quality figures with `cmsopen.plotting`

How the figures are drawn, and why:

* **Data are points with error bars, models are lines.** A bin count is a Poisson measurement with uncertainty
  $\sqrt{N}$; a fitted model is a smooth prediction with no fluctuation of its own.
* **The bin width is in the y label** ("Events / 1 GeV"): without it a count cannot be compared with another binning.
* **Signal and background are drawn separately**: the dashed background and the shaded signal show how the fit
  splits each bin, and make an unphysical background visible.
* **A pull panel** shows (data $-$ fit) / $\sigma$ per bin: if the model is right these scatter around 0 with unit
  spread; a run of same-sign pulls points to a missing feature (here, the radiative tail below the Z).
* **The PDG mass is a reference line**, read from the `particle` package. The fit never uses it.
* **"Unofficial analysis of CMS Open Data"**: these are real CMS data, but this is not a CMS result.

The style is plain matplotlib: STIX serif fonts, inward ticks on all sides, the Okabe-Ito colour-blind-safe palette
with distinct line styles (readable in grayscale), editable text in PDF and 300 dpi PNGs. Legends and annotations
are placed by measuring them and the data with the renderer, so they never cover data."""
        ),
        new_code_cell(
            r"""import sys
import tempfile
from pathlib import Path

from IPython.display import Image, display

import cmsopen

sys.path.insert(0, str(Path.cwd()))  # the notebook runs in examples/, next to make_figures.py
import make_figures

print(f"cmsopen imported from: {cmsopen.__file__}")"""
        ),
        new_markdown_cell(
            r"""## Build every figure from the real file

`make_figures.build` runs the whole chain (selection, opposite-sign pairs, `best_pair`, both fits) and
`make_figures.write` saves the figures, a caption and a README into a new temporary directory: the same files that
`python examples/make_figures.py` writes to the untracked `build/figures/`."""
        ),
        new_code_cell(
            r"""outdir = Path(tempfile.mkdtemp(prefix="cmsopen-figures-"))
figs = make_figures.write(make_figures.build(DATA_FILE), outdir)
print(f"Figures written to {outdir}:")
for files in figs.files.values():
    for f in files:
        print(f"  {f.name:<20} {f.stat().st_size:>9,} bytes")
main_fit = figs.fits[make_figures.MAIN_MODEL]
print()
print(main_fit.table())"""
        ),
        new_markdown_cell(
            r"""## The Z peak with its fit

A Voigt peak (natural width fixed, Gaussian resolution free) on a quadratic background, fitted over 70-110 GeV.
Both fits' backgrounds dip below zero near 110 GeV, so the annotation does not quote yields. The pulls show the
radiative tail: a run of positive pulls at 83-87 GeV that the symmetric peak cannot describe."""
        ),
        new_code_cell(r"""display(Image(filename=str(outdir / "z_peak_fit.png"), width=640))"""),
        new_markdown_cell(
            r"""## Opposite-sign vs same-sign pairs

A loose selection (no ID, no isolation) keeps enough background to see it: same-sign pairs, which cannot come from
a Z, form a smooth, falling spectrum with no peak, while the opposite-sign pairs show the Z."""
        ),
        new_code_cell(r"""display(Image(filename=str(outdir / "z_os_vs_ss.png"), width=640))"""),
        new_markdown_cell(
            r"""## Muon $p_T$ and $\eta$, before and after the selection

All muons in the file (dashed) against the muons that pass the selection (solid). The raw collection reaches
$|\eta| \approx 12$, far outside the detector; after the cuts every muon is inside $|\eta| < 2.4$ and above 20 GeV,
and the selected $p_T$ spectrum peaks near $m_Z/2 \approx 45$ GeV."""
        ),
        new_code_cell(
            r"""display(Image(filename=str(outdir / "muon_pt.png"), width=640))
display(Image(filename=str(outdir / "muon_eta.png"), width=640))"""
        ),
        new_markdown_cell(r"""## The cutflow"""),
        new_code_cell(r"""display(Image(filename=str(outdir / "cutflow.png"), width=640))"""),
        new_markdown_cell(
            r"""## Self-checks

1. Every expected file exists and is larger than 20 kB.
2. Each PNG has exactly figsize $\times$ 300 dpi pixels.
3. On the real-data figures, no legend or annotation overlaps the data points, error bars or curves, and no text is
   clipped by the figure edge (measured with the renderer).
4. The peak position printed in the annotation equals the fitted value to the displayed precision.
5. Regenerating every figure from the data gives byte-identical files."""
        ),
        new_code_cell(CHECKS_CLASS),
        new_code_cell(LAYER7_CHECKS),
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
    "layer3_selection.ipynb": layer3,
    "layer4_combinatorics.ipynb": layer4,
    "layer5_kinematics.ipynb": layer5,
    "layer6_fitting.ipynb": layer6,
    "layer7_plotting.ipynb": layer7,
}


def main() -> None:
    for name, build in NOTEBOOKS.items():
        nb = build()
        nbformat.validate(nb)
        nbformat.write(nb, HERE / name)
        print(f"wrote {HERE / name}")


if __name__ == "__main__":
    main()
