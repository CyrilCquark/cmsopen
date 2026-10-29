"""The last-resort placement stage of plot_mass_spectrum: a long mixture annotation with six-digit yields."""

import numpy as np
import pytest

import cmsopen.plotting as plotting
from cmsopen import fit_mass_peak, make_histogram
from cmsopen.fitting import pdg_mass_width
from cmsopen.pipeline import CHANNELS, resonance_label

JPSI = CHANNELS["Jpsi_mumu"]


@pytest.fixture(scope="module")
def big_jpsi_fit():
    """A J/psi-like two-resolution peak with 120,000 signal pairs (the 6-file development set has ~100,000)."""
    rng = np.random.default_rng(1)
    n = 120_000
    m = 3.0934 + np.where(rng.random(n) < 0.42, 0.042, 0.024) * rng.standard_normal(n)
    h = make_histogram(np.concatenate([m, rng.uniform(2.6, 3.6, 30_000)]), bins=JPSI.bins, range=JPSI.mass_range)
    width = pdg_mass_width(JPSI.resonance)[2]
    return h, fit_mass_peak(h, model="cb2_bw_poly2", fit_range=JPSI.fit_range, poly_degree=2, natural_width=width,
                            cb_n=JPSI.cb_n)


def plot(h, fit):
    pdg = pdg_mass_width(JPSI.resonance)
    mass, width = pdg[0], pdg[2]
    return plotting.plot_mass_spectrum(h, fit, resonance_label=resonance_label(JPSI), pdg_mass=mass,
                                       natural_width=width)


def test_long_annotation_is_placed_by_the_last_resort_stage(big_jpsi_fit):
    fig, axes = plot(*big_jpsi_fit)
    annotation = next(t for t in axes[0].texts if t.get_gid() == plotting._ANNOTATION_GID)
    assert annotation.get_fontsize() in plotting._LAST_RESORT_FONT_SIZES
    assert plotting.layout_overlaps(fig) == []


def test_without_the_last_resort_stage_it_cannot_be_placed(big_jpsi_fit, monkeypatch):
    monkeypatch.setattr(plotting, "_LAST_RESORT_FONT_SIZES", ())
    with pytest.raises(RuntimeError, match="could not place"):
        plot(*big_jpsi_fit)
