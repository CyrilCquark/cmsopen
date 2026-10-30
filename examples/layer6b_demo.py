"""Layer 6b/6c/6d demo: Breit-Wigner (x) Crystal Ball fits, resolution mixtures, model comparison, validation.

For each channel (Z_mumu, Jpsi_mumu) the demo fits the default model
(chosen on the development file by the rules in dev/model_choice.md: since
Amendment 2 the resolution mixtures cb2_bw_exp for the Z and cb2_bw_poly2 for
the J/psi), compares voigt_poly, cb_bw_exp, cb_bw_poly2, cb2_bw_exp and
cb2_bw_poly2 on the same histogram, shows the Amendment 2 comparison and the
mixture parameters (sigma1, r, f, FWHM/2.355), runs the pre-registered
validation (dev/validation_plan.md) and prints its table and systematics
summary.

The self-checks are STRUCTURAL only; no physics number is asserted to be
correct: the categories partition the pairs; a fit that claims reliable
yields has a background that is not negative anywhere in its fit range;
parallel equals serial; validation off gives exactly the old output; the
5,000-pair rule fires exactly for the entries below 5,000 pairs; a mixture
with f = 1 is the single-resolution model; a mixture fitted to a sample with
one resolution is ineligible; a mixture's reported resolution is its
numerical FWHM / 2.355. Layer 6d (Amendment 3): the three-resolution models
cb3_bw_exp and cb3_bw_poly2 are fitted and reported (they may fail on one
file; the rule was applied on the 6-file development set), a three-resolution
mixture with g = 1 is the two-resolution model, a cb3 fit to a sample with
one resolution is ineligible, and every scaled validation error
(max(1, sqrt(chi2/ndf)) x the raw error) is at least the raw error.

On macOS a script that uses n_workers needs the ``if __name__ == "__main__":``
guard, as here.

Usage:
    python examples/layer6b_demo.py [--file PATH]

Exits 1 if any check fails.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import numpy as np

import cmsopen
from cmsopen.fitting import (
    MIXTURE_MODELS,
    THREE_RES_MODELS,
    FitError,
    FitResult,
    MassHistogram,
    crystalball2_bw,
    crystalball3_bw,
    crystalball_bw,
    fit_mass_peak,
    pdg_mass_width,
)
from cmsopen.pipeline import CHANNELS
from cmsopen.validation import MIN_PAIRS

REPO = Path(__file__).resolve().parents[1]
COMPARED = ("voigt_poly", "cb_bw_exp", "cb_bw_poly2", "cb2_bw_exp", "cb2_bw_poly2", "cb3_bw_exp", "cb3_bw_poly2")
SINGLE_OF = {"cb2_bw_exp": "cb_bw_exp", "cb2_bw_poly2": "cb_bw_poly2"}
FWHM_PER_SIGMA = 2.3548200450309493
PARTITIONS = ("region", "phi(mu+)", "phi(mu-)", "eta(mu+)", "eta(mu-)", "pT(sublead)", "PV_npvsGood")


class Checks:
    """Collects self-check results and prints one OK/FAIL/SKIP line each."""

    def __init__(self) -> None:
        self.failures: list[str] = []

    def check(self, name: str, ok: bool, detail: str) -> None:
        """Print one OK or FAIL line and remember failures."""
        print(f"{'OK' if ok else 'FAIL'}: {name} ({detail})")
        if not ok:
            self.failures.append(name)


def default_file() -> Path:
    """The first ROOT file in the repository's data/ directory (exits with a message if there is none)."""
    files = sorted((REPO / "data").glob("*.root"))
    if not files:
        sys.exit(f"error: no .root file in {REPO / 'data'}; download one (see DATA.md) or pass --file PATH")
    return files[0]


def compare_models(result: cmsopen.AnalysisResult) -> dict[str, FitResult | str]:
    """voigt_poly, cb_bw_exp and cb_bw_poly2 on the channel's histogram (a FitResult, or the failure reason)."""
    cfg = result.config
    out: dict[str, FitResult | str] = {}
    for model in COMPARED:
        try:
            out[model] = fit_mass_peak(
                result.histogram,
                model=model,
                fit_range=cfg.fit_range,
                poly_degree=cfg.poly_degree,
                natural_width=pdg_mass_width(cfg.resonance)[2],
                cb_n=cfg.cb_n,
            )
        except FitError as exc:
            out[model] = f"fit failed: {exc}"
    return out


def print_comparison(name: str, fits: dict[str, FitResult | str]) -> None:
    """One line per model: position, resolution, chi2/ndf, AIC and whether its yields are reliable."""
    print(f"Model comparison, {name}:")
    for model, fit in fits.items():
        if isinstance(fit, str):
            print(f"  {model:<12} {fit}")
            continue
        m, me = fit.peak_position
        s, se = fit.resolution
        aic = fit.chi2 + 2 * len(fit.values)
        print(
            f"  {model:<12} position {m:.4f} +- {me:.4f} GeV, resolution {s:.4f} +- {se:.4f} GeV, "
            f"chi2/ndf {fit.chi2_ndf:.3f}, AIC {aic:.1f}, yields reliable: {fit.yields_reliable}"
        )


def print_mixtures(name: str, fits: dict[str, FitResult | str]) -> None:
    """The mixture parameters and the Amendment 2 comparison with the single-resolution model of the same background."""
    print(f"Resolution mixtures, {name} (Amendment 2):")
    for model in MIXTURE_MODELS:
        fit, single = fits[model], fits[SINGLE_OF[model]]
        if isinstance(fit, str):
            print(f"  {model:<12} {fit}")
            continue
        p = fit.parameters
        s, se = fit.resolution
        line = (
            f"  {model:<12} sigma1 {p['sigma'][0]:.4f} +- {p['sigma'][1]:.4f} GeV, r {p['r'][0]:.3f} +- "
            f"{p['r'][1]:.3f}, f {p['f'][0]:.3f} +- {p['f'][1]:.3f}, FWHM/2.355 {s:.4f} +- {se:.4f} GeV, "
            f"on a bound: {fit.on_bound or 'none'}"
        )
        if isinstance(single, FitResult):
            line += f"; AIC {aic(fit):.1f} vs {SINGLE_OF[model]} {aic(single):.1f}"
        print(line)


def print_three(name: str, fits: dict[str, FitResult | str]) -> None:
    """The three-resolution fits (Amendment 3): parameters, or why the fit is not eligible."""
    print(f"Three-resolution mixtures, {name} (Amendment 3; the rule is applied on the 6-file development set):")
    for model in THREE_RES_MODELS:
        fit = fits[model]
        if isinstance(fit, str):
            print(f"  {model:<12} {fit}")
            continue
        p = fit.parameters
        s, se = fit.resolution
        print(
            f"  {model:<12} sigma1 {p['sigma'][0]:.4f} +- {p['sigma'][1]:.4f} GeV, r2 {p['r2'][0]:.3f}, "
            f"s {p['s'][0]:.3f}, f1 {p['f1'][0]:.3f}, g {p['g'][0]:.3f}, FWHM/2.355 {s:.4f} +- {se:.4f} GeV, "
            f"chi2/ndf {fit.chi2_ndf:.3f}"
        )


def g_one_matches_two(fit: FitResult) -> float:
    """Largest difference (relative to the peak) between the three-resolution signal with g = 1 and the
    two-resolution signal with r = r2 and f = f1, at the parameters of a two-resolution fit (s set to 2)."""
    a, m, s1, alpha, r, f = fit.values[:6]
    edges = fit._fit_edges()
    x = np.linspace(edges[0], edges[-1], 801)
    kw = dict(n=fit.cb_n, gamma=fit.gamma, norm_edges=edges)
    three = crystalball3_bw(x, a, m, s1, alpha, r, 2.0, f, 1.0, **kw)
    two = crystalball2_bw(x, a, m, s1, alpha, r, f, **kw)
    return float(np.max(np.abs(three - two) / two.max()))


def aic(fit: FitResult) -> float:
    """chi2 + 2k."""
    return fit.chi2 + 2 * len(fit.values)


def f_one_matches_single(fit: FitResult) -> float:
    """Largest relative difference between the mixture with f = 1 and the single-resolution signal, same parameters."""
    a, m, s1, alpha, r, _ = fit.values[:6]
    edges = fit._fit_edges()
    x = np.linspace(edges[0], edges[-1], 801)
    kw = dict(n=fit.cb_n, gamma=fit.gamma, norm_edges=edges)
    mix = crystalball2_bw(x, a, m, s1, alpha, r, 1.0, **kw)
    single = crystalball_bw(x, a, m, s1, alpha, **kw)
    return float(np.max(np.abs(mix - single) / single.max()))


def one_resolution_toy(seed: int = 2) -> MassHistogram:
    """A Z-like sample with a single resolution (Breit-Wigner (x) one Gaussian) on a flat background."""
    rng = np.random.default_rng(seed)
    gamma = 0.5 * pdg_mass_width("Z")[2]
    sig = 91.0 + gamma * rng.standard_cauchy(40000) + 1.4 * rng.standard_normal(40000)
    counts, edges = np.histogram(np.r_[sig, rng.uniform(60, 120, 8000)], bins=60, range=(60.0, 120.0))
    return MassHistogram(counts.astype(np.float64), edges)


def background_ok(fit: FitResult) -> bool:
    """A fit claiming reliable yields must have a background that is >= 0 everywhere in its fit range."""
    if not fit.yields_reliable:
        return True  # nothing is claimed
    grid = np.linspace(*fit.fit_range, 2001)
    return bool(np.all(fit.background(grid) >= 0) and np.isfinite(fit.signal_yield[0]))


def without_validation(d: dict[str, Any]) -> str:
    """The JSON of a result dictionary without its validation part."""
    return json.dumps({k: v for k, v in d.items() if k != "validation"}, sort_keys=True)


def main() -> int:
    """Parse the command line, run the demo, and return the exit status."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--file", type=Path, default=None, help="NanoAOD ROOT file (default: first data/*.root)")
    path = (parser.parse_args().file or default_file()).resolve()
    if not path.exists():
        sys.exit(f"error: file not found: {path}")
    print(f"cmsopen imported from: {cmsopen.__file__}")
    print(f"Data file: {path}")
    tmp = Path(tempfile.mkdtemp(prefix="cmsopen-layer6b-"))
    checks = Checks()
    results: dict[str, cmsopen.AnalysisResult] = {}

    for name in ("Z_mumu", "Jpsi_mumu"):
        cfg = CHANNELS[name]
        print(f"\n=== {name}: default model {cfg.model} (cb_n = {cfg.cb_n:g})")
        start = time.perf_counter()
        result = results[name] = cmsopen.analyze(path, channel=name, validation=True, verbose=False)
        print(f"[time] analyze with validation: {time.perf_counter() - start:.1f} s")
        print(result.fit.table())
        saved = result.save(tmp / name)
        print(f"Figures and summaries written to {tmp / name} ({len(saved)} files)")
        fits = compare_models(result)
        print_comparison(name, fits)
        print_mixtures(name, fits)
        print_three(name, fits)
        v = result.validation
        assert v is not None
        print()
        print(v.table())

        plain = cmsopen.analyze(path, channel=name, verbose=False)
        on = result.to_dict()
        checks.check(
            f"{name}: validation off gives exactly the old output",
            plain.validation is None
            and "validation" not in plain.to_dict()
            and json.dumps(plain.to_dict(), sort_keys=True) == without_validation(on)
            and result.summary().startswith(plain.summary() + "\n\nValidation ("),
            "to_dict() without the validation part and the summary text compared",
        )
        sums = {s: sum(e.n_pairs for e in v.study(s)) for s in PARTITIONS}
        checks.check(
            f"{name}: every category and binning partitions the pairs",
            all(n == v.inclusive.n_pairs for n in sums.values()) and v.inclusive.n_pairs == result.fit.n_entries,
            f"{v.inclusive.n_pairs:,} pairs; sums {', '.join(f'{k} {n:,}' for k, n in sums.items())}",
        )
        claims = [result.fit, *(f for f in fits.values() if isinstance(f, FitResult))]
        checks.check(
            f"{name}: every fit that claims reliable yields has a non-negative background over its fit range",
            all(background_ok(f) for f in claims),
            ", ".join(f"{f.model_name}: {'claims' if f.yields_reliable else 'does not claim'}" for f in claims),
        )
        mixtures = [f for m, f in fits.items() if m in MIXTURE_MODELS and isinstance(f, FitResult)]
        diffs = [f_one_matches_single(f) for f in mixtures]
        checks.check(
            f"{name}: a mixture with f = 1 is the single-resolution model",
            bool(mixtures) and max(diffs) < 1e-6,
            ", ".join(
                f"{f.model_name}: max difference {d:.1e} of the peak" for f, d in zip(mixtures, diffs, strict=True)
            ),
        )
        ratios = [abs(f.resolution[0] - f.fwhm[0] / FWHM_PER_SIGMA) for f in mixtures]
        checks.check(
            f"{name}: a mixture's reported resolution is its numerical FWHM / 2.355",
            bool(mixtures) and max(ratios) < 1e-12,
            ", ".join(f"{f.model_name}: {f.resolution[0]:.5f} GeV = {f.fwhm[0]:.5f} / 2.355" for f in mixtures),
        )
        diffs3 = [g_one_matches_two(f) for f in mixtures]
        checks.check(
            f"{name}: a three-resolution mixture with g = 1 is the two-resolution model",
            bool(mixtures) and max(diffs3) < 1e-6,
            ", ".join(f"at the {f.model_name} fit: max difference {d:.1e} of the peak"
                      for f, d in zip(mixtures, diffs3, strict=True)),
        )
        fitted = [e for e in (v.inclusive, *v.entries) if e.fitted]
        summary = v.summary
        checks.check(
            f"{name}: every scaled validation error is at least the raw error (scale factor never below 1)",
            all(e.scale_factor >= 1.0 and e.error_scaled >= e.error for e in fitted)
            and (summary.pdg_offset_error_scaled is None
                 or summary.pdg_offset_error_scaled >= summary.pdg_offset_error),
            f"{len(fitted)} fitted entries, scale factors {min(e.scale_factor for e in fitted):.2f}-"
            f"{max(e.scale_factor for e in fitted):.2f}; headline +- {summary.pdg_offset_error:.5f} raw, "
            f"+- {summary.pdg_offset_error_scaled:.5f} scaled",
        )
        small = [e for e in (v.inclusive, *v.entries) if e.n_pairs < MIN_PAIRS]
        large = [e for e in (v.inclusive, *v.entries) if e.n_pairs >= MIN_PAIRS]
        checks.check(
            f"{name}: the {MIN_PAIRS:,}-pair rule fires exactly for the entries below {MIN_PAIRS:,} pairs",
            all(e.status == "insufficient" and e.position is None for e in small)
            and all(e.status in ("fitted", "failed") for e in large),
            f"{len(small)} insufficient, {sum(e.fitted for e in large)} fitted, "
            f"{sum(e.status == 'failed' for e in large)} failed",
        )

    print("\n=== Eligibility on a sample with one resolution (Amendment 2 and 3 rules)")
    toy = one_resolution_toy()
    outcomes = {}
    for model in (*MIXTURE_MODELS, *THREE_RES_MODELS):
        try:
            fit = fit_mass_peak(toy, model=model, natural_width=pdg_mass_width("Z")[2], cb_n=CHANNELS["Z_mumu"].cb_n)
            outcomes[model] = "eligible" if not fit.on_bound and fit.yields_reliable else f"on a bound: {fit.on_bound}"
        except FitError as exc:
            outcomes[model] = f"ineligible: {str(exc)[str(exc).find('parameter') :][:70]}"
        print(f"  {model}: {outcomes[model]}")
    checks.check(
        "a two- or three-resolution mixture fitted to a sample with one resolution is ineligible "
        "(rule (a)/(b) of Amendments 2 and 3)",
        all(not o.startswith("eligible") for o in outcomes.values()),
        "; ".join(f"{m}: {o.split(':')[0]}" for m, o in outcomes.items()),
    )

    # The whole file: the default resolution mixture needs the full sample (on a subset its second core can be
    # undetermined, and the fit then fails by design).
    print("\n=== Parallel equals serial (Z_mumu with validation, the whole file)")
    serial = results["Z_mumu"]
    parallel = cmsopen.analyze(path, channel="Z_mumu", validation=True, verbose=False, n_workers=2)
    checks.check(
        "parallel (n_workers=2) equals serial with validation on (the summary's model list includes cb3)",
        json.dumps(serial.to_dict(), sort_keys=True) == json.dumps(parallel.to_dict(), sort_keys=True)
        and serial.summary() == parallel.summary(),
        "to_dict() and summary text compared",
    )

    if checks.failures:
        print(f"{len(checks.failures)} check(s) failed: {', '.join(checks.failures)}")
        return 1
    print("All checks passed")
    return 0


if __name__ == "__main__":  # required for n_workers on macOS: worker processes re-import this script
    sys.exit(main())
