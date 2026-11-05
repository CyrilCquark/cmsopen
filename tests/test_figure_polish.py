"""The final figures and captions: what they say follows the fit shown, and nothing covers anything else."""

import re
import sys
from pathlib import Path
from types import SimpleNamespace

import matplotlib.text
import numpy as np
import pytest
from test_plot_placement import jpsi_masses, z_masses

from cmsopen import plotting
from cmsopen.fitting import compare_to_pdg, fit_mass_peak, make_histogram, pdg_mass_width
from cmsopen.pipeline import CHANNELS, resonance_label
from cmsopen.plotting import BinnedValues, layout_overlaps
from cmsopen.selection import CutFlow, CutStep

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples"))
import make_figures  # noqa: E402

sys.path.pop(0)
RUN = r"2012B+2012C DoubleMuParked, $\sqrt{s}$ = 8 TeV"
CHANNEL_NAMES = ("Z_mumu", "Jpsi_mumu")


@pytest.fixture(scope="module", params=CHANNEL_NAMES)
def channel(request):
    """Each channel's default-model fit of a high-statistics synthetic sample, and its histogram."""
    cfg = CHANNELS[request.param]
    masses = (z_masses if request.param == "Z_mumu" else jpsi_masses)(np.random.default_rng(1))
    h = make_histogram(masses, bins=cfg.bins, range=cfg.mass_range)
    fit = fit_mass_peak(h, model=cfg.model, fit_range=cfg.fit_range, poly_degree=cfg.poly_degree,
                        natural_width=pdg_mass_width(cfg.resonance)[2], cb_n=cfg.cb_n)
    return cfg, h, fit


def spectrum(cfg, h, fit):
    pdg = pdg_mass_width(cfg.resonance)
    return plotting.plot_mass_spectrum(h, fit, resonance_label=resonance_label(cfg), pdg_mass=pdg[0],
                                       natural_width=pdg[2], data_label=RUN)


class Unreliable:
    """A fit with the same numbers whose yields are not reliable (its background goes negative)."""

    yields_reliable = False

    def __init__(self, fit):
        self._fit = fit

    def __getattr__(self, name):
        return getattr(self._fit, name)


# -- captions -----------------------------------------------------------------------------------------------------


def test_the_yields_sentence_follows_the_fit_shown(channel):
    _, _, fit = channel
    assert fit.yields_reliable
    alternate = Unreliable(SimpleNamespace(model_name="voigt_poly"))
    both_good = make_figures._yields_sentence(fit)
    assert "given in the figure annotation" in both_good and "not quoted" not in both_good
    good_bad = make_figures._yields_sentence(fit, alternate)
    assert good_bad.startswith("The signal and background yields of the fit shown are given in the figure annotation.")
    assert "Those of the `voigt_poly` fit are not quoted" in good_bad
    bad = make_figures._yields_sentence(Unreliable(fit), fit)
    assert bad.startswith(f"Signal and background yields are not quoted: in the `{fit.model_name}` fit shown")
    assert "given in the figure annotation" not in bad


def test_the_caption_with_an_unreliable_alternate_says_the_shown_yields_are_in_the_figure(channel, monkeypatch):
    cfg, _, fit = channel
    other = Unreliable(fit)
    real = make_figures.compare_to_pdg
    monkeypatch.setattr(make_figures, "compare_to_pdg", lambda f, r: real(getattr(f, "_fit", f), r))
    if cfg.name == "Z_mumu":
        text = make_figures.caption({cfg.model: fit, "alt": other}, cfg.model, "alt")
    else:
        text = make_figures.jpsi_caption(SimpleNamespace(fit=fit, alternate_fit=other, config=cfg, files=[]))
    assert "yields of the fit shown are given in the figure annotation" in text
    assert "Signal and background yields are not quoted" not in text
    assert not re.search(r"\+- 0\.0*(?![0-9])", text), text


@pytest.mark.parametrize("error", [10.0 ** k * m for k in range(-8, 4) for m in (1.0, 1.04, 4.9, 9.96)])
def test_an_uncertainty_never_rounds_to_zero_and_has_two_significant_digits(error):
    text = make_figures.pm_text(3.0969, error)
    shown = float(text.split(" +- ")[1])
    assert shown > 0
    assert abs(shown - error) / error <= 0.051  # two significant digits, at worst 5 %


@pytest.mark.parametrize("error", [0.0, float("nan"), -1.0])
def test_no_uncertainty_is_said_in_words(error):
    assert make_figures.pm_text(1.5, error) == "1.5 (no uncertainty)"


def test_every_number_with_an_error_in_a_fit_line_keeps_its_error(channel):
    cfg, _, fit = channel
    line = make_figures._fit_line(fit, "Z" if cfg.name == "Z_mumu" else "J/psi")
    pairs = re.findall(r"([0-9.]+) \+- ([0-9.]+)", line)
    assert len(pairs) >= 6 and all(float(e) > 0 for _, e in pairs), line
    digits = plotting.pm_digits(fit.peak_position[1])
    assert f"{compare_to_pdg(fit, 'Z' if cfg.name == 'Z_mumu' else 'J/psi').difference:+.{digits}f} GeV" in line


# -- the fit figures ----------------------------------------------------------------------------------------------


def test_fit_figure_layout_headroom_and_nothing_overlaps(channel):
    cfg, h, fit = channel
    fig, axes = spectrum(cfg, h, fit)
    assert layout_overlaps(fig) == []
    top = axes[0].get_ylim()[1] / float(np.max(h.counts + h.errors))
    assert 1.25 <= top <= 1.4 + 1e-9, top


def test_fit_figure_keeps_the_pdg_line_whole(channel):
    cfg, h, fit = channel
    _, axes = spectrum(cfg, h, fit)
    (line,) = [x for x in axes[0].lines if x.get_gid() == "pdg"]
    annotation = next(t for t in axes[0].texts if t.get_gid() == "annotation")
    assert line.get_visible() and annotation.get_bbox_patch() is None  # no box hides anything
    assert axes[0].get_legend().get_frame_on() is False


def test_the_layout_checker_sees_a_box_on_the_pdg_line(channel):
    cfg, h, fit = channel
    fig, axes = spectrum(cfg, h, fit)
    annotation = next(t for t in axes[0].texts if t.get_gid() == "annotation")
    pdg = pdg_mass_width(cfg.resonance)[0]
    annotation.set_transform(axes[0].get_xaxis_transform())
    annotation.set_position((pdg, 0.97))
    annotation.set_ha("center")
    assert any("annotation overlaps pdg" in p for p in layout_overlaps(fig))


def test_the_layout_checker_does_not_excuse_an_opaque_box(channel):
    cfg, h, fit = channel
    fig, axes = spectrum(cfg, h, fit)
    annotation = next(t for t in axes[0].texts if t.get_gid() == "annotation")
    annotation.set_transform(axes[0].get_xaxis_transform())
    annotation.set_position((pdg_mass_width(cfg.resonance)[0], 0.97))
    annotation.set_ha("center")
    annotation.set_bbox({"facecolor": "white", "edgecolor": "none", "alpha": 1.0})
    assert any("annotation overlaps pdg" in p for p in layout_overlaps(fig))


def test_the_annotation_is_shortened_rather_than_given_more_headroom(channel, monkeypatch):
    cfg, h, fit = channel
    place, tops = plotting._place_boxes, []

    def spy(ax, annotation, logy, kwargs, y_tops=None):
        tops.append(y_tops)
        place(ax, annotation, logy, kwargs, y_tops)

    monkeypatch.setattr(plotting, "_place_boxes", spy)
    spectrum(cfg, h, fit)
    assert tops and tops[0] is not None
    base = float(np.max(h.counts + h.errors))
    assert [round(t / base, 2) for t in tops[0]] == [1.25, 1.32, 1.4]


# -- every figure -------------------------------------------------------------------------------------------------


def small_text(fig):
    """Text set below 8 pt. Sub- and superscripts inside mathtext are the documented exception: not separate text."""
    return [t.get_text() for t in fig.findobj(matplotlib.text.Text)
            if t.get_text().strip() and t.get_fontsize() < plotting.MIN_FONT_SIZE]


def cutflow():
    steps = [
        CutStep("all events", {}, "start", 2_000_000, 400_000, 500_000),
        CutStep("require_trigger", {"paths": ("HLT_A", "HLT_B")}, "event", 1_000_000, 200_000, 250_000),
        CutStep("min_pt", {"value": 20.0}, "particle", 200_000, 120_000, 250_000),
        CutStep("max_eta", {"value": 2.4}, "particle", 190_000, 118_000, 250_000),
        CutStep("quality_id", {"name": "tight"}, "particle", 150_000, 100_000, 250_000),
        CutStep("max_rel_iso", {"value": 0.12, "cone": 0.4}, "particle", 90_000, 60_000, 250_000),
        CutStep("require", {"n": 2, "exactly": False}, "event", 60_000, 30_000, 30_000),
    ]
    return CutFlow(steps)


def all_figures():
    edges = np.linspace(60.0, 120.0, 61)
    rng = np.random.default_rng(3)
    from cmsopen.fitting import MassHistogram

    os_h = MassHistogram(rng.poisson(2000.0 * np.exp(-0.5 * ((edges[:-1] - 91) / 3) ** 2) + 50).astype(float), edges)
    ss_h = MassHistogram(rng.poisson(10.0, 60).astype(float), edges)
    pt = BinnedValues.from_values(rng.exponential(30.0, 20_000), plotting.PT_EDGES_DEFAULT)
    eta = BinnedValues.from_values(rng.normal(0.0, 1.4, 20_000), plotting.ETA_EDGES_DEFAULT)
    return {
        "os_vs_ss": plotting.plot_os_vs_ss(os_h, ss_h, data_label=RUN, pdg_mass=91.1879)[0],
        "pt": plotting.plot_pt_distribution(pt, before=pt, data_label=RUN)[0],
        "eta": plotting.plot_eta_distribution(eta, before=eta, data_label=RUN)[0],
        "cutflow": plotting.plot_cutflow(cutflow(), data_label=RUN)[0],
    }


@pytest.fixture(scope="module")
def figures():
    return all_figures()


@pytest.mark.parametrize("name", ["os_vs_ss", "pt", "eta", "cutflow"])
def test_every_figure_has_the_run_label_no_small_text_and_no_overlap(figures, name):
    fig = figures[name]
    assert fig.axes[0].get_title(loc="right").splitlines() == [RUN, plotting.FOOTNOTE]
    assert small_text(fig) == []
    assert layout_overlaps(fig) == []


def test_the_fit_figure_has_the_run_label_and_no_small_text(channel):
    fig, axes = spectrum(*channel)
    assert axes[0].get_title(loc="right").splitlines() == [RUN, plotting.FOOTNOTE]
    assert small_text(fig) == []


def test_the_mathtext_exception_is_documented():
    assert "sub- and superscripts" in (Path(plotting.__file__).read_text())


def test_the_eta_figure_marks_the_cut_and_says_before_selection(figures):
    ax = figures["eta"].axes[0]
    labels = [t.get_text() for t in ax.get_legend().get_texts()]
    assert any(t.startswith("All muons, before selection (") for t in labels)
    assert any("= 2.4 (selection cut)" in t for t in labels)
    cuts = [x for x in ax.lines if x.get_gid() == "acceptance"]
    assert sorted(x.get_xdata()[0] for x in cuts) == [-2.4, 2.4]


@pytest.mark.parametrize(("cut", "text"), [
    ("all events", "All events"),
    ("min_pt(20)", r"Muon $p_{\mathrm{T}}$ > 20 GeV"),
    ("max_eta(2.4)", r"Muon $|\eta|$ < 2.4"),
    ("quality_id(soft)", "Soft muon ID"),
    ("max_rel_iso(0.12, cone=0.4)", "Relative isolation < 0.12 (cone 0.4)"),
    ("require(>= 2)", "At least two muons"),
    ("require(>= 1)", "At least one muon"),
    ("trigger(HLT_A OR HLT_B)", "Trigger: HLT_A or HLT_B"),
    ("something_new(3)", "something_new(3)"),
])
def test_cutflow_steps_are_readable(cut, text):
    assert plotting.readable_cut(cut) == text


def test_the_cutflow_says_which_column_counts_what(figures):
    fig = figures["cutflow"]
    ax = fig.axes[0]

    def by(gid):
        return [t for t in ax.texts if t.get_gid() == gid]

    assert [t.get_text() for t in by("column-title")] == ["Events (% of all)", "Muons"]
    assert [t.get_text() for t in by("muon-count")][:3] == ["2,000,000", "1,000,000", "200,000"]
    assert [t.get_text() for t in by("bar-label")][:3] == ["500,000 (100.0 %)", "250,000 (50.0 %)", "120,000 (24.0 %)"]
    assert fig.get_supxlabel().replace("\n", " ") == plotting.CUTFLOW_NOTE
    assert "at a muon cut, events with at least one muon" in plotting.CUTFLOW_NOTE
    ticks = [t.get_text() for t in ax.get_yticklabels()]
    assert "At least two muons" in ticks and not any("require" in t or "min_pt" in t for t in ticks)
    fig.set_dpi(300)
    fig.draw_without_rendering()
    r = fig.canvas.get_renderer()
    bars = max(p.get_window_extent(r).x1 for p in ax.patches)
    for a, b in zip(by("bar-label"), by("muon-count"), strict=True):
        ea, eb = a.get_window_extent(r), b.get_window_extent(r)
        assert bars < ea.x0 and ea.x1 < eb.x0 and eb.x1 <= ax.get_window_extent(r).x1
