"""Tests for scripts/render_results.py and scripts/check_readme_numbers.py, using temporary files only."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
from render_results import BEGIN, END, render_results_block  # noqa: E402

sys.path.pop(0)

# Synthetic values for the tests only; they are not results.
PRODUCTION = {
    "schema_version": 1,
    "sample": {"n_files": 20, "n_events": 1234567, "n_pairs": 76543},
    "fit": {"model": "toy_model", "fit_range_gev": [70.0, 110.0], "peak_position_gev": 90.1234,
            "stat_error_gev": 0.0123, "resolution_gev": 1.5, "resolution_error_gev": 0.02, "chi2": 40.0, "ndf": 34},
    "pdg": {"mass_gev": 91.0, "source": "synthetic"},
    "fit_choice_spread_gev": 0.0456,
}


def check(tmp_path, readme_text=None, production=None):
    readme = tmp_path / "README.md"
    if readme_text is not None:
        readme.write_text(readme_text)
    prod = tmp_path / "production.json"
    if production is not None:
        prod.write_text(json.dumps(production))
    return subprocess.run([sys.executable, str(SCRIPTS / "check_readme_numbers.py"), "--readme", str(readme),
                           "--production", str(prod)], capture_output=True, text=True)


def readme_with(block):
    return f"# Project\n\nIntro with 3 numbers 1.2 outside the block.\n\n{BEGIN}\n{block}\n{END}\n\nMore text 42.\n"


def test_render_is_deterministic_and_uses_the_input():
    text = render_results_block(PRODUCTION)
    assert text == render_results_block(json.loads(json.dumps(PRODUCTION)))
    assert "20 files, 1,234,567 events, 76,543 opposite-sign pairs" in text
    assert "90.123 +- 0.012 (stat.) GeV" in text
    assert "-0.877 GeV" in text  # offset = 90.1234 - 91.0
    assert "0.046 GeV" in text and "40.0 / 34" in text
    no_spread = {k: v for k, v in PRODUCTION.items() if k != "fit_choice_spread_gev"}
    assert "Fit-choice spread" not in render_results_block(no_spread)


@pytest.mark.parametrize("broken", [{"schema_version": 2}, {k: v for k, v in PRODUCTION.items() if k != "fit"},
                                    {**PRODUCTION, "sample": {"n_files": 20}}])
def test_render_rejects_bad_schema(broken):
    data = {**PRODUCTION, **broken} if "schema_version" in broken and len(broken) == 1 else broken
    with pytest.raises(ValueError):
        render_results_block(data)


def test_no_markers_skips(tmp_path):
    out = check(tmp_path, "# Readme with numbers 91.2 but no block\n")
    assert out.returncode == 0 and out.stdout.strip() == "SKIP: README has no results block yet"


def test_block_without_production_must_have_no_digits(tmp_path):
    ok = check(tmp_path, readme_with("Results will appear after the production run."))
    assert ok.returncode == 0 and "OK" in ok.stdout
    bad = check(tmp_path, readme_with("Peak at 91.0 GeV"))
    assert bad.returncode == 1 and "digits" in bad.stdout


def test_block_must_equal_rendered_text(tmp_path):
    rendered = render_results_block(PRODUCTION)
    ok = check(tmp_path, readme_with(f"\n{rendered}\n"), PRODUCTION)
    assert ok.returncode == 0, ok.stdout
    edited = rendered.replace("90.123", "91.188")
    bad = check(tmp_path, readme_with(edited), PRODUCTION)
    assert bad.returncode == 1 and "differs" in bad.stdout and "91.188" in bad.stdout


@pytest.mark.parametrize("text", [f"{BEGIN}\nx\n", f"x\n{END}\n", f"{END}\nx\n{BEGIN}\n", f"{BEGIN}\n{BEGIN}\nx\n{END}\n"])
def test_malformed_markers_fail(tmp_path, text):
    out = check(tmp_path, text)
    assert out.returncode == 1 and "malformed" in out.stdout


def test_missing_readme_and_bad_production_fail(tmp_path):
    assert check(tmp_path).returncode == 1
    out = check(tmp_path, readme_with("x"), {"schema_version": 1})
    assert out.returncode == 1 and "cannot render" in out.stdout
