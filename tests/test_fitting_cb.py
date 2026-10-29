"""The Breit-Wigner (x) Crystal Ball models cb_bw_exp and cb_bw_poly2 of cmsopen.fitting."""

import math

import numpy as np
import pytest
from scipy import integrate, special, stats

from cmsopen.fitting import (
    CB_BW_THRESHOLD,
    CB_MODELS,
    FitError,
    MassHistogram,
    _cb_bw_shape,
    _gl_points,
    crystal_ball,
    crystalball_bw,
    crystalball_bw_exp,
    crystalball_bw_poly2,
    exponential,
    fit_mass_peak,
    fit_stability,
    pdg_mass_width,
)

Z_GAMMA = 0.5 * pdg_mass_width("Z")[2]
JPSI_GAMMA = 0.5 * pdg_mass_width("J/psi")[2]

# Toy truth: a resonance with a radiative low-mass tail on a falling exponential background.
TOYS = {
    "Z": dict(mass=91.0, sigma=1.4, alpha=1.5, n=3.0, gamma=Z_GAMMA, slope=-0.04, n_sig=20000, n_bkg=8000,
              hist=(60.0, 120.0), bins=60, fit=(70.0, 110.0)),
    "Jpsi": dict(mass=3.097, sigma=0.03, alpha=1.8, n=3.0, gamma=JPSI_GAMMA, slope=-2.0, n_sig=15000, n_bkg=6000,
                 hist=(2.6, 3.6), bins=50, fit=(2.8, 3.4)),
}


def cb_toy(rng, kind, **override):
    """A Poisson-fluctuated histogram drawn event by event, independently of cmsopen's model code.

    Signal: mass + gamma * Cauchy + sigma * Crystal Ball (scipy.stats.crystalball, tail on the low side).
    Background: exp(slope * m) truncated to the histogram range, sampled by inverting its CDF.
    """
    t = {**TOYS[kind], **override}
    lo, hi = t["hist"]
    k = rng.poisson(t["n_sig"])
    sig = (t["mass"] + t["gamma"] * rng.standard_cauchy(k)
           + t["sigma"] * stats.crystalball.rvs(t["alpha"], t["n"], size=k, random_state=rng))
    u = rng.random(rng.poisson(t["n_bkg"]))
    bkg = lo + np.log1p(u * np.expm1(t["slope"] * (hi - lo))) / t["slope"]
    counts, edges = np.histogram(np.r_[sig, bkg], bins=t["bins"], range=t["hist"])
    return MassHistogram(counts.astype(np.float64), edges)


def fit_toy(h, kind, model="cb_bw_exp", **kw):
    t = TOYS[kind]
    return fit_mass_peak(h, model=model, fit_range=t["fit"], natural_width=2 * t["gamma"], cb_n=t["n"], **kw)


# -- the shape ----------------------------------------------------------------------------------------------------


def test_crystal_ball_core_tail_and_continuity():
    alpha, n = 1.3, 2.5
    u = np.array([-5.0, -alpha, 0.0, 1.0, 5.0])
    y = crystal_ball(u, alpha, n)
    np.testing.assert_allclose(y[2:], np.exp(-0.5 * u[2:] ** 2), rtol=1e-15)  # Gaussian above the join
    assert y[0] > math.exp(-12.5) * 1e3  # the low side has the long tail, the high side does not
    eps = 1e-7
    left, right = crystal_ball([-alpha - eps], alpha, n)[0], crystal_ball([-alpha + eps], alpha, n)[0]
    assert left == pytest.approx(right, rel=1e-6)  # continuous value
    d_left = (crystal_ball([-alpha - eps], alpha, n) - crystal_ball([-alpha - 2 * eps], alpha, n))[0] / eps
    d_right = (crystal_ball([-alpha + 2 * eps], alpha, n) - crystal_ball([-alpha + eps], alpha, n))[0] / eps
    assert d_left == pytest.approx(d_right, rel=1e-4)  # continuous slope
    assert crystal_ball(0.0, alpha, n) == 1.0
    with pytest.raises(ValueError, match="alpha > 0 and n > 0"):
        crystal_ball(u, 0.0, n)


@pytest.mark.parametrize("kind, convolve", [("Z", None), ("Jpsi", True)])
def test_large_alpha_limit_matches_voigt_profile(kind, convolve):
    """alpha -> infinity: the Crystal Ball is a Gaussian, so BW (x) CB is a Voigt profile."""
    t = TOYS[kind]
    edges = np.linspace(*t["fit"], 41)
    pts, wts = _gl_points(edges)
    x = np.linspace(edges[0] + 1e-3 * t["sigma"], edges[-1] - 1e-3 * t["sigma"], 801)
    got = crystalball_bw(x, 1000.0, t["mass"], t["sigma"], 50.0, n=t["n"], gamma=t["gamma"], norm_edges=edges,
                         convolve=convolve)
    voigt = special.voigt_profile(x - t["mass"], t["sigma"], t["gamma"])
    norm = special.voigt_profile(pts - t["mass"], t["sigma"], t["gamma"]) @ wts
    np.testing.assert_allclose(got, 1000.0 * voigt / norm, rtol=1e-4)


def test_large_alpha_limit_of_the_crystal_ball_branch_is_a_gaussian():
    t = TOYS["Jpsi"]
    edges = np.linspace(*t["fit"], 31)
    pts, wts = _gl_points(edges)
    x = np.linspace(2.81, 3.39, 301)
    got = crystalball_bw(x, 1.0, t["mass"], t["sigma"], 50.0, n=3.0, gamma=t["gamma"], norm_edges=edges)
    gauss = special.voigt_profile(x - t["mass"], t["sigma"], 0.0)
    np.testing.assert_allclose(got, gauss / (special.voigt_profile(pts - t["mass"], t["sigma"], 0.0) @ wts),
                               rtol=1e-10)


def test_narrow_width_branch_and_agreement_where_the_branches_meet():
    sigma, mass = 0.03, 3.097
    edges = np.linspace(2.8, 3.4, 31)
    x = np.linspace(2.81, 3.39, 600)
    # J/psi: Gamma / sigma ~ 0.003, far below the threshold, so the Crystal Ball is used alone.
    assert 2 * JPSI_GAMMA < CB_BW_THRESHOLD * sigma
    np.testing.assert_array_equal(_cb_bw_shape(x, mass, sigma, 1.5, 3.0, JPSI_GAMMA, (2.8, 3.4)),
                                  crystal_ball((x - mass) / sigma, 1.5, 3.0))
    # The automatic choice switches at the threshold.
    below, above = 0.5 * 0.99 * CB_BW_THRESHOLD * sigma, 0.5 * 1.01 * CB_BW_THRESHOLD * sigma
    assert np.array_equal(_cb_bw_shape(x, mass, sigma, 1.5, 3.0, below, (2.8, 3.4)),
                          crystal_ball((x - mass) / sigma, 1.5, 3.0))
    assert not np.array_equal(_cb_bw_shape(x, mass, sigma, 1.5, 3.0, above, (2.8, 3.4)),
                              crystal_ball((x - mass) / sigma, 1.5, 3.0))
    # Where they meet, both branches describe the same density: the difference is the neglected width,
    # about (Gamma / 2) / sigma * sqrt(2 / pi) of the peak height, and shrinks in proportion to Gamma.
    diffs = []
    for ratio in (CB_BW_THRESHOLD, CB_BW_THRESHOLD / 2, CB_BW_THRESHOLD / 4):
        gamma = 0.5 * ratio * sigma
        conv = crystalball_bw(x, 1.0, mass, sigma, 1.5, n=3.0, gamma=gamma, norm_edges=edges, convolve=True)
        alone = crystalball_bw(x, 1.0, mass, sigma, 1.5, n=3.0, gamma=gamma, norm_edges=edges, convolve=False)
        diffs.append(float(np.max(np.abs(conv - alone)) / conv.max()))
    assert diffs[0] < 1.2 * 0.5 * CB_BW_THRESHOLD * math.sqrt(2 / math.pi) < 0.025
    assert diffs[1] == pytest.approx(diffs[0] / 2, rel=0.15) and diffs[2] == pytest.approx(diffs[0] / 4, rel=0.15)


def test_signal_is_normalised_over_the_fit_bins_and_composite_models_add_up():
    edges = np.linspace(70.0, 110.0, 41)
    pts, wts = _gl_points(edges)
    sig = crystalball_bw(pts, 5000.0, 91.0, 1.4, 1.2, n=2.0, gamma=Z_GAMMA, norm_edges=edges)
    assert sig @ wts == pytest.approx(5000.0, rel=1e-12)
    x = np.linspace(70, 110, 7)
    kw = dict(n=2.0, gamma=Z_GAMMA, norm_edges=edges, x0=90.0)
    np.testing.assert_allclose(
        crystalball_bw_exp(x, 5000.0, 91.0, 1.4, 1.2, 30.0, -0.05, **kw),
        crystalball_bw(x, 5000.0, 91.0, 1.4, 1.2, n=2.0, gamma=Z_GAMMA, norm_edges=edges)
        + 30.0 * np.exp(-0.05 * (x - 90.0)),
    )
    np.testing.assert_allclose(
        crystalball_bw_poly2(x, 5000.0, 91.0, 1.4, 1.2, 30.0, -1.0, 0.01, **kw),
        crystalball_bw(x, 5000.0, 91.0, 1.4, 1.2, n=2.0, gamma=Z_GAMMA, norm_edges=edges)
        + 30.0 - (x - 90.0) + 0.01 * (x - 90.0) ** 2,
    )


# -- fits -----------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("kind", ["Z", "Jpsi"])
def test_toy_recovery_with_a_low_mass_tail(kind):
    t = TOYS[kind]
    r = fit_toy(cb_toy(np.random.default_rng(11), kind), kind)
    for name, truth in (("mean", t["mass"]), ("sigma", t["sigma"]), ("slope", t["slope"])):
        value, error = r.parameters[name]
        assert abs(value - truth) < 3 * error, (name, value, error, truth)
    assert r.yields_reliable and r.background_label == "exp" and r.cb_n == t["n"]
    assert r.gamma == pytest.approx(t["gamma"], rel=1e-12)
    assert r.signal_yield[0] == pytest.approx(r.parameters["amplitude"][0], rel=1e-4)


@pytest.mark.slow
@pytest.mark.parametrize("kind", ["Z", "Jpsi"])
def test_pull_test_1000_toys(kind, capsys):
    t = TOYS[kind]
    rng = np.random.default_rng(2012 if kind == "Z" else 2013)
    pulls, failed = [], 0
    for _ in range(1000):
        try:
            r = fit_toy(cb_toy(rng, kind), kind)
        except FitError:
            failed += 1
            continue
        m, e = r.peak_position
        pulls.append((m - t["mass"]) / e)
    pulls = np.array(pulls)
    with capsys.disabled():
        print(f"\n  cb_bw_exp {kind}-like pull test, 1,000 toys: mean {pulls.mean():+.3f}, "
              f"std {pulls.std(ddof=1):.3f}, {failed} failed fits")
    assert failed <= 10
    assert abs(pulls.mean()) < 0.2
    assert 0.8 < pulls.std(ddof=1) < 1.2


@pytest.mark.parametrize("kind", ["Z", "Jpsi"])
def test_exponential_background_positive_over_the_full_range(kind):
    t = TOYS[kind]
    r = fit_toy(cb_toy(np.random.default_rng(5), kind), kind)
    full = np.linspace(*t["hist"], 2001)
    assert np.all(r.background(full) > 0) and r.parameters["c0"][0] > 0
    assert np.all(exponential(np.linspace(-100, 100, 11), 0.0, 3.0) >= 0)  # c0 >= 0 bound: never negative
    assert not r.warnings and r.yields_reliable
    # the analytic background yield equals a numerical integral of the fitted exponential
    assert r.background_yield[0] == pytest.approx(integrate.quad(r.background, *r.fit_range)[0], rel=1e-9)


@pytest.mark.parametrize("model", CB_MODELS)
@pytest.mark.parametrize("kind", ["Z", "Jpsi"])
def test_covariance_symmetric_and_positive_semidefinite(model, kind):
    r = fit_toy(cb_toy(np.random.default_rng(7), kind), kind, model=model)
    cov = r.covariance
    np.testing.assert_allclose(cov, cov.T, rtol=1e-10, atol=0)
    eig = np.linalg.eigvalsh(0.5 * (cov + cov.T))
    assert eig.min() >= -1e-12 * eig.max()
    assert np.all(np.isfinite(r.errors)) and np.all(r.errors > 0)


@pytest.mark.parametrize("model", CB_MODELS)
def test_chi2_matches_an_independent_bin_integration(model):
    h = cb_toy(np.random.default_rng(21), "Z")
    r = fit_toy(h, "Z", model=model)
    inside = r.fit_mask
    bins = zip(h.edges[:-1][inside], h.edges[1:][inside], strict=True)
    expected = np.array([integrate.quad(r.model, a, b)[0] for a, b in bins])
    counts = h.counts[inside]
    assert r.chi2 == pytest.approx(np.sum((counts - expected) ** 2 / np.maximum(counts, 1.0)), rel=1e-5)
    np.testing.assert_allclose(r.expected_counts(), expected, rtol=1e-5)


@pytest.mark.parametrize("model", CB_MODELS)
@pytest.mark.parametrize("seed", [1, 2, 3])
def test_flat_noise_raises(model, seed):
    edges = np.linspace(60.0, 120.0, 61)
    flat = MassHistogram(np.random.default_rng(seed).poisson(50.0, 60).astype(float), edges)
    with pytest.raises(FitError):
        fit_mass_peak(flat, model=model, cb_n=3.0)


def test_arguments_and_reporting():
    h = cb_toy(np.random.default_rng(3), "Z")
    with pytest.raises(ValueError, match="cb_n"):
        fit_mass_peak(h, model="cb_bw_exp")
    with pytest.raises(ValueError, match="cb_n"):
        fit_mass_peak(h, model="cb_bw_poly2", cb_n=-1.0)
    r = fit_toy(h, "Z", model="cb_bw_poly2", poly_degree=4)  # the quadratic is part of the model's name
    assert r.poly_degree == 2 and r.background_label == "pol2"
    assert r.parameter_names == ("amplitude", "mean", "sigma", "alpha", "c0", "c1", "c2")
    text = r.table()
    assert "polynomial degree 2" in text and "Crystal Ball tail exponent" in text and "FWHM" in text
    e = fit_toy(h, "Z")
    assert e.parameter_names == ("amplitude", "mean", "sigma", "alpha", "c0", "slope")
    assert "exponential background" in e.table()
    fwhm, err = e.fwhm
    assert 2 * e.resolution[0] < fwhm < 4 * e.resolution[0] + 2 * Z_GAMMA and 0 < err < 0.1 * fwhm


def test_fit_stability_with_the_cb_models():
    t = TOYS["Z"]
    rng = np.random.default_rng(4)
    lo, hi = t["hist"]
    k = rng.poisson(t["n_sig"])
    masses = t["mass"] + t["sigma"] * stats.crystalball.rvs(t["alpha"], t["n"], size=k, random_state=rng)
    masses = np.r_[masses + Z_GAMMA * rng.standard_cauchy(k), rng.uniform(lo, hi, 6000)]
    s = fit_stability(masses, fit_ranges=((70, 110), (75, 105)), bin_widths=(1.0,), models=CB_MODELS, cb_n=3.0,
                      natural_width=2 * Z_GAMMA, poly_degrees=(1, 2, 3))
    configs = sorted((r["model"], r["fit_range"], r["poly_degree"] or 0) for r in (*s.rows, *s.failed))
    assert len(configs) == 4  # one background per CB model, not one per polynomial degree
    assert {r["poly_degree"] for r in s.rows} <= {None, 2}
    assert " exp" in str(s)


def test_no_tail_in_the_data_is_a_loud_failure():
    """A Voigt peak with no tail (noise-free expected counts) leaves alpha free: fail, never report alpha +- 0."""
    edges = np.linspace(60.0, 120.0, 61)
    centers = 0.5 * (edges[1:] + edges[:-1])
    h = MassHistogram(20000 * special.voigt_profile(centers - 91.0, 1.4, Z_GAMMA) + 100.0, edges)
    for model in CB_MODELS:
        with pytest.raises(FitError, match=r"alpha.*not constrained by the data.*no radiative tail"):
            fit_mass_peak(h, model=model, cb_n=3.0)


# -- the pipeline -----------------------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def fsr_file(tmp_path_factory):
    from test_pipeline import write_z_file

    return write_z_file(tmp_path_factory.mktemp("cb") / "fsr.root", 3000, seed=3, fsr=0.3)


@pytest.mark.parametrize("model, background", [("cb_bw_exp", "exp"), ("cb_bw_poly2", "pol2")])
def test_analyze_with_a_cb_model(fsr_file, model, background, tmp_path):
    from test_pipeline import TRUE_MASS

    from cmsopen import analyze
    from cmsopen.pipeline import CHANNELS
    from cmsopen.plotting import layout_overlaps

    r = analyze(fsr_file, model=model, verbose=False, outdir=tmp_path)
    assert r.fit.model_name == model and r.alternate_fit.model_name == "voigt_poly"
    m, me = r.fit.peak_position
    assert abs(m - TRUE_MASS) < 3 * me  # the pole mass, not the radiatively shifted maximum
    assert r.stability.n_fits == 9 and {row["model"] for row in r.stability.rows} == {model}
    d = r.to_dict()
    cb_n = CHANNELS["Z_mumu"].cb_n
    assert d["fit"]["background"] == background and d["fit"]["cb_n"] == cb_n == d["channel"]["cb_n"]
    assert ("Fits (signal + background):" in r.summary()) is (background == "exp")
    note = next(t.get_text() for t in r.figures["mass_fit"].axes[0].texts if t.get_gid() == "annotation")
    assert f"BW$\\otimes$CB + {background} fit" in note and f"$n$ = {cb_n:g} (fixed)" in note and "\\alpha" in note
    assert "M_{\\mathrm{pole}}" in note and "m_{\\mathrm{peak}}" not in note
    assert layout_overlaps(r.figures["mass_fit"]) == []
    assert (tmp_path / "summary.json").exists()


def test_analyze_and_cli_report_a_missing_tail(tmp_path, capsys):
    from test_pipeline import write_z_file

    from cmsopen import AnalysisError, analyze
    from cmsopen.__main__ import main

    # A tail-free file: here alpha is left free (cb_bw_exp can still find a loose alpha in the fluctuations of a
    # small sample; the deterministic no-tail case is test_no_tail_in_the_data_is_a_loud_failure).
    plain = write_z_file(tmp_path / "plain.root", 3000, seed=3)
    with pytest.raises(AnalysisError, match="no radiative tail"):
        analyze(plain, model="cb_bw_poly2", verbose=False, stability=False)
    assert main(["analyze", str(plain), "--model", "cb_bw_poly2", "--quiet", "--no-stability"]) == 1
    assert "no radiative tail" in capsys.readouterr().err


def test_channel_config_cb_n():
    import dataclasses

    from cmsopen.pipeline import CHANNELS

    for cfg in CHANNELS.values():
        assert cfg.cb_n > 0
    with pytest.raises(ValueError, match="cb_n"):
        dataclasses.replace(CHANNELS["Z_mumu"], cb_n=0.0)


def test_fit_records_its_bounds():
    import dataclasses

    r = fit_toy(cb_toy(np.random.default_rng(12), "Z"), "Z")
    lower, upper = r.bounds
    assert len(lower) == len(upper) == len(r.values)
    assert lower[r.parameter_names.index("alpha")] == 0.1 and upper[r.parameter_names.index("alpha")] == 10.0
    assert lower[r.parameter_names.index("c0")] == 0.0  # the exponential stays positive
    assert r.on_bound == []
    stuck = dataclasses.replace(r, values=np.where(np.arange(len(r.values)) == 3, 10.0, r.values))
    assert stuck.on_bound == ["alpha"] and dataclasses.replace(r, bounds=None).on_bound == []


def test_registered_default_models_follow_the_model_choice_rule(tmp_path, capsys):
    """dev/model_choice.md: Amendment 1 set cb_n (Z 2, J/psi 100); Amendment 2 selected cb2_bw_exp and cb2_bw_poly2."""
    import dataclasses

    from test_pipeline import write_z_file

    from cmsopen import analyze
    from cmsopen.__main__ import build_parser
    from cmsopen.pipeline import CHANNELS

    assert (CHANNELS["Z_mumu"].model, CHANNELS["Z_mumu"].cb_n) == ("cb2_bw_exp", 2.0)
    assert (CHANNELS["Jpsi_mumu"].model, CHANNELS["Jpsi_mumu"].cb_n) == ("cb2_bw_poly2", 100.0)
    # a radiative tail and two resolutions, which the default mixture model describes
    f = write_z_file(tmp_path / "mix.root", 15000, seed=4, fsr=0.3, wide_fraction=0.5, wide_sigma=4.0)
    r = analyze(f, verbose=False, stability=False)  # no model given: the channel's default
    assert r.fit.model_name == "cb2_bw_exp" and r.alternate_fit.model_name == "voigt_poly"
    assert analyze(f, verbose=False, stability=False, model="gauss_poly").fit.model_name == "gauss_poly"
    with pytest.raises(ValueError, match="model must be one of"):
        dataclasses.replace(CHANNELS["Z_mumu"], model="breit_wigner")
    assert build_parser().parse_args(["analyze", "x.root"]).model is None
