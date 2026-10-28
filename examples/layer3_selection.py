"""Layer 3 demo: muon selection and its cutflow with cmsopen.selection.

Applies the Z -> mu+ mu- selection to every event of the file, step by
step: dimuon trigger, pt > 20 GeV, |eta| < 2.4, tight ID, relative isolation
< 0.12, and at least two surviving muons. Prints the cutflow, shows that
the junk in the raw collection is gone, and compares the dimuon mass
spectrum of the two leading opposite-charge muons with the crude layer 5
selection. Pairing proper is layer 4, so the opposite-charge requirement
here is a plain awkward mask.

Usage:
    python examples/layer3_selection.py [--file PATH]

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
from cmsopen import invariant_mass, open_events, select_muons
from cmsopen.ingestion import DIMUON_TRIGGERS_2012

Z_MASS = 91.1876  # PDG, GeV
PT_MIN = 20.0  # GeV
ETA_MAX = 2.4
ISO_MAX = 0.12
BINS = np.arange(60.0, 122.0, 2.0)  # 60-120 GeV in 2 GeV bins
PEAK_SEARCH = (70.0, 110.0)
PEAK_WINDOW = (88.0, 94.0)
WIDE = (60.0, 120.0)
CORE = (85.0, 97.0)


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


def leading_pair_mass(muons) -> np.ndarray:
    """Invariant mass of the two highest-pT muons in each event with opposite charges."""
    muons = muons[ak.argsort(muons.p4.pt, axis=1, ascending=False)]
    muons = muons[muons.num >= 2]
    lead, sub = muons[:, 0], muons[:, 1]
    opposite = ak.to_numpy(lead.charge * sub.charge < 0)
    return ak.to_numpy(invariant_mass(lead[opposite].p4, sub[opposite].p4))


def crude_layer5_mass(muons) -> np.ndarray:
    """The layer 5 demo selection: leading two muons, opposite charge, pt > 20 GeV, |eta| < 2.4."""
    muons = muons[ak.argsort(muons.p4.pt, axis=1, ascending=False)]
    muons = muons[muons.num >= 2]
    lead, sub = muons[:, 0], muons[:, 1]
    selected = ak.to_numpy(
        (lead.charge * sub.charge < 0)
        & (lead.p4.pt > PT_MIN) & (sub.p4.pt > PT_MIN)
        & (np.abs(lead.p4.eta) < ETA_MAX) & (np.abs(sub.p4.eta) < ETA_MAX)
    )
    return ak.to_numpy(invariant_mass(lead[selected].p4, sub[selected].p4))


def independent_cutflow(path: Path) -> list[tuple[int, int, int]]:
    """Recompute every cutflow row with uproot and plain awkward, without cmsopen.

    Returns (particles, events with >= 1 particle, events) per row.
    """
    with uproot.open(path) as f:
        a = f["Events"].arrays(
            ["Muon_pt", "Muon_eta", "Muon_tightId", "Muon_pfRelIso04_all", *DIMUON_TRIGGERS_2012]
        )
    fired = np.logical_or.reduce([ak.to_numpy(a[name]) for name in DIMUON_TRIGGERS_2012])

    def row(mask, events):
        per_event = ak.sum(mask, axis=1)[events]
        return int(ak.sum(per_event)), int(ak.sum(per_event > 0)), int(np.sum(events))

    everything = ak.ones_like(a.Muon_pt, dtype=bool)
    m_pt = a.Muon_pt > PT_MIN
    m_eta = m_pt & (abs(a.Muon_eta) < ETA_MAX)
    m_id = m_eta & a.Muon_tightId
    m_iso = m_id & (a.Muon_pfRelIso04_all < ISO_MAX)
    two = fired & ak.to_numpy(ak.sum(m_iso, axis=1) >= 2)
    all_events = np.ones(len(a), dtype=bool)
    return [
        row(everything, all_events),
        row(everything, fired),
        row(m_pt, fired),
        row(m_eta, fired),
        row(m_id, fired),
        row(m_iso, fired),
        row(m_iso, two),
    ]


def text_histograms(crude: np.ndarray, selected: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    c_counts, edges = np.histogram(crude, bins=BINS)
    s_counts, _ = np.histogram(selected, bins=BINS)
    print("Dimuon invariant mass (GeV), 2 GeV bins:  crude (layer 5) vs full selection   [# = selected]")
    scale = 40 / s_counts.max() if s_counts.max() else 0
    for lo, hi, c, s in zip(edges[:-1], edges[1:], c_counts, s_counts):
        print(f"  {lo:5.0f}-{hi:<5.0f} {c:7d} {s:7d}  {'#' * int(round(s * scale))}")
    return c_counts, s_counts, edges


def fraction_in(mass: np.ndarray, inner: tuple[float, float], outer: tuple[float, float]) -> tuple[float, int, int]:
    n_outer = int(np.sum((mass >= outer[0]) & (mass < outer[1])))
    n_inner = int(np.sum((mass >= inner[0]) & (mass < inner[1])))
    return (n_inner / n_outer if n_outer else float("nan")), n_inner, n_outer


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--file", type=Path, default=None, help="NanoAOD ROOT file (default: first data/*.root)")
    path = parser.parse_args().file or default_file()
    if not path.exists():
        sys.exit(f"error: file not found: {path}")

    print(f"cmsopen imported from: {cmsopen.__file__}")
    print()

    with open_events(path) as events:
        everything = select_muons(events)
        triggered = everything.require_trigger(*DIMUON_TRIGGERS_2012)
    # The particle cuts below are cmsopen.ZMUMU_MUON_CUTS, written out step by step.
    final = (
        triggered
        .min_pt(PT_MIN)
        .max_eta(ETA_MAX)
        .quality_id("tight")
        .max_rel_iso(ISO_MAX)
        .require(2)
    )
    cutflow = final.cutflow()
    print(f"Cutflow on {path.name}:")
    print(cutflow)
    print()

    raw, sel = everything.particles, final.particles
    raw_pt, raw_eta = ak.flatten(raw.p4.pt), ak.flatten(raw.p4.eta)
    sel_pt, sel_eta = ak.flatten(sel.p4.pt), ak.flatten(sel.p4.eta)
    print("Junk removed (all muons in the file vs muons after the full selection):")
    print(f"  {'':12}{'muons':>12}{'max |eta|':>12}{'max pt [GeV]':>15}{'min pt [GeV]':>15}")
    for label, pt, eta in (("before", raw_pt, raw_eta), ("after", sel_pt, sel_eta)):
        print(f"  {label:12}{len(pt):>12,}{float(ak.max(abs(eta))):>12.4f}{float(ak.max(pt)):>15.1f}{float(ak.min(pt)):>15.4f}")
    print()

    crude = crude_layer5_mass(raw)
    selected = leading_pair_mass(sel)
    print(f"crude layer 5 selection:   {len(crude):,} opposite-charge leading pairs")
    print(f"full layer 3 selection:    {len(selected):,} opposite-charge leading pairs "
          f"(of {final.n_events:,} events with >= 2 selected muons)")
    c_counts, s_counts, edges = text_histograms(crude, selected)
    print()

    checks = Checks()
    d = cutflow.to_dict()
    columns = ("n_particles", "n_events_with_particles", "n_events")
    increases = [(c, i) for c in columns for i in range(1, len(cutflow)) if d[c][i] > d[c][i - 1]]
    checks.check(
        "cutflow is monotonically non-increasing in particles, events with >= 1 particle and events",
        not increases,
        f"{len(cutflow)} rows; increases found: {increases}" if increases else f"{len(cutflow)} rows x 3 columns",
    )

    ours = [tuple(d[c][i] for c in columns) for i in range(len(cutflow))]
    theirs = independent_cutflow(path)
    pairs = "; ".join(f"{d['cut'][i]}: {o[0]:,}/{o[1]:,}/{o[2]:,} vs {t[0]:,}/{t[1]:,}/{t[2]:,}"
                      for i, (o, t) in enumerate(zip(ours, theirs)))
    checks.check(
        "cutflow agrees with an independent uproot + plain awkward recomputation",
        ours == theirs,
        f"particles/events>=1/events, cmsopen vs independent: {pairs}",
    )

    max_eta, min_pt = float(ak.max(abs(sel_eta))), float(ak.min(sel_pt))
    checks.check(
        f"after the cuts: max |eta| < {ETA_MAX} and min pt > {PT_MIN:.0f} GeV",
        max_eta < ETA_MAX and min_pt > PT_MIN,
        f"max |eta| = {max_eta:.4f}, min pt = {min_pt:.4f} GeV over {len(sel_pt):,} muons",
    )

    in_search = (edges[:-1] >= PEAK_SEARCH[0]) & (edges[1:] <= PEAK_SEARCH[1])
    peak = int(np.flatnonzero(in_search)[np.argmax(s_counts[in_search])])
    peak_lo, peak_hi = edges[peak], edges[peak + 1]
    checks.check(
        f"Z peak after selection: highest bin in {PEAK_SEARCH[0]:.0f}-{PEAK_SEARCH[1]:.0f} GeV lies within "
        f"{PEAK_WINDOW[0]:.0f}-{PEAK_WINDOW[1]:.0f} GeV",
        bool(peak_lo >= PEAK_WINDOW[0] and peak_hi <= PEAK_WINDOW[1]),
        f"peak bin {peak_lo:.0f}-{peak_hi:.0f} GeV with {s_counts[peak]:,} pairs",
    )

    f_sel, n_core_s, n_wide_s = fraction_in(selected, CORE, WIDE)
    f_crude, n_core_c, n_wide_c = fraction_in(crude, CORE, WIDE)
    checks.check(
        f"purity: fraction of {WIDE[0]:.0f}-{WIDE[1]:.0f} GeV pairs inside {CORE[0]:.0f}-{CORE[1]:.0f} GeV "
        "is higher after the full selection than for the crude selection",
        f_sel > f_crude,
        f"full {f_sel:.4f} ({n_core_s:,}/{n_wide_s:,}) vs crude {f_crude:.4f} ({n_core_c:,}/{n_wide_c:,})",
    )

    if checks.failures:
        print(f"{len(checks.failures)} check(s) failed: {', '.join(checks.failures)}")
        return 1
    print("All checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
