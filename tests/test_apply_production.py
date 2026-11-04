"""Tests of the post-production path: scripts/apply_production.py and everything it writes.

All of it happens in temporary copies of the repository; nothing is written to the repository itself. The copy holds
the saved dry-run output if it exists on this machine (with placeholder figures), or else the output of a real
production run on the synthetic registry, so the tests also run where no dry-run output is available.
"""

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
from test_production import clone_working_tree, git, make_copy, record_gates, run

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"
sys.path.insert(0, str(SCRIPTS))
from release_lib import NumberAudit, audit_numbers, lint_template, tokens  # noqa: E402

sys.path.pop(0)
GENERATED = (
    "README.md",
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


def apply(repo, *args):
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
    for line in (
        "OK: README results block equals",
        "OK: CITATION.cff follows the CFF",
        "OK: every number traces",
        "OK: mkdocs build --strict",
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
        if name not in ("docs/api.md", "docs/changelog.md"):  # these two state no result
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
    assert cff["authors"][0]["family-names"] == "Nadar" and cff["authors"][0]["email"] == "Cyril.nadar1@gmail.com"
    assert cff["license"] == zenodo["license"] == "MIT"
    assert "TODO" in (repo / "CITATION.cff").read_text() and zenodo["creators"][0]["orcid"] == "TODO"
    assert "10.7483/OPENDATA.CMS.M5AD.Y3V3" in (repo / "CITATION.cff").read_text()
    strict = script(repo, "check_release_metadata.py", "--release")
    assert strict.returncode == 1 and "TODO" in strict.stdout


# --- refusals: nothing is written


@pytest.fixture
def fresh(tmp_path, applied):
    """A copy with the production file, before the apply step."""
    repo = tmp_path / "repo"
    clone_working_tree(repo)
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


@pytest.mark.slow
def test_apply_after_a_real_production_run_on_the_synthetic_registry(tmp_path):
    repo = real_run_output(tmp_path)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "production outputs (test)")
    app = tmp_path / "application"
    out = apply(repo, "--self-checks-only", "--application-dir", str(app))
    assert out.returncode == 0 and "APPLY COMPLETE" in out.stdout, out.stdout + out.stderr
    for name in GENERATED:
        text = (repo / name).read_text()
        assert DRY not in text, name
        assert "SYNTH-" not in text, name
    assert DRY not in (app / "numbers.md").read_text()
    assert apply(repo, "--check").returncode == 0
    (repo / "results" / "production.json").write_text((repo / "results" / "production.json").read_text() + " ")
    out = apply(repo, "--check")  # the README states the file's hash, so a changed file is noticed
    assert out.returncode == 1 and "README.md differs" in out.stdout


def test_the_repository_itself_is_never_marked_as_a_test_copy():
    assert not (REPO / "scripts" / ".production_test_copy").exists()
