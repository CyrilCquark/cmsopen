"""examples/make_figures.py on several files: the figures of a list of files are those of their union, in order."""

import sys
from pathlib import Path

import numpy as np
import pytest
from test_pipeline import write_z_file

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples"))
import make_figures  # noqa: E402

sys.path.pop(0)


@pytest.fixture(scope="module")
def two_files(tmp_path_factory):
    d = tmp_path_factory.mktemp("figs")
    return (write_z_file(d / "a.root", 12_000, seed=41, full_branches=True),
            write_z_file(d / "b.root", 9_000, seed=42, full_branches=True))


@pytest.fixture(scope="module")
def built(two_files):
    a, b = two_files
    return make_figures.build(a), make_figures.build(b), make_figures.build([a, b])


@pytest.mark.slow
def test_two_files_give_the_sum_of_their_histograms_and_cutflows(built):
    fa, fb, both = built
    for name in ("z_peak", "os", "ss"):
        assert np.array_equal(both.histograms[name].counts,
                              fa.histograms[name].counts + fb.histograms[name].counts), name
    for ra, rb, rboth in zip(fa.cutflow, fb.cutflow, both.cutflow, strict=True):
        assert (rboth.n_events, rboth.n_particles) == (ra.n_events + rb.n_events, ra.n_particles + rb.n_particles)
    assert set(both.figures) == set(make_figures.EXPECTED) and set(both.fits) == {"voigt_poly", "gauss_poly"}
    assert both.histograms["z_peak"].counts.sum() > fa.histograms["z_peak"].counts.sum()


@pytest.mark.slow
def test_one_file_as_a_path_or_a_list_is_the_same(two_files, built):
    a, _ = two_files
    single = make_figures.build([a])
    assert np.array_equal(single.histograms["z_peak"].counts, built[0].histograms["z_peak"].counts)
    assert np.array_equal(single.fits["voigt_poly"].values, built[0].fits["voigt_poly"].values)


@pytest.mark.slow
def test_write_lists_every_file_in_the_readme(two_files, built, tmp_path):
    a, b = two_files
    make_figures.write(built[2], tmp_path)
    text = (tmp_path / "README.md").read_text()
    assert "2 DoubleMuParked NanoAOD Run 1 files" in text
    assert text.index(f"`{a.name}` | {a.stat().st_size:,} |") < text.index(f"`{b.name}` | {b.stat().st_size:,} |")
    assert f"--file data/{a.name} data/{b.name}" in text
    make_figures.write(built[0], tmp_path / "one")
    one = (tmp_path / "one" / "README.md").read_text()
    assert f"`{a.name}` ({a.stat().st_size:,} bytes): Run2012C DoubleMuParked" in one


def test_cli_passes_every_file_in_order(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(make_figures, "build", lambda paths: calls.append(paths) or make_figures.Figures())
    monkeypatch.setattr(make_figures, "write", lambda figs, outdir: figs)
    files = [tmp_path / n for n in ("c.root", "a.root", "b.root")]
    assert make_figures.main(["--file", str(files[0]), str(files[1]), "--outdir", str(tmp_path / "o")]) == 0
    assert make_figures.main(["--file", str(files[0]), "--file", str(files[1]), str(files[2]),
                              "--outdir", str(tmp_path / "o")]) == 0
    assert calls == [[p.resolve() for p in files[:2]], [p.resolve() for p in files]]


def test_build_needs_a_file():
    with pytest.raises(ValueError, match="at least one file"):
        make_figures.build([])
