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
    python scripts/model_choice.py [--file PATH] [--grid original|amended]

``--grid amended`` uses the cb_n grid of Amendment 1 in dev/model_choice.md.
``--amendment2`` instead applies the resolution-mixture rule of Amendment 2
(the channel's current default against the mixture with the same background,
at the channel's current cb_n). ``--amendment3`` applies the three-resolution
rule of Amendment 3 on the 6-file development set (dev/development_set.json,
in its fixed order); with ``--single`` it fits the development file alone,
for information only.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from cmsopen import analyze
from cmsopen.datasets import DEV_FILENAME
from cmsopen.fitting import FitError, FitResult, MassHistogram, fit_mass_peak, pdg_mass_width
from cmsopen.pipeline import CHANNELS, ChannelConfig

CB_N_GRIDS = {"original": (1, 2, 3, 5, 10, 20), "amended": (1, 2, 3, 5, 10, 20, 30, 50, 100)}  # Amendment 1
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


def scan(h: MassHistogram, cfg: ChannelConfig, grid: tuple[int, ...]) -> tuple[float | None, list[str]]:
    """Step 1: the cb_n with the lowest chi2/ndf (cb_bw_exp), and the Markdown table of the scan."""
    rows = [
        "| cb_n | chi2 / ndf | chi2/ndf | p-value | pole M [GeV] | sigma [GeV] | alpha |",
        "|---|---|---|---|---|---|---|",
    ]
    best: tuple[float, float] | None = None
    for n in grid:
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


MIXTURE_OF = {"cb_bw_exp": "cb2_bw_exp", "cb_bw_poly2": "cb2_bw_poly2"}  # Amendment 2: same background
AIC_MARGIN = 10.0


def amendment2(h: MassHistogram, cfg: ChannelConfig) -> tuple[str, list[str], list[str]]:
    """Amendment 2: the current default, both mixtures, eligibility (a)-(d) for the same-background mixture."""
    default, candidate = cfg.model, MIXTURE_OF.get(cfg.model)
    header = (
        "| model | role | eligible | converged | on bound | background > 0 | chi2 / ndf | chi2/ndf | p-value | "
        "pole [GeV] | sigma1 [GeV] | r | f | FWHM/2.355 [GeV] | signal yield | background yield | k | AIC |"
    )
    rows = [header, "|" + "---|" * 18]
    fits: dict[str, FitResult | None] = {}
    for model in (default, "cb2_bw_exp", "cb2_bw_poly2"):
        role = "current default" if model == default else "candidate" if model == candidate else "information only"
        try:
            r = fit(h, cfg, model, cfg.cb_n)
        except FitError as exc:
            fits[model] = None
            rows.append(f"| {model} | {role} | no | no ({exc}) |" + " |" * 14)
            continue
        fits[model] = r
        d = 4 if r.peak_position[0] < 10 else 3
        mix = "r" in r.parameters
        fwhm, fwhm_err = r.fwhm
        sy, by = r.signal_yield, r.background_yield
        rows.append(
            f"| {model} | {role} | {'yes' if not r.on_bound and r.yields_reliable else 'no'} | yes "
            f"| {', '.join(r.on_bound) or 'none'} | {'yes' if r.yields_reliable else 'no'} | {r.chi2:.1f} / {r.ndf} "
            f"| {r.chi2_ndf:.4f} | {r.p_value:.3g} | {pm(*r.peak_position, d)} | {pm(*r.parameters['sigma'], d)} "
            f"| {pm(*r.parameters['r'], 3) if mix else '-'} | {pm(*r.parameters['f'], 3) if mix else '-'} "
            f"| {pm(fwhm / 2.3548200450309493, fwhm_err / 2.3548200450309493, d)} "
            f"| {sy[0]:,.0f} +- {sy[1]:,.0f} | {by[0]:,.0f} +- {by[1]:,.0f} | {len(r.values)} | {aic(r):.1f} |"
        )
    base, cand = fits[default], fits.get(candidate) if candidate else None
    if candidate is None or base is None:
        return default, rows, [f"No same-background mixture for {default}, or the default failed; unchanged."]
    if cand is None:
        return default, rows, [f"(a) {candidate} did not converge: not eligible. Selected: {default} (unchanged)."]
    checks = [
        ("(a) converged", True),
        ("(b) no parameter on a bound", not cand.on_bound),
        ("(c) background positive over the fit range", cand.yields_reliable),
        (f"(d) AIC {aic(cand):.1f} <= {aic(base):.1f} - {AIC_MARGIN:g} = {aic(base) - AIC_MARGIN:.1f}",
         aic(cand) <= aic(base) - AIC_MARGIN),
    ]
    chosen = candidate if all(ok for _, ok in checks) else default
    why = [f"{candidate}: " + "; ".join(f"{name}: {'yes' if ok else 'NO'}" for name, ok in checks) + "."]
    why.append(f"Selected: {chosen} ({'changes the default' if chosen != default else 'unchanged'}).")
    return chosen, rows, why


THREE_OF = {"cb2_bw_exp": "cb3_bw_exp", "cb2_bw_poly2": "cb3_bw_poly2"}  # Amendment 3: same background
GEV_FWHM = 2.3548200450309493


def development_set() -> list[Path]:
    """The 6 development files in their fixed order (dev/development_set.md)."""
    d = json.loads((REPO / "dev" / "development_set.json").read_text())
    return [REPO / "data" / d["original_development_file"], *(REPO / "data" / f["filename"] for f in d["files"])]


def amendment3(h: MassHistogram, cfg: ChannelConfig) -> tuple[str, list[str], list[str]]:
    """Amendment 3: the current default, both cb3 models, eligibility (a)-(d) for the same-background cb3 model."""
    default, candidate = cfg.model, THREE_OF.get(cfg.model)
    header = (
        "| model | role | eligible | chi2 / ndf | chi2/ndf | p-value | pole [GeV] | sigma1 [GeV] | r (r2) | s | f (f1) "
        "| g | FWHM/2.355 [GeV] | signal yield | background yield | k | AIC | on a bound |"
    )
    rows = [header, "|" + "---|" * 18]
    fits: dict[str, FitResult | None] = {}
    for model in (default, "cb3_bw_exp", "cb3_bw_poly2"):
        role = "current default" if model == default else "candidate" if model == candidate else "information only"
        try:
            r = fit(h, cfg, model, cfg.cb_n)
        except FitError as exc:
            fits[model] = None
            rows.append(f"| {model} | {role} | no: {exc} |" + " |" * 15)
            continue
        fits[model] = r
        d = 4 if r.peak_position[0] < 10 else 3
        par = r.parameters
        fwhm, fwhm_err = r.fwhm
        sy, by = r.signal_yield, r.background_yield

        def get(*names: str, par: dict = par) -> str:
            return next((pm(*par[n], 3) for n in names if n in par), "-")

        rows.append(
            f"| {model} | {role} | {'yes' if not r.on_bound and r.yields_reliable else 'no'} | {r.chi2:.1f} / {r.ndf} "
            f"| {r.chi2_ndf:.4f} | {r.p_value:.3g} | {pm(*r.peak_position, d)} | {pm(*par['sigma'], d)} "
            f"| {get('r2', 'r')} | {get('s')} | {get('f1', 'f')} | {get('g')} "
            f"| {pm(fwhm / GEV_FWHM, fwhm_err / GEV_FWHM, d)} | {sy[0]:,.0f} +- {sy[1]:,.0f} "
            f"| {by[0]:,.0f} +- {by[1]:,.0f} | {len(r.values)} | {aic(r):.1f} | {', '.join(r.on_bound) or 'none'} |"
        )
    base, cand = fits[default], fits.get(candidate) if candidate else None
    if candidate is None or base is None:
        return default, rows, [f"No same-background cb3 model for {default}, or the default failed; unchanged."]
    if cand is None:
        return default, rows, [f"(a)/(b) {candidate} raised FitError (not converged, a parameter on a bound or not "
                               f"constrained): not eligible. Selected: {default} (unchanged)."]
    checks = [
        ("(a) converged", True),
        ("(b) no parameter on a bound, unconstrained-parameter check passed", not cand.on_bound),
        ("(c) background positive over the fit range", cand.yields_reliable),
        (f"(d) AIC {aic(cand):.1f} <= {aic(base):.1f} - {AIC_MARGIN:g} = {aic(base) - AIC_MARGIN:.1f}",
         aic(cand) <= aic(base) - AIC_MARGIN),
    ]
    chosen = candidate if all(ok for _, ok in checks) else default
    why = [f"{candidate}: " + "; ".join(f"{name}: {'yes' if ok else 'NO'}" for name, ok in checks) + "."]
    why.append(f"Selected: {chosen} ({'changes the default' if chosen != default else 'unchanged'}).")
    return chosen, rows, why


def run_amendment3(single: bool, workers: int) -> int:
    """Amendment 3 on the 6-file development set (or the single development file, for information)."""
    files = development_set()[:1] if single else development_set()
    missing = [p.name for p in files if not p.exists()]
    if missing:
        print(f"error: missing development files: {missing}", file=sys.stderr)
        return 2
    label = "the original development file (information only)" if single else "the 6-file development set"
    outcome = {}
    for name in ("Z_mumu", "Jpsi_mumu"):
        cfg = CHANNELS[name]
        h = analyze(files, channel=name, stability=False, verbose=False, n_workers=workers).histogram
        print(f"### {name} (Amendment 3 on {label}; cb_n = {cfg.cb_n:g}, current default {cfg.model})\n")
        chosen, table, why = amendment3(h, cfg)
        print("\n".join(table))
        print()
        print("\n".join(why))
        print()
        outcome[name] = chosen
    print(f"### Outcome of Amendment 3 ({label})\n")
    for name, chosen in outcome.items():
        change = "unchanged" if chosen == CHANNELS[name].model else f"changes to {chosen}"
        print(f"- {name}: default {CHANNELS[name].model} {change}.")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Run the rule for every registered channel on the development file and print the results."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--file", type=Path, default=REPO / "data" / DEV_FILENAME, help="the development file")
    parser.add_argument("--grid", choices=sorted(CB_N_GRIDS), default="original", help="cb_n grid (default original)")
    parser.add_argument("--amendment2", action="store_true", help="apply the resolution-mixture rule of Amendment 2")
    parser.add_argument("--amendment3", action="store_true",
                        help="apply the three-resolution rule of Amendment 3 on the 6-file development set")
    parser.add_argument("--single", action="store_true", help="with --amendment3: the development file alone")
    parser.add_argument("--workers", type=int, default=4, help="with --amendment3: worker processes")
    args = parser.parse_args(argv)
    if args.amendment3:
        return run_amendment3(args.single, args.workers)
    path, grid = args.file.resolve(), CB_N_GRIDS[args.grid]
    if path.name != DEV_FILENAME:
        print(f"error: the rule is applied to the development file {DEV_FILENAME} only", file=sys.stderr)
        return 2
    if not path.exists():
        print(f"error: file not found: {path}", file=sys.stderr)
        return 2
    outcome: dict[str, Any] = {}
    if args.amendment2:
        for name in ("Z_mumu", "Jpsi_mumu"):
            cfg = CHANNELS[name]
            h = analyze(path, channel=name, stability=False, verbose=False).histogram
            print(f"### {name} (Amendment 2; cb_n = {cfg.cb_n:g}, current default {cfg.model})\n")
            chosen, table, why = amendment2(h, cfg)
            print("\n".join(table))
            print()
            print("\n".join(why))
            print()
            outcome[name] = chosen
        print("### Outcome of Amendment 2\n")
        for name, chosen in outcome.items():
            change = "unchanged" if chosen == CHANNELS[name].model else f"changes to {chosen}"
            print(f"- {name}: default {CHANNELS[name].model} {change}.")
        return 0
    for name in ("Z_mumu", "Jpsi_mumu"):
        cfg = CHANNELS[name]
        h = analyze(path, channel=name, stability=False, verbose=False).histogram  # the channel's own histogram
        print(f"### {name}\n")
        print(f"Histogram: {h!r}; fit range {cfg.fit_range[0]:g}-{cfg.fit_range[1]:g} GeV.\n")
        cb_n, rows = scan(h, cfg, grid)
        print(f"Step 1, cb_n scan (cb_bw_exp), grid {args.grid} {grid}:\n")
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
        cfg = CHANNELS[name]
        n_text = "unchanged" if cb_n == cfg.cb_n else f"differs from the registered {cfg.cb_n:g}"
        m_text = "unchanged" if chosen in (None, cfg.model) else f"differs from the registered {cfg.model}"
        print(f"- {name}: selected cb_n = {cb_n} ({n_text}); selected model {chosen} ({m_text}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
