"""Scaled statistical errors in the validation (dev/validation_plan.md, prompt 10 addendum)."""

import math
from types import SimpleNamespace

import pytest
from test_validation_model import single_resolution_pairs

import cmsopen.validation as validation
from cmsopen.pipeline import CHANNELS
from cmsopen.validation import _entry_from_fit, scale_factor

Z = CHANNELS["Z_mumu"]


def fake_fit(position, error, chi2_ndf):
    """The attributes of a FitResult that a validation entry reads."""
    return SimpleNamespace(peak_position=(position, error), resolution=(1.2, 0.02), chi2_ndf=chi2_ndf,
                           signal_yield=(1000.0, 30.0), yields_reliable=True, model_name="cb_bw_exp")


@pytest.mark.parametrize(("chi2_ndf", "expected"), [(0.25, 1.0), (0.999, 1.0), (1.0, 1.0), (2.25, 1.5), (4.0, 2.0),
                                                    (float("nan"), 1.0), (0.0, 1.0)])
def test_scale_factor_is_never_below_one(chi2_ndf, expected):
    assert scale_factor(chi2_ndf) == pytest.approx(expected, rel=1e-15)
    assert scale_factor(chi2_ndf) >= 1.0


def test_entries_keep_raw_values_and_use_scaled_errors_for_the_difference():
    inclusive = _entry_from_fit(fake_fit(91.0, 0.010, 4.0), "inclusive", "all pairs", 1000, None)
    assert (inclusive.scale_factor, inclusive.error, inclusive.error_scaled) == (2.0, 0.010, 0.020)
    good = _entry_from_fit(fake_fit(91.05, 0.030, 0.64), "region", "BB", 400, inclusive)  # chi2/ndf < 1: S = 1
    bad = _entry_from_fit(fake_fit(90.90, 0.030, 2.25), "region", "EE", 300, inclusive)  # S = 1.5
    assert (good.scale_factor, good.error, good.error_scaled) == (1.0, 0.030, 0.030)
    assert bad.scale_factor == 1.5 and bad.error == 0.030 and bad.error_scaled == pytest.approx(0.045)
    for e in (good, bad):
        delta = e.position - inclusive.position
        assert e.delta == pytest.approx(delta)
        assert e.delta_sigma == pytest.approx(delta / math.hypot(e.error, inclusive.error))  # raw, unchanged
        assert e.delta_sigma_scaled == pytest.approx(delta / math.hypot(e.error_scaled, inclusive.error_scaled))
        assert abs(e.delta_sigma_scaled) <= abs(e.delta_sigma)
    d = bad.to_dict()
    assert {"error", "delta_sigma", "scale_factor", "error_scaled", "delta_sigma_scaled"} <= set(d)


def test_the_summary_reports_raw_and_scaled_errors():
    v = validation.run_validation(Z, "cb_bw_poly2", single_resolution_pairs(), {}, validation_model="cb_bw_exp")
    s = v.summary
    fitted = [e for e in (v.inclusive, *v.entries) if e.fitted]
    assert fitted and all(e.error_scaled == pytest.approx(e.error * max(1.0, math.sqrt(e.chi2_ndf))) for e in fitted)
    # the headline offset: raw and scaled, scaled with the headline fit's own chi2/ndf
    headline = validation.fit_entry(single_resolution_pairs()["mass"], Z, "cb_bw_poly2", "inclusive", "all pairs")
    assert s.pdg_offset_error == pytest.approx(headline.error)
    assert s.pdg_offset_error_scaled == pytest.approx(headline.error * scale_factor(headline.chi2_ndf))
    assert s.pdg_offset_error_scaled >= s.pdg_offset_error
    text = v.table()
    assert "err x S" in text and "d/s scaled" in text and "scaled +-" in text


def test_charge_differences_carry_scaled_errors():
    entry = {}
    for name, (pos, err, chi2) in {"plus": (91.1, 0.02, 2.25), "minus": (90.9, 0.02, 0.5)}.items():
        entry[name] = _entry_from_fit(fake_fit(pos, err, chi2), f"phi(mu{'+' if name == 'plus' else '-'})",
                                      validation.PHI_LABELS[0], 6000, None)
    inclusive = _entry_from_fit(fake_fit(91.0, 0.01, 1.0), "inclusive", "all pairs", 30000, None)
    region = _entry_from_fit(fake_fit(91.0, 0.02, 1.0), "region", "BB", 9000, inclusive)
    s = validation.systematics_summary(Z, "cb_bw_exp", single_resolution_pairs()["mass"], inclusive,
                                       [region, entry["plus"], entry["minus"]])
    (d,) = s.charge_differences
    assert d["error"] == pytest.approx(math.hypot(0.02, 0.02))
    assert d["error_scaled"] == pytest.approx(math.hypot(0.03, 0.02))
    assert s.charge_weighted_mean == pytest.approx(0.2) and s.charge_weighted_mean_scaled == pytest.approx(0.2)
    assert s.charge_weighted_mean_error_scaled == pytest.approx(d["error_scaled"])
