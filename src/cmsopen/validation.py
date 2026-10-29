"""Layer 6b validation: is the fitted peak the same in every part of the detector, for both charges, at all pileup?

The categories, bins, working points, minimum size and reported quantities are
the ones pre-registered in dev/validation_plan.md; nothing here is chosen by
looking at the data.

Physics context
---------------
Barrel and endcap. The CMS muon system and tracker are a central cylinder
(the *barrel*, here |eta| < 1.2) closed by two disks (the *endcaps*,
1.2 <= |eta| <= 2.4). Muons in the two regions cross different amounts of
material, are measured by different detectors (drift tubes in the barrel,
cathode strip chambers in the endcaps) and bend over a shorter lever arm in
the magnetic field at large |eta|, so the momentum resolution is worse and the
momentum scale can differ. A pair is classified by where its two muons are:
BB (both barrel), BE (one each), EE (both endcap). A peak that moves between
BB and EE points to a region-dependent momentum scale; a resolution that grows
from BB to EE is expected.

Charge. A muon's momentum is measured from the curvature of its track,
kappa = q / pT. A misaligned tracker (for example a small twist of the barrel
layers, or a radial distortion) biases the measured curvature by an additive
amount delta(kappa) that depends on the track's azimuth phi and
pseudorapidity eta. An additive curvature bias raises the pT of one charge
and lowers the other's, so the dimuon peak, binned in the phi or eta of the
mu+ and of the mu-, moves in opposite directions for the two charges. A
wrong magnetic-field value instead scales every momentum the same way and
moves both together. Comparing mu+ with mu- bin by bin therefore separates
alignment-type biases from a global momentum scale.

Pileup. Each bunch crossing in 2012 had on average about 20 additional
proton-proton collisions (pileup), recorded as extra primary vertices
(PV_npvsGood). Extra particles enter the isolation sums and the event
reconstruction; a peak position or resolution that changes with the number
of vertices would expose a pileup-dependent selection or calibration.

Working points. Tighter muon identification and isolation change the mix of
events: isolation also counts the photons of final-state radiation near the
muon, so a tighter isolation removes radiative events preferentially and can
move the peak and the size of its low-mass tail. Rerunning the analysis at
several (overlapping) working points shows how much the result depends on
that choice.

Offsets are measurements, not error bars. Every number reported here is a
measured shift with its statistical uncertainty. A spread between categories
or a mu+/mu- difference is a property of this detector and this reconstruction;
it is reported as measured. Whether and how it becomes a systematic
uncertainty, or a correction, is a separate decision; there is no target for
the mass.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import numpy as np

from cmsopen.fitting import (
    CB_MODELS,
    MIXTURE_MODELS,
    THREE_RES_MODELS,
    FitError,
    FitResult,
    fit_mass_peak,
    fit_stability,
    make_histogram,
    pdg_mass_width,
)

if TYPE_CHECKING:
    from cmsopen.pipeline import ChannelConfig

__all__ = [
    "BARREL_MAX_ETA",
    "ENDCAP_MAX_ETA",
    "ETA_EDGES",
    "MIN_PAIRS",
    "PHI_EDGES",
    "PILEUP_EDGES",
    "PT_EDGES",
    "REGIONS",
    "WORKING_POINTS",
    "SystematicsSummary",
    "ValidationEntry",
    "ValidationResult",
    "bin_index",
    "classify_regions",
    "fit_entry",
    "run_validation",
    "systematics_summary",
    "working_point_cuts",
]

BARREL_MAX_ETA = 1.2
"""Barrel: |eta| < 1.2."""
ENDCAP_MAX_ETA = 2.4
"""Endcap: 1.2 <= |eta| <= 2.4."""
REGIONS: tuple[str, ...] = ("BB", "BE", "EE")
MIN_PAIRS = 5000
"""Fewest pairs in the fit range for an entry to be fitted; never lowered (dev/validation_plan.md)."""
PHI_EDGES: tuple[float, ...] = (-math.pi, -math.pi / 2, 0.0, math.pi / 2, math.pi)
PHI_LABELS: tuple[str, ...] = ("[-pi, -pi/2)", "[-pi/2, 0)", "[0, pi/2)", "[pi/2, pi]")
ETA_EDGES: tuple[float, ...] = (-2.4, -0.8, 0.8, 2.4)
PT_EDGES: Mapping[str, tuple[float, ...]] = {
    "Z_mumu": (20.0, 30.0, 40.0, 50.0, math.inf),
    "Jpsi_mumu": (3.0, 4.0, 6.0, 10.0, math.inf),
}
"""Sub-leading muon pT bins (GeV) per registered channel."""
PILEUP_EDGES: tuple[float, ...] = (0.0, 15.0, 23.0, math.inf)
WORKING_POINTS: tuple[tuple[str, float], ...] = tuple(
    (qid, iso) for qid in ("medium", "tight") for iso in (0.08, 0.12, 0.20)
)
"""(quality_id, max_rel_iso) samples; overlapping, not a partition."""
COMPARED_MODELS: tuple[str, ...] = (
    "voigt_poly",
    "cb_bw_exp",
    "cb_bw_poly2",
    "cb2_bw_exp",
    "cb2_bw_poly2",
    "cb3_bw_exp",
    "cb3_bw_poly2",
)
PAIR_FIELDS: tuple[str, ...] = ("mass", "eta_plus", "eta_minus", "phi_plus", "phi_minus", "pt_sublead", "npv")


# -- classification -----------------------------------------------------------------------------------------------


def classify_regions(eta_a: Any, eta_b: Any) -> np.ndarray:
    """``"BB"``, ``"BE"`` or ``"EE"`` for each pair, from its two muons' pseudorapidities.

    Barrel is |eta| < 1.2, endcap 1.2 <= |eta| <= 2.4. A muon beyond 2.4 is
    outside the acceptance of the selection and raises ValueError.
    """
    a, b = np.abs(np.asarray(eta_a, dtype=np.float64)), np.abs(np.asarray(eta_b, dtype=np.float64))
    if np.any(a > ENDCAP_MAX_ETA) or np.any(b > ENDCAP_MAX_ETA) or np.any(np.isnan(a) | np.isnan(b)):
        raise ValueError(f"muons must have |eta| <= {ENDCAP_MAX_ETA} to be classified")
    n_endcap = (a >= BARREL_MAX_ETA).astype(int) + (b >= BARREL_MAX_ETA).astype(int)
    return np.asarray(REGIONS)[n_endcap]


def bin_index(values: Any, edges: Sequence[float]) -> np.ndarray:
    """Bin of each value for half-open bins [e_k, e_k+1), the last bin closed when its upper edge is finite.

    Values outside every bin get -1.
    """
    v = np.asarray(values, dtype=np.float64)
    e = np.asarray(edges, dtype=np.float64)
    idx = np.searchsorted(e, v, side="right") - 1
    if np.isfinite(e[-1]):
        idx = np.where(v == e[-1], len(e) - 2, idx)
    return np.where((idx >= 0) & (idx < len(e) - 1) & ~np.isnan(v), idx, -1)


def _labels(edges: Sequence[float], unit: str = "") -> list[str]:
    def fmt(x: float) -> str:
        return "inf" if math.isinf(x) else f"{x:g}"

    out = []
    for k in range(len(edges) - 1):
        lo, hi = edges[k], edges[k + 1]
        closing = "]" if k == len(edges) - 2 and math.isfinite(hi) else ")"
        out.append(f"[{fmt(lo)}, {fmt(hi)}{closing}{unit}")
    return out


def working_point_cuts(muon_cuts: Mapping[str, Any], quality_id: str, max_rel_iso: float) -> dict[str, Any]:
    """The channel's muon cuts with ``quality_id`` and ``max_rel_iso`` replaced by the working point's."""
    cuts = {k: v for k, v in muon_cuts.items() if k not in ("quality_id", "max_rel_iso")}
    cuts.update(quality_id=quality_id, max_rel_iso=max_rel_iso)
    return cuts


# -- entries -------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ValidationEntry:
    """One category, bin or working point: its size and, if it has at least :data:`MIN_PAIRS` pairs, its fit.

    ``status`` is ``"fitted"``, ``"insufficient"`` (fewer than
    :data:`MIN_PAIRS` pairs in the fit range: not fitted) or ``"failed"``
    (the fit raised :class:`~cmsopen.fitting.FitError`; ``reason`` says why).
    ``delta`` is position - inclusive position (GeV) and ``delta_sigma`` that
    difference over sqrt(error^2 + inclusive error^2). Because the entry is a
    subset of (or overlaps) the inclusive sample the two errors are
    correlated, so this combined error overstates the uncertainty of the
    difference: delta_sigma is a conservative consistency measure, not a
    significance.

    ``scale_factor`` is S = max(1, sqrt(chi2/ndf)) of the entry's own fit and
    ``error_scaled`` = error * S (dev/validation_plan.md, prompt 10 addendum).
    When chi2/ndf exceeds 1 the line shape does not describe the sub-sample
    perfectly and the curvature error understates the uncertainty of the
    position; scaling by sqrt(chi2/ndf) (the PDG's scale factor) widens it
    accordingly, and never narrows it. ``delta_sigma_scaled`` is delta over the
    combined scaled errors; the raw ``error`` and ``delta_sigma`` are kept.
    """

    study: str
    label: str
    n_pairs: int
    status: str
    model: str
    position: float | None = None
    error: float | None = None
    resolution: float | None = None
    resolution_error: float | None = None
    chi2_ndf: float | None = None
    signal_yield: float | None = None
    yields_reliable: bool | None = None
    delta: float | None = None
    delta_sigma: float | None = None
    reason: str = ""
    scale_factor: float | None = None
    error_scaled: float | None = None
    delta_sigma_scaled: float | None = None

    @property
    def fitted(self) -> bool:
        """True if the entry was fitted successfully."""
        return self.status == "fitted"

    @property
    def status_text(self) -> str:
        """``"fitted"``, ``"insufficient statistics (n = ...)"`` or ``"fit failed: ..."``."""
        if self.status == "insufficient":
            return f"insufficient statistics (n = {self.n_pairs:,})"
        if self.status == "failed":
            return f"fit failed: {self.reason}"
        return "fitted"

    def to_dict(self) -> dict[str, Any]:
        """The entry as plain JSON types."""
        d = {k: getattr(self, k) for k in self.__dataclass_fields__}
        d["status_text"] = self.status_text
        return d


def fit_entry(
    masses: Any,
    config: ChannelConfig,
    model: str,
    study: str,
    label: str,
    inclusive: ValidationEntry | None = None,
) -> ValidationEntry:
    """Histogram ``masses`` as the channel does and fit them with ``model``, or report too few pairs.

    The entry is fitted only if at least :data:`MIN_PAIRS` masses lie in the
    channel's fit range; otherwise it is returned with status
    ``"insufficient"`` and no fit is attempted. The histogram, fit range,
    polynomial degree, natural width and Crystal Ball exponent are the
    channel's.
    """
    m = np.asarray(masses, dtype=np.float64)
    lo, hi = config.fit_range
    n_pairs = int(np.sum((m >= lo) & (m < hi)))
    if n_pairs < MIN_PAIRS:
        return ValidationEntry(study, label, n_pairs, "insufficient", model)
    hist = make_histogram(m, bins=config.bins, range=config.mass_range)
    try:
        fit = fit_mass_peak(
            hist,
            model=model,
            fit_range=config.fit_range,
            poly_degree=config.poly_degree,
            natural_width=pdg_mass_width(config.resonance)[2],
            cb_n=config.cb_n,
        )
    except FitError as exc:
        return ValidationEntry(study, label, n_pairs, "failed", model, reason=str(exc))
    return _entry_from_fit(fit, study, label, n_pairs, inclusive)


def scale_factor(chi2_ndf: float) -> float:
    """The error scale factor S = max(1, sqrt(chi2/ndf)): never below 1 (dev/validation_plan.md, prompt 10)."""
    return max(1.0, math.sqrt(chi2_ndf)) if math.isfinite(chi2_ndf) and chi2_ndf > 0 else 1.0


def _entry_from_fit(
    fit: FitResult, study: str, label: str, n_pairs: int, inclusive: ValidationEntry | None
) -> ValidationEntry:
    pos, err = fit.peak_position
    res, res_err = fit.resolution
    scale = scale_factor(fit.chi2_ndf)
    delta = delta_sigma = delta_sigma_scaled = None
    if inclusive is not None and inclusive.fitted:
        delta = pos - _num(inclusive.position)
        delta_sigma = delta / math.hypot(err, _num(inclusive.error))
        delta_sigma_scaled = delta / math.hypot(err * scale, _num(inclusive.error_scaled))
    return ValidationEntry(
        study,
        label,
        n_pairs,
        "fitted",
        fit.model_name,
        position=pos,
        error=err,
        resolution=res,
        resolution_error=res_err,
        chi2_ndf=fit.chi2_ndf,
        signal_yield=fit.signal_yield[0],
        yields_reliable=fit.yields_reliable,
        delta=delta,
        delta_sigma=delta_sigma,
        scale_factor=scale,
        error_scaled=err * scale,
        delta_sigma_scaled=delta_sigma_scaled,
    )


# -- the systematics summary ----------------------------------------------------------------------------------------


@dataclass(frozen=True)
class SystematicsSummary:
    """Measured offsets and spreads for one channel (dev/validation_plan.md); none is a target or an error bar.

    Attributes
    ----------
    model, validation_model : str
        The headline model (the channel default) and the validation model
        that fitted the scans (dev/validation_plan.md, prompt 8 addendum).
    pdg_offset, pdg_offset_error : float
        Headline inclusive position - PDG mass (GeV) and the statistical
        error; the headline fit uses the channel default ``model``.
    pdg_offset_error_scaled : float or None
        The same error times max(1, sqrt(chi2/ndf)) of the headline fit.
    models : tuple of dict
        voigt_poly, cb_bw_exp, cb_bw_poly2, cb2_bw_exp and cb2_bw_poly2 on the inclusive sample:
        position, error, chi2/ndf, and ``eligible`` by the model-choice
        criteria (converged, no parameter on a bound, background positive).
    model_spread : float or None
        max - min of the eligible models' positions (None if fewer than two).
    fit_choice_rows, fit_choice_failed : tuples
        The headline model over the channel's fit-range x bin-width grid.
    fit_choice_spread, fit_choice_std : float or None
    background_variation : dict
        The headline model's signal with the other background, and its
        difference to the headline position.
    category_spread, category_max_delta_sigma : float or None
        From here on, quantities of the scans (fitted with the validation
        model). max - min of the fitted BB/BE/EE positions, and the largest
        |delta_sigma| among them.
    charge_differences : tuple of dict
        Per phi or eta bin where both charges are fitted: m(mu+) - m(mu-)
        and its combined error.
    charge_max_difference, charge_weighted_mean, charge_weighted_mean_error : float or None
    category_max_delta_sigma_scaled, charge_weighted_mean_scaled, charge_weighted_mean_error_scaled : float or None
        The same with the scaled errors (each charge difference also carries
        ``error_scaled``).
    working_point_spread : float or None
        max - min of the fitted working-point positions.
    """

    channel: str
    model: str
    pdg_particle: str
    pdg_mass: float
    pdg_offset: float | None
    pdg_offset_error: float | None
    models: tuple[dict[str, Any], ...]
    model_spread: float | None
    fit_choice_rows: tuple[dict[str, Any], ...]
    fit_choice_failed: tuple[dict[str, Any], ...]
    fit_choice_spread: float | None
    fit_choice_std: float | None
    background_variation: dict[str, Any]
    category_spread: float | None
    category_max_delta_sigma: float | None
    charge_differences: tuple[dict[str, Any], ...]
    charge_max_difference: float | None
    charge_weighted_mean: float | None
    charge_weighted_mean_error: float | None
    working_point_spread: float | None
    n_insufficient: int = 0
    n_failed: int = 0
    validation_model: str | None = None
    pdg_offset_error_scaled: float | None = None
    category_max_delta_sigma_scaled: float | None = None
    charge_weighted_mean_scaled: float | None = None
    charge_weighted_mean_error_scaled: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """The summary as plain JSON types."""
        from cmsopen.pipeline import _jsonable

        return dict(_jsonable({k: getattr(self, k) for k in self.__dataclass_fields__}))

    def table(self) -> str:
        """A plain-text table of every quantity, each labelled as measured."""

        def gev(x: float | None, digits: int = 4) -> str:
            return "n/a" if x is None else f"{x:+.{digits}f} GeV"

        scans = self.validation_model or self.model
        lines = [
            f"Systematics summary ({self.channel}, headline model {self.model}, validation scans {scans}); "
            "all values measured, no targets"
        ]
        if self.pdg_offset is not None:
            lines.append(
                f"  offset from PDG {self.pdg_particle} mass ({self.pdg_mass:.4f} GeV): {gev(self.pdg_offset)} "
                f"+- {self.pdg_offset_error:.4f} (stat.)"
                + (
                    ""
                    if self.pdg_offset_error_scaled is None
                    else f", scaled +- {self.pdg_offset_error_scaled:.4f} (stat. x max(1, sqrt(chi2/ndf)))"
                )
            )
        lines.append("  fit choices, model (inclusive sample):")
        for row in self.models:
            if row["status"] == "fitted":
                lines.append(
                    f"    {row['model']:<12} {'eligible' if row['eligible'] else 'not eligible':<13} "
                    f"{row['position']:.4f} +- {row['error']:.4f} GeV, chi2/ndf {row['chi2_ndf']:.3f}"
                    + (f"  ({row['why_not']})" if row["why_not"] else "")
                )
            else:
                lines.append(f"    {row['model']:<12} not eligible  fit failed: {row['reason']}")
        lines.append(f"    spread of the eligible models (max - min): {gev(self.model_spread)}")
        lines.append(
            f"  fit choices, range x bin width ({len(self.fit_choice_rows)} fits, "
            f"{len(self.fit_choice_failed)} failed): max - min {gev(self.fit_choice_spread)}, "
            f"std {gev(self.fit_choice_std)}"
        )
        bv = self.background_variation
        if bv.get("status") == "fitted":
            lines.append(f"  background variation ({bv['model']}): {gev(bv['difference'])} relative to the headline")
        else:
            lines.append(f"  background variation ({bv.get('model')}): {bv.get('reason', 'not available')}")
        lines.append(f"  from the validation scans ({scans}):")
        lines.append(
            f"  categories BB/BE/EE: max - min {gev(self.category_spread)}, largest |delta|/sigma "
            f"{'n/a' if self.category_max_delta_sigma is None else f'{self.category_max_delta_sigma:.2f}'}"
            + (
                ""
                if self.category_max_delta_sigma_scaled is None
                else f" (scaled errors: {self.category_max_delta_sigma_scaled:.2f})"
            )
        )
        lines.append("  mu+ minus mu- (bins where both charges are fitted):")
        for d in self.charge_differences:
            lines.append(
                f"    {d['binning']} {d['bin']}: {gev(d['difference'])} +- {d['error']:.4f}"
                + (f" (scaled +- {d['error_scaled']:.4f})" if d.get("error_scaled") is not None else "")
            )
        if not self.charge_differences:
            lines.append("    none (no bin has both charges fitted)")
        lines.append(
            f"    largest |difference| {gev(self.charge_max_difference)}; weighted mean "
            + (
                "n/a"
                if self.charge_weighted_mean is None
                else f"{gev(self.charge_weighted_mean)} +- {self.charge_weighted_mean_error:.4f}"
            )
            + (
                ""
                if self.charge_weighted_mean_scaled is None
                else f"; with scaled errors {gev(self.charge_weighted_mean_scaled)} "
                f"+- {self.charge_weighted_mean_error_scaled:.4f}"
            )
        )
        lines.append(f"  working points: max - min {gev(self.working_point_spread)}")
        lines.append(f"  entries with insufficient statistics: {self.n_insufficient}; failed fits: {self.n_failed}")
        return "\n".join(lines)


def _num(value: float | None) -> float:
    """A fitted number (callers check ``ValidationEntry.fitted`` first)."""
    if value is None:
        raise ValueError("this entry has no fitted value")
    return float(value)


def _spread(values: Sequence[float]) -> float | None:
    return float(max(values) - min(values)) if len(values) >= 2 else None


def systematics_summary(
    config: ChannelConfig,
    model: str,
    masses: Any,
    inclusive: ValidationEntry,
    entries: Sequence[ValidationEntry],
    headline: ValidationEntry | None = None,
) -> SystematicsSummary:
    """Collect the measured offsets and spreads of dev/validation_plan.md for one channel.

    ``masses`` are all chosen-pair masses (the inclusive sample), ``model``
    the headline model (the channel default) and ``headline`` the inclusive
    fit with it, ``inclusive`` the inclusive reference fitted with the
    validation model and ``entries`` the category, bin and working-point
    entries from :func:`run_validation`, fitted with that same validation
    model (``headline`` defaults to ``inclusive``: one model for both).
    The offset from the PDG mass is the headline's. The fit-choice part refits the
    inclusive masses: the models of the model-choice rule and its Amendment 2
    mixtures (eligibility as there), the channel's fit-range x bin-width grid with ``model``, and
    ``model`` with the other background (cb_bw_exp <-> cb_bw_poly2; one
    polynomial degree more for the polynomial models).
    """
    m = np.asarray(masses, dtype=np.float64)
    width = pdg_mass_width(config.resonance)[2]
    hist = make_histogram(m, bins=config.bins, range=config.mass_range)
    common: dict[str, Any] = {"fit_range": config.fit_range, "poly_degree": config.poly_degree, "natural_width": width}

    head = inclusive if headline is None else headline
    pdg_mass = pdg_mass_width(config.resonance)[0]
    offset = offset_err = None
    if head.fitted:
        offset, offset_err = _num(head.position) - pdg_mass, head.error

    models: list[dict[str, Any]] = []
    for name in COMPARED_MODELS:
        try:
            fit = fit_mass_peak(hist, model=name, cb_n=config.cb_n, **common)
        except FitError as exc:
            models.append({"model": name, "status": "failed", "eligible": False, "reason": str(exc)})
            continue
        why = [f"parameter on a bound: {fit.on_bound}"] if fit.on_bound else []
        why += [] if fit.yields_reliable else ["background not positive over the fit range"]
        pos, err = fit.peak_position
        models.append(
            {
                "model": name,
                "status": "fitted",
                "eligible": not why,
                "why_not": "; ".join(why),
                "position": pos,
                "error": err,
                "chi2_ndf": fit.chi2_ndf,
            }
        )
    eligible_positions = [r["position"] for r in models if r["eligible"]]

    stab = fit_stability(
        m,
        fit_ranges=config.stability_fit_ranges or (config.fit_range,),
        bin_widths=config.stability_bin_widths or ((config.mass_range[1] - config.mass_range[0]) / config.bins,),
        poly_degrees=(config.poly_degree,),
        models=(model,),
        hist_range=config.mass_range,
        natural_width=width,
        cb_n=config.cb_n,
    )
    stab_positions = [r["mass"] for r in stab.rows]

    other = {"cb_bw_exp": "cb_bw_poly2", "cb_bw_poly2": "cb_bw_exp", "cb2_bw_exp": "cb2_bw_poly2",
             "cb2_bw_poly2": "cb2_bw_exp", "cb3_bw_exp": "cb3_bw_poly2", "cb3_bw_poly2": "cb3_bw_exp"}.get(model, model)
    fixed_background = model in (*CB_MODELS, *MIXTURE_MODELS, *THREE_RES_MODELS)
    degree = config.poly_degree if fixed_background else config.poly_degree + 1
    variation: dict[str, Any] = {"model": other if fixed_background else f"{model}, degree {degree}"}
    try:
        alt = fit_mass_peak(hist, model=other, cb_n=config.cb_n, **{**common, "poly_degree": degree})
        variation.update(status="fitted", position=alt.peak_position[0])
        if head.fitted:
            variation["difference"] = alt.peak_position[0] - _num(head.position)
    except FitError as exc:
        variation.update(status="failed", reason=f"fit failed: {exc}")

    regions = [e for e in entries if e.study == "region" and e.fitted]
    by_key = {(e.study, e.label): e for e in entries}
    differences: list[dict[str, Any]] = []
    for binning, labels in (("phi", PHI_LABELS), ("eta", tuple(_labels(ETA_EDGES)))):
        for label in labels:
            plus, minus = by_key.get((f"{binning}(mu+)", label)), by_key.get((f"{binning}(mu-)", label))
            if plus is not None and minus is not None and plus.fitted and minus.fitted:
                differences.append(
                    {
                        "binning": binning,
                        "bin": label,
                        "difference": _num(plus.position) - _num(minus.position),
                        "error": math.hypot(_num(plus.error), _num(minus.error)),
                        "error_scaled": math.hypot(_num(plus.error_scaled), _num(minus.error_scaled)),
                    }
                )

    def weighted(key: str) -> tuple[float | None, float | None]:
        if not differences:
            return None, None
        w = np.array([1.0 / d[key] ** 2 for d in differences])
        return (float(np.sum(w * np.array([d["difference"] for d in differences])) / w.sum()),
                float(1.0 / math.sqrt(w.sum())))

    mean, mean_err = weighted("error")
    mean_scaled, mean_err_scaled = weighted("error_scaled")
    wps = [_num(e.position) for e in entries if e.study == "working point" and e.fitted]

    return SystematicsSummary(
        channel=config.name,
        model=model,
        pdg_particle=config.resonance,
        pdg_mass=pdg_mass,
        pdg_offset=offset,
        pdg_offset_error=offset_err,
        models=tuple(models),
        model_spread=_spread(eligible_positions),
        fit_choice_rows=tuple({k: v for k, v in r.items() if k != "warnings"} for r in stab.rows),
        fit_choice_failed=tuple(stab.failed),
        fit_choice_spread=_spread(stab_positions),
        fit_choice_std=stab.std if stab_positions else None,
        background_variation=variation,
        category_spread=_spread([_num(e.position) for e in regions]),
        category_max_delta_sigma=max(
            (abs(_num(e.delta_sigma)) for e in regions if e.delta_sigma is not None), default=None
        ),
        charge_differences=tuple(differences),
        charge_max_difference=max((abs(d["difference"]) for d in differences), default=None),
        charge_weighted_mean=mean,
        charge_weighted_mean_error=mean_err,
        working_point_spread=_spread(wps),
        n_insufficient=sum(e.status == "insufficient" for e in entries),
        n_failed=sum(e.status == "failed" for e in entries),
        validation_model=inclusive.model,
        pdg_offset_error_scaled=head.error_scaled if head.fitted else None,
        category_max_delta_sigma_scaled=max(
            (abs(_num(e.delta_sigma_scaled)) for e in regions if e.delta_sigma_scaled is not None), default=None
        ),
        charge_weighted_mean_scaled=mean_scaled,
        charge_weighted_mean_error_scaled=mean_err_scaled,
    )


# -- the whole validation ---------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ValidationResult:
    """Every validation entry of one channel and its :class:`SystematicsSummary`.

    ``model`` is the validation model that fitted the inclusive reference and
    every entry; ``headline_model`` the channel default whose inclusive fit
    gives the headline offset in the summary.
    """

    channel: str
    model: str
    inclusive: ValidationEntry
    entries: tuple[ValidationEntry, ...]
    summary: SystematicsSummary = field(repr=False)
    headline_model: str | None = None

    def study(self, name: str) -> list[ValidationEntry]:
        """The entries of one study (``"region"``, ``"phi(mu+)"``, ..., ``"working point"``)."""
        return [e for e in self.entries if e.study == name]

    def to_dict(self) -> dict[str, Any]:
        """The result as plain JSON types."""
        return {
            "schema": "cmsopen.ValidationResult/1",
            "channel": self.channel,
            "model": self.model,
            "headline_model": self.headline_model or self.model,
            "min_pairs": MIN_PAIRS,
            "inclusive": self.inclusive.to_dict(),
            "entries": [e.to_dict() for e in self.entries],
            "systematics_summary": self.summary.to_dict(),
        }

    def table(self) -> str:
        """Plain-text tables: one row per entry, then the systematics summary."""
        head = (
            f"{'study':<15}{'entry':<22}{'pairs':>8}  {'position [GeV]':>22}{'resolution [GeV]':>22}"
            f"{'chi2/ndf':>10}{'signal':>10}{'delta/sigma':>13}{'S':>7}{'err x S':>11}{'d/s scaled':>12}  status"
        )
        title = (
            f"Validation ({self.channel}; scans and inclusive reference fitted with the validation model "
            f"{self.model}, headline model {self.headline_model or self.model}; at least {MIN_PAIRS:,} pairs per entry)"
        )
        lines = [title, head]
        d = 4 if self.inclusive.position is None or self.inclusive.position < 10 else 3
        for e in (self.inclusive, *self.entries):
            if e.fitted:
                lines.append(
                    f"{e.study:<15}{e.label:<22}{e.n_pairs:>8,}  "
                    f"{f'{e.position:.{d + 1}f} +- {e.error:.{d + 1}f}':>22}"
                    f"{f'{e.resolution:.{d + 1}f} +- {e.resolution_error:.{d + 1}f}':>22}"
                    f"{e.chi2_ndf:>10.3f}{e.signal_yield:>10,.0f}"
                    f"{'' if e.delta_sigma is None else f'{e.delta_sigma:+.2f}':>13}"
                    f"{_num(e.scale_factor):>7.2f}{f'{_num(e.error_scaled):.{d + 1}f}':>11}"
                    f"{'' if e.delta_sigma_scaled is None else f'{e.delta_sigma_scaled:+.2f}':>12}  "
                    + ("fitted" if e.yields_reliable else "fitted (yields not reliable)")
                )
            else:
                lines.append(f"{e.study:<15}{e.label:<22}{e.n_pairs:>8,}  {'':>107}  {e.status_text}")
        lines.append(
            "delta/sigma = (entry - inclusive) / sqrt(err^2 + err_incl^2); the samples overlap, so this overstates "
            "the uncertainty of the difference"
        )
        lines.append(
            "S = max(1, sqrt(chi2/ndf)) of the entry's fit; err x S = scaled statistical error; d/s scaled = "
            "(entry - inclusive) / sqrt((err S)^2 + (err_incl S_incl)^2) (dev/validation_plan.md, prompt 10)"
        )
        lines.append("")
        lines.append(self.summary.table())
        return "\n".join(lines)


def run_validation(
    config: ChannelConfig,
    model: str,
    pairs: Mapping[str, np.ndarray],
    working_points: Mapping[tuple[str, float], np.ndarray],
    pt_edges: Sequence[float] | None = None,
    validation_model: str | None = None,
) -> ValidationResult:
    """Fit every pre-registered category, bin and working point of one channel and summarise the systematics.

    ``model`` is the headline model (the channel default). The scans and the
    inclusive reference their differences are taken to are fitted with
    ``validation_model`` (default: ``model``). The registered channels'
    defaults are resolution mixtures, whose second core cannot be
    identified in a sub-sample of nearly one resolution (a barrel-only or a
    narrow pT bin); the validation model is the single-resolution line shape
    with the same background, so that each sub-sample is described by a
    model it can determine (dev/validation_plan.md, prompt 8 addendum).

    ``pairs`` holds, per chosen pair, ``mass``, ``eta_plus``, ``eta_minus``,
    ``phi_plus``, ``phi_minus``, ``pt_sublead`` and ``npv`` (PV_npvsGood);
    ``working_points`` the masses of the reselected sample for each
    (quality_id, max_rel_iso). ``pt_edges`` default to :data:`PT_EDGES` for
    the channel; a channel without registered edges has no pT study.
    """
    missing = [k for k in PAIR_FIELDS if k not in pairs]
    if missing:
        raise ValueError(f"pairs lacks {missing}")
    mass = np.asarray(pairs["mass"], dtype=np.float64)
    scan_model = model if validation_model is None else validation_model
    inclusive = fit_entry(mass, config, scan_model, "inclusive", "all pairs")
    headline = inclusive if scan_model == model else fit_entry(mass, config, model, "headline", "all pairs")

    def add(study: str, labels: Sequence[str], index: np.ndarray) -> None:
        for k, label in enumerate(labels):
            entries.append(fit_entry(mass[index == k], config, scan_model, study, label, inclusive))

    entries: list[ValidationEntry] = []
    regions = classify_regions(pairs["eta_plus"], pairs["eta_minus"])
    add("region", REGIONS, np.searchsorted(np.asarray(REGIONS), regions))
    for charge in ("plus", "minus"):
        sign = "+" if charge == "plus" else "-"
        add(f"phi(mu{sign})", PHI_LABELS, bin_index(pairs[f"phi_{charge}"], PHI_EDGES))
    for charge in ("plus", "minus"):
        sign = "+" if charge == "plus" else "-"
        add(f"eta(mu{sign})", _labels(ETA_EDGES), bin_index(pairs[f"eta_{charge}"], ETA_EDGES))
    edges = pt_edges if pt_edges is not None else PT_EDGES.get(config.name)
    if edges is not None:
        add("pT(sublead)", _labels(edges, " GeV"), bin_index(pairs["pt_sublead"], edges))
    add("PV_npvsGood", _labels(PILEUP_EDGES), bin_index(pairs["npv"], PILEUP_EDGES))
    for (qid, iso), wp_masses in working_points.items():
        entries.append(
            fit_entry(wp_masses, config, scan_model, "working point", f"{qid}, iso < {iso:g}", inclusive)
        )
    summary = systematics_summary(config, model, mass, inclusive, entries, headline)
    return ValidationResult(config.name, scan_model, inclusive, tuple(entries), summary, model)
