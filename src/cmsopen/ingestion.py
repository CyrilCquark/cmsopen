"""Layer 1: open CMS NanoAOD ROOT files and read raw branches lazily.

Physics context
---------------
The CMS detector records *events*: snapshots of the debris from a single
proton-proton bunch crossing at the LHC. After reconstruction, every
event contains a variable number of particle candidates (muons, electrons,
jets, ...). NanoAOD stores these as flat *columns*: one ROOT branch per
quantity, e.g. ``Muon_pt`` holds the transverse momentum of every muon,
with a counter branch ``nMuon`` telling how many muons each event has.

This module only *reads* data. It applies no cuts and no physics
selection: what you get back is exactly what is stored in the file.
Selection lives in :mod:`cmsopen.selection` (layer 3); ``muons()`` and
``electrons()`` hand over to it when given cut keywords.

Run 1 caveat
------------
The development file is a Run 1 (2012) "nanoaod-run1" file produced from
legacy AOD by the CMS Open Data group. It resembles modern NanoAOD but is
*not identical*. For example, electron ID is the integer
``Electron_cutBased`` (there is no ``Electron_tightId``), and
``Electron_nNano`` is a per-event scalar even though it carries the
``Electron_`` prefix. Never assume a modern branch name exists: every
default below was checked against the real file with ``tree.keys()``.

Units
-----
All energies, momenta and masses are in GeV, as stored by CMS. At collider
energies the natural scale is the GeV (the proton mass is ~0.938 GeV, the
Z boson ~91.19 GeV), and in natural units (c = 1) energy, momentum and mass
share the same unit, so a single unit covers all of them.
"""

from __future__ import annotations

import difflib
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

import awkward as ak
import numpy as np
import uproot

if TYPE_CHECKING:
    from cmsopen.selection import Selection

__all__ = [
    "DIMUON_TRIGGERS_2012",
    "ELECTRON_BRANCHES_DEFAULT",
    "EVENT_BRANCHES",
    "MUON_BRANCHES_DEFAULT",
    "EventCollection",
    "NotNanoAODError",
    "open_events",
]

MUON_BRANCHES_DEFAULT: tuple[str, ...] = (
    "pt",
    "eta",
    "phi",
    "mass",
    "charge",
    "pfRelIso04_all",
    "pfRelIso03_all",
    "looseId",
    "mediumId",
    "tightId",
    "softId",
    "isGlobal",
    "isTracker",
    "isPFcand",
    "dxy",
    "dz",
)
"""Default muon fields (``Muon_`` prefix stripped), verified on the Run 1 file.

Kinematics
    ``pt`` is the transverse momentum (GeV): the momentum component
    perpendicular to the beam. Because the colliding partons carry unknown
    momentum *along* the beam, only the transverse plane is balanced, so pt
    is the natural measure of how "hard" a particle is.
    ``eta`` is the pseudorapidity, ``-ln tan(theta/2)``, where theta is the
    polar angle to the beam. eta = 0 is perpendicular to the beam, and
    |eta| grows toward the beam pipe. The CMS muon system covers |eta| < 2.4.
    Differences in eta are invariant under boosts along the beam.
    ``phi`` is the azimuthal angle around the beam, in radians.
    ``mass`` is the rest mass hypothesis assigned by reconstruction; for
    muons it is the PDG value, 0.10566 GeV.
    ``charge`` is +1 or -1 in units of the elementary charge, measured from
    the bending direction in the 3.8 T solenoid field.

Isolation
    ``pfRelIso04_all`` and ``pfRelIso03_all`` are the scalar sum of pt of
    particle-flow candidates in a cone of radius dR = 0.4 (or 0.3) around the
    muon, divided by the muon pt. Muons from Z decays are *isolated*
    (little activity nearby); muons from heavy-flavour decays inside jets
    are not. A small relative isolation (e.g. < 0.15) suppresses that
    background.

Identification
    ``looseId``, ``mediumId``, ``tightId`` and ``softId`` are boolean working
    points of the official CMS muon ID, each a bundle of track-quality and
    muon-chamber requirements trading efficiency for purity.
    ``isGlobal`` means the track was fitted using both the inner tracker and
    the muon chambers; ``isTracker`` means an inner-tracker track was matched
    to muon-chamber hits; ``isPFcand`` means the particle-flow algorithm
    accepted it as a muon.

Impact parameters
    ``dxy`` and ``dz`` (cm) are the transverse and longitudinal distances of
    closest approach to the primary vertex. Prompt muons (from a Z) point
    back to the collision; muons from cosmic rays or long-lived decays
    often do not.
"""

ELECTRON_BRANCHES_DEFAULT: tuple[str, ...] = (
    "pt",
    "eta",
    "phi",
    "mass",
    "charge",
    "cutBased",
    "pfRelIso03_all",
    "isEB",
    "isEE",
    "convVeto",
    "dxy",
    "dz",
)
"""Default electron fields (``Electron_`` prefix stripped), verified on the Run 1 file.

``pt``, ``eta``, ``phi``, ``mass``, ``charge``, ``dxy`` and ``dz`` mean the
same as for muons (see :data:`MUON_BRANCHES_DEFAULT`).

``cutBased`` is the Run 1 cut-based electron ID as an *integer* working point
(higher means tighter: conventionally 0 fail, 1 veto, 2 loose, 3 medium,
4 tight). Unlike modern NanoAOD there are no per-working-point booleans.
``pfRelIso03_all`` is the relative isolation in a dR = 0.3 cone.
``isEB`` / ``isEE`` say whether the electron's calorimeter cluster lies in
the ECAL barrel (|eta| < ~1.48) or the endcaps, which have different
resolution and different ID cuts.
``convVeto`` is True if the electron is *not* consistent with a photon that
converted to an e+e- pair in the tracker material, a major source of
fake prompt electrons.
"""

EVENT_BRANCHES: tuple[str, ...] = ("run", "luminosityBlock", "event")
"""Branches that uniquely identify a collision event.

``run`` is a period of continuous data taking (hours). ``luminosityBlock``
is a ~23 second slice of a run, the unit in which data quality is certified
and integrated luminosity is counted. ``event`` is the bunch-crossing
number within the run. Together, ``(run, luminosityBlock, event)`` uniquely
labels a recorded collision, which is how duplicates across datasets are
removed and how certified-good luminosity sections are selected.
"""

DIMUON_TRIGGERS_2012: tuple[str, ...] = ("HLT_Mu17_Mu8", "HLT_Mu17_TkMu8")
"""2012 double-muon High Level Trigger paths used for Z -> mu+ mu-.

The LHC delivers ~20 million bunch crossings per second, far more than can
be stored. The trigger system decides in real time which events to keep.
The Level-1 hardware trigger is followed by the *High Level Trigger* (HLT),
a software farm running fast reconstruction. Each HLT *path* is one such
decision. ``HLT_Mu17_Mu8`` fires when the event has one muon with
pt > 17 GeV and a second with pt > 8 GeV; ``HLT_Mu17_TkMu8`` is the same but
the second muon only needs a tracker-based reconstruction.

Requiring a trigger in the analysis matters because only events that
*passed* some trigger exist in the dataset, and the DoubleMuon primary
dataset is the union of several paths with different efficiencies.
Demanding a known, well-understood path makes the selection reproducible
and its efficiency measurable. Both Z muons (typically ~40 GeV each) sit
well above these thresholds.
"""


class NotNanoAODError(ValueError):
    """Raised when a file lacks the expected flat NanoAOD event tree.

    NanoAOD is a *flat* columnar format: one TTree (``Events``) whose
    branches are plain numbers or variable-length lists of numbers, with
    no nested C++ objects. Files in other CMS formats (AOD, MiniAOD) store
    serialized C++ classes and cannot be read column by column this way.
    """


def _closest(name: str, candidates: Sequence[str], n: int = 5) -> list[str]:
    return difflib.get_close_matches(name, candidates, n=n, cutoff=0.5)


def _as_list(branches: str | Sequence[str]) -> list[str]:
    return [branches] if isinstance(branches, str) else list(branches)


class EventCollection:
    """Lazy view of the events in one NanoAOD file.

    Opening the file reads only the metadata (branch names, types, entry
    count). Event data is read only when you call :meth:`arrays`,
    :meth:`collection`, :meth:`trigger` or :meth:`iterate`, and then only
    the branches you ask for. A NanoAOD file has hundreds of branches
    (about 900 in the 2012 DoubleMuon file) and a dimuon analysis needs
    about ten, so columnar, on-demand reading is what makes large files
    usable.

    Particle quantities come back as *jagged* awkward arrays: each event is
    a list whose length is that event's particle count. Jaggedness is
    unavoidable because the number of muons varies event by event (zero,
    one, two, sometimes more), so the data cannot be a rectangular
    ``(events, muons)`` matrix without padding. Awkward arrays let you do
    vectorized numpy-style math over such lists without Python loops.

    Use :func:`open_events` to construct one. The object can be used as a
    context manager to close the underlying file.

    Parameters
    ----------
    tree : uproot.TTree
        The opened, validated event tree.
    path : str
        Local path or URL the tree was read from.
    file : uproot.ReadOnlyDirectory
        The open file handle, kept so it can be closed.
    """

    def __init__(self, tree: uproot.TTree, path: str, file: uproot.ReadOnlyDirectory) -> None:
        self._tree = tree
        self._file = file
        self.path: str = path
        """Local path or URL of the ROOT file."""
        self.tree_name: str = tree.name
        """Name of the event TTree, normally ``"Events"``."""
        self._branches: list[str] = sorted(tree.keys())
        self._branch_set: frozenset[str] = frozenset(self._branches)

    # -- metadata -----------------------------------------------------------

    @property
    def n_events(self) -> int:
        """Number of recorded collision events in the tree (read from metadata)."""
        return int(self._tree.num_entries)

    def __len__(self) -> int:
        return self.n_events

    @property
    def branches(self) -> list[str]:
        """Sorted list of all branch names in the tree.

        Each name is ``<Collection>_<quantity>`` for per-particle columns
        (``Muon_pt``), ``n<Collection>`` for the per-event particle count
        (``nMuon``), ``HLT_<path>`` for trigger decisions, or a bare name for
        event-level quantities (``run``, ``event``).
        """
        return list(self._branches)

    def has_branch(self, name: str) -> bool:
        """Return True if ``name`` is a branch in the tree.

        Use this to check for branches that differ between Run 1 and modern
        NanoAOD before relying on them.
        """
        return name in self._branch_set

    def _check_branches(self, names: Sequence[str]) -> None:
        missing = [n for n in names if n not in self._branch_set]
        if not missing:
            return
        parts = []
        for m in missing:
            close = _closest(m, self._branches)
            hint = f" (closest matches: {', '.join(close)})" if close else " (no close matches)"
            parts.append(f"{m!r}{hint}")
        raise KeyError(f"Branch(es) not found in tree {self.tree_name!r} of {self.path}: " + "; ".join(parts))

    # -- reading ------------------------------------------------------------

    def arrays(
        self,
        branches: str | Sequence[str],
        entry_start: int | None = None,
        entry_stop: int | None = None,
    ) -> ak.Array:
        """Read raw branches into an awkward record array, one record per event.

        Only the requested branches are decompressed and read, which is
        the point of a columnar format.

        Parameters
        ----------
        branches : str or sequence of str
            Full branch names, e.g. ``["nMuon", "Muon_pt"]``.
        entry_start, entry_stop : int, optional
            Half-open event range ``[entry_start, entry_stop)``. Defaults to
            all events.

        Returns
        -------
        ak.Array
            Record array with one field per branch. Per-particle branches
            are jagged (``var * float32``); per-event branches are flat.

        Raises
        ------
        KeyError
            If a branch does not exist; the message lists the closest
            matching names so typos are easy to fix.
        """
        names = _as_list(branches)
        self._check_branches(names)
        return self._tree.arrays(names, entry_start=entry_start, entry_stop=entry_stop, library="ak")

    def collection(
        self,
        prefix: str,
        fields: Sequence[str] | None = None,
        entry_start: int | None = None,
        entry_stop: int | None = None,
    ) -> ak.Array:
        """Read one particle collection as a jagged array of particle records.

        NanoAOD stores a particle's properties in separate columns
        (``Muon_pt``, ``Muon_eta``, ...). This zips them back into one
        record per particle, so ``muons[i]`` is the list of muons in event
        ``i`` and ``muons.pt`` is the jagged array of their transverse
        momenta. Grouping fields this way lets later layers treat a muon as
        one physical object (one four-vector with a charge and ID flags)
        rather than a bundle of unrelated columns.

        Parameters
        ----------
        prefix : str
            Collection name without the trailing underscore, e.g. ``"Muon"``.
        fields : sequence of str, optional
            Field names without the prefix, e.g. ``["pt", "eta"]``. Defaults
            to every *per-particle* (jagged) ``<prefix>_*`` branch. Per-event
            scalars that share the prefix, such as Run 1 ``Electron_nNano``,
            are skipped because they do not describe individual particles.
        entry_start, entry_stop : int, optional
            Half-open event range to read.

        Returns
        -------
        ak.Array
            Type ``n_events * var * {field: dtype, ...}``.

        Raises
        ------
        KeyError
            If a requested field's branch does not exist.
        ValueError
            If no branches match, or a requested field is a per-event scalar
            and so cannot be zipped into per-particle records.
        """
        head = f"{prefix}_"
        if fields is None:
            fields = [b[len(head):] for b in self._branches if b.startswith(head) and self._is_jagged(b)]
            if not fields:
                raise ValueError(f"No per-particle branches with prefix {head!r} in {self.path}")
        names = [head + f for f in fields]
        self._check_branches(names)
        scalars = [n for n in names if not self._is_jagged(n)]
        if scalars:
            raise ValueError(
                f"Branch(es) {scalars} hold one value per event, not per particle, "
                f"and cannot be zipped into the {prefix!r} collection"
            )
        raw = self._tree.arrays(names, entry_start=entry_start, entry_stop=entry_stop, library="ak")
        return ak.zip({f: raw[n] for f, n in zip(fields, names, strict=False)})

    def muons(
        self,
        fields: Sequence[str] = MUON_BRANCHES_DEFAULT,
        entry_start: int | None = None,
        entry_stop: int | None = None,
        **cuts: Any,
    ) -> ak.Array | Selection:
        """Read the muon collection: raw, or with selection cuts applied.

        Muons are about 200 times heavier than electrons, so they barely
        radiate and pass through the calorimeters, reaching the outer muon
        chambers. That makes them the cleanest probe of the Z boson: Z ->
        mu+ mu- events stand out with two energetic, isolated, oppositely
        charged muons.

        Without cut keywords, no ID, isolation or kinematic cuts are
        applied and the raw record array is returned. The raw collection
        includes poorly measured candidates (in the 2012 file, |eta| up to
        ~12, far beyond the detector, and pt up to ~120 TeV).

        With cut keywords, e.g. ``events.muons(min_pt=20, max_eta=2.4)``,
        the cuts are applied in keyword order and a
        :class:`~cmsopen.selection.Selection` is returned, which can be
        chained further (``.require(2)``) and reports a cutflow. See
        :func:`cmsopen.selection.select_muons` for the valid keywords.

        Parameters
        ----------
        fields : sequence of str, optional
            Muon fields to read; defaults to :data:`MUON_BRANCHES_DEFAULT`.
        entry_start, entry_stop : int, optional
            Half-open event range to read.
        **cuts
            Particle-level cuts (layer 3), applied in the order given.

        Returns
        -------
        ak.Array or Selection
            Without cuts: ``n_events * var * {pt, eta, phi, mass, charge, ...}``.
            With cuts: a Selection holding a ``Muon`` collection.
        """
        if cuts:
            from cmsopen.selection import select_muons

            return select_muons(self, fields, entry_start, entry_stop, **cuts)
        return self.collection("Muon", fields, entry_start, entry_stop)

    def electrons(
        self,
        fields: Sequence[str] = ELECTRON_BRANCHES_DEFAULT,
        entry_start: int | None = None,
        entry_stop: int | None = None,
        **cuts: Any,
    ) -> ak.Array | Selection:
        """Read the electron collection: raw, or with selection cuts applied.

        Electrons leave a track and deposit their energy in the
        electromagnetic calorimeter. Z -> e+ e- is the electron counterpart
        of the dimuon channel. Without cut keywords no cuts are applied and
        the raw record array is returned. With cut keywords (``min_pt``,
        ``max_eta``, ``max_rel_iso``) a
        :class:`~cmsopen.selection.Selection` is returned; see
        :func:`cmsopen.selection.select_electrons`.

        Parameters
        ----------
        fields : sequence of str, optional
            Electron fields to read; defaults to
            :data:`ELECTRON_BRANCHES_DEFAULT`.
        entry_start, entry_stop : int, optional
            Half-open event range to read.
        **cuts
            Particle-level cuts (layer 3), applied in the order given.

        Returns
        -------
        ak.Array or Selection
            Without cuts: ``n_events * var * {pt, eta, phi, mass, charge, cutBased, ...}``.
            With cuts: a Selection holding an ``Electron`` collection.
        """
        if cuts:
            from cmsopen.selection import select_electrons

            return select_electrons(self, fields, entry_start, entry_stop, **cuts)
        return self.collection("Electron", fields, entry_start, entry_stop)

    def trigger(
        self,
        *names: str,
        entry_start: int | None = None,
        entry_stop: int | None = None,
    ) -> np.ndarray:
        """Per-event trigger decision: True if ANY of the named HLT paths fired.

        Each ``HLT_*`` branch is a boolean per event recording whether that
        High Level Trigger path accepted the event. An analysis normally
        requires a logical OR of a few paths (see
        :data:`DIMUON_TRIGGERS_2012`) so that its event sample has a
        well-defined, measurable trigger efficiency.

        Parameters
        ----------
        *names : str
            One or more HLT path branch names, e.g. ``"HLT_Mu17_Mu8"``.
        entry_start, entry_stop : int, optional
            Half-open event range to read.

        Returns
        -------
        numpy.ndarray of bool
            Shape ``(n_selected_events,)``.

        Raises
        ------
        ValueError
            If no path names are given.
        KeyError
            If a path is not in this file (trigger menus change between
            run periods); the message lists the closest matching names.
        """
        if not names:
            raise ValueError("trigger() needs at least one HLT path name")
        decisions = self.arrays(names, entry_start, entry_stop)
        return np.logical_or.reduce([ak.to_numpy(decisions[n]).astype(bool) for n in names])

    def iterate(
        self,
        branches: str | Sequence[str],
        step_size: int | str = 100_000,
        entry_start: int | None = None,
        entry_stop: int | None = None,
    ) -> Iterator[ak.Array]:
        """Yield consecutive chunks of events, each an awkward record array.

        Use this to stream through files too large for memory: each chunk
        is processed and discarded before the next is read. Because events
        are independent collisions, per-event results (such as histogram
        fills) from different chunks can simply be added together.

        Parameters
        ----------
        branches : str or sequence of str
            Full branch names to read.
        step_size : int or str, optional
            Events per chunk (int) or a memory size such as ``"100 MB"``.
        entry_start, entry_stop : int, optional
            Half-open event range to cover.

        Yields
        ------
        ak.Array
            Record array with one field per branch for the next chunk.
        """
        names = _as_list(branches)
        self._check_branches(names)
        yield from self._tree.iterate(
            names, step_size=step_size, entry_start=entry_start, entry_stop=entry_stop, library="ak"
        )

    # -- helpers ------------------------------------------------------------

    def _is_jagged(self, name: str) -> bool:
        return isinstance(self._tree[name].interpretation, uproot.AsJagged)

    def summary(self) -> str:
        """Return a short human-readable description of the file."""
        return (
            f"File:     {self.path}\n"
            f"Tree:     {self.tree_name}\n"
            f"Events:   {self.n_events:,}\n"
            f"Branches: {len(self._branches)}"
        )

    def close(self) -> None:
        """Close the underlying ROOT file."""
        self._file.close()

    def __enter__(self) -> EventCollection:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def __repr__(self) -> str:
        return f"EventCollection(path={self.path!r}, tree={self.tree_name!r}, n_events={self.n_events})"


def open_events(path: str | Path, tree: str = "Events") -> EventCollection:
    """Open a NanoAOD file and return a lazy :class:`EventCollection`.

    Only file metadata is read here; no event data is loaded until you ask
    for specific branches.

    Parameters
    ----------
    path : str or pathlib.Path
        Local file path or an ``http(s)://`` URL, for example a file on
        opendata.cern.ch. URLs are read with HTTP range requests, so only
        the needed bytes are downloaded. XRootD is not required.
    tree : str, optional
        Name of the event TTree. NanoAOD always uses ``"Events"``.

    Returns
    -------
    EventCollection

    Raises
    ------
    NotNanoAODError
        If the tree is missing (the message lists the trees that do exist),
        is not a TTree, or does not have the flat NanoAOD structure (nested
        sub-branches, or missing ``run``/``luminosityBlock``/``event``).
    """
    path = str(path)
    options = {}
    if path.startswith(("http://", "https://")):
        # uproot's own HTTP source avoids the fsspec/aiohttp dependency.
        options["handler"] = uproot.source.http.HTTPSource
    file = uproot.open(path, **options)
    try:
        trees = file.keys(cycle=False, filter_classname="TTree", recursive=True)
        if tree not in file:
            raise NotNanoAODError(f"No tree {tree!r} in {path}. Trees in this file: {trees or 'none'}")
        obj = file[tree]
        if not isinstance(obj, uproot.TTree):
            raise NotNanoAODError(f"{tree!r} in {path} is a {obj.classname}, not a TTree. Trees in this file: {trees}")
        nested = [b.name for b in obj.branches if b.branches]
        if nested:
            raise NotNanoAODError(
                f"Tree {tree!r} in {path} is not flat NanoAOD: branches with sub-branches: {nested[:5]}"
            )
        missing = [b for b in EVENT_BRANCHES if b not in obj]
        if missing:
            raise NotNanoAODError(f"Tree {tree!r} in {path} lacks NanoAOD event-ID branches {missing}")
    except BaseException:
        file.close()
        raise
    return EventCollection(obj, path, file)
