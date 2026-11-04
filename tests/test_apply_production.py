"""Tests of the post-production path: scripts/apply_production.py and everything it writes.

All of it happens in temporary copies of the repository; nothing is written to the repository itself. The copy holds
the saved dry-run output if it exists on this machine (with placeholder figures), or else the output of a real
production run on the synthetic registry, so the tests also run where no dry-run output is available.
"""

import importlib.util
import json
import os
import re
import shutil
import struct
import subprocess
import sys
from pathlib import Path

import pytest
from release_fixtures import DRY_RUN_JSON, install_production
from test_production import clone_working_tree, git, make_copy, record_gates, restore_pre_production, run

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"
sys.path.insert(0, str(SCRIPTS))
from release_lib import NumberAudit, audit_numbers, lint_template, tokens  # noqa: E402

sys.path.pop(0)
GENERATED = (
    "README.md",
    "README_PYPI.md",
    "DATA.md",
    "results/production_extras.json",
    "CITATION.cff",
    ".zenodo.json",
    "docs/index.md",
    "docs/physics.md",
    "docs/user_guide.md",
    "docs/api.md",
    "docs/validation.md",
    "docs/reproducibility.md",
    "docs/changelog.md",
    "notebooks/01_z_peak.ipynb",
    "notebooks/02_jpsi_peak.ipynb",
    "notebooks/03_modular_usage.ipynb",
)
ASSETS = (
    "one_page_summary.md",
    "one_page_summary.pdf",
    "activity_descriptions.md",
    "verify_in_10_minutes.md",
    "email_to_mentor.md",
    "numbers.md",
    "figures/hero_z_peak_fit.png",
    "figures/supporting_jpsi_peak_fit.png",
    "figures/supporting_z_os_vs_ss.png",
)
DRY = "DRY-RUN DATA"
HAS_MKDOCS = importlib.util.find_spec("mkdocs") is not None and importlib.util.find_spec("mkdocstrings") is not None
needs_docs = pytest.mark.skipif(not HAS_MKDOCS, reason="the docs extra is not installed")
AI_LINE = "built with AI coding assistance (Claude Code) under my direction"


def apply(repo, *args):
    if not HAS_MKDOCS and "--check" not in args:  # the gates run without the docs extra
        args = (*args, "--skip-docs-build")
    return subprocess.run(
        [sys.executable, "scripts/apply_production.py", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )


def script(repo, name, *args):
    return subprocess.run([sys.executable, f"scripts/{name}", *args], cwd=repo, capture_output=True, text=True)


def snapshot(repo, app):
    files = {name: (repo / name).read_bytes() for name in GENERATED}
    files.update({f"app/{name}": (app / name).read_bytes() for name in ASSETS})
    return files


def real_run_output(tmp):
    """The output of a real production run on the synthetic registry, from the same path as the production command."""
    repo, _ = make_copy(tmp)
    record_gates(repo)
    out = run(repo, "production_run.py", "--confirm-single-production-run", "--workers", "2")
    assert out.returncode == 0, out.stdout + out.stderr
    return repo


@pytest.fixture(scope="module")
def applied(tmp_path_factory):
    """A copy after the whole apply step, notebooks run top to bottom: (repository, assets, production data)."""
    tmp = tmp_path_factory.mktemp("apply")
    repo, app = tmp / "repo", tmp / "application"
    if DRY_RUN_JSON.exists():
        data = json.loads(DRY_RUN_JSON.read_text())
    else:
        source = real_run_output(tmp / "source")
        data = json.loads((source / "results" / "production.json").read_text())
    clone_working_tree(repo)
    restore_pre_production(repo)  # once the generated files are committed, a plain clone already has them
    install_production(repo, data)
    out = apply(repo, "--dry-run-data", "--application-dir", str(app))
    assert out.returncode == 0 and "APPLY COMPLETE" in out.stdout, out.stdout + out.stderr
    return repo, app, data, out.stdout


# --- the guards, without a copy


def test_tokens_are_numbers_and_never_digits_inside_names():
    assert tokens("peak 91.2 GeV, 1,234 pairs, 3e-05, version 0.1.0.") == ["91.2", "1,234", "3e-05", "0.1.0"]
    assert tokens("chi2/ndf T4 2012B cb2_bw_exp J/psi") == []


def test_template_lint_finds_typed_numbers_and_accepts_placeholders_and_code():
    assert lint_template("The peak is 91.234 GeV.") == ["91.234"]
    assert lint_template("We read 6 files.") == ["6"]
    assert lint_template("The peak is {{ z.peak }} GeV at 8 TeV in Run 2012.") == []
    assert lint_template("```bash\npython3.12 -m venv .venv --n 5\n```\n[a](http://x.org/1.2)\n1. first\n") == []


def test_every_template_of_the_branch_is_free_of_typed_numbers():
    sys.path[:0] = [str(SCRIPTS), str(REPO / "examples")]
    try:
        from apply_production import template_problems

        assert template_problems() == []
    finally:
        del sys.path[:2]


def test_the_number_audit_accepts_rounded_values_of_the_file_and_nothing_else():
    audit = NumberAudit({"a": 90.89266077, "n": 173754, "b": 0.00014, "text": "chi2/ndf <= 2.0"})
    text = "peak 90.8927 and 90.89, 173,754 pairs, error 0.00014, benchmark 2.0"
    assert audit_numbers(text, audit) == []
    assert audit_numbers("peak 91.234 from 7 files", audit) == ["91.234", "7"]


def test_the_docs_workflow_is_manual_only():
    text = (REPO / ".github" / "workflows" / "docs.yml").read_text()
    triggers = text.split("\non:\n", 1)[1].split("\npermissions:", 1)[0].split()
    assert triggers == ["workflow_dispatch:"]




# --- the end-to-end run in a copy


@pytest.mark.slow
def test_apply_reports_what_it_changed_and_passes_every_check(applied):
    _, _, _, stdout = applied
    assert ("OK: mkdocs build --strict" in stdout) == HAS_MKDOCS
    for line in (
        "OK: README results block equals",
        "OK: CITATION.cff follows the CFF",
        "OK: every number traces",
        "OK: no production file referenced",
        "APPLY COMPLETE",
    ):
        assert line in stdout, stdout
    assert re.search(r"OK: 01_z_peak: \d+ self-checks", stdout) and re.search(r"OK: 03_modular_usage", stdout)
    for name in GENERATED:
        assert f"  {name}\n" in stdout


def _channel_numbers(data, name):
    c = data["channels"][name]
    r = c["result"]
    d = 4 if name == "Z_mumu" else 5
    return [
        f"{r['peak_position_gev']:.{d}f}",
        f"{r['chi2_ndf']:.3f}",
        f"{r['pdg_mass_gev']:.4f}",
        f"{r['offset_from_pdg_gev']:+.{d}f}",
        f"{r['n_pairs_in_fit_range']:,}",
    ]


def _text(repo, app, name):
    path = app / name[4:] if name.startswith("app/") else repo / name
    text = path.read_text()
    if name.endswith(".ipynb"):
        text = "\n".join("".join(c["source"]) for c in json.loads(text)["cells"])
    return text


@pytest.mark.slow
@pytest.mark.parametrize(
    "name,channels",
    [
        ("README.md", ("Z_mumu", "Jpsi_mumu")),
        ("docs/index.md", ("Z_mumu", "Jpsi_mumu")),
        ("app/numbers.md", ("Z_mumu", "Jpsi_mumu")),
        ("notebooks/01_z_peak.ipynb", ("Z_mumu",)),
        ("notebooks/02_jpsi_peak.ipynb", ("Jpsi_mumu",)),
        ("notebooks/03_modular_usage.ipynb", ("Z_mumu", "Jpsi_mumu")),
    ],
)
def test_the_numbers_equal_production_json(applied, name, channels):
    """Recomputed here, independently of the generators' formatting code."""
    repo, app, data, _ = applied
    text = _text(repo, app, name)
    for channel in channels:
        for number in _channel_numbers(data, channel):
            assert number in text, f"{name}: {channel} {number}"
    assert str(data["targets"]["T4"]["benchmark"]["n_files"]) in text and str(data["sample"]["n_files"]) in text


@pytest.mark.slow
@pytest.mark.parametrize(
    "name",
    [
        "CITATION.cff",
        ".zenodo.json",
        "app/one_page_summary.md",
        "app/activity_descriptions.md",
        "app/email_to_mentor.md",
    ],
)
def test_the_summaries_state_the_chi2_benchmark_and_observed_values(applied, name):
    repo, app, data, _ = applied
    text = _text(repo, app, name)
    assert f"{data['channels']['Z_mumu']['t2']['benchmark']:.1f}" in text
    for channel in ("Z_mumu", "Jpsi_mumu"):
        assert f"{data['channels'][channel]['result']['chi2_ndf']:.3f}" in text
    assert re.search(r"benchmark", text, flags=re.I) and re.search(r"observed|was \d", text)
    assert f"{data['sample']['n_files']}" in text


@pytest.mark.slow
def test_benchmarks_are_labelled_and_a_missed_one_is_reported_as_not_met(applied):
    repo, _, data, _ = applied
    block = repo.joinpath("README.md").read_text().split("<!-- RESULTS:BEGIN -->")[1].split("<!-- RESULTS:END -->")[0]
    header = next(line for line in block.splitlines() if line.startswith("| target"))
    assert header.index("controlling benchmark") < header.index("observed") < header.index("status")
    for name, target in data["targets"].items():
        row = next(line for line in block.splitlines() if line.startswith(f"| {name} "))
        met = target["met"]
        assert ("not met" in row) == (not all(met.values()) if isinstance(met, dict) else not met), row
    rows = [line for line in block.splitlines() if line.startswith("| χ²/ndf")]
    assert "**benchmark**" in rows[0] and "observed" in rows[1] and "benchmark" not in rows[1]


@pytest.mark.slow
def test_dry_run_data_are_labelled_in_every_generated_file(applied):
    repo, app, data, _ = applied
    if "dry run" not in data["gates"]["summary"]:
        pytest.skip("synthetic production output, not labelled as a dry run")
    for name in GENERATED:
        if name not in ("docs/api.md", "docs/changelog.md", "DATA.md"):  # these state no result
            assert DRY in (repo / name).read_text(), name
    for name in ASSETS:
        if name.endswith(".md"):
            assert DRY in (app / name).read_text(), name


@pytest.mark.slow
def test_no_production_file_name_in_anything_generated(applied):
    repo, app, _, _ = applied
    registry = json.loads((REPO / "results" / "production_files.json").read_text())
    stems = [e["filename"].removesuffix(".root") for r in registry["records"] for e in r["selected"]]
    assert len(stems) == 20
    for name in GENERATED:
        text = (repo / name).read_text()
        assert not [s for s in stems if s in text], name
    for name in ASSETS:
        if name.endswith(".md"):
            assert not [s for s in stems if s in (app / name).read_text()], name
    out = script(repo, "check_blinding.py")
    assert out.returncode == 0, out.stdout


@pytest.mark.slow
def test_rerunning_is_byte_identical(applied, tmp_path):
    repo, app, _, _ = applied
    before = snapshot(repo, app)
    out = apply(repo, "--dry-run-data", "--self-checks-only", "--application-dir", str(app))
    assert out.returncode == 0, out.stdout + out.stderr
    assert "changed in the repository (0 files" in out.stdout and "(0 files)" in out.stdout
    assert snapshot(repo, app) == before
    check = apply(repo, "--check")
    assert check.returncode == 0 and "byte-identical" in check.stdout, check.stdout


@pytest.mark.slow
@needs_docs
def test_the_docs_build_strict_and_the_home_page_is_the_readme(applied, tmp_path):
    repo, _, data, _ = applied
    site = tmp_path / "site"
    out = subprocess.run(
        [sys.executable, "-m", "mkdocs", "build", "--strict", "--site-dir", str(site)],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    assert out.returncode == 0, out.stderr[-3000:]
    home = (site / "index.html").read_text()
    assert f"{data['channels']['Z_mumu']['result']['peak_position_gev']:.4f}" in home
    assert "figures/z_peak_fit.png" in home
    assert "cmsopen.pipeline.analyze" in (site / "api" / "index.html").read_text()


@pytest.mark.slow
def test_the_quick_start_commands_of_the_readme_run_from_the_copy(applied, tmp_path):
    repo, _, _, _ = applied
    readme = (repo / "README.md").read_text()
    block = readme.split("Then three commands:", 1)[1].split("```bash\n", 1)[1].split("```", 1)[0]
    commands = block.strip().splitlines()
    assert len(commands) == 3
    env = {**os.environ, "PATH": f"{Path(sys.executable).parent}:{os.environ['PATH']}", "MPLBACKEND": "Agg"}
    for command in commands:
        out = subprocess.run(command, shell=True, cwd=repo, capture_output=True, text=True, env=env)
        assert out.returncode == 0, command + "\n" + out.stdout + out.stderr
    assert "All checks passed" in out.stdout
    assert (repo / "out" / "z" / "mass_fit.png").exists() and (repo / "out" / "jpsi" / "summary.json").exists()
    shutil.rmtree(repo / "out")


def _png_dpi(data):
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    position = 8
    while position < len(data):
        length, kind = struct.unpack(">I4s", data[position : position + 8])
        if kind == b"pHYs":
            x, _, unit = struct.unpack(">IIB", data[position + 8 : position + 17])
            return x * 0.0254 if unit == 1 else 0
        position += length + 12
    return 0


@pytest.mark.slow
def test_the_application_assets(applied):
    repo, app, data, _ = applied
    for name in ASSETS:
        assert (app / name).stat().st_size > 0, name
    assert not str(app).startswith(str(REPO))
    pdf = (app / "one_page_summary.pdf").read_bytes()
    assert len(re.findall(rb"/Type\s*/Page\b", pdf)) == 1
    for name, source in (
        ("hero_z_peak_fit.png", "z_peak_fit.png"),
        ("supporting_jpsi_peak_fit.png", "jpsi_peak_fit.png"),
        ("supporting_z_os_vs_ss.png", "z_os_vs_ss.png"),
    ):
        image = (app / "figures" / name).read_bytes()
        assert image == (repo / "docs" / "figures" / source).read_bytes()
        assert _png_dpi(image) > 299
    text = (app / "activity_descriptions.md").read_text()
    long, short, line = re.split(r"^## .*$", text, flags=re.M)[1:]
    assert 130 <= len(long.split()) <= 170, len(long.split())
    assert 40 <= len(short.split()) <= 60, len(short.split())
    assert line.strip().count("\n") == 0
    for name in ("one_page_summary.md", "email_to_mentor.md"):
        assert AI_LINE in " ".join((app / name).read_text().split()), name
    for version in (long, short, line):
        assert AI_LINE in " ".join(version.split())
    assert "[mentor's name]" in (app / "email_to_mentor.md").read_text()
    if shutil.which("pdftotext"):
        out = subprocess.run(["pdftotext", str(app / "one_page_summary.pdf"), "-"], capture_output=True, text=True)
        assert f"{data['channels']['Z_mumu']['result']['peak_position_gev']:.4f}" in out.stdout


@pytest.mark.slow
def test_citation_version_and_authors_match_the_package(applied):
    repo, _, _, _ = applied
    import yaml

    cff = yaml.safe_load((repo / "CITATION.cff").read_text())
    zenodo = json.loads((repo / ".zenodo.json").read_text())
    version = re.search(r'__version__ = "(.+)"', (REPO / "src" / "cmsopen" / "__init__.py").read_text()).group(1)
    assert cff["version"] == zenodo["version"] == version
    assert cff["authors"][0]["family-names"] == "Nadar" and "email" not in cff["authors"][0]
    assert cff["license"] == zenodo["license"] == "MIT"
    assert "TODO" in (repo / "CITATION.cff").read_text() and zenodo["creators"][0]["orcid"] == "TODO"
    assert "10.7483/OPENDATA.CMS.M5AD.Y3V3" in (repo / "CITATION.cff").read_text()
    assert "10.7483/OPENDATA.CMS.YLIC.86ZZ" in (repo / "CITATION.cff").read_text()
    strict = script(repo, "check_release_metadata.py", "--release")
    assert strict.returncode == 1 and "TODO" in strict.stdout


@pytest.mark.slow
def test_the_orcid_and_the_second_doi_come_from_the_metadata_file_and_clear_the_todos(fresh):
    path = fresh / "templates" / "release_metadata.json"
    meta = json.loads(path.read_text())
    meta["orcid"] = "0000-0002-1825-0097"  # the identifier ORCID uses in its own documentation
    meta["record_dois"] = {"31123": "10.7483/OPENDATA.CMS.EXAMPLE"}
    path.write_text(json.dumps(meta))
    out = apply(fresh, "--dry-run-data", "--self-checks-only", "--application-dir", str(fresh.parent / "a"))
    assert out.returncode == 0, out.stdout + out.stderr
    strict = script(fresh, "check_release_metadata.py", "--release")
    assert strict.returncode == 0, strict.stdout
    assert "https://orcid.org/0000-0002-1825-0097" in (fresh / "CITATION.cff").read_text()
    assert json.loads((fresh / ".zenodo.json").read_text())["creators"][0]["orcid"] == "0000-0002-1825-0097"


@pytest.mark.slow
def test_the_generated_notebooks_pass_ruff(applied):
    repo, _, _, _ = applied
    out = subprocess.run([sys.executable, "-m", "ruff", "check", "notebooks"], cwd=repo, capture_output=True, text=True)
    assert out.returncode == 0, out.stdout


# --- refusals: nothing is written


@pytest.fixture
def fresh(tmp_path, applied):
    """A copy with the production file, before the apply step."""
    repo = tmp_path / "repo"
    clone_working_tree(repo)
    restore_pre_production(repo)  # once the generated files are committed, a plain clone already has them
    install_production(repo, applied[2])
    return repo


def _nothing_written(repo):
    return not (repo / "CITATION.cff").exists() and not (repo / "notebooks" / "01_z_peak.ipynb").exists()


@pytest.mark.slow
def test_refuses_without_a_production_file(fresh, tmp_path):
    (fresh / "results" / "production.json").unlink()
    out = apply(fresh, "--dry-run-data", "--application-dir", str(tmp_path / "a"))
    assert out.returncode == 2 and "does not exist" in out.stdout and _nothing_written(fresh)


@pytest.mark.slow
def test_refuses_a_file_that_fails_the_schema(fresh, tmp_path):
    path = fresh / "results" / "production.json"
    data = json.loads(path.read_text())
    del data["channels"]["Jpsi_mumu"]["result"]["chi2_ndf"]
    path.write_text(json.dumps(data))
    out = apply(fresh, "--dry-run-data", "--application-dir", str(tmp_path / "a"))
    assert (
        out.returncode == 2 and "channels.Jpsi_mumu.result.chi2_ndf: missing" in out.stdout and _nothing_written(fresh)
    )


@pytest.mark.slow
def test_refuses_dry_run_data_without_the_flag_or_outside_a_test_copy(fresh, tmp_path):
    out = apply(fresh, "--application-dir", str(tmp_path / "a"))
    assert out.returncode == 2 and "not the production result" in out.stdout and _nothing_written(fresh)
    (fresh / "scripts" / ".production_test_copy").unlink()
    out = apply(fresh, "--dry-run-data", "--application-dir", str(tmp_path / "a"))
    assert out.returncode == 2 and "marked temporary test copy" in out.stdout and _nothing_written(fresh)


@pytest.mark.slow
def test_dry_run_data_never_go_to_the_default_application_directory(fresh):
    out = apply(fresh, "--dry-run-data")
    assert out.returncode == 2 and "default application directory" in out.stdout and _nothing_written(fresh)


@pytest.mark.slow
def test_refuses_figures_that_do_not_belong_to_the_production_file(fresh, tmp_path):
    (fresh / "docs" / "figures" / "z_peak_fit_caption.md").write_text("Peak 12.345 GeV, an old development caption.\n")
    out = apply(fresh, "--dry-run-data", "--application-dir", str(tmp_path / "a"))
    assert out.returncode == 2 and "do not belong" in out.stdout and _nothing_written(fresh)
    (fresh / "docs" / "figures" / "jpsi_peak_fit.png").unlink()
    out = apply(fresh, "--dry-run-data", "--application-dir", str(tmp_path / "a"))
    assert out.returncode == 2 and "figures missing" in out.stdout


# --- deliberate breakages: the checks must fail, then pass again once restored


@pytest.fixture
def broken(applied):
    """Restore whatever a test breaks in the shared copy."""
    repo = applied[0]
    saved = {
        p: p.read_bytes()
        for p in [
            repo / "README.md",
            repo / "CITATION.cff",
            repo / "templates" / "README.md",
            repo / "notebooks" / "01_z_peak.ipynb",
        ]
    }
    yield repo
    for path, content in saved.items():
        path.write_bytes(content)
    assert apply(repo, "--check").returncode == 0


@pytest.mark.slow
def test_breakage_a_number_typed_in_the_readme_template(broken, tmp_path):
    path = broken / "templates" / "README.md"
    path.write_text(path.read_text().replace("## Licence", "The Z peak is at 91.234 GeV.\n\n## Licence"))
    out = apply(broken, "--dry-run-data", "--application-dir", str(tmp_path / "a"))
    assert out.returncode == 2 and "templates/README.md: 91.234" in out.stdout


@pytest.mark.slow
def test_breakage_a_number_edited_in_the_generated_readme(broken):
    path = broken / "README.md"
    data = json.loads((broken / "results" / "production.json").read_text())
    peak = f"{data['channels']['Z_mumu']['result']['peak_position_gev']:.4f}"
    path.write_text(path.read_text().replace(peak, "91.1876"))
    assert script(broken, "check_readme_numbers.py").returncode == 1
    out = apply(broken, "--check")
    assert out.returncode == 1 and "README.md differs" in out.stdout


@pytest.mark.slow
def test_breakage_a_version_mismatch_in_the_citation(broken):
    path = broken / "CITATION.cff"
    path.write_text(
        path.read_text().replace('version: "', 'version: "9.', 1).replace('cff-version: "9.', "cff-version: ")
    )
    out = script(broken, "check_release_metadata.py")
    assert out.returncode == 1 and "differs from cmsopen.__version__" in out.stdout


@pytest.mark.slow
def test_breakage_a_number_edited_in_a_notebook_fails_its_self_check(broken):
    path = broken / "notebooks" / "01_z_peak.ipynb"
    data = json.loads((broken / "results" / "production.json").read_text())
    chi2 = f"{data['channels']['Z_mumu']['result']['chi2_ndf']:.3f}"
    path.write_text(path.read_text().replace(chi2, "1.234"))
    out = script(broken, "check_notebooks.py", "--self-checks-only")
    assert out.returncode == 1 and "FAIL" in out.stdout


# --- the real production path on the synthetic registry, including its real figures and captions


def tree_state(repo):
    """Every file of a tree with its bytes, apart from .git and bytecode."""
    return {p.relative_to(repo).as_posix(): p.read_bytes() for p in repo.rglob("*")
            if p.is_file() and ".git" not in p.parts and "__pycache__" not in p.parts}


@pytest.mark.slow
@pytest.mark.timeout(900, method="signal")  # a production run on the synthetic registry, a rehearsal and an apply
def test_apply_after_a_real_production_run_on_the_synthetic_registry(tmp_path):
    """The whole path on real outputs of the production command: rehearse, apply, extras from the saved histogram."""
    repo = real_run_output(tmp_path)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "production outputs (test)")
    app = tmp_path / "application"

    before = tree_state(repo)
    out = apply(repo, "--rehearse", "--self-checks-only", "--application-dir", str(app))
    assert out.returncode == 0 and "REHEARSAL PASSED" in out.stdout, out.stdout + out.stderr
    assert tree_state(repo) == before and not app.exists()
    assert "  README.md\n" in out.stdout and "  DATA.md\n" in out.stdout and "OK: every number traces" in out.stdout

    out = apply(repo, "--self-checks-only", "--application-dir", str(app))
    assert out.returncode == 0 and "APPLY COMPLETE" in out.stdout, out.stdout + out.stderr
    for name in GENERATED:
        text = (repo / name).read_text()
        assert DRY not in text, name
        assert "SYNTH-" not in text, name
    assert DRY not in (app / "numbers.md").read_text()
    assert apply(repo, "--check").returncode == 0

    summary = json.loads((repo / "build" / "production" / "Jpsi_mumu" / "run1" / "summary.json").read_text())
    edges, counts = summary["histogram"]["edges_gev"], summary["histogram"]["counts"]
    # recomputed here, independently
    window = sum(c for lo, c in zip(edges, counts, strict=False) if 2.9 - 1e-9 <= lo < 3.3 - 1e-9)
    side = sum(c for lo, c in zip(edges, counts, strict=False) if not 2.9 - 1e-9 <= lo < 3.3 - 1e-9)
    background = side * 0.4 / 0.6
    extras = {r["metric"]: r for r in json.loads((repo / "results" / "production_extras.json").read_text())["rows"]}
    pairs = next(v for k, v in extras.items() if k.startswith("J/psi opposite-sign"))
    assert pairs["observed"].startswith(f"{int(window):,} pairs") and pairs["status"] in ("met", "not met")
    sb = next(v for k, v in extras.items() if k.startswith("J/psi sideband"))
    assert sb["observed"] == f"{(window - background) / background:.2f}"

    shutil.rmtree(repo / "build" / "production")  # as in a fresh clone: the kept file replaces the saved outputs
    assert apply(repo, "--check").returncode == 0
    production = repo / "results" / "production.json"
    production.write_text(production.read_text() + " ")
    out = apply(repo, "--check")  # the README states the file's hash, so a changed file is noticed
    assert out.returncode == 1 and "README.md differs" in out.stdout


# --- prompt 14: the registry table, DATA.md, the rehearsal, the PyPI description, the extras of the install


def extras_module():
    sys.path.insert(0, str(SCRIPTS))
    try:
        import production_extras
        return production_extras
    finally:
        sys.path.pop(0)


def test_the_window_and_the_sidebands_come_from_the_histogram_edges():
    extras = extras_module()
    edges = [2.6 + 0.02 * i for i in range(51)]
    counts = [10] * 50  # flat: S = 0
    window, sb = extras.jpsi_window_and_background({"histogram": {"edges_gev": edges, "counts": counts}})
    assert window == 200 and sb == pytest.approx(0.0, abs=1e-9)
    counts = [10] * 15 + [40] * 20 + [10] * 15  # B = 300 x 0.4 / 0.6 = 200; S = 800 - 200
    window, sb = extras.jpsi_window_and_background({"histogram": {"edges_gev": edges, "counts": counts}})
    assert window == 800 and sb == pytest.approx(3.0)
    off_edges = [2.61 + 0.02 * i for i in range(51)]
    assert extras.jpsi_window_and_background({"histogram": {"edges_gev": off_edges, "counts": counts}}) is None


def test_the_toy_record_parses_every_format_the_tests_print():
    sys.path.insert(0, str(SCRIPTS))
    try:
        from record_test_metrics import parse
    finally:
        sys.path.pop(0)
    entries = parse("  pull test, 1,000 toys: mean +0.103, std 0.997\n"
                    "  cb_bw_exp Z-like pull test, 1,000 toys: mean -0.038, std 1.039, 0 failed fits\n"
                    "  cb2_bw_exp Z-like pull test, 1,000 toys, 34 failed fits (14 x): mean mean -0.046 std 1.033, "
                    "r mean -0.030 std 0.9\n")
    assert [e["n_failed"] for e in entries] == [0, 0, 34]
    assert entries[0]["pulls"]["mean"] == {"mean": 0.103, "std": 0.997}
    assert entries[2]["pulls"]["r"] == {"mean": -0.03, "std": 0.9} and entries[2]["pulls"]["mean"]["std"] == 1.033


def test_the_docs_are_an_extra_of_their_own_and_cffconvert_is_no_dependency():
    tomllib = pytest.importorskip("tomllib")
    extras = tomllib.loads((REPO / "pyproject.toml").read_text())["project"]["optional-dependencies"]
    assert not [d for d in extras["dev"] if d.startswith(("mkdocs", "mkdocstrings"))]
    assert {d.split(">")[0] for d in extras["docs"]} == {"mkdocs", "mkdocs-material", "mkdocstrings[python]"}
    assert not [d for group in extras.values() for d in group if "cffconvert" in d]


def test_a_missing_docs_extra_is_a_docs_build_failure_never_a_silent_skip(monkeypatch):
    sys.path[:0] = [str(SCRIPTS), str(REPO / "examples")]
    try:
        import apply_production
    finally:
        del sys.path[:2]
    monkeypatch.setattr(apply_production.importlib.util, "find_spec", lambda name: None)
    assert "not installed" in apply_production.docs_build_failure()


def test_the_pypi_description_pins_images_and_links_to_the_tag():
    sys.path.insert(0, str(SCRIPTS))
    try:
        from generate_release_files import pypi_readme
    finally:
        sys.path.pop(0)
    text = pypi_readme("![a](docs/figures/z.png) [b](DATA.md) [c](https://x.org/y) ![d](https://x.org/d.png)", "v1.2.3",
                       "https://github.com/O/R")
    assert text == ("![a](https://raw.githubusercontent.com/O/R/v1.2.3/docs/figures/z.png) "
                    "[b](https://github.com/O/R/blob/v1.2.3/DATA.md) [c](https://x.org/y) ![d](https://x.org/d.png)")


@pytest.mark.slow
def test_the_generated_pypi_readme_differs_from_the_github_readme_only_in_its_paths(applied):
    repo, _, _, _ = applied
    github, pypi = (repo / "README.md").read_text(), (repo / "README_PYPI.md").read_text()
    version = re.search(r'__version__ = "(.+)"', (REPO / "src" / "cmsopen" / "__init__.py").read_text()).group(1)
    assert "](docs/figures/z_peak_fit.png)" in github  # the GitHub README keeps its relative paths
    assert f"https://raw.githubusercontent.com/CyrilCquark/cmsopen/v{version}/docs/figures/z_peak_fit.png" in pypi
    assert not re.findall(r"\]\((?!https?://|#)[^)]+\)", pypi)
    assert re.sub(r"\]\([^)]*\)", "]", github) == re.sub(r"\]\([^)]*\)", "]", pypi)


@pytest.mark.slow
def test_data_md_gets_the_record_facts_and_keeps_what_it_had(applied):
    repo, _, _, _ = applied
    original = git(repo, "show", "HEAD:DATA.md")  # the copy's HEAD is the branch: DATA.md before the patch
    if "Records of the production sample" in original:  # past the apply step: the text at the freeze
        original = git(repo, "show", "35af6445db8d601972e60d3ba03f7c19a99527bb:DATA.md")
    patched = (repo / "DATA.md").read_text()
    kept = original.replace("| Events (whole record) | 35,455,705 in 74 files |", "")
    assert not [line for line in kept.splitlines() if line not in patched.splitlines()]
    for fact in ("## Records of the production sample", "[31123]", "10.7483/OPENDATA.CMS.YLIC.86ZZ", "| 57 | 56 |",
                 "| 74 | 73 |", "(73 separate files and one file that merges them)", "Cite as"):
        assert fact in patched, fact
    assert patched.count("## How to cite") == 1


@pytest.mark.slow
def test_every_registry_benchmark_has_an_observed_value_or_a_reason(applied):
    repo, app, _, _ = applied
    extras = extras_module()
    registry = extras.registry_rows(repo)
    assert len(registry) >= 15
    rows = json.loads((repo / "results" / "production_extras.json").read_text())["rows"]
    by_metric = {r["metric"]: r for r in rows}
    for metric, benchmark in registry:
        assert by_metric[metric]["benchmark"] == benchmark
        row = by_metric[metric]
        assert row["status"] != "not derivable" or row["observed"].startswith("not derivable: "), metric
    for name in ("README.md", "docs/validation.md"):
        text = (repo / name).read_text()
        assert all(metric in text for metric, _ in registry), name
    assert all(metric in (app / "numbers.md").read_text() for metric, _ in registry)
    toys = next(r for r in rows if r["metric"].startswith("Pull-test toys"))
    assert toys["source"] == "from the test suite, not production data" and toys["status"] != "not derivable"
    breakage = next(r for r in rows if r["metric"].startswith("Deliberate-breakage"))
    assert breakage["status"] == "not derivable"


@pytest.mark.slow
def test_a_toy_record_for_other_fit_code_is_reported_as_stale(fresh):
    extras = extras_module()
    path = fresh / "dev" / "test_metrics.json"
    record = json.loads(path.read_text())
    record["fitting_blob"] = "0" * 40
    path.write_text(json.dumps(record))
    tests, reason = extras.load_test_metrics(fresh)
    assert tests is None and "different fit code" in reason


@pytest.mark.slow
def test_the_email_is_left_out_by_default_and_goes_only_into_the_citation_on_request(fresh, tmp_path):
    address = json.loads((fresh / "templates" / "release_metadata.json").read_text())["email"]
    app = tmp_path / "a"
    out = apply(fresh, "--dry-run-data", "--self-checks-only", "--application-dir", str(app))
    assert out.returncode == 0, out.stdout + out.stderr
    for name in GENERATED:
        assert address not in (fresh / name).read_text(), name
    for path in app.glob("*.md"):
        assert address not in path.read_text(), path.name
    out = apply(fresh, "--dry-run-data", "--self-checks-only", "--include-email", "--application-dir", str(app))
    assert out.returncode == 0, out.stdout + out.stderr
    assert address in (fresh / "CITATION.cff").read_text() and address not in (fresh / ".zenodo.json").read_text()
    assert apply(fresh, "--check").returncode == 0  # a reader's check needs no flag


@pytest.mark.slow
def test_a_failed_rehearsal_says_so_and_changes_nothing(fresh, tmp_path):
    path = fresh / "templates" / "README.md"
    path.write_text(path.read_text().replace("## Licence", "The Z peak is at 91.234 GeV.\n\n## Licence"))
    before = tree_state(fresh)
    out = apply(fresh, "--rehearse", "--dry-run-data", "--self-checks-only", "--application-dir", str(tmp_path / "a"))
    assert out.returncode == 2 and "REHEARSAL FAILED" in out.stdout and "91.234" in out.stdout
    assert tree_state(fresh) == before and not (tmp_path / "a").exists()


@pytest.mark.slow
def test_a_rehearsal_on_dry_run_data_passes_in_a_marked_copy_and_changes_nothing(fresh, tmp_path):
    before = tree_state(fresh)
    out = apply(fresh, "--rehearse", "--dry-run-data", "--self-checks-only", "--application-dir", str(tmp_path / "a"))
    assert out.returncode == 0 and "REHEARSAL PASSED" in out.stdout, out.stdout + out.stderr
    assert "CITATION.cff" in out.stdout and tree_state(fresh) == before and not (tmp_path / "a").exists()


def test_the_repository_itself_is_never_marked_as_a_test_copy():
    assert not (REPO / "scripts" / ".production_test_copy").exists()
