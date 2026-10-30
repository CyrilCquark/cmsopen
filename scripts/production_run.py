"""The single production run: download, analysis of both channels, figures, T1-T7, results/production.json.

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
3. per channel (Z_mumu and Jpsi_mumu): the analysis with validation twice,
   once with worker processes and once serially, into
   build/production/<channel>/ (T1: the two summary.json files must be
   byte-identical, which also checks parallel against serial); the fits of
   Run 2012B and Run 2012C separately (T6); one fit per file (the per-file
   table);
4. the final figures into docs/figures/: z_* and the muon and cutflow figures
   (examples/make_figures.py) and jpsi_* (the Jpsi_mumu analysis's own
   figures, same format and labels); the data are described by record and
   size, never by file name;
5. results/production.json: the README's schema (the Z headline), every
   channel's result with its raw and scaled statistical errors, fit-choice
   spread, cutflow, validation tables and systematics summary, T6 and the
   per-file table; the T1-T7 table (controlling benchmark versus observed,
   dev/targets.md); the files by record, size and checksum; the git HEAD, the
   freeze commit, the environment with its SHA-256, the recorded gates and the
   timings.

No production file name is printed or written into the repository (the
per-channel analysis outputs, which list their input files, stay in the
gitignored build/production/; error messages are printed with each file
replaced by its record and index).

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
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from production_preflight import (  # noqa: E402
    DOWNLOAD_DIR,
    GATES_DIR,
    LOCK,
    PRODUCTION_JSON,
    REGISTRY,
    REPO,
    load_registry,
    run_preflight,
    selected,
)

CHI2_NDF_BENCHMARK = 2.0  # T2 (dev/targets.md)
FILES_BENCHMARK = {31129: 12, 31123: 8}  # T4 (dev/targets.md): 20 files, 12 from record 31129, 8 from 31123


def _label(e: dict[str, Any], k: int, n: int) -> str:
    return f"file {k}/{n} (record {e['record_id']}, index {e['index']})"


def sanitize(text: str, paths: list[Path], files: list[dict[str, Any]]) -> str:
    """``text`` with every production file's path and name replaced by its record and index."""
    for k, (p, e) in enumerate(zip(paths, files, strict=False), 1):
        text = text.replace(str(p), _label(e, k, len(files)))
    for k, e in enumerate(files, 1):
        text = text.replace(e["filename"], _label(e, k, len(files)))
    return text


def _download(files: list[dict[str, Any]]) -> list[Path] | None:
    from cmsopen.datasets import DownloadError, fetch_example_data

    paths = []
    for k, e in enumerate(files, 1):
        label = f"{_label(e, k, len(files))}, {int(e['size_bytes']):,} bytes"
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
        "scale_factor": scale_factor(fit.chi2_ndf),
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


PER_FILE_KEYS = ("model", "peak_position_gev", "stat_error_gev", "stat_error_scaled_gev", "resolution_gev",
                 "chi2_ndf", "yields_reliable", "offset_from_pdg_gev", "n_events", "n_pairs_in_fit_range")


def _per_file(name: str, paths: list[Path], files: list[dict[str, Any]], workers: int) -> list[dict[str, Any]]:
    """The channel's default fit on each file alone: pole (peak position), errors, chi2/ndf (or why it failed)."""
    from cmsopen import AnalysisError, analyze

    rows = []
    for k, (p, e) in enumerate(zip(paths, files, strict=True), 1):
        row: dict[str, Any] = {"file": k, "record_id": e["record_id"], "run_period": e["run_period"],
                               "index": e["index"], "size_bytes": int(e["size_bytes"])}
        try:
            r = analyze(p, channel=name, n_workers=workers, stability=False, verbose=False)
        except AnalysisError as exc:
            row.update(status="failed", reason=sanitize(str(exc), paths, files))
        else:
            f = _fit_dict(r)
            row.update(status="fitted", **{key: f[key] for key in PER_FILE_KEYS})
        rows.append(row)
    return rows


def _channel(name: str, paths: list[Path], files: list[dict[str, Any]], workers: int) -> tuple[dict[str, Any], Any]:
    """Every result of one channel, and its AnalysisResult (for the figures)."""
    from cmsopen import analyze

    out = REPO / "build" / "production" / name
    timing: dict[str, float] = {}
    t = time.perf_counter()
    first = analyze(paths, channel=name, n_workers=workers, validation=True, verbose=False, outdir=out / "run1")
    timing["analysis_parallel_s"] = time.perf_counter() - t
    t = time.perf_counter()
    analyze(paths, channel=name, n_workers=None, validation=True, verbose=False, outdir=out / "run2")
    timing["analysis_serial_s"] = time.perf_counter() - t
    run1 = (out / "run1" / "summary.json").read_bytes()
    same = run1 == (out / "run2" / "summary.json").read_bytes()
    periods = [e["run_period"].removeprefix("Run") for e in files]
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
    t = time.perf_counter()
    per_file = _per_file(name, paths, files, workers)
    timing["per_file_s"] = time.perf_counter() - t
    v = first.validation
    alternate = first.alternate_fit
    result = {
        "result": _fit_dict(first),
        "alternate_fit": None if alternate is None else {
            "model": alternate.model_name, "peak_position_gev": alternate.peak_position[0],
            "stat_error_gev": alternate.peak_position[1], "chi2_ndf": alternate.chi2_ndf},
        "fit_choice_spread_gev": first.stability.std if first.stability else None,
        "fit_choice_spread_label": "standard deviation of the peak over the channel's fit ranges x bin widths",
        "cutflow": json.loads(run1)["cutflow"],
        "n_files": len(first.files),
        "validation": v.to_dict() if v is not None else None,
        "warnings": [sanitize(w, paths, files) for w in first.warnings],
        "t1": {"summary_json_byte_identical": same, "runs": ["parallel", "serial"]},
        "t2": {"chi2_ndf": first.fit.chi2_ndf, "benchmark": CHI2_NDF_BENCHMARK,
               "yields_reliable": first.fit.yields_reliable,
               "met": first.fit.chi2_ndf <= CHI2_NDF_BENCHMARK and first.fit.yields_reliable},
        "t6": t6,
        "per_file": per_file,
        "timing_s": {k: round(x, 1) for k, x in timing.items()},
    }
    return result, first


def _figures(paths: list[Path], jpsi: Any) -> list[str]:
    sys.path.insert(0, str(REPO / "examples"))
    import make_figures

    figs = make_figures.write(make_figures.build(paths), REPO / "docs" / "figures", anonymous=True, jpsi=jpsi)
    written = [p for files in figs.files.values() for p in files]
    extra = [REPO / "docs" / "figures" / name for name in ("z_peak_fit_caption.md", "README.md")]
    return sorted(str(p.relative_to(REPO)) for p in [*written, *extra])


def targets(data: dict[str, Any], gates: dict[str, Any]) -> dict[str, Any]:
    """T1-T7 (dev/targets.md): each target's controlling benchmark and the observed value, labelled, with met/not."""
    ch = data["channels"]
    by_record = Counter(f["record_id"] for f in data["files"])
    analysed = {name: c["n_files"] for name, c in ch.items()}
    studies = {name: sorted({e["study"] for e in (c["validation"] or {}).get("entries", [])}) for name, c in ch.items()}
    t3_obs = {name: {"offset_from_pdg_gev": c["result"]["offset_from_pdg_gev"],
                     "stat_error_gev": c["result"]["stat_error_gev"],
                     "stat_error_scaled_gev": c["result"]["stat_error_scaled_gev"],
                     "fit_choice_spread_gev": c["fit_choice_spread_gev"],
                     "diagnostic_studies": studies[name]} for name, c in ch.items()}
    t5_obs = {"cutflow": all(c["cutflow"] for c in ch.values()), "files_by_record_and_size": bool(data["files"]),
              "git_head": bool(data["git_head"]), "environment_sha256": bool(data["environment"].get("sha256")),
              "attempts": "attempts" in data, "timings": bool(data["timing_s"])}
    n_benchmark = sum(FILES_BENCHMARK.values())
    return {
        "T1": {"benchmark": "summary.json byte-identical on a repeated run (parallel, then serial), every channel",
               "observed": {n: c["t1"]["summary_json_byte_identical"] for n, c in ch.items()},
               "met": all(c["t1"]["summary_json_byte_identical"] for c in ch.values())},
        "T2": {"benchmark": f"chi2/ndf <= {CHI2_NDF_BENCHMARK} with a positive background in the fit range",
               "observed": {n: {"chi2_ndf": c["t2"]["chi2_ndf"], "yields_reliable": c["t2"]["yields_reliable"]}
                            for n, c in ch.items()},
               "met": {n: c["t2"]["met"] for n, c in ch.items()}},
        "T3": {"benchmark": "offset from PDG with raw and scaled stat. errors, fit-choice spread and the diagnostic "
                            "studies (barrel/endcap, mu+ vs mu-) reported; no numeric target on the mass",
               "observed": t3_obs,
               "met": all({"region", "phi(mu+)", "phi(mu-)"} <= set(s) for s in studies.values())},
        "T4": {"benchmark": {"n_files": n_benchmark, "by_record": {str(k): v for k, v in FILES_BENCHMARK.items()}},
               "observed": {"n_files": len(data["files"]),
                            "by_record": {str(k): v for k, v in sorted(by_record.items())},
                            "analysed_per_channel": analysed},
               "met": dict(by_record) == FILES_BENCHMARK and all(n == n_benchmark for n in analysed.values())},
        "T5": {"benchmark": "cutflow, files by record and size, commit, environment hash, attempts and timings "
                            "recorded; the README block is checked afterwards by scripts/check_readme_numbers.py",
               "observed": t5_obs, "met": all(t5_obs.values())},
        "T6": {"benchmark": "2012B and 2012C peak and resolution with differences and combined stat. errors, "
                            "every channel (reported, no threshold)",
               "observed": {n: {k: v for k, v in c["t6"].items() if k != "periods"} for n, c in ch.items()},
               "met": all(len(c["t6"]["periods"]) == 2 for c in ch.values())},
        "T7": {"benchmark": "full test suite and quality gates (coverage >= 90 %, mypy and ruff clean) passed at "
                            "the production HEAD",
               "observed": gates,
               "met": gates.get("pytest_rc") == 0 and gates.get("quality_rc") == 0
               and gates.get("head") == data["git_head"]},
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
        channels, results = {}, {}
        for name in args.channels:
            print(f"analysing {name} ...", flush=True)
            t = time.perf_counter()
            channels[name], results[name] = _channel(name, paths, files, args.workers)
            timing[f"{name}_s"] = round(time.perf_counter() - t, 1)
            res = channels[name]["result"]
            print(f"{name}: {res['model']}, peak {res['peak_position_gev']:.4f} +- {res['stat_error_gev']:.4f} GeV, "
                  f"chi2/ndf {res['chi2_ndf']:.3f}; T1 {channels[name]['t1']['summary_json_byte_identical']}",
                  flush=True)
        t = time.perf_counter()
        figures = _figures(paths, results.get("Jpsi_mumu"))
        timing["figures_s"] = round(time.perf_counter() - t, 1)
        print(f"figures written: {len(figures)} files in docs/figures/ (figures, captions, README)", flush=True)
    except Exception as exc:  # any analysis failure: reported; the lock stays (the files have been opened)
        print(f"FAIL: the production analysis failed: {type(exc).__name__}: {sanitize(str(exc), paths, files)}")
        return 6

    headline = channels.get("Z_mumu") or next(iter(channels.values()))
    res = headline["result"]
    from importlib import metadata

    record = REPO / GATES_DIR / f"{pf.head}.json"
    gates = json.loads(record.read_text()) if record.exists() else {}
    data: dict[str, Any] = {
        "schema_version": 1,
        "sample": {"n_files": len(files), "n_events": res["n_events"], "n_pairs": res["n_pairs_in_fit_range"]},
        "fit": {k: res[k] for k in ("model", "fit_range_gev", "peak_position_gev", "stat_error_gev", "resolution_gev",
                                    "resolution_error_gev", "chi2", "ndf")},
        "pdg": {"mass_gev": res["pdg_mass_gev"], "source": f"particle {metadata.version('particle')}"},
        "fit_choice_spread_gev": headline["fit_choice_spread_gev"],
        "channels": channels,
        "figures": figures,
        "files": [{"record_id": e["record_id"], "run_period": e["run_period"], "index": e["index"],
                   "size_bytes": int(e["size_bytes"]), "checksum": e["checksum"]} for e in files],
        "registry_sha256": hashlib.sha256((REPO / REGISTRY).read_bytes()).hexdigest(),
        "git_head": pf.head,
        "freeze_commit": pf.freeze_commit,
        "environment": pf.environment,
        "gates": gates,
        "attempts": 1,
        "timing_s": {**timing, "total_s": round(time.perf_counter() - start, 1)},
    }
    data["targets"] = targets(data, gates)
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
