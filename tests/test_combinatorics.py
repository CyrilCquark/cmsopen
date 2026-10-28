import math

import awkward as ak
import numpy as np
import pytest
import uproot
from synthetic import REAL_FILE

import cmsopen
from cmsopen import FourMomentum, Muon, Selection, open_events
from cmsopen.combinatorics import (
    MuonPairs,
    PairMultiplicity,
    all_pairs,
    best_pair,
    make_pairs,
    multiplicity,
    opposite_sign_pairs,
    same_sign_pairs,
)
from cmsopen.kinematics import delta_r, invariant_mass, pair_eta, pair_phi, pair_pt, pair_rapidity
from cmsopen.objects import Electron

M_MU = 0.1056583755  # GeV
Z_MASS = 91.1876  # GeV

# Hand-built events with 0, 1, 2, 3, 4 and 2 (same-sign) muons. pT is deliberately NOT in
# descending order, so leg ordering must come from an explicit sort.
#   event 2: 2 muons (+ -), pts 40 < 50          -> 1 OS pair, leg1 = index 1
#   event 3: 3 muons (+ + -), pts 20, 60, 40     -> pT order 1, 2, 0
#   event 4: 4 muons (- + - +), pts 10, 30, 25, 50 -> pT order 3, 1, 2, 0
#   event 5: 2 muons (+ +), pts 30, 35           -> 1 SS pair, no OS pair
HAND = {
    "pt": [[], [25.0], [40.0, 50.0], [20.0, 60.0, 40.0], [10.0, 30.0, 25.0, 50.0], [30.0, 35.0]],
    "eta": [[], [0.1], [0.5, -0.4], [1.0, -1.2, 0.3], [0.0, 2.0, -1.5, 0.7], [-0.2, 0.9]],
    "phi": [[], [0.0], [0.3, -2.8], [2.0, -1.0, 0.5], [1.0, -2.5, 3.0, -0.1], [0.4, 2.9]],
    "mass": [[], [M_MU], [M_MU] * 2, [M_MU] * 3, [M_MU] * 4, [M_MU] * 2],
    "charge": [[], [1], [1, -1], [1, 1, -1], [-1, 1, -1, 1], [1, 1]],
}
EXPECTED = {
    # charge mode: (index1, index2) per event, in pT order of the pairs
    "opposite": ([[], [], [1], [1, 2], [3, 3, 1, 1], []], [[], [], [0], [2, 0], [2, 0, 2, 0], []]),
    "same": ([[], [], [], [1], [3, 2], [1]], [[], [], [], [0], [1, 0], [0]]),
    "any": (
        [[], [], [1], [1, 1, 2], [3, 3, 3, 1, 1, 2], [1]],
        [[], [], [0], [2, 0, 0], [1, 2, 0, 2, 0, 0], [0]],
    ),
}


def make_muons(data=HAND, extras=None, dtype=np.float64) -> Muon:
    arrays = [ak.values_astype(ak.Array(data[k]), dtype) for k in ("pt", "eta", "phi", "mass")]
    return Muon(FourMomentum(*arrays), data["charge"], extras)


def random_muons(n_events=300, seed=1) -> Muon:
    """Random events with 0-7 muons, random charges, and a unique id per muon."""
    rng = np.random.default_rng(seed)
    counts = rng.integers(0, 8, n_events)
    n = int(counts.sum())

    def jag(x):
        return ak.unflatten(x, counts)

    return Muon(
        FourMomentum(jag(rng.uniform(5, 80, n)), jag(rng.uniform(-2.4, 2.4, n)), jag(rng.uniform(-np.pi, np.pi, n)), jag(np.full(n, M_MU))),
        jag(rng.choice([-1, 1], n)),
        {"uid": jag(np.arange(n))},
    )


def pair_set(pairs: MuonPairs, event: int) -> list[tuple[int, int, float]]:
    """Sorted (uid of one leg, uid of the other, mass) for one event: order-independent."""
    u1, u2, m = (ak.to_list(x[event]) for x in (pairs.leg1._extra("uid"), pairs.leg2._extra("uid"), pairs.mass))
    return sorted((min(a, b), max(a, b), round(mm, 9)) for a, b, mm in zip(u1, u2, m))


# -- 1. exact pairs on hand-built events -------------------------------------------------------------


@pytest.mark.parametrize("charge", ["opposite", "same", "any"])
def test_hand_built_pairs_exact(charge):
    pairs = make_pairs(make_muons(), charge=charge)
    index1, index2 = EXPECTED[charge]
    assert pairs.index1.tolist() == index1
    assert pairs.index2.tolist() == index2
    assert pairs.num.tolist() == [len(x) for x in index1]
    assert len(pairs) == 6


def test_named_functions_equal_make_pairs():
    muons = make_muons()
    for func, charge in ((opposite_sign_pairs, "opposite"), (same_sign_pairs, "same"), (all_pairs, "any")):
        assert func(muons).index1.tolist() == make_pairs(muons, charge).index1.tolist()
        assert func(muons).index2.tolist() == make_pairs(muons, charge).index2.tolist()
    assert make_pairs(muons).index1.tolist() == EXPECTED["opposite"][0]  # default is opposite sign


def test_legs_are_the_input_muons():
    muons = make_muons()
    pairs = all_pairs(muons)
    for leg, index in ((pairs.leg1, pairs.index1), (pairs.leg2, pairs.index2)):
        for field in ("pt", "eta", "phi", "mass"):
            assert getattr(leg.p4, field).tolist() == getattr(muons.p4, field)[index].tolist()
        assert leg.charge.tolist() == muons.charge[index].tolist()
    assert isinstance(pairs.leg1, Muon) and isinstance(pairs.leg2, Muon)


def test_ranks_are_pt_positions():
    pairs = all_pairs(make_muons())
    # event 4 pT order is 3, 1, 2, 0: ranks of (3,1) are (0,1), of (2,0) are (2,3)
    assert pairs.rank1.tolist()[4] == [0, 0, 0, 1, 1, 2]
    assert pairs.rank2.tolist()[4] == [1, 2, 3, 2, 3, 3]


# -- 2. counting identity ---------------------------------------------------------------------------


@pytest.mark.parametrize("muons", [make_muons(), random_muons()], ids=["hand", "random"])
def test_os_plus_ss_equals_all_equals_n_choose_2(muons):
    n = ak.to_numpy(muons.num)
    n_os, n_ss, n_all = (ak.to_numpy(make_pairs(muons, c).num) for c in ("opposite", "same", "any"))
    np.testing.assert_array_equal(n_os + n_ss, n_all)
    np.testing.assert_array_equal(n_all, n * (n - 1) // 2)
    n_plus = ak.to_numpy(ak.sum(muons.charge > 0, axis=1))
    n_minus = n - n_plus
    np.testing.assert_array_equal(n_os, n_plus * n_minus)
    np.testing.assert_array_equal(n_ss, n_plus * (n_plus - 1) // 2 + n_minus * (n_minus - 1) // 2)


# -- 3. charges, no self-pairs, no duplicates ------------------------------------------------------


def test_charge_products_no_self_pairs_no_duplicates():
    muons = random_muons()
    os_pairs, ss_pairs, every = opposite_sign_pairs(muons), same_sign_pairs(muons), all_pairs(muons)
    assert ak.all(os_pairs.charge_product == -1)
    assert ak.all(ss_pairs.charge_product == 1)
    assert ak.all(os_pairs.leg1.charge == -os_pairs.leg2.charge)
    for pairs in (os_pairs, ss_pairs, every):
        assert not ak.any(pairs.index1 == pairs.index2)
        # an unordered pair as one key; no key appears twice in an event
        key = ak.where(pairs.index1 < pairs.index2, pairs.index1 * 100 + pairs.index2, pairs.index2 * 100 + pairs.index1)
        key = ak.sort(key, axis=1)
        assert not ak.any(key[:, 1:] == key[:, :-1])
    assert ak.all(every.charge_product == ak.values_astype(every.leg1.charge * every.leg2.charge, np.int64))
    assert str(ak.type(every.charge_product)).endswith("int64")


# -- 4. leg ordering and input-order independence -----------------------------------------------------


def test_leg1_has_higher_pt():
    for pairs in (all_pairs(random_muons()), all_pairs(make_muons())):
        assert ak.all(pairs.leg1.p4.pt >= pairs.leg2.p4.pt)


def test_equal_pt_keeps_input_order():
    muons = make_muons({"pt": [[30.0, 30.0]], "eta": [[0.0, 1.0]], "phi": [[0.0, 2.0]], "mass": [[M_MU] * 2], "charge": [[1, -1]]})
    pairs = all_pairs(muons)
    assert pairs.index1.tolist() == [[0]] and pairs.index2.tolist() == [[1]]


@pytest.mark.parametrize("charge", ["opposite", "same", "any"])
def test_shuffled_input_gives_same_pairs(charge):
    muons = random_muons(seed=7)
    rng = np.random.default_rng(3)
    keys = ak.unflatten(rng.random(int(ak.sum(muons.num))), muons.num)
    shuffled = muons[ak.argsort(keys, axis=1)]
    assert not ak.all(ak.flatten(shuffled._extra("uid")) == ak.flatten(muons._extra("uid")))  # it really moved
    a, b = make_pairs(muons, charge), make_pairs(shuffled, charge)
    for event in range(len(muons)):
        assert pair_set(a, event) == pair_set(b, event)
    # pT ordering makes even the order of the pairs identical (random pts have no ties)
    assert a.leg1._extra("uid").tolist() == b.leg1._extra("uid").tolist()
    assert a.leg2._extra("uid").tolist() == b.leg2._extra("uid").tolist()


# -- 5. kinematics through the pair API ------------------------------------------------------------------


def test_pair_kinematics_equal_layer5_on_legs():
    pairs = all_pairs(random_muons())
    p1, p2 = pairs.leg1.p4, pairs.leg2.p4
    for prop, func in (("mass", invariant_mass), ("pt", pair_pt), ("eta", pair_eta), ("phi", pair_phi),
                       ("rapidity", pair_rapidity), ("delta_r", delta_r)):
        assert ak.all(getattr(pairs, prop) == func(p1, p2)), prop


def test_z_at_rest_gives_pdg_mass():
    p = math.sqrt((Z_MASS / 2) ** 2 - M_MU**2)  # each muon's momentum in the Z rest frame
    muons = make_muons({"pt": [[p, p]], "eta": [[0.0, 0.0]], "phi": [[0.0, math.pi]], "mass": [[M_MU, M_MU]], "charge": [[-1, 1]]})
    pairs = opposite_sign_pairs(muons)
    assert pairs.num.tolist() == [1]
    assert pairs.mass[0, 0] == pytest.approx(Z_MASS, abs=1e-9)
    assert pairs.pt[0, 0] == pytest.approx(0.0, abs=1e-9)


def test_float32_input_gives_float64_output():
    pairs = all_pairs(make_muons(dtype=np.float32))
    for prop in ("mass", "pt", "rapidity", "delta_r"):
        assert str(ak.type(getattr(pairs, prop))).endswith("float64"), prop
    assert str(ak.type(pairs.leg1.p4.pt)).endswith("float64")


# -- 6. best_pair and multiplicity --------------------------------------------------------------------------


def _massless(pt, phi, charge):
    """One event of massless muons at eta = 0, where m^2 = 2 pt1 pt2 (1 - cos dphi) exactly."""
    n = len(pt)
    return make_muons({"pt": [pt], "eta": [[0.0] * n], "phi": [phi], "mass": [[0.0] * n], "charge": [charge]})


# m0 (50, +) and m1 (45, +) are the leading two but same-sign. OS pairs:
#   (0,3): pt sum 94, (1,3): 89, (0,2): 80, (1,2): 75
BEST = _massless([50.0, 45.0, 30.0, 44.0], [0.0, math.pi / 2, math.pi, -2.0], [1, 1, -1, -1])


def _mass(i, j):
    pt, phi = [50.0, 45.0, 30.0, 44.0], [0.0, math.pi / 2, math.pi, -2.0]
    return math.sqrt(2 * pt[i] * pt[j] * (1 - math.cos(phi[i] - phi[j])))


def test_best_pair_strategies_pick_the_right_pair():
    os_pairs = opposite_sign_pairs(BEST)
    assert sorted(zip(os_pairs.index1[0].tolist(), os_pairs.index2[0].tolist())) == [(0, 2), (0, 3), (1, 2), (1, 3)]
    for i, j, m in zip(os_pairs.index1[0].tolist(), os_pairs.index2[0].tolist(), os_pairs.mass[0].tolist()):
        assert m == pytest.approx(_mass(i, j), rel=1e-12)

    hp = best_pair(os_pairs)  # default = highest_pt_sum
    assert (hp.index1.tolist(), hp.index2.tolist()) == ([[0]], [[3]])

    # (1,3) has mass ~87.0 GeV, the closest of the four to 91.19
    assert min(((i, j) for i, j in [(0, 2), (0, 3), (1, 2), (1, 3)]), key=lambda p: abs(_mass(*p) - Z_MASS)) == (1, 3)
    cl = best_pair(os_pairs, "closest_to", target=Z_MASS)
    assert (cl.index1.tolist(), cl.index2.tolist()) == ([[1]], [[3]])
    cl_low = best_pair(os_pairs, "closest_to", target=50.0)  # (1,2) is ~52 GeV
    assert (cl_low.index1.tolist(), cl_low.index2.tolist()) == ([[1]], [[2]])

    # the two leading muons are same-sign: "leading" gives nothing on OS pairs and never falls back
    assert best_pair(os_pairs, "leading").num.tolist() == [0]
    lead_any = best_pair(all_pairs(BEST), "leading")
    assert (lead_any.index1.tolist(), lead_any.index2.tolist()) == ([[0]], [[1]])


def test_best_pair_on_hand_events():
    os_pairs = opposite_sign_pairs(make_muons())
    hp = best_pair(os_pairs, "highest_pt_sum")
    # event 3: OS (1,2) 100 vs (2,0) 60; event 4: (3,2) 75 is the largest
    assert hp.index1.tolist() == [[], [], [1], [1], [3], []]
    assert hp.index2.tolist() == [[], [], [0], [2], [2], []]
    lead = best_pair(os_pairs, "leading")
    # event 3 leading two (1, 2) are OS; event 4 leading two (3, 1) are SS
    assert lead.index1.tolist() == [[], [], [1], [1], [], []]


@pytest.mark.parametrize("strategy,kw", [("highest_pt_sum", {}), ("leading", {}), ("closest_to", {"target": Z_MASS})])
def test_best_pair_at_most_one_per_event(strategy, kw):
    pairs = all_pairs(random_muons())
    best = best_pair(pairs, strategy, **kw)
    assert len(best) == len(pairs)
    assert ak.all(best.num <= 1)
    # with no charge requirement the leading pair always exists, so every strategy picks one when it can
    np.testing.assert_array_equal(ak.to_numpy(best.num == 1), ak.to_numpy(pairs.num >= 1))
    np.testing.assert_array_equal(best.event_index, pairs.event_index)
    if strategy == "highest_pt_sum":
        assert ak.all(ak.max(pairs.leg1.p4.pt + pairs.leg2.p4.pt, axis=1)[pairs.num > 0]
                      == ak.flatten(best.leg1.p4.pt + best.leg2.p4.pt))
    if strategy == "closest_to":
        assert ak.all(ak.min(abs(pairs.mass - Z_MASS), axis=1)[pairs.num > 0] == ak.flatten(abs(best.mass - Z_MASS)))


def test_best_pair_argument_errors():
    pairs = all_pairs(make_muons())
    with pytest.raises(ValueError, match="requires target"):
        best_pair(pairs, "closest_to")
    with pytest.raises(ValueError, match="only used by"):
        best_pair(pairs, "highest_pt_sum", target=91.0)
    with pytest.raises(ValueError, match="strategy must be one of"):
        best_pair(pairs, "closest")
    with pytest.raises(ValueError, match="finite"):
        best_pair(pairs, "closest_to", target=float("nan"))
    with pytest.raises(TypeError):
        best_pair(make_muons())


def test_multiplicity():
    m = multiplicity(all_pairs(make_muons()))  # pair counts 0, 0, 1, 3, 6, 1
    assert isinstance(m, PairMultiplicity)
    assert m.to_dict() == {"0": 2, "1": 2, "2": 0, "3+": 2}
    assert (m.n_events, m.n_pairs) == (6, 11)
    assert m.zero + m.one + m.two + m.three_or_more == m.n_events
    assert multiplicity(opposite_sign_pairs(make_muons())).to_dict() == {"0": 3, "1": 1, "2": 1, "3+": 1}
    assert "3+" in str(m) and "11 pairs" in str(m)


# -- 7. event_index through a Selection ---------------------------------------------------------------------


def test_event_index_carried_through_selection():
    muons = make_muons()
    sel = Selection(muons).min_pt(24.0).require(2)
    kept = np.flatnonzero(ak.to_numpy(ak.sum(muons.p4.pt > 24.0, axis=1)) >= 2)
    np.testing.assert_array_equal(sel.event_index, kept)  # events 2, 3, 4, 5
    pairs = all_pairs(sel)
    np.testing.assert_array_equal(pairs.event_index, kept)
    # every leg is the original muon at [event_index][position in the selected list]
    original_pt = ak.Array(HAND["pt"])[kept]
    selected = original_pt[original_pt > 24.0]
    assert pairs.leg1.p4.pt.tolist() == selected[pairs.index1].tolist()
    assert pairs.leg2.p4.pt.tolist() == selected[pairs.index2].tolist()
    # and through to the file's arrays, event by event
    for row, pts in zip(pairs.event_index, pairs.leg1.p4.pt.tolist()):
        assert set(pts) <= set(HAND["pt"][row])
    assert not pairs.event_index.flags.writeable


def test_plain_muons_event_index_is_arange():
    np.testing.assert_array_equal(all_pairs(make_muons()).event_index, np.arange(6))


# -- container behaviour ---------------------------------------------------------------------------------------


def test_indexing_returns_muonpairs():
    pairs = all_pairs(make_muons())
    heavy = pairs[pairs.mass > 50]
    assert isinstance(heavy, MuonPairs) and len(heavy) == 6
    assert ak.all(heavy.mass > 50)
    np.testing.assert_array_equal(heavy.event_index, np.arange(6))
    sub = pairs[2:5]
    assert len(sub) == 3 and sub.index1.tolist() == EXPECTED["any"][0][2:5]
    np.testing.assert_array_equal(sub.event_index, [2, 3, 4])
    has = pairs[ak.to_numpy(pairs.num > 0)]
    np.testing.assert_array_equal(has.event_index, [2, 3, 4, 5])
    picked = pairs[[4, 2]]
    np.testing.assert_array_equal(picked.event_index, [4, 2])
    with pytest.raises(TypeError, match="single integer"):
        pairs[0]


def test_to_awkward():
    pairs = all_pairs(make_muons())
    rec = pairs.to_awkward()
    assert {"leg1", "leg2", "index1", "index2", "charge_product", "mass", "pt", "eta", "phi", "rapidity", "delta_r", "event_index"} <= set(rec.fields)
    assert rec.mass.tolist() == pairs.mass.tolist()
    assert rec.leg1.pt.tolist() == pairs.leg1.p4.pt.tolist()
    assert rec.event_index.tolist() == [[i] * n for i, n in enumerate(pairs.num.tolist())]
    assert "n_pairs=11" in repr(pairs)


# -- edge cases -------------------------------------------------------------------------------------------------------


def test_events_with_fewer_than_two_muons():
    muons = make_muons({"pt": [[], [10.0], []], "eta": [[], [0.0], []], "phi": [[], [0.0], []], "mass": [[], [M_MU], []], "charge": [[], [1], []]})
    for charge in ("opposite", "same", "any"):
        pairs = make_pairs(muons, charge)
        assert len(pairs) == 3 and pairs.num.tolist() == [0, 0, 0]
        assert pairs.mass.tolist() == [[], [], []]
        assert best_pair(pairs).num.tolist() == [0, 0, 0]
    assert multiplicity(all_pairs(muons)).to_dict() == {"0": 3, "1": 0, "2": 0, "3+": 0}


def test_empty_and_untyped_input():
    empty = make_muons({k: ak.Array([[0.0]])[0:0] for k in ("pt", "eta", "phi", "mass")} | {"charge": ak.Array([[1]])[0:0]})
    untyped = Muon(FourMomentum([[], []], [[], []], [[], []], [[], []]), [[], []])
    for muons, n in ((empty, 0), (untyped, 2)):
        for charge in ("opposite", "same", "any"):
            pairs = make_pairs(muons, charge)
            assert len(pairs) == n and pairs.n_pairs == 0
            assert pairs.mass.tolist() == [[]] * n
            assert pairs.charge_product.tolist() == [[]] * n
            for strategy, kw in (("highest_pt_sum", {}), ("leading", {}), ("closest_to", {"target": Z_MASS})):
                assert best_pair(pairs, strategy, **kw).n_pairs == 0
            assert multiplicity(pairs).n_events == n
            assert len(pairs.to_awkward()) == n


def test_all_events_removed_by_selection():
    sel = Selection(make_muons()).require(10)
    assert len(sel) == 0
    pairs = opposite_sign_pairs(sel)
    assert len(pairs) == 0 and pairs.event_index.tolist() == []
    assert len(best_pair(pairs)) == 0
    assert multiplicity(pairs).to_dict() == {"0": 0, "1": 0, "2": 0, "3+": 0}


def test_bad_inputs():
    with pytest.raises(ValueError, match="charge must be one of"):
        make_pairs(make_muons(), "opposite_sign")
    electrons = Electron(FourMomentum([[30.0, 20.0]], [[0.0, 0.0]], [[0.0, 1.0]], [[0.0005, 0.0005]]), [[1, -1]])
    with pytest.raises(TypeError, match="Muon"):
        make_pairs(electrons)
    with pytest.raises(TypeError, match="Muon"):
        make_pairs(Selection(electrons))
    with pytest.raises(ValueError, match="jagged"):
        make_pairs(make_muons()[3])


def test_package_exports():
    for name in ("make_pairs", "opposite_sign_pairs", "same_sign_pairs", "all_pairs", "best_pair", "multiplicity", "MuonPairs"):
        assert getattr(cmsopen, name) is not None and name in cmsopen.__all__


# -- 8. real file: pair counts vs an independent computation --------------------------------------------------------


@pytest.mark.skipif(not REAL_FILE.exists(), reason=f"real CMS file not downloaded: {REAL_FILE} (see DATA.md)")
def test_real_file_pair_counts_match_independent_numpy():
    """Pair counts on the first 100,000 raw events equal counting formulas computed without cmsopen."""
    n_read = 100_000
    with uproot.open(REAL_FILE) as f:
        q = f["Events"]["Muon_charge"].array(entry_stop=n_read)
    counts = ak.to_numpy(ak.num(q))
    flat = ak.to_numpy(ak.flatten(q))
    assert set(np.unique(flat)) == {-1, 1}  # real muons: the OS/SS split is complete
    event_of = np.repeat(np.arange(len(counts)), counts)
    n_plus = np.bincount(event_of, weights=(flat > 0), minlength=len(counts)).astype(np.int64)
    n_minus = counts - n_plus
    expected = {
        "opposite": n_plus * n_minus,
        "same": n_plus * (n_plus - 1) // 2 + n_minus * (n_minus - 1) // 2,
        "any": counts * (counts - 1) // 2,
    }

    with open_events(REAL_FILE) as ev:
        muons = Muon.from_events(ev, entry_stop=n_read, fields=("pt", "eta", "phi", "mass", "charge"))
    assert len(muons) == n_read
    for charge, exp in expected.items():
        pairs = make_pairs(muons, charge)
        np.testing.assert_array_equal(ak.to_numpy(pairs.num), exp, err_msg=charge)
        assert not ak.any(pairs.index1 == pairs.index2)
        assert ak.all(pairs.leg1.p4.pt >= pairs.leg2.p4.pt)
    assert expected["any"].sum() > 100_000  # the test exercises real combinatorics
