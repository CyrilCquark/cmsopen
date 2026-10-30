"""scripts/check_package.py: the sdist and wheel build, pass twine, contain what they should, and install."""

import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_package.py"


@pytest.mark.slow
def test_package_builds_installs_and_runs(tmp_path):
    out = subprocess.run([sys.executable, str(SCRIPT), "--offline"], cwd=tmp_path, capture_output=True, text=True)
    assert out.returncode == 0, out.stdout + out.stderr
    assert out.stdout.strip().splitlines()[-1] == "OK: package checks pass"
    assert "FAIL" not in out.stdout
