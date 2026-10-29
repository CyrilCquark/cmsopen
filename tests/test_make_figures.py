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
    # the synthetic peaks have one resolution: voigt_poly describes them (the default mixture cannot be fitted)
    a, b = two_files
    return (make_figures.build(a, "voigt_poly"), make_figures.build(b, "voigt_poly"),
            make_figures.build([a, b], "voigt_poly"))


@pytest.mark.slow
def test_two_files_give_the_sum_of_their_histograms_and_cutflows(built):
    fa, fb, both = built
    for name in ("z_peak", "os", "ss"):
        assert np.array_equal(both.histograms[name].counts,
                              fa.histograms[name].counts + fb.histograms[name].counts), name
    for ra, rb, rboth in zip(fa.cutflow, fb.cutflow, both.cutflow, strict=True):
        assert (rboth.n_events, rboth.n_particles) == (ra.n_events + rb.n_events, ra.n_particles + rb.n_particles)
    assert set(both.figures) == set(make_figures.EXPECTED) and set(both.fits) == {"voigt_poly", "gauss_poly"}
    assert (both.main_model, both.other_model) == ("voigt_poly", "gauss_poly")
    assert both.histograms["z_peak"].counts.sum() > fa.histograms["z_peak"].counts.sum()


@pytest.mark.slow
def test_one_file_as_a_path_or_a_list_is_the_same(two_files, built):
    a, _ = two_files
    single = make_figures.build([a], "voigt_poly")
    assert np.array_equal(single.histograms["z_peak"].counts, built[0].histograms["z_peak"].counts)
    assert np.array_equal(single.fits["voigt_poly"].values, built[0].fits["voigt_poly"].values)


@pytest.mark.slow
def test_write_lists_every_file_in_the_readme(two_files, built, tmp_path):
    a, b = two_files
    make_figures.write(built[2], tmp_path)
    text = (tmp_path / "README.md").read_text()
    assert "2 NanoAOD Run 1 files (CMS 2012 open data, DoubleMuParked, sqrt(s) = 8 TeV)" in text  # not listed
    assert text.index(f"`{a.name}` | {a.stat().st_size:,} |") < text.index(f"`{b.name}` | {b.stat().st_size:,} |")
    assert f"--file data/{a.name} data/{b.name} --model voigt_poly" in text
    make_figures.write(built[0], tmp_path / "one")
    one = (tmp_path / "one" / "README.md").read_text()
    assert f"`{a.name}` ({a.stat().st_size:,} bytes): CMS 2012 open data, DoubleMuParked, sqrt(s) = 8 TeV" in one
    caption = (tmp_path / "one" / "z_peak_fit_caption.md").read_text()
    assert "- `voigt_poly` (shown)" in caption and "- `gauss_poly` (same data" in caption


def test_cli_passes_every_file_in_order(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(make_figures, "build", lambda paths, model=None: calls.append((paths, model))
                        or make_figures.Figures())
    monkeypatch.setattr(make_figures, "write", lambda figs, outdir: figs)
    files = [tmp_path / n for n in ("c.root", "a.root", "b.root")]
    assert make_figures.main(["--file", str(files[0]), str(files[1]), "--outdir", str(tmp_path / "o")]) == 0
    assert make_figures.main(["--file", str(files[0]), "--file", str(files[1]), str(files[2]),
                              "--outdir", str(tmp_path / "o")]) == 0
    assert make_figures.main(["--file", str(files[0]), "--model", "voigt_poly", "--outdir", str(tmp_path / "o")]) == 0
    assert calls == [([p.resolve() for p in files[:2]], None), ([p.resolve() for p in files], None),
                     ([files[0].resolve()], "voigt_poly")]


def test_the_default_model_is_the_channel_default():
    from cmsopen.pipeline import _ALTERNATE_MODEL, CHANNELS

    assert make_figures.MAIN_MODEL == CHANNELS["Z_mumu"].model == "cb2_bw_exp"
    assert make_figures.OTHER_MODEL == _ALTERNATE_MODEL["cb2_bw_exp"] == "voigt_poly"
    with pytest.raises(ValueError, match="model must be one of"):
        make_figures.build([Path("x.root")], "lorentz")


def test_build_needs_a_file():
    with pytest.raises(ValueError, match="at least one file"):
        make_figures.build([])


@pytest.mark.slow
def test_chunked_reading_gives_identical_figures_and_tables(two_files, tmp_path):
    """Reading in small chunks (histogramming pT and eta per chunk) changes no number and no byte of any figure."""
    a, b = two_files
    small = make_figures.build([a, b], "voigt_poly", chunk_size=1_000)
    whole = make_figures.build([a, b], "voigt_poly", chunk_size=10**9)  # one chunk per file
    for name in ("z_peak", "os", "ss"):
        assert np.array_equal(small.histograms[name].counts, whole.histograms[name].counts), name
    assert np.array_equal(small.fits["voigt_poly"].values, whole.fits["voigt_poly"].values)
    assert small.cutflow.to_records() == whole.cutflow.to_records()
    make_figures.write(small, tmp_path / "small")
    make_figures.write(whole, tmp_path / "whole")
    files = sorted(p.name for p in (tmp_path / "whole").iterdir())
    assert files == sorted(p.name for p in (tmp_path / "small").iterdir())
    for name in files:
        assert (tmp_path / "small" / name).read_bytes() == (tmp_path / "whole" / name).read_bytes(), name


def test_binned_values_give_the_same_figure_as_raw_values(tmp_path):
    from cmsopen.plotting import (
        ETA_EDGES_DEFAULT,
        PT_EDGES_DEFAULT,
        BinnedValues,
        plot_eta_distribution,
        plot_pt_distribution,
        save_figure,
    )

    rng = np.random.default_rng(3)
    pt_sel, pt_all = rng.exponential(30.0, 5000) + 20.0, rng.exponential(8.0, 40000)
    eta_sel, eta_all = rng.uniform(-2.4, 2.4, 5000), rng.normal(0.0, 4.0, 40000)
    halves = [slice(0, 17000), slice(17000, None)]
    binned_all = BinnedValues.from_values(pt_all[halves[0]], PT_EDGES_DEFAULT) + BinnedValues.from_values(
        pt_all[halves[1]], PT_EDGES_DEFAULT)
    pairs = [
        (plot_pt_distribution(pt_sel, before=pt_all)[0],
         plot_pt_distribution(BinnedValues.from_values(pt_sel, PT_EDGES_DEFAULT), before=binned_all)[0]),
        (plot_eta_distribution(eta_sel, before=eta_all)[0],
         plot_eta_distribution(BinnedValues.from_values(eta_sel, ETA_EDGES_DEFAULT),
                               before=BinnedValues.from_values(eta_all, ETA_EDGES_DEFAULT))[0]),
    ]
    for i, (raw, binned) in enumerate(pairs):
        (p1,) = save_figure(raw, tmp_path / f"raw{i}", formats=("png",))
        (p2,) = save_figure(binned, tmp_path / f"binned{i}", formats=("png",))
        assert p1.read_bytes() == p2.read_bytes()
    assert binned_all.n_total == 40000 and binned_all.n_outside == int(np.sum(pt_all >= 200.0))
    with pytest.raises(ValueError, match="different bin edges"):
        binned_all + BinnedValues.from_values(pt_sel, np.linspace(0, 100, 11))
    with pytest.raises(ValueError, match="edges differ"):
        plot_pt_distribution(BinnedValues.from_values(pt_sel, np.linspace(0, 100, 11)))
