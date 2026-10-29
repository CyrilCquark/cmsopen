"""Parallel processing in cmsopen.analyze: results must be identical to the serial run."""

import dataclasses
import subprocess
import sys

import numpy as np
import pytest
from test_pipeline import write_z_file

from cmsopen.pipeline import CHANNELS, AnalysisError, analyze

pytestmark = pytest.mark.slow  # worker pools: every test here starts processes


@pytest.fixture(scope="module")
def files(tmp_path_factory):
    d = tmp_path_factory.mktemp("par")
    return write_z_file(d / "p1.root", 200, seed=4), write_z_file(d / "p2.root", 200, seed=5)


def run(path, **kw):
    # The synthetic files have a Voigt peak with no radiative tail, so the Voigt model is requested explicitly;
    # test_default_cb_model_parallel_equals_serial covers the channel's default (Crystal Ball) model.
    kw.setdefault("model", "voigt_poly")
    return analyze(path, verbose=False, stability=False, **kw)


def assert_identical(a, b):
    np.testing.assert_array_equal(a.masses, b.masses)
    np.testing.assert_array_equal(a.same_sign_masses, b.same_sign_masses)
    assert a.cutflow.to_records() == b.cutflow.to_records()
    np.testing.assert_array_equal(a.fit.values, b.fit.values)
    np.testing.assert_array_equal(a.fit.covariance, b.fit.covariance)
    np.testing.assert_array_equal(a.alternate_fit.values, b.alternate_fit.values)
    assert a.n_os_pairs == b.n_os_pairs and a.n_events == b.n_events
    assert a.summary() == b.summary()


@pytest.mark.parametrize("chunk_size", [1, 7, 100_000])
def test_one_file_parallel_equals_serial(files, chunk_size):
    serial = run(files[0], chunk_size=chunk_size)
    for workers in (2, 4):
        assert_identical(serial, run(files[0], chunk_size=chunk_size, n_workers=workers))


@pytest.mark.parametrize("chunk_size", [1, 7, 100_000])
def test_two_files_parallel_equals_serial(files, chunk_size):
    serial = run(list(files), chunk_size=chunk_size)
    for workers in (2, 4):
        assert_identical(serial, run(list(files), chunk_size=chunk_size, n_workers=workers))


def test_one_worker_is_serial_and_limits_apply(files):
    assert_identical(run(files[0], chunk_size=7), run(files[0], chunk_size=7, n_workers=1))
    limited = run(list(files), chunk_size=7, n_events=300, n_workers=3)
    assert limited.n_events == 300 and limited.cutflow[0].n_events == 300
    assert_identical(run(list(files), chunk_size=7, n_events=300), limited)


def test_worker_error_names_file_and_chunk(files):
    cfg = dataclasses.replace(CHANNELS["Z_mumu"], name="broken", muon_cuts={"not_a_cut": 1.0})
    with pytest.raises(AnalysisError, match=rf"worker failed on {files[0]}, chunk 0 \(events 0-50\): TypeError"):
        run(files[0], config=cfg, chunk_size=50, n_workers=2)
    with pytest.raises(AnalysisError, match=rf"{files[0]}, chunk 0 \(events 0-50\) failed: TypeError"):
        run(files[0], config=cfg, chunk_size=50)  # serial reports it the same way


@pytest.mark.parametrize("bad", [0, -2, 1.5, True])
def test_invalid_worker_counts(files, bad):
    with pytest.raises(ValueError, match="n_workers"):
        run(files[0], n_workers=bad)


def test_cli_workers(tmp_path, files):
    out = subprocess.run(
        [
            sys.executable,
            "-m",
            "cmsopen",
            "analyze",
            str(files[0]),
            "--workers",
            "2",
            "--chunk-size",
            "50",
            "--no-stability",
            "--model",
            "voigt_poly",
            "--outdir",
            str(tmp_path / "w"),
        ],
        capture_output=True,
        text=True,
    )
    assert out.returncode == 0, out.stderr
    serial = subprocess.run(
        [
            sys.executable,
            "-m",
            "cmsopen",
            "analyze",
            str(files[0]),
            "--chunk-size",
            "50",
            "--no-stability",
            "--model",
            "voigt_poly",
            "--outdir",
            str(tmp_path / "s"),
        ],
        capture_output=True,
        text=True,
    )
    assert serial.returncode == 0
    assert (tmp_path / "w" / "summary.json").read_bytes() == (tmp_path / "s" / "summary.json").read_bytes()
    assert out.stdout.replace(str(tmp_path / "w"), "") == serial.stdout.replace(str(tmp_path / "s"), "")


def test_default_cb_model_parallel_equals_serial(tmp_path):
    """The channel's default model (cb_bw_exp for Z_mumu) on a file with a radiative tail: identical in parallel."""
    f = write_z_file(tmp_path / "fsr.root", 3000, seed=3, fsr=0.3)
    serial = analyze(f, verbose=False, stability=True, chunk_size=500)
    parallel = analyze(f, verbose=False, stability=True, chunk_size=500, n_workers=2)
    assert serial.fit.model_name == "cb_bw_exp"
    assert_identical(serial, parallel)
