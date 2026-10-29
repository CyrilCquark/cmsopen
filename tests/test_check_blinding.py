"""Tests for scripts/check_blinding.py, each in a throwaway git repository with a fake registry."""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_blinding.py"
ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.org", "GIT_COMMITTER_NAME": "t",
       "GIT_COMMITTER_EMAIL": "t@example.org", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
PROD = ["AAAAAAAA-1111-2222-3333-444444444444.root", "BBBBBBBB-5555-6666-7777-888888888888.root"]
DEV = "DDDDDDDD-0000-0000-0000-000000000000.root"


def git(repo, *args):
    subprocess.run(["git", *args], cwd=repo, env=ENV, capture_output=True, text=True, check=True)


def run(repo):
    return subprocess.run([sys.executable, str(SCRIPT)], cwd=repo, env=ENV, capture_output=True, text=True)


def write_registry(repo, names=PROD):
    registry = {"development_file": DEV, "records": [{"record_id": 1, "selected": [{"filename": n} for n in names]}]}
    path = repo / "results" / "production_files.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(registry, indent=2) + "\n")
    (repo / "dev").mkdir(exist_ok=True)
    (repo / "dev" / "registry.sha256").write_text(
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  results/production_files.json\n")


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-q", "-b", "main")
    write_registry(tmp_path)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "code.py").write_text(f'DEV = "data/{DEV}"\n')  # the development file is fine
    (tmp_path / "CLAUDE.md").write_text("rules\n")
    (tmp_path / ".gitignore").write_text("build/\n")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "init")
    return tmp_path


def test_clean_repo_passes(repo):
    out = run(repo)
    assert out.returncode == 0, out.stdout + out.stderr
    assert out.stdout.strip() == "OK: no production file referenced outside the registry; registry intact"


@pytest.mark.parametrize("rel", ["src/code.py", "tests/test_x.py", "examples/demo.py", "scripts/s.py", "CLAUDE.md",
                                 "dev/notes.md"])
def test_production_name_in_tracked_file_fails(repo, rel):
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"see {PROD[1]}\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "leak")
    out = run(repo)
    assert out.returncode == 1 and rel in out.stdout and PROD[1] in out.stdout


def test_stem_without_suffix_and_lowercase_are_caught(repo):
    (repo / "src" / "a.py").write_text(f"x = '{PROD[0].removesuffix('.root').lower()}'\n")
    out = run(repo)  # untracked, not ignored: also scanned
    assert out.returncode == 1 and "src/a.py" in out.stdout


def test_ignored_files_are_not_scanned(repo):
    (repo / "build").mkdir()
    (repo / "build" / "log.txt").write_text(PROD[0])
    assert run(repo).returncode == 0


def test_registry_tampering_fails(repo):
    path = repo / "results" / "production_files.json"
    path.write_text(path.read_text().replace("AAAAAAAA", "CCCCCCCC"))
    out = run(repo)
    assert out.returncode == 1 and "SHA-256" in out.stdout


def test_missing_hash_or_registry_fails(repo):
    (repo / "dev" / "registry.sha256").unlink()
    out = run(repo)
    assert out.returncode == 1 and "registry.sha256 is missing" in out.stdout
    write_registry(repo)
    (repo / "results" / "production_files.json").unlink()
    out = run(repo)
    assert out.returncode == 1 and "missing" in out.stdout


def write_dev_set(repo, names):
    dev_set = {"original_development_file": DEV, "files": [{"filename": n} for n in names]}
    (repo / "dev" / "development_set.json").write_text(json.dumps(dev_set) + "\n")


def test_disjoint_development_set_passes(repo):
    write_dev_set(repo, ["EEEEEEEE-0000-0000-0000-000000000001.root", "EEEEEEEE-0000-0000-0000-000000000002.root"])
    out = run(repo)
    assert out.returncode == 0, out.stdout
    assert out.stdout.splitlines()[-1] == "OK: development set (3 files) disjoint from production"


def test_development_set_overlapping_production_fails_without_printing_the_name(repo):
    write_dev_set(repo, ["EEEEEEEE-0000-0000-0000-000000000001.root", PROD[1]])
    out = run(repo)
    assert out.returncode == 1
    assert "1 development-set file(s) coincide with production files" in out.stdout
    assert "dev/development_set.json: references production file (name not printed)" in out.stdout
    assert PROD[1] not in out.stdout and PROD[1].removesuffix(".root") not in out.stdout + out.stderr


def test_unreadable_development_set_fails(repo):
    (repo / "dev" / "development_set.json").write_text("{}\n")
    out = run(repo)
    assert out.returncode == 1 and "cannot read the development set" in out.stdout
