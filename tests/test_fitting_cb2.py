"""The resolution-mixture models cb2_bw_exp and cb2_bw_poly2 (dev/model_choice.md, Amendment 2)."""

import math

import numpy as np
import pytest
from scipy import integrate, stats

from cmsopen.fitting import (
    CB_BW_THRESHOLD,
    MIXTURE_MODELS,
    FitError,
    MassHistogram,
    _gl_points,
    crystalball2_bw,
    crystalball_bw,
    fit_mass_peak,
    fit_stability,
    pdg_mass_width,
)

Z_GAMMA = 0.5 * pdg_mass_width("Z")[2]
JPSI_GAMMA = 0.5 * pdg_mass_width("J/psi")[2]

# Toy truth: two resolutions (narrow sigma1, wide r * sigma1, narrow fraction f), a radiative tail, an exponential
# background. The Z-like widths are chosen so the two cores are separable under the Z's natural width.
TOYS = {
    "Z": dict(mass=91.0, sigma1=0.8, r=2.5, f=0.5, alpha=1.5, n=2.0, gamma=Z_GAMMA, slope=-0.04, n_sig=80000,
              n_bkg=8000, hist=(60.0, 120.0), bins=60, fit=(70.0, 110.0)),
    "Jpsi": dict(mass=3.097, sigma1=0.025, r=1.8, f=0.6, alpha=1.5, n=3.0, gamma=JPSI_GAMMA, slope=-2.0,
                 n_sig=30000, n_bkg=8000, hist=(2.6, 3.6), bins=50, fit=(2.8, 3.4)),
}


def mix_toy(rng, kind, **override):
    """Event-by-event toy, independent of cmsopen's model code (scipy.stats.crystalball, tail on the low side)."""
    t = {**TOYS[kind], **override}
    lo, hi = t["hist"]
    k = rng.poisson(t["n_sig"])
    width = np.where(rng.random(k) < t["f"], t["sigma1"], t["r"] * t["sigma1"])
    sig = (t["mass"] + t["gamma"] * rng.standard_cauchy(k)
           + width * stats.crystalball.rvs(t["alpha"], t["n"], size=k, random_state=rng))
    u = rng.random(rng.poisson(t["n_bkg"]))
    bkg = lo + np.log1p(u * np.expm1(t["slope"] * (hi - lo))) / t["slope"]
    counts, edges = np.histogram(np.r_[sig, bkg], bins=t["bins"], range=t["hist"])
    return MassHistogram(counts.astype(np.float64), edges)


def fit_toy(h, kind, model="cb2_bw_exp"):
    t = TOYS[kind]
    return fit_mass_peak(h, model=model, fit_range=t["fit"], natural_width=2 * t["gamma"], cb_n=t["n"])


# -- the shape ----------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("kind", ["Z", "Jpsi"])
def test_f_one_reproduces_the_single_resolution_model(kind):
    t = TOYS[kind]
    edges = np.linspace(*t["fit"], 41)
    x = np.linspace(edges[0], edges[-1], 501)
    kw = dict(n=t["n"], gamma=t["gamma"], norm_edges=edges)
    single = crystalball_bw(x, 1000.0, t["mass"], t["sigma1"], 1.4, **kw)
    mixture = crystalball2_bw(x, 1000.0, t["mass"], t["sigma1"], 1.4, 2.0, 1.0, **kw)
    np.testing.assert_allclose(mixture, single, rtol=1e-6)
    # and f = 1 - 1e-9 is continuous with it (the wide core contributes nothing)
    near = crystalball2_bw(x, 1000.0, t["mass"], t["sigma1"], 1.4, 2.0, 1.0 - 1e-9, **kw)
    np.testing.assert_allclose(near, single, rtol=0, atol=1e-6 * single.max())


def test_mixture_is_the_weighted_sum_of_two_normalised_cores():
    t = TOYS["Z"]
    edges = np.linspace(70.0, 110.0, 41)
    pts, wts = _gl_points(edges)
    kw = dict(n=2.0, gamma=Z_GAMMA, norm_edges=edges)
    mix = crystalball2_bw(pts, 500.0, 91.0, 0.9, 1.3, 2.2, 0.3, **kw)
    assert mix @ wts == pytest.approx(500.0, rel=1e-12)  # amplitude = signal events in the fit bins
    narrow = crystalball_bw(pts, 500.0, 91.0, 0.9, 1.3, **kw)
    wide = crystalball_bw(pts, 500.0, 91.0, 2.2 * 0.9, 1.3, **kw)
    np.testing.assert_allclose(mix, 0.3 * narrow + 0.7 * wide, rtol=1e-12)
    assert t["r"] > 1


def test_narrow_width_branch_is_decided_from_sigma1():
    # J/psi: the natural width is far below sigma1, so both cores are Crystal Balls without the Breit-Wigner.
    edges = np.linspace(2.8, 3.4, 31)
    x = np.linspace(2.81, 3.39, 200)
    assert 2 * JPSI_GAMMA < CB_BW_THRESHOLD * 0.025
    auto = crystalball2_bw(x, 1.0, 3.097, 0.025, 1.5, 1.8, 0.6, n=3.0, gamma=JPSI_GAMMA, norm_edges=edges)
    alone = crystalball2_bw(x, 1.0, 3.097, 0.025, 1.5, 1.8, 0.6, n=3.0, gamma=JPSI_GAMMA, norm_edges=edges,
                            convolve=False)
    np.testing.assert_array_equal(auto, alone)
    # a width between 0.05 sigma1 and 0.05 r sigma1: both cores are convolved (decided once, from sigma1)
    gamma = 0.5 * 0.06 * 0.025
    auto = crystalball2_bw(x, 1.0, 3.097, 0.025, 1.5, 1.8, 0.6, n=3.0, gamma=gamma, norm_edges=edges)
    conv = crystalball2_bw(x, 1.0, 3.097, 0.025, 1.5, 1.8, 0.6, n=3.0, gamma=gamma, norm_edges=edges, convolve=True)
    np.testing.assert_array_equal(auto, conv)


# -- fits -----------------------------------------------------------------------------------------------------------


def test_identical_resolutions_are_ineligible():
    """Two identical cores: r and f are not determined, so the fit fails (rule (a)/(b) of Amendment 2)."""
    h = mix_toy(np.random.default_rng(2), "Z", r=1.0, f=1.0)
    flagged = r"parameter\(s\) \[[^\]]*'(r|f)'[^\]]*\] (not constrained by the data|ended on a bound)"
    for model in MIXTURE_MODELS:
        with pytest.raises(FitError, match=flagged):
            fit_toy(h, "Z", model=model)


@pytest.mark.parametrize("kind", ["Z", "Jpsi"])
def test_toy_recovery_of_a_two_resolution_mixture(kind):
    t = TOYS[kind]
    r = fit_toy(mix_toy(np.random.default_rng(11), kind), kind)
    for name, truth in (("mean", t["mass"]), ("sigma", t["sigma1"]), ("f", t["f"]), ("r", t["r"])):
        value, error = r.parameters[name]
        assert abs(value - truth) < 3 * error, (name, value, error, truth)
    assert r.on_bound == [] and r.yields_reliable and r.background_label == "exp"
    fwhm, fwhm_err = r.fwhm
    assert r.resolution == pytest.approx((fwhm / 2.3548200450309493, fwhm_err / 2.3548200450309493))
    assert r.parameter_names == ("amplitude", "mean", "sigma", "alpha", "r", "f", "c0", "slope")


@pytest.mark.slow
@pytest.mark.parametrize("kind", ["Z", "Jpsi"])
def test_pull_test_1000_toys(kind, capsys):
    t = TOYS[kind]
    rng = np.random.default_rng(3012 if kind == "Z" else 3013)
    names = ("mean", "sigma", "f", "r")
    truth = {"mean": t["mass"], "sigma": t["sigma1"], "f": t["f"], "r": t["r"]}
    pulls, failed = {k: [] for k in names}, []
    for _ in range(1000):
        try:
            r = fit_toy(mix_toy(rng, kind), kind)
        except FitError as exc:
            failed.append("on a bound" if "ended on a bound" in str(exc) else "not constrained"
                          if "not constrained" in str(exc) else "other")
            continue
        for k in names:
            v, e = r.parameters[k]
            pulls[k].append((v - truth[k]) / e)
    stats_ = {k: (float(np.mean(v)), float(np.std(v, ddof=1))) for k, v in pulls.items()}
    with capsys.disabled():
        breakdown = ", ".join(f"{failed.count(r)} {r}" for r in sorted(set(failed)))
        print(f"\n  cb2_bw_exp {kind}-like pull test, 1,000 toys, {len(failed)} failed fits ({breakdown or 'none'}): "
              + ", ".join(f"{k} mean {m:+.3f} std {s:.3f}" for k, (m, s) in stats_.items()))
    # Failed fits (a mixture parameter on a bound or not constrained by a fluctuation, which Amendment 2 treats as
    # ineligible) are reported, not asserted: the user's decision after a first run exceeded a 2 % limit set here.
    for k in ("mean", "sigma"):
        m, s = stats_[k]
        assert abs(m) < 0.2 and 0.8 < s < 1.2, (k, m, s)


@pytest.mark.parametrize("kind", ["Z", "Jpsi"])
def test_background_positive_and_covariance(kind):
    t = TOYS[kind]
    for model in MIXTURE_MODELS:
        r = fit_toy(mix_toy(np.random.default_rng(5), kind), kind, model=model)
        cov = r.covariance
        np.testing.assert_allclose(cov, cov.T, rtol=1e-10, atol=0)
        eig = np.linalg.eigvalsh(0.5 * (cov + cov.T))
        assert eig.min() >= -1e-12 * eig.max()
        if model == "cb2_bw_exp":
            assert np.all(r.background(np.linspace(*t["hist"], 2001)) > 0) and r.yields_reliable
            assert r.background_yield[0] == pytest.approx(integrate.quad(r.background, *r.fit_range)[0], rel=1e-9)


@pytest.mark.parametrize("model", MIXTURE_MODELS)
@pytest.mark.parametrize("seed", [1, 2, 3])
def test_flat_noise_raises(model, seed):
    edges = np.linspace(60.0, 120.0, 61)
    flat = MassHistogram(np.random.default_rng(seed).poisson(50.0, 60).astype(float), edges)
    with pytest.raises(FitError):
        fit_mass_peak(flat, model=model, cb_n=2.0)


def test_unconstrained_check_covers_r_and_f(monkeypatch):
    """A curvature-based error of ~0, or wider than half the allowed range, is not a measurement, for r and f too."""
    import cmsopen.fitting as fitting

    h = mix_toy(np.random.default_rng(7), "Jpsi")
    good = fit_toy(h, "Jpsi")
    real = fitting.optimize.curve_fit
    for index, error in ((4, 2.0), (5, 1e-14), (5, 0.6)):  # r +- 2 (range 2.8), f +- ~0, f +- 0.6 (range 0.9)

        def fake(*a, index=index, error=error, **k):
            values, cov = real(*a, **k)
            cov = cov.copy()
            cov[index, :] = cov[:, index] = 0.0
            cov[index, index] = error**2
            return values, cov

        monkeypatch.setattr(fitting.optimize, "curve_fit", fake)
        name = good.parameter_names[index]
        with pytest.raises(FitError, match=rf"\['{name}'\] not constrained by the data"):
            fit_toy(h, "Jpsi")
    monkeypatch.setattr(fitting.optimize, "curve_fit", real)


def test_reporting_and_stability():
    h = mix_toy(np.random.default_rng(8), "Jpsi")
    r = fit_toy(h, "Jpsi", model="cb2_bw_poly2")
    assert r.background_label == "pol2" and r.n_signal_parameters == 6 and r.cb_n == 3.0
    lower, upper = r.bounds
    assert (lower[4], upper[4], lower[5], upper[5]) == (1.2, 4.0, 0.05, 0.95)
    text = r.table()
    assert " r " in text and " f " in text and "FWHM" in text
    s = fit_stability(np.repeat(0.5 * (h.edges[1:] + h.edges[:-1]), h.counts.astype(int)), fit_ranges=((2.8, 3.4),),
                      bin_widths=(0.02,), models=MIXTURE_MODELS, hist_range=(2.6, 3.6),
                      natural_width=2 * JPSI_GAMMA, cb_n=3.0)
    assert sorted((row["model"], row["poly_degree"] or 0) for row in (*s.rows, *s.failed)) == [
        ("cb2_bw_exp", 0), ("cb2_bw_poly2", 2)]
    assert math.isfinite(s.mean)
