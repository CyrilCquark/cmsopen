from pathlib import Path

import awkward as ak
import numpy as np
import pytest
import uproot
from synthetic import ELECTRON_PT, HLT_A, HLT_B, MUON_CHARGE, MUON_PT, N_EVENTS, REAL_FILE, _write_ttree

import cmsopen
from cmsopen.ingestion import (
    DIMUON_TRIGGERS_2012,
    MUON_BRANCHES_DEFAULT,
    EventCollection,
    NotNanoAODError,
    open_events,
)


def test_package_exports():
    assert cmsopen.open_events is open_events
    assert cmsopen.EventCollection is EventCollection


def test_open_metadata(events: EventCollection, nano_file: Path):
    assert len(events) == events.n_events == N_EVENTS
    assert events.tree_name == "Events"
    assert events.path == str(nano_file)
    assert events.branches == sorted(events.branches)
    for name in ("nMuon", "Muon_pt", "Electron_cutBased", "HLT_Mu17_Mu8", "run"):
        assert events.has_branch(name)
    assert not events.has_branch("Muon_nonexistent")
    summary = events.summary()
    assert "Events" in summary and str(N_EVENTS) in summary and str(len(events.branches)) in summary


def test_open_is_lazy(nano_file: Path, monkeypatch: pytest.MonkeyPatch):
    """Opening and querying metadata must not decompress any event data."""
    calls = []

    def spy(*args, **kwargs):
        calls.append(1)
        raise AssertionError("event data was read")

    monkeypatch.setattr(uproot.behaviors.TBranch, "_ranges_or_baskets_to_arrays", spy)
    ev = open_events(nano_file)
    len(ev), ev.branches, ev.has_branch("Muon_pt"), ev.summary(), repr(ev)
    assert calls == []
    # The spy really sits on the read path: an actual read hits it.
    with pytest.raises(AssertionError, match="event data was read"):
        ev.arrays("Muon_pt")
    assert calls == [1]
    ev.close()


def test_arrays_reads_only_requested(events: EventCollection):
    arr = events.arrays(["nMuon", "Muon_pt"])
    assert arr.fields == ["nMuon", "Muon_pt"]
    assert arr.nMuon.tolist() == [len(x) for x in MUON_PT]
    assert arr.Muon_pt.tolist() == MUON_PT
    single = events.arrays("run", entry_start=1, entry_stop=3)
    assert len(single) == 2


def test_arrays_missing_branch_suggests(events: EventCollection):
    with pytest.raises(KeyError) as err:
        events.arrays(["Muon_pt", "Muon_ptt"])
    assert "Muon_ptt" in str(err.value)
    assert "closest matches: Muon_pt" in str(err.value)


def test_collection_zips_jagged_records(events: EventCollection):
    mu = events.collection("Muon", ["pt", "charge"])
    assert str(ak.type(mu)) == f"{N_EVENTS} * var * {{pt: float32, charge: int32}}"
    assert ak.num(mu).tolist() == [len(x) for x in MUON_PT]
    assert mu.pt.tolist() == MUON_PT
    assert mu.charge.tolist() == MUON_CHARGE
    assert mu[0, 1].tolist() == {"pt": 38.0, "charge": -1}


def test_collection_default_fields_skip_scalars(events: EventCollection):
    el = events.collection("Electron")
    assert set(el.fields) == {"pt", "eta", "cutBased"}  # Electron_nNano excluded
    assert ak.num(el).tolist() == [len(x) for x in ELECTRON_PT]


def test_collection_errors(events: EventCollection):
    with pytest.raises(ValueError, match="one value per event"):
        events.collection("Electron", ["pt", "nNano"])
    with pytest.raises(KeyError, match="Muon_et"):
        events.collection("Muon", ["et"])
    with pytest.raises(ValueError, match="No per-particle branches"):
        events.collection("Tau")


def test_muons_and_electrons_wrappers(events: EventCollection):
    mu = events.muons(fields=["pt", "eta", "phi", "mass", "charge", "tightId"], entry_stop=4)
    assert len(mu) == 4
    assert mu.fields == ["pt", "eta", "phi", "mass", "charge", "tightId"]
    assert mu.tightId.tolist()[0] == [True, True]
    el = events.electrons(fields=["pt", "cutBased"])
    assert el.pt.tolist() == ELECTRON_PT
    # Defaults reference real Run 1 branches the synthetic file lacks.
    with pytest.raises(KeyError, match="Muon_pfRelIso04_all"):
        events.muons()


def test_trigger_any_of(events: EventCollection):
    a = events.trigger("HLT_Mu17_Mu8")
    assert isinstance(a, np.ndarray) and a.dtype == bool
    assert a.tolist() == HLT_A
    both = events.trigger(*DIMUON_TRIGGERS_2012)
    assert both.tolist() == [x or y for x, y in zip(HLT_A, HLT_B, strict=False)]
    assert events.trigger(*DIMUON_TRIGGERS_2012, entry_start=2, entry_stop=4).tolist() == [True, True]
    assert not events.trigger("HLT_IsoMu24").any()


def test_trigger_errors(events: EventCollection):
    with pytest.raises(KeyError, match="closest matches: HLT_Mu17_Mu8"):
        events.trigger("HLT_Mu17_Mu9")
    with pytest.raises(ValueError, match="at least one"):
        events.trigger()


def test_iterate_chunks(events: EventCollection):
    chunks = list(events.iterate(["Muon_pt", "run"], step_size=4))
    assert [len(c) for c in chunks] == [4, 2]
    assert sum(len(c) for c in chunks) == N_EVENTS
    assert ak.concatenate([c.Muon_pt for c in chunks]).tolist() == MUON_PT
    with pytest.raises(KeyError):
        next(events.iterate("Muon_ptx"))


def test_missing_tree_lists_trees(nano_file: Path):
    with pytest.raises(NotNanoAODError, match=r"No tree 'Runs'.*\['Events'\]"):
        open_events(nano_file, tree="Runs")
    assert issubclass(NotNanoAODError, ValueError)


def test_non_nanoaod_files_rejected(tmp_path: Path):
    hist_file = tmp_path / "hist.root"
    with uproot.recreate(hist_file) as f:
        f["Events"] = np.histogram([1.0, 2.0])
    with pytest.raises(NotNanoAODError, match="not a TTree"):
        open_events(hist_file)

    no_ids = tmp_path / "noids.root"
    with uproot.recreate(no_ids) as f:
        _write_ttree(f, "Events", {"x": np.arange(3)})
    with pytest.raises(NotNanoAODError, match="event-ID branches"):
        open_events(no_ids)


@pytest.mark.skipif(not REAL_FILE.exists(), reason=f"real CMS file not downloaded: {REAL_FILE} (see DATA.md)")
@pytest.mark.slow
def test_real_file_reproduces_measured_numbers():
    with open_events(REAL_FILE) as ev:
        assert ev.tree_name == "Events"
        assert len(ev) == 396_766
        assert all(ev.has_branch(f"Muon_{f}") for f in MUON_BRANCHES_DEFAULT)
        mu = ev.muons(fields=["mass"], entry_stop=100_000)
        assert len(mu) == 100_000
        assert ak.sum(ak.num(mu)) == 474_335
        assert ak.mean(mu.mass) == pytest.approx(0.105658, abs=1e-5)
        assert ev.trigger("HLT_Mu17_Mu8", entry_stop=100_000).mean() == pytest.approx(0.401, abs=0.002)
