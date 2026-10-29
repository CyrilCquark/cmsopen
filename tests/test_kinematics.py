import awkward as ak
import numpy as np
import pytest

import cmsopen
from cmsopen import FourMomentum
from cmsopen.kinematics import (
    delta_eta,
    delta_phi,
    delta_r,
    invariant_mass,
    invariant_mass_squared,
    pair_eta,
    pair_phi,
    pair_pt,
    pair_rapidity,
    pair_summary,
    sum_four_momenta,
)

Z_MASS = 91.1876
JPSI_MASS = 3.0969
MU_MASS = 0.10566


def _flat(x) -> np.ndarray:
    return ak.to_numpy(ak.flatten(x, axis=None))


def _p4(pt, eta, phi, mass) -> FourMomentum:
    return FourMomentum.from_arrays(*(ak.Array(x) for x in (pt, eta, phi, mass)))


def decay_at_rest(
    parent_mass: float, theta: float, phi: float, m: float = MU_MASS
) -> tuple[FourMomentum, FourMomentum]:
    """Two-body decay of a parent at rest: back-to-back legs with p = sqrt((M/2)^2 - m^2)."""
    p = np.sqrt((parent_mass / 2) ** 2 - m**2)
    legs = []
    for th, ph in [(theta, phi), (np.pi - theta, phi + np.pi if phi <= 0 else phi - np.pi)]:
        legs.append(_p4([[p * np.sin(th)]], [[-np.log(np.tan(th / 2))]], [[ph]], [[m]]))
    return legs[0], legs[1]


def boost_z(p4: FourMomentum, w: float) -> FourMomentum:
    """Boost along the beam axis by rapidity w: pt and phi unchanged, (E, pz) rotate hyperbolically."""
    e, pz = p4.energy, p4.pz
    pz_new = pz * np.cosh(w) + e * np.sinh(w)
    return FourMomentum.from_arrays(p4.pt, np.arcsinh(pz_new / p4.pt), p4.phi, p4.mass)


@pytest.fixture
def random_pairs() -> tuple[FourMomentum, FourMomentum]:
    """Seeded jagged pairs of muons (0-3 pairs per event, including empty events)."""
    rng = np.random.default_rng(91)
    counts = rng.integers(0, 4, size=300)
    counts[:2] = 0
    n = int(counts.sum())

    def leg():
        return _p4(
            *(
                ak.unflatten(x, counts)
                for x in (
                    rng.uniform(5.0, 200.0, n),
                    rng.uniform(-2.4, 2.4, n),
                    rng.uniform(-np.pi, np.pi, n),
                    np.full(n, MU_MASS),
                )
            )
        )

    return leg(), leg()


def test_exports():
    for name in ("invariant_mass", "pair_summary", "delta_r", "sum_four_momenta", "pair_rapidity"):
        assert getattr(cmsopen, name) is globals()[name]


# -- 1. resonances at rest ------------------------------------------------------


@pytest.mark.parametrize(
    "parent, theta, phi",
    [(Z_MASS, np.pi / 2, 0.0), (JPSI_MASS, np.pi / 2, 0.0), (Z_MASS, 0.7, -2.1), (JPSI_MASS, 2.3, 1.2)],
)
def test_parent_at_rest(parent, theta, phi):
    p1, p2 = decay_at_rest(parent, theta, phi)
    assert _flat(invariant_mass(p1, p2))[0] == pytest.approx(parent, rel=1e-9)
    assert _flat(pair_pt(p1, p2))[0] == pytest.approx(0.0, abs=1e-9)
    assert _flat(delta_r(p1, p2))[0] >= np.pi - 1e-12


def test_parent_at_rest_random_directions():
    rng = np.random.default_rng(1876)
    for theta, phi in zip(np.arccos(rng.uniform(-0.95, 0.95, 20)), rng.uniform(-np.pi, np.pi, 20), strict=False):
        p1, p2 = decay_at_rest(Z_MASS, theta, phi)
        assert _flat(invariant_mass(p1, p2))[0] == pytest.approx(Z_MASS, rel=1e-9)


# -- 2. massless hand cases -----------------------------------------------------


def test_collinear_massless_pair_has_zero_mass():
    exact = invariant_mass(_p4([[30.0]], [[0.0]], [[0.0]], [[0.0]]), _p4([[50.0]], [[0.0]], [[0.0]], [[0.0]]))
    assert _flat(exact)[0] == 0.0
    p1 = _p4([[30.0]], [[1.3]], [[0.4]], [[0.0]])
    p2 = _p4([[50.0]], [[1.3]], [[0.4]], [[0.0]])
    energy = _flat(p1.energy + p2.energy)[0]
    # Rounding in E^2 - |p|^2 leaves at most ~sqrt(eps) * E; the clip keeps it real.
    assert _flat(invariant_mass(p1, p2))[0] <= 1e-7 * energy


def test_massless_at_right_angle():
    e1, e2 = 20.0, 45.0
    m = invariant_mass(_p4([[e1]], [[0.0]], [[0.0]], [[0.0]]), _p4([[e2]], [[0.0]], [[np.pi / 2]], [[0.0]]))
    assert _flat(m)[0] == pytest.approx(np.sqrt(2 * e1 * e2), rel=1e-12)


# -- 3. Lorentz invariance under longitudinal boosts ----------------------------


@pytest.mark.parametrize("w", [-2.0, -0.5, 0.3, 1.0, 2.5])
def test_boost_along_z(random_pairs, w):
    p1, p2 = random_pairs
    b1, b2 = boost_z(p1, w), boost_z(p2, w)
    np.testing.assert_allclose(_flat(invariant_mass(b1, b2)), _flat(invariant_mass(p1, p2)), rtol=1e-9)
    np.testing.assert_allclose(_flat(pair_rapidity(b1, b2)), _flat(pair_rapidity(p1, p2)) + w, rtol=0, atol=1e-9)
    np.testing.assert_allclose(_flat(pair_pt(b1, b2)), _flat(pair_pt(p1, p2)), rtol=1e-9)


# -- 4. closed form for massless legs -------------------------------------------


def test_massless_closed_form(random_pairs):
    p1, p2 = (FourMomentum.from_arrays(p.pt, p.eta, p.phi, p.pt * 0) for p in random_pairs)
    expected = 2 * p1.pt * p2.pt * (np.cosh(p1.eta - p2.eta) - np.cos(p1.phi - p2.phi))
    np.testing.assert_allclose(_flat(invariant_mass_squared(p1, p2)), _flat(expected), rtol=1e-9)
    np.testing.assert_allclose(_flat(invariant_mass(p1, p2)), np.sqrt(_flat(expected)), rtol=1e-9)


# -- 5. angles ------------------------------------------------------------------


def test_delta_phi_wrapping():
    assert delta_phi(3.0, -3.0) == pytest.approx(6.0 - 2 * np.pi)
    assert delta_phi(-3.0, 3.0) == pytest.approx(2 * np.pi - 6.0)
    assert delta_phi(0.5, 0.2) == pytest.approx(0.3)
    rng = np.random.default_rng(3)
    a = ak.unflatten(rng.uniform(-np.pi, np.pi, 1000), [500, 0, 500])
    b = ak.unflatten(rng.uniform(-np.pi, np.pi, 1000), [500, 0, 500])
    d = _flat(delta_phi(a, b))
    assert np.all((d >= -np.pi) & (d <= np.pi))
    np.testing.assert_allclose(np.cos(d), np.cos(_flat(a) - _flat(b)), atol=1e-12)


def test_delta_r_hand_cases():
    assert _flat(delta_r(_p4([[10.0]], [[0.0]], [[0.0]], [[0.0]]), _p4([[10.0]], [[0.3]], [[0.4]], [[0.0]])))[
        0
    ] == pytest.approx(0.5)
    across_seam = delta_r(_p4([[10.0]], [[1.0]], [[3.0]], [[0.0]]), _p4([[10.0]], [[1.0]], [[-3.0]], [[0.0]]))
    assert _flat(across_seam)[0] == pytest.approx(2 * np.pi - 6.0)
    assert delta_eta(1.5, -0.5) == pytest.approx(2.0)


def test_symmetry_under_swapping_legs(random_pairs):
    p1, p2 = random_pairs
    for f in (invariant_mass, pair_pt, pair_eta, pair_phi, pair_rapidity, delta_r):
        np.testing.assert_allclose(_flat(f(p1, p2)), _flat(f(p2, p1)), rtol=1e-12, atol=1e-12)
    np.testing.assert_allclose(_flat(delta_phi(p1.phi, p2.phi)), -_flat(delta_phi(p2.phi, p1.phi)), atol=1e-12)


# -- 6. cross-check with vector -------------------------------------------------


def test_agrees_with_vector(random_pairs):
    vector = pytest.importorskip("vector")
    p1, p2 = random_pairs
    v1, v2 = (vector.zip({"pt": p.pt, "eta": p.eta, "phi": p.phi, "mass": p.mass}) for p in (p1, p2))
    total = v1 + v2
    s = pair_summary(p1, p2)
    for ours, theirs in [
        (s.mass, total.mass),
        (s.pt, total.pt),
        (s.eta, total.eta),
        (s.phi, total.phi),
        (s.rapidity, total.rapidity),
        (s.delta_r, v1.deltaR(v2)),
        (s.delta_phi, v1.deltaphi(v2)),
    ]:
        np.testing.assert_allclose(_flat(ours), _flat(theirs), rtol=1e-9, atol=1e-9)
    px, py, pz, e = sum_four_momenta(p1, p2)
    for ours, theirs in [(px, total.px), (py, total.py), (pz, total.pz), (e, total.E)]:
        np.testing.assert_allclose(_flat(ours), _flat(theirs), rtol=1e-12, atol=1e-9)


# -- 7. jagged behavior ---------------------------------------------------------


def test_structure_preserved_and_empty_events(random_pairs):
    p1, p2 = random_pairs
    s = pair_summary(p1, p2)
    assert ak.fields(s) == ["mass", "pt", "eta", "phi", "rapidity", "delta_r", "delta_phi"]
    assert len(s) == len(p1)
    assert ak.num(s).tolist() == p1.num.tolist()
    assert s[:2].tolist() == [[], []]
    assert ak.num(invariant_mass(p1, p2)).tolist() == p1.num.tolist()


def test_mismatched_structure_raises(random_pairs):
    p1, p2 = random_pairs
    with pytest.raises(ValueError, match="different particle counts"):
        invariant_mass(p1, p2[p2.pt > 50])
    with pytest.raises(ValueError, match="same events"):
        pair_summary(p1, p2[:10])
    with pytest.raises(ValueError, match="different particle counts"):
        delta_phi(p1.phi, p2.phi[p2.pt > 50])
    with pytest.raises(ValueError, match="scalar and an array"):
        delta_phi(p1.phi, 0.0)
    with pytest.raises(TypeError):
        invariant_mass(p1.pt, p2.pt)


def test_float32_input_gives_float64_output():
    f32 = ak.values_astype(ak.Array([[45.0, 40.0], []]), np.float32)
    p1 = FourMomentum.from_arrays(
        f32, f32 * 0 + np.float32(0.3), f32 * 0 + np.float32(1.0), f32 * 0 + np.float32(MU_MASS)
    )
    p2 = FourMomentum.from_arrays(
        f32, f32 * 0 - np.float32(0.4), f32 * 0 - np.float32(2.0), f32 * 0 + np.float32(MU_MASS)
    )
    s = pair_summary(p1, p2)
    for field in ak.fields(s):
        assert ak.type(s[field]).content.content.primitive == "float64"
    for x in (*sum_four_momenta(p1, p2), delta_eta(f32, f32)):
        assert ak.type(x).content.content.primitive == "float64"
