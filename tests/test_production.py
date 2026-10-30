"""The production preflight and the single production run, on a TEMPORARY copy of the repository.

The copy carries a SYNTHETIC registry: four files of Z and J/psi events (synthetic_production.py), two labelled
record 31123 (Run2012B) and two 31129 (Run2012C), served from a temporary directory through file:// URLs, so the
download step uses the real fetch with its size and adler32 checks. No real production file is touched or named.
"""

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from synthetic_production import write_production_file

from cmsopen.datasets import adler32_of

REPO = Path(__file__).resolve().parents[1]
ENV_GIT = ["-c", "user.name=test", "-c", "user.email=test@example.org", "-c", "commit.gpgsign=false"]


def git(repo, *args):
    out = subprocess.run(["git", *ENV_GIT, *args], cwd=repo, capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return out.stdout


def make_copy(tmp: Path, n_events: int = 15_000) -> tuple[Path, Path]:
    """A clone of the repository with the current working tree and a synthetic registry, committed and clean.

    Each synthetic file has ``n_events`` Z events and as many J/psi events.
    """
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
            path = write_production_file(source / f"SYNTH-{record_id}-{j}.root", n_events, n_events, seed=seed)
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


FIGURES = {"README.md", "cutflow.png", "muon_eta.png", "muon_pt.png", "z_os_vs_ss.png", "z_peak_fit.pdf",
           "z_peak_fit.png", "z_peak_fit_caption.md", "jpsi_os_vs_ss.png", "jpsi_peak_fit.pdf", "jpsi_peak_fit.png",
           "jpsi_peak_fit_caption.md"}


def check_production_json(repo: Path, n_files: int = 4) -> dict:
    """Every Phase A field of results/production.json, for both channels; no file name anywhere."""
    text = (repo / "results" / "production.json").read_text()
    assert "SYNTH-" not in text
    data = json.loads(text)
    assert data["schema_version"] == 1 and data["sample"]["n_files"] == n_files
    assert set(data["channels"]) == {"Z_mumu", "Jpsi_mumu"}
    for name, c in data["channels"].items():
        r = c["result"]
        assert r["stat_error_scaled_gev"] == pytest.approx(r["stat_error_gev"] * r["scale_factor"]), name
        assert r["scale_factor"] >= 1 and c["fit_choice_spread_gev"] is not None, name
        assert c["t1"]["summary_json_byte_identical"] is True, name
        assert set(c["t6"]["periods"]) == {"2012B", "2012C"}, name
        assert "peak_position_gev_difference_2012B_minus_2012C" in c["t6"], name
        assert [step["step"] for step in c["cutflow"]] == list(range(len(c["cutflow"]))), name
        studies = {e["study"] for e in c["validation"]["entries"]}
        assert {"region", "phi(mu+)", "phi(mu-)", "pT(sublead)", "PV_npvsGood", "working point"} <= studies, name
        assert "systematics_summary" in c["validation"], name
        assert [row["file"] for row in c["per_file"]] == list(range(1, n_files + 1)), name
        assert all(row["status"] == "fitted" and row["chi2_ndf"] > 0 for row in c["per_file"]), name
    assert data["channels"]["Jpsi_mumu"]["result"]["model"] == "cb2_bw_poly2"
    t = data["targets"]
    assert set(t) == {f"T{k}" for k in range(1, 8)}
    assert all("benchmark" in v and "observed" in v and "met" in v for v in t.values())
    assert t["T1"]["met"] is True and t["T3"]["met"] is True and t["T6"]["met"] is True and t["T7"]["met"] is True
    assert t["T4"]["benchmark"] == {"n_files": 20, "by_record": {"31129": 12, "31123": 8}}
    assert t["T4"]["observed"]["by_record"] == {"31123": 2, "31129": 2} and t["T4"]["met"] is False  # 4 synthetic
    assert sorted(Path(f).name for f in data["figures"]) == sorted(FIGURES)
    return data


@pytest.mark.slow
@pytest.mark.timeout(1500)
def test_dry_run_of_the_production_path_and_the_single_run_guard(tmp_path, capsys):
    """Download (file://, same checks), analysis of both channels twice (T1, parallel vs serial), T6, per-file fits,
    figures (z_* and jpsi_*), production.json with the T1-T7 table; then the single-run guard."""
    repo, _ = make_copy(tmp_path)
    record_gates(repo)
    out = run(repo, "production_run.py", "--confirm-single-production-run", "--workers", "2")
    with capsys.disabled():
        print("\n" + out.stdout)
    assert out.returncode == 0, out.stdout + out.stderr
    assert "SYNTH-" not in out.stdout
    data = check_production_json(repo)
    assert len(list((repo / "data" / "production").glob("*.root"))) == 4
    assert {p.name for p in (repo / "docs" / "figures").iterdir()} == FIGURES
    for name in ("README.md", "jpsi_peak_fit_caption.md", "z_peak_fit_caption.md"):
        assert "SYNTH-" not in (repo / "docs" / "figures" / name).read_text()
    readme = (repo / "docs" / "figures" / "README.md").read_text()
    assert "pre-registered production sample" in readme and "`jpsi_peak_fit.png`" in readme
    sys.path.insert(0, str(repo / "scripts"))
    from render_results import render_results_block

    sys.path.pop(0)
    assert "Peak position" in render_results_block(data)
    changed = git(repo, "status", "--porcelain", "--untracked-files=all")
    with capsys.disabled():
        print("paths the production run created or modified (git status of the copy):\n" + changed)
    again = run(repo, "production_run.py", "--confirm-single-production-run")
    assert again.returncode == 3 and "REFUSED: single-run guard" in again.stdout


def test_sanitize_replaces_every_file_name_and_path(tmp_path):
    sys.path.insert(0, str(REPO / "scripts"))
    from production_run import sanitize

    sys.path.pop(0)
    files = [{"filename": "AAA.root", "record_id": 31129, "index": 3},
             {"filename": "BBB.root", "record_id": 31123, "index": 0}]
    paths = [tmp_path / "AAA.root", tmp_path / "BBB.root"]
    text = sanitize(f"cannot read {paths[0]} (chunk 2); BBB.root has no Events tree", paths, files)
    assert text == ("cannot read file 1/2 (record 31129, index 3) (chunk 2); file 2/2 (record 31123, index 0) has no "
                    "Events tree")
