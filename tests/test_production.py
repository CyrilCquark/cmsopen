"""The production preflight and the single production run, on a TEMPORARY copy of the repository.

The copy carries a SYNTHETIC registry: four files written with the synthetic writer, two labelled record 31123
(Run2012B) and two 31129 (Run2012C), served from a temporary directory through file:// URLs, so the download step
uses the real fetch with its size and adler32 checks. No real production file is touched or named.
"""

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from test_pipeline import write_z_file

from cmsopen.datasets import adler32_of

REPO = Path(__file__).resolve().parents[1]
ENV_GIT = ["-c", "user.name=test", "-c", "user.email=test@example.org", "-c", "commit.gpgsign=false"]


def git(repo, *args):
    out = subprocess.run(["git", *ENV_GIT, *args], cwd=repo, capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return out.stdout


def make_copy(tmp: Path, n_events: int = 15_000) -> tuple[Path, Path]:
    """A clone of the repository with the current working tree and a synthetic registry, committed and clean."""
    repo, source = tmp / "repo", tmp / "source"
    subprocess.run(["git", "clone", "-q", "--no-hardlinks", str(REPO), str(repo)], check=True)
    tracked = subprocess.run(["git", "ls-files", "-co", "--exclude-standard"], cwd=REPO, capture_output=True,
                             text=True, check=True).stdout.splitlines()
    for rel in tracked:  # the working tree as it is (so uncommitted changes are tested too)
        src = REPO / rel
        if src.is_file():
            (repo / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, repo / rel)
    source.mkdir()
    records = []
    for record_id, period, seeds in ((31129, "Run2012C", (101, 102)), (31123, "Run2012B", (103, 104))):
        selected = []
        for j, seed in enumerate(seeds, 1):
            path = write_z_file(source / f"SYNTH-{record_id}-{j}.root", n_events, seed=seed, fsr=0.3,
                                wide_fraction=0.5, wide_sigma=4.0, npv=True, medium_id=True, full_branches=True)
            selected.append({"j": j, "index": j - 1, "position": j - 1, "filename": path.name,
                             "https_url": path.as_uri(), "size_bytes": path.stat().st_size,
                             "checksum": f"adler32:{adler32_of(path)}"})
        records.append({"record_id": record_id, "run_period": period, "selected": selected})
    registry = {"schema_version": 1, "purpose": "synthetic (tests)", "records": records, "n_files_total": 4}
    reg = repo / "results" / "production_files.json"
    reg.write_text(json.dumps(registry, indent=2) + "\n")
    (repo / "dev" / "registry.sha256").write_text(
        f"{hashlib.sha256(reg.read_bytes()).hexdigest()}  results/production_files.json\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "synthetic registry (test)")
    return repo, source


def record_gates(repo: Path) -> None:
    """A recorded pass of the gates for the copy's HEAD (the tests do not rerun the full suite inside the copy)."""
    head = git(repo, "rev-parse", "HEAD").strip()
    (repo / "build" / "gates").mkdir(parents=True, exist_ok=True)
    (repo / "build" / "gates" / f"{head}.json").write_text(json.dumps(
        {"head": head, "pytest_rc": 0, "quality_rc": 0, "summary": "recorded by the test"}))


def run(repo: Path, script: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(repo / "scripts" / script), *args], cwd=repo, capture_output=True,
                          text=True)


@pytest.fixture(scope="module")
def copy(tmp_path_factory):
    return make_copy(tmp_path_factory.mktemp("production"))


@pytest.mark.slow
def test_preflight_passes_on_the_clean_copy_and_names_no_file(copy):
    repo, source = copy
    record_gates(repo)
    out = run(repo, "production_preflight.py")
    assert out.returncode == 0, out.stdout + out.stderr
    assert out.stdout.strip().splitlines()[-1] == "PREFLIGHT PASSED"
    assert "SYNTH-" not in out.stdout  # no production (here: synthetic) file name is printed
    assert "FAIL" not in out.stdout


@pytest.mark.slow
def test_preflight_fails_when_a_production_file_is_present_or_the_tree_is_dirty(copy):
    repo, source = copy
    record_gates(repo)
    shutil.copy(next(source.glob("*.root")), repo / "data" / "stray.root")
    stray = repo / "data" / next(source.glob("*.root")).name
    shutil.move(repo / "data" / "stray.root", stray)
    out = run(repo, "production_preflight.py")
    assert out.returncode == 1 and "FAIL: none of the production files exists locally" in out.stdout
    assert "SYNTH-" not in out.stdout
    stray.unlink()
    (repo / "notes.txt").write_text("dirty\n")
    out = run(repo, "production_preflight.py")
    assert out.returncode == 1 and "FAIL: git working tree is clean" in out.stdout
    (repo / "notes.txt").unlink()


@pytest.mark.slow
def test_the_production_command_requires_the_confirmation_flag(copy):
    repo, _ = copy
    out = run(repo, "production_run.py")
    assert out.returncode == 2 and "REFUSED" in out.stdout
    assert not (repo / "results" / "production.json").exists() and not (repo / "data" / "production").exists()


@pytest.mark.slow
def test_the_production_command_refuses_when_the_preflight_fails(copy):
    repo, _ = copy
    record_gates(repo)
    (repo / "notes.txt").write_text("dirty\n")
    out = run(repo, "production_run.py", "--confirm-single-production-run", "--channels", "Z_mumu")
    (repo / "notes.txt").unlink()
    assert out.returncode == 4 and "REFUSED: the preflight failed" in out.stdout
    assert not (repo / "results" / "production_run.lock").exists()


@pytest.mark.slow
@pytest.mark.timeout(1500)
def test_dry_run_of_the_production_path_and_the_single_run_guard(tmp_path, capsys):
    """Download (file://, same checks), figures, analysis twice (T1, parallel vs serial), T6, production.json."""
    repo, _ = make_copy(tmp_path)
    record_gates(repo)
    out = run(repo, "production_run.py", "--confirm-single-production-run", "--channels", "Z_mumu", "--workers",
              "2")
    with capsys.disabled():
        print("\n" + out.stdout)
    assert out.returncode == 0, out.stdout + out.stderr
    assert "SYNTH-" not in out.stdout
    data = json.loads((repo / "results" / "production.json").read_text())
    z = data["channels"]["Z_mumu"]
    assert z["t1"]["summary_json_byte_identical"] is True
    t6 = z["t6"]
    assert set(t6["periods"]) == {"2012B", "2012C"} and "peak_position_gev_difference_2012B_minus_2012C" in t6
    assert data["sample"]["n_files"] == 4 and data["schema_version"] == 1
    assert "SYNTH-" not in (repo / "results" / "production.json").read_text()
    assert len(list((repo / "data" / "production").glob("*.root"))) == 4
    readme = (repo / "docs" / "figures" / "README.md").read_text()
    assert "SYNTH-" not in readme and "pre-registered production sample" in readme
    sys.path.insert(0, str(repo / "scripts"))
    from render_results import render_results_block

    sys.path.pop(0)
    assert "Peak position" in render_results_block(data)
    changed = git(repo, "status", "--porcelain", "--untracked-files=all")
    with capsys.disabled():
        print("paths the production run created or modified (git status of the copy):\n" + changed)
    again = run(repo, "production_run.py", "--confirm-single-production-run", "--channels", "Z_mumu")
    assert again.returncode == 3 and "REFUSED: single-run guard" in again.stdout
