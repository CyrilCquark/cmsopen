import dataclasses
import math

import awkward as ak
import hist
import numpy as np
import pytest
from scipy import integrate, special, stats
from synthetic import REAL_FILE

import cmsopen
from cmsopen.fitting import (
    MODELS,
    FitError,
    FitResult,
    MassHistogram,
    compare_to_pdg,
    fit_mass_peak,
    fit_stability,
    gaussian,
    gaussian_plus_polynomial,
    make_histogram,
    pdg_mass_width,
    polynomial,
    pull_test,
    toy_histogram,
    voigt_plus_polynomial,
)

TRUE_MEAN, TRUE_SIGMA = 91.0, 2.0
EDGES = np.linspace(60.0, 120.0, 61)


def gauss_exp_toy(rng, n_signal=4000.0, n_background=4000.0, mean=TRUE_MEAN, sigma=TRUE_SIGMA, slope=25.0, edges=EDGES):
    """Independent toy generator: Gaussian + falling exponential, integrated per bin, Poisson-fluctuated."""
    signal = n_signal * np.diff(stats.norm.cdf(edges, mean, sigma))
    expon = stats.truncexpon(b=(edges[-1] - edges[0]) / slope, loc=edges[0], scale=slope)
    background = n_background * np.diff(expon.cdf(edges))
    return MassHistogram(rng.poisson(signal + background).astype(float), edges)


def sampled_masses(rng, n_signal=20000, n_background=20000, mean=TRUE_MEAN, sigma=TRUE_SIGMA, gamma=None, slope=25.0):
    """Unbinned toy masses: Gaussian (or Voigt if gamma is given) signal plus exponential background in 60-120 GeV."""
    sig = mean + sigma * rng.standard_normal(n_signal)
    if gamma is not None:
        sig = sig + gamma * rng.standard_cauchy(n_signal)
    bkg = stats.truncexpon(b=60.0 / slope, loc=60.0, scale=slope).rvs(n_background, random_state=rng)
    return np.concatenate([sig, bkg])


# -- 1. toy fit recovers the truth ---------------------------------------------------------------------


def test_gaussian_toy_recovers_truth():
    h = gauss_exp_toy(np.random.default_rng(11))
    r = fit_mass_peak(h, model="gauss_poly", fit_range=(70, 110), poly_degree=2)
    (m, me), (s, se) = r.peak_position, r.resolution
    assert abs(m - TRUE_MEAN) < 3 * me, (m, me)
    assert abs(s - TRUE_SIGMA) < 3 * se, (s, se)
    assert r.warnings == ()
    assert r.parameter_names == ("amplitude", "mean", "sigma", "c0", "c1", "c2")
    # signal + background yields add up to the entries in the window (Neyman chi2 is slightly low)
    total = r.signal_yield[0] + r.background_yield[0]
    assert abs(total - r.n_entries) < 3 * math.sqrt(r.n_entries)
    assert r.fwhm[0] == pytest.approx(2 * math.sqrt(2 * math.log(2)) * s)


# -- 2. pull test -----------------------------------------------------------------------------------------


@pytest.mark.slow
def test_pull_test_1000_toys(capsys):
    rng = np.random.default_rng(2012)
    pulls = []
    for _ in range(1000):
        r = fit_mass_peak(gauss_exp_toy(rng), model="gauss_poly", fit_range=(70, 110), poly_degree=2)
        m, e = r.peak_position
        pulls.append((m - TRUE_MEAN) / e)
    pulls = np.array(pulls)
    mean, std = pulls.mean(), pulls.std(ddof=1)
    with capsys.disabled():
        print(f"\n  pull test, 1,000 toys: mean {mean:+.3f}, std {std:.3f}")
    assert len(pulls) == 1000
    assert abs(mean) < 0.2
    assert 0.8 < std < 1.2


def test_library_pull_test_matches_its_definition():
    result = pull_test(n_toys=60, seed=7)
    assert result.n_toys == 60 and result.n_failed == 0 and len(result.pulls) == 60
    assert result.mean == pytest.approx(np.mean(result.pulls))
    assert result.std == pytest.approx(np.std(result.pulls, ddof=1))
    # same seed, same toys
    np.testing.assert_array_equal(pull_test(n_toys=5, seed=3).pulls, pull_test(n_toys=5, seed=3).pulls)


# -- 3. Voigt toy ---------------------------------------------------------------------------------------------


def test_voigt_recovers_breit_wigner_convolved_gaussian():
    gamma, sigma = 1.25, 1.5  # Breit-Wigner half width and Gaussian resolution of the toy, GeV
    masses = sampled_masses(np.random.default_rng(5), n_signal=40000, n_background=10000, sigma=sigma, gamma=gamma)
    r = fit_mass_peak(masses, model="voigt_poly", natural_width=2 * gamma, fit_range=(70, 110), poly_degree=2)
    (m, me), (s, se) = r.peak_position, r.resolution
    assert r.gamma == pytest.approx(gamma)
    assert abs(m - TRUE_MEAN) < 3 * me, (m, me)
    assert abs(s - sigma) < 3 * se, (s, se)
    assert r.p_value > 1e-3
    # a Gaussian fitted to the same data needs a much wider effective sigma and fits worse
    g = fit_mass_peak(masses, model="gauss_poly", fit_range=(70, 110), poly_degree=2)
    assert g.resolution[0] > s + 0.5
    assert g.chi2 > r.chi2


def test_voigt_default_width_is_the_z_width():
    r = fit_mass_peak(toy_histogram(np.random.default_rng(1)), model="voigt_poly")
    assert r.gamma == pytest.approx(0.5 * pdg_mass_width("Z")[2])
    assert 2.4 < 2 * r.gamma < 2.6


# -- 4. chi2, ndf, p-value, covariance --------------------------------------------------------------------------


@pytest.mark.parametrize("model", MODELS)
def test_chi2_ndf_pvalue_and_covariance(model):
    h = gauss_exp_toy(np.random.default_rng(21), n_signal=8000)
    r = fit_mass_peak(h, model=model, fit_range=(70, 110), poly_degree=2)
    edges = h.edges
    inside = (edges[:-1] >= 70) & (edges[1:] <= 110)
    # independent: integrate the fitted density over each bin with adaptive quadrature
    bins = zip(edges[:-1][inside], edges[1:][inside], strict=False)
    expected = np.array([integrate.quad(r.model, a, b)[0] for a, b in bins])
    counts = h.counts[inside]
    chi2 = np.sum((counts - expected) ** 2 / np.maximum(counts, 1.0))
    assert r.chi2 == pytest.approx(chi2, rel=1e-6)
    assert r.ndf == inside.sum() - 6 == 34
    assert r.p_value == pytest.approx(stats.chi2.sf(chi2, 34), rel=1e-5)
    assert r.chi2_ndf == pytest.approx(r.chi2 / r.ndf)
    cov = r.covariance
    np.testing.assert_allclose(cov, cov.T, rtol=1e-10, atol=0)
    assert np.linalg.eigvalsh(cov).min() >= -1e-12 * np.abs(cov).max()
    np.testing.assert_allclose(r.errors, np.sqrt(np.diag(cov)))
    np.testing.assert_allclose(np.diag(r.correlation), 1.0)
    assert r.parameters["mean"] == (pytest.approx(r.values[1]), pytest.approx(r.errors[1]))


def test_covariance_is_absolute_not_rescaled_by_chi2():
    """Errors are the Poisson ones, (J^T W J)^-1, even when chi2/ndf is far from 1.

    A pull test cannot see this: on toys where the model is right, chi2/ndf ~ 1 and a covariance
    rescaled by chi2/ndf looks the same. A Voigt fitted to a pure-Gaussian toy has chi2/ndf well
    above 1, where rescaling would inflate the errors.
    """
    h = gauss_exp_toy(np.random.default_rng(21), n_signal=20000)
    r = fit_mass_peak(h, model="voigt_poly", fit_range=(70, 110), poly_degree=2)
    assert r.chi2_ndf > 1.5
    weights = 1.0 / np.maximum(h.counts[r.fit_mask], 1.0)
    jac = np.empty((int(r.fit_mask.sum()), len(r.values)))
    for j in range(len(r.values)):
        step = 1e-4 * r.errors[j]
        up, down = r.values.copy(), r.values.copy()
        up[j] += step
        down[j] -= step
        jac[:, j] = (r._density(up) - r._density(down)) / (2 * step)
    independent = np.linalg.inv(jac.T @ (weights[:, None] * jac))
    np.testing.assert_allclose(np.diag(r.covariance), np.diag(independent), rtol=1e-3)


# -- 5. make_histogram ------------------------------------------------------------------------------------------------


def test_make_histogram_counts_errors_and_flow():
    values = np.array([59.0, 60.0, 60.5, 61.2, 90.0, 119.99, 120.0, 150.0, np.nan])
    h = make_histogram(values)
    in_range = (values >= 60) & (values < 120)
    assert h.counts.sum() == in_range.sum() == h.n_entries == 5
    assert (h.underflow, h.overflow) == (1, 2)
    assert len(h.counts) == 60 and h.widths == pytest.approx(np.ones(60))
    np.testing.assert_array_equal(h.errors, np.sqrt(h.counts))
    np.testing.assert_array_equal(h.fit_errors, np.sqrt(np.maximum(h.counts, 1)))
    np.testing.assert_array_equal(h.counts, np.histogram(values[in_range], bins=EDGES)[0])
    assert h.centers[0] == 60.5


def test_make_histogram_flattens_jagged_awkward():
    jagged = ak.Array([[91.0, 70.0], [], [100.5], [119.0, 61.0, 200.0]])
    h = make_histogram(jagged, bins=6, range=(60, 120))
    assert h.n_entries == 5 and h.overflow == 1
    np.testing.assert_array_equal(h.counts, [1, 1, 0, 1, 1, 1])


def test_make_histogram_edges_and_to_hist():
    h = make_histogram([1.0, 2.5, 2.6], bins=[0.0, 2.0, 3.0])
    np.testing.assert_array_equal(h.counts, [1, 2])
    hh = h.to_hist()
    assert isinstance(hh, hist.Hist)
    np.testing.assert_array_equal(hh.values(), h.counts)
    np.testing.assert_array_equal(hh.axes[0].edges, h.edges)
    h2 = make_histogram(np.array([65.0, 65.5, 70.0]))
    np.testing.assert_array_equal(h2.to_hist().values(), h2.counts)


def test_make_histogram_empty_raises():
    with pytest.raises(ValueError, match="no values"):
        make_histogram([])
    with pytest.raises(ValueError, match="no values"):
        make_histogram(ak.Array([[], []]))


def test_mass_histogram_validation():
    with pytest.raises(ValueError):
        MassHistogram(np.array([1.0, -1.0]), np.array([0.0, 1.0, 2.0]))
    with pytest.raises(ValueError):
        MassHistogram(np.array([1.0]), np.array([0.0, 1.0, 2.0]))


# -- models -----------------------------------------------------------------------------------------------------------


def test_models():
    x = np.linspace(40, 140, 20001)
    assert integrate.simpson(gaussian(x, 500.0, 91.0, 2.0), x=x) == pytest.approx(500.0, rel=1e-6)
    assert polynomial(np.array([90.0, 92.0]), 3.0, 0.5, 0.25, x0=90.0) == pytest.approx([3.0, 3.0 + 1.0 + 1.0])
    assert polynomial(np.array([1.0, 2.0])) == pytest.approx([0.0, 0.0])
    gp = gaussian_plus_polynomial(x, 500.0, 91.0, 2.0, 1.0, 0.0, x0=90.0)
    assert gp == pytest.approx(gaussian(x, 500.0, 91.0, 2.0) + 1.0)
    v = voigt_plus_polynomial(x, 1000.0, 91.0, 1.5, 0.0, gamma=1.25)
    # within +-50 GeV of the peak a Lorentzian of half width 1.25 holds (2/pi) atan(50/1.25) of its area
    assert integrate.simpson(v, x=x) == pytest.approx(1000.0 * 2 / math.pi * math.atan(50 / 1.25), rel=2e-3)
    assert v == pytest.approx(1000.0 * special.voigt_profile(x - 91.0, 1.5, 1.25))


# -- 6. PDG comparison -------------------------------------------------------------------------------------------------


def test_pdg_z_mass_from_particle(capsys):
    mass, mass_err, width, width_err = pdg_mass_width("Z")
    with capsys.disabled():
        print(f"\n  particle package: Z mass {mass!r} +- {mass_err!r} GeV, width {width!r} +- {width_err!r} GeV")
    assert mass == pytest.approx(91.1876, abs=1e-3)
    assert width == pytest.approx(2.4952, abs=5e-3)
    assert pdg_mass_width(23) == (mass, mass_err, width, width_err)


def test_compare_to_pdg_hand_case():
    r = fit_mass_peak(toy_histogram(np.random.default_rng(4)))
    values, errors = r.values.copy(), r.errors.copy()
    values[1], errors[1] = 91.0, 0.05
    hand = dataclasses.replace(r, values=values, errors=errors)
    c = compare_to_pdg(hand)
    pdg = pdg_mass_width("Z")[0]
    assert c.pdg_mass == pdg
    assert c.fitted == 91.0 and c.fitted_error == 0.05
    assert c.difference == pytest.approx(91.0 - pdg)
    assert c.pull == pytest.approx((91.0 - pdg) / 0.05)
    assert c.pull < 0 and "below" in c.note
    values[1] = pdg + 0.01
    close = compare_to_pdg(dataclasses.replace(r, values=values, errors=errors))
    assert close.pull == pytest.approx(0.2) and "consistent" in close.note and "above" in close.note
    with pytest.raises(TypeError):
        compare_to_pdg("not a fit")


# -- 7. failures are loud ----------------------------------------------------------------------------------------------


@pytest.mark.parametrize("model", MODELS)
@pytest.mark.parametrize("seed", [1, 2, 3])
def test_flat_noise_raises(model, seed):
    flat = MassHistogram(np.random.default_rng(seed).poisson(50.0, 60).astype(float), EDGES)
    with pytest.raises(FitError):
        fit_mass_peak(flat, model=model)


@pytest.mark.parametrize("model", MODELS)
def test_all_zero_histogram_raises(model):
    with pytest.raises(FitError, match="no entries"):
        fit_mass_peak(MassHistogram(np.zeros(60), EDGES), model=model)
    outside = make_histogram([10.0, 20.0, 200.0])  # values exist, but none in range
    with pytest.raises(FitError, match="no entries"):
        fit_mass_peak(outside, model=model)


def test_bad_arguments():
    h = toy_histogram(np.random.default_rng(0))
    with pytest.raises(ValueError, match="model"):
        fit_mass_peak(h, model="breit_wigner")
    with pytest.raises(ValueError, match="poly_degree"):
        fit_mass_peak(h, poly_degree=7)
    with pytest.raises(ValueError, match="unknown parameter"):
        fit_mass_peak(h, initial={"width": 2.0})
    with pytest.raises(ValueError, match="no bin"):
        fit_mass_peak(h, fit_range=(130, 140))
    with pytest.raises(FitError, match="cannot constrain"):
        fit_mass_peak(h, fit_range=(88, 92), poly_degree=2)


def test_fit_from_values_initial_and_actual_range():
    masses = sampled_masses(np.random.default_rng(8))
    r = fit_mass_peak(masses, fit_range=(75, 105), bins=30)  # 2 GeV bins from 60: 75 and 105 are not edges
    assert r.fit_range == (76.0, 104.0)
    assert r.x0 == 90.0
    r2 = fit_mass_peak(masses, initial={"mean": 89.0, "sigma": 3.0})
    r3 = fit_mass_peak(masses)
    assert r2.peak_position[0] == pytest.approx(r3.peak_position[0], abs=1e-3)


def test_negative_background_is_a_warning_not_silent():
    """A background component below zero (total still positive) is reported, not hidden and not fatal."""
    # Exact expected counts: Voigt peak plus a line that crosses zero at ~106.7 GeV. The Lorentzian
    # tail keeps the total positive at 110 GeV (about 110 - 24 events/GeV).
    centers = 0.5 * (EDGES[:-1] + EDGES[1:])
    density = voigt_plus_polynomial(centers, 100000.0, 91.0, 1.4, 120.0, -7.2, gamma=1.25, x0=90.0)
    window = (centers > 70) & (centers < 110)
    assert np.all(density[window] > 0)
    counts = np.where(window, density, 0.0)  # only the 70-110 GeV bins are fitted
    r = fit_mass_peak(MassHistogram(counts, EDGES), model="voigt_poly", natural_width=2.5, poly_degree=1)
    assert r.background(110.0) < 0 < r.model(110.0)
    assert r.warnings and "significantly negative" in r.warnings[0]
    assert "WARNING" in r.table()
    assert r.peak_position[0] == pytest.approx(91.0, abs=1e-3)
    assert r.values[3:] == pytest.approx([120.0, -7.2], rel=1e-3)


# -- 8. fit_stability --------------------------------------------------------------------------------------------------


def test_fit_stability_grid_and_summary():
    masses = sampled_masses(np.random.default_rng(13), n_signal=20000, n_background=20000)
    s = fit_stability(masses)
    assert s.n_fits == 3 * 3 * 3 * 2 == 54
    assert len(s.rows) + len(s.failed) == 54
    configs = {(r["model"], r["bin_width"], r["poly_degree"]) for r in (*s.rows, *s.failed)}
    assert len(configs) == 2 * 3 * 3
    masses_fit = np.array([r["mass"] for r in s.rows])
    assert s.mean == pytest.approx(masses_fit.mean())
    assert s.std == pytest.approx(masses_fit.std(ddof=1))
    assert (s.min, s.max) == (masses_fit.min(), masses_fit.max())
    assert s.range == pytest.approx(masses_fit.max() - masses_fit.min())
    assert abs(s.mean - TRUE_MEAN) < 0.1
    text = str(s)
    assert f"{len(s.rows)} of 54 fits converged" in text


def test_fit_stability_lists_failures():
    flat = np.random.default_rng(1).uniform(60, 120, 20000)
    s = fit_stability(flat, fit_ranges=((70, 110),), bin_widths=(1.0,), poly_degrees=(1, 2), models=("gauss_poly",))
    assert len(s.failed) == 2 and len(s.rows) == 0 and math.isnan(s.mean)
    assert all("reason" in f for f in s.failed)
    assert "FAILED" in str(s)
    with pytest.raises(ValueError, match="does not divide"):
        fit_stability(flat, bin_widths=(0.7,))


def test_package_exports():
    for name in (
        "make_histogram",
        "MassHistogram",
        "fit_mass_peak",
        "FitResult",
        "FitError",
        "compare_to_pdg",
        "fit_stability",
        "gaussian",
        "polynomial",
        "gaussian_plus_polynomial",
        "voigt_plus_polynomial",
    ):
        assert name in cmsopen.__all__ and getattr(cmsopen, name) is not None
    assert isinstance(fit_mass_peak(toy_histogram(np.random.default_rng(2))), FitResult)


# -- real file ---------------------------------------------------------------------------------------------------------


@pytest.mark.skipif(not REAL_FILE.exists(), reason=f"real CMS file not downloaded: {REAL_FILE} (see DATA.md)")
@pytest.mark.slow
def test_real_file_z_peak():
    from cmsopen import ZMUMU_MUON_CUTS, best_pair, open_events, opposite_sign_pairs
    from cmsopen.ingestion import DIMUON_TRIGGERS_2012

    with open_events(REAL_FILE) as ev:
        sel = ev.muons(**ZMUMU_MUON_CUTS).require_trigger(*DIMUON_TRIGGERS_2012).require(2)
    masses = best_pair(opposite_sign_pairs(sel)).mass
    for model in MODELS:
        r = fit_mass_peak(masses, model=model)
        assert abs(r.peak_position[0] - 91.1876) < 1.0
        assert 0.5 < r.resolution[0] < 4.0
        assert np.all(np.isfinite(r.errors))


# -- machine-readable warnings and the PDG output ----------------------------------------------------------------


def _voigt_line_toy(c0, c1, scale=1.0):
    centers = 0.5 * (EDGES[:-1] + EDGES[1:])
    density = scale * voigt_plus_polynomial(centers, 25000.0, 91.0, 1.4, c0, c1, gamma=1.25, x0=90.0)
    window = (centers > 70) & (centers < 110)
    return MassHistogram(np.where(window, density, 0.0), EDGES)


def test_warnings_are_machine_readable_and_yields_flagged():
    from cmsopen.fitting import FitWarning

    # significantly negative: the 4x-scaled line crossing zero at ~106.7 GeV (see the test above)
    r = fit_mass_peak(_voigt_line_toy(30.0, -1.8, scale=4.0), model="voigt_poly", natural_width=2.5, poly_degree=1)
    assert isinstance(r.warnings, tuple) and len(r.warnings) == 1
    w = r.warnings[0]
    assert isinstance(w, FitWarning) and isinstance(w, str)
    assert w.code == "background_negative"
    assert w.details["significant"] is True
    assert w.details["min_density"] < 0 and 70 <= w.details["at_mass"] <= 110
    assert w.details["min_density"] + 3 * w.details["error"] < 0
    assert r.yields_reliable is False

    # mildly negative: same shape at 1/4 the statistics, the dip is within 3 errors of zero
    mild = fit_mass_peak(_voigt_line_toy(30.0, -1.8), model="voigt_poly", natural_width=2.5, poly_degree=1)
    assert [x.code for x in mild.warnings] == ["background_negative"]
    assert mild.warnings[0].details["significant"] is False and "dips below zero" in mild.warnings[0]
    assert mild.yields_reliable is False
    assert "WARNING" in mild.table()

    # a positive background: no warning, yields reliable
    clean = fit_mass_peak(_voigt_line_toy(30.0, -0.5), model="voigt_poly", natural_width=2.5, poly_degree=1)
    assert np.all(clean.background(np.linspace(70, 110, 401)) >= 0)
    assert clean.warnings == () and clean.yields_reliable is True


def test_yields_reliable_matches_background_sign_on_toys():
    for seed in range(5):
        r = fit_mass_peak(gauss_exp_toy(np.random.default_rng(seed)))
        negative = bool(np.any(r.background(np.linspace(*r.fit_range, 401)) < 0))
        assert r.yields_reliable is (not negative)


def test_compare_to_pdg_output_is_labelled_statistical():
    r = fit_mass_peak(toy_histogram(np.random.default_rng(4)))
    c = compare_to_pdg(r)
    text = str(c)
    assert c.relative_difference == pytest.approx(c.difference / c.pdg_mass)
    assert "stat-only uncertainty" in text
    assert "(statistical error only)" in text
    assert f"{100 * c.relative_difference:+.3f} %" in text
    assert f"{c.difference:+.4f} GeV" in text
    assert "statistical sigma" not in text  # no bare pull presented as a significance
    assert "FitWarning" in cmsopen.__all__
