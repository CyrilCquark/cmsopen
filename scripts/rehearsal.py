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
Stage ``rest`` (after ``confirm``; information only, nothing refitted with
another model): the statistics-scaling table (cumulative 1, 2, 4, 6 files),
the validation tables and figures with the per-category chi2/ndf, the
per-file and per-run consistency, the structure of the headline fit's
residuals (pulls per bin, |pull| > 3, lag-1 autocorrelation, runs test,
chi2 by region, chi2/ndf over the fit-range x bin-width grid), and the
validation entries that reach the 5,000-pair threshold only on the 6 files.

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


def pull_structure(fit: Any) -> dict[str, Any]:
    """Pulls per fitted bin and the statistics that separate structured misfit from scatter.

    pull = (N - mu) / sqrt(max(N, 1)), the fit's own chi2 terms (their squares
    sum to chi2). Regions: "core" is within 2 x the reported resolution of the
    fitted position (FWHM/2.355 for the mixtures), "left" and "right" are the
    bins below and above it. Lag-1 autocorrelation r1 = sum (p_i - pbar)(p_i+1 -
    pbar) / sum (p_i - pbar)^2 (about 0 +- 1/sqrt(n) for independent pulls).
    Wald-Wolfowitz runs test on the signs of the pulls: z = (R - E[R]) / sd(R),
    two-sided normal p-value.
    """
    h = fit.histogram
    mask = fit.fit_mask
    lo, hi = h.edges[:-1][mask], h.edges[1:][mask]
    centers = 0.5 * (lo + hi)
    counts = h.counts[mask]
    mu = fit.expected_counts()
    pulls = (counts - mu) / h.fit_errors[mask]
    pos, res = fit.peak_position[0], fit.resolution[0]
    region = np.where(centers < pos - 2 * res, "left", np.where(centers > pos + 2 * res, "right", "core"))
    p = pulls - pulls.mean()
    r1 = float(np.sum(p[:-1] * p[1:]) / np.sum(p * p))
    signs = np.sign(pulls[pulls != 0])
    n_plus, n_minus = int(np.sum(signs > 0)), int(np.sum(signs < 0))
    n = n_plus + n_minus
    runs = int(1 + np.sum(signs[1:] != signs[:-1]))
    expected = 2 * n_plus * n_minus / n + 1
    variance = 2 * n_plus * n_minus * (2 * n_plus * n_minus - n) / (n * n * (n - 1))
    z = (runs - expected) / math.sqrt(variance)
    regions = {}
    for name in ("left", "core", "right"):
        sel = region == name
        regions[name] = {"bins": int(sel.sum()), "chi2": float(np.sum(pulls[sel] ** 2)),
                         "range": (float(lo[sel].min()), float(hi[sel].max())) if sel.any() else None}
    return {
        "table": [{"lo": float(a), "hi": float(b), "data": float(c), "fit": float(m), "pull": float(q),
                   "region": str(g)} for a, b, c, m, q, g in zip(lo, hi, counts, mu, pulls, region, strict=True)],
        "big": [(float(a), float(b), float(q)) for a, b, q in zip(lo, hi, pulls, strict=True) if abs(q) > 3],
        "r1": r1, "n": len(pulls), "runs": runs, "runs_expected": expected, "runs_z": z,
        "runs_p": float(2 * stats.norm.sf(abs(z))), "n_plus": n_plus, "n_minus": n_minus, "regions": regions,
        "chi2": fit.chi2, "ndf": fit.ndf,
    }


def pulls_figure(structure: dict[str, Any], channel: str, fit: Any) -> Any:
    """The pulls per bin of the 6-file headline fit, with the core region shaded."""
    from matplotlib.figure import Figure

    from cmsopen.plotting import MIN_FONT_SIZE, OKABE_ITO, paper_style

    rows = structure["table"]
    x = np.array([0.5 * (r["lo"] + r["hi"]) for r in rows])
    q = np.array([r["pull"] for r in rows])
    core = [r for r in rows if r["region"] == "core"]
    with paper_style():
        fig = Figure(figsize=(5.0, 3.0), layout="constrained")
        ax = fig.subplots()
        ax.axvspan(core[0]["lo"], core[-1]["hi"], color=OKABE_ITO["sky_blue"], alpha=0.3, lw=0,
                   label="core (within 2 x resolution)")
        for level in (-3, 3):
            ax.axhline(level, color="0.5", ls=":", lw=0.8)
        ax.axhline(0, color="black", lw=0.6)
        ax.plot(x, q, "o", color="black", ms=3.5, label="pull per bin")
        ax.set_xlabel(r"$m_{\mu\mu}$ [GeV]")
        ax.set_ylabel(r"(data $-$ fit) / $\sigma$")
        ax.set_ylim(-max(4.0, float(np.abs(q).max()) + 1), max(4.0, float(np.abs(q).max()) + 1))
        ax.legend(loc="upper right", fontsize=MIN_FONT_SIZE, frameon=False, ncol=2)
        ax.set_title(f"CMS Open Data, {channel} ({fit.model_name}): pulls, 6-file development set",
                     loc="left", fontsize=9)
    return fig


def _structure_lines(s: dict[str, Any]) -> list[str]:
    reg = s["regions"]
    lines = [f"  chi2 {s['chi2']:.1f} / ndf {s['ndf']} over {s['n']} bins"]
    for name in ("left", "core", "right"):
        r = reg[name]
        rng = "-" if r["range"] is None else f"{r['range'][0]:g}-{r['range'][1]:g} GeV"
        lines.append(f"  chi2 {name:<5} ({rng}, {r['bins']} bins): {r['chi2']:.1f}"
                     + (f" ({r['chi2'] / r['bins']:.2f} per bin)" if r["bins"] else ""))
    lines.append("  bins with |pull| > 3: "
                 + (", ".join(f"{a:g}-{b:g} GeV ({q:+.2f})" for a, b, q in s["big"]) or "none"))
    lines.append(f"  lag-1 autocorrelation of the pulls: {s['r1']:+.3f} (1/sqrt(n) = {1 / math.sqrt(s['n']):.3f})")
    lines.append(f"  runs test on the pull signs: {s['runs']} runs ({s['n_plus']} +, {s['n_minus']} -), expected "
                 f"{s['runs_expected']:.1f}, z = {s['runs_z']:+.2f}, p = {s['runs_p']:.3g}")
    return lines


def rest() -> int:
    """Stage 2: scaling, validation tables, consistency, misfit structure and newly sufficient entries."""
    sys.path.insert(0, str(REPO / "scripts"))
    from run_validation import entries_figure

    from cmsopen.fitting import fit_stability
    from cmsopen.plotting import save_figure
    from cmsopen.validation import MIN_PAIRS

    files = development_files()
    out: list[str] = [f"Rehearsal tables ({LABEL})", ""]
    log: dict[str, Any] = {"label": LABEL}
    for channel in CHANNEL_NAMES:
        cfg = CHANNELS[channel]
        with open(OUT / f"{channel}_result.pkl", "rb") as fh:
            saved = pickle.load(fh)
        masses = saved["masses"]
        out += [f"== {channel} (headline model {cfg.model}) ==", "",
                "1. Statistics scaling (cumulative, fixed order: the original file, then the new files by index):",
                f"  {'files':>5} {'pairs in fit range':>19} {'chi2/ndf':>9} {'ndf':>4} {'p-value':>9} "
                f"{'pole/peak [GeV]':>24}"]
        for k in (1, 2, 4, 6):
            try:
                fit = fit_masses(np.concatenate(masses[:k]), channel)
                pos, err = fit.peak_position
                out.append(f"  {k:>5} {fit.n_entries:>19,} {fit.chi2_ndf:>9.3f} {fit.ndf:>4} {fit.p_value:>9.3g} "
                           f"{f'{pos:.4f} +- {err:.4f}':>24}")
            except FitError as exc:
                out.append(f"  {k:>5} fit failed: {exc}")

        v = saved["validation"]
        table = v.table()
        (OUT / channel / "validation.txt").write_text(f"{LABEL}\n{table}\n")
        fig = entries_figure(v)
        fig.axes[0].set_title(f"CMS Open Data, {channel}: validation (6-file development set)", fontsize=9,
                              loc="left")
        save_figure(fig, OUT / channel / "validation_entries")
        flagged = [e for e in (v.inclusive, *v.entries) if e.status != "fitted"]
        out += ["", f"2. Validation (validation model {v.model}, headline model {v.headline_model}; at least "
                    f"{MIN_PAIRS:,} pairs per entry):", table, "",
                "  per category (validation model): " + "; ".join(
                    f"{e.label} {e.n_pairs:,} pairs, " + (f"chi2/ndf {e.chi2_ndf:.3f}" if e.fitted else e.status_text)
                    for e in v.study("region")),
                f"  flagged entries ({len(flagged)}): "
                + ("; ".join(f"{e.study} {e.label}: {e.status_text}" for e in flagged) or "none"), ""]

        out.append("3. Per file (headline model, each file fitted on its own):")
        values, errors = [], []
        for (run, p), m in zip(files, masses, strict=True):
            try:
                fit = fit_masses(m, channel)
            except FitError as exc:
                out.append(f"  {p.name} ({run}): fit failed: {exc}")
                continue
            (pos, err), (res, rerr) = fit.peak_position, fit.resolution
            out.append(f"  {p.name} ({run}): chi2/ndf {fit.chi2_ndf:.3f} (ndf {fit.ndf}), {pos:.4f} +- {err:.4f} GeV, "
                       f"resolution {res:.4f} +- {rerr:.4f} GeV, {fit.n_entries:,} pairs")
            values.append(pos)
            errors.append(err)
        mean, mean_err, chi2, ndf = _weighted(values, errors)
        out.append(f"  weighted mean {mean:.4f} +- {mean_err:.4f} GeV; chi2 of consistency of the {len(values)} "
                   f"positions {chi2:.2f} / {ndf} (p = {stats.chi2.sf(chi2, ndf):.3g})")
        by_run = {}
        for run in ("2012C", "2012B"):
            sel = [m for (r, _), m in zip(files, masses, strict=True) if r == run]
            fit = fit_masses(np.concatenate(sel), channel)
            by_run[run] = fit.peak_position
            run_values = [v_ for (r, _), v_ in zip(files, values, strict=True) if r == run]
            run_errors = [e_ for (r, _), e_ in zip(files, errors, strict=True) if r == run]
            wm, wme, _, _ = _weighted(run_values, run_errors)
            out.append(f"  {run} ({len(sel)} files): fitted together {fit.peak_position[0]:.4f} +- "
                       f"{fit.peak_position[1]:.4f} GeV (chi2/ndf {fit.chi2_ndf:.3f}); weighted mean of the files "
                       f"{wm:.4f} +- {wme:.4f} GeV")
        (c, ce), (b, be) = by_run["2012C"], by_run["2012B"]
        diff, diff_err = c - b, math.hypot(ce, be)
        out += [f"  2012C - 2012B (fitted together): {diff:+.4f} +- {diff_err:.4f} GeV = {diff / diff_err:+.2f} "
                "sigma (stat.)", ""]

        full = fit_masses(np.concatenate(masses), channel)
        s = pull_structure(full)
        with open(OUT / channel / "pulls.csv", "w") as fh:
            fh.write("lo_gev,hi_gev,data,fit,pull,region\n")
            fh.writelines(f"{r['lo']:.4f},{r['hi']:.4f},{r['data']:.0f},{r['fit']:.2f},{r['pull']:.4f},{r['region']}\n"
                          for r in s["table"])
        save_figure(pulls_figure(s, channel, full), OUT / channel / "pulls")
        out += [f"4. Structure of the headline fit's residuals on the 6 files ({full.model_name}; pulls in "
                f"build/rehearsal/{channel}/pulls.csv and pulls.png):", *_structure_lines(s)]
        stab = fit_stability(np.concatenate(masses), fit_ranges=cfg.stability_fit_ranges,
                             bin_widths=cfg.stability_bin_widths, poly_degrees=(cfg.poly_degree,),
                             models=(cfg.model,), hist_range=cfg.mass_range,
                             natural_width=pdg_mass_width(cfg.resonance)[2], cb_n=cfg.cb_n)
        out.append("  chi2/ndf over the fit-range x bin-width grid (report only):")
        for r in sorted(stab.rows, key=lambda r: (r["fit_range"], r["bin_width"])):
            out.append(f"    {r['fit_range'][0]:g}-{r['fit_range'][1]:g} GeV, bins {r['bin_width']:g} GeV: "
                       f"chi2/ndf {r['chi2_ndf']:.3f}, p {r['p_value']:.3g}, position {r['mass']:.4f} GeV")
        for f in stab.failed:
            out.append(f"    {f.get('fit_range')}, bins {f.get('bin_width')}: fit failed: {f.get('reason', f)}")
        out.append("")

        single = json.loads((REPO / "build" / "validation" / channel / "summary.json").read_text())["validation"]
        before = {(e["study"], e["label"]): e for e in single["entries"]}
        newly = [e for e in v.entries if e.n_pairs >= MIN_PAIRS
                 and before.get((e.study, e.label), {}).get("status") == "insufficient"]
        out += [f"6. Entries at or above {MIN_PAIRS:,} pairs on the 6 files that were insufficient on the original "
                f"file (build/validation/{channel}/summary.json): {len(newly)}"]
        out += [f"  {e.study} {e.label}: {before[(e.study, e.label)]['n_pairs']:,} -> {e.n_pairs:,} pairs, "
                + (f"now fitted ({e.position:.4f} +- {e.error:.4f} GeV, chi2/ndf {e.chi2_ndf:.3f})" if e.fitted
                   else e.status_text) for e in newly]
        still = [e for e in v.entries if e.status == "insufficient"]
        out += ["  still insufficient on the 6 files: "
                + ("; ".join(f"{e.study} {e.label} ({e.n_pairs:,})" for e in still) or "none"), ""]
        log[channel] = {"structure": {k: x for k, x in s.items() if k != "table"}}
    text = "\n".join(out)
    (OUT / "tables.txt").write_text(text + "\n")
    (OUT / "rest.json").write_text(json.dumps(log, indent=2, default=float) + "\n")
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
