"""The production preflight and the single production run, on a TEMPORARY copy of the repository.

The copy carries a SYNTHETIC registry: four files of Z and J/psi events (synthetic_production.py), two labelled
record 31123 (Run2012B) and two 31129 (Run2012C), served from a temporary directory through file:// URLs, so the
download step uses the real fetch with its size and adler32 checks. No real production file is touched or named.
"""

import hashlib
import json
import os
import re
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


def clone_working_tree(repo: Path) -> None:
    """A clone of the repository with the current working tree on top (so uncommitted changes are tested too)."""
    subprocess.run(["git", "clone", "-q", "--no-hardlinks", str(REPO), str(repo)], check=True)
    tracked = subprocess.run(["git", "ls-files", "-co", "--exclude-standard"], cwd=REPO, capture_output=True,
                             text=True, check=True).stdout.splitlines()
    for rel in tracked:
        src = REPO / rel
        if src.is_file():
            (repo / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, repo / rel)


def restore_pre_production(repo: Path) -> None:
    """Put the copy in the state before a production run, also when the repository itself is past that state.

    These tests rehearse a production run, which needs the single-run guard and the docs-freeze check to pass. Once
    the real results and generated documentation are committed, a plain clone would fail both for that reason alone.
    """
    freeze = re.search(r"Frozen at commit `([0-9a-f]{40})`", (repo / "dev" / "model_choice.md").read_text()).group(1)
    for name in ("results/production.json", "results/production_run.lock", "results/production_run.log",
                 "CITATION.cff", ".zenodo.json", "README_PYPI.md", "results/production_extras.json"):
        (repo / name).unlink(missing_ok=True)
    for name in ("docs", "notebooks"):
        shutil.rmtree(repo / name, ignore_errors=True)
    paths = git(repo, "ls-tree", "-r", "--name-only", freeze, "--", "README.md", "DATA.md", "LICENSE", "docs",
                "notebooks")
    git(repo, "checkout", "-q", freeze, "--", *paths.split("\n")[:-1])


def make_copy(tmp: Path, n_events: int = 15_000) -> tuple[Path, Path]:
    """A clone of the repository with the current working tree and a synthetic registry, committed and clean.

    Each synthetic file has ``n_events`` Z events and as many J/psi events.
    """
    repo, source = tmp / "repo", tmp / "source"
    clone_working_tree(repo)
    restore_pre_production(repo)
    source.mkdir()
    records = []
    for record_id, period, seeds in ((31129, "Run2012C", (101, 102)), (31123, "Run2012B", (103, 104))):
        selected = []
        for j, seed in enumerate(seeds, 1):
            path = write_production_file(source / f"SYNTH-{record_id}-{j}.root", n_events, n_events, seed=seed)
            selected.append({"j": j, "index": j - 1, "position": j - 1, "filename": path.name,
                             "https_url": path.as_uri(), "size_bytes": path.stat().st_size,
                             "checksum": f"adler32:{adler32_of(path)}"})
        records.append({"record_id": record_id, "run_period": period, "selected": selected,
                        "title": f"synthetic {period}", "record_url": f"https://opendata.cern.ch/record/{record_id}"})
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


def arm_test_hook(repo: Path) -> Path:
    """Mark ``repo`` as a temporary test copy (ignored by git there), so production_run.py honours the injection."""
    with open(repo / ".git" / "info" / "exclude", "a") as f:
        f.write("scripts/.production_test_copy\n")
    marker = repo / "scripts" / ".production_test_copy"
    marker.write_text(str(repo.resolve()) + "\n")
    return marker


def run(repo: Path, script: str, *args: str, inject: str | None = None) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k != "CMSOPEN_PRODUCTION_INJECT"}
    env["PYTHONPATH"] = str(repo / "src")  # the copy's code, as the preflight requires (not the editable install's)
    env["PYTHONDONTWRITEBYTECODE"] = "1"  # a same-size edit within one second must not run from stale bytecode
    if inject:
        env["CMSOPEN_PRODUCTION_INJECT"] = inject  # a test hook of production_run.py: "raise:<phase>", "kill:<phase>"
    return subprocess.run([sys.executable, str(repo / "scripts" / script), *args], cwd=repo, capture_output=True,
                          text=True, env=env)


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
    report = run(repo, "production_report.py")
    with capsys.disabled():
        print(report.stdout)
    assert report.returncode == 0 and "SYNTH-" not in report.stdout and ".root" not in report.stdout
    for heading in ("== Run", "== Targets T1-T7", "== Z_mumu: headline fit", "== Jpsi_mumu: headline fit",
                    "== Jpsi_mumu: per-run consistency (T6)", "== Z_mumu: validation", "== Jpsi_mumu: per-file fits",
                    "== Z_mumu: cutflow", "== Timings", "events with muons"):
        assert heading in report.stdout, heading
    assert "T4: NOT MET" in report.stdout and "T1: met" in report.stdout and "attempts: 1" in report.stdout
    assert run(repo, "production_report.py", str(repo / "missing.json")).returncode == 1
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


# -- crash and resume (Phase B of prompt 12): one copy, the Z channel only, the steps in order ---------------------

Z_ONLY = ("--confirm-single-production-run", "--channels", "Z_mumu", "--workers", "2", "--retry-backoff", "0.01")


def show(capsys, title, out):
    with capsys.disabled():
        print(f"\n--- {title} (exit {out.returncode})\n{out.stdout.strip()}")


def events(repo):
    return [json.loads(line) for line in (repo / "results" / "production_run.log").read_text().splitlines()]


@pytest.fixture(scope="module")
def resume(tmp_path_factory):
    """A copy whose download directory already holds a truncated file and a corrupted file of the registry."""
    repo, source = make_copy(tmp_path_factory.mktemp("resume"))
    record_gates(repo)
    arm_test_hook(repo)
    sources = sorted(source.glob("SYNTH-*.root"))
    (repo / "data" / "production").mkdir(parents=True)
    data = sources[0].read_bytes()
    (repo / "data" / "production" / sources[0].name).write_bytes(data[: len(data) // 3])  # truncated
    data = bytearray(sources[1].read_bytes())
    data[1000] ^= 0xFF
    (repo / "data" / "production" / sources[1].name).write_bytes(bytes(data))  # same size, corrupted
    return repo, source


@pytest.mark.slow
def test_resume_1_truncated_and_corrupted_downloads_are_refetched_then_an_injected_exception_after_the_lock(
        resume, capsys):
    repo, source = resume
    out = run(repo, "production_run.py", *Z_ONLY, inject="raise:lock")
    show(capsys, "attempt 1: truncated and corrupted files present; an exception injected after the lock", out)
    assert out.returncode == 6 and "FAIL: the production analysis failed in phase 'lock': RuntimeError" in out.stdout
    assert "run state: not started" in out.stdout and "SYNTH-" not in out.stdout
    for f in source.glob("SYNTH-*.root"):  # both bad copies were replaced by verified ones
        assert (repo / "data" / "production" / f.name).read_bytes() == f.read_bytes()
    assert (repo / "results" / "production_run.lock").exists() and not (repo / "results" / "production.json").exists()
    end = events(repo)[-1]
    assert (end["event"], end["attempt"], end["status"], end["phase"], end["exception"]) == (
        "attempt_end", 1, "failed", "lock", "RuntimeError")
    assert git(repo, "status", "--porcelain").splitlines() == ["?? results/production_run.lock",
                                                               "?? results/production_run.log"]


@pytest.mark.slow
def test_resume_2_a_dirty_tree_is_refused(resume, capsys):
    repo, _ = resume
    n = len(events(repo))
    (repo / "notes.txt").write_text("dirty\n")
    out = run(repo, "production_run.py", *Z_ONLY)
    show(capsys, "resume with an untracked file", out)
    (repo / "notes.txt").unlink()
    assert out.returncode == 8 and "REFUSED: resuming needs a clean working tree" in out.stdout
    assert "run state: analysis started" in out.stdout and len(events(repo)) == n  # no attempt started


@pytest.mark.slow
def test_resume_3_a_changed_head_needs_a_reason_and_may_not_change_the_analysis(resume, capsys):
    repo, _ = resume
    with open(repo / "dev" / "production_runbook.md", "a") as f:
        f.write("\n<!-- a code fix (test) -->\n")
    git(repo, "commit", "-qam", "a code fix (test)")
    record_gates(repo)
    out = run(repo, "production_run.py", *Z_ONLY)
    show(capsys, "resume after a new commit, without --code-fix-reason", out)
    assert out.returncode == 8 and "differs from the lock's commit" in out.stdout and "--code-fix-reason" in out.stdout
    pipeline = repo / "src" / "cmsopen" / "pipeline.py"
    text = pipeline.read_text()
    assert text.count("        bins=60,\n") == 1
    pipeline.write_text(text.replace("        bins=60,\n", "        bins=61,\n"))
    git(repo, "commit", "-qam", "change a Z histogram choice (test)")
    record_gates(repo)
    out = run(repo, "production_run.py", *Z_ONLY, "--code-fix-reason", "rebinned (test)")
    show(capsys, "resume with --code-fix-reason after changing an analysis choice", out)
    assert out.returncode == 8 and "the analysis choices changed" in out.stdout
    git(repo, "revert", "--no-edit", "HEAD")
    record_gates(repo)
    assert len([e for e in events(repo) if e["event"] == "attempt_start"]) == 1


@pytest.mark.slow
def test_resume_4_a_killed_process_after_a_code_fix(resume, capsys):
    repo, _ = resume
    out = run(repo, "production_run.py", *Z_ONLY, "--code-fix-reason", "the fix of test 3 (test)",
              inject="kill:figures")
    show(capsys, "attempt 2: code fix recorded, process killed at the figures step", out)
    assert out.returncode == -9 and "code fix recorded" in out.stdout and "attempt 2 started" in out.stdout
    last = events(repo)[-1]
    assert (last["event"], last["attempt"], last["phase"]) == ("phase", 2, "figures")  # no end: killed
    lock = json.loads((repo / "results" / "production_run.lock").read_text())
    assert lock["head"] == git(repo, "rev-parse", "HEAD").strip() != lock["first_head"]
    (repo / "docs" / "figures" / "z_peak_fit.png").write_bytes(b"partial")  # what a kill mid-figures leaves
    (repo / "docs" / "figures" / "jpsi_peak_fit.png").write_bytes(b"partial")


@pytest.mark.slow
def test_resume_5_completes_and_records_every_attempt(resume, capsys):
    repo, _ = resume
    out = run(repo, "production_run.py", *Z_ONLY)
    show(capsys, "attempt 3: resume to completion", out)
    assert out.returncode == 0 and out.stdout.strip().endswith("PRODUCTION RUN COMPLETE")
    assert "run lock kept" in out.stdout and "attempt 3 started" in out.stdout
    data = json.loads((repo / "results" / "production.json").read_text())
    attempts = data["attempts"]
    with capsys.disabled():
        print("attempts in results/production.json:\n" + json.dumps(attempts, indent=2))
        print("results/production_run.log:\n" + (repo / "results" / "production_run.log").read_text())
    assert attempts["n"] == 3
    assert [(f["attempt"], f["status"], f["phase"]) for f in attempts["failed"]] == [
        (1, "failed", "lock"), (2, "interrupted", "figures")]
    assert attempts["failed"][0]["exception"] == "RuntimeError"
    assert [(c["attempt"], c["reason"]) for c in attempts["code_fixes"]] == [(2, "the fix of test 3 (test)")]
    assert data["first_head"] != data["git_head"] == attempts["code_fixes"][0]["to_head"]
    assert (repo / "docs" / "figures" / "z_peak_fit.png").stat().st_size > 20_000  # regenerated, not the partial
    assert not (repo / "docs" / "figures" / "jpsi_peak_fit.png").exists()  # Z only: the partial file was removed
    assert "SYNTH-" not in (repo / "results" / "production_run.log").read_text()


@pytest.mark.slow
def test_resume_6_a_second_run_after_completion_is_refused(resume, capsys):
    repo, _ = resume
    out = run(repo, "production_run.py", *Z_ONLY)
    show(capsys, "a run after completion", out)
    assert out.returncode == 3 and "REFUSED: single-run guard" in out.stdout and "run state: complete" in out.stdout


# -- the failure-injection hook: only in a marked temporary test copy --------------------------------------------


@pytest.mark.slow
def test_outside_a_test_copy_the_injection_is_refused_by_the_preflight(copy, capsys):
    repo, _ = copy
    record_gates(repo)
    clean = run(repo, "production_preflight.py")
    assert clean.returncode == 0 and "PASS: no failure-injection hook is armed" in clean.stdout
    assert len([x for x in clean.stdout.splitlines() if x.startswith("PASS: ")]) == 13
    out = run(repo, "production_preflight.py", inject="raise:lock")
    show(capsys, "preflight with the injection variable set", out)
    assert out.returncode == 1 and "FAIL: no failure-injection hook is armed" in out.stdout
    out = run(repo, "production_run.py", *Z_ONLY, inject="kill:lock")
    assert out.returncode == 4 and "REFUSED: the preflight failed" in out.stdout
    assert not (repo / "results" / "production_run.lock").exists()
    assert not (repo / "results" / "production_run.log").exists()


@pytest.mark.slow
def test_the_standalone_preflight_fails_on_a_marker_even_a_valid_one(copy):
    repo, _ = copy
    record_gates(repo)
    marker = arm_test_hook(repo)
    try:
        out = run(repo, "production_preflight.py")
    finally:
        marker.unlink()
    assert out.returncode == 1 and "FAIL: no failure-injection hook is armed" in out.stdout


def test_the_hook_is_honoured_only_with_a_marker_holding_this_repository(tmp_path, monkeypatch):
    sys.path.insert(0, str(REPO / "scripts"))
    import production_preflight
    import production_run

    sys.path.pop(0)

    class Log:
        def add(self, **event):
            pass

    kills = []
    monkeypatch.setattr(production_run.os, "kill", lambda pid, sig: kills.append(sig))
    monkeypatch.setenv("CMSOPEN_PRODUCTION_INJECT", "raise:lock")
    assert not production_preflight.is_test_copy(REPO)  # the real repository is never a test copy
    production_run._checkpoint(Log(), 1, "lock")  # ignored here
    monkeypatch.setenv("CMSOPEN_PRODUCTION_INJECT", "kill:lock")
    production_run._checkpoint(Log(), 1, "lock")
    assert kills == []
    marker = tmp_path / "scripts" / ".production_test_copy"
    marker.parent.mkdir()
    monkeypatch.setattr(production_run, "REPO", tmp_path)
    marker.write_text("/some/other/repository\n")  # a marker copied from elsewhere does not count
    production_run._checkpoint(Log(), 1, "lock")
    assert kills == []
    marker.write_text(str(tmp_path.resolve()) + "\n")
    production_run._checkpoint(Log(), 1, "lock")
    assert len(kills) == 1
    monkeypatch.setenv("CMSOPEN_PRODUCTION_INJECT", "raise:lock")
    with pytest.raises(RuntimeError, match="injected failure at lock"):
        production_run._checkpoint(Log(), 1, "lock")
