"""Figure text: never below 8 pt, the annotation never over the data, a shortened annotation when it does not fit."""

import numpy as np
import pytest
from test_pipeline import write_z_file

import cmsopen.plotting as plotting
from cmsopen import analyze, fit_mass_peak, make_histogram
from cmsopen.datasets import GENERIC_DATA_LABEL
from cmsopen.fitting import pdg_mass_width
from cmsopen.pipeline import CHANNELS, resonance_label

SINGLE = r"2012C DoubleMuParked, $\sqrt{s}$ = 8 TeV"
MIXED = r"2012B+2012C DoubleMuParked, $\sqrt{s}$ = 8 TeV"


def z_masses(rng):
    """Z-like: 170,000 pairs (about the 6-file development set), two resolutions, a radiative tail, background."""
    n = 170_000
    m = 90.9 + 0.5 * 2.4952 * rng.standard_cauchy(n) + np.where(rng.random(n) < 0.8, 1.2, 3.0) * rng.standard_normal(n)
    tail = rng.random(n) < 0.1
    m[tail] -= rng.exponential(4.0, tail.sum())
    return np.concatenate([m, 60.0 + rng.exponential(25.0, 5000)])


def jpsi_masses(rng):
    """J/psi-like: 120,000 pairs in two resolutions on a flat background (six-digit yields)."""
    n = 120_000
    m = 3.0934 + np.where(rng.random(n) < 0.42, 0.042, 0.024) * rng.standard_normal(n)
    return np.concatenate([m, rng.uniform(2.6, 3.6, 30_000)])


@pytest.fixture(scope="module", params=["Z_mumu", "Jpsi_mumu"])
def channel_fit(request):
    """Each channel's default-model fit of a high-statistics synthetic sample."""
    cfg = CHANNELS[request.param]
    masses = (z_masses if request.param == "Z_mumu" else jpsi_masses)(np.random.default_rng(1))
    h = make_histogram(masses, bins=cfg.bins, range=cfg.mass_range)
    width = pdg_mass_width(cfg.resonance)[2]
    fit = fit_mass_peak(h, model=cfg.model, fit_range=cfg.fit_range, poly_degree=cfg.poly_degree,
                        natural_width=width, cb_n=cfg.cb_n)
    return cfg, h, fit


def plot(cfg, h, fit, data_label):
    pdg = pdg_mass_width(cfg.resonance)
    return plotting.plot_mass_spectrum(h, fit, resonance_label=resonance_label(cfg), pdg_mass=pdg[0],
                                       natural_width=pdg[2], data_label=data_label)


def texts(fig):
    return [t for t in fig.findobj(lambda o: hasattr(o, "get_fontsize") and hasattr(o, "get_text")) if t.get_text()]


def annotation_of(axes):
    return next(t for t in axes[0].texts if t.get_gid() == plotting._ANNOTATION_GID)


@pytest.mark.parametrize("label", [SINGLE, MIXED, GENERIC_DATA_LABEL])
def test_no_text_below_8_pt_and_the_annotation_does_not_cover_the_data(channel_fit, label):
    fig, axes = plot(*channel_fit, label)
    small = [(t.get_fontsize(), t.get_text()[:40]) for t in texts(fig) if t.get_fontsize() < plotting.MIN_FONT_SIZE]
    assert small == [] and plotting.MIN_FONT_SIZE == 8.0
    assert plotting.layout_overlaps(fig) == []
    text = annotation_of(axes).get_text()
    assert text.splitlines()[-1] == label and "M_{\\mathrm{pole}}" in text and "\\chi^2" in text


def test_a_long_annotation_is_shortened_not_shrunk(channel_fit):
    cfg, h, fit = channel_fit
    if cfg.name != "Jpsi_mumu":
        pytest.skip("only the J/psi mixture with six-digit yields and the mixed label needs shortening")
    _, axes = plot(cfg, h, fit, MIXED)
    text = annotation_of(axes).get_text()
    assert "\\alpha" not in text and "(fixed)" not in text  # alpha and n, then the fixed width, are left out
    assert annotation_of(axes).get_fontsize() >= plotting.MIN_FONT_SIZE


def test_without_shortening_it_cannot_be_placed(channel_fit, monkeypatch):
    cfg, h, fit = channel_fit
    if cfg.name != "Jpsi_mumu":
        pytest.skip("only the J/psi case needs shortening")
    full = plotting._fit_annotation
    monkeypatch.setattr(plotting, "_fit_annotation", lambda *a, **k: full(*a[:4]))  # every level gives the full text
    with pytest.raises(RuntimeError, match="could not place"):
        plot(cfg, h, fit, MIXED)


@pytest.mark.slow
def test_every_pipeline_figure_has_no_text_below_8_pt(tmp_path):
    f = write_z_file(tmp_path / "z.root", 15_000, seed=4, fsr=0.3, wide_fraction=0.5, wide_sigma=4.0)
    r = analyze(f, verbose=False, stability=False)
    for name, fig in r.figures.items():
        assert min(t.get_fontsize() for t in texts(fig)) >= plotting.MIN_FONT_SIZE, name
        assert plotting.layout_overlaps(fig) == [], name
