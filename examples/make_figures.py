"""Make the final figures of the Z -> mu+ mu- analysis from real CMS files.

Runs the whole chain on every event of one or more files (one file at a
time, in the order given, so memory holds one file's arrays; the masses and
muon values are concatenated in that order and the cutflows added): the Z -> mu mu selection
(dimuon trigger, then cmsopen.ZMUMU_MUON_CUTS, then at least two muons),
opposite-sign pairs, one per event with best_pair "highest_pt_sum", and
two fits over the Z_mumu channel's fit range: its default model (the same
fit as cmsopen.analyze; ``--model`` overrides it) and the alternate model
analyze reports next to it. The figures that predate Layer 6b used
voigt_poly with gauss_poly as the comparison: ``--model voigt_poly`` gives
that fit. The data label of the figures (the run periods) comes from
cmsopen.datasets.run_label. Writes to OUTDIR (default build/figures/, which
is not tracked by git):

    z_peak_fit.png/.pdf      the mass spectrum with the fit and pulls
    z_peak_fit_caption.md    the caption, with every fit parameter and the alternate fit for comparison
    z_os_vs_ss.png           opposite- vs same-sign pairs, loose selection, log scale
    muon_pt.png              muon pT, all muons vs selected
    muon_eta.png             muon eta, all muons vs selected, with the |eta| = 2.4 edges
    cutflow.png              events left after each selection step
    README.md                what each figure is, how to regenerate it, data and versions

docs/figures/ is protected documentation (see "Documentation freeze" in
CLAUDE.md). The script writes there only with --production, and then only
if the git working tree is clean. That is for the final production run,
on the user's explicit instruction; never run it otherwise.

Usage:
    python examples/make_figures.py [--file PATH [PATH ...]] [--model MODEL] [--outdir DIR]
    python examples/make_figures.py --production [--file PATH [PATH ...]]
"""

from __future__ import annotations

import argparse
import platform
import subprocess
import sys
from dataclasses import dataclass, field
from importlib import metadata
from pathlib import Path
from typing import Any

import awkward as ak
import numpy as np

from cmsopen import (
    ZMUMU_MUON_CUTS,
    best_pair,
    fit_mass_peak,
    make_histogram,
    open_events,
    opposite_sign_pairs,
    same_sign_pairs,
    select_muons,
)
from cmsopen.datasets import run_label
from cmsopen.fitting import MODELS, compare_to_pdg, pdg_mass_width
from cmsopen.ingestion import DIMUON_TRIGGERS_2012
from cmsopen.pipeline import _ALTERNATE_MODEL, CHANNELS, resonance_label
from cmsopen.plotting import (
    plot_cutflow,
    plot_eta_distribution,
    plot_mass_spectrum,
    plot_os_vs_ss,
    plot_pt_distribution,
    save_figure,
)
from cmsopen.selection import CutFlow

REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUTDIR = REPO / "build" / "figures"
PRODUCTION_OUTDIR = REPO / "docs" / "figures"
BOLD, RESET = "\033[1m", "\033[0m"
CHANNEL = CHANNELS["Z_mumu"]
MAIN_MODEL = CHANNEL.model  # the channel default, as in cmsopen.analyze
OTHER_MODEL = _ALTERNATE_MODEL[MAIN_MODEL]
EXPECTED = {
    "z_peak_fit": ("png", "pdf"),
    "z_os_vs_ss": ("png",),
    "muon_pt": ("png",),
    "muon_eta": ("png",),
    "cutflow": ("png",),
}
PACKAGES = ("cmsopen", "numpy", "awkward", "uproot", "scipy", "matplotlib", "hist", "particle")


@dataclass
class Figures:
    """The figures, the fits behind them and the files written."""

    figures: dict[str, Any] = field(default_factory=dict)
    fits: dict[str, Any] = field(default_factory=dict)
    files: dict[str, list[Path]] = field(default_factory=dict)
    data_files: list[Path] = field(default_factory=list)
    main_model: str = MAIN_MODEL
    other_model: str = OTHER_MODEL
    data_label: str = ""
    histograms: dict[str, Any] = field(default_factory=dict)
    cutflow: CutFlow | None = None


@dataclass
class _FileValues:
    """What one file contributes: chosen-pair masses, loose OS/SS masses, muon pT/eta and the cutflow."""

    mass: np.ndarray
    os_mass: np.ndarray
    ss_mass: np.ndarray
    pt: np.ndarray
    eta: np.ndarray
    pt_all: np.ndarray
    eta_all: np.ndarray
    cutflow: CutFlow


def _flat(array: Any) -> np.ndarray:
    return np.asarray(ak.to_numpy(ak.flatten(array, axis=None)), dtype=np.float64)


def _file_values(path: Path) -> _FileValues:
    """Run the selection on one file and keep only the flat values the figures need."""
    with open_events(path) as events:
        everything = select_muons(events)
        triggered = everything.require_trigger(*DIMUON_TRIGGERS_2012)
        loose = events.muons(min_pt=20.0, max_eta=2.4).require_trigger(*DIMUON_TRIGGERS_2012).require(2)
    final = triggered.apply(**ZMUMU_MUON_CUTS).require(2)
    best = best_pair(opposite_sign_pairs(final), "highest_pt_sum")
    return _FileValues(
        mass=_flat(best.mass),
        os_mass=_flat(opposite_sign_pairs(loose).mass),
        ss_mass=_flat(same_sign_pairs(loose).mass),
        pt=_flat(final.particles.p4.pt),
        eta=_flat(final.particles.p4.eta),
        pt_all=_flat(everything.particles.p4.pt),
        eta_all=_flat(everything.particles.p4.eta),
        cutflow=final.cutflow(),
    )


def default_file() -> Path:
    """The first ROOT file in the repository's data/ directory (exits with a message if there is none)."""
    files = sorted((REPO / "data").glob("*.root"))
    if not files:
        sys.exit(f"error: no .root file in {REPO / 'data'}; download one (see DATA.md) or pass --file PATH")
    return files[0]


def build(paths: Path | list[Path], model: str | None = None) -> Figures:
    """Run the analysis on ``paths`` (one file or several, in order) and build every figure (nothing is written).

    Each file is processed on its own; the per-file values are concatenated in
    file order and the cutflows added (:meth:`CutFlow.combine`), so the
    figures of several files are those of their union. ``model`` (default:
    the channel's default model) is fitted exactly as cmsopen.analyze fits it,
    together with analyze's alternate model for comparison.
    """
    main = MAIN_MODEL if model is None else model
    if main not in MODELS:
        raise ValueError(f"model must be one of {MODELS}, got {main!r}")
    files = [paths] if isinstance(paths, Path) else list(paths)
    if not files:
        raise ValueError("build() needs at least one file")
    parts = [_file_values(p) for p in files]

    def cat(name: str) -> np.ndarray:
        return np.concatenate([getattr(v, name) for v in parts])

    out = Figures(data_files=files, main_model=main, other_model=_ALTERNATE_MODEL[main], data_label=run_label(files))
    out.cutflow = CutFlow.combine([v.cutflow for v in parts])
    cfg = CHANNEL
    h = make_histogram(cat("mass"), bins=cfg.bins, range=cfg.mass_range)
    out.histograms["z_peak"] = h
    pdg_mass, _, width, _ = pdg_mass_width(cfg.resonance)
    for name in (out.main_model, out.other_model):  # the same call as cmsopen.analyze
        out.fits[name] = fit_mass_peak(h, model=name, fit_range=cfg.fit_range, poly_degree=cfg.poly_degree,
                                       natural_width=width, cb_n=cfg.cb_n)
    fit = out.fits[out.main_model]
    symbol = resonance_label(cfg)
    out.figures["z_peak_fit"], _ = plot_mass_spectrum(
        h, fit, resonance_label=symbol, pdg_mass=pdg_mass, natural_width=width if fit.gamma is not None else None,
        data_label=out.data_label,
    )

    h_os = make_histogram(cat("os_mass"), bins=cfg.bins, range=cfg.mass_range)
    h_ss = make_histogram(cat("ss_mass"), bins=cfg.bins, range=cfg.mass_range)
    out.histograms["os"], out.histograms["ss"] = h_os, h_ss
    out.figures["z_os_vs_ss"], _ = plot_os_vs_ss(
        h_os, h_ss, selection="Loose selection: no ID, no isolation", resonance_label=symbol, pdg_mass=pdg_mass
    )

    out.figures["muon_pt"], _ = plot_pt_distribution(cat("pt"), before=cat("pt_all"))
    out.figures["muon_eta"], _ = plot_eta_distribution(cat("eta"), before=cat("eta_all"))
    out.figures["cutflow"], _ = plot_cutflow(out.cutflow)
    return out


_MODEL_TEXT = {
    "voigt_poly": "a Voigt peak (a Breit-Wigner of the Z natural width, fixed, convolved with a free Gaussian "
                  "resolution) plus a quadratic background",
    "gauss_poly": "a Gaussian peak plus a quadratic background",
    "cb_bw_exp": "a Breit-Wigner of the Z natural width (fixed) convolved with a Crystal Ball resolution function "
                 "(Gaussian core with a power-law low-mass tail for final-state radiation; tail exponent n fixed) "
                 "plus an exponential background",
    "cb_bw_poly2": "a Breit-Wigner of the Z natural width (fixed) convolved with a Crystal Ball resolution function "
                   "(tail exponent n fixed) plus a quadratic background",
    "cb2_bw_exp": "a Breit-Wigner of the Z natural width (fixed) convolved with the sum of two Crystal Balls of "
                  "widths sigma1 and r * sigma1 (a fraction f in the narrow one; shared alpha and fixed n), for the "
                  "mix of muon momentum resolutions, plus an exponential background",
    "cb2_bw_poly2": "a Breit-Wigner of the Z natural width (fixed) convolved with the sum of two Crystal Balls of "
                    "widths sigma1 and r * sigma1 (a fraction f in the narrow one; shared alpha and fixed n) plus a "
                    "quadratic background",
    "cb3_bw_exp": "a Breit-Wigner of the Z natural width (fixed) convolved with the sum of three Crystal Balls of "
                  "widths sigma1, r2 * sigma1 and r2 * s * sigma1 (fractions f1, (1 - f1) g and (1 - f1)(1 - g); "
                  "shared alpha and fixed n) plus an exponential background",
    "cb3_bw_poly2": "a Breit-Wigner of the Z natural width (fixed) convolved with the sum of three Crystal Balls of "
                    "widths sigma1, r2 * sigma1 and r2 * s * sigma1 (fractions f1, (1 - f1) g and (1 - f1)(1 - g); "
                    "shared alpha and fixed n) plus a quadratic background",
}


def _pm(fit: Any, name: str, digits: int = 3) -> str:
    v, e = fit.parameters[name]
    return f"{v:.{digits}f} +- {e:.{digits}f}"


def _fit_line(fit: Any) -> str:
    """Every fitted quantity of one fit, including those the figure annotation may leave out."""
    m, me = fit.peak_position
    s, se = fit.resolution
    c = compare_to_pdg(fit)
    position = "pole mass" if fit.cb_n is not None else "peak position"
    mixture = "r" in fit.parameters or "r2" in fit.parameters
    width = "resolution (FWHM/2.355 of the signal)" if mixture else "sigma"
    extra = []
    if "r2" in fit.parameters:
        extra.append(f"sigma1 {_pm(fit, 'sigma')} GeV, r2 {_pm(fit, 'r2')}, s {_pm(fit, 's')}, f1 {_pm(fit, 'f1')}, "
                     f"g {_pm(fit, 'g')}")
    if "r" in fit.parameters:
        extra.append(f"sigma1 {_pm(fit, 'sigma')} GeV, r {_pm(fit, 'r')}, f {_pm(fit, 'f')}")
    if fit.cb_n is not None:
        extra.append(f"alpha {_pm(fit, 'alpha')}, n = {fit.cb_n:g} (fixed)")
    if fit.gamma is not None:
        extra.append(f"natural width {2 * fit.gamma:.4f} GeV (fixed)")
    return (
        f"{position} {m:.3f} +- {me:.3f} GeV (stat.), {width} {s:.3f} +- {se:.3f} GeV, "
        + "".join(f"{x}, " for x in extra)
        + f"chi2/ndf = {fit.chi2:.1f}/{fit.ndf}; {c.difference:+.3f} GeV ({100 * c.relative_difference:+.2f} %) "
        f"from the PDG mass {c.pdg_mass:.4f} GeV"
    )


def _yields_sentence(fits: dict[str, Any]) -> str:
    unreliable = [name for name, fit in fits.items() if not fit.yields_reliable]
    if not unreliable:
        return "Signal and background yields are given in the figure annotation."
    which = "both fits" if len(unreliable) == len(fits) else f"the {', '.join(unreliable)} fit"
    return (
        f"Signal and background yields are not quoted: in {which} the fitted background goes below zero "
        "inside the fit range, most likely because the peak model does not describe the radiative tail "
        "below the Z and the background bends to absorb it."
    )


def caption(fits: dict[str, Any], main_model: str = MAIN_MODEL, other_model: str = OTHER_MODEL,
            data_label: str = "") -> str:
    """The caption of z_peak_fit: the figure, both fits with every parameter, the data and the caveats."""
    main, other = fits[main_model], fits[other_model]
    data = data_label.replace(r"$\sqrt{s}$", "sqrt(s)") if data_label else "CMS 2012 open data"
    return f"""# z_peak_fit

Invariant mass of the two muons of one opposite-sign pair per event (the pair with the highest
pT sum), after the Z -> mu+ mu- selection, in 1 GeV bins ({data}), with a fit of
{_MODEL_TEXT[main_model]} over {main.fit_range[0]:g}-{main.fit_range[1]:g} GeV (model `{main_model}`, the
natural width from the `particle` package). The lower panel shows (data - fit) / sigma per bin. The dotted
line is the PDG Z mass, drawn for reference only; the fit does not use it.

- `{main_model}` (shown): {_fit_line(main)}.
- `{other_model}` (same data, same range, not shown): {_fit_line(other)}.

{_yields_sentence(fits)}
Uncertainties are statistical only. The offset from the PDG mass reflects the absent muon momentum-scale
corrections and the simple line shape; it is not a measurement of the Z mass. Unofficial analysis of CMS Open
Data.
"""


_ROW_FIT = (
    "| `z_peak_fit.png`, `z_peak_fit.pdf` | Dimuon mass spectrum with the fit (model `{model}`), background, "
    "signal band, PDG Z mass and pull panel. Caption: [`z_peak_fit_caption.md`](z_peak_fit_caption.md). |"
)
_ROW_OS_SS = (
    "| `z_os_vs_ss.png` | Opposite- vs same-sign pair masses (all candidates) for a loose selection (pT > 20 GeV, "
    "abs(eta) < 2.4, dimuon trigger, no ID or isolation), log scale: the peak is opposite-sign only. |"
)


def _plain(label: str) -> str:
    return label.replace(r"$\sqrt{s}$", "sqrt(s)")


def _data_section(data_files: list[Path]) -> str:
    if len(data_files) == 1:
        f = data_files[0]
        return (f"`{f.name}` ({f.stat().st_size:,} bytes): {_plain(run_label([f]))}, NanoAOD Run 1, from the "
                "CERN Open Data\nportal; see `DATA.md`.")
    rows = "\n".join(f"| `{f.name}` | {f.stat().st_size:,} |" for f in data_files)
    return (f"{len(data_files)} NanoAOD Run 1 files ({_plain(run_label(data_files))}) from the CERN Open Data "
            f"portal, analysed in this order:\n\n| file | bytes |\n|---|---|\n{rows}")


def readme(fits: dict[str, Any], data_files: list[Path], main_model: str = MAIN_MODEL) -> str:
    """The README of the figures directory: what each figure is, how to regenerate it, data and versions."""
    try:
        commit = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"], capture_output=True,
                                text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        commit = "unknown"
    versions = "\n".join(f"| {pkg} | {metadata.version(pkg)} |" for pkg in PACKAGES)
    return f"""# Figures

Final figures of the cmsopen Z -> mu+ mu- analysis of real CMS Open Data. Unofficial analysis of CMS Open
Data: these are not CMS results.

| file | content |
|---|---|
{_ROW_FIT.format(model=main_model)}
{_ROW_OS_SS}
| `muon_pt.png` | Muon pT: every muon in the file vs the muons passing the full selection. |
| `muon_eta.png` | Muon eta: every muon vs the selected muons, with the abs(eta) = 2.4 acceptance edges. |
| `cutflow.png` | Events left after each step of the selection, with the percentage of all events. |

## Regenerate

From the repository root, with the package installed (`pip install -e ".[dev]"`):

```bash
python examples/make_figures.py --production --file {" ".join(f"data/{f.name}" for f in data_files)}\
{"" if main_model == MAIN_MODEL else f" --model {main_model}"}
```

The output is deterministic: rerunning on the same data and software gives byte-identical files.

## Data

{_data_section(data_files)}

## Software

Generated from commit `{commit}` with Python {platform.python_version()}:

| package | version |
|---|---|
{versions}
"""


def write(figs: Figures, outdir: Path) -> Figures:
    """Save every figure, the caption and the README into ``outdir``."""
    outdir.mkdir(parents=True, exist_ok=True)
    for name, formats in EXPECTED.items():
        figs.files[name] = save_figure(figs.figures[name], outdir / name, formats=formats)
    (outdir / "z_peak_fit_caption.md").write_text(caption(figs.fits, figs.main_model, figs.other_model,
                                                          figs.data_label))
    (outdir / "README.md").write_text(readme(figs.fits, figs.data_files, figs.main_model))
    return figs


def _inside(path: Path, directory: Path) -> bool:
    try:
        path.resolve().relative_to(directory.resolve())
    except ValueError:
        return False
    return True


def _working_tree_clean() -> tuple[bool, str]:
    try:
        out = subprocess.run(
            ["git", "-C", str(REPO), "status", "--porcelain"], capture_output=True, text=True, check=True
        ).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        return False, f"cannot run git status: {exc}"
    return not out.strip(), out


def main(argv: list[str] | None = None) -> int:
    """Parse the command line, run the demo or tool, and return the exit status."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--file", type=Path, nargs="+", action="extend", default=None,
                        help="NanoAOD ROOT file(s), analysed in the order given (default: first data/*.root)")
    parser.add_argument("--model", default=None, choices=MODELS,
                        help=f"peak model (default: the Z_mumu channel's {MAIN_MODEL}; voigt_poly gives the figures "
                             "made before Layer 6b)")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--outdir", type=Path, default=None, help=f"output directory (default {DEFAULT_OUTDIR})")
    group.add_argument(
        "--production",
        action="store_true",
        help=f"write into {PRODUCTION_OUTDIR} (protected documentation; clean working tree required)",
    )
    args = parser.parse_args(argv)
    if args.production:
        print(
            f"{BOLD}WARNING: --production OVERWRITES PROTECTED DOCUMENTATION in {PRODUCTION_OUTDIR}. "
            f"Run it only for the final production run, on explicit instruction.{RESET}",
            file=sys.stderr,
        )
        clean, detail = _working_tree_clean()
        if not clean:
            print(f"error: refusing --production: the git working tree is not clean:\n{detail}", file=sys.stderr)
            return 1
        args.outdir = PRODUCTION_OUTDIR
    else:
        args.outdir = args.outdir or DEFAULT_OUTDIR
        if _inside(args.outdir, REPO / "docs"):
            print(
                f"error: {args.outdir} is protected documentation; use --production for that "
                f"(see CLAUDE.md, Documentation freeze)",
                file=sys.stderr,
            )
            return 1
    paths = [p.resolve() for p in (args.file or [default_file()])]
    figs = write(build(paths, args.model), args.outdir)
    for paths in figs.files.values():
        for p in paths:
            print(f"{p}  {p.stat().st_size:,} bytes")
    print(f"{args.outdir / 'z_peak_fit_caption.md'}")
    print(f"{args.outdir / 'README.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
