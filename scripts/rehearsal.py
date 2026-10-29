"""Rehearse the production code path on the 6-file development set (dev/development_set.md).

Every number is a "development observation (6-file development set)"; none
of it enters README.md, docs/, notebooks/ or results/production.json, and
nothing is re-selected (the defaults are only confirmed).

Stage ``confirm`` (writes build/rehearsal/):
  - per file and channel: ``analyze(file, n_workers=N)``, timed (time per
    file), keeping the chosen-pair masses;
  - parallel equals serial on the first 2 files (Z_mumu, to_dict and summary);
  - per channel: ``analyze(all 6 files, n_workers=N, validation=True)``, the
    production path, timed; its masses must equal the per-file masses
    concatenated in order;
  - the confirmation table of the headline fits. Exit 3 (stop) if a fit
    failed, a parameter is on a bound, the background is not positive or
    chi2/ndf > 2.0.
Stage ``rest`` (after ``confirm`` passed): the statistics-scaling table
(cumulative 1, 2, 4, 6 files), the validation tables and figures, and the
per-file and per-run consistency.

Peak memory is the largest resident set size of this process and of its
(finished) worker processes, from getrusage.

Usage:
    python scripts/rehearsal.py confirm [--workers N]
    python scripts/rehearsal.py rest
"""

from __future__ import annotations

import argparse
import json
import math
import pickle
import resource
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
from scipy import stats

from cmsopen import AnalysisError, analyze, make_histogram
from cmsopen.fitting import FitError, fit_mass_peak, pdg_mass_width
from cmsopen.pipeline import CHANNELS

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "build" / "rehearsal"
LABEL = "development observation (6-file development set)"
CHANNEL_NAMES = ("Z_mumu", "Jpsi_mumu")
CHI2_NDF_LIMIT = 2.0  # T2 (dev/targets.md); here only a stop criterion of the rehearsal


def development_files() -> list[tuple[str, Path]]:
    """(run, path) of the 6 files in the fixed order: the original file, then the new ones in index order."""
    dev = json.loads((REPO / "dev" / "development_set.json").read_text())
    run = {31129: "2012C", 31123: "2012B"}
    files = [("2012C", REPO / "data" / dev["original_development_file"])]
    files += [(run[f["record_id"]], REPO / "data" / f["filename"]) for f in dev["files"]]
    for _, p in files:
        if not p.exists():
            sys.exit(f"error: {p} is missing; download the development set first (dev/development_set.md)")
    return files


def peak_rss_mb() -> tuple[float, float]:
    """Peak resident set size of this process and of its largest finished child, in MB (macOS: bytes)."""
    scale = 1.0 if sys.platform == "darwin" else 1024.0
    own = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * scale / 1e6
    kids = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss * scale / 1e6
    return own, kids


def headline(fit: Any, channel: str) -> dict[str, Any]:
    """The confirmation quantities of one headline fit."""
    pdg = pdg_mass_width(CHANNELS[channel].resonance)[0]
    pos, err = fit.peak_position
    grid = np.linspace(*fit.fit_range, 2001)
    return {
        "model": fit.model_name,
        "converged": True,  # fit_mass_peak raises FitError otherwise
        "on_bound": list(fit.on_bound),
        "background_positive": bool(np.all(fit.background(grid) >= 0)),
        "yields_reliable": bool(fit.yields_reliable),
        "chi2_ndf": fit.chi2_ndf,
        "p_value": fit.p_value,
        "position": pos,
        "error": err,
        "offset": pos - pdg,
        "signal": fit.signal_yield,
        "background": fit.background_yield,
        "n_entries": fit.n_entries,
    }


def fit_masses(masses: np.ndarray, channel: str) -> Any:
    """The channel's headline fit (its default model and settings) of a set of masses, as analyze() does it."""
    cfg = CHANNELS[channel]
    hist = make_histogram(masses, bins=cfg.bins, range=cfg.mass_range)
    return fit_mass_peak(hist, model=cfg.model, fit_range=cfg.fit_range, poly_degree=cfg.poly_degree,
                         natural_width=pdg_mass_width(cfg.resonance)[2], cb_n=cfg.cb_n)


def confirm(workers: int) -> int:
    """Stage 1: timing, parallel = serial, the 6-file production path, and the confirmation table."""
    OUT.mkdir(parents=True, exist_ok=True)
    files = development_files()
    paths = [p for _, p in files]
    log: dict[str, Any] = {"label": LABEL, "workers": workers, "files": [{"run": r, "name": p.name,
                                                                          "bytes": p.stat().st_size}
                                                                         for r, p in files]}
    per_file: dict[str, list[dict[str, Any]]] = {c: [] for c in CHANNEL_NAMES}
    masses: dict[str, list[np.ndarray]] = {c: [] for c in CHANNEL_NAMES}
    for channel in CHANNEL_NAMES:
        for run, p in files:
            t = time.perf_counter()
            try:
                r = analyze(p, channel=channel, n_workers=workers, verbose=False, stability=False)
            except AnalysisError as exc:  # a failed headline fit: reported, and the rehearsal stops
                print(f"STOP: [{channel}] {p.name}: {exc}")
                return 3
            dt = time.perf_counter() - t
            masses[channel].append(r.masses)
            per_file[channel].append({"run": run, "name": p.name, "seconds": dt, "n_events": r.n_events,
                                      "n_pairs": len(r.masses), **headline(r.fit, channel)})
            print(f"[{channel}] {p.name} ({run}): {dt:.1f} s, {r.n_events:,} events, "
                  f"pole {r.fit.peak_position[0]:.4f} +- {r.fit.peak_position[1]:.4f}", flush=True)
    log["per_file"] = per_file

    t = time.perf_counter()
    first2 = dict(channel="Z_mumu", verbose=False, stability=False)
    serial = analyze(paths[:2], **first2)
    t_serial = time.perf_counter() - t
    t = time.perf_counter()
    parallel = analyze(paths[:2], n_workers=workers, **first2)
    t_parallel = time.perf_counter() - t
    same = (json.dumps(serial.to_dict(), sort_keys=True) == json.dumps(parallel.to_dict(), sort_keys=True)
            and serial.summary() == parallel.summary())
    log["parallel_equals_serial_2_files"] = {"equal": same, "serial_s": t_serial, "parallel_s": t_parallel}
    print(f"parallel (n_workers={workers}) equals serial on 2 files (Z_mumu): {same} "
          f"(serial {t_serial:.1f} s, parallel {t_parallel:.1f} s)", flush=True)

    full: dict[str, Any] = {}
    for channel in CHANNEL_NAMES:
        t = time.perf_counter()
        try:
            r = analyze(paths, channel=channel, n_workers=workers, verbose=False, validation=True,
                        outdir=OUT / channel)
        except AnalysisError as exc:
            print(f"STOP: [{channel}] 6 files: {exc}")
            return 3
        dt = time.perf_counter() - t
        concat_ok = bool(np.array_equal(r.masses, np.concatenate(masses[channel])))
        full[channel] = {"seconds": dt, "n_events": r.n_events, "masses_equal_concatenation": concat_ok,
                         **headline(r.fit, channel)}
        with open(OUT / f"{channel}_result.pkl", "wb") as fh:
            pickle.dump({"masses": masses[channel], "validation": r.validation}, fh)
        print(f"[{channel}] 6 files with validation: {dt:.1f} s, {r.n_events:,} events; masses equal the per-file "
              f"concatenation: {concat_ok}", flush=True)
    log["six_files"] = full
    own, kids = peak_rss_mb()
    log["peak_rss_mb"] = {"main_process": own, "largest_worker": kids}

    lines = [f"Confirmation of the defaults on the 6-file development set ({LABEL}); no re-selection", ""]
    stop = []
    for channel, h in full.items():
        sig, bkg = h["signal"], h["background"]
        lines += [
            f"{channel}: model {h['model']}, {h['n_entries']:,} pairs in the fit range",
            f"  converged: {'yes' if h['converged'] else 'no'}; parameters on a bound: {h['on_bound'] or 'none'}; "
            f"background positive over the fit range: {'yes' if h['background_positive'] else 'no'}",
            f"  chi2/ndf {h['chi2_ndf']:.3f} (benchmark <= {CHI2_NDF_LIMIT}), p-value {h['p_value']:.3g}",
            f"  pole/peak {h['position']:.4f} +- {h['error']:.4f} GeV (stat.), offset from PDG {h['offset']:+.4f} GeV",
            f"  signal {sig[0]:,.0f} +- {sig[1]:,.0f}, background {bkg[0]:,.0f} +- {bkg[1]:,.0f}",
        ]
        if h["on_bound"] or not h["background_positive"] or h["chi2_ndf"] > CHI2_NDF_LIMIT:
            stop.append(channel)
    lines += ["", f"time: {sum(sum(f['seconds'] for f in v) for v in per_file.values()):.0f} s for the 12 per-file "
                  f"runs; 6-file runs with validation: "
                  + ", ".join(f"{c} {v['seconds']:.0f} s" for c, v in full.items()),
              f"peak memory: main process {own:,.0f} MB, largest worker {kids:,.0f} MB"]
    lines.append("STOP: " + ", ".join(stop) if stop else "OK: no stop criterion met")
    (OUT / "confirmation.txt").write_text("\n".join(lines) + "\n")
    (OUT / "confirm.json").write_text(json.dumps(log, indent=2, default=float) + "\n")
    print("\n".join(lines))
    return 3 if stop or not same or not all(v["masses_equal_concatenation"] for v in full.values()) else 0


def _weighted(values: list[float], errors: list[float]) -> tuple[float, float, float, int]:
    w = 1.0 / np.square(errors)
    mean = float(np.sum(w * np.asarray(values)) / w.sum())
    chi2 = float(np.sum(w * np.square(np.asarray(values) - mean)))
    return mean, float(1.0 / math.sqrt(w.sum())), chi2, len(values) - 1


def rest() -> int:
    """Stage 2: scaling, validation tables and figures, per-file and per-run consistency."""
    sys.path.insert(0, str(REPO / "scripts"))
    from run_validation import entries_figure

    from cmsopen.plotting import save_figure

    log = json.loads((OUT / "confirm.json").read_text())
    files = development_files()
    out: list[str] = [f"Rehearsal tables ({LABEL})", ""]
    for channel in CHANNEL_NAMES:
        with open(OUT / f"{channel}_result.pkl", "rb") as fh:
            saved = pickle.load(fh)
        masses = saved["masses"]
        out += [f"== {channel} (headline model {CHANNELS[channel].model}) ==", "",
                "Statistics scaling (cumulative, fixed order):",
                f"  {'files':>5} {'pairs in fit range':>19} {'chi2/ndf':>9} {'p-value':>9} {'pole/peak [GeV]':>24}"]
        for k in (1, 2, 4, 6):
            try:
                fit = fit_masses(np.concatenate(masses[:k]), channel)
                pos, err = fit.peak_position
                out.append(f"  {k:>5} {fit.n_entries:>19,} {fit.chi2_ndf:>9.3f} {fit.p_value:>9.3g} "
                           f"{f'{pos:.4f} +- {err:.4f}':>24}")
            except FitError as exc:
                out.append(f"  {k:>5} fit failed: {exc}")
        out += ["", "Per file (headline model; information only, previewing T6):"]
        values, errors = [], []
        for (run, p), row in zip(files, log["per_file"][channel], strict=True):
            out.append(f"  {p.name} ({run}): {row['position']:.4f} +- {row['error']:.4f} GeV, "
                       f"chi2/ndf {row['chi2_ndf']:.3f}, {row['n_entries']:,} pairs")
            values.append(row["position"])
            errors.append(row["error"])
        mean, mean_err, chi2, ndf = _weighted(values, errors)
        out.append(f"  weighted mean {mean:.4f} +- {mean_err:.4f} GeV; chi2 of consistency {chi2:.2f} / {ndf} "
                   f"(p = {stats.chi2.sf(chi2, ndf):.3g})")
        by_run = {}
        for run in ("2012C", "2012B"):
            sel = [m for (r, _), m in zip(files, masses, strict=True) if r == run]
            fit = fit_masses(np.concatenate(sel), channel)
            by_run[run] = fit.peak_position
            out.append(f"  {run} ({len(sel)} files, fitted together): {fit.peak_position[0]:.4f} +- "
                       f"{fit.peak_position[1]:.4f} GeV, chi2/ndf {fit.chi2_ndf:.3f}")
        (c, ce), (b, be) = by_run["2012C"], by_run["2012B"]
        diff, diff_err = c - b, math.hypot(ce, be)
        out += [f"  2012C - 2012B: {diff:+.4f} +- {diff_err:.4f} GeV = {diff / diff_err:+.2f} sigma (stat.)", ""]

        v = saved["validation"]
        table = v.table()
        (OUT / channel / "validation.txt").write_text(f"{LABEL}\n{table}\n")
        fig = entries_figure(v)
        fig.axes[0].set_title(f"CMS Open Data, {channel}: validation (6-file development set)", fontsize=9,
                              loc="left")
        save_figure(fig, OUT / channel / "validation_entries")
        flagged = [e for e in (v.inclusive, *v.entries) if e.status != "fitted"]
        out += ["Validation (validation model " + v.model + "):", table, "",
                f"Flagged entries ({len(flagged)}): "
                + ("; ".join(f"{e.study} {e.label}: {e.status_text}" for e in flagged) or "none"), ""]
    text = "\n".join(out)
    (OUT / "tables.txt").write_text(text + "\n")
    print(text)
    return 0


def main(argv: list[str] | None = None) -> int:
    """Run one stage."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("stage", choices=("confirm", "rest"))
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args(argv)
    return confirm(args.workers) if args.stage == "confirm" else rest()


if __name__ == "__main__":
    sys.exit(main())
