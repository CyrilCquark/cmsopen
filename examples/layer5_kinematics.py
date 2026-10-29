"""Layer 5 demo: a first look at the dimuon invariant mass with cmsopen.kinematics.

This is NOT the final analysis: selection (layer 3) and pairing (layer 4)
are not built yet, so a simple selection is written here with plain
awkward masks. Events need at least two muons; the two highest-pT muons
must have opposite charge, pt > 20 GeV and |eta| < 2.4. Their invariant
mass is histogrammed from 60 to 120 GeV, where the Z boson peak appears.

Usage:
    python examples/layer5_kinematics.py [--file PATH]

Exits 1 if any check fails.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import awkward as ak
import numpy as np

import cmsopen
from cmsopen import FourMomentum, Muon, invariant_mass, open_events

try:
    import vector
except ImportError:
    vector = None

Z_MASS = 91.1876  # PDG, GeV
MU_MASS = 0.10566  # GeV
PT_MIN = 20.0  # GeV
ETA_MAX = 2.4
BINS = np.arange(60.0, 122.0, 2.0)  # 60-120 GeV in 2 GeV bins
PEAK_SEARCH = (70.0, 110.0)
PEAK_WINDOW = (88.0, 94.0)


class Checks:
    """Collects self-check results and prints one OK/FAIL/SKIP line each."""

    def __init__(self) -> None:
        self.failures: list[str] = []

    def check(self, name: str, ok: bool, detail: str) -> None:
        """Print one OK or FAIL line and remember failures."""
        print(f"{'OK' if ok else 'FAIL'}: {name} ({detail})")
        if not ok:
            self.failures.append(name)

    def skip(self, name: str, reason: str) -> None:
        """Print one SKIP line (a check that cannot run here)."""
        print(f"SKIP: {name} ({reason})")


def default_file() -> Path:
    """The first ROOT file in the repository's data/ directory (exits with a message if there is none)."""
    data_dir = Path(__file__).resolve().parents[1] / "data"
    files = sorted(data_dir.glob("*.root"))
    if not files:
        sys.exit(f"error: no .root file in {data_dir}; download one (see DATA.md) or pass --file PATH")
    return files[0]


def main() -> int:
    """Parse the command line, run the demo or tool, and return the exit status."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--file", type=Path, default=None, help="NanoAOD ROOT file (default: first data/*.root)")
    path = parser.parse_args().file or default_file()
    if not path.exists():
        sys.exit(f"error: file not found: {path}")

    print(f"cmsopen imported from: {cmsopen.__file__}")
    status = vector.__version__ if vector else "not installed"
    print(f"vector library: {status} (pip install vector to enable the cross-check)")
    print()

    with open_events(path) as events:
        n_total = len(events)
        muons = Muon.from_events(events, fields=("pt", "eta", "phi", "mass", "charge"))

    # Demo-only selection with plain awkward masks (layers 3 and 4 will replace this).
    muons = muons[ak.argsort(muons.p4.pt, axis=1, ascending=False)]
    muons = muons[muons.num >= 2]
    lead, sub = muons[:, 0], muons[:, 1]
    selected = (
        (lead.charge * sub.charge < 0)
        & (lead.p4.pt > PT_MIN)
        & (sub.p4.pt > PT_MIN)
        & (np.abs(lead.p4.eta) < ETA_MAX)
        & (np.abs(sub.p4.eta) < ETA_MAX)
    )
    lead, sub = lead[selected], sub[selected]
    mass = ak.to_numpy(invariant_mass(lead.p4, sub.p4))

    print(f"events in file:                         {n_total:,}")
    print(f"events with >= 2 muons:                 {len(muons):,}")
    print(f"events used (leading pair passes cuts): {len(mass):,}")
    counts, edges = np.histogram(mass, bins=BINS)
    print(f"pairs with 60 <= M < 120 GeV:           {int(counts.sum()):,}")
    print()

    print("Dimuon invariant mass (GeV), 2 GeV bins:")
    scale = 50 / counts.max() if counts.max() else 0
    for lo, hi, n in zip(edges[:-1], edges[1:], counts, strict=False):
        print(f"  {lo:5.0f}-{hi:<5.0f} {n:7d} {'#' * int(round(n * scale))}")
    print()

    checks = Checks()
    checks.check(
        "all masses finite and non-negative",
        bool(np.all(np.isfinite(mass)) and np.all(mass >= 0)),
        f"{len(mass):,} masses, min {mass.min():.4g} GeV, max {mass.max():.4g} GeV" if len(mass) else "no pairs",
    )

    in_search = (edges[:-1] >= PEAK_SEARCH[0]) & (edges[1:] <= PEAK_SEARCH[1])
    peak = int(np.flatnonzero(in_search)[np.argmax(counts[in_search])])
    peak_lo, peak_hi = edges[peak], edges[peak + 1]
    checks.check(
        f"Z peak: highest bin in {PEAK_SEARCH[0]:.0f}-{PEAK_SEARCH[1]:.0f} GeV lies within "
        f"{PEAK_WINDOW[0]:.0f}-{PEAK_WINDOW[1]:.0f} GeV",
        bool(peak_lo >= PEAK_WINDOW[0] and peak_hi <= PEAK_WINDOW[1]),
        f"peak bin {peak_lo:.0f}-{peak_hi:.0f} GeV with {counts[peak]:,} pairs",
    )

    p = np.sqrt((Z_MASS / 2) ** 2 - MU_MASS**2)  # two-body decay momentum
    leg1 = FourMomentum.from_arrays([p], [0.0], [0.0], [MU_MASS])
    leg2 = FourMomentum.from_arrays([p], [0.0], [np.pi], [MU_MASS])
    m_rest = float(invariant_mass(leg1, leg2)[0])
    checks.check(
        "Z at rest -> mu+ mu- gives back the Z mass",
        abs(m_rest - Z_MASS) <= 1e-9 * Z_MASS,
        f"{m_rest:.10f} GeV, expected {Z_MASS}",
    )

    if vector is None:
        checks.skip("agreement with vector library on the real pairs", "vector is not installed")
    else:
        v1, v2 = (vector.zip({"pt": q.pt, "eta": q.eta, "phi": q.phi, "mass": q.mass}) for q in (lead.p4, sub.p4))
        theirs = ak.to_numpy((v1 + v2).mass)
        rel = np.abs(mass - theirs) / np.maximum(theirs, 1e-300)
        checks.check(
            f"agreement with vector {vector.__version__} on all {len(mass):,} real pairs",
            bool(np.allclose(mass, theirs, rtol=1e-9, atol=1e-9)),
            f"max relative difference {rel.max():.3g}",
        )

    if checks.failures:
        print(f"{len(checks.failures)} check(s) failed: {', '.join(checks.failures)}")
        return 1
    print("All checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
