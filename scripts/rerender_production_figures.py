"""Render docs/figures/ again from the local production files, only after proving that the numbers have not moved.

The one path by which docs/figures/ may change after the production run (scripts/check_docs_frozen.py and
scripts/apply_production.py enforce it through the provenance file). It changes how the figures look, never what they
say:

1. it verifies the local files of the registry in data/production/ by size and adler32 (it downloads nothing);
2. it reruns the same analysis of every channel as scripts/production_run.py (both runs of T1, the run periods of T6,
   the per-file fits), in a temporary directory;
3. it compares every value with results/production.json: exactly where the production check was exact (the headline
   fit, the alternate fit, the cutflow, the validation tables and the warnings all come from the summary that T1
   requires byte-identical, and summary.json is compared byte for byte with the run's saved copy when that exists),
   within a relative 1e-9 for the run-period and per-file fits;
4. if anything differs it reports each difference and writes NOTHING (exit 3);
5. if all is equal it writes docs/figures/ and results/figures_rerender.json: the commit, the reason, the verification,
   the hash of each figure and the timings.

results/production.json is read, never written. No production file name is printed or written.

Usage:
    python scripts/rerender_production_figures.py [--reason TEXT] [--workers N]

Exit status: 0 written; 2 refused before the analysis (nothing written); 3 the numbers differ (nothing written).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "examples"))
from check_docs_frozen import PROVENANCE  # noqa: E402
from production_preflight import DOWNLOAD_DIR, PRODUCTION_JSON, REGISTRY, REPO, load_registry, selected  # noqa: E402
from production_run import _channel, sanitize  # noqa: E402

RELATIVE_TOLERANCE = 1e-9
TOLERANT_KEYS = ("per_file", "t6")  # not covered by T1's byte-identical summary
SKIPPED_KEYS = ("timing_s",)  # how long it took is not a result
REASON = "layout and caption polish"


class Comparison:
    """The outcome of comparing a rerun with the record: counts, the largest deviation and every difference."""

    def __init__(self) -> None:
        self.exact = 0
        self.tolerant = 0
        self.largest = 0.0
        self.differences: list[str] = []

    def compare(self, recorded: Any, rerun: Any, path: str, tolerant: bool = False) -> None:
        """Walk both values together; every leaf is counted, and recorded as a difference if it differs."""
        if isinstance(recorded, dict) and isinstance(rerun, dict):
            if set(recorded) != set(rerun):
                self.differences.append(f"{path}: keys differ: {sorted(set(recorded) ^ set(rerun))}")
            for key in sorted(set(recorded) & set(rerun)):
                self.compare(recorded[key], rerun[key], f"{path}.{key}", tolerant or key in TOLERANT_KEYS)
        elif isinstance(recorded, list) and isinstance(rerun, list):
            if len(recorded) != len(rerun):
                self.differences.append(f"{path}: {len(recorded)} entries recorded, {len(rerun)} in the rerun")
            for k, (a, b) in enumerate(zip(recorded, rerun, strict=False)):
                self.compare(a, b, f"{path}[{k}]", tolerant)
        elif (isinstance(recorded, float) or isinstance(rerun, float)) and not isinstance(recorded, (bool, str)):
            self._number(recorded, rerun, path, tolerant)
        else:
            self.exact += 1
            if recorded != rerun or type(recorded) is not type(rerun):
                self.differences.append(f"{path}: recorded {recorded!r}, rerun {rerun!r}")

    def _number(self, recorded: Any, rerun: Any, path: str, tolerant: bool) -> None:
        if tolerant:
            self.tolerant += 1
        else:
            self.exact += 1
        if not isinstance(rerun, (int, float)) or isinstance(rerun, bool) or recorded is None:
            self.differences.append(f"{path}: recorded {recorded!r}, rerun {rerun!r}")
            return
        if math.isnan(recorded) and math.isnan(rerun):
            return
        if recorded == rerun:
            return
        deviation = abs(rerun - recorded) / max(abs(recorded), abs(rerun))
        self.largest = max(self.largest, deviation)
        if not tolerant or deviation > RELATIVE_TOLERANCE:
            self.differences.append(f"{path}: recorded {recorded!r}, rerun {rerun!r} (relative {deviation:.3g})")


def sha256(path: Path) -> str:
    """SHA-256 of a file, hex."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _as_written(value: Any) -> Any:
    """A rerun's values as results/production.json holds them: through JSON, as the run wrote them."""
    return json.loads(json.dumps(value))


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, check=True).stdout


def local_files(files: list[dict[str, Any]]) -> tuple[list[Path] | None, str]:
    """The registry's files in data/production/, in registry order, verified; or None and why (no name in it)."""
    from cmsopen.datasets import adler32_of

    paths = []
    for k, e in enumerate(files, 1):
        path = REPO / DOWNLOAD_DIR / e["filename"]
        label = f"file {k}/{len(files)} (record {e['record_id']}, index {e['index']})"
        if not path.is_file():
            return None, f"{label} is not in {DOWNLOAD_DIR}/"
        if path.stat().st_size != int(e["size_bytes"]) or adler32_of(path) != e["checksum"].split(":")[1]:
            return None, f"{label} does not match the registry's size and checksum"
        paths.append(path)
    return paths, ""


def verify_channel(name: str, recorded: dict[str, Any], rerun: dict[str, Any],
                   tmp: Path) -> tuple[Comparison, bool | None]:
    """Compare one channel with the record; also its summary.json with the run's saved copy, when that exists."""
    comparison = Comparison()
    recorded_values = {k: v for k, v in recorded.items() if k not in SKIPPED_KEYS}
    rerun_values = {k: v for k, v in _as_written(rerun).items() if k not in SKIPPED_KEYS}
    comparison.compare(recorded_values, rerun_values, f"channels.{name}")
    saved = REPO / "build" / "production" / name / "run1" / "summary.json"
    same = None
    if saved.exists():
        same = saved.read_bytes() == (tmp / name / "run1" / "summary.json").read_bytes()
        if not same:
            comparison.differences.append(f"channels.{name}: summary.json differs from the run's saved copy")
    return comparison, same


def verify_z_figure_fit(data: dict[str, Any], figs: Any) -> Comparison:
    """The Z figure is fitted again by examples/make_figures.py: its fit must be the recorded one too."""
    recorded = data["channels"]["Z_mumu"]["result"]
    fit = figs.fits[figs.main_model]
    comparison = Comparison()
    for key, value in (("peak_position_gev", fit.peak_position[0]), ("stat_error_gev", fit.peak_position[1]),
                       ("resolution_gev", fit.resolution[0]), ("chi2", fit.chi2), ("chi2_ndf", fit.chi2_ndf)):
        comparison.compare(recorded[key], float(value), f"figure fit {key}", tolerant=True)
    return comparison


def main(argv: list[str] | None = None) -> int:
    """Verify the numbers, then write the figures and their provenance; return the exit status."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--reason", default=REASON, help=f"recorded in the provenance file (default: {REASON!r})")
    parser.add_argument("--workers", type=int, default=4, help="analysis worker processes (default 4)")
    args = parser.parse_args(argv)
    start = time.perf_counter()
    production = REPO / PRODUCTION_JSON
    if not production.exists():
        print(f"REFUSED: {PRODUCTION_JSON} does not exist; the production run writes the first figures")
        return 2
    if _git("status", "--porcelain").strip():
        print("REFUSED: the working tree is not clean; commit first, so the provenance names the code that drew these")
        return 2
    data = json.loads(production.read_text())
    if hashlib.sha256((REPO / REGISTRY).read_bytes()).hexdigest() != data["registry_sha256"]:
        print(f"REFUSED: {REGISTRY} is not the registry that {PRODUCTION_JSON} records")
        return 2
    files = selected(load_registry(REPO))
    paths, why = local_files(files)
    if paths is None:
        print(f"REFUSED: {why}; nothing is downloaded here")
        return 2
    print(f"verified {len(paths)} local production files against the registry (size and adler32)", flush=True)
    head = _git("rev-parse", "HEAD").strip()
    build = REPO / "build"
    build.mkdir(exist_ok=True)
    timing: dict[str, float] = {}
    with tempfile.TemporaryDirectory(dir=build, prefix="figures_rerender_") as tmpname:
        tmp = Path(tmpname)
        channels, results, report, differences = {}, {}, {}, []
        for name, recorded in data["channels"].items():
            print(f"analysing {name} again ...", flush=True)
            t = time.perf_counter()
            try:
                channels[name], results[name] = _channel(name, paths, files, args.workers, outdir=tmp / name)
            except Exception as exc:  # any failure of the rerun: nothing is written
                message = sanitize(str(exc), paths, files)
                print(f"REFUSED: the analysis of {name} failed: {type(exc).__name__}: {message}")
                print("NOTHING WRITTEN")
                return 3
            timing[f"{name}_s"] = round(time.perf_counter() - t, 1)
            comparison, summary_same = verify_channel(name, recorded, channels[name], tmp)
            differences += comparison.differences
            report[name] = {"values_compared_exactly": comparison.exact,
                            "values_compared_within_1e-9": comparison.tolerant,
                            "largest_relative_deviation": comparison.largest,
                            "differences": len(comparison.differences),
                            "summary_json_identical_to_the_saved_run": summary_same}
            verdict = "FAIL" if comparison.differences else "OK"
            print(f"{verdict}: {name}: {comparison.exact:,} values exact, {comparison.tolerant:,} within a relative "
                  f"1e-9 (largest deviation {comparison.largest:.3g}), {len(comparison.differences)} differences; "
                  f"T1 in the rerun {channels[name]['t1']['summary_json_byte_identical']}; summary.json against the "
                  f"run's saved copy: {'not available' if summary_same is None else summary_same}", flush=True)
        import make_figures

        t = time.perf_counter()
        figs = make_figures.build(paths)
        fit_check = verify_z_figure_fit(data, figs)
        differences += fit_check.differences
        report["z_figure_fit"] = {"values_compared_within_1e-9": fit_check.tolerant,
                                  "largest_relative_deviation": fit_check.largest,
                                  "differences": len(fit_check.differences)}
        verdict = "FAIL" if fit_check.differences else "OK"
        print(f"{verdict}: the Z figure's own fit: {fit_check.tolerant} values within a relative 1e-9 "
              f"(largest deviation {fit_check.largest:.3g})", flush=True)
        if differences:
            for line in differences[:50]:
                print(f"DIFFERS: {sanitize(line, paths, files)}")
            print(f"NUMBERS DIFFER: {len(differences)} differences from {PRODUCTION_JSON}; NOTHING WRITTEN")
            return 3
        out = tmp / "figures"
        make_figures.write(figs, out, anonymous=True, jpsi=results.get("Jpsi_mumu"))
        timing["figures_s"] = round(time.perf_counter() - t, 1)
        written = sorted(f"docs/figures/{p.name}" for p in out.iterdir())
        if written != sorted(data["figures"]):
            print(f"REFUSED: the rerender wrote {written}, {PRODUCTION_JSON} lists {sorted(data['figures'])}")
            print("NOTHING WRITTEN")
            return 3
        for p in out.iterdir():
            shutil.copy2(p, REPO / "docs" / "figures" / p.name)
    hashes = {name: sha256(REPO / name) for name in written}
    record = {
        "schema_version": 1,
        "commit": head,
        "reason": args.reason,
        "verification": {"result": f"every value equals {PRODUCTION_JSON}", "relative_tolerance": RELATIVE_TOLERANCE,
                         "exact_except": list(TOLERANT_KEYS), "not_compared": list(SKIPPED_KEYS), "checks": report},
        "figures": hashes,
        "timing_s": {**timing, "total_s": round(time.perf_counter() - start, 1)},
    }
    (REPO / PROVENANCE).write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    print(f"ALL NUMBERS EQUAL: written {len(hashes)} files in docs/figures/ and {PROVENANCE} (commit {head[:12]}, "
          f"{record['timing_s']['total_s']} s)")
    return 0


if __name__ == "__main__":  # required for the worker processes on macOS
    sys.exit(main())
