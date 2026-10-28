"""Layer 4: muon pairs (combinatorics), candidate choice and multiplicity.

Physics context
---------------
The Z boson is electrically neutral. Electric charge is exactly conserved,
so its two decay muons must have charges that add up to zero: one mu+
(charge +1) and one mu- (charge -1). A Z -> mu+ mu- candidate is therefore
an *opposite-sign* (OS) pair, with charge product q1 * q2 = -1.

A *same-sign* (SS) pair (mu+ mu+ or mu- mu-, q1 * q2 = +1) has total charge
+-2 and cannot come from a Z, or from any neutral resonance. Same-sign pairs
come from the backgrounds:

* combinatorics: two unrelated muons in the same collision, for example
  one from each of two b-hadron decays, or one prompt muon and one from a
  hadron decaying in flight;
* misidentification: a hadron punching through to the muon chambers and
  reconstructed as a muon, whose charge is unrelated to the other muon;
* charge mismeasurement: a very stiff (high-pT) track whose curvature sign
  is measured wrongly, rare at Z energies.

Pairing two unrelated muons gives OS and SS pairs at similar rates, while
a neutral resonance gives only OS. The SS spectrum is therefore a
data-driven estimate of the size and shape of the combinatorial
background under the OS spectrum. It is an estimate, not an exact copy:
some backgrounds favour OS, for example a b quark and a b antiquark that
each decay to a muon (mostly mu- and mu+), with B-meson mixing turning
part of them into SS. A Z peak in the OS spectrum with no peak in the SS
spectrum shows that the peak is a real neutral particle and not an
artefact of the selection.

Combinatorics
-------------
An event with n selected muons has n(n-1)/2 unordered pairs of distinct
muons: 0 for n = 0 or 1, 1 for n = 2, 3 for n = 3, 6 for n = 4. If n+ muons
are positive and n- negative (n+ + n- = n), the pairs split exactly into

    n_OS = n+ * n-   and   n_SS = n+(n+ - 1)/2 + n-(n- - 1)/2,

which add up to n(n-1)/2. A pair never uses the same muon twice and is
never counted twice: (a, b) and (b, a) are the same pair.

Several candidates per event
----------------------------
A Z decays to exactly two muons, but an event can contain extra muons,
for example from a b-hadron decay in the same collision or from another
collision in the same bunch crossing (pileup). Each extra muon creates
extra pairs, so one event can yield several Z *candidates*, of which at
most one is the real Z. Keeping them all counts some events more than once
and adds combinatorial pairs to the spectrum. Choosing one (see
:func:`best_pair`) needs a rule, and the rule matters: a rule that looks at
the mass, such as "the pair closest to 91 GeV", builds a peak at 91 GeV
even from pure background and biases any fit to the spectrum. Rules based
on quantities that do not depend on the pair mass, such as the pT of the
legs, avoid that bias.

Leg ordering
------------
The two muons of a pair are physically interchangeable; the invariant
mass and every other pair quantity are symmetric in them. Naming them
``leg1`` and ``leg2`` is a convention. Here ``leg1`` is always the muon
with the higher pT (the "leading" leg) and ``leg2`` the lower ("subleading"),
which is how trigger thresholds and analysis cuts are usually written
(for example 17 GeV and 8 GeV for ``HLT_Mu17_Mu8``). The ordering is made
explicitly by sorting each event's muons by pT, never by trusting the
order of the input. For two muons with exactly equal pT, the one that
comes first in the input is ``leg1``.

Everything here is vectorized with awkward and numpy; there are no Python
loops over events, muons or pairs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import awkward as ak
import numpy as np

from cmsopen.kinematics import delta_r, invariant_mass, pair_eta, pair_phi, pair_pt, pair_rapidity
from cmsopen.objects import Muon
from cmsopen.selection import Selection

__all__ = [
    "BEST_PAIR_STRATEGIES",
    "CHARGE_MODES",
    "MuonPairs",
    "PairMultiplicity",
    "all_pairs",
    "best_pair",
    "make_pairs",
    "multiplicity",
    "opposite_sign_pairs",
    "same_sign_pairs",
]

CHARGE_MODES: tuple[str, ...] = ("opposite", "same", "any")
"""Accepted values of the ``charge`` argument of :func:`make_pairs`."""

BEST_PAIR_STRATEGIES: tuple[str, ...] = ("highest_pt_sum", "leading", "closest_to")
"""Accepted values of the ``strategy`` argument of :func:`best_pair`."""


def _readonly(index: np.ndarray) -> np.ndarray:
    index = np.asarray(index, dtype=np.int64)
    index.flags.writeable = False
    return index


def _as_int64(array: ak.Array) -> ak.Array:
    return ak.values_astype(array, np.int64)


class MuonPairs:
    """Muon pairs in a set of events: zero or more pairs per event, as jagged arrays.

    Entry ``[i][k]`` of every field describes pair ``k`` of event ``i``.
    ``leg1`` and ``leg2`` are :class:`~cmsopen.objects.Muon` collections
    with this same jagged structure (one muon per pair, not one per muon),
    so ``pairs.leg1.p4.pt[i][k]`` is the pT of the leading muon of pair
    ``k`` in event ``i``. ``leg1`` is always the higher-pT muon of the pair
    (see the module docstring on leg ordering).

    Pair kinematics (:attr:`mass`, :attr:`pt`, :attr:`eta`, :attr:`phi`,
    :attr:`rapidity`, :attr:`delta_r`) are computed on demand from the legs'
    four-momenta with :mod:`cmsopen.kinematics`, in float64.

    Usually built with :func:`make_pairs`, :func:`opposite_sign_pairs`,
    :func:`same_sign_pairs` or :func:`all_pairs`, not directly.

    Indexing
    --------
    ``pairs[mask]`` with a jagged boolean mask (one entry per pair, e.g.
    ``pairs[pairs.mass > 60]``) keeps the selected pairs and every event;
    a jagged integer array picks pairs by position. A flat boolean mask,
    an integer array or a slice selects whole events, and
    :attr:`event_index` follows. A single integer is not accepted, because
    the result would no longer be a set of events.

    Parameters
    ----------
    leg1, leg2 : Muon
        The higher-pT and lower-pT muon of each pair, same jagged structure.
    index1, index2 : array-like
        Jagged integer positions of ``leg1`` and ``leg2`` in the event's
        input muon list.
    rank1, rank2 : array-like
        Jagged pT rank of each leg among the event's input muons (0 = the
        highest-pT muon of the event).
    event_index : array-like
        File row of each event (one integer per event).

    Raises
    ------
    ValueError
        If the fields do not share one jagged structure or ``event_index``
        has the wrong length.
    """

    def __init__(
        self,
        leg1: Muon,
        leg2: Muon,
        index1: Any,
        index2: Any,
        rank1: Any,
        rank2: Any,
        event_index: Any,
    ) -> None:
        if not isinstance(leg1, Muon) or not isinstance(leg2, Muon):
            raise TypeError(f"leg1 and leg2 must be Muon collections, got {type(leg1).__name__} and {type(leg2).__name__}")
        self.leg1: Muon = leg1
        """The higher-pT muon of each pair (jagged: one entry per pair)."""
        self.leg2: Muon = leg2
        """The lower-pT muon of each pair (jagged: one entry per pair)."""
        self.index1: ak.Array = _as_int64(ak.Array(index1))
        """Position of ``leg1`` in its event's input muon list (jagged int64)."""
        self.index2: ak.Array = _as_int64(ak.Array(index2))
        """Position of ``leg2`` in its event's input muon list (jagged int64)."""
        self.rank1: ak.Array = _as_int64(ak.Array(rank1))
        """pT rank of ``leg1`` among the event's input muons, 0 = highest (jagged int64)."""
        self.rank2: ak.Array = _as_int64(ak.Array(rank2))
        """pT rank of ``leg2`` among the event's input muons (jagged int64)."""
        self._event_index = _readonly(event_index)
        ref = ak.num(self.index1, axis=1)
        for name, arr in (
            ("leg1", leg1.p4.pt), ("leg2", leg2.p4.pt), ("index2", self.index2),
            ("rank1", self.rank1), ("rank2", self.rank2),
        ):
            if arr.ndim != 2 or len(arr) != len(ref) or not ak.all(ak.num(arr, axis=1) == ref):
                raise ValueError(f"{name!r} does not have the same jagged structure as 'index1'")
        if self._event_index.shape != (len(ref),):
            raise ValueError(f"event_index has shape {self._event_index.shape}, expected ({len(ref)},): one row per event")

    # -- bookkeeping ---------------------------------------------------------------

    @property
    def event_index(self) -> np.ndarray:
        """File row of each event (read-only int64 array, one entry per event).

        Carried through from a :class:`~cmsopen.selection.Selection`, so it
        still points at the right row after event-level cuts; for a plain
        Muon collection it is ``0 .. n_events - 1``.
        """
        return self._event_index

    @property
    def charge_product(self) -> ak.Array:
        """q1 * q2 of each pair (jagged int64): -1 for opposite sign, +1 for same sign."""
        return _as_int64(self.leg1.charge * self.leg2.charge)

    @property
    def num(self) -> ak.Array:
        """Number of pairs in each event."""
        return ak.num(self.index1, axis=1)

    @property
    def n_pairs(self) -> int:
        """Total number of pairs, summed over events."""
        return int(ak.sum(self.num))

    def __len__(self) -> int:
        """Number of events (including events with no pair)."""
        return len(self.index1)

    # -- pair kinematics (layer 5) -------------------------------------------------

    @property
    def mass(self) -> ak.Array:
        """Invariant mass of each pair (GeV). See :func:`cmsopen.kinematics.invariant_mass`."""
        return invariant_mass(self.leg1.p4, self.leg2.p4)

    @property
    def pt(self) -> ak.Array:
        """Transverse momentum of each pair (GeV). See :func:`cmsopen.kinematics.pair_pt`."""
        return pair_pt(self.leg1.p4, self.leg2.p4)

    @property
    def eta(self) -> ak.Array:
        """Pseudorapidity of each pair's momentum. See :func:`cmsopen.kinematics.pair_eta`."""
        return pair_eta(self.leg1.p4, self.leg2.p4)

    @property
    def phi(self) -> ak.Array:
        """Azimuth of each pair's transverse momentum (radians). See :func:`cmsopen.kinematics.pair_phi`."""
        return pair_phi(self.leg1.p4, self.leg2.p4)

    @property
    def rapidity(self) -> ak.Array:
        """Rapidity of each pair. See :func:`cmsopen.kinematics.pair_rapidity`."""
        return pair_rapidity(self.leg1.p4, self.leg2.p4)

    @property
    def delta_r(self) -> ak.Array:
        """Angular separation of the two legs in eta-phi. See :func:`cmsopen.kinematics.delta_r`."""
        return delta_r(self.leg1.p4, self.leg2.p4)

    # -- container behaviour -----------------------------------------------------------

    def __getitem__(self, where: Any) -> MuonPairs:
        if isinstance(where, (bool, np.bool_)) or isinstance(where, (int, np.integer)):
            raise TypeError(
                "MuonPairs takes a jagged pair mask, a flat event mask, an integer array or a slice; "
                "a single integer would not give a set of events (use pairs[[i]] for one event)"
            )
        event_index = self._event_index
        if not isinstance(where, slice):
            where = ak.Array(where) if not isinstance(where, ak.Array) else where
            if where.ndim == 1:
                event_index = self._event_index[ak.to_numpy(where)]
            elif where.ndim != 2:
                raise ValueError(f"MuonPairs index must be 1- or 2-dimensional, got {where.ndim} dimensions")
        else:
            event_index = self._event_index[where]
        return MuonPairs(
            self.leg1[where], self.leg2[where],
            self.index1[where], self.index2[where],
            self.rank1[where], self.rank2[where],
            event_index,
        )

    def to_awkward(self) -> ak.Array:
        """Return one jagged record array with one record per pair.

        Fields: ``leg1`` and ``leg2`` (the muon records of
        :meth:`Muon.to_awkward`), ``index1``, ``index2``, ``rank1``,
        ``rank2``, ``charge_product``, ``mass``, ``pt``, ``eta``, ``phi``,
        ``rapidity``, ``delta_r``, and ``event_index`` repeated on every
        pair of the event.
        """
        event_index = ak.broadcast_arrays(ak.Array(self._event_index), self.index1)[0]
        return ak.zip(
            {
                "leg1": self.leg1.to_awkward(),
                "leg2": self.leg2.to_awkward(),
                "index1": self.index1,
                "index2": self.index2,
                "rank1": self.rank1,
                "rank2": self.rank2,
                "charge_product": self.charge_product,
                "mass": self.mass,
                "pt": self.pt,
                "eta": self.eta,
                "phi": self.phi,
                "rapidity": self.rapidity,
                "delta_r": self.delta_r,
                "event_index": event_index,
            },
            depth_limit=2,
        )

    def __repr__(self) -> str:
        return f"MuonPairs(n_events={len(self):,}, n_pairs={self.n_pairs:,})"


# -- pair finding ------------------------------------------------------------------


def _unpack(muons: Selection | Muon) -> tuple[Muon, np.ndarray]:
    if isinstance(muons, Selection):
        particles, event_index = muons.particles, muons.event_index
    else:
        particles, event_index = muons, None
    if not isinstance(particles, Muon):
        raise TypeError(f"expected a Muon collection or a Selection of muons, got {type(particles).__name__}")
    if particles.p4.pt.ndim != 2:
        raise ValueError("pairing needs a jagged Muon collection with one list of muons per event")
    if event_index is None:
        event_index = np.arange(len(particles), dtype=np.int64)
    return particles, event_index


def make_pairs(muons: Selection | Muon, charge: str = "opposite") -> MuonPairs:
    """Form every unordered pair of distinct muons in each event, filtered by charge.

    A Z boson is neutral, so by charge conservation its decay muons have
    opposite charges: ``charge="opposite"`` keeps exactly the pairs that
    could be a Z -> mu+ mu- decay. ``charge="same"`` keeps the pairs that
    cannot (total charge +-2), which measure the combinatorial and
    misidentification background (see the module docstring).
    ``charge="any"`` keeps every pair.

    How the pairs are formed: in each event the muons are sorted by pT,
    highest first (a stable sort, so equal pTs keep their input order), and
    ``ak.argcombinations(..., 2)`` lists every pair of positions (a, b) with
    a < b in that sorted list. Requiring a < b means a muon is never paired
    with itself and no pair appears twice, giving exactly n(n-1)/2 pairs for
    n muons; and because the list is sorted, the first muon of every pair is
    the higher-pT one, which becomes ``leg1``. The pairs of an event come in
    the order (1st, 2nd), (1st, 3rd), ..., (2nd, 3rd), ... of the pT-sorted
    muons, whatever order the input muons were in. The charge requirement is
    then a mask on q1 * q2.

    Events with fewer than two muons get an empty list of pairs; no event is
    ever dropped, so the result has one entry per input event. Pairs refer to
    the input through :attr:`MuonPairs.index1` / :attr:`~MuonPairs.index2`
    (position in the event's input muon list) and to the file through
    :attr:`MuonPairs.event_index`.

    Parameters
    ----------
    muons : Selection or Muon
        A selection of muons (e.g. after ``.require(2)``), whose
        ``event_index`` is carried through, or a plain jagged Muon
        collection (``event_index`` is then 0 .. n_events - 1).
    charge : {"opposite", "same", "any"}
        Charge requirement on the pair.

    Returns
    -------
    MuonPairs

    Raises
    ------
    ValueError
        If ``charge`` is not one of :data:`CHARGE_MODES`.
    TypeError
        If ``muons`` is not a Muon collection or a Selection of muons.
    """
    if charge not in CHARGE_MODES:
        raise ValueError(f"charge must be one of {CHARGE_MODES}, got {charge!r}")
    particles, event_index = _unpack(muons)

    order = ak.argsort(particles.p4.pt, axis=1, ascending=False, stable=True)
    rank1, rank2 = ak.unzip(ak.argcombinations(order, 2, axis=1))
    index1, index2 = order[rank1], order[rank2]

    if charge != "any":
        q = _as_int64(particles.charge)
        product = q[index1] * q[index2]
        keep = product == (-1 if charge == "opposite" else 1)
        index1, index2, rank1, rank2 = index1[keep], index2[keep], rank1[keep], rank2[keep]

    return MuonPairs(particles[index1], particles[index2], index1, index2, rank1, rank2, event_index)


def opposite_sign_pairs(muons: Selection | Muon) -> MuonPairs:
    """All opposite-sign muon pairs (q1 * q2 = -1): the Z -> mu+ mu- candidates.

    Charge is conserved and the Z is neutral, so a Z always decays to one
    mu+ and one mu-. Same as ``make_pairs(muons, charge="opposite")``.
    """
    return make_pairs(muons, charge="opposite")


def same_sign_pairs(muons: Selection | Muon) -> MuonPairs:
    """All same-sign muon pairs (q1 * q2 = +1): a background-only control sample.

    A same-sign pair has charge +-2 and cannot come from a Z. Pairings of
    unrelated or misidentified muons produce same-sign and opposite-sign
    pairs at similar rates, so the same-sign spectrum estimates the
    combinatorial background under the opposite-sign one (approximately:
    see the module docstring for backgrounds that favour opposite sign).
    Same as ``make_pairs(muons, charge="same")``.
    """
    return make_pairs(muons, charge="same")


def all_pairs(muons: Selection | Muon) -> MuonPairs:
    """Every pair of distinct muons, with no charge requirement: n(n-1)/2 per event.

    Same as ``make_pairs(muons, charge="any")``. For real muons (charge
    +-1) every pair is either opposite- or same-sign, so the counts satisfy
    n_all = n_OS + n_SS in every event.
    """
    return make_pairs(muons, charge="any")


# -- one candidate per event -------------------------------------------------------


def best_pair(pairs: MuonPairs, strategy: str = "highest_pt_sum", target: float | None = None) -> MuonPairs:
    """Keep at most one pair per event, chosen by ``strategy``.

    Why choose: an event with three or more selected muons gives several
    candidate pairs (three muons give three pairs, four give six), but a Z
    decays to only two muons. Keeping every candidate counts such events
    several times and adds combinatorial pairs to the spectrum. Choosing one
    candidate per event gives one entry per event, but the choice is part of
    the measurement and can bias it.

    Strategies
    ----------
    ``"highest_pt_sum"`` (default)
        The pair with the largest leg1.pt + leg2.pt. Z muons are hard
        (about 45 GeV each), while extra muons from heavy-flavour decays
        or pileup are mostly soft, so the hardest pair is the most likely
        Z. The rule does not look at the pair mass, so it cannot create a
        peak where there is none. On a tie, the first pair in pT order wins.
    ``"leading"``
        Only the pair formed by the two highest-pT muons of the event (in
        the input to :func:`make_pairs`), kept only if it is in ``pairs``,
        i.e. if it passed the charge requirement and any later pair cut.
        Events whose two leading muons have the same sign get no pair; the
        rule never falls back to another pair. Also mass-blind.
    ``"closest_to"``
        The pair whose mass is closest to ``target`` (GeV), which must be
        given. WARNING: this rule must NOT be the default and must NOT be
        used for a headline mass spectrum or fit. Choosing the candidate
        whose mass is nearest the Z mass pulls the chosen masses towards
        the target in every multi-candidate event, so it sculpts a fake peak
        at ``target`` even out of pure background, makes the peak look
        narrower and purer than it is, and biases any fitted mass and width
        towards ``target``. It is only appropriate where that bias does not
        matter or is the point, for example a ZZ -> 4 mu analysis that
        assigns muons to an on-shell Z after the four-muon mass is fixed,
        or a study of the bias itself.

    Parameters
    ----------
    pairs : MuonPairs
        Candidate pairs, e.g. from :func:`opposite_sign_pairs`.
    strategy : {"highest_pt_sum", "leading", "closest_to"}
        How to choose.
    target : float, optional
        Target mass in GeV; required for ``"closest_to"`` and not allowed
        otherwise.

    Returns
    -------
    MuonPairs
        Same events (and :attr:`~MuonPairs.event_index`) as ``pairs``, each
        with 0 or 1 pair; events without candidates stay, with an empty list.

    Raises
    ------
    ValueError
        For an unknown strategy, a missing ``target`` with ``"closest_to"``,
        or a ``target`` given with another strategy.
    """
    if not isinstance(pairs, MuonPairs):
        raise TypeError(f"best_pair() needs MuonPairs, got {type(pairs).__name__}")
    if strategy not in BEST_PAIR_STRATEGIES:
        raise ValueError(f"strategy must be one of {BEST_PAIR_STRATEGIES}, got {strategy!r}")
    if strategy == "closest_to":
        if target is None:
            raise ValueError('best_pair(strategy="closest_to") requires target=<mass in GeV>')
        target = float(target)
        if not np.isfinite(target):
            raise ValueError(f"target must be a finite mass in GeV, got {target!r}")
    elif target is not None:
        raise ValueError(f"target is only used by strategy='closest_to', not {strategy!r}")

    if strategy == "leading":
        return pairs[(pairs.rank1 == 0) & (pairs.rank2 == 1)]
    if strategy == "highest_pt_sum":
        choice = ak.argmax(pairs.leg1.p4.pt + pairs.leg2.p4.pt, axis=1, keepdims=True)
    else:
        choice = ak.argmin(np.abs(pairs.mass - target), axis=1, keepdims=True)
    return pairs[ak.drop_none(choice)]


# -- multiplicity --------------------------------------------------------------------


@dataclass(frozen=True)
class PairMultiplicity:
    """How many events have 0, 1, 2 and 3 or more candidate pairs.

    The multiplicity shows how often the choice of candidate matters: only
    events with two or more pairs are affected by :func:`best_pair`.
    """

    n_events: int
    n_pairs: int
    zero: int
    one: int
    two: int
    three_or_more: int

    def to_dict(self) -> dict[str, int]:
        """Return ``{"0": ..., "1": ..., "2": ..., "3+": ...}`` event counts."""
        return {"0": self.zero, "1": self.one, "2": self.two, "3+": self.three_or_more}

    def __str__(self) -> str:
        lines = [f"{'pairs per event':>16}  {'events':>10}  {'fraction':>8}"]
        for label, count in self.to_dict().items():
            frac = f"{100 * count / self.n_events:.2f}%" if self.n_events else "-"
            lines.append(f"{label:>16}  {count:>10,}  {frac:>8}")
        lines.append(f"{'total':>16}  {self.n_events:>10,}  ({self.n_pairs:,} pairs)")
        return "\n".join(lines)


def multiplicity(pairs: MuonPairs) -> PairMultiplicity:
    """Count events with 0, 1, 2 and 3+ candidate pairs.

    With n muons there are n(n-1)/2 pairs before any charge requirement, so
    multiplicity grows quickly: 2 muons give 1 pair, 3 give 3, 4 give 6.
    For opposite-sign pairs, 3 muons (two of one sign) give 2 pairs and
    4 muons (two of each sign) give 4.
    """
    if not isinstance(pairs, MuonPairs):
        raise TypeError(f"multiplicity() needs MuonPairs, got {type(pairs).__name__}")
    num = ak.to_numpy(pairs.num)
    return PairMultiplicity(
        n_events=len(num),
        n_pairs=int(num.sum()),
        zero=int(np.sum(num == 0)),
        one=int(np.sum(num == 1)),
        two=int(np.sum(num == 2)),
        three_or_more=int(np.sum(num >= 3)),
    )
