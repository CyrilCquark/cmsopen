"""Layer 2 demo: build Muon objects and their four-momenta from real CMS data.

Loads the first 100,000 events as a Muon collection, shows the jagged
structure and a per-muon table of kinematics for event 0, then runs
self-checks: the relativistic mass-shell relation for every muon, known
values for the first event, agreement with the `vector` library (if
installed), and structural consistency.

Usage:
    python examples/layer2_objects.py [--file PATH]

Exits 1 if any check fails.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import awkward as ak
import numpy as np

import cmsopen
from cmsopen import Muon, open_events

try:
    import vector
except ImportError:
    vector = None

KNOWN_FILE = "45F7AE81-7A79-4CB1-998E-7BD156490294.root"  # Run2012C DoubleMuParked, see DATA.md
KNOWN_FIRST_PTS = [71.24144, 25.51886, 3.74997]
N_EVENTS = 100_000
# E^2 and |p|^2 are large and nearly equal, so their difference can only be
# exact to a few float64 ulps of E^2: the tolerance is relative to E^2.
SHELL_TOLERANCE = 16 * np.finfo(np.float64).eps


class Checks:
    """Collects self-check results and prints one OK/FAIL/SKIP line each."""

    def __init__(self) -> None:
        self.failures: list[str] = []

    def check(self, name: str, ok: bool, detail: str) -> None:
        print(f"{'OK' if ok else 'FAIL'}: {name} ({detail})")
        if not ok:
            self.failures.append(name)

    def skip(self, name: str, reason: str) -> None:
        print(f"SKIP: {name} ({reason})")


def default_file() -> Path:
    data_dir = Path(__file__).resolve().parents[1] / "data"
    files = sorted(data_dir.glob("*.root"))
    if not files:
        sys.exit(f"error: no .root file in {data_dir}; download one (see DATA.md) or pass --file PATH")
    return files[0]


def flat(x: ak.Array) -> np.ndarray:
    return ak.to_numpy(ak.flatten(x, axis=None))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--file", type=Path, default=None, help="NanoAOD ROOT file (default: first data/*.root)")
    path = parser.parse_args().file or default_file()
    if not path.exists():
        sys.exit(f"error: file not found: {path}")

    print(f"cmsopen imported from: {cmsopen.__file__}")
    print(f"vector library: {vector.__version__ if vector else 'not installed (pip install vector to enable the cross-check)'}")
    print()
    with open_events(path) as events:
        muons = Muon.from_events(events, entry_stop=N_EVENTS)
    p4 = muons.p4

    print(repr(muons))
    print(f"events: {len(muons):,}   muons: {int(ak.sum(muons.num)):,}")
    print(f"muons per event, first 5 events (.num): {muons.num[:5].tolist()}")
    print()

    print("event 0 muons (GeV, radians):")
    columns = {
        "pt": p4.pt[0], "eta": p4.eta[0], "phi": p4.phi[0], "charge": muons.charge[0],
        "E": p4.energy[0], "px": p4.px[0], "py": p4.py[0], "pz": p4.pz[0],
    }
    print("  #  " + "".join(f"{name:>11}" for name in columns))
    for j in range(int(muons.num[0])):
        cells = "".join(
            f"{int(v[j]):>11d}" if name == "charge" else f"{float(v[j]):>11.5f}" for name, v in columns.items()
        )
        print(f"  {j:<3}{cells}")
    print()

    checks = Checks()

    px, py, pz, e = (flat(c) for c in p4.as_cartesian())
    e2 = e**2
    residual = e2 - (px**2 + py**2 + pz**2) - flat(p4.mass) ** 2
    rel = np.abs(residual) / e2
    checks.check(
        f"E^2 - |p|^2 = m^2 for all {len(e):,} muons",
        bool(np.all(rel <= SHELL_TOLERANCE)),
        f"max abs error {np.abs(residual).max():.3g} GeV^2, max error relative to E^2 {rel.max():.3g}, "
        f"tolerance {SHELL_TOLERANCE:.3g}",
    )

    if path.name == KNOWN_FILE:
        pts = p4.pt[0].to_numpy()
        checks.check(
            "first-event muon pts",
            len(pts) == len(KNOWN_FIRST_PTS) and np.allclose(pts, KNOWN_FIRST_PTS, rtol=0, atol=1e-5),
            f"{pts.round(5).tolist()}, expected {KNOWN_FIRST_PTS}",
        )
    else:
        checks.skip("first-event muon pts", f"{path.name} is not the known 2012C file {KNOWN_FILE}")

    if vector is None:
        checks.skip("agreement with vector library", "vector is not installed")
    else:
        v = vector.zip({"pt": p4.pt, "eta": p4.eta, "phi": p4.phi, "mass": p4.mass})
        worst = 0.0
        ok = True
        for ours, theirs in [(px, v.px), (py, v.py), (pz, v.pz), (e, v.E)]:
            theirs = flat(theirs)
            ok &= bool(np.allclose(ours, theirs, rtol=1e-12, atol=1e-9))
            worst = max(worst, float(np.max(np.abs(ours - theirs) / np.maximum(np.abs(theirs), 1e-300))))
        checks.check(
            f"agreement with vector {vector.__version__} for all muons (px, py, pz, E)",
            ok,
            f"max relative difference {worst:.3g}",
        )

    same = bool(ak.all(ak.num(p4.pt, axis=1) == muons.num)) and len(p4.pt) == len(muons.num)
    checks.check("p4.pt counts per event equal .num", same, f"{len(muons):,} events compared")

    if checks.failures:
        print(f"{len(checks.failures)} check(s) failed: {', '.join(checks.failures)}")
        return 1
    print("All checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
