"""scripts/rerender_production_figures.py, on a synthetic production in a TEMPORARY copy of the repository."""

import hashlib
import json

import pytest
from test_production import git, make_copy, record_gates, run


def figure_hashes(repo):
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (repo / "docs" / "figures").iterdir()}


@pytest.mark.slow
@pytest.mark.timeout(900)
def test_the_rerender_writes_only_if_every_number_is_equal(tmp_path, capsys):
    repo, _ = make_copy(tmp_path)
    record_gates(repo)
    out = run(repo, "production_run.py", "--confirm-single-production-run", "--workers", "2")
    assert out.returncode == 0, out.stdout + out.stderr
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "synthetic production")
    production = repo / "results" / "production.json"
    original = production.read_text()
    provenance = repo / "results" / "figures_rerender.json"
    before = figure_hashes(repo)

    # a dirty tree is refused before any analysis
    (repo / "scratch.txt").write_text("x\n")
    out = run(repo, "rerender_production_figures.py")
    assert out.returncode == 2 and "not clean" in out.stdout
    (repo / "scratch.txt").unlink()

    # one recorded number differs: nothing written, and the difference is named
    data = json.loads(original)
    data["channels"]["Z_mumu"]["result"]["peak_position_gev"] += 1e-7
    data["channels"]["Jpsi_mumu"]["per_file"][0]["peak_position_gev"] *= 1 + 1e-6
    production.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    git(repo, "commit", "-qam", "tampered")
    out = run(repo, "rerender_production_figures.py", "--workers", "2")
    with capsys.disabled():
        print("\n" + out.stdout)
    assert out.returncode == 3, out.stdout + out.stderr
    assert "NUMBERS DIFFER" in out.stdout and "NOTHING WRITTEN" in out.stdout
    assert "DIFFERS: channels.Z_mumu.result.peak_position_gev" in out.stdout
    assert "DIFFERS: channels.Jpsi_mumu.per_file[0].peak_position_gev" in out.stdout
    assert not provenance.exists() and figure_hashes(repo) == before
    assert "SYNTH-" not in out.stdout

    # everything equal: written, with the provenance
    production.write_text(original)
    git(repo, "commit", "-qam", "restored")
    head = git(repo, "rev-parse", "HEAD").strip()
    out = run(repo, "rerender_production_figures.py", "--workers", "2")
    with capsys.disabled():
        print(out.stdout)
    assert out.returncode == 0, out.stdout + out.stderr
    assert "ALL NUMBERS EQUAL" in out.stdout and "SYNTH-" not in out.stdout
    assert production.read_text() == original
    record = json.loads(provenance.read_text())
    assert record["commit"] == head and record["reason"] == "layout and caption polish"
    checks = record["verification"]["checks"]
    assert checks["Z_mumu"]["differences"] == checks["Jpsi_mumu"]["differences"] == 0
    assert checks["Z_mumu"]["values_compared_exactly"] > 100
    assert set(checks["layout"]) >= {"z_peak_fit", "jpsi_peak_fit", "z_os_vs_ss", "jpsi_os_vs_ss", "muon_pt",
                                     "muon_eta", "cutflow"}
    assert all(row["overlaps"] == row["text_below_8_pt"] == 0 for row in checks["layout"].values())
    assert checks["Z_mumu"]["summary_json_identical_to_the_saved_run"] is True
    assert {f"docs/figures/{n}": h for n, h in figure_hashes(repo).items()} == record["figures"]
    assert "SYNTH-" not in provenance.read_text()
    assert record["timing_s"]["total_s"] > 0

    # the freeze check accepts the result, and refuses a figure edited afterwards
    since = git(repo, "rev-parse", "HEAD").strip()
    out = run(repo, "check_docs_frozen.py", "--since", since)
    assert out.returncode == 0, out.stdout
    (repo / "docs" / "figures" / "cutflow.png").write_bytes(b"edited by hand")
    out = run(repo, "check_docs_frozen.py", "--since", since)
    assert out.returncode == 1 and "cutflow.png differs from its hash" in out.stdout
