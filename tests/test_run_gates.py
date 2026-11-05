"""scripts/run_gates.py: the record holds every gate, and any failed gate fails the run."""

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "run_gates.py"


def run_main(monkeypatch, tmp_path, failing: str | None):
    """run_gates.main() with every subprocess faked; the command containing ``failing`` exits 1."""
    spec = importlib.util.spec_from_file_location("run_gates", SCRIPT)
    gates = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gates)
    commands = []

    def fake_run(cmd, **_):
        commands.append(" ".join(cmd))
        stdout = "" if cmd[0] == "git" and "status" in cmd else "1 passed"
        return subprocess.CompletedProcess(cmd, 1 if failing and failing in " ".join(cmd) else 0, stdout, "")

    monkeypatch.setattr(gates.subprocess, "run", fake_run)
    monkeypatch.setattr(gates, "REPO", tmp_path)
    return gates.main(), commands, tmp_path


def test_all_gates_run_and_are_recorded(monkeypatch, tmp_path):
    rc, commands, repo = run_main(monkeypatch, tmp_path, None)
    assert rc == 0
    for needed in ("pytest", "check_quality", "check_notebooks", "check_release_metadata", "mkdocs build --strict",
                   "check_package"):
        assert any(needed in c for c in commands), needed
    assert not any("--release" in c for c in commands)
    record = json.loads(next((repo / "build" / "gates").glob("*.json")).read_text())
    assert record["release_rc"] == {"check_notebooks": 0, "check_release_metadata": 0, "mkdocs_strict": 0,
                                    "check_package": 0}


@pytest.mark.parametrize("failing", ["pytest", "check_quality", "check_notebooks", "check_release_metadata", "mkdocs",
                                     "check_package"])
def test_any_failed_gate_fails_the_run(monkeypatch, tmp_path, failing):
    assert run_main(monkeypatch, tmp_path, failing)[0] == 1
