import functools
import math
import operator
from pathlib import Path

import awkward as ak
import numpy as np
import pytest
import uproot
from synthetic import HLT_A, HLT_B, MUON_PT, N_EVENTS, REAL_FILE

import cmsopen
from cmsopen import Electron, FourMomentum, Muon, open_events
from cmsopen.ingestion import DIMUON_TRIGGERS_2012, MUON_BRANCHES_DEFAULT
from cmsopen.selection import (
    ZMUMU_MUON_CUTS,
    CutFlow,
    MissingFieldError,
    Selection,
    global_muon,
    max_abs_dxy,
    max_abs_dz,
    max_eta,
    max_rel_iso,
    min_pt,
    quality_id,
    select_electrons,
    select_muons,
)

# Hand-built muons: 4 events with 2, 0, 3 and 1 muons. Several values sit
# exactly on the thresholds tested below (pt 20, |eta| 2.4, iso 0.12 and
# 0.15, |dxy| 0.2, |dz| 0.5); all cuts are strict, so those values FAIL.
HAND = {
    "pt": [[25.0, 20.0], [], [19.9, 50.0, 20.0001], [100.0]],
    "eta": [[-2.5, 2.4], [], [0.0, -2.39, 2.41], [-0.5]],
    "phi": [[0.1, 0.2], [], [0.3, 0.4, 0.5], [0.6]],
    "mass": [[0.1057, 0.1057], [], [0.1057, 0.1057, 0.1057], [0.1057]],
    "charge": [[1, -1], [], [-1, 1, -1], [1]],
    "pfRelIso04_all": [[0.12, 0.05], [], [0.0, 0.2, 0.11999], [0.05]],
    "pfRelIso03_all": [[0.1, 0.2], [], [0.3, 0.0, 0.0], [0.15]],
    "looseId": [[True, True], [], [True, True, True], [True]],
    "mediumId": [[True, False], [], [False, True, True], [True]],
    "tightId": [[True, False], [], [False, True, True], [True]],
    "softId": [[False, False], [], [True, False, False], [False]],
    "isGlobal": [[True, True], [], [True, False, True], [False]],
    "isTracker": [[True, False], [], [True, True, True], [True]],
    "dxy": [[0.2, -0.01], [], [-0.2, 0.0, 0.3], [0.05]],
    "dz": [[-0.5, 0.1], [], [0.0, 0.5, -0.49], [1.0]],
}

EXPECTED_MASKS = {
    "min_pt(20)": [[True, False], [], [False, True, True], [True]],
    "max_eta(2.4)": [[False, False], [], [True, True, False], [True]],
    "max_rel_iso(0.12)": [[False, True], [], [True, False, True], [True]],
    "max_rel_iso(0.15, cone=0.3)": [[True, False], [], [False, True, True], [False]],
    "quality_id(loose)": HAND["looseId"],
    "quality_id(medium)": HAND["mediumId"],
    "quality_id(tight)": HAND["tightId"],
    "quality_id(soft)": HAND["softId"],
    "max_abs_dxy(0.2)": [[False, True], [], [False, True, False], [True]],
    "max_abs_dz(0.5)": [[False, True], [], [True, False, True], [False]],
    "global_muon": [[True, False], [], [True, False, True], [False]],
}


def make_muons(data=HAND, drop=()) -> Muon:
    extras = {k: v for k, v in data.items() if k not in ("pt", "eta", "phi", "mass", "charge", *drop)}
    p4 = FourMomentum.from_arrays(data["pt"], data["eta"], data["phi"], data["mass"])
    return Muon(p4, data["charge"], extras)


def make_electrons() -> Electron:
    pt = [[30.0, 10.0], [], [15.0]]
    eta = [[1.0, -2.6], [], [2.0]]
    p4 = FourMomentum.from_arrays(pt, eta, [[0.0, 0.0], [], [0.0]], [[0.000511] * 2, [], [0.000511]])
    return Electron(p4, [[-1, 1], [], [1]], {"pfRelIso03_all": [[0.1, 0.3], [], [0.2]], "cutBased": [[4, 0], [], [2]]})


@pytest.fixture
def muons() -> Muon:
    return make_muons()


@pytest.fixture
def full_events(full_nano_file: Path):
    with open_events(full_nano_file) as ev:
        yield ev


# -- 1. cut functions with known answers ----------------------------------------------


@pytest.mark.parametrize(
    "label, compute",
    [
        ("min_pt(20)", lambda m: min_pt(m, 20)),
        ("max_eta(2.4)", lambda m: max_eta(m, 2.4)),
        ("max_rel_iso(0.12)", lambda m: max_rel_iso(m, 0.12)),
        ("max_rel_iso(0.15, cone=0.3)", lambda m: max_rel_iso(m, 0.15, cone=0.3)),
        ("quality_id(loose)", lambda m: quality_id(m, "loose")),
        ("quality_id(medium)", lambda m: quality_id(m, "medium")),
        ("quality_id(tight)", lambda m: quality_id(m, "tight")),
        ("quality_id(soft)", lambda m: quality_id(m, "soft")),
        ("max_abs_dxy(0.2)", lambda m: max_abs_dxy(m, 0.2)),
        ("max_abs_dz(0.5)", lambda m: max_abs_dz(m, 0.5)),
        ("global_muon", lambda m: global_muon(m)),
    ],
)
def test_cut_function_masks(muons: Muon, label, compute):
    mask = compute(muons)
    assert isinstance(mask, ak.Array)
    assert str(ak.type(mask)) == "4 * var * bool"
    assert mask.tolist() == EXPECTED_MASKS[label]


def test_threshold_values_fail_strict_cuts(muons: Muon):
    """Values exactly at the threshold are rejected by every cut (strict inequalities)."""
    assert not min_pt(muons, 20)[0, 1]  # pt == 20
    assert not max_eta(muons, 2.4)[0, 1]  # eta == +2.4
    assert not max_eta(muons, 2.5)[0, 0]  # eta == -2.5: abs() makes it sit on the threshold
    assert not max_rel_iso(muons, 0.12)[0, 0]  # iso == 0.12
    assert not max_abs_dxy(muons, 0.2)[0, 0] and not max_abs_dxy(muons, 0.2)[2, 0]  # dxy == +-0.2
    assert not max_abs_dz(muons, 0.5)[0, 0] and not max_abs_dz(muons, 0.5)[2, 1]  # dz == -+0.5
    # Just inside the threshold passes.
    assert min_pt(muons, 20)[2, 2] and max_rel_iso(muons, 0.12)[2, 2] and max_abs_dz(muons, 0.5)[2, 2]


def test_negative_eta_uses_absolute_value(muons: Muon):
    assert max_eta(muons, 2.4)[2, 1]  # eta = -2.39 passes
    assert not max_eta(muons, 2.4)[0, 0]  # eta = -2.5 fails
    assert max_eta(muons, 2.6)[0, 0]


def test_nan_fails_every_cut():
    data = {k: [list(v[3])] for k, v in HAND.items()}
    for name in ("pt", "eta", "pfRelIso04_all", "dxy", "dz"):
        data[name] = [[float("nan")]]
    m = make_muons(data)
    for mask in (min_pt(m, 0), max_eta(m, 10), max_rel_iso(m, 10), max_abs_dxy(m, 10), max_abs_dz(m, 10)):
        assert mask.tolist() == [[False]]


def test_empty_events_and_empty_collection():
    empty = {k: [[], []] for k in HAND}
    m = make_muons(empty)
    for mask in (min_pt(m, 1), max_eta(m, 1), max_rel_iso(m, 1), quality_id(m, "tight"), global_muon(m)):
        assert mask.tolist() == [[], []]
    sel = Selection(m).min_pt(1).require(1)
    assert sel.n_events == 0 and sel.n_particles == 0
    assert sel.cutflow().to_dict()["n_events_eff_prev"][-1] == 0.0


def test_electron_cuts():
    el = make_electrons()
    assert min_pt(el, 12).tolist() == [[True, False], [], [True]]
    assert max_eta(el, 2.5).tolist() == [[True, False], [], [True]]
    assert max_rel_iso(el, 0.2).tolist() == [[True, False], [], [False]]  # default cone 0.3; 0.2 fails
    assert max_rel_iso(el, 0.25, cone=0.3).tolist() == [[True, False], [], [True]]
    with pytest.raises(ValueError, match=r"cone 0.4 not available for Electron; use one of \[0.3\]"):
        max_rel_iso(el, 0.2, cone=0.4)
    cuts = (
        lambda: quality_id(el, "tight"),
        lambda: global_muon(el),
        lambda: max_abs_dxy(el, 1),
        lambda: max_abs_dz(el, 1),
    )
    for cut in cuts:
        with pytest.raises(TypeError, match="needs a Muon collection, got Electron"):
            cut()
    sel = Selection(el).apply(min_pt=12, max_rel_iso=0.25)
    assert sel.particles.p4.pt.tolist() == [[30.0], [], [15.0]]
    with pytest.raises(TypeError, match="unknown Electron cut"):
        sel.apply(quality_id="tight")


# -- 2. cutflow by hand -------------------------------------------------------------------


def test_cutflow_hand_computed(muons: Muon):
    sel = Selection(muons).min_pt(20).max_eta(2.4).quality_id("tight").max_rel_iso(0.12).require(1)
    cf = sel.cutflow()
    assert isinstance(cf, CutFlow) and len(cf) == 6
    d = cf.to_dict()
    assert d["cut"] == [
        "all events",
        "min_pt(20)",
        "max_eta(2.4)",
        "quality_id(tight)",
        "max_rel_iso(0.12, cone=0.4)",
        "require(>= 1)",
    ]
    assert d["level"] == ["start", "particle", "particle", "particle", "particle", "event"]
    assert d["n_particles"] == [6, 4, 2, 2, 1, 1]
    assert d["n_events_with_particles"] == [3, 3, 2, 2, 1, 1]
    assert d["n_events"] == [4, 4, 4, 4, 4, 1]
    assert d["n_particles_eff_prev"] == pytest.approx([1, 4 / 6, 2 / 4, 1, 1 / 2, 1])
    assert d["n_particles_eff_start"] == pytest.approx([1, 4 / 6, 2 / 6, 2 / 6, 1 / 6, 1 / 6])
    assert d["n_events_with_particles_eff_prev"] == pytest.approx([1, 1, 2 / 3, 1, 1 / 2, 1])
    assert d["n_events_eff_prev"] == pytest.approx([1, 1, 1, 1, 1, 1 / 4])
    assert d["n_events_eff_start"] == pytest.approx([1, 1, 1, 1, 1, 1 / 4])
    assert d["params"][4] == {"value": 0.12, "cone": 0.4}
    assert sel.event_index.tolist() == [3]

    records = cf.to_records()
    assert len(records) == 6 and records[1]["cut"] == "min_pt(20)" and records[1]["n_particles"] == 4
    assert [s.n_particles for s in cf] == d["n_particles"]

    text = str(cf)
    lines = text.splitlines()
    assert "min_pt(20)" in text and "require(>= 1)" in text and "66.7%" in text and "25.0%" in text
    assert len({len(ln) for ln in lines[:-1]}) == 1  # aligned: every table line has the same width
    assert repr(cf) == "CutFlow(6 rows, final: 1 events, 1 particles)"


def test_selection_inspection(muons: Muon):
    sel = Selection(muons, entry_start=10).min_pt(20)
    assert sel.particles.p4.pt.tolist() == [[25.0], [], [50.0, 20.0001], [100.0]]
    assert isinstance(sel.particles, Muon)
    assert len(sel) == sel.n_events == 4 and sel.n_particles == 4
    assert sel.event_index.tolist() == [10, 11, 12, 13]
    assert [s.name for s in sel.history] == ["all events", "min_pt"]
    assert sel.events is None
    assert repr(sel) == "Selection(Muon: 4 of 4 events, 4 particles; min_pt(20))"
    assert repr(Selection(muons)) == "Selection(Muon: 4 of 4 events, 6 particles; no cuts)"


# -- 3. commutation and immutability --------------------------------------------------------

ALL_CUTS = [
    ("min_pt", (20,)),
    ("max_eta", (2.4,)),
    ("max_rel_iso", (0.15,)),
    ("quality_id", ("loose",)),
    ("max_abs_dxy", (0.25,)),
    ("max_abs_dz", (0.6,)),
    ("global_muon", ()),
]


@pytest.fixture(scope="module")
def random_muons() -> Muon:
    """Seeded random muons with every field, so all seven cuts remove something."""
    rng = np.random.default_rng(7)
    counts = rng.integers(0, 5, size=200)
    n = int(counts.sum())
    cols = {
        "pt": rng.exponential(25.0, n),
        "eta": rng.uniform(-3.0, 3.0, n),
        "phi": rng.uniform(-np.pi, np.pi, n),
        "mass": np.full(n, 0.1057),
        "charge": rng.choice([-1, 1], n),
        "pfRelIso04_all": rng.exponential(0.2, n),
        "pfRelIso03_all": rng.exponential(0.2, n),
        "dxy": rng.normal(0, 0.2, n),
        "dz": rng.normal(0, 0.5, n),
    }
    for flag in ("looseId", "mediumId", "tightId", "softId", "isGlobal", "isTracker"):
        cols[flag] = rng.random(n) < 0.8
    return make_muons({k: ak.unflatten(v, counts) for k, v in cols.items()})


def _state(sel: Selection):
    p = sel.particles
    return p.p4.pt.tolist(), p.p4.eta.tolist(), p.charge.tolist(), p.extras.dxy.tolist()


def test_particle_cuts_commute(random_muons: Muon):
    """Every one of the 7! = 5040 orderings of the seven particle-level cuts keeps the same muons.

    An ordering is a path from "no cuts" to "all cuts" through the 2^7
    subsets of cuts. The test applies every cut to the state of every
    subset (448 transitions) and checks that each route into a subset
    gives the same muons as the first route found. Then every path, and
    therefore every ordering, ends in the same state. Applying each
    ordering one by one gives the same result but takes minutes.
    """
    args = dict(ALL_CUTS)
    names = list(args)
    states = {frozenset(): Selection(random_muons)}
    for size in range(len(names)):
        for subset in [k for k in states if len(k) == size]:
            for name in names:
                if name in subset:
                    continue
                sel = getattr(states[subset], name)(*args[name])
                key = subset | {name}
                if key in states:
                    assert _state(sel) == _state(states[key]), f"{sorted(subset)} + {name} differs"
                else:
                    states[key] = sel
    assert len(states) == 2 ** len(names)

    final = states[frozenset(names)]
    combined = functools.reduce(operator.and_, [getattr(cmsopen.selection, n)(random_muons, *a) for n, a in ALL_CUTS])
    assert _state(final) == _state(Selection(random_muons[combined]))
    assert 0 < final.n_particles < Selection(random_muons).n_particles  # the cuts really did something
    # A few full orderings spelled out, as a direct check of the same property.
    for order in (names, names[::-1], names[3:] + names[:3]):
        sel = Selection(random_muons)
        for name in order:
            sel = getattr(sel, name)(*args[name])
        assert _state(sel) == _state(final)


def test_selection_is_immutable(muons: Muon):
    base = Selection(muons)
    before = (base.particles.p4.pt.tolist(), base.event_index.tolist(), base.history, base.n_particles)
    chained = base.min_pt(20).max_eta(2.4).quality_id("tight").require(1)
    assert chained is not base
    assert (base.particles.p4.pt.tolist(), base.event_index.tolist(), base.history, base.n_particles) == before
    assert len(base.history) == 1 and len(chained.history) == 5
    with pytest.raises(ValueError, match="read-only"):
        base.event_index[0] = 99
    with pytest.raises(ValueError, match="read-only"):
        chained.event_index[0] = 99
    with pytest.raises(AttributeError):
        base.particles = None


# -- 4. event-level require -----------------------------------------------------------------


@pytest.mark.parametrize(
    "n, exactly, kept",
    [
        (0, False, [0, 1, 2, 3]),
        (1, False, [0, 2, 3]),
        (2, False, [0, 2]),
        (3, False, [2]),
        (4, False, []),
        (0, True, [1]),
        (1, True, [3]),
        (2, True, [0]),
        (3, True, [2]),
    ],
)
def test_require_counts(muons: Muon, n, exactly, kept):
    """Events have 2, 0, 3, 1 muons."""
    sel = Selection(muons).require(n, exactly=exactly)
    assert sel.event_index.tolist() == kept
    assert sel.n_events == len(kept)
    original = ak.Array(HAND["pt"])
    assert sel.particles.p4.pt.tolist() == original[np.asarray(kept, dtype=np.int64)].tolist()
    assert sel.history[-1].label == f"require({'==' if exactly else '>='} {n})"


def test_require_after_particle_cuts_and_twice(muons: Muon):
    sel = Selection(muons, entry_start=100).min_pt(20)  # counts become 1, 0, 2, 1
    assert sel.require(2).event_index.tolist() == [102]
    twice = Selection(muons).require(1).require(2)
    assert twice.event_index.tolist() == [0, 2]
    twice = Selection(muons).require(2).require(3, exactly=True)
    assert twice.event_index.tolist() == [2]
    assert twice.particles.charge.tolist() == [HAND["charge"][2]]
    assert twice.cutflow().to_dict()["n_events"] == [4, 2, 1]


def test_require_rejects_bad_n(muons: Muon):
    for bad in (-1, 1.5, True, "2"):
        with pytest.raises(ValueError, match="non-negative integer"):
            Selection(muons).require(bad)


# -- 5. triggers on a synthetic ROOT file ----------------------------------------------------

FIRED = [a or b for a, b in zip(HLT_A, HLT_B, strict=False)]  # [T, F, T, T, F, F]
COUNTS = [len(x) for x in MUON_PT]  # [2, 0, 1, 3, 0, 2]


def test_require_trigger_subset(full_events):
    sel = select_muons(full_events).require_trigger(*DIMUON_TRIGGERS_2012)
    assert sel.event_index.tolist() == [i for i, f in enumerate(FIRED) if f] == [0, 2, 3]
    assert sel.particles.p4.pt.tolist() == [MUON_PT[i] for i in (0, 2, 3)]
    assert select_muons(full_events).require_trigger("HLT_Mu17_TkMu8").event_index.tolist() == [0, 2]
    assert sel.history[-1].label == "trigger(HLT_Mu17_Mu8 OR HLT_Mu17_TkMu8)"


def test_require_trigger_alignment_before_and_after_require(full_events):
    after = select_muons(full_events).require(2).require_trigger(*DIMUON_TRIGGERS_2012)
    before = select_muons(full_events).require_trigger(*DIMUON_TRIGGERS_2012).require(2)
    expected = [i for i in range(N_EVENTS) if FIRED[i] and COUNTS[i] >= 2]
    assert expected == [0, 3]
    for sel in (after, before):
        assert sel.event_index.tolist() == expected
        assert sel.particles.p4.pt.tolist() == [MUON_PT[i] for i in expected]
    # Event 5 has 2 muons but no trigger: require(2) keeps it, the trigger then drops it.
    assert select_muons(full_events).require(2).event_index.tolist() == [0, 3, 5]


def test_require_trigger_with_entry_range(full_events):
    """event_index refers to file rows; the trigger mask is aligned with it inside a sub-range."""
    sel = select_muons(full_events, entry_start=2, entry_stop=6).require(2)
    assert sel.event_index.tolist() == [3, 5]
    trig = sel.require_trigger(*DIMUON_TRIGGERS_2012)
    assert trig.event_index.tolist() == [3]
    assert trig.particles.p4.pt.tolist() == [MUON_PT[3]]
    run_lumi = full_events.arrays("luminosityBlock")[trig.event_index]
    assert run_lumi.luminosityBlock.tolist() == [3]


# -- 6. errors --------------------------------------------------------------------------------


def test_unknown_quality_id_lists_valid_names(muons: Muon):
    with pytest.raises(ValueError, match=r"unknown muon ID 'super'; valid names: loose, medium, tight, soft"):
        quality_id(muons, "super")
    with pytest.raises(ValueError, match="valid names"):
        Selection(muons).quality_id("Tight")


def test_missing_field_is_named(muons: Muon):
    bare = make_muons(drop=("tightId", "pfRelIso04_all", "dxy", "isTracker"))
    with pytest.raises(MissingFieldError, match=r"quality_id\(\) needs the field 'tightId' \(branch Muon_tightId\)"):
        quality_id(bare, "tight")
    with pytest.raises(MissingFieldError, match=r"'pfRelIso04_all' \(branch Muon_pfRelIso04_all\)"):
        Selection(bare).max_rel_iso(0.1)
    with pytest.raises(MissingFieldError, match="'dxy'"):
        max_abs_dxy(bare, 0.2)
    with pytest.raises(MissingFieldError, match="'isTracker'"):
        global_muon(bare)
    assert issubclass(MissingFieldError, KeyError)


def test_missing_field_through_events(full_events):
    with pytest.raises(MissingFieldError, match="Muon_pfRelIso04_all"):
        full_events.muons(fields=["pt", "eta", "phi", "mass", "charge"], max_rel_iso=0.1)


def test_require_trigger_without_events(muons: Muon):
    with pytest.raises(ValueError, match="no link to an EventCollection"):
        Selection(muons).require_trigger("HLT_Mu17_Mu8")
    with pytest.raises(ValueError, match="at least one HLT path"):
        Selection(muons).require_trigger()


def test_require_trigger_closed_file(full_nano_file: Path):
    with open_events(full_nano_file) as ev:
        sel = ev.muons(min_pt=1)
    with pytest.raises(ValueError, match="file is closed"):
        sel.require_trigger("HLT_Mu17_Mu8")


def test_unknown_trigger_path_lists_closest(full_events):
    sel = full_events.muons(min_pt=20)
    with pytest.raises(KeyError, match="closest matches: HLT_Mu17_Mu8"):
        sel.require_trigger("HLT_Mu17_Mu9")


def test_bad_arguments(muons: Muon):
    with pytest.raises(TypeError, match="real number"):
        min_pt(muons, "20")
    with pytest.raises(TypeError, match="real number"):
        max_eta(muons, None)
    with pytest.raises(ValueError, match="NaN"):
        max_rel_iso(muons, math.nan)
    with pytest.raises(TypeError, match="needs a ParticleCollection"):
        min_pt(ak.Array(HAND["pt"]), 20)
    with pytest.raises(TypeError, match=r"unknown Muon cut\(s\) \['min_ptt'\]"):
        Selection(muons).apply(min_ptt=20)
    with pytest.raises(TypeError, match="global_muon takes True or False"):
        Selection(muons).apply(global_muon="yes")


# -- entry points --------------------------------------------------------------------------------


def test_events_muons_with_cuts_in_keyword_order(full_events):
    sel = full_events.muons(max_eta=2.4, min_pt=25)
    assert isinstance(sel, Selection) and isinstance(sel.particles, Muon)
    assert [s.label for s in sel.history] == ["all events", "max_eta(2.4)", "min_pt(25)"]
    assert sel.particles.p4.pt.tolist() == [[45.0, 38.0], [], [], [50.0, 41.0], [], [30.0, 29.0]]
    req = full_events.muons(min_pt=20, max_eta=2.4).require(2)
    assert req.event_index.tolist() == [0, 3, 5]
    assert select_muons(full_events, min_pt=20, max_eta=2.4).require(2).event_index.tolist() == [0, 3, 5]
    # None skips a cut; global_muon=True applies it.
    assert [s.name for s in full_events.muons(min_pt=None, global_muon=True).history] == ["all events", "global_muon"]
    assert [s.name for s in select_muons(full_events).history] == ["all events"]


def test_zmumu_cuts_constant(full_events):
    assert list(ZMUMU_MUON_CUTS) == ["min_pt", "max_eta", "quality_id", "max_rel_iso"]
    assert dict(ZMUMU_MUON_CUTS) == {"min_pt": 20.0, "max_eta": 2.4, "quality_id": "tight", "max_rel_iso": 0.12}
    with pytest.raises(TypeError):
        ZMUMU_MUON_CUTS["min_pt"] = 10  # read-only
    sel = full_events.muons(**ZMUMU_MUON_CUTS)
    assert [s.label for s in sel.history][1:] == [
        "min_pt(20)",
        "max_eta(2.4)",
        "quality_id(tight)",
        "max_rel_iso(0.12, cone=0.4)",
    ]


def test_events_electrons_with_cuts(full_events):
    sel = full_events.electrons(min_pt=10)
    assert isinstance(sel, Selection) and isinstance(sel.particles, Electron)
    assert sel.particles.p4.pt.tolist() == [[], [25.0], [], [], [12.0], []]
    assert sel.history[-1].label == "min_pt(10)"
    assert select_electrons(full_events, max_rel_iso=0.05).history[-1].label == "max_rel_iso(0.05, cone=0.3)"
    with pytest.raises(TypeError, match="valid: min_pt, max_eta, max_rel_iso"):
        full_events.electrons(quality_id="tight")


def test_package_exports():
    for name in (
        "Selection",
        "CutFlow",
        "MissingFieldError",
        "ZMUMU_MUON_CUTS",
        "select_muons",
        "select_electrons",
        "min_pt",
        "max_eta",
        "max_rel_iso",
        "quality_id",
        "max_abs_dxy",
        "max_abs_dz",
        "global_muon",
    ):
        assert getattr(cmsopen, name) is getattr(cmsopen.selection, name)
        assert name in cmsopen.__all__


# -- 7. backward compatibility ----------------------------------------------------------------------


def test_muons_without_cuts_unchanged(full_events, events):
    raw = full_events.muons()
    assert isinstance(raw, ak.Array) and not isinstance(raw, Selection)
    assert raw.fields == list(MUON_BRANCHES_DEFAULT)
    assert str(ak.type(raw)) == str(ak.type(full_events.collection("Muon", MUON_BRANCHES_DEFAULT)))
    assert raw.pt.tolist() == MUON_PT
    # Same assertions as the layer 1 test of the wrapper.
    mu = events.muons(fields=["pt", "eta", "phi", "mass", "charge", "tightId"], entry_stop=4)
    assert isinstance(mu, ak.Array) and len(mu) == 4
    assert mu.fields == ["pt", "eta", "phi", "mass", "charge", "tightId"]
    with pytest.raises(KeyError, match="Muon_pfRelIso04_all"):
        events.muons()
    el = full_events.electrons()
    assert isinstance(el, ak.Array) and str(ak.type(el)) == str(ak.type(full_events.collection("Electron", el.fields)))


# -- 8. real file ------------------------------------------------------------------------------------


@pytest.mark.skipif(not REAL_FILE.exists(), reason=f"real CMS file not downloaded: {REAL_FILE} (see DATA.md)")
def test_real_file_matches_independent_awkward():
    """The Z->mumu selection equals a plain uproot+awkward computation that does not call cmsopen cuts."""
    branches = ["Muon_pt", "Muon_eta", "Muon_tightId", "Muon_pfRelIso04_all", "HLT_Mu17_Mu8", "HLT_Mu17_TkMu8"]
    with uproot.open(REAL_FILE) as f:
        raw = f["Events"].arrays(branches)
    trig = ak.to_numpy(raw.HLT_Mu17_Mu8 | raw.HLT_Mu17_TkMu8)
    rows = np.flatnonzero(trig)
    t = raw[trig]
    pt, eta = t.Muon_pt, t.Muon_eta
    m_pt = pt > 20
    m_eta = m_pt & (abs(eta) < 2.4)
    m_id = m_eta & t.Muon_tightId
    m_iso = m_id & (t.Muon_pfRelIso04_all < 0.12)
    two = ak.to_numpy(ak.sum(m_iso, axis=1) >= 2)
    per_event = [ak.num(pt), *(ak.sum(m, axis=1) for m in (m_pt, m_eta, m_id, m_iso))]
    expected_particles = [int(ak.sum(c)) for c in per_event] + [int(ak.sum(per_event[-1][two]))]

    with open_events(REAL_FILE) as ev:
        sel = (
            cmsopen.select_muons(ev, fields=("pt", "eta", "phi", "mass", "charge", "tightId", "pfRelIso04_all"))
            .require_trigger(*DIMUON_TRIGGERS_2012)
            .apply(**ZMUMU_MUON_CUTS)
            .require(2)
        )
    assert len(ev) == 396_766
    np.testing.assert_array_equal(sel.event_index, rows[two])
    assert ak.all(sel.particles.p4.pt == ak.values_astype(pt[m_iso][two], np.float64))
    assert ak.all(ak.num(sel.particles.p4.pt) == ak.num(pt[m_iso][two]))
    assert sel.cutflow().to_dict()["n_particles"][1:] == expected_particles
    assert sel.cutflow().to_dict()["n_events"][1:] == [len(rows)] * 5 + [int(two.sum())]

    final_pt = ak.flatten(sel.particles.p4.pt)
    final_eta = ak.flatten(sel.particles.p4.eta)
    assert ak.all(final_pt > 20) and not ak.any(final_pt <= 20)
    assert ak.all(abs(final_eta) < 2.4) and not ak.any(abs(final_eta) >= 2.4)
    assert ak.all(ak.num(sel.particles.p4.pt) >= 2)
