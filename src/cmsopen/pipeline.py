"""Layer 8: the end-to-end analysis, from NanoAOD files to a fitted resonance peak.

The measurement, in the order a physicist would explain it
---------------------------------------------------------
1. Select clean muons. A collision record contains many muon candidates,
   most of them soft muons from hadron decays or badly measured tracks.
   Kinematic, identification and isolation cuts (Layer 3) keep the
   well-measured muons that a resonance decay produces.
2. Require the trigger. Only events accepted by a trigger were recorded,
   and a dataset is the union of many trigger paths. Requiring specific,
   well-understood paths gives a sample whose selection can be described.
3. Require two muons and form opposite-sign pairs. A neutral resonance
   (Z, J/psi) decays to a mu+ mu- pair, so the candidates are opposite-sign
   pairs (Layer 4). When an event has several candidates, one is chosen by
   a rule that does not look at the mass, so no peak is manufactured.
4. Compute the invariant mass. The summed four-momentum of the two muons
   is the parent's four-momentum, and its Lorentz-invariant length is the
   parent's mass (Layer 5).
5. Fit signal plus background. The mass spectrum is a peak on a smooth
   continuum; a peak model plus a polynomial background is fitted to the
   histogram (Layer 6). Two peak models are fitted, a Gaussian and a Voigt
   (Breit-Wigner of the known natural width convolved with a Gaussian
   resolution): the difference between them shows how much the result
   depends on the assumed line shape, and the stability scan refits under
   many reasonable fit choices to show how much it depends on those.
6. Compare with the PDG value and state the systematic effects. The fitted
   peak position is compared with the world average read from the
   ``particle`` package. Its uncertainty is statistical only. A simple
   analysis of uncalibrated open data is expected to be offset from the PDG
   value by effects this uncertainty does not include: the muon momentum
   scale is not calibrated, final-state radiation pulls events below the
   peak, and a fitted peak position is not the PDG pole mass. The offset is
   therefore reported with that caveat and never as an agreement or
   disagreement with the PDG.

Files are read in chunks of events, so memory stays bounded however many
files are processed. Per-event results (cutflow counts, pair masses) from
different chunks and files are independent and are combined exactly.
Nothing loops over events in Python.
"""

from __future__ import annotations

import json
import math
import platform
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, fields
from importlib import metadata
from pathlib import Path
from types import MappingProxyType
from typing import Any, cast

import awkward as ak
import numpy as np

from cmsopen.combinatorics import best_pair, opposite_sign_pairs, same_sign_pairs
from cmsopen.fitting import (
    MODELS,
    STABILITY_MODELS,
    FitError,
    FitResult,
    MassHistogram,
    PdgComparison,
    StabilityResult,
    compare_to_pdg,
    fit_mass_peak,
    fit_stability,
    make_histogram,
    pdg_latex_name,
    pdg_mass_width,
)
from cmsopen.ingestion import DIMUON_TRIGGERS_2012, NotNanoAODError, open_events
from cmsopen.selection import MUON_ID_WORKING_POINTS, ZMUMU_MUON_CUTS, CutFlow, select_muons

__all__ = [
    "CHANNELS",
    "PROTECTED_DIRS",
    "PROTECTED_FILES",
    "AnalysisError",
    "AnalysisResult",
    "ChannelConfig",
    "analyze",
    "register_channel",
]

# The same rules as scripts/check_docs_frozen.py ("Documentation freeze" in CLAUDE.md).
PROTECTED_FILES = ("README.md", "DATA.md", "LICENSE", "CITATION.cff", "results/production.json")
PROTECTED_DIRS = ("docs/", "notebooks/")

SYSTEMATICS_SENTENCE = (
    "Offsets of this size are expected to be dominated by systematic effects that the statistical "
    "uncertainty does not include (no muon momentum-scale calibration, final-state radiation)."
)


class AnalysisError(RuntimeError):
    """Raised when an analysis cannot produce a result: bad input, no surviving events, or no fit.

    The message says what went wrong in terms of the analysis (which file,
    which branch, which cut), so a command-line user sees a clear sentence
    rather than a traceback.
    """


# -- channels -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class ChannelConfig:
    """Everything that defines one dimuon resonance analysis.

    Attributes
    ----------
    name : str
        Registry key, e.g. ``"Z_mumu"``.
    description : str
        One line for printouts.
    muon_cuts : mapping
        Keyword arguments of :meth:`cmsopen.selection.Selection.apply`
        (``min_pt``, ``max_eta``, ``quality_id``, ``max_rel_iso``, ...), in
        the order they are applied.
    triggers : tuple of str
        HLT paths; an event is kept if ANY fired. Empty: no trigger
        requirement.
    mass_range : (float, float)
        Histogram range in GeV.
    bins : int
        Number of equal histogram bins over ``mass_range``.
    fit_range : (float, float)
        Default fit window in GeV.
    poly_degree : int
        Degree of the polynomial background.
    resonance : str
        ``particle`` package name of the resonance, for the PDG comparison
        and the natural width of the Voigt model.
    cb_n : float
        The fixed tail exponent n of the Crystal Ball in the ``cb_bw_*``
        models. n and alpha are strongly correlated (a tail that starts a
        little later and falls a little faster looks almost the same), so
        fitting both is unstable; n is chosen once per channel on the
        development file (dev/model_choice.md) and kept fixed.
    resonance_label : str, optional
        The resonance in matplotlib mathtext (no dollar signs), used in the
        figures' "PDG m_..." and "Gamma_..." labels, e.g. ``"Z"`` or
        ``r"J/\\psi"``. If None, the ``particle`` package's LaTeX name is used.
    candidate_strategy : str
        :func:`cmsopen.combinatorics.best_pair` strategy (mass-blind ones
        only: ``"highest_pt_sum"`` or ``"leading"``).
    stability_fit_ranges, stability_bin_widths : tuples
        The fit-choice grid of :func:`cmsopen.fitting.fit_stability`.
    min_pairs : int
        Fewest candidate pairs in the fit range for which a fit is attempted.
    """

    name: str
    description: str
    muon_cuts: Mapping[str, Any]
    triggers: tuple[str, ...]
    mass_range: tuple[float, float]
    bins: int
    fit_range: tuple[float, float]
    poly_degree: int
    resonance: str
    candidate_strategy: str = "highest_pt_sum"
    stability_fit_ranges: tuple[tuple[float, float], ...] = ()
    stability_bin_widths: tuple[float, ...] = ()
    min_pairs: int = 100
    resonance_label: str | None = None
    cb_n: float = 3.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "muon_cuts", MappingProxyType(dict(self.muon_cuts)))
        object.__setattr__(self, "triggers", tuple(self.triggers))
        if self.candidate_strategy not in ("highest_pt_sum", "leading"):
            raise ValueError(f"candidate_strategy must be mass-blind ('highest_pt_sum' or 'leading'), "
                             f"got {self.candidate_strategy!r}")
        lo, hi = self.mass_range
        flo, fhi = self.fit_range
        if not (lo < hi and lo <= flo < fhi <= hi):
            raise ValueError(
                f"need mass_range low < high containing fit_range; got {self.mass_range}, {self.fit_range}"
            )
        if self.bins < 1 or self.poly_degree < 0:
            raise ValueError("bins must be >= 1 and poly_degree >= 0")
        if not (math.isfinite(self.cb_n) and self.cb_n > 0):
            raise ValueError(f"cb_n must be a positive number, got {self.cb_n!r}")

    def to_dict(self) -> dict[str, Any]:
        """The configuration as plain JSON types."""
        d = {f.name: getattr(self, f.name) for f in fields(self)}
        d["muon_cuts"] = dict(self.muon_cuts)
        return _jsonable(d)


CHANNELS: dict[str, ChannelConfig] = {}
"""Registered channels by name; add your own with :func:`register_channel`."""


def register_channel(config: ChannelConfig, replace: bool = False) -> ChannelConfig:
    """Add a channel to :data:`CHANNELS` so ``analyze(path, channel=config.name)`` can use it.

    Raises ValueError if the name is taken (unless ``replace=True``).
    """
    if not isinstance(config, ChannelConfig):
        raise TypeError(f"register_channel() needs a ChannelConfig, got {type(config).__name__}")
    if config.name in CHANNELS and not replace:
        raise ValueError(f"channel {config.name!r} is already registered; pass replace=True to overwrite it")
    CHANNELS[config.name] = config
    return config


register_channel(
    ChannelConfig(
        name="Z_mumu",
        description="Z -> mu+ mu-: tight isolated muons, dimuon trigger, 60-120 GeV",
        muon_cuts=ZMUMU_MUON_CUTS,
        triggers=DIMUON_TRIGGERS_2012,
        mass_range=(60.0, 120.0),
        bins=60,
        fit_range=(70.0, 110.0),
        poly_degree=2,
        resonance="Z",
        resonance_label="Z",
        candidate_strategy="highest_pt_sum",
        stability_fit_ranges=((70.0, 110.0), (75.0, 105.0), (80.0, 100.0)),
        stability_bin_widths=(0.5, 1.0, 2.0),
    )
)

register_channel(
    ChannelConfig(
        name="Jpsi_mumu",
        description="J/psi -> mu+ mu-: soft-ID muons above 3 GeV, J/psi dimuon triggers, 2.6-3.6 GeV",
        muon_cuts={"min_pt": 3.0, "max_eta": 2.4, "quality_id": "soft"},
        triggers=("HLT_Dimuon8_Jpsi", "HLT_Dimuon10_Jpsi"),
        mass_range=(2.6, 3.6),
        bins=50,
        fit_range=(2.8, 3.4),
        poly_degree=2,
        resonance="J/psi",
        resonance_label=r"J/\psi",
        candidate_strategy="highest_pt_sum",
        stability_fit_ranges=((2.8, 3.4), (2.85, 3.35), (2.9, 3.3)),
        stability_bin_widths=(0.01, 0.02, 0.04),
    )
)


def resonance_label(config: ChannelConfig) -> str:
    """The resonance of a channel in mathtext for figure labels: ``config.resonance_label``, or else the
    ``particle`` package's LaTeX name (e.g. ``Z^{0}``)."""
    return config.resonance_label or pdg_latex_name(config.resonance)


# The second fit reported next to the primary one, to show how the result depends on the line shape.
_ALTERNATE_MODEL = {"gauss_poly": "voigt_poly", "voigt_poly": "gauss_poly", "cb_bw_exp": "voigt_poly",
                    "cb_bw_poly2": "voigt_poly"}


def _channel(channel: str, config: ChannelConfig | None) -> ChannelConfig:
    if config is not None:
        if not isinstance(config, ChannelConfig):
            raise TypeError(f"config must be a ChannelConfig, got {type(config).__name__}")
        return config
    if channel not in CHANNELS:
        raise ValueError(f"unknown channel {channel!r}; valid channels: {', '.join(sorted(CHANNELS))}")
    return CHANNELS[channel]


# -- protected paths ------------------------------------------------------------------------------


def _git_root(path: Path) -> Path | None:
    for parent in (path, *path.parents):
        if (parent / ".git").exists():
            return parent
    return None


def _protected_reason(target: Path) -> str | None:
    """Why ``target`` (a directory to write into, or a file) is protected documentation, or None."""
    target = target.expanduser().resolve()
    roots = {r for r in (_git_root(target), _git_root(Path(__file__).resolve())) if r is not None}
    for root in roots:
        try:
            rel = target.relative_to(root).as_posix()
        except ValueError:
            continue
        if rel in PROTECTED_FILES:
            return f"{rel} is a protected file"
        for d in PROTECTED_DIRS:
            if rel == d.rstrip("/") or rel.startswith(d):
                return f"{rel} is inside the protected directory {d}"
    return None


def _refuse_protected(target: Path) -> None:
    reason = _protected_reason(target)
    if reason:
        raise AnalysisError(
            f"refusing to write to {target}: {reason} (see 'Documentation freeze' in CLAUDE.md); "
            "choose another output directory"
        )


# -- the result --------------------------------------------------------------------------------------


def _jsonable(obj: Any) -> Any:
    """Convert to plain JSON types; non-finite floats become None."""
    if isinstance(obj, Mapping):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return _jsonable(obj.tolist())
    if isinstance(obj, (bool, np.bool_)):
        return bool(obj)
    if isinstance(obj, (int, np.integer)):
        return int(obj)
    if isinstance(obj, (float, np.floating)):
        return float(obj) if math.isfinite(obj) else None
    if obj is None or isinstance(obj, str):
        return obj
    return str(obj)


def _fit_dict(fit: FitResult | None) -> dict[str, Any] | None:
    if fit is None:
        return None
    m, me = fit.peak_position
    s, se = fit.resolution
    d: dict[str, Any] = {
        "model": fit.model_name,
        "fit_range_gev": list(fit.fit_range),
        "poly_degree": fit.poly_degree,
        "background": fit.background_label,
        "cb_n": fit.cb_n,
        "parameters": {k: {"value": v, "error": e} for k, (v, e) in fit.parameters.items()},
        "peak_position_gev": m,
        "peak_position_stat_error_gev": me,
        "resolution_gev": s,
        "resolution_error_gev": se,
        "natural_width_gev": None if fit.gamma is None else 2 * fit.gamma,
        "chi2": fit.chi2,
        "ndf": fit.ndf,
        "chi2_ndf": fit.chi2_ndf,
        "p_value": fit.p_value,
        "n_entries_in_fit_range": fit.n_entries,
        "yields_reliable": fit.yields_reliable,
        "signal_yield": list(fit.signal_yield) if fit.yields_reliable else None,
        "background_yield": list(fit.background_yield) if fit.yields_reliable else None,
        "warnings": [str(w) for w in fit.warnings],
        "warning_codes": [w.code for w in fit.warnings],
    }
    return _jsonable(d)


def _pdg_dict(c: PdgComparison | None) -> dict[str, Any] | None:
    if c is None:
        return None
    return _jsonable(
        {
            "particle": c.particle,
            "pdg_mass_gev": c.pdg_mass,
            "pdg_mass_error_gev": c.pdg_mass_error,
            "fitted_gev": c.fitted,
            "fitted_stat_error_gev": c.fitted_error,
            "offset_gev": c.difference,
            "offset_percent": 100 * c.relative_difference,
            "pull_statistical_error_only": c.pull,
        }
    )


@dataclass
class AnalysisResult:
    """The outcome of :func:`analyze`.

    Attributes
    ----------
    config : ChannelConfig
    files : list of str
    n_events : int
        Events processed (after ``n_events`` limiting).
    cutflow : CutFlow
        Combined over all chunks and files.
    masses : numpy.ndarray
        Mass (GeV) of the chosen opposite-sign pair of every selected event
        with one, in file and event order.
    same_sign_masses : numpy.ndarray
        Masses of all same-sign pairs in the selected events (background
        control sample).
    n_os_pairs : int
        All opposite-sign candidates before choosing one per event.
    histogram : MassHistogram
    fit : FitResult
        The primary model.
    alternate_fit : FitResult or None
        The other peak model (None if it failed; see ``warnings``).
    pdg : dict
        Model name -> :class:`~cmsopen.fitting.PdgComparison`.
    stability : StabilityResult or None
    figures : dict
        Name -> matplotlib Figure.
    warnings : list of str
    versions : dict
        Package name -> version, for reproducibility.
    """

    config: ChannelConfig
    files: list[str]
    n_events: int
    cutflow: CutFlow
    masses: np.ndarray
    same_sign_masses: np.ndarray
    n_os_pairs: int
    histogram: MassHistogram
    fit: FitResult
    alternate_fit: FitResult | None
    pdg: dict[str, PdgComparison]
    stability: StabilityResult | None
    figures: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    versions: dict[str, str] = field(default_factory=dict)

    # -- text --------------------------------------------------------------------------------

    def _fit_rows(self) -> list[str]:
        rows = [f"  {'model':<12}{'peak [GeV]':>22}{'resolution [GeV]':>22}{'chi2/ndf':>22}{'p-value':>10}  yields"]
        for fit in (self.fit, self.alternate_fit):
            if fit is None:
                continue
            m, me = fit.peak_position
            s, se = fit.resolution
            if fit.yields_reliable:
                sy, sye = fit.signal_yield
                by, bye = fit.background_yield
                yields = f"signal {sy:,.0f} +- {sye:,.0f}, background {by:,.0f} +- {bye:,.0f}"
            else:
                yields = "yields not shown: background not positive"
            rows.append(
                f"  {fit.model_name:<12}{f'{m:.4f} +- {me:.4f}':>22}{f'{s:.4f} +- {se:.4f}':>22}"
                f"{f'{fit.chi2:.1f}/{fit.ndf} = {fit.chi2_ndf:.2f}':>22}{fit.p_value:>10.3g}  {yields}"
            )
        return rows

    def summary(self) -> str:
        """The printed report: inputs, cutflow, pairs, fits, the PDG offset with its caveat, stability, warnings."""
        lines = [f"cmsopen analysis: {self.config.name} ({self.config.description})"]
        lines.append(f"Files ({len(self.files)}):")
        lines += [f"  {f}" for f in self.files]
        lines.append(f"Events processed: {self.n_events:,}")
        lines.append("")
        lines.append("Cutflow:")
        lines.append(str(self.cutflow))
        lines.append("")
        lines.append(
            f"Opposite-sign pair candidates: {self.n_os_pairs:,}; one per event ({self.config.candidate_strategy}): "
            f"{len(self.masses):,}; same-sign pairs: {len(self.same_sign_masses):,}"
        )
        lo, hi = self.fit.fit_range
        lines.append(f"Histogram: {self.histogram!r}; fit range {lo:g}-{hi:g} GeV, {self.fit.n_entries:,} entries")
        lines.append("")
        polynomial_only = all(f is None or f.poly_degree is not None for f in (self.fit, self.alternate_fit))
        lines.append("Fits (signal + polynomial background):" if polynomial_only else "Fits (signal + background):")
        lines += self._fit_rows()
        lines.append("")
        c = self.pdg[self.fit.model_name]
        m, me = self.fit.peak_position
        s, se = self.fit.resolution
        lines.append(f"Peak position ({self.fit.model_name}): {m:.4f} +- {me:.4f} GeV (statistical error only)")
        lines.append(
            f"Resolution: {s:.4f} +- {se:.4f} GeV; "
            f"chi2/ndf = {self.fit.chi2:.1f}/{self.fit.ndf} = {self.fit.chi2_ndf:.2f}"
        )
        lines.append(f"PDG {c.particle} mass (particle package): {c.pdg_mass:.4f} GeV")
        for fit in (self.fit, self.alternate_fit):
            if fit is None:
                continue
            cc = self.pdg[fit.model_name]
            lines.append(
                f"Offset from PDG ({fit.model_name}): {cc.difference:+.4f} GeV "
                f"({100 * cc.relative_difference:+.3f} %), "
                f"pull {cc.pull:+.1f} (statistical error only)"
            )
        lines.append(SYSTEMATICS_SENTENCE)
        if self.stability is not None:
            st = self.stability
            lines.append(
                f"Stability over {st.n_fits} fit choices ({len(st.failed)} failed): peak mean {st.mean:.4f} GeV, "
                f"spread {st.std:.4f} GeV (std), range {st.min:.4f}-{st.max:.4f} GeV (fit-choice spread only)"
            )
        if self.warnings:
            lines.append("")
            lines.append("Warnings:")
            lines += [f"  - {w}" for w in self.warnings]
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """A JSON-serializable summary (no Figure objects, no per-pair arrays)."""
        st = self.stability
        return _jsonable(
            {
                "schema": "cmsopen.AnalysisResult/1",
                "channel": self.config.to_dict(),
                "files": list(self.files),
                "n_events": self.n_events,
                "cutflow": [
                    {
                        k: r[k]
                        for k in (
                            "step",
                            "cut",
                            "name",
                            "params",
                            "level",
                            "n_particles",
                            "n_events_with_particles",
                            "n_events",
                        )
                    }
                    for r in self.cutflow.to_records()
                ],
                "n_os_pairs": self.n_os_pairs,
                "n_chosen_pairs": len(self.masses),
                "n_same_sign_pairs": len(self.same_sign_masses),
                "histogram": {
                    "edges_gev": self.histogram.edges,
                    "counts": self.histogram.counts,
                    "underflow": self.histogram.underflow,
                    "overflow": self.histogram.overflow,
                },
                "fit": _fit_dict(self.fit),
                "alternate_fit": _fit_dict(self.alternate_fit),
                "pdg_comparison": {name: _pdg_dict(c) for name, c in self.pdg.items()},
                "systematics_note": SYSTEMATICS_SENTENCE,
                "stability": None
                if st is None
                else {
                    "rows": [
                        {k: v for k, v in r.items() if k != "warnings"} | {"warnings": [str(w) for w in r["warnings"]]}
                        for r in st.rows
                    ],
                    "failed": st.failed,
                    "mean_gev": st.mean,
                    "std_gev": st.std,
                    "min_gev": st.min,
                    "max_gev": st.max,
                    "label": "fit-choice spread only",
                },
                "warnings": list(self.warnings),
                "versions": dict(self.versions),
            }
        )

    def save(self, directory: str | Path) -> list[Path]:
        """Write figures (png and pdf), summary.txt and summary.json into ``directory``; return the paths.

        The output is deterministic (no timestamps, user names or random
        content), so two runs on the same inputs give byte-identical files.
        Writing into protected documentation (README.md, DATA.md, LICENSE,
        CITATION.cff, results/production.json, docs/, notebooks/) is refused.
        """
        from cmsopen.plotting import save_figure

        directory = Path(directory)
        _refuse_protected(directory)
        directory.mkdir(parents=True, exist_ok=True)
        written: list[Path] = []
        for name, fig in sorted(self.figures.items()):
            written += save_figure(fig, directory / name, formats=("png", "pdf"))
        text = directory / "summary.txt"
        text.write_text(self.summary() + "\n")
        js = directory / "summary.json"
        js.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True, allow_nan=False) + "\n")
        return [*written, text, js]


# -- the analysis -------------------------------------------------------------------------------------


def _muon_fields(cuts: Mapping[str, Any]) -> tuple[str, ...]:
    """Muon branches (without prefix) needed by the cuts, besides the four-momentum and charge."""
    names = ["pt", "eta", "phi", "mass", "charge"]
    for name, value in cuts.items():
        if value is None or value is False:
            continue
        if name == "quality_id":
            names.append(MUON_ID_WORKING_POINTS.get(value, str(value)))
        elif name == "max_rel_iso":
            names.append("pfRelIso04_all")
        elif name == "max_abs_dxy":
            names.append("dxy")
        elif name == "max_abs_dz":
            names.append("dz")
        elif name == "global_muon":
            names += ["isGlobal", "isTracker"]
    return tuple(dict.fromkeys(names))


def _versions() -> dict[str, str]:
    out = {"python": platform.python_version()}
    for pkg in ("cmsopen", "uproot", "awkward", "numpy", "scipy", "particle", "matplotlib"):
        try:
            out[pkg] = metadata.version(pkg)
        except metadata.PackageNotFoundError:
            out[pkg] = "not installed"
    return out


def _survivors(step: Any) -> int:
    return step.n_events if step.level in ("start", "event") else step.n_events_with_particles


def _check_survivors(cutflow: CutFlow) -> None:
    steps = list(cutflow)
    if _survivors(steps[-1]) > 0:
        return
    last_ok = None
    for prev, step in zip(steps, steps[1:], strict=False):
        if _survivors(prev) > 0 and _survivors(step) == 0:
            last_ok, killer = prev, step
            break
    if last_ok is None:
        raise AnalysisError("no events to analyse: the input contains no events")
    raise AnalysisError(
        f"no events survive the selection: {_survivors(last_ok):,} events after '{last_ok.label}' "
        f"(the last cut that kept events), 0 after '{killer.label}'"
    )


@dataclass(frozen=True)
class _Unit:
    """One piece of work: a half-open event range of one file."""

    file_index: int
    chunk_index: int
    path: str
    start: int
    stop: int

    def describe(self) -> str:
        return f"{self.path}, chunk {self.chunk_index} (events {self.start}-{self.stop})"


@dataclass
class _ChunkResult:
    cutflow: CutFlow
    masses: np.ndarray
    same_sign: np.ndarray
    n_os: int


def _open(path: str) -> Any:
    try:
        return open_events(path)
    except FileNotFoundError:
        raise AnalysisError(f"file not found: {path}") from None
    except NotNanoAODError as exc:
        raise AnalysisError(f"{path} is not a usable NanoAOD file: {exc}") from None
    except OSError as exc:
        raise AnalysisError(f"cannot open {path}: {exc}") from None


def _plan(
    files: Sequence[str], config: ChannelConfig, n_events: int | None, chunk_size: int, fields: tuple[str, ...]
) -> tuple[list[_Unit], int]:
    """Split the input into chunks, file by file, after checking every file can be analysed."""
    units: list[_Unit] = []
    n_done = 0
    for i, path in enumerate(files):
        remaining = None if n_events is None else n_events - n_done
        if remaining is not None and remaining <= 0:
            break
        with _open(path) as events:
            n_total = events.n_events if remaining is None else min(remaining, events.n_events)
            missing = [f"Muon_{f}" for f in fields if not events.has_branch(f"Muon_{f}")]
            missing += [t for t in config.triggers if not events.has_branch(t)]
            if missing:
                raise AnalysisError(f"{path} lacks branches needed by channel {config.name!r}: {missing}")
        starts = range(0, n_total, chunk_size) if n_total else [0]  # an empty file still gives a (zero) cutflow
        units += [_Unit(i, j, path, start, min(start + chunk_size, n_total)) for j, start in enumerate(starts)]
        n_done += n_total
    return units, n_done


def _run_chunk(
    events: Any,
    triggers: tuple[str, ...],
    cuts: Mapping[str, Any],
    strategy: str,
    fields: tuple[str, ...],
    start: int,
    stop: int,
) -> _ChunkResult:
    """Selection, trigger, pairing and masses for one event range of an open file (the unit of work)."""
    sel = select_muons(events, fields=fields, entry_start=start, entry_stop=stop)
    if triggers:
        sel = sel.require_trigger(*triggers)
    sel = sel.apply(**cuts).require(2)
    os_pairs = opposite_sign_pairs(sel)
    chosen = best_pair(os_pairs, strategy)
    return _ChunkResult(
        cutflow=sel.cutflow(),
        masses=ak.to_numpy(ak.flatten(chosen.mass)).astype(np.float64),
        same_sign=ak.to_numpy(ak.flatten(same_sign_pairs(sel).mass)).astype(np.float64),
        n_os=os_pairs.n_pairs,
    )


_WORKER_FILE: dict[str, Any] = {}
"""In a worker process: the file it has open (opening a NanoAOD file reads all its branch metadata)."""


def _chunk_worker(
    path: str,
    triggers: tuple[str, ...],
    cuts: dict[str, Any],
    strategy: str,
    fields: tuple[str, ...],
    start: int,
    stop: int,
) -> _ChunkResult:
    """Process-pool entry point: process one chunk, keeping the worker's current file open between chunks.

    Opening a file costs a noticeable fraction of a chunk's processing time,
    so a worker keeps its last file open and reopens only when it is given a
    chunk of a different file. The chunk is processed by exactly the same
    code as in a serial run.
    """
    events = _WORKER_FILE.get(path)
    if events is None:
        for old in _WORKER_FILE.values():
            old.close()
        _WORKER_FILE.clear()
        events = _WORKER_FILE[path] = open_events(path)
    return _run_chunk(events, triggers, cuts, strategy, fields, start, stop)


def _execute(
    units: list[_Unit], config: ChannelConfig, fields: tuple[str, ...], n_workers: int | None
) -> list[_ChunkResult]:
    """Process every unit, serially or in a process pool, and return the results in unit order.

    Results are collected in the fixed order of the units (files in the
    order given, chunks in event order), never in the order workers finish,
    so a parallel run gives exactly the same masses, cutflow and fits as a
    serial one.
    """
    cuts, triggers, strategy = dict(config.muon_cuts), config.triggers, config.candidate_strategy
    results: list[_ChunkResult] = []
    if n_workers is None or n_workers == 1:
        i = 0
        while i < len(units):
            path = units[i].path
            with _open(path) as events:
                while i < len(units) and units[i].path == path:
                    unit = units[i]
                    try:
                        results.append(_run_chunk(events, triggers, cuts, strategy, fields, unit.start, unit.stop))
                    except AnalysisError:
                        raise
                    except Exception as exc:
                        raise AnalysisError(f"{unit.describe()} failed: {type(exc).__name__}: {exc}") from None
                    i += 1
        return results
    from concurrent.futures import ProcessPoolExecutor

    with ProcessPoolExecutor(max_workers=min(n_workers, len(units))) as pool:
        futures = [pool.submit(_chunk_worker, u.path, triggers, cuts, strategy, fields, u.start, u.stop) for u in units]
        for unit, future in zip(units, futures, strict=False):
            try:
                results.append(future.result())
            except Exception as exc:
                pool.shutdown(wait=False, cancel_futures=True)
                raise AnalysisError(f"worker failed on {unit.describe()}: {type(exc).__name__}: {exc}") from None
    return results


def _figures(
    cfg: ChannelConfig, hist: MassHistogram, fit: FitResult, ss_hist: MassHistogram | None, cutflow: CutFlow
) -> dict[str, Any]:
    """The result figures, every label built from the channel's resonance and the PDG values of ``particle``."""
    from cmsopen.plotting import plot_cutflow, plot_mass_spectrum, plot_os_vs_ss

    pdg_mass, _, width, _ = pdg_mass_width(cfg.resonance)
    symbol = resonance_label(cfg)
    figures: dict[str, Any] = {}
    figures["mass_fit"], _ = plot_mass_spectrum(
        hist,
        fit,
        label="CMS Open Data",
        resonance_label=symbol,
        pdg_mass=pdg_mass,
        natural_width=width if fit.gamma is not None else None,
    )
    if ss_hist is not None:
        figures["os_vs_ss"], _ = plot_os_vs_ss(hist, ss_hist, resonance_label=symbol, pdg_mass=pdg_mass)
    figures["cutflow"], _ = plot_cutflow(cutflow)
    return figures


def analyze(
    path: str | Path | Sequence[str | Path],
    channel: str = "Z_mumu",
    *,
    n_events: int | None = None,
    chunk_size: int = 100_000,
    model: str = "voigt_poly",
    fit_range: tuple[float, float] | None = None,
    bins: int | None = None,
    outdir: str | Path | None = None,
    verbose: bool = True,
    stability: bool = True,
    config: ChannelConfig | None = None,
    n_workers: int | None = None,
) -> AnalysisResult:
    """Run the full dimuon resonance analysis on one or more NanoAOD files.

    The chain (see the module docstring for the physics of each step):
    select muons with the channel's cuts after requiring its trigger, keep
    events with at least two selected muons, form opposite-sign pairs and
    choose one per event with a mass-blind rule, compute the invariant
    masses, histogram them, fit signal plus background with both peak
    models (the requested one is the primary result, the other shows the
    line-shape dependence), compare each fitted peak with the PDG value,
    optionally refit over the channel's grid of fit choices, and draw the
    figures.

    Files are processed one after another, each in chunks of
    ``chunk_size`` events, so memory stays bounded; the cutflows of the
    chunks are added exactly (:meth:`CutFlow.combine`) and the masses are
    concatenated in event order, so the result does not depend on the chunk
    size, nor on ``n_workers``.

    Parameters
    ----------
    path : str, Path, or list of them
        Local NanoAOD files or ``https://`` URLs.
    channel : str
        A name in :data:`CHANNELS` (ignored if ``config`` is given).
    n_events : int, optional
        Process at most this many events in total, taking files in order.
    chunk_size : int
        Events per chunk.
    model : {"voigt_poly", "gauss_poly", "cb_bw_exp", "cb_bw_poly2"}
        The primary peak model. The ``cb_bw_*`` models (Breit-Wigner (x)
        Crystal Ball, see :func:`cmsopen.fitting.crystalball_bw`) use the
        channel's fixed ``cb_n``. The other fit reported next to it is
        ``gauss_poly`` for ``voigt_poly`` and ``voigt_poly`` for the rest.
    fit_range : (float, float), optional
        Overrides the channel's fit range (GeV).
    bins : int, optional
        Overrides the channel's number of bins.
    outdir : str or Path, optional
        If given, :meth:`AnalysisResult.save` writes there (protected
        documentation paths are refused).
    verbose : bool
        Print the summary.
    stability : bool
        Run :func:`cmsopen.fitting.fit_stability` over the channel's grid
        (with both Gaussian and Voigt peaks for those primary models, with
        the primary model alone for ``cb_bw_*``).
    config : ChannelConfig, optional
        Use this configuration instead of a registered channel.
    n_workers : int, optional
        None or 1: process the chunks one after another in this process.
        Greater than 1: process them in a pool of that many worker
        processes. The chunks are merged in their fixed file and event order,
        so the result is identical to the serial one. On macOS and Windows
        the workers are started with "spawn", which re-imports the calling
        script: a script that passes ``n_workers`` must put its top-level
        code under ``if __name__ == "__main__":``. Notebook cells and the
        ``cmsopen`` command need nothing extra.

    Raises
    ------
    AnalysisError
        Missing file, a file without the NanoAOD ``Events`` tree, missing
        branches, no events surviving the selection (the message names the
        last cut that kept events), too few pairs, a failed primary fit, or
        an error while processing a chunk (the message names the file and
        the chunk, also when it happened in a worker process).
    ValueError
        Unknown channel (the message lists the valid ones), unknown model,
        or invalid sizes.
    """
    cfg = _channel(channel, config)
    if model not in MODELS:
        raise ValueError(f"model must be one of {MODELS}, got {model!r}")
    if not isinstance(chunk_size, (int, np.integer)) or chunk_size < 1:
        raise ValueError(f"chunk_size must be a positive integer, got {chunk_size!r}")
    if n_workers is not None and (
        isinstance(n_workers, bool) or not isinstance(n_workers, (int, np.integer)) or n_workers < 1
    ):
        raise ValueError(f"n_workers must be a positive integer or None, got {n_workers!r}")
    if n_events is not None and (not isinstance(n_events, (int, np.integer)) or n_events < 1):
        raise ValueError(f"n_events must be a positive integer or None, got {n_events!r}")
    if outdir is not None:
        _refuse_protected(Path(outdir))
    files = [str(path)] if isinstance(path, (str, Path)) else [str(p) for p in path]
    if not files:
        raise ValueError("no input files given")
    frange = cast(tuple[float, float], tuple(fit_range)) if fit_range is not None else cfg.fit_range
    n_bins = bins if bins is not None else cfg.bins
    muon_fields = _muon_fields(cfg.muon_cuts)

    units, n_done = _plan(files, cfg, n_events, chunk_size, muon_fields)
    chunks = _execute(units, cfg, muon_fields, n_workers)
    cutflow = CutFlow.combine([c.cutflow for c in chunks])
    _check_survivors(cutflow)
    masses = np.concatenate([c.masses for c in chunks])
    ss_masses = np.concatenate([c.same_sign for c in chunks])
    n_os = sum(c.n_os for c in chunks)

    in_range = int(np.sum((masses >= frange[0]) & (masses < frange[1])))
    if in_range < cfg.min_pairs:
        raise AnalysisError(
            f"too few pairs to fit: {in_range} opposite-sign pairs in {frange[0]:g}-{frange[1]:g} GeV "
            f"(need at least {cfg.min_pairs}); {len(masses)} pairs in total from {n_done:,} events"
        )
    hist = make_histogram(masses, bins=n_bins, range=cfg.mass_range)
    width = pdg_mass_width(cfg.resonance)[2]
    warnings: list[str] = []
    try:
        fit = fit_mass_peak(
            hist, model=model, fit_range=frange, poly_degree=cfg.poly_degree, natural_width=width, cb_n=cfg.cb_n
        )
    except FitError as exc:
        raise AnalysisError(f"the {model} fit failed: {exc}") from None
    other = _ALTERNATE_MODEL[model]
    try:
        alternate: FitResult | None = fit_mass_peak(
            hist, model=other, fit_range=frange, poly_degree=cfg.poly_degree, natural_width=width, cb_n=cfg.cb_n
        )
    except FitError as exc:
        alternate = None
        warnings.append(f"the alternate {other} fit failed: {exc}")
    for f_ in (fit, alternate):
        if f_ is not None:
            warnings += [f"{f_.model_name}: {w}" for w in f_.warnings]
    pdg = {f_.model_name: compare_to_pdg(f_, cfg.resonance) for f_ in (fit, alternate) if f_ is not None}

    stab = None
    if stability:
        stab = fit_stability(
            masses,
            fit_ranges=cfg.stability_fit_ranges or (frange,),
            bin_widths=cfg.stability_bin_widths or ((cfg.mass_range[1] - cfg.mass_range[0]) / n_bins,),
            hist_range=cfg.mass_range,
            natural_width=width,
            models=STABILITY_MODELS if model in STABILITY_MODELS else (model,),
            cb_n=cfg.cb_n,
        )
        if stab.failed:
            warnings.append(
                f"{len(stab.failed)} of {stab.n_fits} stability fits failed (listed in the stability table)"
            )

    ss_hist = make_histogram(ss_masses, bins=n_bins, range=cfg.mass_range) if len(ss_masses) else None
    figures = _figures(cfg, hist, fit, ss_hist, cutflow)

    result = AnalysisResult(
        config=cfg,
        files=files,
        n_events=n_done,
        cutflow=cutflow,
        masses=masses,
        same_sign_masses=ss_masses,
        n_os_pairs=n_os,
        histogram=hist,
        fit=fit,
        alternate_fit=alternate,
        pdg=pdg,
        stability=stab,
        figures=figures,
        warnings=warnings,
        versions=_versions(),
    )
    if verbose:
        print(result.summary())
    if outdir is not None:
        result.save(outdir)
    return result
