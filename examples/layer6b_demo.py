"""Layer 6b demo: the Breit-Wigner (x) Crystal Ball fit, the model comparison, the validation scan, the systematics.

For each channel (Z_mumu, Jpsi_mumu) the demo fits the default model
(cb_bw_exp for the Z, cb_bw_poly2 for the J/psi, chosen on the development
file by the rule in dev/model_choice.md), compares voigt_poly, cb_bw_exp and
cb_bw_poly2 on the same histogram, runs the pre-registered validation
(dev/validation_plan.md) and prints its table and systematics summary.

The self-checks are STRUCTURAL only; no physics number is asserted to be
correct: the categories partition the pairs; a fit that claims reliable
yields has a background that is not negative anywhere in its fit range;
parallel equals serial; validation off gives exactly the old output; the
5,000-pair rule fires exactly for the entries below 5,000 pairs.

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
from cmsopen.fitting import FitError, FitResult, fit_mass_peak, pdg_mass_width
from cmsopen.pipeline import CHANNELS
from cmsopen.validation import MIN_PAIRS

REPO = Path(__file__).resolve().parents[1]
COMPARED = ("voigt_poly", "cb_bw_exp", "cb_bw_poly2")
PARTITIONS = ("region", "phi(mu+)", "phi(mu-)", "eta(mu+)", "eta(mu-)", "pT(sublead)", "PV_npvsGood")
PARALLEL_EVENTS = 150_000


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

    for name in ("Z_mumu", "Jpsi_mumu"):
        cfg = CHANNELS[name]
        print(f"\n=== {name}: default model {cfg.model} (cb_n = {cfg.cb_n:g})")
        start = time.perf_counter()
        result = cmsopen.analyze(path, channel=name, validation=True, verbose=False)
        print(f"[time] analyze with validation: {time.perf_counter() - start:.1f} s")
        print(result.fit.table())
        saved = result.save(tmp / name)
        print(f"Figures and summaries written to {tmp / name} ({len(saved)} files)")
        fits = compare_models(result)
        print_comparison(name, fits)
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
        small = [e for e in (v.inclusive, *v.entries) if e.n_pairs < MIN_PAIRS]
        large = [e for e in (v.inclusive, *v.entries) if e.n_pairs >= MIN_PAIRS]
        checks.check(
            f"{name}: the {MIN_PAIRS:,}-pair rule fires exactly for the entries below {MIN_PAIRS:,} pairs",
            all(e.status == "insufficient" and e.position is None for e in small)
            and all(e.status in ("fitted", "failed") for e in large),
            f"{len(small)} insufficient, {sum(e.fitted for e in large)} fitted, "
            f"{sum(e.status == 'failed' for e in large)} failed",
        )

    print(f"\n=== Parallel equals serial (Z_mumu with validation, first {PARALLEL_EVENTS:,} events)")
    first = dict(
        channel="Z_mumu", n_events=PARALLEL_EVENTS, chunk_size=50_000, validation=True, verbose=False, stability=False
    )
    serial = cmsopen.analyze(path, **first)
    parallel = cmsopen.analyze(path, n_workers=2, **first)
    checks.check(
        "parallel (n_workers=2) equals serial with validation on",
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
