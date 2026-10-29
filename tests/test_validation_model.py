"""The validation model (dev/validation_plan.md, prompt 8 addendum): scans and their reference vs the headline."""

import dataclasses

import numpy as np
import pytest
from test_pipeline import write_z_file

import cmsopen.validation as validation
from cmsopen import analyze
from cmsopen.fitting import pdg_mass_width
from cmsopen.pipeline import CHANNELS, ChannelConfig
from cmsopen.validation import fit_entry

Z = CHANNELS["Z_mumu"]


def single_resolution_pairs(n=12_000, sigma=1.2, seed=1):
    """Z-like pairs of ONE resolution (BW (x) Gaussian, a 10 % radiative tail, 5 % flat background), all barrel.

    Like a real barrel-only sub-sample: a single-resolution Crystal Ball describes it, while a resolution
    mixture has no second core to find (r or f ends on a bound or is not constrained).
    """
    rng = np.random.default_rng(seed)
    m = 91.1876 + 0.5 * 2.4952 * rng.standard_cauchy(n) + sigma * rng.standard_normal(n)
    tail = rng.random(n) < 0.1
    m[tail] -= rng.exponential(4.0, tail.sum())
    m = np.concatenate([m, rng.uniform(60.0, 120.0, n // 20)])
    k = len(m)
    return {"mass": m, "eta_plus": rng.uniform(-1.0, 1.0, k), "eta_minus": rng.uniform(-1.0, 1.0, k),
            "phi_plus": rng.uniform(-3.1, 3.1, k), "phi_minus": rng.uniform(-3.1, 3.1, k),
            "pt_sublead": rng.uniform(20.0, 60.0, k), "npv": rng.integers(0, 15, k).astype(float)}


@pytest.fixture(scope="module")
def pairs():
    return single_resolution_pairs()


def test_registered_channels_have_the_pre_registered_validation_models():
    assert (Z.model, Z.validation_model, Z.cb_n) == ("cb2_bw_exp", "cb_bw_exp", 2.0)
    j = CHANNELS["Jpsi_mumu"]
    assert (j.model, j.validation_model, j.cb_n) == ("cb2_bw_poly2", "cb_bw_poly2", 100.0)


def test_validation_model_is_left_out_of_the_config_dict():
    # outputs without validation must not depend on it (byte-identical to the code before the field existed)
    assert "validation_model" not in Z.to_dict()
    assert Z.to_dict() == dataclasses.replace(Z, validation_model=None).to_dict()


def test_invalid_validation_model_is_rejected():
    with pytest.raises(ValueError, match="validation_model"):
        dataclasses.replace(Z, validation_model="lorentz")
    with pytest.raises(ValueError, match="validation_model"):
        analyze("does-not-matter.root", validation=True, validation_model="lorentz", verbose=False)


def test_scans_and_their_reference_use_the_validation_model_and_the_offset_the_headline(pairs):
    # headline cb_bw_poly2, scans cb_bw_exp: two different models that both describe this sample
    v = validation.run_validation(Z, "cb_bw_poly2", pairs, {}, validation_model="cb_bw_exp")
    assert (v.model, v.headline_model) == ("cb_bw_exp", "cb_bw_poly2")
    assert v.inclusive.model == "cb_bw_exp" and all(e.model == "cb_bw_exp" for e in v.entries)
    reference = fit_entry(pairs["mass"], Z, "cb_bw_exp", "inclusive", "all pairs")
    headline = fit_entry(pairs["mass"], Z, "cb_bw_poly2", "inclusive", "all pairs")
    assert reference.fitted and headline.fitted
    assert v.inclusive.position == pytest.approx(reference.position, rel=1e-12)
    assert abs(headline.position - reference.position) > 1e-4  # so the checks below can tell them apart
    fitted = [e for e in v.entries if e.fitted]
    assert fitted and any(e.study == "region" and e.label == "BB" for e in fitted)
    for e in fitted:
        assert e.delta == pytest.approx(e.position - reference.position, rel=1e-12, abs=1e-12)
    s = v.summary
    assert (s.model, s.validation_model) == ("cb_bw_poly2", "cb_bw_exp")
    assert s.pdg_offset == pytest.approx(headline.position - pdg_mass_width("Z")[0], rel=1e-12)
    bv = s.background_variation
    assert bv["model"] == "cb_bw_exp" and bv["difference"] == pytest.approx(bv["position"] - headline.position)
    text = v.table()
    assert "fitted with the validation model cb_bw_exp, headline model cb_bw_poly2" in text
    assert "headline model cb_bw_poly2, validation scans cb_bw_exp" in text
    d = v.to_dict()
    assert (d["model"], d["headline_model"]) == ("cb_bw_exp", "cb_bw_poly2")
    assert {e["model"] for e in d["entries"]} == {"cb_bw_exp"}


@pytest.mark.slow
def test_a_single_resolution_subsample_fails_under_the_mixture_and_fits_under_the_validation_model(pairs):
    mixture = validation.run_validation(Z, "cb2_bw_exp", pairs, {})
    scans = validation.run_validation(Z, "cb2_bw_exp", pairs, {}, validation_model="cb_bw_exp")
    bb_mix = next(e for e in mixture.study("region") if e.label == "BB")
    bb = next(e for e in scans.study("region") if e.label == "BB")
    assert bb_mix.n_pairs == bb.n_pairs >= validation.MIN_PAIRS
    assert bb_mix.status == "failed" and bb_mix.model == "cb2_bw_exp"
    assert ("bound" in bb_mix.reason or "not constrained" in bb_mix.reason) and ("'r'" in bb_mix.reason
                                                                                 or "'f'" in bb_mix.reason)
    assert bb.status == "fitted" and bb.model == "cb_bw_exp"
    assert scans.inclusive.fitted and not mixture.inclusive.fitted
    assert sum(e.status == "failed" for e in scans.entries) < sum(e.status == "failed" for e in mixture.entries)


@pytest.mark.slow
def test_analyze_uses_the_channel_validation_model_unless_overridden(tmp_path):
    f = write_z_file(tmp_path / "vm.root", 30_000, seed=31, npv=True, medium_id=True)
    cfg: ChannelConfig = dataclasses.replace(Z, name="vm", model="voigt_poly", validation_model="gauss_poly")
    common = dict(config=cfg, validation=True, verbose=False, stability=False)
    r = analyze(f, **common)
    v = r.validation
    assert (v.model, v.headline_model, r.fit.model_name) == ("gauss_poly", "voigt_poly", "voigt_poly")
    assert v.inclusive.model == "gauss_poly" and {e.model for e in v.entries} == {"gauss_poly"}
    assert r.to_dict()["validation"]["headline_model"] == "voigt_poly"
    o = analyze(f, validation_model="voigt_poly", **common).validation
    assert o.model == "voigt_poly" and {e.model for e in o.entries} == {"voigt_poly"}
    plain = analyze(f, config=cfg, verbose=False, stability=False)
    assert plain.to_dict() == {k: x for k, x in r.to_dict().items() if k != "validation"}
