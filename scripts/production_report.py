"""Print the summary of the production run from results/production.json, to read and to paste back for review.

Sections: the run (commits, environment, attempts and code fixes); the T1-T7
table (each target's controlling benchmark from dev/targets.md and the
observed value, each labelled, and whether it is met); the headline result
of every channel with its raw and scaled statistical errors, the fit-choice
spread and the alternate fit; the per-run consistency (T6); the validation
table and the systematics summary of every channel; the per-file table; the
cutflows; the timings. Every value comes from results/production.json as
written by scripts/production_run.py; nothing is refitted. No file name is
printed (results/production.json contains none: files appear by record,
index and size).

Usage:
    python scripts/production_report.py [results/production.json]

Exit 0; 1 if the file is missing or not a production summary.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
DEFAULT = REPO / "results" / "production.json"


def _num(x: Any, digits: int = 4, sign: bool = False) -> str:
    if x is None:
        return "n/a"
    if isinstance(x, bool):
        return str(x)
    if isinstance(x, (int, float)):
        return f"{x:+.{digits}f}" if sign else f"{x:.{digits}f}"
    return str(x)


def _opt(x: float | None, spec: str) -> str:
    return "" if x is None else format(x, spec)


def _digits(channel: dict[str, Any]) -> int:
    """Decimals for GeV values: 4 above 10 GeV (the Z), 5 below (the J/psi)."""
    return 4 if channel["result"]["peak_position_gev"] > 10 else 5


def _met(value: Any) -> str:
    if isinstance(value, dict):
        return ", ".join(f"{k}: {'met' if v else 'NOT MET'}" for k, v in value.items())
    return "met" if value else "NOT MET"


def _observed(target: str, obs: Any) -> str:
    if target == "T1":
        return ", ".join(f"{k}: byte-identical {v}" for k, v in obs.items())
    if target == "T2":
        return ", ".join(f"{k}: chi2/ndf {v['chi2_ndf']:.3f}, background positive {v['yields_reliable']}"
                         for k, v in obs.items())
    if target == "T3":
        return "; ".join(
            f"{k}: offset {_num(v['offset_from_pdg_gev'], 5, True)} +- {_num(v['stat_error_gev'], 5)} (stat.) "
            f"+- {_num(v['stat_error_scaled_gev'], 5)} (scaled) GeV, fit-choice spread "
            f"{_num(v['fit_choice_spread_gev'], 5)} GeV, {len(v['diagnostic_studies'])} diagnostic studies"
            for k, v in obs.items())
    if target == "T4":
        return (f"{obs['n_files']} files, by record {obs['by_record']}, analysed per channel "
                f"{obs['analysed_per_channel']}")
    if target == "T5":
        return ", ".join(f"{k} {'yes' if v else 'NO'}" for k, v in obs.items())
    if target == "T6":
        parts = []
        for k, v in obs.items():
            for key, d in sorted(v.items()):
                what = "peak" if key.startswith("peak") else "resolution"
                parts.append(f"{k} {what} {_num(d['value'], 5, True)} +- {_num(d['error'], 5)} GeV "
                             f"({d['in_sigma']:+.2f} sigma)")
        return "; ".join(parts) or "no period difference (one period only)"
    if target == "T7":
        if not obs:
            return "no gates record"
        return (f"record for {str(obs.get('head', '?'))[:12]}: pytest exit {obs.get('pytest_rc')}, quality exit "
                f"{obs.get('quality_rc')}, coverage {obs.get('coverage_total', 'not recorded')}; {obs.get('summary')}")
    return json.dumps(obs)


def _benchmark(b: Any) -> str:
    if isinstance(b, dict):
        return f"{b['n_files']} files, by record {b['by_record']}"
    return str(b)


def section_run(d: dict[str, Any]) -> list[str]:
    """The commits, environment, registry and every attempt and code fix."""
    a = d.get("attempts", {})
    lines = ["== Run",
             f"git HEAD {d['git_head'][:12]} (first attempt at {d.get('first_head', d['git_head'])[:12]}), model "
             f"freeze {d['freeze_commit'][:12]}, environment sha256 {d['environment']['sha256'][:16]}..., "
             f"Python {d['environment']['python']}",
             f"registry sha256 {d['registry_sha256'][:16]}...; {d['sample']['n_files']} files, "
             f"{sum(f['size_bytes'] for f in d['files']):,} bytes",
             f"attempts: {a.get('n', '?')}"]
    for f in a.get("failed", []):
        lines.append(f"  attempt {f['attempt']} {f['status']} in phase '{f['phase']}' at {f['time']}: {f['exception']}")
    for c in a.get("code_fixes", []):
        lines.append(f"  code fix at attempt {c['attempt']}: {c['from_head'][:12]} -> {c['to_head'][:12]}: "
                     f"{c['reason']}")
    return lines


def section_targets(d: dict[str, Any]) -> list[str]:
    """T1-T7: benchmark, observed value and met / NOT MET, each on its own labelled line."""
    lines = ["", "== Targets T1-T7 (controlling benchmark versus observed; dev/targets.md)"]
    for name, t in sorted(d["targets"].items()):
        lines += [f"{name}: {_met(t['met'])}",
                  f"  benchmark: {_benchmark(t['benchmark'])}",
                  f"  observed:  {_observed(name, t['observed'])}"]
    return lines


def section_headline(name: str, c: dict[str, Any]) -> list[str]:
    """The channel's headline fit with raw and scaled stat. errors, offset, fit-choice spread, alternate fit."""
    r, n = c["result"], _digits(c)
    alt = c.get("alternate_fit")
    lines = [
        "", f"== {name}: headline fit (observed)",
        f"model {r['model']}, fit range {r['fit_range_gev'][0]:g}-{r['fit_range_gev'][1]:g} GeV, "
        f"{r['n_events']:,} events, {r['n_pairs_in_fit_range']:,} pairs in the fit range",
        f"peak (pole) {_num(r['peak_position_gev'], n)} GeV +- {_num(r['stat_error_gev'], n)} (stat., raw) "
        f"+- {_num(r['stat_error_scaled_gev'], n)} (stat., scaled by S = {r['scale_factor']:.3f})",
        f"resolution {_num(r['resolution_gev'], n)} +- {_num(r['resolution_error_gev'], n)} GeV; chi2/ndf "
        f"{r['chi2']:.1f}/{r['ndf']} = {r['chi2_ndf']:.3f} (benchmark <= 2.0), p-value {r['p_value']:.3g}, "
        f"background positive {r['yields_reliable']}",
        f"offset from the PDG mass {r['pdg_mass_gev']:.4f} GeV: {_num(r['offset_from_pdg_gev'], n, True)} GeV "
        "(not a mass measurement: no momentum-scale corrections)",
        f"fit-choice spread {_num(c['fit_choice_spread_gev'], n)} GeV ({c.get('fit_choice_spread_label', '')})",
    ]
    if alt:
        lines.append(f"alternate fit {alt['model']}: {_num(alt['peak_position_gev'], n)} +- "
                     f"{_num(alt['stat_error_gev'], n)} GeV, chi2/ndf {alt['chi2_ndf']:.3f}")
    lines += [f"warning: {w}" for w in c.get("warnings", [])]
    return lines


def section_periods(name: str, c: dict[str, Any]) -> list[str]:
    """Run 2012B versus Run 2012C (T6): both fits and their differences."""
    n = _digits(c)
    lines = ["", f"== {name}: per-run consistency (T6)",
             f"{'period':<8}{'files':>6}{'pairs':>10}  {'peak [GeV]':>24}{'resolution [GeV]':>24}{'chi2/ndf':>10}"]
    for period, p in sorted(c["t6"]["periods"].items()):
        lines.append(f"{period:<8}{p['n_files']:>6}{p['n_pairs_in_fit_range']:>10,}  "
                     f"{_num(p['peak_position_gev'], n) + ' +- ' + _num(p['stat_error_gev'], n):>24}"
                     f"{_num(p['resolution_gev'], n) + ' +- ' + _num(p['resolution_error_gev'], n):>24}"
                     f"{p['chi2_ndf']:>10.3f}")
    for key, v in sorted((k, v) for k, v in c["t6"].items() if k != "periods"):
        lines.append(f"{key}: {_num(v['value'], n, True)} +- {_num(v['error'], n)} GeV ({v['in_sigma']:+.2f} sigma)")
    return lines


def section_validation(name: str, c: dict[str, Any]) -> list[str]:
    """The validation table (every entry) and the systematics summary's spreads."""
    v = c.get("validation")
    if not v:
        return ["", f"== {name}: no validation"]
    n = _digits(c)
    lines = ["", f"== {name}: validation (scans fitted with {v['model']}; at least {v['min_pairs']:,} pairs per entry)",
             f"{'study':<14}{'entry':<22}{'pairs':>9}  {'position [GeV]':>24}{'chi2/ndf':>9}{'d/s':>7}{'S':>6}"
             f"{'d/s scaled':>11}  status"]
    for e in [v["inclusive"], *v["entries"]]:
        pos = (f"{_num(e.get('position'), n)} +- {_num(e.get('error'), n)}"
               if e.get("status") == "fitted" else "")
        lines.append(f"{e['study']:<14}{e['label']:<22}{e['n_pairs']:>9,}  {pos:>24}"
                     f"{_opt(e.get('chi2_ndf'), '.3f'):>9}{_opt(e.get('delta_sigma'), '+.2f'):>7}"
                     f"{_opt(e.get('scale_factor'), '.2f'):>6}{_opt(e.get('delta_sigma_scaled'), '+.2f'):>11}  "
                     f"{e['status']}{': ' + e['reason'] if e.get('reason') else ''}")
    s = v["systematics_summary"]
    lines += [
        f"systematics summary (measured, no targets): model spread {_num(s.get('model_spread'), n)} GeV; fit-choice "
        f"spread (max - min) {_num(s.get('fit_choice_spread'), n)} GeV; category spread "
        f"{_num(s.get('category_spread'), n)} GeV, largest |delta|/sigma {_num(s.get('category_max_delta_sigma'), 2)} "
        f"(scaled {_num(s.get('category_max_delta_sigma_scaled'), 2)}); mu+ vs mu- largest difference "
        f"{_num(s.get('charge_max_difference'), n)} GeV; working-point spread {_num(s.get('working_point_spread'), n)} "
        f"GeV; {s.get('n_insufficient', 0)} entries below the pair threshold, {s.get('n_failed', 0)} failed",
    ]
    return lines


def section_per_file(name: str, c: dict[str, Any]) -> list[str]:
    """One row per file (record, period, index): pole, stat. error and chi2/ndf, or why the fit failed."""
    n = _digits(c)
    lines = ["", f"== {name}: per-file fits ({c['result']['model']}, each file alone)",
             f"{'file':>4} {'record':>7} {'period':<9}{'index':>6}{'events':>11}{'pairs':>9}  {'pole [GeV]':>24}"
             f"{'chi2/ndf':>9}  status"]
    for row in c["per_file"]:
        if row["status"] == "fitted":
            pole = f"{_num(row['peak_position_gev'], n)} +- {_num(row['stat_error_gev'], n)}"
            lines.append(f"{row['file']:>4} {row['record_id']:>7} {row['run_period']:<9}{row['index']:>6}"
                         f"{row['n_events']:>11,}{row['n_pairs_in_fit_range']:>9,}  {pole:>24}{row['chi2_ndf']:>9.3f}"
                         "  fitted")
        else:
            lines.append(f"{row['file']:>4} {row['record_id']:>7} {row['run_period']:<9}{row['index']:>6}"
                         f"{'':>11}{'':>9}  {'':>24}{'':>9}  failed: {row['reason']}")
    return lines


def section_cutflow(name: str, c: dict[str, Any]) -> list[str]:
    """Events after each selection step, with the share of all events."""
    lines = ["", f"== {name}: cutflow",
             f"  {'step':>4} {'cut':<42}{'muons':>13}{'events with muons':>19}{'events':>13}{'of all':>9}"]
    first = c["cutflow"][0]["n_events"] if c["cutflow"] else 0
    for s in c["cutflow"]:
        share = 100 * s["n_events"] / first if first else 0.0
        lines.append(f"  {s['step']:>4} {s['cut']:<42}{s['n_particles']:>13,}{s['n_events_with_particles']:>19,}"
                     f"{s['n_events']:>13,}{share:>8.2f}%")
    return lines


def section_timing(d: dict[str, Any]) -> list[str]:
    """The run's and every channel's timings."""
    t = d["timing_s"]
    lines = ["", "== Timings (seconds)", "  " + ", ".join(f"{k} {v}" for k, v in t.items())]
    for name, c in sorted(d["channels"].items(), key=lambda item: (item[0] != "Z_mumu", item[0])):
        lines.append(f"  {name}: " + ", ".join(f"{k} {v}" for k, v in c["timing_s"].items()))
    return lines


def report(d: dict[str, Any]) -> str:
    """The whole report as text."""
    lines = section_run(d) + section_targets(d)
    channels = sorted(d["channels"].items(), key=lambda item: (item[0] != "Z_mumu", item[0]))  # Z first
    for name, c in channels:
        lines += section_headline(name, c) + section_periods(name, c)
    for name, c in channels:
        lines += section_validation(name, c) + section_per_file(name, c) + section_cutflow(name, c)
    lines += section_timing(d)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Print the report of the given (or the default) production summary."""
    args = sys.argv[1:] if argv is None else argv
    path = Path(args[0]) if args else DEFAULT
    try:
        data = json.loads(path.read_text())
        text = report(data)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"error: cannot report {path}: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
