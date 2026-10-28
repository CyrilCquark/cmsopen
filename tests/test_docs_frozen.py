"""Tests for scripts/check_docs_frozen.py, each in a throwaway git repository."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_docs_frozen.py"
ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.org", "GIT_COMMITTER_NAME": "t",
       "GIT_COMMITTER_EMAIL": "t@example.org", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}


def git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, env=ENV, capture_output=True, text=True, check=True).stdout.strip()


def check(repo, rev):
    return subprocess.run([sys.executable, str(SCRIPT), "--since", rev], cwd=repo, env=ENV, capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-q", "-b", "main")
    files = {"README.md": "readme\n", "DATA.md": "data\n", "LICENSE": "mit\n", "docs/figures/a.png": "png\n",
             "notebooks/n.ipynb": "{}\n", "src/code.py": "x = 1\n", ".gitignore": "build/\n"}
    for name, text in files.items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(text)
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "start")
    return tmp_path, git(tmp_path, "rev-parse", "HEAD")


def commit_all(repo, msg="change"):
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", msg)


def test_unchanged_passes(repo):
    path, start = repo
    out = check(path, start)
    assert out.returncode == 0, out.stdout + out.stderr
    assert out.stdout.strip() == f"OK: protected documentation unchanged since {start}"


def test_unprotected_changes_and_ignored_files_pass(repo):
    path, start = repo
    (path / "src" / "code.py").write_text("x = 2\n")
    (path / "src" / "new.py").write_text("y = 1\n")
    commit_all(path)
    (path / "examples").mkdir()
    (path / "examples" / "untracked.py").write_text("z\n")  # untracked but not protected
    (path / "build").mkdir()
    (path / "build" / "docs.png").write_text("ignored\n")  # ignored
    assert check(path, start).returncode == 0


@pytest.mark.parametrize("name", ["README.md", "DATA.md", "LICENSE", "docs/figures/a.png", "notebooks/n.ipynb"])
def test_committed_modification_fails(repo, name):
    path, start = repo
    (path / name).write_text("edited\n")
    commit_all(path)
    out = check(path, start)
    assert out.returncode == 1 and name in out.stdout and "FAIL" in out.stdout


def test_uncommitted_and_staged_modifications_fail(repo):
    path, start = repo
    (path / "DATA.md").write_text("unstaged edit\n")
    out = check(path, start)
    assert out.returncode == 1 and "DATA.md" in out.stdout
    git(path, "add", "DATA.md")
    assert check(path, start).returncode == 1


def test_untracked_new_file_under_docs_fails(repo):
    path, start = repo
    (path / "docs" / "new_figure.png").write_text("new\n")
    out = check(path, start)
    assert out.returncode == 1
    assert "??" in out.stdout and "docs/new_figure.png" in out.stdout


def test_untracked_notebook_and_production_json_fail(repo):
    path, start = repo
    (path / "notebooks" / "extra.ipynb").write_text("{}\n")
    (path / "results").mkdir()
    (path / "results" / "production.json").write_text("{}\n")
    out = check(path, start)
    assert out.returncode == 1
    assert "notebooks/extra.ipynb" in out.stdout and "results/production.json" in out.stdout


def test_deleted_readme_fails(repo):
    path, start = repo
    (path / "README.md").unlink()
    out = check(path, start)
    assert out.returncode == 1 and "README.md" in out.stdout and "D" in out.stdout
    commit_all(path, "delete readme")
    assert check(path, start).returncode == 1


def test_rename_out_of_and_into_protected_paths_fails(repo):
    path, start = repo
    git(path, "mv", "docs/figures/a.png", "src/a.png")
    commit_all(path, "move out")
    out = check(path, start)
    assert out.returncode == 1 and "docs/figures/a.png" in out.stdout
    path2 = path
    git(path2, "mv", "src/code.py", "docs/code.py")
    commit_all(path2, "move in")
    assert "docs/code.py" in check(path2, start).stdout


def test_change_then_revert_passes(repo):
    path, start = repo
    (path / "README.md").write_text("edited\n")
    commit_all(path, "edit")
    (path / "README.md").write_text("readme\n")
    commit_all(path, "revert")
    assert check(path, start).returncode == 0  # content identical to START


def test_bad_revision_is_a_usage_error(repo):
    path, _ = repo
    out = check(path, "does-not-exist")
    assert out.returncode == 2 and "not a commit" in out.stderr


# -- the --production guard of examples/make_figures.py (never touches the real docs/) ---------------------


@pytest.fixture
def make_figures_in(tmp_path, monkeypatch):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples"))
    import make_figures

    sys.path.pop(0)
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    (repo / "f.txt").write_text("x\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "init")
    monkeypatch.setattr(make_figures, "REPO", repo)
    monkeypatch.setattr(make_figures, "PRODUCTION_OUTDIR", repo / "docs" / "figures")
    monkeypatch.setattr(make_figures, "DEFAULT_OUTDIR", repo / "build" / "figures")
    for key in ("GIT_CONFIG_GLOBAL", "GIT_CONFIG_NOSYSTEM"):
        monkeypatch.setenv(key, ENV[key])
    calls = []
    monkeypatch.setattr(make_figures, "build", lambda path: calls.append(("build", path)) or make_figures.Figures())
    monkeypatch.setattr(make_figures, "write", lambda figs, outdir: calls.append(("write", outdir)) or figs)
    return make_figures, repo, calls


def test_make_figures_default_is_untracked_build_dir(make_figures_in):
    mf, repo, calls = make_figures_in
    assert mf.main(["--file", str(repo / "f.txt")]) == 0
    assert calls[-1] == ("write", repo / "build" / "figures")
    assert Path(mf.__file__).resolve().parents[1].joinpath(".gitignore").read_text().count("build/") >= 1


def test_make_figures_refuses_docs_without_production(make_figures_in, capsys):
    mf, repo, calls = make_figures_in
    assert mf.main(["--file", str(repo / "f.txt"), "--outdir", str(repo / "docs" / "figures")]) == 1
    assert not calls and "protected documentation" in capsys.readouterr().err


def test_make_figures_production_refuses_dirty_tree_and_warns(make_figures_in, capsys):
    mf, repo, calls = make_figures_in
    (repo / "f.txt").write_text("dirty\n")
    assert mf.main(["--production", "--file", str(repo / "f.txt")]) == 1
    err = capsys.readouterr().err
    assert "\033[1mWARNING" in err and "OVERWRITES PROTECTED DOCUMENTATION" in err and "not clean" in err
    assert not calls and not (repo / "docs").exists()


def test_make_figures_production_on_clean_tree_targets_docs(make_figures_in, capsys):
    mf, repo, calls = make_figures_in
    assert mf.main(["--production", "--file", str(repo / "f.txt")]) == 0
    assert calls[-1] == ("write", repo / "docs" / "figures")  # stubbed: nothing is written
    assert "WARNING" in capsys.readouterr().err


def test_make_figures_production_and_outdir_are_exclusive(make_figures_in):
    mf, repo, _ = make_figures_in
    with pytest.raises(SystemExit):
        mf.main(["--production", "--outdir", str(repo / "x")])
