"""Channel-specific labels in the mass-fit figures: every label comes from the channel's resonance."""

import dataclasses

import numpy as np
import pytest

import cmsopen.pipeline as pipeline
from cmsopen.fitting import MassHistogram, fit_mass_peak, pdg_mass_width, toy_histogram
from cmsopen.pipeline import CHANNELS, resonance_label
from cmsopen.plotting import _width_text, layout_overlaps, plot_mass_spectrum, plot_os_vs_ss
from cmsopen.selection import CutFlow, CutStep

# Toy shapes that look like each channel's real spectrum (resolution, background slope), in GeV.
TOYS = {"Z_mumu": {"sigma": 2.0, "slope": 25.0}, "Jpsi_mumu": {"sigma": 0.03, "slope": 1.0}}
LABELS = {"Z_mumu": "Z", "Jpsi_mumu": r"J/\psi"}
CUTFLOW = CutFlow(
    [
        CutStep("all events", {}, "start", 100, 90, 100),
        CutStep("require", {"n": 2, "exactly": False}, "event", 40, 20, 20),
    ]
)


def channel_figures(name, seed=3):
    """The figures analyze() draws for this channel (pipeline._figures), on a toy spectrum shaped like the channel."""
    cfg = CHANNELS[name]
    mass, _, width, _ = pdg_mass_width(cfg.resonance)
    h = toy_histogram(np.random.default_rng(seed), mean=mass, bins=cfg.bins, range=cfg.mass_range, **TOYS[name])
    fit = fit_mass_peak(
        h, model="voigt_poly", fit_range=cfg.fit_range, poly_degree=cfg.poly_degree, natural_width=width
    )
    ss = MassHistogram(np.full(cfg.bins, 3.0), h.edges)
    return pipeline._figures(cfg, h, fit, ss, CUTFLOW), mass


def texts(fig):
    """Legend entries and annotation text of the first axes."""
    ax = fig.axes[0]
    legend = [t.get_text() for t in ax.get_legend().get_texts()]
    notes = [t.get_text() for t in ax.texts if t.get_gid() == "annotation"]
    return legend, "\n".join(notes)


def test_registered_channels_have_labels():
    assert set(TOYS) == set(CHANNELS), "add a toy shape for every registered channel"
    for name, cfg in CHANNELS.items():
        assert resonance_label(cfg) == LABELS[name]


@pytest.mark.parametrize("name", sorted(TOYS))
def test_mass_fit_labels_name_this_channels_resonance_only(name):
    figures, mass = channel_figures(name)
    legend, note = texts(figures["mass_fit"])
    label = LABELS[name]
    assert f"PDG $m_{{{label}}}$ = {mass:.4f} GeV" in legend
    assert f"$\\Gamma_{{{label}}}$ = " in note
    for other_name, other in LABELS.items():
        if other_name != name:
            assert all(other not in t for t in legend) and other not in note


@pytest.mark.parametrize("name, unit", [("Z_mumu", "GeV"), ("Jpsi_mumu", "MeV")])
def test_natural_width_unit(name, unit):
    figures, _ = channel_figures(name)
    width = pdg_mass_width(CHANNELS[name].resonance)[2]
    _, note = texts(figures["mass_fit"])
    assert f"= {_width_text(width)} (fixed)" in note and _width_text(width).endswith(unit)


def test_width_text_switches_unit_below_100_mev():
    assert _width_text(0.0926e-3) == "0.0926 MeV"
    assert _width_text(0.0999) == "99.9 MeV"
    assert _width_text(0.1) == "0.100 GeV"
    assert _width_text(2.5) == "2.500 GeV"


@pytest.mark.parametrize("name", sorted(TOYS))
def test_os_vs_ss_labels_name_this_channels_resonance(name):
    figures, mass = channel_figures(name)
    ax = figures["os_vs_ss"].axes[0]
    legend = [t.get_text() for t in ax.get_legend().get_texts()]
    assert f"PDG $m_{{{LABELS[name]}}}$ = {mass:.4f} GeV" in legend
    assert not any(other in t for t in legend for n, other in LABELS.items() if n != name)


@pytest.mark.parametrize("name", sorted(TOYS))
def test_layout_has_no_overlaps_for_each_channel(name):
    figures, _ = channel_figures(name)
    for fig_name, fig in figures.items():
        assert layout_overlaps(fig) == [], fig_name


def test_pdg_line_only_inside_the_plotted_range():
    h = toy_histogram(np.random.default_rng(1), mean=3.1, sigma=0.03, slope=1.0, bins=50, range=(2.6, 3.6))
    fit = fit_mass_peak(h, model="gauss_poly", fit_range=(2.8, 3.4))
    for mass, inside in ((91.1879, False), (2.5999, False), (3.6001, False), (3.0969, True), (2.6, True)):
        fig, (ax, _) = plot_mass_spectrum(h, fit, resonance_label="X", pdg_mass=mass)
        lines = [ln for ln in ax.lines if ln.get_gid() == "pdg"]
        legend = [t.get_text() for t in ax.get_legend().get_texts()]
        if inside:
            assert len(lines) == 1 and lines[0].get_xdata()[0] == mass
            assert f"PDG $m_{{X}}$ = {mass:.4f} GeV" in legend
        else:
            assert not lines and not any("PDG" in t for t in legend), mass
        fig2, ax2 = plot_os_vs_ss(h, h, resonance_label="X", pdg_mass=mass)
        assert bool([ln for ln in ax2.lines if ln.get_gid() == "pdg"]) is inside
    fig, (ax, _) = plot_mass_spectrum(h, fit)  # no PDG mass given: no line, nothing assumed
    assert not [ln for ln in ax.lines if ln.get_gid() == "pdg"]
    fig, (ax, _) = plot_mass_spectrum(h, fit, pdg=False, resonance_label="X", pdg_mass=3.0969)
    assert not [ln for ln in ax.lines if ln.get_gid() == "pdg"]


def test_gamma_without_label_and_width_mismatch():
    h = toy_histogram(np.random.default_rng(2))
    width = pdg_mass_width("Z")[2]
    fit = fit_mass_peak(h, model="voigt_poly", natural_width=width)
    _, note = texts(plot_mass_spectrum(h, fit)[0])
    assert "$\\Gamma$ = 2.496 GeV (fixed)" in note
    with pytest.raises(ValueError, match="differs from the width fixed in the fit"):
        plot_mass_spectrum(h, fit, natural_width=1.0)


def test_label_falls_back_to_the_particle_package():
    cfg = dataclasses.replace(CHANNELS["Jpsi_mumu"], name="jpsi_nolabel", resonance_label=None)
    assert resonance_label(cfg) == r"J/\psi(1S)"
    assert resonance_label(dataclasses.replace(CHANNELS["Z_mumu"], resonance_label=None)) == "Z^{0}"
