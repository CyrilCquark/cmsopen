"""Edge cases and error paths of cmsopen.pipeline not covered by the end-to-end tests."""

import dataclasses
import json
from importlib import metadata
from pathlib import Path

import numpy as np
import pytest
from test_pipeline import write_z_file

import cmsopen.pipeline as pipeline
from cmsopen.pipeline import CHANNELS, AnalysisError, ChannelConfig, analyze, register_channel

Z = CHANNELS["Z_mumu"]


@pytest.fixture(scope="module")
def zfile(tmp_path_factory):
    return write_z_file(tmp_path_factory.mktemp("edge") / "z.root", 400, seed=8)


def run(path, **kw):
    kw.setdefault("model", "voigt_poly")  # the synthetic peak is Voigt-shaped (one resolution, no tail)
    return analyze(path, verbose=False, stability=False, **kw)


def test_channel_config_validation():
    with pytest.raises(ValueError, match="bins"):
        dataclasses.replace(Z, bins=0)
    with pytest.raises(ValueError, match="poly_degree"):
        dataclasses.replace(Z, poly_degree=-1)
    with pytest.raises(TypeError, match="ChannelConfig"):
        register_channel({"name": "x"})
    cfg = Z.to_dict()
    assert cfg["muon_cuts"] == dict(Z.muon_cuts) and cfg["triggers"] == list(Z.triggers)
    json.dumps(cfg)


@pytest.mark.parametrize(
    "kwargs, match",
    [
        ({"model": "breit_wigner"}, "model must be one of"),
        ({"chunk_size": 0}, "chunk_size"),
        ({"n_events": 0}, "n_events"),
        ({"config": "Z_mumu"}, "config must be a ChannelConfig"),
    ],
)
def test_argument_validation(zfile, kwargs, match):
    with pytest.raises((ValueError, TypeError), match=match):
        run(zfile, **kwargs)


def test_no_input_files():
    with pytest.raises(ValueError, match="no input files"):
        run([])


def test_unreadable_path_is_an_analysis_error(tmp_path):
    with pytest.raises(AnalysisError, match="cannot open"):
        run(tmp_path)  # a directory, not a file


def test_cut_fields_are_requested_from_the_file(zfile):
    cfg = dataclasses.replace(Z, name="ip", muon_cuts={"min_pt": 20.0, "max_abs_dxy": 0.2, "max_abs_dz": 0.5,
                                                       "global_muon": True, "max_eta": None})
    with pytest.raises(AnalysisError, match=r"Muon_dxy.*Muon_dz.*Muon_isGlobal.*Muon_isTracker"):
        run(zfile, config=cfg)
    assert pipeline._muon_fields({"global_muon": False, "min_pt": 20}) == ("pt", "eta", "phi", "mass", "charge")


def test_channel_without_trigger(zfile):
    cfg = dataclasses.replace(Z, name="notrig", triggers=())
    r = run(zfile, config=cfg)
    assert [s.name for s in r.cutflow][1] == "min_pt"  # no trigger row
    assert r.cutflow[0].n_events == 400 and len(r.masses) > len(run(zfile).masses)


def test_empty_file_has_no_events_to_analyse(tmp_path):
    empty = write_z_file(tmp_path / "empty.root", 1, seed=1)
    with pytest.raises(AnalysisError, match="too few pairs|no events"):
        run(empty)


def test_n_events_stops_before_the_second_file(zfile, tmp_path, monkeypatch):
    opened = []
    real = pipeline._open
    monkeypatch.setattr(pipeline, "_open", lambda p: opened.append(p) or real(p))
    r = run([zfile, tmp_path / "never_opened.root"], n_events=400)
    assert r.n_events == 400 and opened == [str(zfile), str(zfile)]  # planned and processed; the second never opened


def test_worker_function_in_process_reuses_its_open_file(zfile, tmp_path):
    other = write_z_file(tmp_path / "other.root", 50, seed=9)
    fields = pipeline._muon_fields(Z.muon_cuts)
    args = (Z.triggers, dict(Z.muon_cuts), Z.candidate_strategy, fields)
    pipeline._WORKER_FILE.clear()
    try:
        a = pipeline._chunk_worker(str(zfile), *args, 0, 200)
        first = pipeline._WORKER_FILE[str(zfile)]
        b = pipeline._chunk_worker(str(zfile), *args, 200, 400)
        assert pipeline._WORKER_FILE[str(zfile)] is first  # kept open
        pipeline._chunk_worker(str(other), *args, 0, 50)
        assert list(pipeline._WORKER_FILE) == [str(other)] and first._file.closed  # switched and closed
        serial = run(zfile, chunk_size=200)
        np.testing.assert_array_equal(np.concatenate([a.masses, b.masses]), serial.masses)
    finally:
        for ev in pipeline._WORKER_FILE.values():
            ev.close()
        pipeline._WORKER_FILE.clear()


def test_outdir_saves_in_process(zfile, tmp_path):
    analyze(zfile, verbose=False, stability=False, outdir=tmp_path / "out", model="voigt_poly")
    names = {p.name for p in (tmp_path / "out").iterdir()}
    assert {"cutflow.png", "mass_fit.png", "summary.json", "summary.txt"} <= names


def test_failed_stability_fits_are_reported(zfile):
    cfg = dataclasses.replace(Z, name="stab", stability_fit_ranges=((70.0, 110.0), (100.0, 110.0)),
                              stability_bin_widths=(1.0,))
    r = analyze(zfile, config=cfg, verbose=False, stability=True, model="voigt_poly")
    assert r.stability.failed and any("stability fits failed" in w for w in r.warnings)
    assert "Warnings:" in r.summary()


def test_result_without_alternate_fit(zfile):
    r = run(zfile, model="voigt_poly")
    alone = dataclasses.replace(r, alternate_fit=None, pdg={r.fit.model_name: r.pdg[r.fit.model_name]})
    d = alone.to_dict()
    assert d["alternate_fit"] is None and list(d["pdg_comparison"]) == [r.fit.model_name]
    text = alone.summary()
    assert "gauss_poly" not in text and "voigt_poly" in text


def test_jsonable_and_versions(monkeypatch):
    assert pipeline._jsonable({"p": Path("a/b"), "x": float("nan"), "n": np.int64(3), "t": (1, 2)}) == {
        "p": "a/b", "x": None, "n": 3, "t": [1, 2]}
    real = metadata.version

    def fake(pkg):
        if pkg == "particle":
            raise metadata.PackageNotFoundError(pkg)
        return real(pkg)

    monkeypatch.setattr(pipeline.metadata, "version", fake)
    assert pipeline._versions()["particle"] == "not installed"


def test_config_object_overrides_channel_name(zfile):
    cfg = dataclasses.replace(Z, name="custom", fit_range=(75.0, 105.0), model="voigt_poly")
    r = run(zfile, channel="does_not_matter", config=cfg)
    assert r.config is cfg and r.fit.fit_range == (75.0, 105.0)
    assert isinstance(r.config, ChannelConfig)


def test_analyze_docstring_explains_the_spawn_guard():
    doc = " ".join(analyze.__doc__.split())
    assert 'if __name__ == "__main__":' in doc and "macOS" in doc
