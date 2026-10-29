"""Apply the model-choice rule of dev/model_choice.md to the development file and print the tables.

For each channel: scan the Crystal Ball exponent cb_n with cb_bw_exp and keep
the lowest chi2/ndf; then fit voigt_poly, cb_bw_exp and cb_bw_poly2 with
that cb_n, mark each model eligible or not (converged, no parameter on a
bound, background positive over the fit range), and choose the lowest
chi2/ndf, or the lower AIC among eligible models within 5 % of it. Every fit
is the one analyze() makes: the channel's cuts, histogram, fit range and
polynomial degree, the natural width from the particle package.

Prints Markdown tables and the outcome; changes nothing.

Usage:
    python scripts/model_choice.py [--file PATH]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from cmsopen import analyze
from cmsopen.datasets import DEV_FILENAME
from cmsopen.fitting import FitError, FitResult, MassHistogram, fit_mass_peak, pdg_mass_width
from cmsopen.pipeline import CHANNELS, ChannelConfig

CB_N_GRID = (1, 2, 3, 5, 10, 20)
COMPARED = ("voigt_poly", "cb_bw_exp", "cb_bw_poly2")
CLOSE = 0.05  # chi2/ndf within 5 % of the lowest: decide by AIC
REPO = Path(__file__).resolve().parents[1]


def fit(h: MassHistogram, cfg: ChannelConfig, model: str, cb_n: float) -> FitResult:
    """The primary fit analyze() makes for this channel and model, with the given Crystal Ball exponent."""
    return fit_mass_peak(
        h,
        model=model,
        fit_range=cfg.fit_range,
        poly_degree=cfg.poly_degree,
        natural_width=pdg_mass_width(cfg.resonance)[2],
        cb_n=cb_n,
    )


def aic(r: FitResult) -> float:
    """Akaike information criterion of a binned chi2 fit: chi2 + 2k (k free parameters)."""
    return r.chi2 + 2 * len(r.values)


def pm(value: float, error: float, digits: int) -> str:
    """``value +- error`` with a fixed number of decimals."""
    return f"{value:.{digits}f} +- {error:.{digits}f}"


def scan(h: MassHistogram, cfg: ChannelConfig) -> tuple[float | None, list[str]]:
    """Step 1: the cb_n with the lowest chi2/ndf (cb_bw_exp), and the Markdown table of the scan."""
    rows = ["| cb_n | chi2 / ndf | chi2/ndf | p-value | pole M [GeV] | sigma [GeV] | alpha |", "|---|---|---|---|---|---|---|"]
    best: tuple[float, float] | None = None
    for n in CB_N_GRID:
        try:
            r = fit(h, cfg, "cb_bw_exp", float(n))
        except FitError as exc:
            rows.append(f"| {n} | failed: {exc} | | | | | |")
            continue
        m, s, a = r.peak_position, r.resolution, r.parameters["alpha"]
        d = 4 if m[0] < 10 else 3
        rows.append(
            f"| {n} | {r.chi2:.1f} / {r.ndf} | {r.chi2_ndf:.4f} | {r.p_value:.3g} | {pm(*m, d)} | {pm(*s, d)} | "
            f"{pm(*a, 3)} |"
        )
        key = round(r.chi2_ndf, 4)
        if best is None or key < best[0]:  # ties go to the smaller n (the grid is ascending)
            best = (key, float(n))
    return (None if best is None else best[1]), rows


def compare(h: MassHistogram, cfg: ChannelConfig, cb_n: float) -> tuple[str | None, list[str], list[str]]:
    """Step 2: eligibility and the choice among COMPARED; returns (model, table rows, reasoning lines)."""
    header = (
        "| model | eligible | converged | on bound | background > 0 | chi2 / ndf | chi2/ndf | p-value | "
        "peak or pole [GeV] | resolution [GeV] | signal yield | background yield | yields reliable | k | AIC |"
    )
    rows = [header, "|" + "---|" * 15]
    eligible: dict[str, FitResult] = {}
    for model in COMPARED:
        try:
            r = fit(h, cfg, model, cb_n)
        except FitError as exc:
            rows.append(f"| {model} | no | no ({exc}) |" + " |" * 12)
            continue
        bound, positive = r.on_bound, r.yields_reliable
        ok = not bound and positive
        if ok:
            eligible[model] = r
        m, s = r.peak_position, r.resolution
        d = 4 if m[0] < 10 else 3
        sy, by = r.signal_yield, r.background_yield
        rows.append(
            f"| {model} | {'yes' if ok else 'no'} | yes | {', '.join(bound) or 'none'} | {'yes' if positive else 'no'} "
            f"| {r.chi2:.1f} / {r.ndf} | {r.chi2_ndf:.4f} | {r.p_value:.3g} | {pm(*m, d)} | {pm(*s, d)} "
            f"| {sy[0]:,.0f} +- {sy[1]:,.0f} | {by[0]:,.0f} +- {by[1]:,.0f} | {'yes' if positive else 'no'} "
            f"| {len(r.values)} | {aic(r):.1f} |"
        )
    if not eligible:
        return None, rows, ["No model is eligible; the default stays unchanged."]
    lowest = min(eligible, key=lambda k: eligible[k].chi2_ndf)
    close = [k for k, r in eligible.items() if r.chi2_ndf < (1 + CLOSE) * eligible[lowest].chi2_ndf]
    chosen = min(close, key=lambda k: aic(eligible[k]))
    why = [
        f"Eligible: {', '.join(eligible)}. Lowest chi2/ndf: {lowest} ({eligible[lowest].chi2_ndf:.4f}).",
        f"Within 5 % of it: {', '.join(close)}"
        + (f"; lowest AIC among them: {chosen} ({aic(eligible[chosen]):.1f})." if len(close) > 1 else "."),
        f"Selected: {chosen}.",
    ]
    return chosen, rows, why


def main(argv: list[str] | None = None) -> int:
    """Run the rule for every registered channel on the development file and print the results."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--file", type=Path, default=REPO / "data" / DEV_FILENAME, help="the development file")
    path = parser.parse_args(argv).file.resolve()
    if path.name != DEV_FILENAME:
        print(f"error: the rule is applied to the development file {DEV_FILENAME} only", file=sys.stderr)
        return 2
    if not path.exists():
        print(f"error: file not found: {path}", file=sys.stderr)
        return 2
    outcome: dict[str, Any] = {}
    for name in ("Z_mumu", "Jpsi_mumu"):
        cfg = CHANNELS[name]
        h = analyze(path, channel=name, stability=False, verbose=False).histogram  # the channel's own histogram
        print(f"### {name}\n")
        print(f"Histogram: {h!r}; fit range {cfg.fit_range[0]:g}-{cfg.fit_range[1]:g} GeV.\n")
        cb_n, rows = scan(h, cfg)
        print("Step 1, cb_n scan (cb_bw_exp):\n")
        print("\n".join(rows))
        print(f"\nChosen cb_n: {cb_n}\n")
        if cb_n is None:
            outcome[name] = (None, None)
            print("No cb_n converged; the Crystal Ball models cannot be compared.\n")
            continue
        chosen, table, why = compare(h, cfg, cb_n)
        print(f"Step 2, model comparison (cb_n = {cb_n:g}):\n")
        print("\n".join(table))
        print()
        print("\n".join(why))
        print()
        outcome[name] = (cb_n, chosen)
    print("### Outcome\n")
    for name, (cb_n, chosen) in outcome.items():
        default = "voigt_poly"
        change = "unchanged" if chosen in (None, default) else f"changes from {default} to {chosen}"
        print(f"- {name}: cb_n = {cb_n}; selected model {chosen}; default model {change}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
