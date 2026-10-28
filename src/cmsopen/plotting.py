"""Layer 7: publication-quality figures of the dimuon analysis, in plain matplotlib.

Plotting choices, and the physics behind them
---------------------------------------------
*Data are points with error bars; models are lines.* A bin count is a
measurement with a statistical uncertainty: it is a Poisson random number,
so its standard deviation is sqrt(N). Drawing it as a point with a vertical
bar of +-sqrt(N) shows both the value and how far it could have fluctuated.
A fitted model is a smooth prediction with no fluctuation of its own, so it
is drawn as a line. The horizontal extent of each bin is not an uncertainty
and is not drawn; the bin width is stated in the y-axis label instead.

*The bin width is in the y label.* "Events / 1 GeV" says what a count means.
The same data in 2 GeV bins have twice the counts per bin, so a plot whose
label omits the width cannot be compared with another binning or with a
calculation of the rate per GeV.

*Signal and background are drawn separately.* The fit is a sum. Showing
the background as a dashed line and the signal as the shaded region above
it shows how much of each bin the fit attributes to the Z, and makes a
failure of the decomposition (a background that bends unphysically) visible.

*A pull panel shows where the model fails.* Below the spectrum, each bin's
(data - fit) / error is drawn. If the model is right, these pulls scatter
around 0 with unit spread, about 95 % of them inside +-2; a run of
same-sign pulls points to a missing feature (for the Z, the radiative tail
below the peak). A curve that "looks good" on a linear peak plot can hide
large, systematic disagreements in the tails; the pull panel cannot.

*The PDG mass is a reference line, not a target.* The dotted line marks the
world-average Z mass read from the ``particle`` package. The fit does not
use it: the peak position is measured from the data alone, and the
offset between the two is part of the result (momentum scale, radiation).

*An "Unofficial analysis of CMS Open Data" note.* These are real CMS data,
but this analysis has not gone through CMS's calibration, review and
approval, and the figures must not be mistaken for official CMS results.
No CMS logo or "CMS Preliminary"-style label is drawn.

Style
-----
:func:`paper_style` sets serif text with STIX math (fonts that ship with
matplotlib), 10 pt text, inward ticks on all four sides with minor ticks,
no grid, a frameless legend, thin axes, the Okabe-Ito colour-blind-safe
palette together with distinct line styles (so the figures also read in
grayscale), editable TrueType text in PDF (``pdf.fonttype`` 42) and 300 dpi
output. Figures are 5 inches wide, the usual 1.5-column size: reduced to
a 3.4 inch single column the 10 pt text is still about 7 pt.

Figures are built on :class:`matplotlib.figure.Figure` with the Agg canvas,
without ``matplotlib.pyplot``: they work headless, keep no global state, and
display inline in Jupyter when returned. matplotlib itself is imported only
when a function here is called, so ``import cmsopen`` stays light.
"""

from __future__ import annotations

import contextlib
import math
from collections.abc import Iterator
from typing import Any


__all__ = ["FOOTNOTE", "OKABE_ITO", "apply_paper_style", "paper_rc", "paper_style"]

OKABE_ITO: dict[str, str] = {
    "black": "#000000",
    "orange": "#E69F00",
    "sky_blue": "#56B4E9",
    "green": "#009E73",
    "yellow": "#F0E442",
    "blue": "#0072B2",
    "vermillion": "#D55E00",
    "purple": "#CC79A7",
}
"""The Okabe-Ito palette: eight colours distinguishable with the common forms of colour blindness."""

FOOTNOTE = "Unofficial analysis of CMS Open Data"
"""Printed on every figure: the data are real CMS data, the analysis is not an official CMS result."""

DATA_SOURCE = r"2012C DoubleMuParked, $\sqrt{s}$ = 8 TeV"
SERIF_FONTS = ("STIX Two Text", "STIXGeneral", "DejaVu Serif")
"""Serif text fonts in order of preference; all ship with matplotlib (STIX Two from 3.10, the others earlier)."""
WIDTH = 5.0  # inches: 1.5-column figure width
_ANNOTATION_GID = "annotation"
_LOCATIONS = ("upper right", "upper left", "center right", "center left", "lower right", "lower left")


# -- style -----------------------------------------------------------------------------


def paper_rc() -> dict[str, Any]:
    """Return the rcParams of the paper style (see the module docstring)."""
    from cycler import cycler

    colors = [OKABE_ITO[c] for c in ("black", "blue", "vermillion", "green", "orange", "purple", "sky_blue", "yellow")]
    styles = ["-", "--", "-.", ":", (0, (5, 1, 1, 1, 1, 1)), (0, (3, 1)), (0, (1, 1)), (0, (7, 2))]
    # Concrete font names, not the generic "serif": a generic family is resolved to a font only when
    # text is drawn, from whatever font.serif is set globally at that moment, so a figure built inside
    # paper_style() would be measured with one font and saved or displayed with another.
    return {
        "font.family": list(SERIF_FONTS),
        "font.serif": list(SERIF_FONTS),
        "mathtext.fontset": "stix",
        "font.size": 10.0,
        "axes.labelsize": 11.0,
        "axes.titlesize": 10.0,
        "legend.fontsize": 9.0,
        "xtick.labelsize": 10.0,
        "ytick.labelsize": 10.0,
        "axes.linewidth": 0.6,
        "axes.grid": False,
        "axes.prop_cycle": cycler(color=colors, linestyle=styles),
        "axes.formatter.use_mathtext": True,
        "axes.formatter.limits": (-4, 5),
        "xtick.direction": "in",
        "ytick.direction": "in",
        "xtick.top": True,
        "ytick.right": True,
        "xtick.minor.visible": True,
        "ytick.minor.visible": True,
        "xtick.major.size": 5.0,
        "ytick.major.size": 5.0,
        "xtick.minor.size": 2.5,
        "ytick.minor.size": 2.5,
        "xtick.major.width": 0.6,
        "ytick.major.width": 0.6,
        "xtick.minor.width": 0.5,
        "ytick.minor.width": 0.5,
        "lines.linewidth": 1.3,
        "lines.markersize": 3.5,
        "errorbar.capsize": 0.0,
        "legend.frameon": False,
        "legend.handlelength": 2.2,
        "legend.borderaxespad": 0.6,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        "svg.fonttype": "none",
        "savefig.dpi": 300,
        "figure.dpi": 100,
        "image.cmap": "cividis",
    }


@contextlib.contextmanager
def paper_style() -> Iterator[None]:
    """Context manager: apply the paper style, and restore the previous rcParams on exit."""
    import matplotlib

    with matplotlib.rc_context(paper_rc()):
        yield


def apply_paper_style() -> None:
    """Apply the paper style globally (for the rest of the session; :func:`paper_style` is scoped)."""
    import matplotlib

    matplotlib.rcParams.update(paper_rc())
