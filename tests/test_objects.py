from pathlib import Path

import awkward as ak
import numpy as np
import pytest
from synthetic import ELECTRON_PT, MUON_CHARGE, MUON_PT, N_EVENTS, REAL_FILE

import cmsopen
from cmsopen import Electron, FourMomentum, Muon, open_events
from cmsopen.ingestion import ELECTRON_BRANCHES_DEFAULT, MUON_BRANCHES_DEFAULT

MUON_MASS = 0.1056583755


def _flat(x) -> np.ndarray:
    return ak.to_numpy(ak.flatten(x, axis=None))


def _single(pt, eta, phi, mass) -> FourMomentum:
    return FourMomentum.from_arrays([[pt]], [[eta]], [[phi]], [[mass]])


@pytest.fixture
def random_p4() -> FourMomentum:
    """Seeded random jagged four-momenta spanning soft to TeV muons, with empty events."""
    rng = np.random.default_rng(20120)
    counts = rng.integers(0, 5, size=500)
    counts[:3] = 0
    n = int(counts.sum())
    pt = np.exp(rng.uniform(np.log(0.5), np.log(2000.0), n))
    eta = rng.uniform(-2.4, 2.4, n)
    phi = rng.uniform(-np.pi, np.pi, n)
    mass = np.full(n, MUON_MASS)
    return FourMomentum.from_arrays(*(ak.unflatten(x, counts) for x in (pt, eta, phi, mass)))


def test_exports():
    assert cmsopen.FourMomentum is FourMomentum
    assert cmsopen.Muon is Muon and cmsopen.Electron is Electron


# -- 1. hand-computed cases -----------------------------------------------------


def test_along_x_massless():
    px, py, pz, e = (float(_flat(c)[0]) for c in _single(10.0, 0.0, 0.0, 0.0).as_cartesian())
    assert (px, py, pz, e) == pytest.approx((10.0, 0.0, 0.0, 10.0), abs=1e-12)


def test_phi_quarter_turn():
    p4 = _single(10.0, 0.0, np.pi / 2, 0.0)
    assert _flat(p4.px)[0] == pytest.approx(0.0, abs=1e-12)
    assert _flat(p4.py)[0] == pytest.approx(10.0)


def test_eta_one():
    p4 = _single(10.0, 1.0, 0.0, 0.0)
    assert _flat(p4.pz)[0] == pytest.approx(10.0 * np.sinh(1.0))
    assert _flat(p4.p)[0] == pytest.approx(10.0 * np.cosh(1.0))
    assert _flat(p4.energy)[0] == pytest.approx(10.0 * np.cosh(1.0))


def test_near_rest_energy_is_mass():
    e = _flat(_single(1e-6, 0.3, 1.0, MUON_MASS).energy)[0]
    assert e == pytest.approx(MUON_MASS, rel=1e-9)
    assert e >= MUON_MASS


# -- 2. mass-shell identity -----------------------------------------------------


def test_mass_shell_identity(random_p4: FourMomentum):
    px, py, pz, e = random_p4.as_cartesian()
    residual = _flat(e**2 - px**2 - py**2 - pz**2 - random_p4.mass**2)
    # E^2 and p^2 are large and nearly equal; precision is relative to E^2.
    assert np.all(np.abs(residual) <= 16 * np.finfo(np.float64).eps * _flat(e**2))
    assert np.all(_flat(random_p4.energy) >= _flat(random_p4.mass))


# -- 3. cross-check with the vector library -------------------------------------


def test_agrees_with_vector(random_p4: FourMomentum):
    vector = pytest.importorskip("vector")
    v = vector.zip({"pt": random_p4.pt, "eta": random_p4.eta, "phi": random_p4.phi, "mass": random_p4.mass})
    for ours, theirs in [
        (random_p4.px, v.px),
        (random_p4.py, v.py),
        (random_p4.pz, v.pz),
        (random_p4.energy, v.E),
    ]:
        np.testing.assert_allclose(_flat(ours), _flat(theirs), rtol=1e-12, atol=1e-12)


# -- 4. jagged behavior ---------------------------------------------------------


def test_num_and_empty_events(random_p4: FourMomentum):
    assert len(random_p4) == 500
    assert ak.num(random_p4.pt).tolist() == random_p4.num.tolist()
    assert random_p4.num[:3].tolist() == [0, 0, 0]
    assert random_p4[:3].energy.tolist() == [[], [], []]


def test_jagged_mask_keeps_structure_and_class(random_p4: FourMomentum):
    mask = random_p4.pt > 20
    sel = random_p4[mask]
    assert isinstance(sel, FourMomentum)
    assert len(sel) == len(random_p4)
    assert sel.num.tolist() == ak.sum(mask, axis=1).tolist()
    assert ak.all(sel.pt > 20)
    np.testing.assert_array_equal(_flat(sel.energy), _flat(random_p4.energy[mask]))


def test_slice_and_event_indexing(random_p4: FourMomentum):
    assert isinstance(random_p4[10:20], FourMomentum) and len(random_p4[10:20]) == 10
    picked = random_p4[[5, 7]]
    assert picked.num.tolist() == [random_p4.num[5], random_p4.num[7]]
    one = random_p4[5]
    assert isinstance(one, FourMomentum)
    assert one.num == random_p4.num[5]
    assert one.pt.tolist() == random_p4.pt[5].tolist()
    assert "n_events=500" in repr(random_p4)


def test_mismatched_counts_raise():
    with pytest.raises(ValueError, match="different particle counts"):
        FourMomentum.from_arrays([[1.0, 2.0], []], [[0.0], [0.0]], [[0.0, 0.0], []], [[0.0, 0.0], []])
    with pytest.raises(ValueError, match="same events"):
        FourMomentum.from_arrays([[1.0]], [[0.0], []], [[0.0]], [[0.0]])
    p4 = FourMomentum.from_arrays([[1.0, 2.0]], [[0.0, 0.0]], [[0.0, 0.0]], [[0.0, 0.0]])
    with pytest.raises(ValueError, match="'charge'"):
        Muon(p4, [[1]])
    with pytest.raises(ValueError, match="'tightId'"):
        Muon(p4, [[1, -1]], {"tightId": [[True]]})


def test_collection_mask_indexes_all_fields():
    p4 = FourMomentum.from_arrays([[30.0, 5.0], [], [12.0]], [[0.1, 0.2], [], [1.5]], [[0.0, 1.0], [], [2.0]],
                                  [[MUON_MASS] * 2, [], [MUON_MASS]])
    mu = Muon(
        p4, [[1, -1], [], [1]], {"tightId": [[True, False], [], [True]], "pfRelIso04_all": [[0.05, 0.9], [], [0.1]]}
    )
    tight = mu[mu.tightId]
    assert isinstance(tight, Muon)
    assert tight.num.tolist() == [1, 0, 1]
    assert tight.charge.tolist() == [[1], [], [1]]
    assert tight.iso.tolist() == [[0.05], [], [0.1]]
    assert tight.p4.pt.tolist() == [[30.0], [], [12.0]]
    with pytest.raises(AttributeError, match="mediumId"):
        _ = mu.mediumId


# -- 5. dtype -------------------------------------------------------------------


def test_float32_inputs_become_float64():
    f32 = ak.values_astype(ak.Array([[40.0, 3.0], []]), np.float32)
    p4 = FourMomentum.from_arrays(f32, f32 * 0, f32 * 0, f32 * 0 + np.float32(MUON_MASS))
    for arr in (p4.pt, p4.eta, p4.phi, p4.mass, *p4.as_cartesian(), p4.p):
        assert ak.type(arr).content.content.primitive == "float64"


# -- 6. from_events -------------------------------------------------------------


def test_from_events_synthetic(full_nano_file: Path):
    with open_events(full_nano_file) as events:
        mu = Muon.from_events(events)
        el = Electron.from_events(events, entry_start=1, entry_stop=5)
    assert isinstance(mu, Muon) and len(mu) == N_EVENTS
    assert mu.p4.pt.tolist() == MUON_PT
    assert mu.charge.tolist() == MUON_CHARGE
    assert mu.tightId.tolist() == [[x > 25 for x in ev] for ev in MUON_PT]
    for name in ("iso", "looseId", "mediumId", "softId", "isGlobal", "isTracker", "isPFcand", "dxy", "dz"):
        assert ak.num(getattr(mu, name)).tolist() == mu.num.tolist()
    assert isinstance(el, Electron) and len(el) == 4
    assert el.p4.pt.tolist() == ELECTRON_PT[1:5]
    assert el.cut_based.tolist() == [[1], [], [], [1, 0]]
    for name in ("iso", "isEB", "isEE", "convVeto", "dxy", "dz"):
        assert ak.num(getattr(el, name)).tolist() == el.num.tolist()


@pytest.mark.skipif(not REAL_FILE.exists(), reason=f"real CMS file not downloaded: {REAL_FILE} (see DATA.md)")
def test_from_events_real_file():
    with open_events(REAL_FILE) as events:
        mu = Muon.from_events(events, entry_stop=100_000)
        el = Electron.from_events(events, entry_stop=1_000)
    assert mu.p4.pt[0].to_numpy() == pytest.approx([71.24144, 25.51886, 3.74997], abs=1e-5)
    assert mu.charge[0].tolist() == [-1, 1, 1]
    assert ak.all(mu.p4.energy >= mu.p4.mass)
    assert int(ak.sum(mu.num)) == 474_335
    assert ak.all(ak.num(el.cut_based) == el.num)


# -- 7. to_awkward round trip ---------------------------------------------------


def test_to_awkward_round_trip(full_nano_file: Path):
    with open_events(full_nano_file) as events:
        mu = Muon.from_events(events)
    rec = mu.to_awkward()
    assert ak.fields(rec) == list(MUON_BRANCHES_DEFAULT)
    assert str(ak.type(rec)).startswith(
        f"{N_EVENTS} * var * {{pt: float64, eta: float64, phi: float64, mass: float64, charge: int32"
    )
    back = Muon.from_record(rec)
    assert ak.array_equal(back.to_awkward(), rec)
    assert ak.fields(Electron.from_record(Electron(mu.p4, mu.charge).to_awkward()).to_awkward()) == [
        "pt",
        "eta",
        "phi",
        "mass",
        "charge",
    ]
    assert set(ELECTRON_BRANCHES_DEFAULT) >= {"cutBased", "pfRelIso03_all"}
