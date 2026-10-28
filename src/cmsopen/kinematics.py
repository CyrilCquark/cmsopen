"""Layer 5: two-body kinematics (invariant mass, pair pT, rapidity, delta R).

Physics context
---------------
When a particle of mass M decays, say Z -> mu+ mu-, energy and momentum are
conserved: the four-momentum (E, px, py, pz) of the Z equals the sum of its
daughters' four-momenta. The quantity

    M^2 = E^2 - |p|^2          (natural units, c = 1)

is a Lorentz invariant: every observer, whatever their velocity, computes
the same value, and for a single particle it is that particle's rest mass
squared. Applying it to the *summed* four-momentum of the two muons
therefore recovers the mass of the parent, no matter how fast the Z was
moving or in which direction it decayed. This is the invariant mass, and
it is how unstable particles that never reach the detector are "seen".

Inputs and shapes
-----------------
Every pair function takes two :class:`~cmsopen.objects.FourMomentum`
objects with the *same* jagged structure, for example the first and
second leg of each candidate pair in each event (layer 4 builds these).
Entry ``[i][j]`` of ``p1`` and of ``p2`` together form one pair, and the
result has the same structure. Mismatched structures raise ValueError;
nothing is broadcast or truncated. All results are float64, in GeV and
radians. Formulas are written out with numpy and are fully vectorized.
"""

from __future__ import annotations

from numbers import Real
from typing import Any

import awkward as ak
import numpy as np

from cmsopen.objects import FourMomentum, _check_same_structure

__all__ = [
    "delta_eta",
    "delta_phi",
    "delta_r",
    "invariant_mass",
    "invariant_mass_squared",
    "pair_eta",
    "pair_phi",
    "pair_pt",
    "pair_rapidity",
    "pair_summary",
    "sum_four_momenta",
]


def _check_pair(p1: FourMomentum, p2: FourMomentum) -> None:
    if not isinstance(p1, FourMomentum) or not isinstance(p2, FourMomentum):
        raise TypeError(f"expected two FourMomentum objects, got {type(p1).__name__} and {type(p2).__name__}")
    _check_same_structure({"p1": p1.pt, "p2": p2.pt})


def _as_pair_arrays(a: Any, b: Any) -> tuple[Any, Any]:
    """Return float64 versions of two angle arrays, checking they have the same structure.

    Two scalars are allowed (and stay scalars); a scalar is never broadcast
    against an array.
    """
    a_scalar, b_scalar = isinstance(a, (Real, np.number)), isinstance(b, (Real, np.number))
    if a_scalar and b_scalar:
        return np.float64(a), np.float64(b)
    if a_scalar or b_scalar:
        raise ValueError("both arguments must be arrays of the same structure, or both scalars; got a scalar and an array")
    a = ak.values_astype(ak.Array(a), np.float64)
    b = ak.values_astype(ak.Array(b), np.float64)
    _check_same_structure({"first": a, "second": b})
    return a, b


def sum_four_momenta(p1: FourMomentum, p2: FourMomentum) -> tuple[ak.Array, ak.Array, ak.Array, ak.Array]:
    """Return the summed four-momentum ``(px, py, pz, E)`` of each pair, in GeV.

    Four-momentum is conserved in a decay, so for Z -> mu+ mu- the sum of the
    two muon four-vectors *is* the Z four-vector (up to measurement error
    and any radiated photons). Cartesian components add component by
    component; (pt, eta, phi) do not, which is why the sum is done here
    rather than in detector coordinates. All other pair quantities in this
    module are computed from this sum.

    Raises
    ------
    ValueError
        If ``p1`` and ``p2`` do not have the same jagged structure.
    """
    _check_pair(p1, p2)
    return p1.px + p2.px, p1.py + p2.py, p1.pz + p2.pz, p1.energy + p2.energy


def invariant_mass_squared(p1: FourMomentum, p2: FourMomentum) -> ak.Array:
    """Squared invariant mass of each pair, M^2 = (E1 + E2)^2 - |p1 + p2|^2, in GeV^2.

    This is the Minkowski "length" of the summed four-vector. It is the same
    in every inertial frame (a Lorentz invariant), and in the parent's rest
    frame, where the total momentum is zero, it equals the parent's mass
    squared. For physical pairs M^2 >= (m1 + m2)^2 >= 0, but the subtraction
    of two large, nearly equal numbers can give tiny negative values from
    floating-point rounding when the pair is very light or very boosted.
    This function returns the raw value without any guard.
    """
    px, py, pz, e = sum_four_momenta(p1, p2)
    return e**2 - (px**2 + py**2 + pz**2)


def invariant_mass(p1: FourMomentum, p2: FourMomentum) -> ak.Array:
    """Invariant mass of each pair, M = sqrt((E1 + E2)^2 - |p1 + p2|^2), in GeV.

    Why this reveals the parent: the invariant mass of the decay products
    equals the parent's rest mass because M^2 is Lorentz invariant and the
    parent's momentum is zero in its own rest frame. A Z boson produced with
    any momentum and decaying in any direction gives two muons whose
    invariant mass is the Z mass.

    Why a peak: muon pairs from the Z all cluster at M ~ 91.19 GeV, while
    background pairs (Drell-Yan via a virtual photon, heavy-flavour decays,
    misidentified muons) are spread smoothly over all masses. A histogram
    of M therefore shows a narrow peak on a falling continuum.

    Width of the peak: the Z is unstable (lifetime ~3e-25 s), so by the
    energy-time uncertainty relation its mass is not sharp but follows a
    Breit-Wigner distribution with natural width Gamma_Z = 2.4952 GeV. The
    detector adds its own smearing: muon momenta are measured to roughly
    1-2 % in the barrel (worse at high |eta| and high pt), which spreads the
    observed peak by a Gaussian of comparable size. The measured shape is a
    Breit-Wigner convolved with that resolution (a Voigt profile), which
    layer 6 fits. Final-state photon radiation also shifts some events to
    lower mass, giving a tail on the low side.

    Numerical guard: tiny negative M^2 from rounding are clipped to 0 before
    the square root. That is the ONLY guard; nothing else is altered.
    """
    return np.sqrt(np.maximum(invariant_mass_squared(p1, p2), 0.0))


def pair_pt(p1: FourMomentum, p2: FourMomentum) -> ak.Array:
    """Transverse momentum of each pair (GeV), sqrt(px^2 + py^2) of the summed four-vector.

    The colliding partons have almost no transverse momentum, so a Z
    produced alone would have pT ~ 0. In reality the incoming quarks radiate
    gluons before annihilating (initial-state radiation) and the Z recoils
    against them, giving a pT spectrum that peaks at a few GeV with a long
    tail. The Z pT spectrum is a classic test of QCD.
    """
    px, py, _, _ = sum_four_momenta(p1, p2)
    return np.sqrt(px**2 + py**2)


def pair_phi(p1: FourMomentum, p2: FourMomentum) -> ak.Array:
    """Azimuthal angle (radians, -pi..pi) of the pair's transverse momentum, atan2(py, px).

    Undefined (returned as 0 by atan2) for a pair with exactly zero pT.
    """
    px, py, _, _ = sum_four_momenta(p1, p2)
    return np.arctan2(py, px)


def pair_eta(p1: FourMomentum, p2: FourMomentum) -> ak.Array:
    """Pseudorapidity of the pair's total momentum direction, asinh(pz / pT).

    This is a purely geometric angle, -ln tan(theta/2) of the summed
    three-momentum. For a massive system such as a Z it is NOT its rapidity
    (see :func:`pair_rapidity`); it diverges as the pair's pT goes to 0
    (a pair with exactly zero pT gives +-inf or nan).
    """
    px, py, pz, _ = sum_four_momenta(p1, p2)
    return np.arcsinh(pz / np.sqrt(px**2 + py**2))


def pair_rapidity(p1: FourMomentum, p2: FourMomentum) -> ak.Array:
    """Rapidity of each pair, y = 0.5 ln((E + pz) / (E - pz)), of the summed four-vector.

    Why rapidity: the two colliding partons carry fractions x1 and x2 of
    their protons' momenta, and generally x1 != x2, so the Z is produced
    with an unknown boost along the beam, with y = 0.5 ln(x1/x2) at leading
    order. Rapidity is the natural variable for that motion because a boost
    along z with rapidity w simply shifts every rapidity by w: y -> y + w.
    Differences in rapidity, and the shape of dN/dy, are therefore the same
    in every frame boosted along the beam.

    Why not pseudorapidity: eta equals y only for massless particles
    (E = |p|). For a muon at LHC energies the difference is negligible, but
    a Z with pT of a few GeV is far from massless (M >> pT): its eta can be
    huge while its rapidity stays modest. Physics distributions of massive
    systems are therefore quoted in y.
    """
    _, _, pz, e = sum_four_momenta(p1, p2)
    return 0.5 * np.log((e + pz) / (e - pz))


def delta_phi(phi1: Any, phi2: Any) -> Any:
    """Azimuthal angle difference phi1 - phi2, wrapped into [-pi, pi].

    Azimuth is periodic: phi = 3.0 and phi = -3.0 are only 0.28 rad apart,
    across the +-pi seam, but their raw difference is 6.0. Shifting by pi,
    reducing modulo 2 pi and shifting back maps any difference to the
    equivalent angle in [-pi, pi] (exactly +pi can occur through rounding),
    the shortest signed rotation from phi2 to phi1. Without this, angular separations near the seam would be
    wildly overestimated.

    Parameters
    ----------
    phi1, phi2 : array-like or float
        Angles in radians; two arrays of the same jagged structure, or two
        scalars.
    """
    phi1, phi2 = _as_pair_arrays(phi1, phi2)
    return np.mod(phi1 - phi2 + np.pi, 2 * np.pi) - np.pi


def delta_eta(eta1: Any, eta2: Any) -> Any:
    """Pseudorapidity difference eta1 - eta2.

    For (nearly) massless particles eta equals rapidity, so this difference
    is unchanged by the unknown longitudinal boost of each collision. That
    makes it, with delta phi, the natural measure of separation at a hadron
    collider.

    Parameters
    ----------
    eta1, eta2 : array-like or float
        Two arrays of the same jagged structure, or two scalars.
    """
    eta1, eta2 = _as_pair_arrays(eta1, eta2)
    return eta1 - eta2


def delta_r(p1: FourMomentum, p2: FourMomentum) -> ak.Array:
    """Angular separation in the eta-phi plane, dR = sqrt(d_eta^2 + d_phi^2).

    delta R is the standard distance between two objects at a hadron
    collider: approximately invariant under boosts along the beam, and
    roughly constant in size on the detector. It defines isolation cones
    (sum of activity within dR < 0.3 or 0.4 around a lepton), jet cone
    sizes (anti-kT R = 0.5 in CMS Run 1, 0.4 in Run 2), and matching between objects (e.g. a trigger
    object within dR < 0.1 of a muon). The phi difference is wrapped (see
    :func:`delta_phi`). The two muons from a Z at rest are back to back,
    with dR >= pi.
    """
    _check_pair(p1, p2)
    return np.sqrt(delta_eta(p1.eta, p2.eta) ** 2 + delta_phi(p1.phi, p2.phi) ** 2)


def pair_summary(p1: FourMomentum, p2: FourMomentum) -> ak.Array:
    """Return a record array of pair quantities with the same jagged structure as the inputs.

    Fields: ``mass``, ``pt``, ``eta``, ``phi``, ``rapidity`` (of the summed
    four-vector), and ``delta_r``, ``delta_phi`` (between the legs, phi of
    p1 minus phi of p2). Units are GeV and radians.
    """
    return ak.zip(
        {
            "mass": invariant_mass(p1, p2),
            "pt": pair_pt(p1, p2),
            "eta": pair_eta(p1, p2),
            "phi": pair_phi(p1, p2),
            "rapidity": pair_rapidity(p1, p2),
            "delta_r": delta_r(p1, p2),
            "delta_phi": delta_phi(p1.phi, p2.phi),
        }
    )
