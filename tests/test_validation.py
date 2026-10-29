"""Layer 6b validation (cmsopen.validation): categories, bins, the 5,000-pair rule, injected shifts, the summary."""

import dataclasses
import json
import math

import numpy as np
import pytest
from test_pipeline import TRUE_MASS, write_z_file

import cmsopen.validation as validation
from cmsopen import AnalysisError, analyze
from cmsopen.__main__ import main
from cmsopen.pipeline import CHANNELS
from cmsopen.validation import (
    MIN_PAIRS,
    PHI_EDGES,
    PILEUP_EDGES,
    PT_EDGES,
    WORKING_POINTS,
    bin_index,
    classify_regions,
    fit_entry,
)

Z = CHANNELS["Z_mumu"]
REGION_SHIFT = (0.0, 0.3, 0.8)  # GeV added to BB, BE, EE pairs
PHI_SHIFT = (0.0, 0.25, 0.0, -0.25)  # GeV added by mu+ phi quarter
PARTITIONS = ("region", "phi(mu+)", "phi(mu-)", "eta(mu+)", "eta(mu-)", "pT(sublead)", "PV_npvsGood")


def run(path, **kw):
    # Synthetic peaks are Voigt-shaped with no radiative tail: the Voigt model describes them, so it is both the
    # primary model and the validation model here (the registered channel's validation model is cb_bw_exp).
    return analyze(path, model="voigt_poly", validation_model="voigt_poly", validation=True, verbose=False,
                   stability=False, **kw)


@pytest.fixture(scope="module")
def region_file(tmp_path_factory):
    return write_z_file(tmp_path_factory.mktemp("val") / "regions.root", 120_000, seed=21, y_max=1.9,
                        region_shift=REGION_SHIFT, npv=True, medium_id=True)


@pytest.fixture(scope="module")
def charge_file(tmp_path_factory):
    return write_z_file(tmp_path_factory.mktemp("val") / "charge.root", 60_000, seed=22, plus_phi_shift=PHI_SHIFT,
                        npv=True, medium_id=True)


@pytest.fixture(scope="module")
def region_result(region_file):
    return run(region_file)


@pytest.fixture(scope="module")
def charge_result(charge_file):
    return run(charge_file)


# -- classification ------------------------------------------------------------------------------------------------


def test_region_boundaries():
    eta_a = [0.0, 1.1999, 1.2, -1.2, 2.4, -2.4, 0.5, -1.5]
    eta_b = [0.0, -1.1999, 0.3, 1.2, 1.0, -2.0, -1.3, 0.1]
    assert list(classify_regions(eta_a, eta_b)) == ["BB", "BB", "BE", "EE", "BE", "EE", "BE", "BE"]
    for bad in ([2.4001], [np.nan]):
        with pytest.raises(ValueError, match="eta"):
            classify_regions(bad, [0.0])


def test_bin_boundaries():
    assert list(bin_index([-math.pi, -math.pi / 2, -1e-12, 0.0, math.pi / 2, math.pi], PHI_EDGES)) == [0, 1, 1, 2, 3, 3]
    eta = [-2.4, -0.8, -0.8001, 0.8, 0.7999, 2.4, 2.41]
    assert list(bin_index(eta, validation.ETA_EDGES)) == [0, 1, 0, 2, 1, 2, -1]
    assert list(bin_index([19.99, 20.0, 29.99, 30.0, 50.0, 1e6], PT_EDGES["Z_mumu"])) == [-1, 0, 0, 1, 3, 3]
    assert list(bin_index([2.99, 3.0, 4.0, 6.0, 10.0], PT_EDGES["Jpsi_mumu"])) == [-1, 0, 1, 2, 3]
    assert list(bin_index([0, 14, 15, 22, 23, 80, -1], PILEUP_EDGES)) == [0, 0, 1, 1, 2, 2, -1]


def test_pre_registered_constants():
    assert MIN_PAIRS == 5000
    assert (validation.BARREL_MAX_ETA, validation.ENDCAP_MAX_ETA) == (1.2, 2.4)
    assert WORKING_POINTS == (("medium", 0.08), ("medium", 0.12), ("medium", 0.2), ("tight", 0.08),
                              ("tight", 0.12), ("tight", 0.2))
    assert PT_EDGES["Z_mumu"] == (20.0, 30.0, 40.0, 50.0, math.inf)
    assert PT_EDGES["Jpsi_mumu"] == (3.0, 4.0, 6.0, 10.0, math.inf)
    cuts = validation.working_point_cuts(Z.muon_cuts, "medium", 0.2)
    assert cuts["quality_id"] == "medium" and cuts["max_rel_iso"] == 0.2 and cuts["min_pt"] == Z.muon_cuts["min_pt"]


# -- the 5,000-pair rule -------------------------------------------------------------------------------------------


def test_insufficient_entries_are_not_fitted(monkeypatch):
    calls = []
    real = validation.fit_mass_peak
    monkeypatch.setattr(validation, "fit_mass_peak", lambda *a, **k: calls.append(1) or real(*a, **k))
    rng = np.random.default_rng(3)
    masses = np.r_[TRUE_MASS + 1.5 * rng.standard_normal(MIN_PAIRS - 1), [65.0] * 300]  # 4,999 in 70-110 GeV
    e = fit_entry(masses, Z, "voigt_poly", "test", "small")
    assert e.status == "insufficient" and e.n_pairs == MIN_PAIRS - 1 and not calls
    assert e.status_text == "insufficient statistics (n = 4,999)" and e.position is None
    e = fit_entry(np.r_[masses, [TRUE_MASS]], Z, "voigt_poly", "test", "enough")
    assert e.n_pairs == MIN_PAIRS and calls and e.status in ("fitted", "failed")


def test_failed_fit_is_reported_not_retried(monkeypatch):
    def fail(*a, **k):
        raise validation.FitError("no peak")

    monkeypatch.setattr(validation, "fit_mass_peak", fail)
    e = fit_entry(np.full(6000, 90.0), Z, "voigt_poly", "test", "x")
    assert e.status == "failed" and e.status_text == "fit failed: no peak" and not e.fitted


# -- synthetic data with injected shifts ---------------------------------------------------------------------------


@pytest.mark.slow
def test_categories_partition_all_pairs(region_result, charge_result):
    for result in (region_result, charge_result):
        v = result.validation
        assert v.inclusive.n_pairs == result.fit.n_entries
        for study in PARTITIONS:
            entries = v.study(study)
            assert entries, study
            assert sum(e.n_pairs for e in entries) == v.inclusive.n_pairs, study
        assert len(v.study("working point")) == 6


@pytest.mark.slow
def test_injected_region_shifts_are_recovered(region_result):
    v = region_result.validation
    fitted = {e.label: e for e in v.study("region")}
    assert all(e.fitted for e in fitted.values()), {k: e.status_text for k, e in fitted.items()}
    for label, shift in zip(("BB", "BE", "EE"), REGION_SHIFT, strict=True):
        e = fitted[label]
        assert abs(e.position - (TRUE_MASS + shift)) < 3 * e.error, (label, e.position, e.error)


@pytest.mark.slow
def test_injected_charge_shifts_are_recovered(charge_result):
    v = charge_result.validation
    plus, minus = v.study("phi(mu+)"), v.study("phi(mu-)")
    for k in range(4):
        assert plus[k].fitted and minus[k].fitted
        # mu+ in quarter k carries shift k; the muons are back to back, so the mu- in quarter k has its mu+ in k+2
        assert abs(plus[k].position - (TRUE_MASS + PHI_SHIFT[k])) < 3 * plus[k].error, k
        assert abs(minus[k].position - (TRUE_MASS + PHI_SHIFT[(k + 2) % 4])) < 3 * minus[k].error, k


@pytest.mark.slow
def test_systematics_summary_on_synthetic_data(region_result, charge_result):
    s = region_result.validation.summary
    assert [m["model"] for m in s.models] == ["voigt_poly", "cb_bw_exp", "cb_bw_poly2", "cb2_bw_exp", "cb2_bw_poly2"]
    assert all(isinstance(m["eligible"], bool) for m in s.models)
    assert len(s.fit_choice_rows) + len(s.fit_choice_failed) == 9
    expected = REGION_SHIFT[2] - REGION_SHIFT[0]
    errs = [e.error for e in region_result.validation.study("region")]
    assert abs(s.category_spread - expected) < 3 * math.hypot(errs[0], errs[2])
    assert s.pdg_offset is not None and s.pdg_offset_error > 0
    c = charge_result.validation.summary
    phi = {d["bin"]: d for d in c.charge_differences if d["binning"] == "phi"}
    for k, label in enumerate(validation.PHI_LABELS):
        want = PHI_SHIFT[k] - PHI_SHIFT[(k + 2) % 4]
        assert abs(phi[label]["difference"] - want) < 3 * phi[label]["error"], label
    assert c.charge_max_difference == pytest.approx(max(abs(d["difference"]) for d in c.charge_differences))
    text = c.table()
    assert "no targets" in text and "mu+ minus mu-" in text and "working points" in text
    json.dumps(region_result.validation.to_dict(), allow_nan=False)
    assert "insufficient statistics" in region_result.validation.table()  # the pT tails of the toy are small


# -- integration -----------------------------------------------------------------------------------------------------


@pytest.mark.slow
def test_parallel_equals_serial_with_validation(charge_file):
    serial = run(charge_file, chunk_size=7000)
    parallel = run(charge_file, chunk_size=7000, n_workers=2)
    assert json.dumps(serial.to_dict(), sort_keys=True) == json.dumps(parallel.to_dict(), sort_keys=True)
    assert serial.summary() == parallel.summary()


@pytest.mark.slow
def test_validation_off_is_the_old_behaviour(charge_file, charge_result, tmp_path):
    off = analyze(charge_file, model="voigt_poly", verbose=False, stability=False)
    assert off.validation is None and "validation" not in off.to_dict()
    on = {k: v for k, v in charge_result.to_dict().items() if k != "validation"}
    assert json.dumps(off.to_dict(), sort_keys=True) == json.dumps(on, sort_keys=True)
    assert charge_result.summary().startswith(off.summary() + "\n\nValidation (")
    # the per-pair information follows the masses exactly
    pairs = charge_result.validation
    assert pairs.inclusive.n_pairs == off.fit.n_entries


@pytest.mark.slow
def test_cli_validation_flag(charge_file, tmp_path):
    assert main(["analyze", str(charge_file), "--model", "voigt_poly", "--no-stability", "--quiet", "--validation",
                 "--validation-model", "voigt_poly", "--outdir", str(tmp_path)]) == 0
    assert "Systematics summary" in (tmp_path / "summary.txt").read_text()
    assert "validation" in json.loads((tmp_path / "summary.json").read_text())


def test_missing_pileup_branch_is_an_analysis_error(tmp_path):
    f = write_z_file(tmp_path / "nopv.root", 300, seed=2)
    with pytest.raises(AnalysisError, match="PV_npvsGood"):
        run(f)


def test_run_validation_checks_its_inputs():
    with pytest.raises(ValueError, match="lacks"):
        validation.run_validation(Z, "voigt_poly", {"mass": np.zeros(3)}, {})


def test_channel_without_pt_edges_has_no_pt_study():
    rng = np.random.default_rng(1)
    n = 2000
    pairs = {"mass": TRUE_MASS + 1.5 * rng.standard_normal(n), "eta_plus": rng.uniform(-2, 2, n),
             "eta_minus": rng.uniform(-2, 2, n), "phi_plus": rng.uniform(-3, 3, n), "phi_minus": rng.uniform(-3, 3, n),
             "pt_sublead": rng.uniform(20, 60, n), "npv": rng.integers(0, 30, n).astype(float)}
    cfg = dataclasses.replace(Z, name="custom", model="voigt_poly")
    v = validation.run_validation(cfg, "voigt_poly", pairs, {})
    assert not v.study("pT(sublead)") and v.inclusive.status == "insufficient"
    assert all(e.status == "insufficient" for e in v.entries)
    s = v.summary
    assert s.pdg_offset is None and s.category_spread is None and s.charge_weighted_mean is None
    assert "none (no bin has both charges fitted)" in s.table()
