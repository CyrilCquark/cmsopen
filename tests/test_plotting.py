"""Tests for cmsopen.plotting. Figures use the Agg canvas directly; no display is needed."""

import getpass
import math
import os
import re
import struct
import subprocess
import sys
from pathlib import Path

import matplotlib
import numpy as np
import pytest
from scipy import integrate

from cmsopen import FourMomentum, Muon
from cmsopen.fitting import MassHistogram, fit_mass_peak, toy_histogram, voigt_plus_polynomial
from cmsopen.plotting import (
    FOOTNOTE,
    layout_overlaps,
    paper_rc,
    paper_style,
    plot_cutflow,
    plot_eta_distribution,
    plot_mass_spectrum,
    plot_os_vs_ss,
    plot_pt_distribution,
    save_figure,
)
from cmsopen.selection import Selection

EDGES = np.linspace(60.0, 120.0, 61)


def toy_fit(seed=1, model="voigt_poly", **toy):
    h = toy_histogram(np.random.default_rng(seed), **toy)
    return h, fit_mass_peak(h, model=model)


def by_gid(ax, gid):
    return [a for a in (*ax.lines, *ax.collections, *ax.patches, *ax.texts) if a.get_gid() == gid]


def annotation_text(ax):
    (text,) = by_gid(ax, "annotation")
    return text


# -- an independent overlap check, written separately from cmsopen.plotting ------------------------------


def independent_overlaps(fig, ax, dpi=300, pad=1.0):
    """Measure the legend and annotation and check them against data points, error bars and the fit curve.

    Written independently of cmsopen.plotting: every element is taken from its data arrays and mapped
    with ax.transData, then compared with the boxes measured by the renderer at the output resolution.
    """
    old = fig.dpi
    fig.set_dpi(dpi)
    try:
        fig.draw_without_rendering()
        renderer = fig.canvas.get_renderer()
        boxes = {"legend": ax.get_legend().get_window_extent(renderer)}
        texts = by_gid(ax, "annotation")
        if texts:
            boxes["annotation"] = texts[0].get_window_extent(renderer)
        to_px = ax.transData.transform
        elements = {}
        (data,) = by_gid(ax, "data")
        r = data.get_markersize() * dpi / 72.0
        elements["data points"] = (to_px(np.column_stack([data.get_xdata(), data.get_ydata()])), r)
        for coll in by_gid(ax, "data-errors"):
            segs = coll.get_segments()
            pts = []
            for (x, y0), (_, y1) in segs:  # vertical error bars: sample them finely
                ys = np.linspace(y0, y1, 50)
                pts.append(np.column_stack([np.full(50, x), ys]))
            elements["error bars"] = (to_px(np.vstack(pts)), 1.0)
        for line in by_gid(ax, "fit-total"):
            elements["fit curve"] = (to_px(np.column_stack([line.get_xdata(), line.get_ydata()])), 1.0)
        problems = []
        for bname, bb in boxes.items():
            for ename, (px, radius) in elements.items():
                hit = ((px[:, 0] > bb.x0 - radius - pad) & (px[:, 0] < bb.x1 + radius + pad)
                       & (px[:, 1] > bb.y0 - radius - pad) & (px[:, 1] < bb.y1 + radius + pad))
                if hit.any():
                    x, y = ax.transData.inverted().transform(px[np.argmax(hit)])
                    problems.append(
                        f"{bname} {bb.bounds} overlaps {ename}: {hit.sum()} points, e.g. ({x:.2f}, {y:.1f})"
                    )
        if "annotation" in boxes and boxes["legend"].overlaps(boxes["annotation"]):
            problems.append(f"legend {boxes['legend'].bounds} overlaps annotation {boxes['annotation'].bounds}")
        return problems
    finally:
        fig.set_dpi(old)


# -- 1. structure ---------------------------------------------------------------------------------------


def test_mass_spectrum_structure():
    h, fit = toy_fit()
    fig, axes = plot_mass_spectrum(h, fit)
    assert len(fig.axes) == 2 and len(axes) == 2
    ax, rax = axes
    (data,) = by_gid(ax, "data")
    assert len(data.get_xdata()) == len(h.counts) == 60
    np.testing.assert_array_equal(data.get_xdata(), h.centers)
    np.testing.assert_array_equal(data.get_ydata(), h.counts)
    assert "m_{" in rax.get_xlabel() and "GeV" in rax.get_xlabel()
    assert ax.get_ylabel() == "Events / 1 GeV"
    assert by_gid(ax, "fit-total") and by_gid(ax, "fit-background") and by_gid(ax, "fit-signal") and by_gid(ax, "pdg")
    assert rax.get_shared_x_axes().joined(ax, rax)
    assert not any(t.get_visible() and t.get_text() for t in ax.get_xticklabels())  # no duplicate tick labels
    labels = ax.get_legend_handles_labels()[1]
    assert "Data" in labels and any("PDG" in s for s in labels)

    fig1, axes1 = plot_mass_spectrum(h, fit, residuals=None)
    assert len(fig1.axes) == 1 and len(axes1) == 1
    assert "m_{" in axes1[0].get_xlabel()
    fig2, axes2 = plot_mass_spectrum(h)  # no fit: no pulls, no curves, no annotation
    assert len(fig2.axes) == 1 and not by_gid(axes2[0], "fit-total") and not by_gid(axes2[0], "annotation")


def test_y_label_states_the_bin_width():
    rng = np.random.default_rng(3)
    masses = np.concatenate([rng.normal(91, 2.5, 20000), rng.uniform(60, 120, 6000)])
    from cmsopen.fitting import make_histogram

    h2 = make_histogram(masses, bins=30, range=(60, 120))
    fig, axes = plot_mass_spectrum(h2, fit_mass_peak(h2))
    assert axes[0].get_ylabel() == "Events / 2 GeV"
    h05 = make_histogram(masses, bins=120, range=(60, 120))
    assert plot_mass_spectrum(h05)[1][0].get_ylabel() == "Events / 0.5 GeV"
    with pytest.raises(ValueError, match="equal-width"):
        plot_mass_spectrum(make_histogram(masses, bins=[60, 80, 90, 120]))


# -- 2. layout: the legend and annotation never cover the data ------------------------------------------------


LAYOUT_CASES = {
    "voigt": dict(seed=1, model="voigt_poly"),
    "gauss": dict(seed=1, model="gauss_poly"),
    "wide peak": dict(seed=2, model="gauss_poly", sigma=5.0),
    "high background": dict(seed=3, model="voigt_poly", n_background=20000.0),
    "small sample": dict(seed=4, model="gauss_poly", n_signal=600.0, n_background=300.0),
    "peak off centre": dict(seed=5, model="gauss_poly", mean=80.0),
}


@pytest.mark.parametrize("case", LAYOUT_CASES)
@pytest.mark.parametrize("logy", [False, True])
def test_legend_and_annotation_do_not_cover_data(case, logy):
    """Regression test for the legend that covered the peak in the layer 5 draft."""
    h, fit = toy_fit(**LAYOUT_CASES[case])
    fig, axes = plot_mass_spectrum(h, fit, logy=logy)
    problems = independent_overlaps(fig, axes[0])
    assert not problems, "\n".join(problems)
    assert layout_overlaps(fig) == []


def test_layout_with_same_sign_overlay():
    h, fit = toy_fit()
    ss = MassHistogram(np.random.default_rng(0).poisson(5.0, 60).astype(float), h.edges)
    fig, axes = plot_mass_spectrum(h, fit, same_sign=ss)
    assert by_gid(axes[0], "same-sign")
    assert not independent_overlaps(fig, axes[0])
    assert layout_overlaps(fig) == []


def test_layout_check_detects_an_overlap():
    h, fit = toy_fit()
    fig, axes = plot_mass_spectrum(h, fit)
    axes[0].get_legend().set_loc("center")  # on top of the peak
    assert independent_overlaps(fig, axes[0])
    assert any("legend overlaps" in p for p in layout_overlaps(fig))


# -- 3. y range and pulls ---------------------------------------------------------------------------------------------


def test_linear_y_starts_at_zero_and_pulls_are_right():
    h, fit = toy_fit(model="gauss_poly")
    fig, (ax, rax) = plot_mass_spectrum(h, fit)
    assert ax.get_ylim()[0] == 0.0
    (pulls,) = by_gid(rax, "pulls")
    inside = (h.edges[:-1] >= 70) & (h.edges[1:] <= 110)
    expected = np.array(
        [integrate.quad(fit.model, a, b)[0] for a, b in zip(h.edges[:-1][inside], h.edges[1:][inside], strict=False)]
    )
    independent = (h.counts[inside] - expected) / np.sqrt(np.maximum(h.counts[inside], 1.0))
    np.testing.assert_allclose(pulls.get_xdata(), h.centers[inside])
    np.testing.assert_allclose(pulls.get_ydata(), independent, rtol=1e-6, atol=1e-9)
    assert {round(line.get_ydata()[0], 9) for line in by_gid(rax, "pull-2sigma")} == {-2.0, 2.0}
    assert by_gid(rax, "pull-zero")[0].get_ydata()[0] == 0.0
    lo, hi = rax.get_ylim()
    assert lo == -hi and hi >= 3.5


def test_log_scale_lower_limit_is_positive():
    h, fit = toy_fit()
    fig, (ax, _) = plot_mass_spectrum(h, fit, logy=True)
    assert ax.get_yscale() == "log" and ax.get_ylim()[0] > 0


# -- 4. yields shown only when reliable --------------------------------------------------------------------------------


def test_annotation_hides_yields_when_background_negative():
    centers = 0.5 * (EDGES[:-1] + EDGES[1:])
    density = voigt_plus_polynomial(centers, 100000.0, 91.0, 1.4, 120.0, -7.2, gamma=1.25, x0=90.0)
    counts = np.where((centers > 70) & (centers < 110), density, 0.0)
    h = MassHistogram(counts, EDGES)
    fit = fit_mass_peak(h, model="voigt_poly", natural_width=2.5, poly_degree=1)
    assert fit.yields_reliable is False
    fig, (ax, _) = plot_mass_spectrum(h, fit)
    text = annotation_text(ax).get_text()
    assert "yields not shown: background not positive" in text
    assert "N_{" not in text and "mathrm{sig}" not in text and "mathrm{bkg}" not in text
    assert f"{fit.signal_yield[0]:,.0f}" not in text

    h2, good = toy_fit(model="gauss_poly")
    assert good.yields_reliable
    text2 = annotation_text(plot_mass_spectrum(h2, good)[1][0]).get_text()
    assert "N_{\\mathrm{sig}}" in text2 and f"{good.signal_yield[0]:,.0f}" in text2
    assert "yields not shown" not in text2


def test_annotation_contents_match_the_fit():
    h, fit = toy_fit()
    text = annotation_text(plot_mass_spectrum(h, fit)[1][0]).get_text()
    m = re.search(r"m_\{\\mathrm\{peak\}\}\$ = ([0-9.]+) \$\\pm\$ ([0-9.]+) GeV \(stat\.\)", text)
    assert m, text
    digits = len(m.group(1).split(".")[1])
    assert float(m.group(1)) == round(fit.peak_position[0], digits)
    assert float(m.group(2)) == round(fit.peak_position[1], digits)
    assert f"{fit.chi2:.1f}/{fit.ndf}" in text
    assert "2012C DoubleMuParked" in text and "sqrt{s}" in text and "8 TeV" in text
    assert "sigma_{\\mathrm{res}}" in text and "Gamma_Z" in text


# -- 5. style ----------------------------------------------------------------------------------------------------------


def test_paper_style_restores_rcparams():
    keys = list(paper_rc())
    before = {k: matplotlib.rcParams[k] for k in keys}
    with paper_style():
        assert matplotlib.rcParams["pdf.fonttype"] == 42
        assert matplotlib.rcParams["xtick.direction"] == "in" and matplotlib.rcParams["ytick.right"] is True
        assert matplotlib.rcParams["axes.grid"] is False and matplotlib.rcParams["legend.frameon"] is False
        assert matplotlib.rcParams["savefig.dpi"] == 300
        assert 10 <= matplotlib.rcParams["font.size"] <= 12
    after = {k: matplotlib.rcParams[k] for k in keys}
    assert after == before


def test_footnote_and_label_present_and_no_official_claim():
    h, fit = toy_fit()
    fig, (ax, _) = plot_mass_spectrum(h, fit)
    assert ax.get_title(loc="right") == FOOTNOTE == "Unofficial analysis of CMS Open Data"
    assert ax.get_title(loc="left").strip() == "CMS Open Data"
    all_text = " ".join(t.get_text() for t in fig.findobj(matplotlib.text.Text))
    assert "Preliminary" not in all_text and "CMS Collaboration" not in all_text


def test_fonts_are_concrete_and_measured_consistently():
    """Regression: text measured inside paper_style must be the text drawn outside it (no generic 'serif')."""
    h, fit = toy_fit()
    fig, (ax, _) = plot_mass_spectrum(h, fit)
    ann = annotation_text(ax)
    assert ann.get_fontname() == "STIX Two Text"
    assert ax.get_yticklabels()[1].get_fontname() == "STIX Two Text"
    widths = []
    for dpi in (100, 300):
        fig.set_dpi(dpi)
        fig.draw_without_rendering()
        widths.append(ann.get_window_extent(fig.canvas.get_renderer()).width * 72.0 / dpi)
    fig.set_dpi(100)
    assert widths[0] == pytest.approx(widths[1], abs=1.0)


def test_layout_on_log_axes_uses_the_log_transform():
    """Regression: Path.to_polygons(transform) ignores non-affine transforms; obstacles must not."""
    from cmsopen.plotting import _obstacles

    h_os = MassHistogram(np.full(60, 1000.0), EDGES)
    h_ss = MassHistogram(np.full(60, 10.0), EDGES)
    fig, ax = plot_os_vs_ss(h_os, h_ss)
    fig.draw_without_rendering()
    obstacles = {name: pts for name, pts, _ in _obstacles(ax)}
    expected_y = ax.transData.transform([[90.0, 10.0]])[0, 1]
    assert np.allclose(np.median(obstacles["ss"][:, 1]), expected_y, atol=1.0)


# -- 6. saving ---------------------------------------------------------------------------------------------------------


def _png_size(path):
    data = Path(path).read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">II", data[16:24])


def test_save_figure_files_size_and_determinism(tmp_path):
    h, fit = toy_fit()
    fig, _ = plot_mass_spectrum(h, fit)
    written = save_figure(fig, tmp_path / "sub" / "z_peak")
    assert [p.name for p in written] == ["z_peak.png", "z_peak.pdf"]
    assert all(p.exists() and p.stat().st_size > 10_000 for p in written)
    w, hgt = _png_size(written[0])
    fw, fh = fig.get_size_inches()
    assert (w, hgt) == (round(fw * 300), round(fh * 300))

    again = save_figure(fig, tmp_path / "again" / "z_peak")
    for a, b in zip(written, again, strict=False):
        assert a.read_bytes() == b.read_bytes(), f"{a.name} is not deterministic"

    pdf = written[1].read_bytes()
    assert b"/CreationDate" not in pdf and b"/ModDate" not in pdf
    user = getpass.getuser().encode()
    assert user not in pdf and user not in written[0].read_bytes()
    assert b"/Creator (cmsopen)" in pdf
    # fonttype 42: TrueType fonts embedded (editable text), not Type 3 outlines
    assert b"/FontFile2" in pdf and b"/Type3" not in pdf


def test_save_figure_replaces_suffix_and_custom_formats(tmp_path):
    fig, _ = plot_mass_spectrum(toy_histogram(np.random.default_rng(0)))
    written = save_figure(fig, tmp_path / "x.png", formats=("png",), dpi=100)
    assert written == [tmp_path / "x.png"]
    w, h = _png_size(written[0])
    assert (w, h) == tuple(round(v * 100) for v in fig.get_size_inches())


# -- 7. pT, eta, cutflow, OS vs SS -------------------------------------------------------------------------------------


def _muons(n_events=2000, seed=0, spread=1.0):
    rng = np.random.default_rng(seed)
    counts = rng.integers(0, 4, n_events)
    n = int(counts.sum())
    import awkward as ak

    jag = lambda x: ak.unflatten(x, counts)  # noqa: E731
    p4 = FourMomentum(
        jag(rng.exponential(25.0, n)),
        jag(rng.normal(0, 2.0 * spread, n)),
        jag(rng.uniform(-3, 3, n)),
        jag(np.full(n, 0.1057)),
    )
    return Muon(p4, jag(rng.choice([-1, 1], n)))


def test_eta_plot_acceptance_lines_and_overlay():
    raw = _muons(spread=2.5)
    sel = Selection(raw).max_eta(2.4)
    fig, ax = plot_eta_distribution(sel, before=raw)
    lines = by_gid(ax, "acceptance")
    assert sorted(line.get_xdata()[0] for line in lines) == [-2.4, 2.4]
    assert by_gid(ax, "before") and by_gid(ax, "after")
    assert ax.get_ylabel() == "Muons / 0.25"
    assert layout_overlaps(fig) == []
    fig2, ax2 = plot_eta_distribution(sel)
    assert not by_gid(ax2, "before") and by_gid(ax2, "after")


def test_pt_plot_overlay_and_label():
    raw = _muons()
    fig, ax = plot_pt_distribution(Selection(raw).min_pt(20.0), before=raw)
    assert by_gid(ax, "before") and by_gid(ax, "after")
    assert ax.get_ylabel() == "Muons / 2 GeV" and "GeV" in ax.get_xlabel()
    assert ax.get_yscale() == "log"
    assert layout_overlaps(fig) == []
    assert not by_gid(plot_pt_distribution(raw)[1], "before")


def test_cutflow_and_os_vs_ss():
    raw = _muons()
    sel = Selection(raw).min_pt(20.0).max_eta(2.4).require(2)
    fig, ax = plot_cutflow(sel)
    labels = [t.get_text() for t in by_gid(ax, "bar-label")]
    assert len(labels) == len(sel.cutflow()) and labels[0].endswith("(100.0 %)")
    assert layout_overlaps(fig) == []  # includes: no text clipped by the figure edge
    h_os = MassHistogram(np.random.default_rng(1).poisson(200.0, 60).astype(float), EDGES)
    h_ss = MassHistogram(np.random.default_rng(2).poisson(5.0, 60).astype(float), EDGES)
    fig2, ax2 = plot_os_vs_ss(h_os, h_ss, selection="Loose selection")
    assert ax2.get_yscale() == "log" and by_gid(ax2, "os") and by_gid(ax2, "ss")
    assert ax2.get_legend().get_title().get_text() == "Loose selection"
    assert layout_overlaps(fig2) == []


def test_long_label_does_not_collide_with_footnote():
    h_os = MassHistogram(np.full(60, 100.0), EDGES)
    fig, ax = plot_os_vs_ss(h_os, h_os, label="CMS Open Data, a very long description of the selection used here")
    fig.set_dpi(300)
    fig.draw_without_rendering()
    r = fig.canvas.get_renderer()
    left, right = ax._left_title, ax._right_title
    # the label was lifted onto its own row: its (first, only non-empty) line sits above the footnote
    assert left.get_text().endswith("\n")
    probe = ax.text(0.5, 0.5, left.get_text().strip(), fontproperties=left.get_fontproperties(), transform=ax.transAxes)
    line_height = probe.get_window_extent(r).height
    probe.remove()
    label_row_bottom = left.get_window_extent(r).y1 - line_height
    assert label_row_bottom >= right.get_window_extent(r).y1 - 1.0
    assert layout_overlaps(fig) == []


# -- 8. headless and lazy ----------------------------------------------------------------------------------------------


def test_import_is_lazy_and_plotting_is_headless(tmp_path):
    code = (
        "import sys\n"
        "import cmsopen\n"
        "assert 'matplotlib.pyplot' not in sys.modules, 'pyplot imported by import cmsopen'\n"
        "assert 'matplotlib' not in sys.modules, 'matplotlib imported by import cmsopen'\n"
        "import numpy as np\n"
        "from cmsopen.fitting import toy_histogram, fit_mass_peak\n"
        "h = toy_histogram(np.random.default_rng(0))\n"
        "fig, _ = cmsopen.plot_mass_spectrum(h, fit_mass_peak(h))\n"
        f"cmsopen.save_figure(fig, {str(tmp_path / 'headless')!r})\n"
        "assert 'matplotlib.pyplot' not in sys.modules, 'pyplot imported by plotting'\n"
        "print('ok')\n"
    )
    env = {k: v for k, v in os.environ.items() if k not in ("DISPLAY", "MPLBACKEND", "WAYLAND_DISPLAY")}
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, timeout=300)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "ok"
    assert (tmp_path / "headless.png").exists() and (tmp_path / "headless.pdf").exists()


def test_exports():
    import cmsopen

    for name in (
        "paper_style",
        "apply_paper_style",
        "plot_mass_spectrum",
        "plot_pt_distribution",
        "plot_eta_distribution",
        "plot_cutflow",
        "plot_os_vs_ss",
        "save_figure",
        "layout_overlaps",
    ):
        assert name in cmsopen.__all__ and callable(getattr(cmsopen, name))


def test_bad_arguments():
    h, fit = toy_fit()
    with pytest.raises(ValueError, match="residuals"):
        plot_mass_spectrum(h, fit, residuals="ratio")
    with pytest.raises(ValueError, match="same bin edges"):
        plot_mass_spectrum(h, fit, same_sign=MassHistogram(np.ones(30), np.linspace(60, 120, 31)))
    fig, _ = plot_mass_spectrum(h)
    with pytest.raises(ValueError, match="empty"):
        plot_mass_spectrum(h, fig=fig)
    assert math.isfinite(fit.chi2)
