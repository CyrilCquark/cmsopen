"""Layer 4 demo: opposite- and same-sign muon pairs with cmsopen.combinatorics.

Selects Z -> mu+ mu- muons in every event of the file (dimuon trigger,
cmsopen.ZMUMU_MUON_CUTS, at least two muons), forms every opposite-sign
(OS) and same-sign (SS) pair, and prints the pair multiplicity, the pair
counts and the 60-120 GeV mass spectra of OS pairs (all candidates and
one per event with best_pair "highest_pt_sum") and SS pairs. A Z is
neutral, so it gives only OS pairs; SS pairs measure the combinatorial
background, and a peak in OS with none in SS shows the peak is real.

Usage:
    python examples/layer4_combinatorics.py [--file PATH]

Exits 1 if any check fails.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import awkward as ak
import numpy as np
import uproot

import cmsopen
from cmsopen import (
    ZMUMU_MUON_CUTS,
    all_pairs,
    best_pair,
    multiplicity,
    open_events,
    opposite_sign_pairs,
    same_sign_pairs,
)
from cmsopen.ingestion import DIMUON_TRIGGERS_2012

Z_MASS = 91.1876  # PDG, GeV
BINS = np.arange(60.0, 122.0, 2.0)  # 60-120 GeV in 2 GeV bins
PEAK_SEARCH = (70.0, 110.0)
PEAK_WINDOW = (88.0, 94.0)
SS_MAX_FRACTION = 0.10


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


def independent_pair_counts(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Recompute the selection and the per-event pair counts with uproot and numpy, without cmsopen.

    For n+ positive and n- negative selected muons, an event has n+ * n-
    opposite-sign pairs, n+(n+ - 1)/2 + n-(n- - 1)/2 same-sign pairs and
    n(n-1)/2 pairs in all. Returns (file rows, n_OS, n_SS, n_all) for the
    selected events.
    """
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


def text_histograms(spectra: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    """Print the mass spectra as a text histogram and return the bin counts."""
    counts = {label: np.histogram(m, bins=BINS)[0] for label, m in spectra.items()}
    labels = list(counts)
    print("Dimuon invariant mass (GeV), 2 GeV bins   [# = " + labels[0] + "]")
    print(f"  {'':11}" + "".join(f"{label:>18}" for label in labels))
    first = counts[labels[0]]
    scale = 40 / first.max() if first.max() else 0
    for i, (lo, hi) in enumerate(zip(BINS[:-1], BINS[1:], strict=False)):
        row = "".join(f"{counts[label][i]:>18,}" for label in labels)
        print(f"  {lo:5.0f}-{hi:<5.0f}{row}  {'#' * int(round(first[i] * scale))}")
    print(f"  {'total':11}" + "".join(f"{int(c.sum()):>18,}" for c in counts.values()))
    return counts


def in_window(mass: np.ndarray, window: tuple[float, float]) -> int:
    """Number of masses in the half-open window [low, high)."""
    return int(np.sum((mass >= window[0]) & (mass < window[1])))


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
        n_file = events.n_events
        sel = events.muons(**ZMUMU_MUON_CUTS).require_trigger(*DIMUON_TRIGGERS_2012).require(2)
    print(f"{path.name}: {n_file:,} events")
    print(repr(sel))
    print()

    os_pairs, ss_pairs, every = opposite_sign_pairs(sel), same_sign_pairs(sel), all_pairs(sel)
    best = best_pair(os_pairs, "highest_pt_sum")
    n_muons = ak.to_numpy(sel.particles.num)
    print("Selected muons per event:  " + ", ".join(f"{k}: {c:,}" for k, c in enumerate(np.bincount(n_muons)) if c))
    print()
    for label, pairs in (("opposite-sign", os_pairs), ("same-sign", ss_pairs), ("all", every)):
        print(f"Pair multiplicity, {label} pairs:")
        print(multiplicity(pairs))
        print()
    print(f"Pair counts: {os_pairs.n_pairs:,} OS + {ss_pairs.n_pairs:,} SS = {every.n_pairs:,} all; "
          f"best_pair(OS, highest_pt_sum) keeps {best.n_pairs:,} (one in each event with an OS pair)")
    print()

    m_os = ak.to_numpy(ak.flatten(os_pairs.mass))
    m_best = ak.to_numpy(ak.flatten(best.mass))
    m_ss = ak.to_numpy(ak.flatten(ss_pairs.mass))
    counts = text_histograms({"OS all candidates": m_os, "OS best_pair": m_best, "SS": m_ss})
    print()

    checks = Checks()
    n_os, n_ss, n_all = (ak.to_numpy(p.num) for p in (os_pairs, ss_pairs, every))
    bad = np.flatnonzero(n_os + n_ss != n_all)
    checks.check(
        "n_OS + n_SS == n_all in every event",
        bad.size == 0,
        f"{len(n_all):,} events; {n_os.sum():,} + {n_ss.sum():,} = {n_all.sum():,}"
        + (f"; mismatches at rows {sel.event_index[bad[:5]].tolist()}" if bad.size else ""),
    )

    rows, e_os, e_ss, e_all = independent_pair_counts(path)
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

    os_counts = counts["OS all candidates"]
    in_search = (BINS[:-1] >= PEAK_SEARCH[0]) & (BINS[1:] <= PEAK_SEARCH[1])
    peak = int(np.flatnonzero(in_search)[np.argmax(os_counts[in_search])])
    peak_lo, peak_hi = BINS[peak], BINS[peak + 1]
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

    if checks.failures:
        print(f"{len(checks.failures)} check(s) failed: {', '.join(checks.failures)}")
        return 1
    print("All checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
