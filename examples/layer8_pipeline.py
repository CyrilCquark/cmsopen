"""Layer 8 demo: the end-to-end pipeline, cmsopen.analyze, and the cmsopen command.

Runs the complete Z -> mu+ mu- analysis in one call, saves its figures and
summaries into a new temporary directory, then the J/psi -> mu+ mu- channel,
a parallel run with two worker processes, the data helper on the folder that
already holds the file, and the command line (``python -m cmsopen`` and the
installed ``cmsopen`` script). Checks: the development-file cutflow and fit
entries, the peak position against the Layer 6 value, chunked equals
unchunked, parallel equals serial exactly, the output files exist and are
byte-identical across runs, the command line reproduces the summary, the
J/psi fit converges with its peak in 2.9-3.3 GeV, the data helper verifies
without downloading, and the docs-freeze and blinding checks pass. The wall
time of every step is printed.

On macOS (and Windows) worker processes are started with "spawn", which
re-imports the calling script: a script that uses ``n_workers`` needs the
``if __name__ == "__main__":`` guard at the bottom, as here.

Usage:
    python examples/layer8_pipeline.py [--file PATH] [--since REV]

Exits 1 if any check fails.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

import numpy as np

import cmsopen
from cmsopen.datasets import DEV_FILENAME, DEV_SIZE, fetch_example_data

# Development-file results of the earlier layers (regression values; checked only on that file).
DEV_FINAL_CUTFLOW = (57_058, 28_528, 28_528)  # muons, events with muons, events (last cutflow row)
DEV_FIT_ENTRIES = 26_195  # opposite-sign pairs in the 70-110 GeV fit range
LAYER6_PEAK_GEV = 90.7829  # Layer 6 voigt_poly peak position on the development file
LAYER8_START = "da40816"  # this layer's START commit, the docs-freeze baseline
FIRST_EVENTS = 100_000
OUTPUTS = (
    "cutflow.pdf",
    "cutflow.png",
    "mass_fit.pdf",
    "mass_fit.png",
    "os_vs_ss.pdf",
    "os_vs_ss.png",
    "summary.json",
    "summary.txt",
)
REPO = Path(__file__).resolve().parents[1]
T = TypeVar("T")


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


class Timer:
    """Wall time of each named step, printed when the step ends."""

    def __init__(self) -> None:
        self.times: dict[str, float] = {}

    def run(self, name: str, func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """Call ``func(*args, **kwargs)``, print and remember its wall time, return its result."""
        start = time.perf_counter()
        out = func(*args, **kwargs)
        self.times[name] = time.perf_counter() - start
        print(f"[time] {name}: {self.times[name]:.2f} s")
        return out


def default_file() -> Path:
    """The first ROOT file in the repository's data/ directory (exits with a message if there is none)."""
    files = sorted((REPO / "data").glob("*.root"))
    if not files:
        sys.exit(f"error: no .root file in {REPO / 'data'}; download one (see DATA.md) or pass --file PATH")
    return files[0]


def is_dev_file(path: Path) -> bool:
    """True for the development file of DATA.md (by name and size)."""
    return path.name == DEV_FILENAME and path.stat().st_size == DEV_SIZE


def same_result(a: cmsopen.AnalysisResult, b: cmsopen.AnalysisResult) -> list[str]:
    """The parts in which two analysis results differ (empty if identical): masses, cutflow, fits, summary."""
    differ = []
    if not np.array_equal(a.masses, b.masses):
        differ.append("masses")
    if not np.array_equal(a.same_sign_masses, b.same_sign_masses):
        differ.append("same-sign masses")
    if a.cutflow.to_records() != b.cutflow.to_records():
        differ.append("cutflow")
    da, db = a.to_dict(), b.to_dict()
    for key in ("fit", "alternate_fit", "histogram", "pdg_comparison"):
        if json.dumps(da[key], sort_keys=True) != json.dumps(db[key], sort_keys=True):
            differ.append(key)
    if a.summary() != b.summary():
        differ.append("summary")
    return differ


def list_files(paths: list[Path]) -> None:
    """Print each path with its size in bytes."""
    for p in paths:
        print(f"  {p}  {p.stat().st_size:,} bytes")


def cli_command() -> list[str] | None:
    """The installed ``cmsopen`` console script next to this Python, or on PATH (None if absent)."""
    script = Path(sys.executable).parent / "cmsopen"
    found = str(script) if script.exists() else shutil.which("cmsopen")
    return [found] if found else None


def run_check_script(name: str, *args: str) -> tuple[int, str] | None:
    """Run scripts/<name> from the repository root; (exit status, last output line), None if not in a clone."""
    script = REPO / "scripts" / name
    if not script.exists() or not (REPO / ".git").exists():
        return None
    out = subprocess.run([sys.executable, str(script), *args], cwd=REPO, capture_output=True, text=True)
    lines = (out.stdout + out.stderr).strip().splitlines()
    return out.returncode, lines[-1] if lines else ""


def main() -> int:
    """Parse the command line, run the demo, and return the exit status."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--file", type=Path, default=None, help="NanoAOD ROOT file (default: first data/*.root)")
    parser.add_argument("--since", default=LAYER8_START, help="docs-freeze baseline revision")
    args = parser.parse_args()
    path = (args.file or default_file()).resolve()
    if not path.exists():
        sys.exit(f"error: file not found: {path}")
    print(f"cmsopen imported from: {cmsopen.__file__}")
    print(f"Data file: {path}")
    tmp = Path(tempfile.mkdtemp(prefix="cmsopen-layer8-"))
    print(f"Output directory: {tmp}")
    timer = Timer()

    print("\n=== 1. Z -> mu+ mu-: result = cmsopen.analyze(file)  (prints result.summary())")
    start = time.perf_counter()
    result = cmsopen.analyze(path)
    timer.times["Z analysis"] = time.perf_counter() - start
    print(f"[time] Z analysis: {timer.times['Z analysis']:.2f} s")
    z_files = timer.run("Z save", result.save, tmp / "z")
    print(f"Written to {tmp / 'z'}:")
    list_files(z_files)

    print('\n=== 2. J/psi -> mu+ mu-: cmsopen.analyze(file, channel="Jpsi_mumu")  (prints its summary)')
    jpsi = timer.run("J/psi analysis", cmsopen.analyze, path, channel="Jpsi_mumu")
    jpsi_files = jpsi.save(tmp / "jpsi")
    print(f"J/psi mass-fit figure: {tmp / 'jpsi' / 'mass_fit.png'}")

    print(f"\n=== 3. First {FIRST_EVENTS:,} events: one chunk, chunks of 25,000, and 2 worker processes")
    first = dict(n_events=FIRST_EVENTS, verbose=False, stability=False)
    unchunked = timer.run("unchunked (1 chunk of 100,000)", cmsopen.analyze, path, chunk_size=FIRST_EVENTS, **first)
    serial = timer.run("serial (4 chunks of 25,000)", cmsopen.analyze, path, chunk_size=25_000, **first)
    parallel = timer.run("parallel (n_workers=2)", cmsopen.analyze, path, chunk_size=25_000, n_workers=2, **first)
    print(
        f"  {len(serial.masses):,} pairs; peak {serial.fit.peak_position[0]:.4f} GeV (serial), "
        f"{parallel.fit.peak_position[0]:.4f} GeV (parallel)"
    )

    print("\n=== 4. Data helper: fetch_example_data on the folder that holds the file")
    fetched, n_requests, unchanged = None, None, None
    if is_dev_file(path):
        requests: list[object] = []
        real_urlopen = urllib.request.urlopen
        urllib.request.urlopen = lambda *a, **k: requests.append(a) or real_urlopen(*a, **k)  # count requests
        before = path.stat()
        try:
            fetched = timer.run("fetch_example_data (verify)", fetch_example_data, path.parent, progress=False)
        finally:
            urllib.request.urlopen = real_urlopen
        after = path.stat()
        n_requests = len(requests)
        unchanged = (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns)
        print(f"  returned: {fetched}")
        print(f"  HTTP requests made: {n_requests}; file size and modification time unchanged: {unchanged}")
        print("  no download happened" if n_requests == 0 and unchanged else "  a download happened")
    else:
        print("  skipped: not the development file of DATA.md (the helper would download it)")

    print("\n=== 5. Command line: python -m cmsopen analyze FILE --quiet --outdir ... and the cmsopen script")
    commands = {"python -m cmsopen": [sys.executable, "-m", "cmsopen"], "cmsopen": cli_command()}
    cli: dict[str, tuple[int, str, Path]] = {}
    for label, cmd in commands.items():
        if cmd is None:
            print(f"  {label}: not installed")
            continue
        out = tmp / ("cli_module" if label.startswith("python") else "cli_script")
        proc = timer.run(
            f"CLI {label}",
            subprocess.run,
            [*cmd, "analyze", str(path), "--quiet", "--outdir", str(out)],
            capture_output=True,
            text=True,
        )
        cli[label] = (proc.returncode, proc.stderr.strip(), out)
        print(f"  {' '.join([Path(cmd[0]).name, *cmd[1:]])} analyze ... -> exit {proc.returncode}")

    print("\n=== Self-checks")
    checks = Checks()
    last = result.cutflow[-1]
    if is_dev_file(path):
        got = (last.n_particles, last.n_events_with_particles, last.n_events)
        checks.check(
            "Z: final cutflow row and fit-range entries match the development results",
            got == DEV_FINAL_CUTFLOW and result.fit.n_entries == DEV_FIT_ENTRIES,
            f"{got[0]:,} muons / {got[1]:,} events / {got[2]:,} events, {result.fit.n_entries:,} entries in the fit "
            f"range; expected {DEV_FINAL_CUTFLOW[0]:,} / {DEV_FINAL_CUTFLOW[1]:,} / {DEV_FINAL_CUTFLOW[2]:,}, "
            f"{DEV_FIT_ENTRIES:,}",
        )
        # Like for like: the Layer 6 value is a voigt_poly fit; analyze() reports that model next to the default one.
        voigt = next(f for f in (result.fit, result.alternate_fit) if f is not None and f.model_name == "voigt_poly")
        m, me = voigt.peak_position
        pole, pole_err = result.fit.peak_position
        checks.check(
            "Z: the voigt_poly peak position agrees with the Layer 6 value within the statistical uncertainty",
            abs(m - LAYER6_PEAK_GEV) < me,
            f"pipeline voigt_poly {m:.4f} +- {me:.4f} GeV, Layer 6 {LAYER6_PEAK_GEV:.4f} GeV, "
            f"difference {m - LAYER6_PEAK_GEV:+.4f} GeV; default model {result.fit.model_name}: "
            f"{pole:.4f} +- {pole_err:.4f} GeV (report only)",
        )
    else:
        checks.skip("Z: development cutflow, fit entries and Layer 6 peak", f"{path.name} is not the development file")

    differ = same_result(unchunked, serial)
    checks.check(
        f"chunked (4 x 25,000) equals unchunked (1 x {FIRST_EVENTS:,}) on the first {FIRST_EVENTS:,} events",
        not differ,
        f"{len(serial.masses):,} masses, cutflow, fits and summary compared"
        + (f"; differ: {differ}" if differ else ""),
    )
    differ = same_result(serial, parallel)
    checks.check(
        "parallel (n_workers=2) equals serial exactly",
        not differ,
        "masses, same-sign masses, cutflow, both fits, histogram, PDG comparison and summary"
        + (f"; differ: {differ}" if differ else ""),
    )

    names = sorted(p.name for p in z_files)
    runs = [tmp / "z", *(out for _, _, out in cli.values())]
    identical = [
        all((d / n).exists() and (d / n).read_bytes() == (tmp / "z" / n).read_bytes() for n in OUTPUTS) for d in runs
    ]
    checks.check(
        "all expected output files exist",
        names == sorted(OUTPUTS) and all((tmp / "z" / n).stat().st_size > 0 for n in OUTPUTS),
        ", ".join(names),
    )
    checks.check(
        "independent runs give byte-identical output files",
        len(runs) >= 2 and all(identical),
        f"{len(OUTPUTS)} files in each of {len(runs)} runs (cmsopen.analyze, "
        f"{', '.join(cli) or 'no CLI'}) compared with cmsopen.analyze",
    )
    for label, (code, err, out) in cli.items():
        text = (out / "summary.txt").read_text() if (out / "summary.txt").exists() else ""
        equal = text == result.summary() + "\n"
        checks.check(
            f"CLI `{label} analyze` exits 0 and its summary.txt equals result.summary()",
            code == 0 and equal,
            f"exit {code}, summary equal: {equal}" + (f", stderr: {err[-200:]}" if err else ""),
        )
    if commands["cmsopen"] is None:
        checks.check("the installed cmsopen command exists", False, "not found next to Python or on PATH")

    jm, jme = jpsi.fit.peak_position
    js, jse = jpsi.fit.resolution
    finite = bool(np.all(np.isfinite(jpsi.fit.values)) and np.all(np.isfinite(jpsi.fit.errors)))
    n_window = int(np.sum((jpsi.masses >= 2.9) & (jpsi.masses < 3.3)))
    checks.check(
        "J/psi: the fit converges and its peak lies within 2.9-3.3 GeV (sanity bound; the rest is reported only)",
        finite and 2.9 < jm < 3.3,
        f"{len(jpsi.masses):,} pairs ({n_window:,} in 2.9-3.3 GeV, {jpsi.fit.n_entries:,} in the fit range), "
        f"peak {jm:.4f} +- {jme:.4f} GeV, resolution {js:.4f} +- {jse:.4f} GeV, "
        f"chi2/ndf {jpsi.fit.chi2:.1f}/{jpsi.fit.ndf} = {jpsi.fit.chi2_ndf:.2f}, "
        f"yields reliable: {jpsi.fit.yields_reliable}",
    )
    if fetched is None:
        checks.skip("fetch_example_data verifies the existing file without downloading", "not the development file")
    else:
        checks.check(
            "fetch_example_data verified the existing file and returned it without downloading",
            fetched == path and n_requests == 0 and unchanged,
            f"returned {fetched}; {n_requests} HTTP requests; size and mtime unchanged: {unchanged}",
        )

    for script, script_args, label in (
        ("check_docs_frozen.py", ("--since", args.since), f"docs-freeze check (since {args.since})"),
        ("check_blinding.py", (), "blinding check"),
    ):
        res = run_check_script(script, *script_args)
        if res is None:
            checks.skip(label, f"no git clone with scripts/ at {REPO}")
        else:
            checks.check(f"{label} reports OK", res[0] == 0 and res[1].startswith("OK"), res[1])

    print("\nWall time per step:")
    for name, seconds in timer.times.items():
        print(f"  {name:<34} {seconds:8.2f} s")
    print(f"J/psi files: {', '.join(p.name for p in jpsi_files)}")

    if checks.failures:
        print(f"{len(checks.failures)} check(s) failed: {', '.join(checks.failures)}")
        return 1
    print("All checks passed")
    return 0


if __name__ == "__main__":  # required for n_workers on macOS: worker processes re-import this script
    sys.exit(main())
