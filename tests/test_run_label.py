"""cmsopen.datasets.run_label: the run periods of the input files, from the file listings only."""

import json

import pytest

from cmsopen.datasets import DEV_FILENAME, GENERIC_DATA_LABEL, run_label

B1, B2 = "B0000000-0000-0000-0000-000000000001.root", "B0000000-0000-0000-0000-000000000002.root"
C1, C2 = "C0000000-0000-0000-0000-000000000001.root", "C0000000-0000-0000-0000-000000000002.root"
ORIGINAL = "C0000000-0000-0000-0000-00000000000F.root"
SQRT_S = r"DoubleMuParked, $\sqrt{s}$ = 8 TeV"


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A project directory with a registry (B1 in 2012B, C1 in 2012C) and a development set (B2, C2, ORIGINAL)."""
    (tmp_path / "results").mkdir()
    (tmp_path / "dev").mkdir()
    (tmp_path / "data").mkdir()
    registry = {"records": [
        {"record_id": 1, "run_period": "Run2012C", "selected": [{"filename": C1}]},
        {"record_id": 2, "run_period": "Run2012B", "selected": [{"filename": B1}]},
    ]}
    (tmp_path / "results" / "production_files.json").write_text(json.dumps(registry))
    dev = {"original_development_file": ORIGINAL, "original_development_record_id": 1,
           "files": [{"filename": C2, "record_id": 1}, {"filename": B2, "record_id": 2}]}
    (tmp_path / "dev" / "development_set.json").write_text(json.dumps(dev))
    monkeypatch.chdir(tmp_path / "data")
    return tmp_path


def paths(repo, *names):
    return [repo / "data" / n for n in names]


def test_2012b_only(repo):
    assert run_label(paths(repo, B1, B2)) == f"2012B {SQRT_S}"


def test_2012c_only(repo):
    assert run_label(paths(repo, ORIGINAL, C1, C2)) == f"2012C {SQRT_S}"
    assert run_label(repo / "data" / ORIGINAL) == f"2012C {SQRT_S}"  # one path, not a list


def test_mixed_runs_are_listed_in_order(repo):
    assert run_label(paths(repo, C2, B1)) == f"2012B+2012C {SQRT_S}"


def test_unknown_files_get_the_generic_label(repo, tmp_path_factory):
    assert run_label(paths(repo, C1, "unknown.root")) == GENERIC_DATA_LABEL
    assert run_label([]) == GENERIC_DATA_LABEL
    elsewhere = tmp_path_factory.mktemp("nolisting")
    assert run_label([elsewhere / C1]) == f"2012C {SQRT_S}"  # found through the working directory's listing
    assert GENERIC_DATA_LABEL == r"CMS 2012 open data, DoubleMuParked, $\sqrt{s}$ = 8 TeV"


def test_no_listing_at_all_gives_the_generic_label(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert run_label([tmp_path / C1]) == GENERIC_DATA_LABEL


def test_only_the_label_is_printed(repo, capsys):
    run_label(paths(repo, B1, C1))
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""


def test_periods_come_from_the_registry_not_from_a_table(repo):
    reg = repo / "results" / "production_files.json"
    reg.write_text(reg.read_text().replace("Run2012B", "Run2012D"))
    assert run_label(paths(repo, B1, B2)) == f"2012D {SQRT_S}"


def test_the_real_development_file_is_2012c():
    # this repository's own listings (the test runs with the repository as the working directory)
    assert run_label([f"data/{DEV_FILENAME}"]) == f"2012C {SQRT_S}"
