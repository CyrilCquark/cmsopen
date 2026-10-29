"""Layer 3: object and event selection, with a cutflow.

Physics context
---------------
A reconstructed event holds many lepton candidates, and most of them are
not what an analysis is looking for. In the 2012 DoubleMuParked file there
are about 4.5 muon candidates per event. Most are soft muons from pion,
kaon and heavy-flavour (b, c) hadron decays inside jets. Some are hadrons
that punched through the calorimeter, cosmic rays crossing the detector,
or badly measured tracks: the raw collection reaches |eta| ~ 12 and
pt ~ 120 TeV, values no real muon in this detector can have. The muons
from Z -> mu+ mu- are a small minority. They are energetic (about 45 GeV
each, half the Z mass), central, well reconstructed, isolated from other
activity, and come from the primary collision vertex.

*Selection* keeps the candidates with those properties. Each cut targets one
background mechanism:

* transverse momentum (``min_pt``): soft muons from decays and noise;
* pseudorapidity (``max_eta``): candidates outside the instrumented region;
* identification (``quality_id``, ``global_muon``): fakes and poorly
  measured tracks;
* isolation (``max_rel_iso``): muons produced inside jets;
* impact parameters (``max_abs_dxy``, ``max_abs_dz``): cosmic rays, decays in
  flight and muons from other collisions in the same bunch crossing (pileup).

Two levels of cut
-----------------
*Particle-level* cuts decide, muon by muon, whether a candidate is kept.
They return a jagged boolean mask with the same structure as the
collection, remove particles and never remove events: an event can end up
with zero muons. Because each muon is judged on its own, particle-level
cuts commute: their order changes the cutflow bookkeeping but never the
surviving muons.

*Event-level* cuts decide whether a whole collision is kept: "at least two
selected muons" (:meth:`Selection.require`) or "the dimuon trigger fired"
(:meth:`Selection.require_trigger`).

Thresholds and inequalities
---------------------------
Every threshold cut here is *strict*. A value exactly at the threshold
FAILS: ``pt > 20`` rejects pt = 20, ``|eta| < 2.4`` rejects |eta| = 2.4,
``iso < 0.12`` rejects iso = 0.12, and likewise for ``|dxy|`` and ``|dz|``.
NaN values fail every cut, because any comparison with NaN is False. The
file stores float32; the comparison is done in float64 on the exact stored
value, so a stored ``eta = float32(2.4)`` (which is 2.4000000954) fails
``|eta| < 2.4``.

The cutflow
-----------
A :class:`CutFlow` lists how many particles and events survive each step.
It is the first thing to check in any analysis. It shows which cut does the
work, and it exposes mistakes such as a cut that removes everything or
nothing. The efficiency of each step is also an input to cross-section
measurements, which must correct for signal lost to the cuts. Comparing
cutflows between data and simulation, or between run periods, is a
standard systematic check.

Everything is vectorized with awkward and numpy; there are no Python loops
over events or particles.
"""

from __future__ import annotations

import math
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from numbers import Real
from types import MappingProxyType
from typing import Any, cast

import awkward as ak
import numpy as np

from cmsopen.ingestion import ELECTRON_BRANCHES_DEFAULT, MUON_BRANCHES_DEFAULT, EventCollection
from cmsopen.objects import Electron, Muon, ParticleCollection

__all__ = [
    "MUON_ID_WORKING_POINTS",
    "ZMUMU_MUON_CUTS",
    "CutFlow",
    "CutStep",
    "MissingFieldError",
    "Selection",
    "global_muon",
    "max_abs_dxy",
    "max_abs_dz",
    "max_eta",
    "max_rel_iso",
    "min_pt",
    "quality_id",
    "select_electrons",
    "select_muons",
]

MUON_ID_WORKING_POINTS: Mapping[str, str] = MappingProxyType(
    {"loose": "looseId", "medium": "mediumId", "tight": "tightId", "soft": "softId"}
)
"""Muon ID working-point names accepted by :func:`quality_id`, mapped to their ``Muon_`` fields."""

ZMUMU_MUON_CUTS: Mapping[str, Any] = MappingProxyType(
    {"min_pt": 20.0, "max_eta": 2.4, "quality_id": "tight", "max_rel_iso": 0.12}
)
"""Typical particle-level muon cuts for Z -> mu+ mu-, in the order they are applied.

Use as ``events.muons(**ZMUMU_MUON_CUTS)``. These are a typical choice for
a 2012 dimuon analysis, not a verified official CMS recipe. Each number has
a physical reason:

``min_pt = 20`` GeV
    The 2012 dimuon triggers (:data:`~cmsopen.ingestion.DIMUON_TRIGGERS_2012`)
    need one muon above 17 GeV and one above 8 GeV. The trigger turns on
    gradually around these thresholds, so offline cuts sit a little above
    them, where its efficiency is flat and well understood. Z muons carry
    about M_Z / 2 ~ 45 GeV each, so most survive 20 GeV. Soft muons from
    hadron decays mostly do not.
``max_eta = 2.4``
    The CMS muon chambers and the tracker region used for muon tracks
    cover |eta| < 2.4. Candidates beyond that are not measurable muons.
``quality_id = "tight"``
    The tight ID is the purest standard working point: a global muon with
    a good fit, hits in several muon stations and pixel layers, and a
    track compatible with the primary vertex. It gives up a few percent of
    real muons for a much lower fake rate.
``max_rel_iso = 0.12``
    Relative isolation in a dR = 0.4 cone below 12%: little other activity
    around the muon. Z muons are isolated; muons from b and c decays inside
    jets are not. Typical values used for prompt muons lie between 0.10
    and 0.15.
"""


class MissingFieldError(KeyError):
    """Raised when a cut needs a particle field that was not read from the file.

    NanoAOD is read column by column, so a collection only has the fields
    that were requested. The message names the missing field and how to
    read it.
    """

    def __str__(self) -> str:
        return str(self.args[0]) if self.args else ""


# -- helpers --------------------------------------------------------------------

_KINEMATIC_FIELDS = ("pt", "eta", "phi", "mass")


def _check_collection(particles: Any, cut: str, allowed: tuple[type, ...] = (ParticleCollection,)) -> None:
    if not isinstance(particles, allowed):
        names = " or ".join(t.__name__ for t in allowed)
        raise TypeError(f"{cut}() needs a {names} collection, got {type(particles).__name__}")


def _field(particles: ParticleCollection, name: str, cut: str) -> ak.Array:
    """Return a per-particle field, or raise MissingFieldError naming it."""
    if name in _KINEMATIC_FIELDS:
        return getattr(particles.p4, name)
    if name == "charge":
        return particles.charge
    values = particles._extras.get(name)
    if values is None:
        branch = f"{particles.prefix}_{name}"
        raise MissingFieldError(
            f"{cut}() needs the field {name!r} (branch {branch}), which was not read. "
            f"Fields read: {['pt', 'eta', 'phi', 'mass', 'charge', *particles._extras]}. "
            f"Read it by including {name!r} in fields=..."
        )
    return values


def _threshold(value: Any, cut: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (Real, np.number)):
        raise TypeError(f"{cut}() threshold must be a real number, got {value!r}")
    value = float(value)
    if math.isnan(value):
        raise ValueError(f"{cut}() threshold is NaN")
    return value


# -- particle-level cut functions -------------------------------------------------


def min_pt(particles: ParticleCollection, value: float) -> ak.Array:
    """Keep particles with transverse momentum pt > ``value`` (GeV). Strict: pt = value fails.

    pt is the momentum perpendicular to the beam. Hard-scattering processes
    such as Z and W production give leptons with tens of GeV of pt, while
    most other muon candidates are soft: muons from pion and kaon decays in
    flight, from b and c hadrons, and mis-reconstructed tracks. Their pt
    spectrum falls steeply. A pt threshold therefore removes most
    background at little cost to the signal.

    A second reason is the trigger. Events were only recorded if a trigger
    fired, and a trigger fires only above its own pt threshold (17 and 8 GeV
    for the 2012 dimuon paths). Just above threshold its efficiency changes
    quickly and is hard to model; a few GeV higher it is flat. Offline pt
    cuts are placed on that plateau.

    Parameters
    ----------
    particles : Muon or Electron
        The collection to cut on (needs ``pt``, always present).
    value : float
        Threshold in GeV.

    Returns
    -------
    ak.Array
        Jagged boolean mask, True where pt > value; same structure as
        ``particles``.
    """
    _check_collection(particles, "min_pt")
    return _field(particles, "pt", "min_pt") > _threshold(value, "min_pt")


def max_eta(particles: ParticleCollection, value: float) -> ak.Array:
    """Keep particles with |eta| < ``value``. Strict: |eta| = value fails.

    Pseudorapidity eta = -ln tan(theta/2) measures the angle from the beam
    axis; |eta| = 2.4 is about 10 degrees. The CMS muon chambers and the
    part of the silicon tracker used for muon tracks cover |eta| < 2.4, so a
    muon beyond that cannot be measured well, if at all. The absolute value
    matters: the detector is symmetric, and eta = -2.0 (one endcap) is as
    good as eta = +2.0 (the other).

    The raw 2012 collection contains candidates out to |eta| ~ 12, far
    outside any detector. They are reconstruction artefacts, not muons, and
    this cut removes them.

    Parameters
    ----------
    particles : Muon or Electron
        The collection to cut on (needs ``eta``, always present).
    value : float
        Maximum |eta| (dimensionless).

    Returns
    -------
    ak.Array
        Jagged boolean mask, True where |eta| < value.
    """
    _check_collection(particles, "max_eta")
    return np.abs(_field(particles, "eta", "max_eta")) < _threshold(value, "max_eta")


def max_rel_iso(particles: ParticleCollection, value: float, cone: float | None = None) -> ak.Array:
    """Keep isolated particles: relative isolation < ``value``. Strict: iso = value fails.

    Relative isolation is

        iso = (scalar sum of pT of the other particles within dR < cone) / pT,

    where dR = sqrt(d_eta^2 + d_phi^2) is the distance from the lepton and the
    sum runs over particle-flow candidates (charged hadrons, neutral hadrons
    and photons). Smaller means more isolated: iso = 0 means nothing else
    nearby, iso = 1 means as much pT around the lepton as in the lepton.

    Leptons from W and Z decays are produced alone and are isolated. Muons
    from b and c hadron decays sit inside the jet of their parent quark and
    are surrounded by its other fragments. Isolation is the most powerful
    single cut separating them. Being a ratio, it also tightens with pt: a
    hard muon tolerates more absolute activity than a soft one.

    Parameters
    ----------
    particles : Muon or Electron
        The collection to cut on.
    value : float
        Maximum relative isolation (dimensionless).
    cone : {0.4, 0.3}, optional
        Cone radius dR. Muons: 0.4 (default, ``pfRelIso04_all``) or 0.3
        (``pfRelIso03_all``). Electrons: only 0.3 is stored in this
        file, which is the default.

    Returns
    -------
    ak.Array
        Jagged boolean mask, True where iso < value.

    Raises
    ------
    ValueError
        If ``cone`` is not available for this collection.
    MissingFieldError
        If the isolation field was not read.
    """
    _check_collection(particles, "max_rel_iso", (Muon, Electron))
    cones = {0.4: "pfRelIso04_all", 0.3: "pfRelIso03_all"} if isinstance(particles, Muon) else {0.3: "pfRelIso03_all"}
    if cone is None:
        cone = max(cones)
    if cone not in cones:
        raise ValueError(
            f"max_rel_iso(): cone {cone!r} not available for {type(particles).__name__}; use one of {sorted(cones)}"
        )
    return _field(particles, cones[cone], "max_rel_iso") < _threshold(value, "max_rel_iso")


def quality_id(particles: Muon, name: str) -> ak.Array:
    """Keep muons passing the named CMS muon identification working point.

    Reconstruction is generous on purpose and produces many muon candidates;
    identification decides which are real, well-measured muons. CMS defines
    nested working points that trade efficiency (the fraction of real
    muons kept) against purity (the fraction of kept candidates that are
    real prompt muons):

    ``"loose"`` (``Muon_looseId``)
        A particle-flow muon that is a global or tracker muon. Keeps nearly
        every real muon, including those from hadron decays, and lets
        through some punch-through hadrons.
    ``"medium"`` (``Muon_mediumId``)
        Loose plus track-quality requirements (valid tracker hits, segment
        compatibility). Built for prompt muons.
    ``"tight"`` (``Muon_tightId``)
        A global muon with a good global fit, hits in at least two muon
        stations, pixel and tracker-layer hits, and a track close to the
        primary vertex. The usual choice for W and Z: it suppresses
        punch-through, decays in flight and cosmic rays at the cost of a
        few percent of real muons.
    ``"soft"`` (``Muon_softId``)
        Tuned for low-pt muons from J/psi and B decays. Not meant for Z muons.

    The flags were computed by CMS reconstruction and are read as stored.

    Parameters
    ----------
    particles : Muon
        Muon collection with the needed ID field read.
    name : {"loose", "medium", "tight", "soft"}
        Working point.

    Returns
    -------
    ak.Array
        Jagged boolean mask, True where the muon passes.

    Raises
    ------
    ValueError
        If ``name`` is not a known working point; the message lists them.
    """
    _check_collection(particles, "quality_id", (Muon,))
    if name not in MUON_ID_WORKING_POINTS:
        raise ValueError(f"quality_id(): unknown muon ID {name!r}; valid names: {', '.join(MUON_ID_WORKING_POINTS)}")
    return _field(particles, MUON_ID_WORKING_POINTS[name], "quality_id") == True  # noqa: E712 (elementwise)


def max_abs_dxy(particles: Muon, value: float) -> ak.Array:
    """Keep muons with transverse impact parameter |dxy| < ``value`` (cm). Strict: |dxy| = value fails.

    dxy is the distance of closest approach of the track to the primary
    vertex, measured in the plane transverse to the beam. Muons from a
    Z decay come from the collision point, and the beam spot is only
    ~20 microns wide transversely, so their |dxy| is tens of microns. Large
    values indicate a muon that did not come from the collision: a cosmic
    ray crossing the detector, or a muon from a pion, kaon or b hadron that
    flew some distance before decaying (a decay in flight). Typical cuts
    are |dxy| < 0.2 cm or tighter.

    Only muons support this cut here (electron selection beyond pt, eta and
    isolation is left for a later layer).

    Parameters
    ----------
    particles : Muon
        Needs the ``dxy`` field.
    value : float
        Maximum |dxy| in cm.

    Returns
    -------
    ak.Array
        Jagged boolean mask, True where |dxy| < value.
    """
    _check_collection(particles, "max_abs_dxy", (Muon,))
    return np.abs(_field(particles, "dxy", "max_abs_dxy")) < _threshold(value, "max_abs_dxy")


def max_abs_dz(particles: Muon, value: float) -> ak.Array:
    """Keep muons with longitudinal impact parameter |dz| < ``value`` (cm). Strict: |dz| = value fails.

    dz is the distance from the primary vertex along the beam axis. In 2012
    each bunch crossing contained about 20 proton-proton collisions
    (pileup), spread over several cm along the beam. A muon from the
    collision of interest has |dz| of a fraction of a mm. A muon with large
    |dz| comes from another collision, a cosmic ray, or a decay in flight.
    Typical cuts are |dz| < 0.5 cm.

    Only muons support this cut here.

    Parameters
    ----------
    particles : Muon
        Needs the ``dz`` field.
    value : float
        Maximum |dz| in cm.

    Returns
    -------
    ak.Array
        Jagged boolean mask, True where |dz| < value.
    """
    _check_collection(particles, "max_abs_dz", (Muon,))
    return np.abs(_field(particles, "dz", "max_abs_dz")) < _threshold(value, "max_abs_dz")


def global_muon(particles: Muon) -> ak.Array:
    """Keep muons that are both global and tracker muons (``isGlobal & isTracker``).

    CMS reconstructs muons in two complementary ways. A *global* muon starts
    from a track in the muon chambers and refits it together with a
    matching inner-tracker track, which gives the best momentum at high pt.
    A *tracker* muon starts from an inner-tracker track and finds at least
    one matching segment in the muon chambers, which is more efficient at
    low pt. Requiring both rejects candidates that only one algorithm
    found, which are more often hadrons or mismatched tracks. It is a
    building block of the tight ID.

    Parameters
    ----------
    particles : Muon
        Needs the ``isGlobal`` and ``isTracker`` fields.

    Returns
    -------
    ak.Array
        Jagged boolean mask, True where both flags are set.
    """
    _check_collection(particles, "global_muon", (Muon,))
    return (_field(particles, "isGlobal", "global_muon") == True) & (  # noqa: E712
        _field(particles, "isTracker", "global_muon") == True  # noqa: E712
    )


_PARTICLE_CUTS = {
    "min_pt": min_pt,
    "max_eta": max_eta,
    "max_rel_iso": max_rel_iso,
    "quality_id": quality_id,
    "max_abs_dxy": max_abs_dxy,
    "max_abs_dz": max_abs_dz,
    "global_muon": global_muon,
}
_ELECTRON_CUTS = ("min_pt", "max_eta", "max_rel_iso")


# -- cutflow ---------------------------------------------------------------------


@dataclass(frozen=True)
class CutStep:
    """One step of a cutflow: the cut applied and what survived it.

    Attributes
    ----------
    name : str
        Cut name, e.g. ``"min_pt"``, ``"require"`` or ``"all events"`` for
        the starting row.
    params : mapping
        Cut parameters, e.g. ``{"value": 20.0}``.
    level : {"start", "particle", "event"}
        Whether the step removes particles or whole events.
    n_particles : int
        Particles remaining after the step.
    n_events_with_particles : int
        Remaining events that still contain at least one particle.
    n_events : int
        Events remaining (only event-level cuts change this).
    """

    name: str
    params: Mapping[str, Any] = field(default_factory=dict)
    level: str = "particle"
    n_particles: int = 0
    n_events_with_particles: int = 0
    n_events: int = 0

    @property
    def label(self) -> str:
        """Human-readable cut description, e.g. ``min_pt(20)`` or ``require(>= 2)``."""
        if self.level == "start":
            return self.name
        if self.name == "require":
            return f"require({'==' if self.params['exactly'] else '>='} {self.params['n']})"
        if self.name == "require_trigger":
            return f"trigger({' OR '.join(self.params['paths'])})"
        args = [f"{v:g}" if isinstance(v, float) else str(v) for k, v in self.params.items() if k != "cone"]
        if "cone" in self.params:
            args.append(f"cone={self.params['cone']:g}")
        return f"{self.name}({', '.join(args)})"


_COUNTS = ("n_particles", "n_events_with_particles", "n_events")


def _eff(num: int, den: int) -> float:
    return num / den if den else float("nan")


class CutFlow:
    """How many particles and events survive each selection step.

    Row 0 is ``"all events"`` (nothing cut); each later row is one cut, in
    the order applied. For every row three counts are kept:

    * ``particles``: particles remaining;
    * ``events >= 1``: events that still contain at least one particle;
    * ``events``: events remaining after event-level cuts.

    For each count there are two efficiencies: relative to the previous row
    (what this cut alone removed) and relative to row 0 (the cumulative
    efficiency of the selection so far). A particle-level cut leaves
    ``events`` unchanged, so its effect shows in the first two counts.

    Why it matters: the cutflow is the audit trail of an analysis. It shows
    which cuts dominate, catches cuts that remove all or nothing, and gives
    the selection efficiencies needed to turn an event count into a cross
    section. Cutflows are compared between data and simulation, or between
    data-taking periods, to spot problems.

    Iterating gives the :class:`CutStep` rows.
    """

    def __init__(self, steps: Sequence[CutStep]) -> None:
        if not steps:
            raise ValueError("a CutFlow needs at least the starting row")
        self.steps: tuple[CutStep, ...] = tuple(steps)

    @classmethod
    def combine(cls, cutflows: Sequence[CutFlow]) -> CutFlow:
        """Add cutflows of disjoint event samples (chunks of a file, or several files) row by row.

        Events are independent collisions, so every count in a cutflow, the
        particles, the events with at least one particle and the events, is
        a sum over events. The cutflow of a sample split into pieces is
        therefore exactly the row-by-row sum of the pieces' cutflows, provided
        every piece went through the same cuts in the same order.

        Raises
        ------
        ValueError
            If no cutflow is given or their steps (name, parameters, level)
            differ.
        """
        cutflows = list(cutflows)
        if not cutflows:
            raise ValueError("CutFlow.combine() needs at least one cutflow")
        first = cutflows[0]
        for other in cutflows[1:]:
            mismatch = len(other) != len(first) or any(
                (a.name, dict(a.params), a.level) != (b.name, dict(b.params), b.level)
                for a, b in zip(first, other, strict=False)
            )
            if mismatch:
                raise ValueError(
                    "cannot combine cutflows with different cuts: "
                    f"{[s.label for s in first]} vs {[s.label for s in other]}"
                )
        steps = [
            CutStep(
                step.name,
                dict(step.params),
                step.level,
                sum(cf.steps[i].n_particles for cf in cutflows),
                sum(cf.steps[i].n_events_with_particles for cf in cutflows),
                sum(cf.steps[i].n_events for cf in cutflows),
            )
            for i, step in enumerate(first.steps)
        ]
        return cls(steps)

    def __len__(self) -> int:
        return len(self.steps)

    def __iter__(self) -> Iterator[CutStep]:
        return iter(self.steps)

    def __getitem__(self, i: int) -> CutStep:
        return self.steps[i]

    def to_records(self) -> list[dict[str, Any]]:
        """Return one dict per row, ready for plotting or ``pandas.DataFrame``.

        Keys: ``step``, ``cut`` (label), ``name``, ``params``, ``level``,
        ``n_particles``, ``n_events_with_particles``, ``n_events``, and for
        each count ``<count>_eff_prev`` and ``<count>_eff_start`` (fractions
        in [0, 1], NaN when the denominator is 0).
        """
        first = self.steps[0]
        records = []
        for i, step in enumerate(self.steps):
            prev = self.steps[i - 1] if i else step
            row: dict[str, Any] = {
                "step": i,
                "cut": step.label,
                "name": step.name,
                "params": dict(step.params),
                "level": step.level,
            }
            for c in _COUNTS:
                row[c] = getattr(step, c)
            for c in _COUNTS:
                row[f"{c}_eff_prev"] = _eff(getattr(step, c), getattr(prev, c))
                row[f"{c}_eff_start"] = _eff(getattr(step, c), getattr(first, c))
            records.append(row)
        return records

    def to_dict(self) -> dict[str, list[Any]]:
        """Return the cutflow column by column: ``{column: [value per row]}``.

        Same columns as :meth:`to_records`.
        """
        records = self.to_records()
        return {key: [r[key] for r in records] for key in records[0]}

    def __str__(self) -> str:
        def pct(x: float) -> str:
            return "-" if math.isnan(x) else f"{100 * x:.1f}%"

        records = self.to_records()
        groups = (("particles", "n_particles"), ("events >= 1", "n_events_with_particles"), ("events", "n_events"))
        cut_w = max(len("cut"), *(len(r["cut"]) for r in records))
        num_w = {key: max(len(title), *(len(f"{r[key]:,}") for r in records)) for title, key in groups}
        top = f"{'#':>3}  {'cut':<{cut_w}}" + "".join(
            f"  {title:>{num_w[key]}} {'prev':>7} {'start':>7}" for title, key in groups
        )
        rule = "-" * len(top)
        lines = [top, rule]
        for r in records:
            line = f"{r['step']:>3}  {r['cut']:<{cut_w}}"
            for _, key in groups:
                line += f"  {r[key]:>{num_w[key]},} {pct(r[key + '_eff_prev']):>7} {pct(r[key + '_eff_start']):>7}"
            lines.append(line)
        lines.append(rule)
        lines.append("prev = efficiency relative to the previous row; start = relative to row 0")
        return "\n".join(lines)

    def __repr__(self) -> str:
        last = self.steps[-1]
        return f"CutFlow({len(self.steps)} rows, final: {last.n_events:,} events, {last.n_particles:,} particles)"


# -- the Selection object -----------------------------------------------------------


def _counts(particles: ParticleCollection) -> tuple[int, int, int]:
    num = ak.num(particles.p4.pt, axis=1)
    return int(ak.sum(num)), int(ak.sum(num > 0)), len(particles)


class Selection:
    """A chainable, immutable selection of particles and events, with its history.

    A ``Selection`` holds three things:

    * the surviving particles, as a :class:`~cmsopen.objects.Muon` or
      :class:`~cmsopen.objects.Electron` collection (:attr:`particles`);
    * :attr:`event_index`, the row in the original file of every
      surviving event, so results can be matched back to other branches
      (for example ``events.arrays("run")[sel.event_index]``);
    * the history of cuts, from which :meth:`cutflow` is built.

    Every cut returns a *new* Selection and leaves the original unchanged,
    so intermediate stages can be kept and compared::

        base  = events.muons(min_pt=20, max_eta=2.4)
        tight = base.quality_id("tight").max_rel_iso(0.12)
        pairs = tight.require(2)
        print(pairs.cutflow())

    Particle-level cuts (:meth:`min_pt`, :meth:`max_eta`,
    :meth:`max_rel_iso`, :meth:`quality_id`, :meth:`max_abs_dxy`,
    :meth:`max_abs_dz`, :meth:`global_muon`) remove particles, not events;
    an event may be left with no particles. They commute: any order gives
    the same surviving particles. Event-level cuts (:meth:`require`,
    :meth:`require_trigger`) remove whole events.

    Usually built with ``events.muons(...)``, ``events.electrons(...)``,
    :func:`select_muons` or :func:`select_electrons`.

    Parameters
    ----------
    particles : Muon or Electron
        The starting collection, one entry per event.
    events : EventCollection, optional
        The open file the particles were read from. Needed for
        :meth:`require_trigger`, which reads trigger branches on demand,
        so the file must still be open when that is called.
    entry_start : int, optional
        File row of the first event in ``particles`` (default 0).
    """

    def __init__(
        self, particles: ParticleCollection, events: EventCollection | None = None, entry_start: int = 0
    ) -> None:
        _check_collection(particles, "Selection")
        if particles.p4.pt.ndim != 2:
            raise ValueError("Selection needs a jagged collection with one list of particles per event")
        n_p, n_ne, n_e = _counts(particles)
        self._particles = particles
        self._events = events
        self._entry_start = int(entry_start)
        self._n_start = n_e
        self._event_index = np.arange(self._entry_start, self._entry_start + n_e, dtype=np.int64)
        self._event_index.flags.writeable = False
        self._steps: tuple[CutStep, ...] = (CutStep("all events", {}, "start", n_p, n_ne, n_e),)

    def _derive(self, particles: ParticleCollection, event_index: np.ndarray, step: CutStep) -> Selection:
        new = object.__new__(Selection)
        new._particles = particles
        new._events = self._events
        new._entry_start = self._entry_start
        new._n_start = self._n_start
        event_index.flags.writeable = False
        new._event_index = event_index
        new._steps = (*self._steps, step)
        return new

    # -- particle level ------------------------------------------------------------

    def _particle_cut(self, name: str, mask: ak.Array, params: Mapping[str, Any]) -> Selection:
        particles = self._particles[mask]
        return self._derive(particles, self._event_index, CutStep(name, dict(params), "particle", *_counts(particles)))

    def min_pt(self, value: float) -> Selection:
        """Keep particles with pt > value (GeV, strict). See :func:`min_pt`."""
        return self._particle_cut("min_pt", min_pt(self._particles, value), {"value": float(value)})

    def max_eta(self, value: float) -> Selection:
        """Keep particles with |eta| < value (strict). See :func:`max_eta`."""
        return self._particle_cut("max_eta", max_eta(self._particles, value), {"value": float(value)})

    def max_rel_iso(self, value: float, cone: float | None = None) -> Selection:
        """Keep particles with relative isolation < value (strict). See :func:`max_rel_iso`."""
        mask = max_rel_iso(self._particles, value, cone)
        cone = cone if cone is not None else (0.4 if isinstance(self._particles, Muon) else 0.3)
        return self._particle_cut("max_rel_iso", mask, {"value": float(value), "cone": cone})

    def quality_id(self, name: str) -> Selection:
        """Keep muons passing the named ID working point. See :func:`quality_id`."""
        return self._particle_cut("quality_id", quality_id(cast(Muon, self._particles), name), {"name": name})

    def max_abs_dxy(self, value: float) -> Selection:
        """Keep muons with |dxy| < value (cm, strict). See :func:`max_abs_dxy`."""
        mask = max_abs_dxy(cast(Muon, self._particles), value)
        return self._particle_cut("max_abs_dxy", mask, {"value": float(value)})

    def max_abs_dz(self, value: float) -> Selection:
        """Keep muons with |dz| < value (cm, strict). See :func:`max_abs_dz`."""
        return self._particle_cut("max_abs_dz", max_abs_dz(cast(Muon, self._particles), value), {"value": float(value)})

    def global_muon(self) -> Selection:
        """Keep muons that are both global and tracker muons. See :func:`global_muon`."""
        return self._particle_cut("global_muon", global_muon(cast(Muon, self._particles)), {})

    def apply(self, **cuts: Any) -> Selection:
        """Apply several particle-level cuts given as keywords, in keyword order.

        ``sel.apply(min_pt=20, max_eta=2.4)`` is ``sel.min_pt(20).max_eta(2.4)``.
        The value of each keyword is the cut's argument (the ID name for
        ``quality_id``; ``True`` for ``global_muon``). ``None``, or ``False``
        for ``global_muon``, skips that cut.
        """
        allowed = _ELECTRON_CUTS if isinstance(self._particles, Electron) else tuple(_PARTICLE_CUTS)
        unknown = [k for k in cuts if k not in allowed]
        if unknown:
            raise TypeError(f"unknown {type(self._particles).__name__} cut(s) {unknown}; valid: {', '.join(allowed)}")
        sel = self
        for name, value in cuts.items():
            if value is None or value is False:
                continue
            if name == "global_muon":
                if value is not True:
                    raise TypeError(f"global_muon takes True or False, got {value!r}")
                sel = sel.global_muon()
            else:
                sel = getattr(sel, name)(value)
        return sel

    # -- event level -------------------------------------------------------------------

    def _event_cut(self, name: str, keep: np.ndarray, params: Mapping[str, Any]) -> Selection:
        particles = self._particles[keep]
        return self._derive(
            particles, self._event_index[keep], CutStep(name, dict(params), "event", *_counts(particles))
        )

    def require(self, n: int, exactly: bool = False) -> Selection:
        """Keep events with at least ``n`` (or, with ``exactly=True``, exactly ``n``) particles.

        This is where particle selection becomes event selection. A Z boson
        decays to two muons, so a Z -> mu+ mu- candidate event needs at least
        two muons passing the cuts. ``exactly=True`` vetoes events with extra
        selected leptons, as diboson (ZZ, WZ) analyses do.

        The count is of particles surviving the cuts applied so far, so
        ``require`` is normally called after the particle-level cuts.
        """
        if isinstance(n, bool) or not isinstance(n, (int, np.integer)) or n < 0:
            raise ValueError(f"require() needs a non-negative integer, got {n!r}")
        num = ak.to_numpy(ak.num(self._particles.p4.pt, axis=1))
        keep = num == n if exactly else num >= n
        return self._event_cut("require", keep, {"n": int(n), "exactly": bool(exactly)})

    def require_trigger(self, *names: str) -> Selection:
        """Keep events in which ANY of the named HLT paths fired.

        Only events accepted by a trigger were recorded, but a dataset such
        as DoubleMuParked is the union of many trigger paths with different
        thresholds. Requiring specific, well-understood paths (normally
        :data:`~cmsopen.ingestion.DIMUON_TRIGGERS_2012`) gives a sample
        whose trigger efficiency can be measured and corrected for. The
        decisions are read from the file with
        :meth:`EventCollection.trigger`, then aligned with
        :attr:`event_index`, so this works before or after other
        event-level cuts.

        Raises
        ------
        ValueError
            If no path is given, the Selection has no link to an
            EventCollection (it was built from particles alone), or that
            file has been closed.
        KeyError
            If a path is not in the file; the message lists the closest
            names.
        """
        if not names:
            raise ValueError("require_trigger() needs at least one HLT path name")
        if self._events is None:
            raise ValueError(
                "require_trigger() needs the file the particles came from, but this Selection has no "
                "link to an EventCollection. Build it with events.muons(...), select_muons(events, ...), "
                "or Selection(particles, events=events)."
            )
        if self._events._file.closed:
            raise ValueError(
                f"require_trigger() reads trigger branches from {self._events.path}, but that file is closed. "
                "Call require_trigger() while the file is open (inside the `with open_events(...)` block)."
            )
        fired = self._events.trigger(
            *names, entry_start=self._entry_start, entry_stop=self._entry_start + self._n_start
        )
        keep = fired[self._event_index - self._entry_start]
        return self._event_cut("require_trigger", keep, {"paths": tuple(names)})

    # -- inspection ----------------------------------------------------------------------

    @property
    def particles(self) -> ParticleCollection:
        """The surviving particles (a Muon or Electron collection), one list per surviving event."""
        return self._particles

    @property
    def event_index(self) -> np.ndarray:
        """File row of each surviving event (read-only int64 array, same length as :attr:`particles`)."""
        return self._event_index

    @property
    def events(self) -> EventCollection | None:
        """The EventCollection the particles were read from, or None."""
        return self._events

    @property
    def history(self) -> tuple[CutStep, ...]:
        """All steps so far, starting with ``"all events"``."""
        return self._steps

    @property
    def n_events(self) -> int:
        """Number of events remaining."""
        return len(self._particles)

    @property
    def n_particles(self) -> int:
        """Number of particles remaining, summed over events."""
        return self._steps[-1].n_particles

    def cutflow(self) -> CutFlow:
        """Return the :class:`CutFlow`: counts and efficiencies after each step."""
        return CutFlow(self._steps)

    def __len__(self) -> int:
        return self.n_events

    def __repr__(self) -> str:
        cuts = " -> ".join(s.label for s in self._steps[1:]) or "no cuts"
        return (
            f"Selection({type(self._particles).__name__}: {self.n_events:,} of {self._n_start:,} events, "
            f"{self.n_particles:,} particles; {cuts})"
        )


# -- entry points ----------------------------------------------------------------------


def _select(
    cls: type[ParticleCollection],
    events: EventCollection,
    fields: Sequence[str],
    entry_start: int | None,
    entry_stop: int | None,
    cuts: Mapping[str, Any],
) -> Selection:
    start, stop, _ = slice(entry_start, entry_stop).indices(events.n_events)
    stop = max(start, stop)
    particles = cls.from_record(events.collection(cls.prefix, fields, start, stop))
    return Selection(particles, events, entry_start=start).apply(**cuts)


def select_muons(
    events: EventCollection,
    fields: Sequence[str] = MUON_BRANCHES_DEFAULT,
    entry_start: int | None = None,
    entry_stop: int | None = None,
    **cuts: Any,
) -> Selection:
    """Read muons and apply particle-level cuts given as keywords, in keyword order.

    ``select_muons(events, min_pt=20, max_eta=2.4)`` equals
    ``events.muons(min_pt=20, max_eta=2.4)``. Keyword order is the order of
    the cuts and of the cutflow rows. Valid keywords: ``min_pt``,
    ``max_eta``, ``max_rel_iso``, ``quality_id``, ``max_abs_dxy``,
    ``max_abs_dz``, ``global_muon`` (pass True). With no cuts, returns a
    Selection with only the ``"all events"`` row. For the typical Z cuts use
    ``select_muons(events, **ZMUMU_MUON_CUTS)``.

    Parameters
    ----------
    events : EventCollection
        Open file; stays linked so that :meth:`Selection.require_trigger`
        works.
    fields : sequence of str, optional
        Muon fields to read; must include every field the cuts need.
    entry_start, entry_stop : int, optional
        Half-open range of file rows. :attr:`Selection.event_index` refers
        to rows of the whole file, not of this range.
    """
    return _select(Muon, events, fields, entry_start, entry_stop, cuts)


def select_electrons(
    events: EventCollection,
    fields: Sequence[str] = ELECTRON_BRANCHES_DEFAULT,
    entry_start: int | None = None,
    entry_stop: int | None = None,
    **cuts: Any,
) -> Selection:
    """Read electrons and apply particle-level cuts given as keywords, in keyword order.

    Only ``min_pt``, ``max_eta`` and ``max_rel_iso`` (dR = 0.3 cone) are
    available for electrons. Electron identification is deliberately not
    offered yet. In the 2012 development file, ``Electron_cutBased`` is 0
    for 146,777 of the 147,339 electrons (99.6%), and still for 14,597 of
    the 14,940 with pt > 20 GeV (97.7%). Values 1-4 occur 206, 63, 141 and
    152 times. That is far below what the usual veto/loose/medium/tight
    efficiencies would give, so the stored values need to be understood
    before they are used as an ID. This is left for a later layer.

    Parameters are as for :func:`select_muons`.
    """
    return _select(Electron, events, fields, entry_start, entry_stop, cuts)
