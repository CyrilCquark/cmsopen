"""Make the final figures of the Z -> mu+ mu- analysis from the real CMS file.

Runs the whole chain on every event of the file: the Z -> mu mu selection
(dimuon trigger, then cmsopen.ZMUMU_MUON_CUTS, then at least two muons),
opposite-sign pairs, one per event with best_pair "highest_pt_sum", and
both fit models over 70-110 GeV. Writes to OUTDIR (default docs/figures/):

    z_peak_fit.png/.pdf      the mass spectrum with the Voigt + pol2 fit and pulls
    z_peak_fit_caption.md    the caption, with the Gaussian + pol2 result for comparison
    z_os_vs_ss.png           opposite- vs same-sign pairs, loose selection, log scale
    muon_pt.png              muon pT, all muons vs selected
    muon_eta.png             muon eta, all muons vs selected, with the |eta| = 2.4 edges
    cutflow.png              events left after each selection step
    README.md                what each figure is, how to regenerate it, data and versions

Usage:
    python examples/make_figures.py [--file PATH] [--outdir DIR]
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
from cmsopen.fitting import compare_to_pdg
from cmsopen.ingestion import DIMUON_TRIGGERS_2012
from cmsopen.plotting import (
    plot_cutflow,
    plot_eta_distribution,
    plot_mass_spectrum,
    plot_os_vs_ss,
    plot_pt_distribution,
    save_figure,
)

REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUTDIR = REPO / "docs" / "figures"
MAIN_MODEL = "voigt_poly"
OTHER_MODEL = "gauss_poly"
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
    data_file: Path | None = None


def default_file() -> Path:
    files = sorted((REPO / "data").glob("*.root"))
    if not files:
        sys.exit(f"error: no .root file in {REPO / 'data'}; download one (see DATA.md) or pass --file PATH")
    return files[0]


def build(path: Path) -> Figures:
    """Run the analysis on ``path`` and build every figure (nothing is written)."""
    out = Figures(data_file=path)
    with open_events(path) as events:
        everything = select_muons(events)
        triggered = everything.require_trigger(*DIMUON_TRIGGERS_2012)
        loose = events.muons(min_pt=20.0, max_eta=2.4).require_trigger(*DIMUON_TRIGGERS_2012).require(2)
    final = triggered.apply(**ZMUMU_MUON_CUTS).require(2)

    best = best_pair(opposite_sign_pairs(final), "highest_pt_sum")
    h = make_histogram(best.mass, bins=60, range=(60.0, 120.0))
    for model in (MAIN_MODEL, OTHER_MODEL):
        out.fits[model] = fit_mass_peak(h, model=model, fit_range=(70.0, 110.0), poly_degree=2)
    out.figures["z_peak_fit"], _ = plot_mass_spectrum(h, out.fits[MAIN_MODEL])

    h_os = make_histogram(ak.flatten(opposite_sign_pairs(loose).mass), bins=60, range=(60.0, 120.0))
    h_ss = make_histogram(ak.flatten(same_sign_pairs(loose).mass), bins=60, range=(60.0, 120.0))
    out.figures["z_os_vs_ss"], _ = plot_os_vs_ss(h_os, h_ss, selection="Loose selection: no ID, no isolation")

    out.figures["muon_pt"], _ = plot_pt_distribution(final, before=everything)
    out.figures["muon_eta"], _ = plot_eta_distribution(final, before=everything)
    out.figures["cutflow"], _ = plot_cutflow(final.cutflow())
    return out


def _fit_line(fit: Any) -> str:
    m, me = fit.peak_position
    s, se = fit.resolution
    c = compare_to_pdg(fit)
    return (
        f"peak position {m:.3f} +- {me:.3f} GeV (stat.), sigma {s:.3f} +- {se:.3f} GeV, "
        f"chi2/ndf = {fit.chi2:.1f}/{fit.ndf}; {c.difference:+.3f} GeV ({100 * c.relative_difference:+.2f} %) "
        f"from the PDG mass {c.pdg_mass:.4f} GeV"
    )


def _yields_sentence(fits: dict[str, Any]) -> str:
    unreliable = [name for name, fit in fits.items() if not fit.yields_reliable]
    if not unreliable:
        return "Signal and background yields are given in the figure annotation."
    which = "both fits" if len(unreliable) == len(fits) else f"the {', '.join(unreliable)} fit"
    return (
        f"Signal and background yields are not quoted: in {which} the fitted quadratic background goes below zero "
        "inside the fit range, most likely because the symmetric peak model does not describe the radiative tail "
        "below the Z and the background bends to absorb it."
    )


def caption(fits: dict[str, Any]) -> str:
    main, other = fits[MAIN_MODEL], fits[OTHER_MODEL]
    return f"""# z_peak_fit

Invariant mass of the two muons of one opposite-sign pair per event (the pair with the highest
pT sum), after the Z -> mu+ mu- selection, in 1 GeV bins, with a fit of a Voigt peak (the Breit-Wigner
natural width of the Z fixed to {2 * main.gamma:.4f} GeV from the `particle` package, Gaussian resolution
free) plus a quadratic background over {main.fit_range[0]:g}-{main.fit_range[1]:g} GeV. The lower panel shows
(data - fit) / sigma per bin. The dotted line is the PDG Z mass, drawn for reference only; the fit does not
use it.

- Voigt + pol2 (shown): {_fit_line(main)}.
- Gaussian + pol2 (same data, same range, not shown): {_fit_line(other)}.

{_yields_sentence(fits)}
Uncertainties are statistical only. The offset from the PDG mass reflects the absent muon momentum-scale
corrections and the simple line shape; it is not a measurement of the Z mass. Unofficial analysis of CMS Open
Data.
"""


def readme(fits: dict[str, Any], data_file: Path) -> str:
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
| `z_peak_fit.png`, `z_peak_fit.pdf` | Dimuon mass spectrum with the Voigt + quadratic fit, background, signal band, PDG Z mass and pull panel. Caption: [`z_peak_fit_caption.md`](z_peak_fit_caption.md). |
| `z_os_vs_ss.png` | Opposite- vs same-sign pair masses (all candidates) for a loose selection (pT > 20 GeV, abs(eta) < 2.4, dimuon trigger, no ID or isolation), log scale: the peak is opposite-sign only. |
| `muon_pt.png` | Muon pT: every muon in the file vs the muons passing the full selection. |
| `muon_eta.png` | Muon eta: every muon vs the selected muons, with the abs(eta) = 2.4 acceptance edges. |
| `cutflow.png` | Events left after each step of the selection, with the percentage of all events. |

## Regenerate

From the repository root, with the package installed (`pip install -e ".[dev]"`):

```bash
python examples/make_figures.py --file data/{data_file.name}
```

The output is deterministic: rerunning on the same data and software gives byte-identical files.

## Data

`{data_file.name}` (1,145,602,936 bytes): Run2012C DoubleMuParked, NanoAOD Run 1, from the CERN Open Data
portal; see `DATA.md`.

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
    (outdir / "z_peak_fit_caption.md").write_text(caption(figs.fits))
    (outdir / "README.md").write_text(readme(figs.fits, figs.data_file))
    return figs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--file", type=Path, default=None, help="NanoAOD ROOT file (default: first data/*.root)")
    parser.add_argument("--outdir", type=Path, default=DEFAULT_OUTDIR, help=f"output directory (default {DEFAULT_OUTDIR})")
    args = parser.parse_args()
    path = (args.file or default_file()).resolve()
    figs = write(build(path), args.outdir)
    for paths in figs.files.values():
        for p in paths:
            print(f"{p}  {p.stat().st_size:,} bytes")
    print(f"{args.outdir / 'z_peak_fit_caption.md'}")
    print(f"{args.outdir / 'README.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
