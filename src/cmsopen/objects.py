"""Layer 2: physics objects (four-momenta, muons, electrons) from raw branches.

Physics context
---------------
A detector does not measure four-vectors directly. CMS reconstructs each
charged particle's track in a 3.8 T magnetic field and reports it in the
collider's natural coordinates:

``pt``
    Transverse momentum (GeV), the momentum component perpendicular to the
    beam. The colliding quarks and gluons carry unknown fractions of the
    proton momentum *along* the beam, so only the transverse plane is
    balanced in every collision; pt measures how hard a particle was
    scattered. It is also what the detector measures most directly: the
    curvature radius of a track in the solenoid is r [m] = pt [GeV] / (0.3 B [T]).
``eta``
    Pseudorapidity, eta = -ln tan(theta/2), where theta is the polar angle
    to the beam axis. eta = 0 is perpendicular to the beam and |eta| -> inf
    along it (|eta| = 2.4 is theta ~ 10 degrees). It is used instead of
    theta because, for particles much lighter than their momentum, eta
    equals the rapidity y, and *differences* in rapidity do not change under
    boosts along the beam. Since every collision has an unknown
    longitudinal boost, eta differences are the physically meaningful
    angles, and particle production is roughly uniform in eta.
``phi``
    Azimuthal angle around the beam (radians, -pi..pi).
``mass``
    Rest mass assigned to the particle hypothesis. The detector does not
    measure a muon's mass; reconstruction assigns the PDG value
    m_mu = 0.1057 GeV. A muon is a heavier copy of the electron (about 207
    electron masses), which is why it radiates little and penetrates the
    calorimeters to reach the muon chambers.

From these, the Cartesian four-momentum (E, px, py, pz) follows by
geometry: the transverse momentum is projected onto x and y with phi, the
longitudinal momentum is pz = pt sinh(eta) (because sinh(eta) =
cot(theta)), the total momentum is p = pt cosh(eta) (because cosh(eta) =
1/sin(theta)), and the energy follows from special relativity,
E^2 = p^2 + m^2 in natural units (c = 1). Natural units are why energy,
momentum and mass are all quoted in GeV.

Numerical precision
-------------------
The file stores kinematics as float32 (about 7 significant digits). Every
array here is converted to float64 first. Later layers compute invariant
masses as m^2 = (E1 + E2)^2 - |p1 + p2|^2, a difference of two large,
nearly equal numbers: for two 45 GeV muons, E^2 is ~8000 GeV^2 while m^2 for
a very soft pair may be < 1 GeV^2. In float32 such cancellations lose most
significant digits; float64 keeps ~16 digits, so the result stays accurate
to well below the detector resolution.

Shape
-----
All arrays are *jagged* awkward arrays: n_events lists, each with that
event's number of particles. Every operation is vectorized over events and
particles; there are no Python loops.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar, TypeVar

import awkward as ak
import numpy as np

from cmsopen.ingestion import ELECTRON_BRANCHES_DEFAULT, MUON_BRANCHES_DEFAULT, EventCollection

__all__ = ["Electron", "FourMomentum", "Muon", "ParticleCollection"]

_KINEMATICS = ("pt", "eta", "phi", "mass")

_P = TypeVar("_P", bound="ParticleCollection")


def _to_float64(values: Any) -> ak.Array:
    return ak.values_astype(ak.Array(values), np.float64)


def _counts(array: ak.Array) -> ak.Array | int:
    """Particles per event for a jagged array, or the length of a flat one."""
    return len(array) if array.ndim == 1 else ak.num(array, axis=1)


def _check_same_structure(arrays: Mapping[str, ak.Array]) -> None:
    """Raise ValueError unless all arrays have the same events and particle counts."""
    items = list(arrays.items())
    ref_name, ref = items[0]
    for name, arr in items[1:]:
        if arr.ndim != ref.ndim or len(arr) != len(ref):
            raise ValueError(
                f"{name!r} has {len(arr)} entries at depth {arr.ndim}, but {ref_name!r} has "
                f"{len(ref)} entries at depth {ref.ndim}; all fields must describe the same events"
            )
        if ref.ndim > 1 and not ak.all(ak.num(arr, axis=1) == ak.num(ref, axis=1)):
            bad = int(np.argmax(ak.to_numpy(ak.num(arr, axis=1) != ak.num(ref, axis=1))))
            raise ValueError(
                f"{name!r} and {ref_name!r} have different particle counts per event "
                f"(first mismatch at event {bad}: {ak.num(arr, axis=1)[bad]} vs {ak.num(ref, axis=1)[bad]})"
            )


class FourMomentum:
    """Jagged four-momenta of particles, stored as (pt, eta, phi, mass) in GeV.

    Holds one entry per particle in each event, as jagged float64 arrays.
    The detector-natural coordinates (pt, eta, phi, mass) are stored; the
    Cartesian components (px, py, pz, E) are computed on demand with
    explicit formulas, so the physics is visible in the code.

    Indexing works like the underlying awkward arrays and returns a new
    ``FourMomentum``: a jagged boolean mask selects particles while keeping
    one list per event, and a slice or an integer array selects events. A
    single integer selects one event and gives a flat (non-jagged)
    ``FourMomentum`` of that event's particles.

    Parameters
    ----------
    pt, eta, phi, mass : array-like
        Same-shaped jagged arrays (or flat arrays for a single event).
        Converted to float64.

    Raises
    ------
    ValueError
        If the four arrays do not have the same jagged structure.
    """

    def __init__(self, pt: Any, eta: Any, phi: Any, mass: Any) -> None:
        arrays = {name: _to_float64(v) for name, v in zip(_KINEMATICS, (pt, eta, phi, mass))}
        _check_same_structure(arrays)
        self.pt: ak.Array = arrays["pt"]
        """Transverse momentum (GeV): momentum perpendicular to the beam axis."""
        self.eta: ak.Array = arrays["eta"]
        """Pseudorapidity -ln tan(theta/2), the boost-friendly polar angle."""
        self.phi: ak.Array = arrays["phi"]
        """Azimuthal angle around the beam axis (radians)."""
        self.mass: ak.Array = arrays["mass"]
        """Rest mass hypothesis (GeV), e.g. 0.1057 GeV for a muon."""

    @classmethod
    def from_arrays(cls, pt: Any, eta: Any, phi: Any, mass: Any) -> FourMomentum:
        """Build from separate pt, eta, phi, mass arrays (GeV, radians)."""
        return cls(pt, eta, phi, mass)

    @classmethod
    def from_record(cls, record: ak.Array) -> FourMomentum:
        """Build from a record array with fields ``pt``, ``eta``, ``phi``, ``mass``.

        This is the shape returned by
        :meth:`cmsopen.ingestion.EventCollection.muons`.
        """
        missing = [f for f in _KINEMATICS if f not in ak.fields(record)]
        if missing:
            raise ValueError(f"Record array lacks kinematic field(s) {missing}; has {ak.fields(record)}")
        return cls(record.pt, record.eta, record.phi, record.mass)

    # -- Cartesian components ------------------------------------------------

    @property
    def px(self) -> ak.Array:
        """x component of momentum (GeV): pt projected on the x axis, pt cos(phi)."""
        return self.pt * np.cos(self.phi)

    @property
    def py(self) -> ak.Array:
        """y component of momentum (GeV): pt projected on the y axis, pt sin(phi)."""
        return self.pt * np.sin(self.phi)

    @property
    def pz(self) -> ak.Array:
        """Momentum along the beam (GeV), pt sinh(eta).

        From eta = -ln tan(theta/2) it follows that sinh(eta) = cot(theta),
        so pz = pt cot(theta) = p cos(theta).
        """
        return self.pt * np.sinh(self.eta)

    @property
    def p(self) -> ak.Array:
        """Magnitude of the three-momentum (GeV), pt cosh(eta).

        cosh(eta) = 1/sin(theta), so p = pt / sin(theta). A muon with
        pt = 40 GeV at eta = 2 carries p = 150 GeV: forward particles have
        large momenta even at modest pt.
        """
        return self.pt * np.cosh(self.eta)

    @property
    def energy(self) -> ak.Array:
        """Energy (GeV) from the mass-shell relation E = sqrt(p^2 + m^2).

        In natural units (c = 1) this is Einstein's E^2 = (pc)^2 + (mc^2)^2.
        For a muon with p >> 0.1057 GeV, E is almost equal to p; for a muon
        nearly at rest, E is almost equal to its mass. E >= m always.
        """
        return np.sqrt(self.p**2 + self.mass**2)

    def as_cartesian(self) -> tuple[ak.Array, ak.Array, ak.Array, ak.Array]:
        """Return the Cartesian four-momentum ``(px, py, pz, energy)`` in GeV.

        This is the form in which four-vectors add: the total four-momentum
        of a muon pair is the component-wise sum, from which layer 5 computes
        the invariant mass.
        """
        return self.px, self.py, self.pz, self.energy

    # -- container behavior --------------------------------------------------

    @property
    def num(self) -> ak.Array | int:
        """Number of particles in each event (an int for a single event)."""
        return _counts(self.pt)

    def __len__(self) -> int:
        return len(self.pt)

    def __getitem__(self, where: Any) -> FourMomentum:
        return FourMomentum(self.pt[where], self.eta[where], self.phi[where], self.mass[where])

    def __repr__(self) -> str:
        if self.pt.ndim == 1:
            return f"FourMomentum(n_particles={len(self)})"
        return f"FourMomentum(n_events={len(self)}, n_particles={int(ak.sum(self.num))})"


class ParticleCollection:
    """Base class: one particle species across a set of events.

    Holds the jagged four-momenta (:class:`FourMomentum`), the jagged
    electric charge, and any extra per-particle fields (isolation, ID
    flags, impact parameters) as a jagged record array. All share the same
    jagged structure: event ``i`` has the same number of entries in every
    field.

    Charge is in units of the elementary charge and is +1 or -1 for real
    muons and electrons. It is stored as read and is not enforced, so that
    unexpected values in the data stay visible.

    Indexing (masks, slices, event indices) returns the same subclass with
    every field indexed consistently.

    Parameters
    ----------
    p4 : FourMomentum
        Kinematics of the particles.
    charge : array-like
        Jagged integer charges.
    extras : ak.Array or mapping of str to array, optional
        Extra per-particle fields, keyed by name without the collection
        prefix (e.g. ``"tightId"``).

    Raises
    ------
    ValueError
        If any field's per-event particle counts differ from ``p4``'s.
    """

    prefix: ClassVar[str] = ""
    default_fields: ClassVar[tuple[str, ...]] = ()

    def __init__(self, p4: FourMomentum, charge: Any, extras: ak.Array | Mapping[str, Any] | None = None) -> None:
        self.p4: FourMomentum = p4
        """Four-momenta of the particles (GeV)."""
        self.charge: ak.Array = ak.Array(charge)
        """Electric charge in units of e: +1 or -1 for real leptons."""
        if extras is None:
            extras = {}
        elif isinstance(extras, ak.Array):
            extras = {f: extras[f] for f in ak.fields(extras)}
        self._extras: dict[str, ak.Array] = {k: ak.Array(v) for k, v in extras.items()}
        _check_same_structure({"pt": p4.pt, "charge": self.charge, **self._extras})

    @classmethod
    def from_record(cls: type[_P], record: ak.Array) -> _P:
        """Build from a jagged record array with pt, eta, phi, mass, charge and extras.

        Accepts the output of :meth:`EventCollection.collection` or of
        :meth:`to_awkward`.
        """
        fields = ak.fields(record)
        if "charge" not in fields:
            raise ValueError(f"Record array lacks field 'charge'; has {fields}")
        extras = {f: record[f] for f in fields if f not in (*_KINEMATICS, "charge")}
        return cls(FourMomentum.from_record(record), record.charge, extras)

    @classmethod
    def from_events(
        cls: type[_P],
        events: EventCollection,
        entry_start: int | None = None,
        entry_stop: int | None = None,
        fields: tuple[str, ...] | None = None,
    ) -> _P:
        """Read this collection from a file opened with :func:`cmsopen.open_events`.

        Parameters
        ----------
        events : EventCollection
            The opened file.
        entry_start, entry_stop : int, optional
            Half-open event range to read.
        fields : tuple of str, optional
            Branch fields to read (without prefix); defaults to the
            class's ``default_fields``. Must include pt, eta, phi, mass and
            charge.
        """
        record = events.collection(cls.prefix, fields or cls.default_fields, entry_start, entry_stop)
        return cls.from_record(record)

    @property
    def extras(self) -> ak.Array | None:
        """Extra per-particle fields as one jagged record array (None if there are none)."""
        return ak.zip(self._extras) if self._extras else None

    @property
    def num(self) -> ak.Array | int:
        """Number of particles in each event (an int for a single event)."""
        return self.p4.num

    def to_awkward(self) -> ak.Array:
        """Return one jagged record array with pt, eta, phi, mass, charge and all extras.

        Kinematics are float64. This flat record form is what later layers
        (selection, pairing) operate on with awkward functions such as
        ``ak.combinations``.
        """
        fields = {name: getattr(self.p4, name) for name in _KINEMATICS}
        return ak.zip({**fields, "charge": self.charge, **self._extras})

    def _extra(self, name: str) -> ak.Array:
        try:
            return self._extras[name]
        except KeyError:
            raise AttributeError(
                f"{type(self).__name__} has no field {name!r}; it was not read. "
                f"Available: {sorted(self._extras)}"
            ) from None

    def __len__(self) -> int:
        return len(self.p4)

    def __getitem__(self: _P, where: Any) -> _P:
        return type(self)(self.p4[where], self.charge[where], {k: v[where] for k, v in self._extras.items()})

    def __repr__(self) -> str:
        fields = ", ".join(["pt", "eta", "phi", "mass", "charge", *self._extras])
        if self.p4.pt.ndim == 1:
            return f"{type(self).__name__}(n_particles={len(self)}, fields=[{fields}])"
        return f"{type(self).__name__}(n_events={len(self)}, n_particles={int(ak.sum(self.num))}, fields=[{fields}])"


class Muon(ParticleCollection):
    """All muons in a set of events: a whole collection, not a single muon.

    ``Muon`` holds every reconstructed muon in every event read, as jagged
    arrays (``muons.p4.pt[i]`` is the list of muon pts in event ``i``).
    Indexing with a jagged mask, e.g. ``muons[muons.tightId]``, gives
    another ``Muon`` collection with only the selected muons.

    The muon is a lepton about 207 times heavier than the electron
    (m = 0.1057 GeV). It has a lifetime of 2.2 microseconds, long enough to
    cross the whole detector at LHC energies, and it barely radiates or
    interacts in the calorimeters. That is why the outermost CMS layers are
    muon chambers and why Z -> mu+ mu- gives the cleanest Z boson signal.

    The raw collection is unselected: it includes soft muons from hadron
    decays and badly measured candidates. Layer 3 applies cuts.
    """

    prefix: ClassVar[str] = "Muon"
    default_fields: ClassVar[tuple[str, ...]] = MUON_BRANCHES_DEFAULT

    @property
    def iso(self) -> ak.Array:
        """Relative isolation in a dR = 0.4 cone (``Muon_pfRelIso04_all``).

        The summed pt of other particle-flow candidates within
        dR = sqrt(d_eta^2 + d_phi^2) < 0.4, divided by the muon pt. Muons
        from W/Z decays are isolated (values near 0); muons produced in
        b- and c-hadron decays sit inside jets and have large values. A cut
        such as iso < 0.15 is the standard way to reject them.
        """
        return self._extra("pfRelIso04_all")

    @property
    def looseId(self) -> ak.Array:
        """Loose muon ID: a particle-flow muon that is global or tracker. Very efficient, less pure."""
        return self._extra("looseId")

    @property
    def mediumId(self) -> ak.Array:
        """Medium muon ID: loose plus track-quality requirements, designed for prompt muons."""
        return self._extra("mediumId")

    @property
    def tightId(self) -> ak.Array:
        """Tight muon ID: a well-measured global muon with hits in several chambers and a vertex-compatible track.

        The standard choice for Z and W analyses: it suppresses hadrons
        punching through the calorimeter, decays in flight and cosmic rays.
        """
        return self._extra("tightId")

    @property
    def softId(self) -> ak.Array:
        """Soft muon ID: tuned for low-pt muons (e.g. from J/psi or B decays), not for Z muons."""
        return self._extra("softId")

    @property
    def isGlobal(self) -> ak.Array:
        """True if the muon was fitted from inner-tracker and muon-chamber hits together."""
        return self._extra("isGlobal")

    @property
    def isTracker(self) -> ak.Array:
        """True if an inner-tracker track was matched to at least one muon-chamber segment."""
        return self._extra("isTracker")

    @property
    def isPFcand(self) -> ak.Array:
        """True if the particle-flow algorithm identified this candidate as a muon."""
        return self._extra("isPFcand")

    @property
    def dxy(self) -> ak.Array:
        """Transverse impact parameter (cm): closest approach to the primary vertex in the x-y plane.

        Prompt muons from a Z decay point back to the collision (|dxy| of a
        few tens of microns); cosmic rays and long-lived decays do not.
        """
        return self._extra("dxy")

    @property
    def dz(self) -> ak.Array:
        """Longitudinal impact parameter (cm): distance from the primary vertex along the beam."""
        return self._extra("dz")


class Electron(ParticleCollection):
    """All electrons in a set of events: a whole collection, not a single electron.

    ``Electron`` holds every reconstructed electron in every event read,
    as jagged arrays, exactly like :class:`Muon`.

    Electrons are measured by combining a tracker track with an energy
    deposit (cluster) in the electromagnetic calorimeter, where they shower
    completely. Their mass (0.511 MeV) is negligible at these energies.

    Run 1 difference: ID is the integer ``cut_based`` working point, not
    separate boolean flags as in modern NanoAOD.
    """

    prefix: ClassVar[str] = "Electron"
    default_fields: ClassVar[tuple[str, ...]] = ELECTRON_BRANCHES_DEFAULT

    @property
    def cut_based(self) -> ak.Array:
        """Run 1 cut-based ID working point (``Electron_cutBased``), an integer.

        Following the NanoAOD convention, 0 = fails all, 1 = veto,
        2 = loose, 3 = medium, 4 = tight (the 2012 file holds values 0-4). Each
        level tightens cuts on shower shape, track-cluster matching, the
        hadronic-to-electromagnetic energy ratio and conversion rejection,
        trading efficiency for purity. Select with e.g. ``cut_based >= 4``.
        """
        return self._extra("cutBased")

    @property
    def iso(self) -> ak.Array:
        """Relative isolation in a dR = 0.3 cone (``Electron_pfRelIso03_all``).

        Same idea as the muon isolation: prompt electrons from W/Z decays
        are isolated, electrons inside jets are not.
        """
        return self._extra("pfRelIso03_all")

    @property
    def isEB(self) -> ak.Array:
        """True if the electron's calorimeter cluster is in the ECAL barrel (|eta| < ~1.48)."""
        return self._extra("isEB")

    @property
    def isEE(self) -> ak.Array:
        """True if the cluster is in an ECAL endcap, where resolution and ID cuts differ."""
        return self._extra("isEE")

    @property
    def convVeto(self) -> ak.Array:
        """True if the electron is NOT consistent with a photon conversion (gamma -> e+ e- in the tracker material)."""
        return self._extra("convVeto")

    @property
    def dxy(self) -> ak.Array:
        """Transverse impact parameter (cm) with respect to the primary vertex."""
        return self._extra("dxy")

    @property
    def dz(self) -> ak.Array:
        """Longitudinal impact parameter (cm) with respect to the primary vertex."""
        return self._extra("dz")
