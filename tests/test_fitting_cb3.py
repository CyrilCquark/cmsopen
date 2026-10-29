"""The three-resolution models cb3_bw_exp and cb3_bw_poly2 (dev/model_choice.md, Amendment 3)."""

import math

import numpy as np
import pytest
from scipy import integrate, stats
from test_pipeline import write_z_file

from cmsopen import AnalysisError, analyze
from cmsopen.__main__ import build_parser
from cmsopen.fitting import (
    CB_BW_THRESHOLD,
    MODELS,
    THREE_RES_MODELS,
    FitError,
    MassHistogram,
    _gl_points,
    crystalball2_bw,
    crystalball3_bw,
    crystalball_bw,
    fit_mass_peak,
    fit_stability,
    pdg_mass_width,
)
from cmsopen.pipeline import _ALTERNATE_MODEL

JPSI_GAMMA = 0.5 * pdg_mass_width("J/psi")[2]
Z_GAMMA = 0.5 * pdg_mass_width("Z")[2]

# J/psi-like toy truth: three resolutions sigma1 < r2 sigma1 < r2 s sigma1 with fractions f1, (1-f1) g, (1-f1)(1-g),
# a radiative tail and an exponential background. The cores are well separated so that a 150,000-event toy can
# identify them (closer cores, e.g. r2 1.6 and s 1.9 at 120,000 events, gave sigma1 pulls of width ~1.5 in a probe).
TRUTH = dict(mass=3.097, sigma1=0.018, r2=2.0, s=2.2, f1=0.4, g=0.6, alpha=1.5, n=3.0, slope=-2.0, n_sig=150_000,
             n_bkg=30_000, hist=(2.6, 3.6), bins=50, fit=(2.8, 3.4))
NAMES = ("mean", "sigma", "r2", "s", "f1", "g")
TRUE_VALUES = {"mean": TRUTH["mass"], "sigma": TRUTH["sigma1"], "r2": TRUTH["r2"], "s": TRUTH["s"], "f1": TRUTH["f1"],
               "g": TRUTH["g"]}


def toy(rng, **override):
    """Event-by-event toy, independent of cmsopen's model code (scipy.stats.crystalball, tail on the low side)."""
    t = {**TRUTH, **override}
    lo, hi = t["hist"]
    k = rng.poisson(t["n_sig"])
    u = rng.random(k)
    middle = u < t["f1"] + (1 - t["f1"]) * t["g"]
    width = np.where(u < t["f1"], t["sigma1"], np.where(middle, t["r2"] * t["sigma1"], t["r2"] * t["s"] * t["sigma1"]))
    sig = (t["mass"] + JPSI_GAMMA * rng.standard_cauchy(k)
           + width * stats.crystalball.rvs(t["alpha"], t["n"], size=k, random_state=rng))
    v = rng.random(rng.poisson(t["n_bkg"]))
    bkg = lo + np.log1p(v * np.expm1(t["slope"] * (hi - lo))) / t["slope"]
    counts, edges = np.histogram(np.r_[sig, bkg], bins=t["bins"], range=t["hist"])
    return MassHistogram(counts.astype(np.float64), edges)


def fit_toy(h, model="cb3_bw_exp"):
    return fit_mass_peak(h, model=model, fit_range=TRUTH["fit"], natural_width=2 * JPSI_GAMMA, cb_n=TRUTH["n"])


# -- the shape ----------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(("gamma", "mass", "sigma1", "edges"), [
    (JPSI_GAMMA, 3.097, 0.02, np.linspace(2.8, 3.4, 31)),  # J/psi: no convolution (Gamma << 0.05 sigma1)
    (Z_GAMMA, 91.0, 1.0, np.linspace(70.0, 110.0, 41)),  # Z: Breit-Wigner convolved
])
def test_third_weight_to_zero_reproduces_the_two_resolution_model(gamma, mass, sigma1, edges):
    x = np.linspace(edges[0], edges[-1], 401)
    kw = dict(n=3.0, gamma=gamma, norm_edges=edges)
    two = crystalball2_bw(x, 1000.0, mass, sigma1, 1.4, 2.0, 0.4, **kw)
    exact = crystalball3_bw(x, 1000.0, mass, sigma1, 1.4, 2.0, 2.5, 0.4, 1.0, **kw)
    np.testing.assert_allclose(exact, two, rtol=1e-6)
    near = crystalball3_bw(x, 1000.0, mass, sigma1, 1.4, 2.0, 2.5, 0.4, 1.0 - 1e-9, **kw)  # weight (1-f1)(1-g) -> 0
    np.testing.assert_allclose(near, two, rtol=1e-6, atol=1e-6 * two.max())


def test_mixture_is_the_weighted_sum_of_three_normalised_cores():
    edges = np.linspace(70.0, 110.0, 41)
    pts, wts = _gl_points(edges)
    kw = dict(n=2.0, gamma=Z_GAMMA, norm_edges=edges)
    mix = crystalball3_bw(pts, 500.0, 91.0, 0.8, 1.3, 1.7, 2.1, 0.3, 0.6, **kw)
    assert mix @ wts == pytest.approx(500.0, rel=1e-12)  # amplitude = signal events in the fit bins
    cores = [crystalball_bw(pts, 500.0, 91.0, w, 1.3, **kw) for w in (0.8, 1.7 * 0.8, 1.7 * 2.1 * 0.8)]
    np.testing.assert_allclose(mix, 0.3 * cores[0] + 0.7 * 0.6 * cores[1] + 0.7 * 0.4 * cores[2], rtol=1e-12)


def test_narrow_width_branch_is_decided_from_sigma1():
    edges = np.linspace(2.8, 3.4, 31)
    x = np.linspace(2.81, 3.39, 200)
    args = (x, 1.0, 3.097, 0.025, 1.5, 1.8, 2.0, 0.4, 0.6)
    assert 2 * JPSI_GAMMA < CB_BW_THRESHOLD * 0.025
    auto = crystalball3_bw(*args, n=3.0, gamma=JPSI_GAMMA, norm_edges=edges)
    np.testing.assert_array_equal(auto, crystalball3_bw(*args, n=3.0, gamma=JPSI_GAMMA, norm_edges=edges,
                                                         convolve=False))
    gamma = 0.5 * 0.06 * 0.025  # between 0.05 sigma1 and the wider cores: all three convolved
    auto = crystalball3_bw(*args, n=3.0, gamma=gamma, norm_edges=edges)
    np.testing.assert_array_equal(auto, crystalball3_bw(*args, n=3.0, gamma=gamma, norm_edges=edges, convolve=True))


# -- fits -----------------------------------------------------------------------------------------------------------


def test_identical_components_are_ineligible():
    """One resolution only: r2, s, f1 and g are not determined, so the fit fails (rule (a)/(b) of Amendment 3)."""
    h = toy(np.random.default_rng(2), f1=1.0)
    flagged = r"parameter\(s\) \[[^\]]*'(r2|s|f1|g)'[^\]]*\] (not constrained by the data|ended on a bound)"
    for model in THREE_RES_MODELS:
        with pytest.raises(FitError, match=flagged):
            fit_toy(h, model=model)


def test_toy_recovery_of_a_three_resolution_mixture(capsys):
    r = fit_toy(toy(np.random.default_rng(11)))
    for name in ("mean", "sigma"):
        value, error = r.parameters[name]
        assert abs(value - TRUE_VALUES[name]) < 3 * error, (name, value, error)
    with capsys.disabled():
        print("\n  cb3_bw_exp J/psi-like toy recovery (reported, not asserted): " + ", ".join(
            f"{k} {r.parameters[k][0]:.4g} +- {r.parameters[k][1]:.2g} (truth {TRUE_VALUES[k]:g})"
            for k in ("r2", "s", "f1", "g")))
    assert r.on_bound == [] and r.yields_reliable and r.background_label == "exp"
    assert r.parameter_names == ("amplitude", "mean", "sigma", "alpha", "r2", "s", "f1", "g", "c0", "slope")
    fwhm, fwhm_err = r.fwhm
    assert r.resolution == pytest.approx((fwhm / 2.3548200450309493, fwhm_err / 2.3548200450309493))


@pytest.mark.parametrize("model", THREE_RES_MODELS)
def test_reported_density_is_the_fitted_model(model):
    """The density behind the figures, FWHM and yields (crystalball3_bw) integrates to the counts the fit used."""
    r = fit_toy(toy(np.random.default_rng(12)), model=model)
    edges = np.r_[r.histogram.edges[:-1][r.fit_mask], r.histogram.edges[1:][r.fit_mask][-1:]]
    pts, wts = _gl_points(edges)
    integrals = (r.model(pts) * wts).reshape(edges.size - 1, -1).sum(axis=1)  # 5 Gauss-Legendre points per bin
    np.testing.assert_allclose(integrals, r.expected_counts(), rtol=1e-6)


@pytest.mark.slow
def test_pull_test_1000_toys(capsys):
    rng = np.random.default_rng(3020)
    pulls, failed = {k: [] for k in NAMES}, []
    for _ in range(1000):
        try:
            r = fit_toy(toy(rng))
        except FitError as exc:
            failed.append("on a bound" if "ended on a bound" in str(exc) else "not constrained"
                          if "not constrained" in str(exc) else "other")
            continue
        for k in NAMES:
            v, e = r.parameters[k]
            pulls[k].append((v - TRUE_VALUES[k]) / e)
    summary = {k: (float(np.mean(v)), float(np.std(v, ddof=1))) for k, v in pulls.items()}
    with capsys.disabled():
        breakdown = ", ".join(f"{failed.count(x)} {x}" for x in sorted(set(failed)))
        print(f"\n  cb3_bw_exp J/psi-like pull test, 1,000 toys, {len(failed)} failed fits ({breakdown or 'none'}): "
              + ", ".join(f"{k} mean {m:+.3f} std {s:.3f}" for k, (m, s) in summary.items()))
    # Only M and sigma1 are asserted; the failed-fit count and the other pulls are reported (prompt 10).
    for k in ("mean", "sigma"):
        m, s = summary[k]
        assert abs(m) < 0.2 and 0.8 < s < 1.2, (k, m, s)


@pytest.mark.parametrize("model", THREE_RES_MODELS)
def test_background_positive_and_covariance(model):
    r = fit_toy(toy(np.random.default_rng(5)), model=model)
    cov = r.covariance
    np.testing.assert_allclose(cov, cov.T, rtol=1e-10, atol=0)
    eig = np.linalg.eigvalsh(0.5 * (cov + cov.T))
    assert eig.min() >= -1e-12 * eig.max()
    assert r.yields_reliable
    if model == "cb3_bw_exp":
        assert np.all(r.background(np.linspace(*TRUTH["hist"], 2001)) > 0)
        assert r.background_yield[0] == pytest.approx(integrate.quad(r.background, *r.fit_range)[0], rel=1e-9)


@pytest.mark.parametrize("model", THREE_RES_MODELS)
@pytest.mark.parametrize("seed", [1, 2, 3])
def test_flat_noise_raises(model, seed):
    edges = np.linspace(60.0, 120.0, 61)
    flat = MassHistogram(np.random.default_rng(seed).poisson(50.0, 60).astype(float), edges)
    with pytest.raises(FitError):
        fit_mass_peak(flat, model=model, cb_n=2.0)


def test_unconstrained_check_covers_the_new_parameters(monkeypatch):
    """An error of ~0, or wider than half the allowed range, is not a measurement, for r2, s, f1 and g too."""
    import cmsopen.fitting as fitting

    h = toy(np.random.default_rng(7))
    good = fit_toy(h)
    real = fitting.optimize.curve_fit
    # r2 and s range 1.8, f1 0.85, g 0.9: errors above half of that, or ~0, are flagged
    for index, error in ((4, 1.0), (5, 1e-14), (6, 0.5), (7, 0.5)):

        def fake(*a, index=index, error=error, **k):
            values, cov = real(*a, **k)
            cov = cov.copy()
            cov[index, :] = cov[:, index] = 0.0
            cov[index, index] = error**2
            return values, cov

        monkeypatch.setattr(fitting.optimize, "curve_fit", fake)
        name = good.parameter_names[index]
        with pytest.raises(FitError, match=rf"\['{name}'\] not constrained by the data"):
            fit_toy(h)
    monkeypatch.setattr(fitting.optimize, "curve_fit", real)


def test_reporting_bounds_and_stability():
    h = toy(np.random.default_rng(8))
    r = fit_toy(h, model="cb3_bw_poly2")
    assert r.background_label == "pol2" and r.n_signal_parameters == 8 and r.cb_n == 3.0
    lower, upper = r.bounds
    assert [(lower[i], upper[i]) for i in range(4, 8)] == [(1.2, 3.0), (1.2, 3.0), (0.05, 0.90), (0.05, 0.95)]
    text = r.table()
    assert " r2 " in text and " f1 " in text and "FWHM" in text
    s = fit_stability(np.repeat(0.5 * (h.edges[1:] + h.edges[:-1]), h.counts.astype(int)), fit_ranges=((2.8, 3.4),),
                      bin_widths=(0.02,), models=THREE_RES_MODELS, hist_range=(2.6, 3.6),
                      natural_width=2 * JPSI_GAMMA, cb_n=3.0)
    assert sorted((row["model"], row["poly_degree"] or 0) for row in (*s.rows, *s.failed)) == [
        ("cb3_bw_exp", 0), ("cb3_bw_poly2", 2)]
    assert math.isfinite(s.mean)


def test_registered_in_models_the_cli_and_the_pipeline():
    assert set(THREE_RES_MODELS) <= set(MODELS)
    assert all(_ALTERNATE_MODEL[m] == "voigt_poly" for m in THREE_RES_MODELS)
    args = build_parser().parse_args(["analyze", "f.root", "--model", "cb3_bw_poly2"])
    assert args.model == "cb3_bw_poly2"


@pytest.mark.slow
def test_analyze_fits_cb3_or_reports_why_not(tmp_path):
    """The pipeline runs cb3; on a synthetic Z (natural width 2.5 GeV) with three injected resolutions the extra
    cores are not identifiable at this size, and the eligibility checks say so instead of returning a fit."""
    f = write_z_file(tmp_path / "three.root", 60_000, seed=6, fsr=0.3, wide_fraction=0.35, wide_sigma=2.5,
                     third_fraction=0.2, third_sigma=5.0)
    plain = write_z_file(tmp_path / "plain.root", 60_000, seed=6, fsr=0.3)
    wide = analyze(f, model="voigt_poly", verbose=False, stability=False).masses
    narrow = analyze(plain, model="voigt_poly", verbose=False, stability=False).masses
    in_window = (wide > 70) & (wide < 110)
    assert np.std(wide[in_window]) > np.std(narrow[(narrow > 70) & (narrow < 110)])  # the option widens the peak
    try:
        r = analyze(f, model="cb3_bw_exp", verbose=False, stability=False)
    except AnalysisError as exc:
        assert "cb3_bw_exp" in str(exc) and any(f"'{p}'" in str(exc) for p in ("r2", "s", "f1", "g"))
    else:
        assert r.fit.model_name == "cb3_bw_exp" and r.alternate_fit.model_name == "voigt_poly"


def test_figure_annotation_reports_the_three_cores():
    import cmsopen.plotting as plotting

    r = fit_toy(toy(np.random.default_rng(13)), model="cb3_bw_poly2")
    fig, axes = plotting.plot_mass_spectrum(r.histogram, r, resonance_label=r"J/\psi", pdg_mass=3.0969,
                                            natural_width=2 * JPSI_GAMMA)
    full = plotting._fit_annotation(r, r"J/\psi", 2 * JPSI_GAMMA)  # the unshortened text
    assert "3CB" in full and "$r_2$" in full and "$s$" in full and "$f_1$" in full and "$g$" in full
    shown = next(t for t in axes[0].texts if t.get_gid() == plotting._ANNOTATION_GID).get_text()
    # placed at 8 pt: if needed the weights and core widths are left out (they are in the summary and the caption)
    assert "3CB" in shown and "FWHM/2.355" in shown and "M_{\\mathrm{pole}}" in shown
    assert plotting.layout_overlaps(fig) == []
    sizes = [t.get_fontsize() for t in fig.findobj(lambda o: hasattr(o, "get_fontsize") and hasattr(o, "get_text"))
             if t.get_text()]
    assert min(sizes) >= plotting.MIN_FONT_SIZE
