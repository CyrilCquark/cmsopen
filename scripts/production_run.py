"""The single production run: download, figures, analysis, T1/T2/T6, results/production.json.

Run it ONCE, on the pre-registered production sample (results/production_files.json),
after ``scripts/production_preflight.py`` has passed. It refuses to run

- without ``--confirm-single-production-run`` (exit 2);
- if results/production.json or the run lock results/production_run.lock exists
  (the single-run guard; exit 3);
- if the preflight fails (exit 4).

Steps:

1. download every registered file into data/production/ with the verified,
   resumable fetch of cmsopen.datasets (size and adler32 checked; an
   interrupted download is resumed by running the command again, since
   nothing has been opened yet);
2. write the run lock (from here on the production files are opened);
3. the final figures into docs/figures/ (examples/make_figures.py; the data
   are described by record and size, never by file name);
4. per channel: the analysis with validation twice, once with worker
   processes and once serially, into build/production/<channel>/ (T1: the two
   summary.json files must be byte-identical, which also checks parallel
   against serial); the fits of Run 2012B and Run 2012C separately (T6);
5. results/production.json: the README's schema (the Z headline), every
   channel's result, T1, T2 and T6, the files by record, size and checksum,
   the git HEAD, the freeze commit and the environment with its SHA-256.

No production file name is printed or written into the repository (the
per-channel analysis outputs, which list their input files, stay in the
gitignored build/production/).

Usage:
    python scripts/production_run.py --confirm-single-production-run [--workers N] [--channels Z_mumu Jpsi_mumu]

Exit 0 on success; 5 on a download failure; 6 on an analysis failure; 7 if T1 fails (results are still written).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from production_preflight import (  # noqa: E402
    DOWNLOAD_DIR,
    LOCK,
    PRODUCTION_JSON,
    REGISTRY,
    REPO,
    load_registry,
    run_preflight,
    selected,
)

CHI2_NDF_BENCHMARK = 2.0  # T2 (dev/targets.md)


def _download(files: list[dict[str, Any]]) -> list[Path] | None:
    from cmsopen.datasets import DownloadError, fetch_example_data

    paths = []
    for k, e in enumerate(files, 1):
        label = f"file {k}/{len(files)} (record {e['record_id']}, index {e['index']}, {int(e['size_bytes']):,} bytes)"
        try:
            path = fetch_example_data(REPO / DOWNLOAD_DIR, url=e["https_url"], size=int(e["size_bytes"]),
                                      adler32=e["checksum"].split(":")[1], progress=False)
        except (DownloadError, OSError) as exc:
            kind = type(exc).__name__
            print(f"FAIL: download of {label}: {kind} (run the same command again to resume)")
            return None
        print(f"downloaded and verified {label}", flush=True)
        paths.append(path)
    return paths


def _figures(paths: list[Path]) -> list[str]:
    sys.path.insert(0, str(REPO / "examples"))
    import make_figures

    figs = make_figures.write(make_figures.build(paths), REPO / "docs" / "figures", anonymous=True)
    return sorted(str(p.relative_to(REPO)) for files in figs.files.values() for p in files)


def _fit_dict(r: Any) -> dict[str, Any]:
    from cmsopen.fitting import pdg_mass_width
    from cmsopen.validation import scale_factor

    fit = r.fit
    pos, err = fit.peak_position
    res, res_err = fit.resolution
    pdg = pdg_mass_width(r.config.resonance)[0]
    return {
        "model": fit.model_name,
        "fit_range_gev": list(fit.fit_range),
        "peak_position_gev": pos,
        "stat_error_gev": err,
        "stat_error_scaled_gev": err * scale_factor(fit.chi2_ndf),
        "resolution_gev": res,
        "resolution_error_gev": res_err,
        "chi2": fit.chi2,
        "ndf": fit.ndf,
        "chi2_ndf": fit.chi2_ndf,
        "p_value": fit.p_value,
        "yields_reliable": fit.yields_reliable,
        "signal_yield": list(fit.signal_yield),
        "background_yield": list(fit.background_yield),
        "pdg_mass_gev": pdg,
        "offset_from_pdg_gev": pos - pdg,
        "n_events": r.n_events,
        "n_pairs_in_fit_range": fit.n_entries,
    }


def _channel(name: str, paths: list[Path], periods: list[str], workers: int) -> dict[str, Any]:
    from cmsopen import analyze

    out = REPO / "build" / "production" / name
    timing: dict[str, float] = {}
    t = time.perf_counter()
    first = analyze(paths, channel=name, n_workers=workers, validation=True, verbose=False, outdir=out / "run1")
    timing["analysis_parallel_s"] = time.perf_counter() - t
    t = time.perf_counter()
    analyze(paths, channel=name, n_workers=None, validation=True, verbose=False, outdir=out / "run2")
    timing["analysis_serial_s"] = time.perf_counter() - t
    same = (out / "run1" / "summary.json").read_bytes() == (out / "run2" / "summary.json").read_bytes()
    by_period = {}
    for period in sorted(set(periods)):
        sub = [p for p, q in zip(paths, periods, strict=True) if q == period]
        t = time.perf_counter()
        r = analyze(sub, channel=name, n_workers=workers, stability=False, verbose=False)
        timing[f"analysis_{period}_s"] = time.perf_counter() - t
        by_period[period] = {"n_files": len(sub), **_fit_dict(r)}
    t6: dict[str, Any] = {"periods": by_period}
    if len(by_period) == 2:
        (a, pa), (b, pb) = sorted(by_period.items())
        for key in ("peak_position_gev", "resolution_gev"):
            err_key = "stat_error_gev" if key == "peak_position_gev" else "resolution_error_gev"
            diff, err = pa[key] - pb[key], math.hypot(pa[err_key], pb[err_key])
            t6[f"{key}_difference_{a}_minus_{b}"] = {"value": diff, "error": err, "in_sigma": diff / err}
    v = first.validation
    return {
        "result": _fit_dict(first),
        "fit_choice_spread_gev": first.stability.std if first.stability else None,
        "validation": v.summary.to_dict() if v is not None else None,
        "t1": {"summary_json_byte_identical": same, "runs": ["parallel", "serial"]},
        "t2": {"chi2_ndf": first.fit.chi2_ndf, "benchmark": CHI2_NDF_BENCHMARK,
               "yields_reliable": first.fit.yields_reliable,
               "met": first.fit.chi2_ndf <= CHI2_NDF_BENCHMARK and first.fit.yields_reliable},
        "t6": t6,
        "timing_s": {k: round(x, 1) for k, x in timing.items()},
    }


def main(argv: list[str] | None = None) -> int:
    """Run the production analysis once."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--confirm-single-production-run", action="store_true",
                        help="required: this command runs the production analysis, once")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--channels", nargs="+", default=["Z_mumu", "Jpsi_mumu"])
    parser.add_argument("--no-network", action="store_true", help="skip the preflight's reachability check")
    args = parser.parse_args(argv)
    if not args.confirm_single_production_run:
        print("REFUSED: pass --confirm-single-production-run (the production analysis is run once)")
        return 2
    existing = [str(p) for p in (PRODUCTION_JSON, LOCK) if (REPO / p).exists()]
    if existing:
        print(f"REFUSED: single-run guard: {', '.join(existing)} exists; the production run has already started")
        return 3
    start = time.perf_counter()
    pf = run_preflight(REPO, allow_downloaded=True, network=not args.no_network)
    if not pf.passed:
        print("REFUSED: the preflight failed (see the FAIL lines above)")
        return 4
    registry = load_registry(REPO)
    files = selected(registry)
    t = time.perf_counter()
    paths = _download(files)
    if paths is None:
        return 5
    timing = {"download_s": round(time.perf_counter() - t, 1)}
    (REPO / LOCK).write_text(json.dumps({"head": pf.head, "environment_sha256": pf.environment["sha256"],
                                         "started": time.strftime("%Y-%m-%dT%H:%M:%S%z")}, indent=2) + "\n")
    print(f"run lock written: {LOCK} (the production files are opened from here on)", flush=True)
    try:
        t = time.perf_counter()
        figures = _figures(paths)
        timing["figures_s"] = round(time.perf_counter() - t, 1)
        print(f"figures written: {len(figures)} figure files, the caption and the README in docs/figures/", flush=True)
        periods = [e["run_period"].removeprefix("Run") for e in files]
        channels = {}
        for name in args.channels:
            print(f"analysing {name} ...", flush=True)
            channels[name] = _channel(name, paths, periods, args.workers)
            res = channels[name]["result"]
            print(f"{name}: {res['model']}, peak {res['peak_position_gev']:.4f} +- {res['stat_error_gev']:.4f} GeV, "
                  f"chi2/ndf {res['chi2_ndf']:.3f}; T1 {channels[name]['t1']['summary_json_byte_identical']}",
                  flush=True)
    except Exception as exc:  # any analysis failure: reported; the lock stays (the files have been opened)
        print(f"FAIL: the production analysis failed: {type(exc).__name__}: {exc}")
        return 6

    headline = channels.get("Z_mumu") or next(iter(channels.values()))
    res = headline["result"]
    from importlib import metadata

    data = {
        "schema_version": 1,
        "sample": {"n_files": len(files), "n_events": res["n_events"], "n_pairs": res["n_pairs_in_fit_range"]},
        "fit": {k: res[k] for k in ("model", "fit_range_gev", "peak_position_gev", "stat_error_gev", "resolution_gev",
                                    "resolution_error_gev", "chi2", "ndf")},
        "pdg": {"mass_gev": res["pdg_mass_gev"], "source": f"particle {metadata.version('particle')}"},
        "fit_choice_spread_gev": headline["fit_choice_spread_gev"],
        "channels": channels,
        "files": [{"record_id": e["record_id"], "run_period": e["run_period"], "index": e["index"],
                   "size_bytes": int(e["size_bytes"]), "checksum": e["checksum"]} for e in files],
        "registry_sha256": hashlib.sha256((REPO / REGISTRY).read_bytes()).hexdigest(),
        "git_head": pf.head,
        "freeze_commit": pf.freeze_commit,
        "environment": pf.environment,
        "timing_s": {**timing, "total_s": round(time.perf_counter() - start, 1)},
    }
    (REPO / PRODUCTION_JSON).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    print(f"written: {PRODUCTION_JSON} (total {data['timing_s']['total_s']} s)")
    t1_ok = all(c["t1"]["summary_json_byte_identical"] for c in channels.values())
    if not t1_ok:
        print("FAIL: T1: the two analysis runs gave different summary.json files")
        return 7
    print("PRODUCTION RUN COMPLETE")
    return 0


if __name__ == "__main__":  # required for the worker processes on macOS
    sys.exit(main())
