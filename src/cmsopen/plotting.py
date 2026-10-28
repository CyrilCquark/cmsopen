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
import textwrap
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

import awkward as ak
import numpy as np

from cmsopen.fitting import FitResult, MassHistogram, pdg_mass_width
from cmsopen.objects import Muon
from cmsopen.selection import CutFlow, Selection

if TYPE_CHECKING:  # pragma: no cover
    from matplotlib.axes import Axes
    from matplotlib.figure import Figure

__all__ = [
    "FOOTNOTE",
    "OKABE_ITO",
    "apply_paper_style",
    "layout_overlaps",
    "paper_rc",
    "paper_style",
    "plot_cutflow",
    "plot_eta_distribution",
    "plot_mass_spectrum",
    "plot_os_vs_ss",
    "plot_pt_distribution",
    "save_figure",
]

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


def _new_figure(figsize: tuple[float, float]) -> Figure:
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    fig = Figure(figsize=figsize, layout="constrained")
    FigureCanvasAgg(fig)
    return fig


def _prepare_figure(fig: Figure | None, figsize: tuple[float, float]) -> Figure:
    if fig is None:
        return _new_figure(figsize)
    if fig.axes:
        raise ValueError("fig must be empty; pass fig=None to create a new figure")
    if fig.get_layout_engine() is None:
        fig.set_layout_engine("constrained")
    return fig


def _titles(ax: Axes, label: str) -> None:
    """The data label above the axes on the left, the unofficial-analysis footnote on the right."""
    ax.set_title(label, loc="left", fontsize=10)
    ax.set_title(FOOTNOTE, loc="right", fontsize=7.5, color="0.35", style="italic")


def _separate_titles(ax: Axes) -> None:
    """If the left label and the right footnote would touch, lift the label onto its own row."""
    fig = ax.figure
    with _measuring_dpi(fig):
        fig.draw_without_rendering()
        renderer = fig.canvas.get_renderer()
        left, right = ax._left_title, ax._right_title
        gap = 6 * fig.dpi / 72.0
        lb, rb = left.get_window_extent(renderer), right.get_window_extent(renderer)
        if left.get_text() and right.get_text() and lb.x1 + gap > rb.x0:
            left.set_text(left.get_text() + "\n")


# -- layout: keep the legend and the annotation off the data -------------------------------


def _clip_segments(xy: np.ndarray, box: tuple[float, float, float, float]) -> np.ndarray:
    """Clip the segments of a polyline to a rectangle (Liang-Barsky); returns (n, 2, 2) segment ends.

    Only what lies inside the axes can collide with a box drawn inside the
    axes. Clipping first also keeps off-scale vertices (an empty bin on a
    log axis sits at an enormous negative pixel coordinate) from producing
    absurdly long segments.
    """
    xy = np.asarray(xy, dtype=float)
    if len(xy) < 2:
        return np.empty((0, 2, 2))
    p0, p1 = xy[:-1], xy[1:]
    ok = np.all(np.isfinite(p0), axis=1) & np.all(np.isfinite(p1), axis=1)
    p0, p1 = p0[ok], p1[ok]
    d = p1 - p0
    x0, y0, x1, y1 = box
    t0, t1 = np.zeros(len(d)), np.ones(len(d))
    keep = np.ones(len(d), dtype=bool)
    for p, q in ((-d[:, 0], p0[:, 0] - x0), (d[:, 0], x1 - p0[:, 0]), (-d[:, 1], p0[:, 1] - y0), (d[:, 1], y1 - p0[:, 1])):
        parallel = p == 0
        keep &= ~(parallel & (q < 0))
        with np.errstate(divide="ignore", invalid="ignore"):
            r = np.where(parallel, 0.0, q / np.where(parallel, 1.0, p))
        t0 = np.where(~parallel & (p < 0), np.maximum(t0, r), t0)
        t1 = np.where(~parallel & (p > 0), np.minimum(t1, r), t1)
    keep &= t0 <= t1
    a = p0[keep] + t0[keep, None] * d[keep]
    b = p0[keep] + t1[keep, None] * d[keep]
    return np.stack([a, b], axis=1)


def _densify(segments: np.ndarray, step: float = 2.0) -> np.ndarray:
    """Points along each segment, at most ``step`` display pixels apart (vectorized over segments)."""
    if len(segments) == 0:
        return np.empty((0, 2))
    a, b = segments[:, 0], segments[:, 1]
    seg = b - a
    n = np.maximum(1, np.ceil(np.hypot(seg[:, 0], seg[:, 1]) / step)).astype(int) + 1
    idx = np.repeat(np.arange(len(seg)), n)
    frac = (np.arange(n.sum()) - np.repeat(np.cumsum(n) - n, n)) / np.repeat(n - 1, n)
    return a[idx] + seg[idx] * frac[:, None]


def _path_points(paths: Sequence[Any], transform: Any, box: tuple[float, float, float, float]) -> np.ndarray:
    # transform_path applies the non-affine part (a log axis) too; Path.to_polygons(transform) would
    # apply only the affine part and silently measure a log plot as if it were linear.
    polys = []
    for path in paths:
        for poly in transform.transform_path(path).to_polygons(None, closed_only=False):
            polys.append(_densify(_clip_segments(poly, box)))
    return np.vstack(polys) if polys else np.empty((0, 2))


def _obstacles(ax: Axes) -> list[tuple[str, np.ndarray, float]]:
    """Every drawn data element of ``ax`` as (name, display points, radius in pixels)."""
    from matplotlib.collections import PathCollection

    fig = ax.figure
    px_per_pt = fig.dpi / 72.0
    bb = ax.get_window_extent()
    margin = 4 * px_per_pt
    box = (bb.x0 - margin, bb.y0 - margin, bb.x1 + margin, bb.y1 + margin)
    out = []
    for line in ax.lines:
        if not line.get_visible():
            continue
        name = line.get_gid() or line.get_label() or "line"
        xy = line.get_transform().transform(line.get_path().vertices)
        if line.get_marker() not in (None, "", "None", " "):
            radius = 0.5 * line.get_markersize() * px_per_pt + line.get_markeredgewidth() * px_per_pt
            xy = xy[np.all(np.isfinite(xy), axis=1)]
            inside = (xy[:, 0] >= box[0]) & (xy[:, 0] <= box[2]) & (xy[:, 1] >= box[1]) & (xy[:, 1] <= box[3])
            out.append((f"{name} markers", xy[inside], radius))
        if line.get_linestyle() not in ("None", "", " ", None):
            out.append((name, _path_points([line.get_path()], line.get_transform(), box),
                        0.5 * line.get_linewidth() * px_per_pt))
    for coll in ax.collections:
        if not coll.get_visible():
            continue
        name = coll.get_gid() or coll.get_label() or type(coll).__name__
        if isinstance(coll, PathCollection):  # scatter markers: positions in data coordinates
            xy = coll.get_offset_transform().transform(coll.get_offsets())
            radius = 0.5 * math.sqrt(float(np.max(coll.get_sizes(), initial=1.0))) * px_per_pt
            out.append((f"{name} markers", xy, radius))
        else:  # error bars, filled regions, vertical/horizontal lines
            out.append((name, _path_points(coll.get_paths(), coll.get_transform(), box), 1.0))
    for patch in ax.patches:
        if not patch.get_visible():
            continue
        name = patch.get_gid() or patch.get_label() or type(patch).__name__
        out.append((name, _path_points([patch.get_path()], patch.get_transform(), box),
                    0.5 * patch.get_linewidth() * px_per_pt))
    return out


REFERENCE_GIDS = frozenset({"pdg", "acceptance"})
"""Reference lines (not data): they may pass behind a box only if the box has an opaque background."""


def _is_opaque(artist: Any) -> bool:
    patch = artist.get_frame() if hasattr(artist, "get_frame") else artist.get_bbox_patch()
    if patch is None or not patch.get_visible() or (hasattr(artist, "get_frame_on") and not artist.get_frame_on()):
        return False
    return patch.get_facecolor()[3] >= 0.85  # the face colour's alpha already includes the patch alpha


def _boxes(ax: Axes, renderer: Any) -> list[tuple[str, Any, bool]]:
    """(name, display bbox, opaque background?) of the legend and the annotation block."""
    boxes = []
    legend = ax.get_legend()
    if legend is not None and legend.get_visible():
        boxes.append(("legend", legend.get_window_extent(renderer), _is_opaque(legend)))
    for text in ax.texts:
        if text.get_gid() == _ANNOTATION_GID and text.get_visible():
            boxes.append(("annotation", text.get_window_extent(renderer), _is_opaque(text)))
    return boxes


def _box_hits(bb: Any, obstacles: list, pad: float, opaque: bool) -> list[tuple[str, np.ndarray]]:
    hits = []
    for name, pts, radius in obstacles:
        if opaque and name in REFERENCE_GIDS:
            continue
        r = radius + pad
        inside = (pts[:, 0] >= bb.x0 - r) & (pts[:, 0] <= bb.x1 + r) & (pts[:, 1] >= bb.y0 - r) & (pts[:, 1] <= bb.y1 + r)
        if inside.any():
            hits.append((name, pts[inside]))
    return hits


def _axes_overlaps(ax: Axes, renderer: Any, pad_points: float = 1.5) -> list[str]:
    problems = []
    pad = pad_points * ax.figure.dpi / 72.0
    boxes = _boxes(ax, renderer)
    axes_box = ax.get_window_extent(renderer)
    obstacles = _obstacles(ax)
    for box_name, bb, opaque in boxes:
        if bb.x0 < axes_box.x0 - 1 or bb.x1 > axes_box.x1 + 1 or bb.y0 < axes_box.y0 - 1 or bb.y1 > axes_box.y1 + 1:
            problems.append(f"{box_name} extends outside the axes ({bb} vs {axes_box})")
        for name, pts in _box_hits(bb, obstacles, pad, opaque):
            x, y = ax.transData.inverted().transform(pts[0])
            problems.append(f"{box_name} overlaps {name}: {len(pts)} points, e.g. at data ({x:.4g}, {y:.4g})")
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            if boxes[i][1].overlaps(boxes[j][1]):
                problems.append(f"{boxes[i][0]} overlaps {boxes[j][0]}")
    return problems


LAYOUT_DPI = 300
"""Resolution at which layout is measured: the output resolution of :func:`save_figure`."""


@contextlib.contextmanager
def _measuring_dpi(fig: Figure, dpi: float = LAYOUT_DPI) -> Iterator[None]:
    """Temporarily set the figure resolution for measuring layout.

    Layout is measured at the resolution the figure is saved at, so that
    the pixel rounding of text, markers and line widths is the one in the
    output file. (Text extents in points agree between 100 and 300 dpi to
    about 0.2 pt once fonts are concrete; see :func:`paper_rc`.)
    """
    old = fig.dpi
    fig.set_dpi(max(old, dpi))
    try:
        yield
    finally:
        fig.set_dpi(old)


def layout_overlaps(fig: Figure, dpi: float = LAYOUT_DPI) -> list[str]:
    """Describe every overlap of a legend or annotation block with data, curves or each other.

    For each axes, the legend and the annotation text (gid ``"annotation"``)
    are measured with the renderer at the output resolution ``dpi`` and
    compared, in display pixels, with every data marker (with its radius),
    error bar, curve, filled region, histogram outline and reference line
    in that axes (a reference line, the PDG mass or an acceptance edge, may
    pass behind a box only if the box has an opaque background). A box reaching outside its axes, and any text (titles,
    labels, tick labels) reaching outside the figure, also count. An empty list
    means the figure is clean. This is how the plotting functions place
    their boxes, and how the demos check the final figures.
    """
    with _measuring_dpi(fig, dpi):
        fig.draw_without_rendering()
        renderer = fig.canvas.get_renderer()
        problems = [f"axes {i}: {p}" for i, ax in enumerate(fig.axes) for p in _axes_overlaps(ax, renderer)]
        return problems + _clipped_text(fig, renderer)


def _clipped_text(fig: Figure, renderer: Any) -> list[str]:
    """Every visible piece of text (labels, tick labels, titles, legend) that reaches outside the figure."""
    from matplotlib.text import Text

    page = fig.bbox
    hidden = set()  # labels of ticks outside the view interval: generated but never drawn
    for ax in fig.axes:
        for axis in (ax.xaxis, ax.yaxis):
            lo, hi = sorted(axis.get_view_interval())
            tol = 1e-9 * max(1.0, abs(lo), abs(hi))
            for tick in (*axis.get_major_ticks(), *axis.get_minor_ticks()):
                if not lo - tol <= tick.get_loc() <= hi + tol:
                    hidden.update((id(tick.label1), id(tick.label2)))
    out = []
    for text in fig.findobj(Text):
        if not text.get_visible() or not text.get_text().strip() or id(text) in hidden:
            continue
        bb = text.get_window_extent(renderer)
        if bb.x0 < page.x0 - 0.5 or bb.x1 > page.x1 + 0.5 or bb.y0 < page.y0 - 0.5 or bb.y1 > page.y1 + 0.5:
            out.append(f"text {text.get_text()[:40]!r} is clipped by the figure edge ({bb} vs {page})")
    return out


def _corner(loc: str) -> tuple[float, float, str, str]:
    pad = 0.035
    vert, horiz = loc.split(" ")
    x, ha = (pad, "left") if horiz == "left" else (1 - pad, "right")
    y, va = {"upper": (1 - pad, "top"), "center": (0.5, "center"), "lower": (pad, "bottom")}[vert]
    return x, y, ha, va


_BOX_FONT_SIZES = (8.5, 8.0, 7.5)


def _candidate_box(loc: str, axbb: Any, width: float, height: float, pad: float) -> Any:
    """Where a box of the given size lands for a location string (as Legend and _corner place it)."""
    from matplotlib.transforms import Bbox

    vert, horiz = loc.split(" ")
    x0 = axbb.x0 + pad if horiz == "left" else axbb.x1 - pad - width
    y0 = {"upper": axbb.y1 - pad - height, "center": axbb.y0 + 0.5 * (axbb.height - height), "lower": axbb.y0 + pad}[vert]
    return Bbox.from_bounds(x0, y0, width, height)


def _annotation_box(loc: str, axbb: Any, width: float, height: float) -> Any:
    """Where the annotation text lands: its anchor is set by :func:`_corner` in axes fractions."""
    from matplotlib.transforms import Bbox

    x, y, ha, va = _corner(loc)
    ax_x, ax_y = axbb.x0 + x * axbb.width, axbb.y0 + y * axbb.height
    x0 = ax_x if ha == "left" else ax_x - width
    y0 = {"top": ax_y - height, "center": ax_y - height / 2, "bottom": ax_y}[va]
    return Bbox.from_bounds(x0, y0, width, height)


def _apply(legend: Any, annotation: Any, legend_loc: str, annot_loc: str | None) -> None:
    legend.set_loc(legend_loc)
    if annotation is not None:
        x, y, ha, va = _corner(annot_loc)
        annotation.set_position((x, y))
        annotation.set_ha(ha)
        annotation.set_va(va)


def _place_boxes(ax: Axes, annotation: Any, logy: bool, legend_kwargs: dict[str, Any]) -> None:
    """Put the legend and annotation where they cover nothing; if no corner is free, make room.

    The boxes are measured once; every pair of distinct locations is then
    checked arithmetically against the drawn data (points, error bars,
    curves, histograms, reference lines), in order of preference, and the
    first free pair is applied and confirmed with a real draw (see
    :func:`layout_overlaps`). If no pair is free:

    1. the top of the y-axis is raised (x 1.15 linear, x 3 log, up to about
       x 2 linear), which moves the data down and frees the upper corners;
    2. if a box is too wide to fit beside something that spans the full
       height (the peak, the PDG line), its text is made 0.5 pt smaller,
       down to 7.5 pt, and step 1 repeats;
    3. as a last resort, reference lines (not data) may pass behind the
       boxes, which then get an opaque white background so the line is
       hidden rather than drawn through the text, and the y-axis may grow
       further.

    Data points, error bars and fitted curves are never allowed under a box.
    If nothing works, a RuntimeError is raised rather than a cluttered
    figure returned.
    """
    fig = ax.figure
    pairs = [(a, b) for a in _LOCATIONS for b in _LOCATIONS if a != b]
    if annotation is None:
        pairs = [(a, None) for a in _LOCATIONS]
    ylim0 = ax.get_ylim()
    stages = [(size, 5, False) for size in _BOX_FONT_SIZES] + [(_BOX_FONT_SIZES[-1], 12, True)]
    with _measuring_dpi(fig):
        for size, max_grow, opaque in stages:
            ax.set_ylim(*ylim0)
            legend = ax.legend(loc="upper right", **{**legend_kwargs, "fontsize": size})
            if opaque:
                legend.set_frame_on(True)
                legend.get_frame().set(facecolor="white", edgecolor="none", alpha=0.9)
            if annotation is not None:
                annotation.set_fontsize(size)
                if opaque:
                    annotation.set_bbox({"facecolor": "white", "edgecolor": "none", "alpha": 0.9, "pad": 2.0})
            for _ in range(max_grow + 1):
                if _try_pairs(ax, legend, annotation, pairs, opaque):
                    return
                lo, hi = ax.get_ylim()
                ax.set_ylim(lo, hi * 3.0 if logy else lo + (hi - lo) * 1.15)
            if opaque:
                break
    raise RuntimeError("could not place the legend and annotation without overlapping the data")


def _try_pairs(ax: Axes, legend: Any, annotation: Any, pairs: list, opaque: bool) -> bool:
    fig = ax.figure
    _apply(legend, annotation, *pairs[0])
    fig.draw_without_rendering()
    renderer = fig.canvas.get_renderer()
    axbb = ax.get_window_extent(renderer)
    pad = 1.5 * fig.dpi / 72.0
    legend_bb = legend.get_window_extent(renderer)
    legend_pad = legend.borderaxespad * legend.prop.get_size_in_points() * fig.dpi / 72.0
    annot_size = None
    if annotation is not None:
        abb = annotation.get_window_extent(renderer)
        annot_size = (abb.width, abb.height)
    obstacles = _obstacles(ax)
    for legend_loc, annot_loc in pairs:
        boxes = [_candidate_box(legend_loc, axbb, legend_bb.width, legend_bb.height, legend_pad)]
        if annotation is not None:
            boxes.append(_annotation_box(annot_loc, axbb, *annot_size))
        if any(b.x0 < axbb.x0 or b.x1 > axbb.x1 or b.y0 < axbb.y0 or b.y1 > axbb.y1 for b in boxes):
            continue
        if len(boxes) == 2 and boxes[0].overlaps(boxes[1]):
            continue
        if any(_box_hits(b, obstacles, pad, opaque) for b in boxes):
            continue
        _apply(legend, annotation, legend_loc, annot_loc)
        fig.draw_without_rendering()
        if not _axes_overlaps(ax, fig.canvas.get_renderer()):
            return True
    return False


# -- helpers ----------------------------------------------------------------------------------


def _uniform_width(h: MassHistogram) -> float:
    widths = h.widths
    if not np.allclose(widths, widths[0], rtol=1e-9):
        raise ValueError("this plot needs equal-width bins (the y label states the bin width)")
    return float(widths[0])


def _width_label(width: float) -> str:
    return f"{width:g}"


def _fmt_pm(value: float, error: float) -> tuple[str, str]:
    """Value and error rounded to two significant digits of the error."""
    if not (math.isfinite(error) and error > 0):
        return f"{value:.4g}", f"{error:.2g}"
    digits = max(0, 1 - int(math.floor(math.log10(error))))
    return f"{value:.{digits}f}", f"{error:.{digits}f}"


_MODEL_LABELS = {"gauss_poly": "Gaussian", "voigt_poly": "Voigt"}


def _fit_annotation(fit: FitResult) -> str:
    lines = [f"{_MODEL_LABELS.get(fit.model_name, fit.model_name)} + pol{fit.poly_degree} fit, "
             f"{fit.fit_range[0]:g}$-${fit.fit_range[1]:g} GeV"]
    m, me = _fmt_pm(*fit.peak_position)
    lines.append(rf"$m_{{\mathrm{{peak}}}}$ = {m} $\pm$ {me} GeV (stat.)")
    s, se = _fmt_pm(*fit.resolution)
    if fit.gamma is None:
        lines.append(rf"$\sigma$ = {s} $\pm$ {se} GeV (effective)")
    else:
        lines.append(rf"$\sigma_{{\mathrm{{res}}}}$ = {s} $\pm$ {se} GeV")
        lines.append(rf"$\Gamma_Z$ = {2 * fit.gamma:.3f} GeV (fixed)")
    lines.append(rf"$\chi^2$/ndf = {fit.chi2:.1f}/{fit.ndf}")
    if fit.yields_reliable:
        sy, sye = fit.signal_yield
        by, bye = fit.background_yield
        lines.append(rf"$N_{{\mathrm{{sig}}}}$ = {sy:,.0f} $\pm$ {sye:,.0f},  $N_{{\mathrm{{bkg}}}}$ = {by:,.0f} $\pm$ {bye:,.0f}")
    else:
        lines.append("yields not shown: background not positive")
    lines.append(DATA_SOURCE)
    return "\n".join(lines)


def _flat(values: Any, attr: str) -> np.ndarray:
    if isinstance(values, Selection):
        values = values.particles
    if isinstance(values, Muon):
        values = getattr(values.p4, attr)
    if isinstance(values, ak.Array):
        values = ak.to_numpy(ak.flatten(values, axis=None))
    return np.asarray(values, dtype=np.float64).ravel()


# -- the mass spectrum ---------------------------------------------------------------------------


def plot_mass_spectrum(
    masshist: MassHistogram,
    fit: FitResult | None = None,
    same_sign: MassHistogram | None = None,
    pdg: bool = True,
    residuals: str | None = "pull",
    annotate: bool = True,
    logy: bool = False,
    label: str = "CMS Open Data",
    fig: Figure | None = None,
) -> tuple[Figure, list[Axes]]:
    """Draw the dimuon mass spectrum with its fit, the PDG mass and a pull panel.

    Elements (see the module docstring for why each is drawn this way):

    * data: black points at the bin centres with Poisson error bars sqrt(N)
      (no horizontal bars: the bin width is in the y label);
    * the fitted total (solid line), the fitted background (dashed line) and
      the signal as the shaded band between them, all scaled from densities
      to counts per bin, inside the fit range only;
    * optionally the same-sign spectrum as a step histogram: pairs that
      cannot come from a Z, a direct look at the combinatorial background;
    * the PDG Z mass from the ``particle`` package as a dotted reference line
      (the fit never uses it);
    * a lower panel of pulls (data - fit) / sigma per fitted bin, with
      sigma = sqrt(max(N, 1)) as in the fit, and lines at 0 and +-2;
    * an annotation with the fitted peak position and its statistical error,
      the resolution, chi2/ndf and the data source. Yields are shown only if
      :attr:`FitResult.yields_reliable`; otherwise the block says
      "yields not shown: background not positive".

    The legend and annotation are placed by measuring them and the data with
    the renderer (see :func:`layout_overlaps`); the y-axis starts at 0 on a
    linear scale and is raised if needed to make room.

    Parameters
    ----------
    masshist : MassHistogram
        Opposite-sign pair masses, equal-width bins.
    fit : FitResult, optional
        A fit of ``masshist`` (curves, pulls and annotation need it).
    same_sign : MassHistogram, optional
        Same-sign pair masses with the same bin edges.
    pdg : bool
        Draw the PDG Z mass line.
    residuals : {"pull", None}
        Draw the pull panel (needs ``fit``).
    annotate : bool
        Draw the fit annotation block (needs ``fit``).
    logy : bool
        Logarithmic y-axis.
    label : str
        Text above the plot on the left.
    fig : Figure, optional
        An empty figure to draw into.

    Returns
    -------
    (Figure, list of Axes)
        The main axes first, then the pull panel if drawn.
    """
    if residuals not in ("pull", None):
        raise ValueError(f'residuals must be "pull" or None, got {residuals!r}')
    width = _uniform_width(masshist)
    if same_sign is not None and not np.array_equal(same_sign.edges, masshist.edges):
        raise ValueError("same_sign must have the same bin edges as masshist")
    with_pulls = residuals == "pull" and fit is not None
    with paper_style():
        fig = _prepare_figure(fig, (WIDTH, 4.8 if with_pulls else 3.8))
        if with_pulls:
            ax, rax = fig.subplots(2, 1, sharex=True, gridspec_kw={"height_ratios": [3.2, 1.0]})
            fig.get_layout_engine().set(h_pad=0.0, hspace=0.0)
            axes = [ax, rax]
        else:
            ax = fig.subplots()
            axes = [ax]

        centers, counts = masshist.centers, masshist.counts
        ymax = float(np.max(counts + masshist.errors)) if counts.size else 1.0
        if same_sign is not None:
            ax.stairs(same_sign.counts, same_sign.edges, color=OKABE_ITO["orange"], linestyle="-.", linewidth=1.2,
                      baseline=None if logy else 0.0, label="Same-sign pairs", gid="same-sign")
        if fit is not None:
            lo, hi = fit.fit_range
            x = np.linspace(lo, hi, 1000)
            total, bkg = fit.model(x) * width, fit.background(x) * width
            ax.fill_between(x, bkg, total, color=OKABE_ITO["sky_blue"], alpha=0.35, linewidth=0,
                            label=f"Signal ({_MODEL_LABELS.get(fit.model_name, fit.model_name)})", gid="fit-signal")
            ax.plot(x, bkg, color=OKABE_ITO["vermillion"], linestyle="--", linewidth=1.2,
                    label=f"Background (pol{fit.poly_degree})", gid="fit-background")
            ax.plot(x, total, color=OKABE_ITO["blue"], linestyle="-", linewidth=1.4, label="Fit: signal + background",
                    gid="fit-total")
            ymax = max(ymax, float(np.max(total)))
        data = ax.errorbar(centers, counts, yerr=masshist.errors, fmt="o", color="black", markersize=3.2,
                           elinewidth=0.8, label="Data", zorder=5)
        data.lines[0].set_gid("data")
        for coll in data.lines[2]:
            coll.set_gid("data-errors")
        if pdg:
            mass = pdg_mass_width("Z")[0]
            ax.axvline(mass, color=OKABE_ITO["green"], linestyle=":", linewidth=1.3,
                       label=rf"PDG $m_Z$ = {mass:.4f} GeV", gid="pdg")

        ax.set_xlim(masshist.edges[0], masshist.edges[-1])
        if logy:
            ax.set_yscale("log", nonpositive="mask")
            positive = counts[counts > 0]
            ax.set_ylim(0.5 if positive.size == 0 else max(0.5, 0.5 * positive.min()), ymax * 3)
        else:
            ax.set_ylim(0.0, ymax * 1.08)
        ax.set_ylabel(f"Events / {_width_label(width)} GeV")
        _titles(ax, label)

        if with_pulls:
            inside = fit.fit_mask
            pull = (counts[inside] - fit.expected_counts()) / masshist.fit_errors[inside]
            rax.axhline(0.0, color="black", linewidth=0.6, gid="pull-zero")
            for level in (-2.0, 2.0):
                rax.axhline(level, color="0.45", linestyle=":", linewidth=0.8, gid="pull-2sigma")
            rax.plot(centers[inside], pull, "o", color="black", markersize=2.8, gid="pulls")
            limit = max(3.5, 1.15 * float(np.max(np.abs(pull)))) if pull.size else 3.5
            rax.set_ylim(-limit, limit)
            from matplotlib.ticker import MaxNLocator

            rax.yaxis.set_major_locator(MaxNLocator(nbins=4, symmetric=True, prune="both", integer=True))
            rax.set_ylabel("Pull")  # (data - fit) / sigma; a stacked fraction would be unreadably small
            rax.set_xlabel(r"$m_{\mu\mu}$ [GeV]")
            ax.tick_params(labelbottom=False)
        else:
            ax.set_xlabel(r"$m_{\mu\mu}$ [GeV]")
        fig.align_ylabels(axes)

        annotation = None
        if annotate and fit is not None:
            annotation = ax.text(0.03, 0.97, _fit_annotation(fit), transform=ax.transAxes, fontsize=8.5,
                                 linespacing=1.45, ha="left", va="top", gid=_ANNOTATION_GID)
        _place_boxes(ax, annotation, logy, {})
        _separate_titles(ax)
    return fig, axes


# -- other figures -------------------------------------------------------------------------------------


def _distribution(values: Any, before: Any, bins: np.ndarray, attr: str, xlabel: str, ylabel: str,
                  logy: bool, label: str, fig: Figure | None, acceptance: float | None,
                  outside_text: Any) -> tuple[Figure, Axes]:
    after = _flat(values, attr)
    with paper_style():
        fig = _prepare_figure(fig, (WIDTH, 3.8))
        ax = fig.subplots()
        lo, hi = bins[0], bins[-1]
        peak = 0.0
        if before is not None:
            raw = _flat(before, attr)
            counts, _ = np.histogram(raw, bins=bins)
            outside = int(np.sum((raw < lo) | (raw >= hi)))
            ax.stairs(counts, bins, color=OKABE_ITO["vermillion"], linestyle="--", linewidth=1.2,
                      baseline=None if logy else 0.0, gid="before",
                      label=f"All muons ({raw.size:,}" + (f"; {outside:,} {outside_text})" if outside else ")"))
            peak = max(peak, float(counts.max(initial=0)))
        counts, _ = np.histogram(after, bins=bins)
        outside = int(np.sum((after < lo) | (after >= hi)))
        ax.stairs(counts, bins, color=OKABE_ITO["blue"], linestyle="-", linewidth=1.4,
                  baseline=None if logy else 0.0, gid="after",
                  label=f"Selected muons ({after.size:,}" + (f"; {outside:,} {outside_text})" if outside else ")"))
        peak = max(peak, float(counts.max(initial=0)), 1.0)
        if acceptance is not None:
            for edge in (-acceptance, acceptance):
                ax.axvline(edge, color="0.3", linestyle="-.", linewidth=0.9, gid="acceptance",
                           label=rf"$|\eta|$ = {acceptance:g} (acceptance)" if edge > 0 else "_nolegend_")
        ax.set_xlim(lo, hi)
        if logy:
            ax.set_yscale("log", nonpositive="mask")
            ax.set_ylim(0.5, peak * 5)
        else:
            ax.set_ylim(0.0, peak * 1.1)
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        _titles(ax, label)
        _place_boxes(ax, None, logy, {})
        _separate_titles(ax)
    return fig, ax


def plot_pt_distribution(
    muons_or_selection: Any,
    before: Any = None,
    bins: Sequence[float] | None = None,
    logy: bool = True,
    label: str = "CMS Open Data",
    fig: Figure | None = None,
) -> tuple[Figure, Axes]:
    """Muon transverse momentum, selected muons and optionally all muons before the cuts.

    Transverse momentum is the momentum perpendicular to the beam. Z muons
    carry about half the Z mass each, so selected muons cluster around
    35-50 GeV (the Jacobian peak near m_Z / 2), while the raw collection is
    dominated by soft muons from hadron decays. A log scale shows both the
    falling spectrum and the sharp cut at 20 GeV. Values beyond the axis
    (the raw collection reaches ~100 TeV, unphysical reconstruction
    failures) are counted in the legend.

    Parameters
    ----------
    muons_or_selection : Selection, Muon or array-like
        The selected muons (or their pT values in GeV).
    before : Selection, Muon or array-like, optional
        The muons before the cuts, drawn as a dashed overlay.
    bins : sequence of float, optional
        Bin edges in GeV; default 0-200 GeV in 2 GeV bins.
    """
    edges = np.asarray(bins if bins is not None else np.arange(0.0, 202.0, 2.0), dtype=float)
    width = np.diff(edges)
    ylabel = f"Muons / {width[0]:g} GeV" if np.allclose(width, width[0]) else "Muons / bin"
    return _distribution(muons_or_selection, before, edges, "pt", r"Muon $p_{\mathrm{T}}$ [GeV]", ylabel,
                         logy, label, fig, None, f"outside {edges[0]:g}-{edges[-1]:g} GeV")


def plot_eta_distribution(
    muons_or_selection: Any,
    before: Any = None,
    bins: Sequence[float] | None = None,
    logy: bool = True,
    acceptance: float = 2.4,
    label: str = "CMS Open Data",
    fig: Figure | None = None,
) -> tuple[Figure, Axes]:
    """Muon pseudorapidity, with the |eta| = 2.4 acceptance edges as dashed lines.

    The muon chambers and tracker cover |eta| < 2.4. Before the cuts the
    raw collection extends to |eta| ~ 12, far beyond any detector: these are
    reconstruction artefacts. After the selection every muon is inside the
    dashed lines. The default axis, -12 to 12 in bins of 0.25, makes that
    junk visible.
    """
    edges = np.asarray(bins if bins is not None else np.linspace(-12.0, 12.0, 97), dtype=float)
    width = np.diff(edges)
    ylabel = f"Muons / {width[0]:g}" if np.allclose(width, width[0]) else "Muons / bin"
    return _distribution(muons_or_selection, before, edges, "eta", r"Muon $\eta$", ylabel, logy, label, fig,
                         acceptance, f"outside {edges[0]:g} to {edges[-1]:g}")


def plot_cutflow(cutflow: CutFlow | Selection, label: str = "CMS Open Data", fig: Figure | None = None) -> tuple[Figure, Axes]:
    """Horizontal bars: events left after each selection step, with counts and percent of all events.

    The first bar is every event in the file. Each later bar is the number of
    events that still have at least one selected muon after that step, or,
    for an event-level step (the trigger, ``require(>= 2)``), the events
    kept. The text gives the count and the percentage of all events. The
    cutflow is the audit trail of a selection: it shows which cut does the
    work. Counts are in thousands so the axis needs no offset multiplier;
    the axis is widened until every bar label fits inside it.
    """
    from matplotlib.ticker import AutoMinorLocator

    if isinstance(cutflow, Selection):
        cutflow = cutflow.cutflow()
    rows = cutflow.to_records()
    names = [textwrap.fill(r["cut"], width=26, break_long_words=False) for r in rows]
    values = np.array([r["n_events"] if r["level"] in ("start", "event") else r["n_events_with_particles"]
                       for r in rows], dtype=float)
    start = rows[0]["n_events"]
    with paper_style():
        fig = _prepare_figure(fig, (WIDTH, 0.38 * len(rows) + 1.3))
        ax = fig.subplots()
        y = np.arange(len(rows))[::-1]
        thousands = values / 1000.0
        ax.barh(y, thousands, height=0.62, color=OKABE_ITO["blue"], alpha=0.85, gid="bars")
        texts = [ax.text(v + 0.012 * thousands.max(), yi, f"{n:,.0f} ({100 * n / start:.1f} %)", va="center",
                         ha="left", fontsize=8.5, gid="bar-label") for yi, v, n in zip(y, thousands, values)]
        ax.set_yticks(y, names, fontsize=8.5)
        ax.tick_params(axis="y", which="both", left=False, right=False)
        ax.minorticks_off()
        ax.xaxis.set_minor_locator(AutoMinorLocator())
        ax.set_ylim(-0.6, len(rows) - 0.4)
        ax.set_xlabel("Events (thousands)")
        _titles(ax, label)
        xmax = thousands.max() * 1.15
        with _measuring_dpi(fig):
            for _ in range(20):
                ax.set_xlim(0, xmax)
                fig.draw_without_rendering()
                renderer = fig.canvas.get_renderer()
                right = ax.get_window_extent(renderer).x1
                if max(t.get_window_extent(renderer).x1 for t in texts) < right - 3:
                    break
                xmax *= 1.08
        _separate_titles(ax)
    return fig, ax


def plot_os_vs_ss(masshist_os: MassHistogram, masshist_ss: MassHistogram, logy: bool = True, pdg: bool = True,
                  label: str = "CMS Open Data", selection: str | None = None,
                  fig: Figure | None = None) -> tuple[Figure, Axes]:
    """Opposite-sign and same-sign dimuon mass spectra on one log-scale axis.

    The Z is neutral, so it decays only to opposite-sign pairs; same-sign
    pairs come only from background (unrelated or misidentified muons). A
    peak in the opposite-sign spectrum with none in the same-sign spectrum
    shows the peak is a neutral particle. The log scale is needed because,
    after a tight selection, the same-sign spectrum is orders of magnitude
    smaller. ``selection``, if given, describes the selection as the
    legend title.
    """
    width = _uniform_width(masshist_os)
    if not np.array_equal(masshist_os.edges, masshist_ss.edges):
        raise ValueError("the two histograms must have the same bin edges")
    with paper_style():
        fig = _prepare_figure(fig, (WIDTH, 3.8))
        ax = fig.subplots()
        base = None if logy else 0.0
        ax.stairs(masshist_os.counts, masshist_os.edges, color=OKABE_ITO["blue"], linestyle="-", linewidth=1.4,
                  baseline=base, label=f"Opposite-sign pairs ({masshist_os.n_entries:,})", gid="os")
        ax.stairs(masshist_ss.counts, masshist_ss.edges, color=OKABE_ITO["orange"], linestyle="--", linewidth=1.4,
                  baseline=base, label=f"Same-sign pairs ({masshist_ss.n_entries:,})", gid="ss")
        if pdg:
            mass = pdg_mass_width("Z")[0]
            ax.axvline(mass, color=OKABE_ITO["green"], linestyle=":", linewidth=1.3,
                       label=rf"PDG $m_Z$ = {mass:.4f} GeV", gid="pdg")
        top = max(float(masshist_os.counts.max(initial=0)), float(masshist_ss.counts.max(initial=0)), 1.0)
        ax.set_xlim(masshist_os.edges[0], masshist_os.edges[-1])
        if logy:
            ax.set_yscale("log", nonpositive="mask")
            ax.set_ylim(0.5, top * 5)
        else:
            ax.set_ylim(0.0, top * 1.1)
        ax.set_xlabel(r"$m_{\mu\mu}$ [GeV]")
        ax.set_ylabel(f"Pairs / {_width_label(width)} GeV")
        _titles(ax, label)
        _place_boxes(ax, None, logy, {"title": selection, "title_fontsize": 8.5} if selection else {})
        _separate_titles(ax)
    return fig, ax


# -- saving ------------------------------------------------------------------------------------------------


def save_figure(fig: Figure, path: str | Path, formats: Sequence[str] = ("png", "pdf"), dpi: int = 300) -> list[Path]:
    """Write ``fig`` in each format and return the written paths.

    ``path`` is the file name without (or with, which is replaced) a
    suffix; parent directories are created. The output is deterministic:
    no creation date, user name or software-version timestamps are
    embedded, so regenerating an unchanged figure gives byte-identical files
    and a version-controlled figure only changes when its content does.
    PDF text is embedded as editable TrueType (fonttype 42). The figure is
    saved at its own size (no tight-bbox cropping), so a PNG is exactly
    figsize x dpi pixels.
    """
    import matplotlib

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    metadata = {
        "png": {"Software": "cmsopen"},
        "pdf": {"Creator": "cmsopen", "Producer": "cmsopen", "CreationDate": None, "ModDate": None},
        "svg": {"Creator": "cmsopen", "Date": None},
    }
    written = []
    with matplotlib.rc_context({"pdf.fonttype": 42, "ps.fonttype": 42, "svg.hashsalt": "cmsopen"}):
        for fmt in formats:
            fmt = fmt.lower().lstrip(".")
            out = path.with_suffix(f".{fmt}")
            fig.savefig(out, format=fmt, dpi=dpi, metadata=metadata.get(fmt))
            written.append(out)
    return written
