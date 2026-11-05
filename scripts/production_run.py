"""The single production run: download, analysis of both channels, figures, T1-T7, results/production.json.

Run it ONCE, on the pre-registered production sample (results/production_files.json),
after ``scripts/production_preflight.py`` has passed.

States (dev/production_runbook.md):

- not started: neither the run lock nor results/production.json exists;
- downloaded: every file is in data/production/ and verified (no lock yet:
  nothing has been opened);
- analysis started: the run lock results/production_run.lock exists (the
  production files have been opened);
- complete: results/production.json exists.

Only "complete" blocks a new run (the single-run guard). After a failure
(any state but complete) the same command is run again: an attempt that
failed after the lock is resumed only if HEAD equals the lock's commit, the
working tree is clean (apart from the lock and the log) and the environment
is unchanged. If a code fix was committed after the failure, the command
refuses unless ``--code-fix-reason "..."`` is given; then the fix's commit must
descend from the lock's commit and the analysis choices (every channel's
configuration and the validation plan's constants) must be unchanged; the
new commit and the reason are recorded. Every attempt is numbered;
results/production_run.log (JSON lines, aggregate information only: times,
attempts, phases, exception types, commits) records each attempt's start,
phases and end (complete, failed with the phase and the exception type, or
interrupted when a killed attempt is found by the next one); results/production.json
carries the count, the failed attempts and the code fixes.

It refuses to run

- without ``--confirm-single-production-run`` (exit 2);
- if results/production.json exists (the run is complete; exit 3);
- if the preflight fails (exit 4);
- if a resume is not allowed (dirty tree, changed HEAD without a reason, changed
  analysis choices or environment; exit 8).

Steps of an attempt:

1. download every registered file into data/production/, four at a time by
   default (``--download-workers``, 1 to 4; measured in prompt 12: four streams
   gave 3.05 times the throughput of one), re-verifying every file already
   there by size and adler32 on every attempt: a truncated file is resumed, a
   corrupted one is fetched again from the first byte, never trusted, and a
   network error is retried after a backoff (cmsopen.datasets.fetch_many);
2. write the run lock (from here on the production files are opened; kept
   from an earlier attempt on a resume);
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
    python scripts/production_run.py --confirm-single-production-run [--workers N] [--download-workers N]
                                     [--channels Z_mumu Jpsi_mumu]

    python scripts/production_run.py --confirm-single-production-run --code-fix-reason "..."   # resume after a fix

Exit 0 on success; 5 on a download failure; 6 on an analysis failure; 7 if T1 fails (results are still written);
130 if interrupted with Ctrl-C.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import signal
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from production_preflight import (  # noqa: E402
    DOWNLOAD_DIR,
    GATES_DIR,
    INJECT_ENV,
    LOCK,
    LOG,
    PRODUCTION_JSON,
    REGISTRY,
    REPO,
    git,
    is_test_copy,
    load_registry,
    run_preflight,
    selected,
)

CHI2_NDF_BENCHMARK = 2.0  # T2 (dev/targets.md)
FILES_BENCHMARK = {31129: 12, 31123: 8}  # T4 (dev/targets.md): 20 files, 12 from record 31129, 8 from 31123
FIGURES_DIR = Path("docs") / "figures"


class RunLog:
    """results/production_run.log: one JSON object per line (time, event, attempt, phase, exception type, commits)."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def events(self) -> list[dict[str, Any]]:
        """Every event so far, in order."""
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text().splitlines() if line.strip()]

    def add(self, **event: Any) -> None:
        """Append one event and flush it to disk (it must survive a killed process)."""
        line = json.dumps({"time": time.strftime("%Y-%m-%dT%H:%M:%S%z"), **event}, sort_keys=True)
        with open(self.path, "a") as f:
            f.write(line + "\n")
            f.flush()
            os.fsync(f.fileno())

    def begin(self, head: str) -> int:
        """Close any attempt that never ended (killed) as interrupted, start the next one and return its number."""
        events = self.events()
        ended = {e["attempt"] for e in events if e["event"] == "attempt_end"}
        starts = [e["attempt"] for e in events if e["event"] == "attempt_start"]
        for n in starts:
            if n not in ended:
                phases = [e for e in events if e["event"] == "phase" and e["attempt"] == n]
                self.add(event="attempt_end", attempt=n, status="interrupted",
                         phase=phases[-1]["phase"] if phases else "start", last_seen=(phases or [{}])[-1].get("time"),
                         exception="none recorded (the process was killed or the machine stopped)")
        attempt = len(starts) + 1
        self.add(event="attempt_start", attempt=attempt, head=head)
        return attempt

    def summary(self, attempt: int) -> dict[str, Any]:
        """The attempt count, every failed or interrupted attempt and every code fix, for results/production.json."""
        events = self.events()
        return {
            "n": attempt,
            "failed": [{k: e.get(k) for k in ("attempt", "time", "status", "phase", "exception")}
                       for e in events if e["event"] == "attempt_end" and e["status"] != "complete"],
            "code_fixes": [{k: e[k] for k in ("attempt", "time", "from_head", "to_head", "reason")}
                           for e in events if e["event"] == "code_fix"],
        }


def analysis_config_sha256() -> str:
    """SHA-256 of the analysis choices: every registered channel's configuration and the validation plan's constants."""
    from cmsopen import validation as v
    from cmsopen.pipeline import CHANNELS

    choices = {
        "channels": {n: {**c.to_dict(), "validation_model": c.validation_model} for n, c in sorted(CHANNELS.items())},
        "validation": {k: getattr(v, k) for k in ("BARREL_MAX_ETA", "ENDCAP_MAX_ETA", "MIN_PAIRS", "PHI_EDGES",
                                                  "ETA_EDGES", "PT_EDGES", "PILEUP_EDGES", "WORKING_POINTS",
                                                  "COMPARED_MODELS")},
    }
    return hashlib.sha256(json.dumps(choices, sort_keys=True, default=dict).encode()).hexdigest()


def _checkpoint(log: RunLog, attempt: int, phase: str) -> None:
    """Record that ``phase`` starts; in a temporary test copy only, INJECT_ENV injects a failure or a kill here."""
    log.add(event="phase", attempt=attempt, phase=phase)
    inject = os.environ.get(INJECT_ENV, "") if is_test_copy(REPO) else ""
    if inject == f"raise:{phase}":
        raise RuntimeError(f"injected failure at {phase} (test)")
    if inject == f"kill:{phase}":
        os.kill(os.getpid(), signal.SIGKILL)


def restore_figures() -> None:
    """Put docs/figures/ back to HEAD: a failed or killed attempt may have written part of its figures there."""
    subprocess.run(["git", "checkout", "-q", "HEAD", "--", str(FIGURES_DIR)], cwd=REPO, check=True)
    subprocess.run(["git", "clean", "-fq", "--", str(FIGURES_DIR)], cwd=REPO, check=True)


def _dirty() -> list[str]:
    """Changed or untracked paths other than the run's own state (the lock and the log)."""
    out = git(REPO, "status", "--porcelain", "--untracked-files=all").stdout.splitlines()
    return [line for line in out if line.strip() and line[3:] not in (str(LOCK), str(LOG))]


def check_resume(lock: dict[str, Any], reason: str | None) -> tuple[int, dict[str, Any] | None]:
    """Whether an attempt may resume after the lock: (0, code fix to record or None) or (8, None) with a message."""
    restore_figures()
    dirty = _dirty()
    if dirty:
        print(f"REFUSED: resuming needs a clean working tree ({len(dirty)} changed or untracked paths besides the "
              f"lock and the log); commit or stash them")
        return 8, None
    head = git(REPO, "rev-parse", "HEAD").stdout.strip()
    from production_preflight import environment

    if environment()["sha256"] != lock["environment_sha256"]:
        print("REFUSED: the environment (Python or package versions) changed since the run started; restore it")
        return 8, None
    if head == lock["head"]:
        if reason:
            print("note: HEAD is the lock's commit; --code-fix-reason ignored")
        return 0, None
    if not reason:
        print(f"REFUSED: HEAD {head[:12]} differs from the lock's commit {lock['head'][:12]}; if a code fix was "
              'needed, run again with --code-fix-reason "<what was fixed and why>"')
        return 8, None
    if git(REPO, "merge-base", "--is-ancestor", lock["head"], head).returncode != 0:
        print(f"REFUSED: the lock's commit {lock['head'][:12]} is not an ancestor of HEAD {head[:12]}")
        return 8, None
    if analysis_config_sha256() != lock["analysis_config_sha256"]:
        print("REFUSED: the analysis choices changed (a channel configuration or a validation plan constant differs "
              "from the frozen one); a code fix may not change them")
        return 8, None
    return 0, {"from_head": lock["head"], "to_head": head, "reason": reason}


def _label(e: dict[str, Any], k: int, n: int) -> str:
    return f"file {k}/{n} (record {e['record_id']}, index {e['index']})"


def sanitize(text: str, paths: list[Path], files: list[dict[str, Any]]) -> str:
    """``text`` with every production file's path and name replaced by its record and index."""
    for k, (p, e) in enumerate(zip(paths, files, strict=False), 1):
        text = text.replace(str(p), _label(e, k, len(files)))
    for k, e in enumerate(files, 1):
        text = text.replace(e["filename"], _label(e, k, len(files)))
    return text


def _download(files: list[dict[str, Any]], workers: int, backoff: float) -> list[Path] | None:
    """Every registered file, ``workers`` at a time, each resumable and verified (cmsopen.datasets.fetch_many)."""
    from cmsopen.datasets import DownloadError, fetch_many

    entries = [{"url": e["https_url"], "size": int(e["size_bytes"]), "adler32": e["checksum"].split(":")[1]}
               for e in files]

    def done(k: int, path: Path) -> None:
        print(f"downloaded and verified {_label(files[k], k + 1, len(files))}, {int(files[k]['size_bytes']):,} bytes",
              flush=True)

    try:
        return fetch_many(entries, REPO / DOWNLOAD_DIR, workers=workers, backoff=backoff, on_done=done)
    except (DownloadError, OSError) as exc:
        message = sanitize(str(exc), [], files)
        print(f"FAIL: download: {type(exc).__name__}: {message} (run the same command again to resume)")
        return None


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


def _channel(name: str, paths: list[Path], files: list[dict[str, Any]], workers: int,
             outdir: Path | None = None) -> tuple[dict[str, Any], Any]:
    """Every result of one channel, and its AnalysisResult (for the figures); ``outdir`` default: build/production."""
    from cmsopen import analyze

    out = REPO / "build" / "production" / name if outdir is None else outdir
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


def run_state() -> str:
    """not started, downloaded, analysis started or complete (see the module docstring)."""
    if (REPO / PRODUCTION_JSON).exists():
        return "complete"
    if (REPO / LOCK).exists():
        return "analysis started"
    if any(e["event"] == "downloaded" for e in RunLog(REPO / LOG).events()):
        return "downloaded"
    return "not started"


def main(argv: list[str] | None = None) -> int:
    """Run the production analysis once (resuming a failed attempt when allowed)."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--confirm-single-production-run", action="store_true",
                        help="required: this command runs the production analysis, once")
    parser.add_argument("--workers", type=int, default=4, help="analysis worker processes (default 4)")
    parser.add_argument("--download-workers", type=int, default=4, choices=range(1, 5), metavar="N",
                        help="concurrent downloads, 1 to 4 (default 4)")
    parser.add_argument("--channels", nargs="+", default=["Z_mumu", "Jpsi_mumu"])
    parser.add_argument("--no-network", action="store_true", help="skip the preflight's reachability check")
    parser.add_argument("--code-fix-reason", default=None, metavar="TEXT",
                        help="resume after a code fix committed since the run started: what was fixed and why")
    parser.add_argument("--retry-backoff", type=float, default=10.0, help=argparse.SUPPRESS)  # seconds (tests)
    args = parser.parse_args(argv)
    if not args.confirm_single_production_run:
        print("REFUSED: pass --confirm-single-production-run (the production analysis is run once)")
        return 2
    state = run_state()
    print(f"run state: {state}", flush=True)
    if state == "complete":
        print(f"REFUSED: single-run guard: {PRODUCTION_JSON} exists; the production run is complete")
        return 3
    lock = json.loads((REPO / LOCK).read_text()) if state == "analysis started" else None
    code_fix = None
    if lock is not None:
        rc, code_fix = check_resume(lock, args.code_fix_reason)
        if rc:
            return rc
    elif args.code_fix_reason:
        print("note: no run lock (nothing has been opened yet); --code-fix-reason ignored")
    start = time.perf_counter()
    pf = run_preflight(REPO, allow_downloaded=True, network=not args.no_network, allow_test_hook=is_test_copy(REPO))
    if not pf.passed:
        print("REFUSED: the preflight failed (see the FAIL lines above)")
        return 4
    log = RunLog(REPO / LOG)
    attempt = log.begin(pf.head)
    print(f"attempt {attempt} started (log: {LOG})", flush=True)
    phase = "start"

    def failed(exc: BaseException, rc: int, message: str) -> int:
        log.add(event="attempt_end", attempt=attempt, status="failed", phase=phase, exception=type(exc).__name__)
        print(message)
        return rc

    if code_fix is not None:
        log.add(event="code_fix", attempt=attempt, **code_fix)
        assert lock is not None
        lock.update(head=code_fix["to_head"], code_fixes=[*lock.get("code_fixes", []), code_fix])
        (REPO / LOCK).write_text(json.dumps(lock, indent=2) + "\n")
        print(f"code fix recorded: {code_fix['from_head'][:12]} -> {code_fix['to_head'][:12]}", flush=True)
    registry = load_registry(REPO)
    files = selected(registry)
    phase = "download"
    _checkpoint(log, attempt, phase)
    t = time.perf_counter()
    paths = _download(files, args.download_workers, args.retry_backoff)
    if paths is None:
        log.add(event="attempt_end", attempt=attempt, status="failed", phase=phase, exception="DownloadError")
        return 5
    log.add(event="downloaded", attempt=attempt, n_files=len(paths))
    timing = {"download_s": round(time.perf_counter() - t, 1)}
    try:
        phase = "lock"
        if lock is None:
            lock = {"first_head": pf.head, "head": pf.head, "environment_sha256": pf.environment["sha256"],
                    "analysis_config_sha256": analysis_config_sha256(),
                    "started": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
            (REPO / LOCK).write_text(json.dumps(lock, indent=2) + "\n")
            print(f"run lock written: {LOCK} (the production files are opened from here on)", flush=True)
        else:
            print(f"run lock kept: {LOCK} (resuming after the lock)", flush=True)
        _checkpoint(log, attempt, phase)
        channels, results = {}, {}
        for name in args.channels:
            phase = f"analysis {name}"
            _checkpoint(log, attempt, phase)
            print(f"analysing {name} ...", flush=True)
            t = time.perf_counter()
            channels[name], results[name] = _channel(name, paths, files, args.workers)
            timing[f"{name}_s"] = round(time.perf_counter() - t, 1)
            res = channels[name]["result"]
            print(f"{name}: {res['model']}, peak {res['peak_position_gev']:.4f} +- {res['stat_error_gev']:.4f} GeV, "
                  f"chi2/ndf {res['chi2_ndf']:.3f}; T1 {channels[name]['t1']['summary_json_byte_identical']}",
                  flush=True)
        phase = "figures"
        _checkpoint(log, attempt, phase)
        t = time.perf_counter()
        figures = _figures(paths, results.get("Jpsi_mumu"))
        timing["figures_s"] = round(time.perf_counter() - t, 1)
        print(f"figures written: {len(figures)} files in docs/figures/ (figures, captions, README)", flush=True)
        phase = "results"
        _checkpoint(log, attempt, phase)
    except KeyboardInterrupt as exc:
        restore_figures()
        return failed(exc, 130, "FAIL: interrupted; run the same command again to resume")
    except Exception as exc:  # any analysis failure: recorded; the lock stays (the files have been opened)
        restore_figures()
        return failed(exc, 6, f"FAIL: the production analysis failed in phase '{phase}': {type(exc).__name__}: "
                              f"{sanitize(str(exc), paths, files)} (fix the cause, then run the same command again)")

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
        "first_head": lock["first_head"],
        "freeze_commit": pf.freeze_commit,
        "analysis_config_sha256": lock["analysis_config_sha256"],
        "environment": pf.environment,
        "gates": gates,
        "attempts": log.summary(attempt),
        "timing_s": {**timing, "total_s": round(time.perf_counter() - start, 1)},
    }
    data["targets"] = targets(data, gates)
    (REPO / PRODUCTION_JSON).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    log.add(event="attempt_end", attempt=attempt, status="complete", phase=phase)
    print(f"written: {PRODUCTION_JSON} (attempt {attempt}, total {data['timing_s']['total_s']} s)")
    t1_ok = all(c["t1"]["summary_json_byte_identical"] for c in channels.values())
    if not t1_ok:
        print("FAIL: T1: the two analysis runs gave different summary.json files")
        return 7
    print("PRODUCTION RUN COMPLETE")
    return 0


if __name__ == "__main__":  # required for the worker processes on macOS
    sys.exit(main())
