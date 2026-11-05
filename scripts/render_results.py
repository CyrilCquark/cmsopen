"""Render the README results block from results/production.json.

The README's results block sits between the lines ``<!-- RESULTS:BEGIN -->``
and ``<!-- RESULTS:END -->``. Its text is generated, never typed:
:func:`render_results_block` turns the production summary into Markdown, and
``scripts/check_readme_numbers.py`` fails if the README block differs from
it. results/production.json may only be created by the production run.

Schema of results/production.json (schema_version 1; all masses in GeV)::

    {
      "schema_version": 1,
      "sample": {"n_files": int, "n_events": int, "n_pairs": int},
      "fit": {
        "model": str,                    # e.g. "voigt_poly"
        "fit_range_gev": [float, float],
        "peak_position_gev": float,
        "stat_error_gev": float,
        "resolution_gev": float,
        "resolution_error_gev": float,
        "chi2": float,
        "ndf": int
      },
      "pdg": {"mass_gev": float, "source": str},
      "fit_choice_spread_gev": float     # optional: std of the peak over fit choices
    }

results/production.json as the production run writes it also has "targets"
(T1-T7) and "channels" (Z_mumu, Jpsi_mumu; scripts/production_schema.py checks
them). With those sections the block shows, for every target, the controlling
benchmark next to the observed value and met / not met ("Controlling
benchmarks" in CLAUDE.md), then the headline fit of each channel. A file whose
gates record says it is a dry run is labelled as dry-run data in the block.

Usage:
    python scripts/render_results.py [results/production.json]   # prints the block

Standard library only.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

BEGIN = "<!-- RESULTS:BEGIN -->"
END = "<!-- RESULTS:END -->"

_REQUIRED = {
    "sample": ("n_files", "n_events", "n_pairs"),
    "fit": ("model", "fit_range_gev", "peak_position_gev", "stat_error_gev", "resolution_gev", "resolution_error_gev",
            "chi2", "ndf"),
    "pdg": ("mass_gev", "source"),
}


def _validate(data: dict[str, Any]) -> None:
    if data.get("schema_version") != 1:
        raise ValueError(f"unsupported schema_version {data.get('schema_version')!r}; expected 1")
    for section, keys in _REQUIRED.items():
        if not isinstance(data.get(section), dict):
            raise ValueError(f"missing section {section!r}")
        missing = [k for k in keys if k not in data[section]]
        if missing:
            raise ValueError(f"section {section!r} lacks {missing}")


def is_dry_run(data: dict[str, Any]) -> bool:
    """True if the gates record says this file came from a dry run, not from the production sample."""
    gates = data.get("gates")
    return isinstance(gates, dict) and str(gates.get("summary", "")).lower().startswith("dry run")


def dry_run_banner(data: dict[str, Any]) -> str:
    """The label every generated file carries when built from dry-run data; empty for real results."""
    if not is_dry_run(data):
        return ""
    return (f"> **DRY-RUN DATA, NOT RESULTS.** Built from a rehearsal on {data['sample']['n_files']} development files "
            "with a placeholder gates record. Nothing here is a production result.")


CHANNEL_LABELS = {"Z_mumu": "Z → μ⁺μ⁻", "Jpsi_mumu": "J/ψ → μ⁺μ⁻"}
TARGET_NAMES = {"T1": "Reproducibility", "T2": "Fit adequacy", "T3": "Peak offset reported", "T4": "Statistics",
                "T5": "Transparency", "T6": "Run-period consistency", "T7": "Engineering"}
_SHORT = {"Z_mumu": "Z", "Jpsi_mumu": "J/ψ"}


def fmt(value: Any, spec: str) -> str:
    """A number in this format, or "n/a" for a value the run could not determine (recorded as null)."""
    return "n/a" if value is None else format(value, spec)


def channel_digits(channel: dict[str, Any]) -> int:
    """Decimals for GeV values: 4 above 10 GeV (the Z), 5 below (the J/psi), as in scripts/production_report.py."""
    return 4 if channel["result"]["peak_position_gev"] > 10 else 5


def met_text(met: Any) -> str:
    """"met" / "not met" for a target, per channel where the target is per channel."""
    if isinstance(met, dict):
        return "; ".join(f"{_SHORT.get(k, k)}: {'met' if v else 'not met'}"
                         for k, v in sorted(met.items(), reverse=True))
    return "met" if met else "not met"


def benchmark_text(target: dict[str, Any]) -> str:
    """The controlling benchmark of a target, as written in results/production.json."""
    b = target["benchmark"]
    if isinstance(b, dict):
        by_record = ", ".join(f"{n} from record {r}" for r, n in sorted(b["by_record"].items(), reverse=True))
        return f"{b['n_files']} files ({by_record})"
    return str(b)


def observed_text(name: str, obs: Any) -> str:
    """The observed value of a target, labelled nowhere as a benchmark."""
    channels = sorted(obs, reverse=True) if isinstance(obs, dict) else []
    if name == "T1":
        return "; ".join(f"{_SHORT[k]}: {'byte-identical' if obs[k] else 'differs'}" for k in channels)
    if name == "T2":
        return "; ".join(f"{_SHORT[k]}: χ²/ndf {obs[k]['chi2_ndf']:.3f}, background "
                         f"{'positive' if obs[k]['yields_reliable'] else 'NOT positive'}" for k in channels)
    if name == "T3":
        parts = []
        for k in channels:
            d = 4 if k == "Z_mumu" else 5
            v = obs[k]
            parts.append(f"{_SHORT[k]}: {v['offset_from_pdg_gev']:+.{d}f} ± {v['stat_error_gev']:.{d}f} (stat.) GeV, "
                         f"fit-choice spread {fmt(v['fit_choice_spread_gev'], f'.{d}f')} GeV, "
                         f"{len(v['diagnostic_studies'])} diagnostic studies")
        return "; ".join(parts)
    if name == "T4":
        by_record = ", ".join(f"{n} from record {r}" for r, n in sorted(obs["by_record"].items(), reverse=True))
        return f"{obs['n_files']} files ({by_record})"
    if name == "T5":
        recorded = [k.replace("_", " ") for k, v in sorted(obs.items()) if v]
        missing = [k.replace("_", " ") for k, v in sorted(obs.items()) if not v]
        return "recorded: " + ", ".join(recorded) + (f"; MISSING: {', '.join(missing)}" if missing else "")
    if name == "T6":
        parts = []
        for k in channels:
            for key, label in (("peak_position_gev_difference_2012B_minus_2012C", "peak"),
                               ("resolution_gev_difference_2012B_minus_2012C", "resolution")):
                if key in obs[k]:
                    v = obs[k][key]
                    d = 4 if k == "Z_mumu" else 5
                    value = fmt(v["value"], f"+.{d}f")
                    parts.append(f"{_SHORT[k]} {label} {value} ± {fmt(v['error'], f'.{d}f')} GeV "
                                 f"({fmt(v['in_sigma'], '+.2f')} σ)")
        return "; ".join(parts) or "one run period only: no difference"
    if name == "T7":
        if not obs:
            return "no gates record"
        return (f"record for commit {str(obs.get('head', '?'))[:12]}: pytest exit {obs.get('pytest_rc')}, quality "
                f"exit {obs.get('quality_rc')}, coverage {obs.get('coverage_total', 'not recorded')}; "
                f"{obs.get('summary')}")
    return json.dumps(obs, sort_keys=True)


def targets_table(data: dict[str, Any]) -> str:
    """Target by target: the benchmark first and prominent, then the observed value, then met or not met."""
    lines = ["| target | **controlling benchmark** | observed | status |", "|---|---|---|---|"]
    for name in sorted(data["targets"]):
        t = data["targets"][name]
        lines.append(f"| {name} {TARGET_NAMES.get(name, '')} | **{benchmark_text(t)}** "
                     f"| {observed_text(name, t['observed'])} | {met_text(t['met'])} |")
    return "\n".join(lines)


def headline_table(data: dict[str, Any]) -> str:
    """The headline fit of every channel: observed values, with the chi2/ndf benchmark on its own labelled row."""
    names = [n for n in ("Z_mumu", "Jpsi_mumu") if n in data["channels"]]
    rows: list[list[str]] = []
    for name in names:
        c = data["channels"][name]
        r, d = c["result"], channel_digits(c)
        lo, hi = r["fit_range_gev"]
        alt = c.get("alternate_fit") or {}
        rows.append([
            f"{r['model']}, {lo:g}-{hi:g} GeV",
            f"{r['n_events']:,}",
            f"{r['n_pairs_in_fit_range']:,}",
            f"{r['peak_position_gev']:.{d}f} GeV",
            f"{r['stat_error_gev']:.{d}f} GeV",
            f"{r['stat_error_scaled_gev']:.{d}f} GeV (S = {r['scale_factor']:.3f})",
            f"{r['resolution_gev']:.{d}f} ± {r['resolution_error_gev']:.{d}f} GeV",
            f"**≤ {c['t2']['benchmark']:.1f}**",
            f"{r['chi2']:.1f} / {r['ndf']} = {r['chi2_ndf']:.3f} ({'met' if c['t2']['met'] else 'not met'})",
            fmt(r["p_value"], ".3g"),
            f"{r['pdg_mass_gev']:.4f} GeV",
            f"{r['offset_from_pdg_gev']:+.{d}f} GeV",
            f"{fmt(c['fit_choice_spread_gev'], f'.{d}f')} GeV",
            (f"{alt['model']}: {alt['peak_position_gev']:.{d}f} GeV, χ²/ndf {alt['chi2_ndf']:.3f}" if alt
             else "failed"),
        ])
    labels = ["Model, fit range", "Events read", "Opposite-sign pairs in the fit range",
              "Peak (pole) position, observed", "Statistical error, raw", "Statistical error, scaled",
              "Resolution, observed", "χ²/ndf **benchmark**",
              "χ²/ndf, observed", "Fit p-value, observed", "PDG mass (reference)", "Offset from PDG, observed",
              "Fit-choice spread, observed", "Alternate fit, observed"]
    lines = ["| quantity | " + " | ".join(CHANNEL_LABELS[n] for n in names) + " |", "|---|" + "---|" * len(names)]
    for i, label in enumerate(labels):
        lines.append(f"| {label} | " + " | ".join(row[i] for row in rows) + " |")
    return "\n".join(lines)


def render_results_block(production_json: dict[str, Any]) -> str:
    """Return the Markdown of the README results block (without the marker lines).

    ``production_json`` is the parsed results/production.json (schema in the
    module docstring). The output is deterministic: the same input gives the
    same text. Every number comes from the input; nothing is typed by hand.

    Raises
    ------
    ValueError
        If the input does not follow the schema.
    """
    _validate(production_json)
    if "targets" in production_json and "channels" in production_json:
        sample = production_json["sample"]
        banner = dry_run_banner(production_json)
        intro = ("Numbers from a dry run (generated by scripts/render_results.py)." if banner else
                 f"Results from the pre-registered production sample, {sample['n_files']} files "
                 f"(generated by scripts/render_results.py).")
        parts = [banner] if banner else []
        parts += [intro + " Unofficial analysis of CMS Open Data: these are not CMS results.",
                  "**Controlling benchmarks and observed values.** A benchmark is a requirement fixed before the "
                  "sample was opened; it is not a result. The observed column is what was measured; a benchmark that "
                  "was missed stays listed as not met.",
                  targets_table(production_json),
                  "**Headline fits (observed).** Peak positions are not mass measurements: no muon momentum-scale "
                  "corrections are applied.",
                  headline_table(production_json)]
        return "\n\n".join(parts)
    sample, fit, pdg = production_json["sample"], production_json["fit"], production_json["pdg"]
    lo, hi = fit["fit_range_gev"]
    offset = fit["peak_position_gev"] - pdg["mass_gev"]
    rows = [
        ("Production sample", f"{sample['n_files']} files, {sample['n_events']:,} events, "
                              f"{sample['n_pairs']:,} opposite-sign pairs"),
        ("Fit", f"{fit['model']}, {lo:g}-{hi:g} GeV"),
        ("Peak position", f"{fit['peak_position_gev']:.3f} +- {fit['stat_error_gev']:.3f} (stat.) GeV"),
        ("Resolution", f"{fit['resolution_gev']:.3f} +- {fit['resolution_error_gev']:.3f} GeV"),
        ("chi2 / ndf", f"{fit['chi2']:.1f} / {fit['ndf']}"),
        ("PDG Z mass", f"{pdg['mass_gev']:.4f} GeV ({pdg['source']})"),
        ("Offset from PDG", f"{offset:+.3f} GeV"),
    ]
    if "fit_choice_spread_gev" in production_json:
        rows.append(("Fit-choice spread", f"{production_json['fit_choice_spread_gev']:.3f} GeV"))
    lines = ["Results from the pre-registered production sample (generated by scripts/render_results.py).", "",
             "| quantity | value |", "|---|---|"]
    lines += [f"| {name} | {value} |" for name, value in rows]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Parse the command line, run the demo or tool, and return the exit status."""
    args = sys.argv[1:] if argv is None else argv
    path = Path(args[0] if args else "results/production.json")
    if not path.exists():
        print(f"error: {path} does not exist (only the production run creates it)", file=sys.stderr)
        return 1
    print(render_results_block(json.loads(path.read_text())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
