"""Layer 6 demo: fitting the Z peak with cmsopen.fitting.

Selects Z -> mu+ mu- candidates in every event of the file (dimuon
trigger, cmsopen.ZMUMU_MUON_CUTS, at least two muons, opposite-sign pairs,
one pair per event with best_pair "highest_pt_sum"), histograms the pair
mass in 1 GeV bins over 60-120 GeV and fits 70-110 GeV with a Gaussian and
with a Voigt peak (natural Z width fixed), each on a degree 2 polynomial
background. Prints both fits, compares them with the PDG mass, refits under
54 combinations of fit choices, runs a toy pull test, and, as a
report-only cross-check, compares same-sign and opposite-sign pairs in the
sidebands of a loose selection.

Usage:
    python examples/layer6_fitting.py [--file PATH]

Exits 1 if any check fails.
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import awkward as ak
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

FIT_RANGE = (70.0, 110.0)
POLY_DEGREE = 2
MODELS = {"gauss_poly": "Gaussian + quadratic", "voigt_poly": "Voigt + quadratic"}
SIDEBANDS = ((60.0, 80.0), (100.0, 120.0))
PEAK = (80.0, 100.0)


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


def count_in(mass: np.ndarray, window: tuple[float, float]) -> int:
    """Number of masses in the half-open window [low, high)."""
    return int(np.sum((mass >= window[0]) & (mass < window[1])))


def sideband_cross_check(path: Path) -> None:
    """Report-only: same-sign vs opposite-sign pairs in the sidebands of a loose selection."""
    with open_events(path) as events:
        loose = events.muons(min_pt=20.0, max_eta=2.4).require_trigger(*DIMUON_TRIGGERS_2012).require(2)
    m_os = ak.to_numpy(ak.flatten(opposite_sign_pairs(loose).mass))
    m_ss = ak.to_numpy(ak.flatten(same_sign_pairs(loose).mass))
    print("Cross-check (report only, not a pass/fail check): loose selection, all pair candidates")
    print(f"  {loose!r}")
    print(f"  {'window [GeV]':<16}{'opposite-sign':>15}{'same-sign':>12}{'SS / OS':>10}")
    windows = (*SIDEBANDS, PEAK)
    for lo, hi in windows:
        n_os, n_ss = count_in(m_os, (lo, hi)), count_in(m_ss, (lo, hi))
        ratio = f"{n_ss / n_os:.3f}" if n_os else "-"
        label = f"{lo:g}-{hi:g}" + (" (peak)" if (lo, hi) == PEAK else "")
        print(f"  {label:<16}{n_os:>15,}{n_ss:>12,}{ratio:>10}")
    os_side = sum(count_in(m_os, w) for w in SIDEBANDS)
    ss_side = sum(count_in(m_ss, w) for w in SIDEBANDS)
    print(
        f"  {'both sidebands':<16}{os_side:>15,}{ss_side:>12,}{(ss_side / os_side if os_side else float('nan')):>10.3f}"
    )
    print(
        "  What this shows: same-sign pairs cannot come from a Z, so their rate in the sidebands measures the\n"
        "  combinatorial and misidentified-muon background there. The SS/OS ratio says what fraction of the\n"
        "  opposite-sign sideband pairs that kind of background could account for.\n"
        "  What it does not show: the rest of the opposite-sign sidebands is not 'signal'. Drell-Yan\n"
        "  production (a virtual photon decaying to mu+ mu-) and the Z line-shape tails are genuine\n"
        "  opposite-sign pairs with no same-sign partner, and some backgrounds (b b-bar decays) favour opposite\n"
        "  sign. So SS/OS is not a background fraction, and these counts do not test the polynomial fit."
    )
    print()


def main() -> int:
    """Parse the command line, run the demo or tool, and return the exit status."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--file", type=Path, default=None, help="NanoAOD ROOT file (default: first data/*.root)")
    path = parser.parse_args().file or default_file()
    if not path.exists():
        sys.exit(f"error: file not found: {path}")

    print(f"cmsopen imported from: {cmsopen.__file__}")
    pdg_mass, pdg_mass_err, pdg_width, pdg_width_err = pdg_mass_width("Z")
    print(
        f"PDG Z (from the particle package): mass {pdg_mass:.4f} +- {pdg_mass_err:.4f} GeV, "
        f"width {pdg_width:.4f} +- {pdg_width_err:.4f} GeV"
    )
    print()

    with open_events(path) as events:
        n_file = events.n_events
        sel = events.muons(**ZMUMU_MUON_CUTS).require_trigger(*DIMUON_TRIGGERS_2012).require(2)
    best = best_pair(opposite_sign_pairs(sel), "highest_pt_sum")
    masses = best.mass
    h = make_histogram(masses, bins=60, range=(60.0, 120.0))
    print(f"{path.name}: {n_file:,} events; {sel!r}")
    print(f"{best.n_pairs:,} opposite-sign pairs (one per event); {h!r}")
    print()

    results: dict[str, object] = {}
    for model, label in MODELS.items():
        print(f"== {label} ==")
        try:
            r = fit_mass_peak(h, model=model, fit_range=FIT_RANGE, poly_degree=POLY_DEGREE)
        except FitError as exc:
            print(f"  FitError: {exc}")
            results[model] = exc
            print()
            continue
        results[model] = r
        print(r.table())
        print(f"  compare_to_pdg: {compare_to_pdg(r)}")
        print()

    stability = fit_stability(masses)
    print("Stability of the fitted mass under changes of fit choices (fit range, bin width, degree, model):")
    print(stability)
    print()

    sideband_cross_check(path)

    pulls = pull_test(n_toys=1000)
    print(
        f"Toy pull test: {pulls.n_toys} toys (Gaussian peak at {pulls.true_mean} GeV on a falling exponential), "
        f"{pulls.n_failed} failed; pull mean {pulls.mean:+.3f}, std {pulls.std:.3f}"
    )
    print()

    checks = Checks()
    fits = {m: r for m, r in results.items() if not isinstance(r, Exception)}
    finite = {m: bool(np.all(np.isfinite(r.errors)) and np.all(r.errors > 0)) for m, r in fits.items()}
    checks.check(
        "both fits converge with finite uncertainties",
        len(fits) == len(MODELS) and all(finite.values()),
        "; ".join(
            f"{m}: "
            + (
                f"{len(r.errors)} parameters, max relative error {np.max(r.errors / np.abs(r.values)):.3g}"
                if m in fits
                else f"FitError ({r})"
            )
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

    if checks.failures:
        print(f"{len(checks.failures)} check(s) failed: {', '.join(checks.failures)}")
        return 1
    print("All checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
