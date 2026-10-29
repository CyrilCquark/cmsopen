"""Tests for cmsopen.pipeline (Layer 8 core) and the command-line interface."""

import dataclasses
import json
import math
import os
import shutil
import subprocess
import sys
from pathlib import Path

import awkward as ak
import numpy as np
import pytest
import uproot
from synthetic import REAL_FILE, _write_ttree

import cmsopen
from cmsopen.fitting import FitWarning, pdg_mass_width
from cmsopen.pipeline import (
    CHANNELS,
    PROTECTED_DIRS,
    PROTECTED_FILES,
    AnalysisError,
    AnalysisResult,
    analyze,
    register_channel,
)
from cmsopen.selection import CutFlow, CutStep

M_MU = 0.1056583755
TRUE_MASS, TRUE_SIGMA = 91.0, 1.5  # injected peak position and Gaussian resolution, GeV (synthetic)


def write_z_file(
    path,
    n_events,
    seed=1,
    triggers=("HLT_Mu17_Mu8", "HLT_Mu17_TkMu8"),
    tree="Events",
    fsr=0.0,
    y_max=0.5,
    region_shift=None,
    plus_phi_shift=None,
    npv=False,
    medium_id=False,
    wide_fraction=0.0,
    wide_sigma=None,
):
    """A NanoAOD-like file: one Z-like or background opposite-sign pair per event, plus junk muons.

    Signal masses follow a Breit-Wigner of the PDG Z width convolved with a Gaussian of TRUE_SIGMA,
    centred on TRUE_MASS; the background falls exponentially. Junk muons are soft or outside |eta| < 2.4,
    and 5 % of events have one pair muon non-isolated, so the cuts have work to do. With ``fsr`` > 0, that fraction
    of signal events loses an exponentially distributed mass (mean 4 GeV): a radiative low-mass tail.

    Validation options (all off by default, leaving the file and the random stream unchanged): ``y_max`` is the
    half range of the pair rapidity (wider puts muons in the endcaps); ``region_shift`` = (BB, BE, EE) and
    ``plus_phi_shift`` = 4 values, one per mu+ phi quarter [-pi, -pi/2), ..., [pi/2, pi], add known mass shifts
    (GeV) to every pair of that category before the muon momenta are built; ``npv`` writes PV_npvsGood (uniform
    0-34, from a separate random stream); ``medium_id`` writes Muon_mediumId (true for the pair muons).
    ``wide_fraction`` > 0 gives that fraction of signal events a total Gaussian resolution ``wide_sigma`` (GeV)
    instead of TRUE_SIGMA: a two-resolution mixture, like barrel and endcap pairs (separate random stream).
    """
    rng = np.random.default_rng(seed)
    gamma = 0.5 * pdg_mass_width("Z")[2]
    n = n_events
    is_sig = rng.random(n) < 0.8
    m = np.empty(n)
    mix_rng = np.random.default_rng(seed + 3000) if wide_fraction else None
    for _ in range(50):  # rejection sampling into 60-120 GeV, vectorized over events
        bad = ~((m >= 60) & (m < 120)) if _ else np.ones(n, bool)
        k = int(bad.sum())
        if k == 0:
            break
        sig = TRUE_MASS + gamma * rng.standard_cauchy(k) + TRUE_SIGMA * rng.standard_normal(k)
        if fsr:
            sig -= np.where(rng.random(k) < fsr, rng.exponential(4.0, k), 0.0)
        if mix_rng is not None:  # widen a fraction of events to wide_sigma (resolutions add in quadrature)
            extra = math.sqrt(wide_sigma**2 - TRUE_SIGMA**2)
            sig = sig + np.where(mix_rng.random(k) < wide_fraction, mix_rng.normal(0.0, extra, k), 0.0)
        bkg = 60 + rng.exponential(25.0, k)
        m[bad] = np.where(is_sig[bad], sig, bkg)
    a = rng.uniform(-0.8, 0.8, n)
    y = rng.uniform(-y_max, y_max, n)
    if region_shift is not None or plus_phi_shift is not None:
        extra = np.random.default_rng(seed + 1000)  # a separate stream: the default file is unchanged
        phi1_pre = extra.uniform(-np.pi, np.pi, n)
        q_pre = extra.choice([-1, 1], n)
    else:
        phi1_pre = q_pre = None
    if region_shift is not None:
        barrel = np.abs(np.column_stack([y + a, y - a])) < 1.2
        region = 2 - barrel.sum(axis=1)  # 0 BB, 1 BE, 2 EE
        m = m + np.asarray(region_shift, dtype=float)[region]
    if plus_phi_shift is not None:
        phi_plus = np.where(q_pre > 0, phi1_pre, np.mod(phi1_pre + 2 * np.pi, 2 * np.pi) - np.pi)
        quarter = np.clip(np.floor((phi_plus + np.pi) / (np.pi / 2)).astype(int), 0, 3)
        m = m + np.asarray(plus_phi_shift, dtype=float)[quarter]
    pt = m / (2 * np.cosh(a))  # massless back-to-back legs in the transverse plane: m = 2 pt cosh(a)
    phi1 = rng.uniform(-np.pi, np.pi, n)
    phi2 = np.mod(phi1 + 2 * np.pi, 2 * np.pi) - np.pi
    q = rng.choice([-1, 1], n)
    if phi1_pre is not None:  # the shifted categories were drawn from these angles and charges
        phi1, q = phi1_pre, q_pre
        phi2 = np.mod(phi1 + 2 * np.pi, 2 * np.pi) - np.pi
    iso2 = np.where(rng.random(n) < 0.05, 0.5, 0.02)
    pair = {
        "pt": np.column_stack([pt, pt]), "eta": np.column_stack([y + a, y - a]), "phi": np.column_stack([phi1, phi2]),
        "mass": np.full((n, 2), M_MU), "charge": np.column_stack([q, -q]),
        "tightId": np.ones((n, 2), bool), "pfRelIso04_all": np.column_stack([np.full(n, 0.02), iso2]),
    }
    if medium_id:
        pair["mediumId"] = np.ones((n, 2), bool)
    n_junk = rng.integers(0, 4, n)
    tot = int(n_junk.sum())
    soft = rng.random(tot) < 0.5
    junk = {
        "pt": np.where(soft, rng.uniform(1, 15, tot), rng.uniform(25, 60, tot)),
        "eta": np.where(soft, rng.uniform(-2.3, 2.3, tot), rng.choice([-1, 1], tot) * rng.uniform(2.6, 8.0, tot)),
        "phi": rng.uniform(-np.pi, np.pi, tot), "mass": np.full(tot, M_MU), "charge": rng.choice([-1, 1], tot),
        "tightId": rng.random(tot) < 0.5, "pfRelIso04_all": rng.uniform(0, 1, tot),
    }
    if medium_id:
        junk["mediumId"] = junk["tightId"] | (junk["pfRelIso04_all"] < 0.3)
    muon = {}
    for k in pair:
        dtype = {"charge": np.int32, "tightId": bool, "mediumId": bool}.get(k, np.float32)
        left = ak.values_astype(ak.Array(pair[k].tolist()), dtype)
        right = ak.values_astype(ak.unflatten(junk[k], n_junk), dtype)
        muon[k] = ak.concatenate([left, right], axis=1)
    u = rng.random(n)
    branches = {
        "run": np.full(n, 194050, np.uint32), "luminosityBlock": np.arange(n, dtype=np.uint32) // 100,
        "event": np.arange(1, n + 1, dtype=np.uint64), "Muon": ak.zip(muon),
    }
    if npv:
        branches["PV_npvsGood"] = np.random.default_rng(seed + 2000).integers(0, 35, n).astype(np.int32)
    fired = {"HLT_Mu17_Mu8": u < 0.7, "HLT_Mu17_TkMu8": (u >= 0.6) & (u < 0.9)}
    for t in triggers:
        branches[t] = fired[t]
    with uproot.recreate(path) as f:
        _write_ttree(f, tree, branches)
    return path


@pytest.fixture(scope="module")
def big_file(tmp_path_factory):
    return write_z_file(tmp_path_factory.mktemp("z") / "big.root", 20_000, seed=11)


@pytest.fixture(scope="module")
def small_files(tmp_path_factory):
    d = tmp_path_factory.mktemp("small")
    return write_z_file(d / "a.root", 600, seed=2), write_z_file(d / "b.root", 500, seed=3)


def run(path, **kw):
    kw.setdefault("verbose", False)
    kw.setdefault("stability", False)
    # The synthetic peaks are Voigt-shaped (one resolution, no radiative tail): the Voigt model describes them. The
    # channels' default models (resolution mixtures) are exercised on suitable files in test_fitting_cb*.py.
    kw.setdefault("model", "voigt_poly")
    return analyze(path, **kw)


# -- 1. end to end --------------------------------------------------------------------------------------


def test_end_to_end_recovers_injected_peak(big_file):
    r = run(big_file, stability=True, model="voigt_poly")  # the synthetic truth is a Voigt peak with no tail
    assert isinstance(r, AnalysisResult)
    m, me = r.fit.peak_position
    s, _ = r.fit.resolution
    assert abs(m - TRUE_MASS) < 3 * me, (m, me)
    assert abs(s - TRUE_SIGMA) / TRUE_SIGMA < 0.10, s
    assert r.fit.model_name == "voigt_poly" and r.alternate_fit.model_name == "gauss_poly"
    assert set(r.pdg) == {"voigt_poly", "gauss_poly"}
    assert r.stability is not None and r.stability.n_fits == 54
    assert set(r.figures) >= {"mass_fit", "cutflow"}
    assert r.n_events == 20_000 and r.cutflow[0].n_events == 20_000
    # junk is removed: every selected pair comes from the injected pair muons
    assert len(r.masses) <= 20_000 and np.all((r.masses > 59.9) & (r.masses < 120.1))
    assert [s.name for s in r.cutflow] == ["all events", "require_trigger", "min_pt", "max_eta", "quality_id",
                                          "max_rel_iso", "require"]
    assert set(r.versions) == {"python", "cmsopen", "uproot", "awkward", "numpy", "scipy", "particle", "matplotlib"}


# -- 2. chunking is exact ------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def tiny_file(tmp_path_factory):
    """200 events: enough for a fit, small enough for chunk_size=1 (one read per event)."""
    return write_z_file(tmp_path_factory.mktemp("tiny") / "tiny.root", 200, seed=4)


@pytest.mark.slow
def test_chunked_equals_unchunked(tiny_file):
    f = tiny_file
    results = [run(f, chunk_size=c, model="voigt_poly") for c in (1, 7, 10_000)]  # Voigt-shaped synthetic data
    ref = results[-1]
    for r in results[:-1]:
        np.testing.assert_array_equal(r.masses, ref.masses)
        np.testing.assert_array_equal(r.same_sign_masses, ref.same_sign_masses)
        assert r.cutflow.to_records() == ref.cutflow.to_records()
        np.testing.assert_array_equal(r.fit.values, ref.fit.values)
        np.testing.assert_array_equal(r.fit.covariance, ref.fit.covariance)
        assert r.fit.chi2 == ref.fit.chi2 and r.n_os_pairs == ref.n_os_pairs


def test_cutflow_combine():
    a = CutFlow([CutStep("all events", {}, "start", 10, 8, 9), CutStep("min_pt", {"value": 20.0}, "particle", 4, 3, 9)])
    b = CutFlow([CutStep("all events", {}, "start", 5, 5, 6), CutStep("min_pt", {"value": 20.0}, "particle", 2, 2, 6)])
    c = CutFlow.combine([a, b])
    assert [(s.n_particles, s.n_events_with_particles, s.n_events) for s in c] == [(15, 13, 15), (6, 5, 15)]
    assert CutFlow.combine([a]).to_records() == a.to_records()
    other = CutFlow(
        [CutStep("all events", {}, "start", 1, 1, 1), CutStep("min_pt", {"value": 25.0}, "particle", 1, 1, 1)]
    )
    with pytest.raises(ValueError, match="different cuts"):
        CutFlow.combine([a, other])
    with pytest.raises(ValueError):
        CutFlow.combine([])


# -- 3. limits and several files ----------------------------------------------------------------------------------


@pytest.mark.slow
def test_n_events_and_two_files(small_files):
    f1, f2 = small_files
    voigt = {"model": "voigt_poly"}  # Voigt-shaped synthetic data, no radiative tail
    r = run(f1, n_events=400, **voigt)
    assert r.n_events == 400 and r.cutflow[0].n_events == 400
    a, b, both = run(f1, **voigt), run(f2, **voigt), run([f1, f2], **voigt)
    assert both.n_events == a.n_events + b.n_events == 1100
    assert both.cutflow.to_records() == CutFlow.combine([a.cutflow, b.cutflow]).to_records()
    np.testing.assert_array_equal(both.masses, np.concatenate([a.masses, b.masses]))
    assert both.files == [str(f1), str(f2)]
    limited = run([f1, f2], n_events=700, **voigt)  # all of the first file, 100 events of the second
    assert limited.n_events == 700 and limited.cutflow[0].n_events == 700


# -- 4. errors --------------------------------------------------------------------------------------------------------


def test_unknown_channel_lists_valid_names(small_files):
    with pytest.raises(ValueError, match="valid channels: Jpsi_mumu, Z_mumu"):
        run(small_files[0], channel="W_munu")


def test_missing_file_wrong_tree_and_missing_branch(tmp_path, small_files):
    with pytest.raises(AnalysisError, match="file not found"):
        run(tmp_path / "nope.root")
    wrong = write_z_file(tmp_path / "wrong.root", 50, tree="Other")
    with pytest.raises(AnalysisError, match="not a usable NanoAOD file"):
        run(wrong)
    no_trig = write_z_file(tmp_path / "notrig.root", 50, triggers=("HLT_Mu17_Mu8",))
    with pytest.raises(AnalysisError, match="HLT_Mu17_TkMu8"):
        run(no_trig)


def test_no_survivors_names_the_last_cut(small_files):
    cfg = dataclasses.replace(CHANNELS["Z_mumu"], name="tough", muon_cuts={"min_pt": 1000.0})
    with pytest.raises(
        AnalysisError,
        match=r"after 'trigger\(HLT_Mu17_Mu8 OR HLT_Mu17_TkMu8\)' \(the last cut that kept "
        r"events\), 0 after 'min_pt\(1000\)'",
    ):
        run(small_files[0], config=cfg)


def test_too_few_pairs_is_an_analysis_error(small_files):
    with pytest.raises(AnalysisError, match="too few pairs"):
        run(small_files[0], n_events=30)
    cfg = dataclasses.replace(CHANNELS["Z_mumu"], name="nofit", min_pairs=1)
    with pytest.raises(AnalysisError, match="fit failed"):  # a FitError is wrapped, not raised raw
        run(small_files[0], n_events=12, config=cfg)


@pytest.mark.parametrize("target", ["README.md", "docs", "docs/figures", "notebooks", "notebooks/x", "DATA.md"])
def test_protected_paths_are_refused(tmp_path, small_files, target):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    r = run(small_files[0])
    with pytest.raises(AnalysisError, match="refusing to write"):
        r.save(repo / target)
    with pytest.raises(AnalysisError, match="refusing to write"):
        run(small_files[0], outdir=repo / target)
    assert not (repo / "docs").exists() and not (repo / "notebooks").exists() and not (repo / "README.md").exists()
    r.save(repo / "results" / "dev")  # an unprotected directory is fine


def test_protected_rules_match_the_docs_freeze_script():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import check_docs_frozen

    sys.path.pop(0)
    assert PROTECTED_FILES == check_docs_frozen.PROTECTED_FILES
    assert PROTECTED_DIRS == check_docs_frozen.PROTECTED_DIRS


def test_channel_registry():
    assert {"Z_mumu", "Jpsi_mumu"} <= set(CHANNELS)
    z = CHANNELS["Z_mumu"]
    assert z.triggers == ("HLT_Mu17_Mu8", "HLT_Mu17_TkMu8") and z.mass_range == (60.0, 120.0) and z.bins == 60
    assert z.fit_range == (70.0, 110.0) and z.poly_degree == 2 and z.candidate_strategy == "highest_pt_sum"
    with pytest.raises(ValueError, match="already registered"):
        register_channel(z)
    mine = dataclasses.replace(z, name="my_test_channel")
    try:
        assert register_channel(mine) is CHANNELS["my_test_channel"]
    finally:
        CHANNELS.pop("my_test_channel", None)
    with pytest.raises(ValueError, match="mass-blind"):
        dataclasses.replace(z, candidate_strategy="closest_to")
    with pytest.raises(ValueError):
        dataclasses.replace(z, fit_range=(50.0, 110.0))


# -- 5. saving and the summary --------------------------------------------------------------------------------------


@pytest.mark.slow
def test_save_outputs_and_determinism(tmp_path, small_files):
    r1 = run(small_files[0], stability=True, model="voigt_poly")  # Voigt-shaped synthetic data
    r2 = run(small_files[0], stability=True, model="voigt_poly")
    w1, w2 = r1.save(tmp_path / "one"), r2.save(tmp_path / "two")
    names = sorted(p.name for p in w1)
    assert {"summary.txt", "summary.json", "mass_fit.png", "mass_fit.pdf", "cutflow.png", "cutflow.pdf"} <= set(names)
    assert names == sorted(p.name for p in w2)
    for a in w1:
        assert a.read_bytes() == (tmp_path / "two" / a.name).read_bytes(), a.name
    data = json.loads((tmp_path / "one" / "summary.json").read_text())
    assert "Figure" not in (tmp_path / "one" / "summary.json").read_text()
    assert data["channel"]["name"] == "Z_mumu" and data["fit"]["model"] == "voigt_poly"
    assert data["stability"]["label"] == "fit-choice spread only"
    json.dumps(r1.to_dict(), allow_nan=False)


def test_summary_labels_and_yields(small_files):
    r = run(small_files[0], stability=True)
    text = r.summary()
    assert "(statistical error only)" in text and "fit-choice spread only" in text
    assert "systematic effects" in text and "agree" not in text.lower() and "consistent" not in text.lower()
    assert r.fit.yields_reliable and "signal " in text
    bad = dataclasses.replace(r.fit, warnings=(FitWarning("background_negative", "negative"),))
    hidden = dataclasses.replace(r, fit=bad, alternate_fit=dataclasses.replace(r.alternate_fit, warnings=bad.warnings))
    text2 = hidden.summary()
    assert "yields not shown: background not positive" in text2
    assert f"{r.fit.signal_yield[0]:,.0f} +-" not in text2
    assert hidden.to_dict()["fit"]["signal_yield"] is None


def test_verbose_prints_the_summary(small_files, capsys):
    analyze(small_files[0], stability=False, model="voigt_poly")  # synthetic: Voigt-shaped, one resolution, no tail
    out = capsys.readouterr().out
    assert "Cutflow:" in out and "(statistical error only)" in out


# -- 6. command line ---------------------------------------------------------------------------------------------------


@pytest.mark.slow
def test_cli_module(tmp_path, small_files):
    out = subprocess.run(
        [
            sys.executable,
            "-m",
            "cmsopen",
            "analyze",
            str(small_files[0]),
            "--outdir",
            str(tmp_path / "o"),
            "--no-stability",
            "--quiet",
            "--model",
            "voigt_poly",
        ],
        capture_output=True,
        text=True,
    )
    assert out.returncode == 0, out.stderr
    assert (tmp_path / "o" / "summary.json").exists() and (tmp_path / "o" / "mass_fit.png").exists()
    verbose = subprocess.run(
        [sys.executable, "-m", "cmsopen", "analyze", str(small_files[0]), "--no-stability", "--n-events", "500",
         "--model", "voigt_poly"],
        capture_output=True,
        text=True,
    )
    assert verbose.returncode == 0 and "Events processed: 500" in verbose.stdout


def test_cli_errors_have_no_traceback(tmp_path, small_files):
    for args in (
        ["analyze", str(tmp_path / "missing.root")],
        ["analyze", str(small_files[0]), "--channel", "nope"],
        ["analyze", str(small_files[0]), "--outdir", str(tmp_path / "r" / "docs")],
    ):
        if "docs" in args[-1]:
            (tmp_path / "r" / ".git").mkdir(parents=True, exist_ok=True)
        out = subprocess.run(
            [sys.executable, "-m", "cmsopen", *args, "--quiet", "--no-stability"], capture_output=True, text=True
        )
        assert out.returncode == 1, (args, out.stderr)
        assert out.stderr.startswith("error: ") and "Traceback" not in out.stderr


def test_installed_script(tmp_path, small_files):
    script = Path(sys.executable).parent / ("cmsopen.exe" if os.name == "nt" else "cmsopen")
    if not script.exists():
        script = shutil.which("cmsopen")
    if not script:
        pytest.skip("the cmsopen console script is not installed in this environment")
    out = subprocess.run(
        [str(script), "analyze", str(small_files[0]), "--no-stability", "--quiet", "--outdir", str(tmp_path / "s"),
         "--model", "voigt_poly"],
        capture_output=True,
        text=True,
    )
    assert out.returncode == 0, out.stderr
    assert (tmp_path / "s" / "summary.txt").exists()


def test_exports():
    for name in ("analyze", "AnalysisResult", "ChannelConfig", "CHANNELS", "register_channel", "AnalysisError"):
        assert name in cmsopen.__all__ and getattr(cmsopen, name) is not None


# -- 7. real file ------------------------------------------------------------------------------------------------------


@pytest.mark.skipif(not REAL_FILE.exists(), reason=f"real CMS file not downloaded: {REAL_FILE} (see DATA.md)")
@pytest.mark.slow
def test_real_file_reproduces_development_results():
    """Regression check against the earlier layers' development results (numbers live in this test only)."""
    r = analyze(REAL_FILE, verbose=False, stability=False)
    last = r.cutflow[-1]
    assert (last.n_particles, last.n_events_with_particles, last.n_events) == (57_058, 28_528, 28_528)
    fits = {f.model_name: f for f in (r.fit, r.alternate_fit)}
    assert r.fit.model_name == "cb2_bw_exp" and set(fits) == {"cb2_bw_exp", "voigt_poly"}
    m, me = fits["voigt_poly"].peak_position  # the Layer 6 model, now reported next to the default
    assert abs(m - 90.7829) < me
    pole, pole_err = r.fit.peak_position  # dev/model_choice.md, Amendment 2: cb2_bw_exp, cb_n = 2
    assert abs(pole - 90.852) < 0.001 and abs(pole_err - 0.023) < 0.001
    assert r.fit.n_entries == 26_195
    assert r.n_events == 396_766
