"""The small real-data sample examples/data/cmsopen_sample.root: provenance, reproducibility, end-to-end analysis.

These tests need neither the 1.1 GB development file nor the network (the reproducibility test is skipped
without the development file). The fits use voigt_poly: with a few thousand pairs per channel the frozen
resolution-mixture defaults cannot determine their second core (the fit then fails with the documented
AnalysisError), while a Breit-Wigner of fixed natural width convolved with one Gaussian has only one free shape
parameter and describes a few thousand pairs.
"""

import hashlib
import re
import sys
from pathlib import Path

import awkward as ak
import pytest
import uproot

from cmsopen import AnalysisError, analyze
from cmsopen.datasets import DEV_FILENAME
from cmsopen.fitting import pdg_mass_width
from cmsopen.pipeline import CHANNELS

REPO = Path(__file__).resolve().parents[1]
SAMPLE = REPO / "examples" / "data" / "cmsopen_sample.root"
SAMPLE_MD = REPO / "examples" / "data" / "SAMPLE.md"
WINDOW = {"Z_mumu": 1.0, "Jpsi_mumu": 0.02}  # GeV: generous windows around the PDG mass (structural, not a result)


def provenance(key):
    m = re.search(rf"^\| {key} \| (.+?) \|$", SAMPLE_MD.read_text(), flags=re.M)
    assert m, key
    return m.group(1)


def test_sample_matches_its_provenance():
    data = SAMPLE.read_bytes()
    assert int(provenance("size").split()[0].replace(",", "")) == len(data) < 8_000_000
    assert provenance("SHA-256") == hashlib.sha256(data).hexdigest()
    with uproot.open(SAMPLE) as f:
        tree = f["Events"]
        n = int(re.search(r"first ([\d,]+) events", provenance("events")).group(1).replace(",", ""))
        assert tree.num_entries == n
        assert {"run", "luminosityBlock", "event", "nMuon", "Muon_pt", "PV_npvsGood"} <= set(tree.keys())


@pytest.mark.parametrize("channel", ["Z_mumu", "Jpsi_mumu"])
def test_analyze_runs_end_to_end_on_the_sample(channel, tmp_path):
    r = analyze(SAMPLE, channel=channel, model="voigt_poly", stability=False, verbose=False, outdir=tmp_path)
    assert r.fit.n_entries > 500 and len(r.masses) > 0  # pairs exist in the fit range
    pdg = pdg_mass_width(CHANNELS[channel].resonance)[0]
    assert abs(r.fit.peak_position[0] - pdg) < WINDOW[channel]
    assert {"summary.json", "summary.txt", "mass_fit.png", "cutflow.png"} <= {p.name for p in tmp_path.iterdir()}


def test_the_frozen_default_fits_or_fails_with_the_documented_exception():
    try:
        r = analyze(SAMPLE, channel="Jpsi_mumu", stability=False, verbose=False)
    except AnalysisError as exc:
        assert "fit failed" in str(exc) and "cb2_bw_poly2" in str(exc)
    else:
        assert r.fit.model_name == "cb2_bw_poly2"


@pytest.mark.skipif(not (REPO / "data" / DEV_FILENAME).exists(), reason="the development file is not present")
def test_the_sample_is_reproducible_from_the_development_file(tmp_path):
    sys.path.insert(0, str(REPO / "scripts"))
    import make_skim

    sys.path.pop(0)
    n = int(re.search(r"first ([\d,]+) events", provenance("events")).group(1).replace(",", ""))
    arrays = make_skim.read_source(REPO / "data" / DEV_FILENAME)
    make_skim.write_skim(arrays, n, tmp_path / "again.root")
    with uproot.open(SAMPLE) as a, uproot.open(tmp_path / "again.root") as b:
        ta, tb = a["Events"], b["Events"]
        assert sorted(ta.keys()) == sorted(tb.keys())
        for name in ta.keys():
            assert ak.array_equal(ta[name].array(), tb[name].array()), name
