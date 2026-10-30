"""Layer 9 demo: the whole analysis on the small real-data sample, for readers without the 1.1 GB file.

examples/data/cmsopen_sample.root holds the first events of the development
file (record 31129, Run2012C DoubleMuParked) with only the branches the
analysis reads (examples/data/SAMPLE.md). It is small enough to commit, so
this demo runs from a fresh clone with no download.

With a few thousand pairs per channel, the demo fits voigt_poly: a
Breit-Wigner of the resonance's natural width (fixed) convolved with one
Gaussian resolution, on a quadratic background. That line shape has a
single free width, which a few thousand pairs determine. The frozen default
models (two resolution cores, dev/model_choice.md) need far more pairs to
determine their second core; on the sample they may fail, and the demo shows
that this is reported as an AnalysisError, not hidden.

The self-checks are STRUCTURAL only (no physics number is asserted): the
sample matches its recorded size and SHA-256; both channels produce pairs and
a converged fit whose peak lies within a generous window of the PDG mass
(Z: 1 GeV, J/psi: 0.02 GeV); the figures and summaries are written; parallel
processing equals serial; the frozen default either fits or fails with the
documented exception.

On macOS a script that uses n_workers needs the ``if __name__ == "__main__":``
guard, as here.

Usage:
    python examples/layer9_sample_demo.py [--file PATH]

Exits 1 if any check fails.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tempfile
import time
from pathlib import Path

import cmsopen
from cmsopen.fitting import pdg_mass_width
from cmsopen.pipeline import CHANNELS

HERE = Path(__file__).resolve().parent
SAMPLE = HERE / "data" / "cmsopen_sample.root"
WINDOW = {"Z_mumu": 1.0, "Jpsi_mumu": 0.02}  # GeV around the PDG mass: generous, structural


class Checks:
    """Collects self-check results and prints one OK/FAIL line each."""

    def __init__(self) -> None:
        self.failures: list[str] = []

    def check(self, name: str, ok: bool, detail: str) -> None:
        """Print one OK or FAIL line and remember failures."""
        print(f"{'OK' if ok else 'FAIL'}: {name} ({detail})")
        if not ok:
            self.failures.append(name)


def recorded(key: str) -> str:
    """A value from the provenance table in examples/data/SAMPLE.md."""
    m = re.search(rf"^\| {key} \| (.+?) \|$", (SAMPLE.parent / "SAMPLE.md").read_text(), flags=re.M)
    return m.group(1) if m else ""


def main() -> int:
    """Run the demo and return the exit status."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--file", type=Path, default=SAMPLE, help="the sample (default: examples/data/...)")
    path = parser.parse_args().file.resolve()
    if not path.exists():
        sys.exit(f"error: file not found: {path}")
    print(f"cmsopen imported from: {cmsopen.__file__}")
    print(f"Sample: {path} ({path.stat().st_size:,} bytes)")
    checks = Checks()
    data = path.read_bytes()
    checks.check(
        "the sample matches its recorded size and SHA-256 (examples/data/SAMPLE.md)",
        recorded("size") == f"{len(data):,} bytes" and recorded("SHA-256") == hashlib.sha256(data).hexdigest(),
        f"{len(data):,} bytes, sha256 {hashlib.sha256(data).hexdigest()[:16]}...",
    )
    tmp = Path(tempfile.mkdtemp(prefix="cmsopen-layer9-"))
    results = {}
    for name in ("Z_mumu", "Jpsi_mumu"):
        start = time.perf_counter()
        r = results[name] = cmsopen.analyze(path, channel=name, model="voigt_poly", stability=False, verbose=False,
                                            outdir=tmp / name)
        print(f"\n=== {name} ({time.perf_counter() - start:.1f} s)")
        print(r.fit.table())
        pdg = pdg_mass_width(CHANNELS[name].resonance)[0]
        m, me = r.fit.peak_position
        checks.check(f"{name}: pairs and a converged voigt_poly fit", r.fit.n_entries > 500,
                     f"{r.fit.n_entries:,} pairs in the fit range, chi2/ndf {r.fit.chi2_ndf:.2f}")
        checks.check(f"{name}: the peak lies within {WINDOW[name]:g} GeV of the PDG mass (a generous window)",
                     abs(m - pdg) < WINDOW[name], f"{m:.4f} +- {me:.4f} GeV, PDG {pdg:.4f} GeV")
        written = {p.name for p in (tmp / name).iterdir()}
        checks.check(f"{name}: figures and summaries are written",
                     {"summary.json", "summary.txt", "mass_fit.png", "cutflow.png"} <= written,
                     ", ".join(sorted(written)))

    parallel = cmsopen.analyze(path, channel="Z_mumu", model="voigt_poly", stability=False, verbose=False,
                               n_workers=2, chunk_size=10_000)
    checks.check("parallel (n_workers=2, chunks of 10,000 events) equals serial",
                 json.dumps(parallel.to_dict(), sort_keys=True) == json.dumps(results["Z_mumu"].to_dict(),
                                                                              sort_keys=True),
                 "to_dict() compared")

    default = CHANNELS["Jpsi_mumu"].model
    try:
        r = cmsopen.analyze(path, channel="Jpsi_mumu", stability=False, verbose=False)
        outcome, ok = f"fitted: {r.fit.model_name}, chi2/ndf {r.fit.chi2_ndf:.2f}", r.fit.model_name == default
    except cmsopen.AnalysisError as exc:
        outcome, ok = f"AnalysisError: {str(exc)[:110]}", "fit failed" in str(exc)
    print(f"\nThe frozen J/psi default ({default}) on the sample: {outcome}")
    checks.check("the frozen default either fits or fails with the documented AnalysisError", ok, outcome[:60])

    if checks.failures:
        print(f"{len(checks.failures)} check(s) failed: {', '.join(checks.failures)}")
        return 1
    print("All checks passed")
    return 0


if __name__ == "__main__":  # required for n_workers on macOS: worker processes re-import this script
    sys.exit(main())
