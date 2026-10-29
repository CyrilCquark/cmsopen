"""Layer 1 demo: open a real CMS NanoAOD file and read raw branches.

Shows the file summary, the raw muons of the first three events, and the
fraction of events that fired a 2012 double-muon trigger, then runs
self-checks against numbers measured on the 2012C DoubleMuParked file.

Usage:
    python examples/layer1_ingestion.py [--file PATH]

Exits 1 if any check fails.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

import cmsopen
from cmsopen import open_events
from cmsopen.ingestion import DIMUON_TRIGGERS_2012

KNOWN_FILE = "45F7AE81-7A79-4CB1-998E-7BD156490294.root"  # Run2012C DoubleMuParked, see DATA.md
KNOWN_N_EVENTS = 396_766
KNOWN_FIRST_PTS = [71.24144, 25.51886, 3.74997]
KNOWN_TRIGGER_FRACTION = 0.5212
N_TRIGGER_EVENTS = 100_000


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
    print()
    with open_events(path) as events:
        print(events.summary())
        print()

        muons = events.muons(entry_stop=3)
        for i in range(3):
            print(f"event {i}: Muon_pt     = {muons.pt[i].to_numpy().astype(float).round(5).tolist()}")
            print(f"         Muon_charge = {muons.charge[i].tolist()}")
        print()

        fired = events.trigger(*DIMUON_TRIGGERS_2012, entry_stop=N_TRIGGER_EVENTS)
        fraction = float(fired.mean())
        print(
            f"Dimuon trigger ({' OR '.join(DIMUON_TRIGGERS_2012)}) fraction, "
            f"first {len(fired):,} events: {fraction:.4f}"
        )
        print()

        checks = Checks()
        if path.name != KNOWN_FILE:
            reason = f"{path.name} is not the known 2012C file {KNOWN_FILE}"
            checks.skip("event count", reason)
            checks.skip("first-event muon pts", reason)
            checks.skip("dimuon trigger fraction", reason)
        else:
            checks.check("event count", len(events) == KNOWN_N_EVENTS, f"{len(events):,}, expected {KNOWN_N_EVENTS:,}")
            pts = muons.pt[0].to_numpy().astype(float)
            checks.check(
                "first-event muon pts",
                len(pts) == len(KNOWN_FIRST_PTS) and np.allclose(pts, KNOWN_FIRST_PTS, rtol=0, atol=1e-5),
                f"{pts.round(5).tolist()}, expected {KNOWN_FIRST_PTS}",
            )
            checks.check(
                "dimuon trigger fraction",
                abs(fraction - KNOWN_TRIGGER_FRACTION) <= 0.002,
                f"{fraction:.4f}, expected {KNOWN_TRIGGER_FRACTION} +/- 0.002",
            )

    if checks.failures:
        print(f"{len(checks.failures)} check(s) failed: {', '.join(checks.failures)}")
        return 1
    print("All checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
