"""Layer 6: fitting the dimuon mass spectrum (histograms, models, fits, stability).

Physics context
---------------
Why a peak on a smooth background. Muon pairs from Z -> mu+ mu- all have
an invariant mass near the Z mass, so they pile up in a narrow region of
the mass spectrum. Pairs from other processes (Drell-Yan production
through a virtual photon, heavy-flavour decays, misidentified muons) have
no preferred mass: their spectrum is smooth and falls with mass. A
histogram of the dimuon mass is therefore a *peak* (signal) sitting on a
smooth *continuum* (background). To measure the peak we fit a model with
one term for each, signal plus background; fitting a Gaussian alone would
let the background inflate the fitted height and width and could shift
the peak position wherever the background slopes.

Natural width and resolution. The Z is unstable (lifetime ~3e-25 s). By
the energy-time uncertainty relation its mass is not sharp: the
distribution of true masses is a Breit-Wigner (Cauchy) curve with full
width at half maximum Gamma_Z ~ 2.50 GeV, the *natural width*. The
detector then measures each muon momentum with a finite *resolution*
(about 1-2 % in the CMS barrel), which smears each measured mass by a
roughly Gaussian amount sigma of order 1-2 GeV at 91 GeV. The observed
shape is the Breit-Wigner convolved with that Gaussian: a Voigt profile.
A single Gaussian fitted to it describes both effects with one effective
width; the Voigt model separates them by fixing the natural width to its
known value and letting the Gaussian resolution float.

Statistics. Each bin count N is a Poisson random number whose standard
deviation is the square root of its expected value, estimated here by
sqrt(N). The fit minimises chi2 = sum((N - mu)^2 / sigma^2) over the bins
in the fit range, where mu is the model's expected count, computed by
integrating the model density over each bin (5-point Gauss-Legendre
quadrature: exact for the polynomial and, for a peak at least half a bin
wide, accurate to far better than the statistical precision). Comparing
counts with bin integrals rather than with the density at the bin centre
avoids an artificial broadening of the fitted width by about
(bin width)^2 / 12 in quadrature. Parameter uncertainties
come from the curvature of chi2 at the minimum (the covariance matrix).
"""

from __future__ import annotations

import math
import warnings
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, cast

import awkward as ak
import hist
import numpy as np
from particle import Particle
from scipy import integrate, optimize, special, stats

__all__ = [
    "MODELS",
    "FitError",
    "FitResult",
    "FitWarning",
    "MassHistogram",
    "PdgComparison",
    "PullTestResult",
    "StabilityResult",
    "compare_to_pdg",
    "fit_mass_peak",
    "fit_stability",
    "gaussian",
    "gaussian_plus_polynomial",
    "make_histogram",
    "pdg_mass_width",
    "polynomial",
    "pull_test",
    "toy_histogram",
    "voigt_plus_polynomial",
]

MODELS: tuple[str, ...] = ("gauss_poly", "voigt_poly")
"""Model names accepted by :func:`fit_mass_peak`."""

_FWHM_PER_SIGMA = 2.0 * math.sqrt(2.0 * math.log(2.0))  # 2.3548...


class FitError(RuntimeError):
    """Raised when a fit cannot give a trustworthy result.

    Reasons include: no entries in the fit range, the minimiser not
    converging, a covariance matrix that is not finite or not positive, a
    parameter stuck at one of its bounds (the curvature-based uncertainty
    is then meaningless), a peak that is not significant, or a model that
    predicts a negative count. A fit that fails loudly is better than a
    number that looks like a measurement but is not one.
    """


class FitWarning(str):
    """A problem with a fit that does not invalidate it: readable text plus a machine-readable code.

    It is a ``str`` (its message), so it prints and searches like text, and
    it carries ``code`` (a short identifier such as
    ``"background_negative"``) and ``details`` (a read-only mapping of the
    numbers behind the message) for programs that act on it, for example a
    plot that must not show yields the fit cannot support.
    """

    code: str
    details: Mapping[str, Any]

    def __new__(cls, code: str, message: str, **details: Any) -> FitWarning:
        """Create the warning: ``message`` is its text, ``code`` and ``details`` its machine-readable parts."""
        obj = super().__new__(cls, message)
        obj.code = code
        obj.details = MappingProxyType(dict(details))
        return obj

    def __repr__(self) -> str:
        return f"FitWarning({self.code!r}, {str(self)!r})"


# -- particle data -------------------------------------------------------------------


_PARTICLE_ALIASES = {"Z": 23, "Z0": 23, "W": 24, "W+": 24, "J/psi": 443, "Upsilon": 553}


def _particle(particle: str | int) -> Particle:
    pid = _PARTICLE_ALIASES.get(particle, particle) if isinstance(particle, str) else particle
    return Particle.from_pdgid(pid) if isinstance(pid, int) else Particle.from_name(pid)


def pdg_latex_name(particle: str | int) -> str:
    """The ``particle`` package's LaTeX name of a particle (e.g. ``Z^{0}``, ``J/\\psi(1S)``), for figure labels."""
    return str(_particle(particle).latex_name)


def pdg_mass_width(particle: str | int = "Z") -> tuple[float, float, float, float]:
    """Return ``(mass, mass_error, width, width_error)`` in GeV from the ``particle`` package.

    The ``particle`` package ships the Particle Data Group (PDG) tables in
    MeV; this converts to GeV. Values are read, not hard-coded, so they
    follow the installed PDG edition. ``particle`` may be a name such as
    ``"Z"`` or ``"Z0"``, or a PDG Monte Carlo ID such as 23.
    """
    p = _particle(particle)
    if p.mass is None:
        raise ValueError(f"the particle package has no mass for {p.name}")
    mev = 1e-3
    mass_err = 0.5 * ((p.mass_upper or 0.0) + (p.mass_lower or 0.0)) * mev
    width = (p.width or 0.0) * mev
    width_err = 0.5 * ((p.width_upper or 0.0) + (p.width_lower or 0.0)) * mev
    return p.mass * mev, mass_err, width, width_err


# -- histogram -----------------------------------------------------------------------


@dataclass(frozen=True)
class MassHistogram:
    """A one-dimensional histogram of masses (GeV) with Poisson errors.

    Attributes
    ----------
    counts : ndarray
        Entries in each bin (float64).
    edges : ndarray
        Bin edges in GeV, ``len(counts) + 1`` increasing values.
    underflow, overflow : int
        Entries below the first and above the last edge (not fitted).

    Error convention
    ----------------
    A bin count N is a Poisson random number, so its standard deviation
    is sqrt(expected N), estimated by :attr:`errors` = sqrt(N). For the fit,
    :attr:`fit_errors` = sqrt(max(N, 1)) is used instead, so that an empty
    bin gets error 1 rather than 0 (an error of 0 would be an infinite
    weight). Using the observed N rather than the unknown expected value is
    the "Neyman chi2"; it gives low-count bins too much weight when they
    fluctuate down and too little when they fluctuate up, so it slightly
    biases fits to sparse histograms (the fitted normalisation comes out
    low by about one entry per bin). The default fit range, 70-110 GeV,
    contains hundreds to thousands of entries per 1 GeV bin in the 2012
    data, where this bias is negligible; the sparse far tails are left out.
    """

    counts: np.ndarray
    edges: np.ndarray
    underflow: int = 0
    overflow: int = 0

    def __post_init__(self) -> None:
        counts = np.asarray(self.counts, dtype=np.float64)
        edges = np.asarray(self.edges, dtype=np.float64)
        if counts.ndim != 1 or edges.shape != (counts.size + 1,):
            raise ValueError(f"need 1-D counts and len(counts) + 1 edges, got {counts.shape} and {edges.shape}")
        if counts.size == 0:
            raise ValueError("a histogram needs at least one bin")
        if not np.all(np.diff(edges) > 0):
            raise ValueError("bin edges must be strictly increasing")
        if not np.all(np.isfinite(counts)) or np.any(counts < 0):
            raise ValueError("counts must be finite and non-negative")
        counts.flags.writeable = False
        edges.flags.writeable = False
        object.__setattr__(self, "counts", counts)
        object.__setattr__(self, "edges", edges)

    @property
    def centers(self) -> np.ndarray:
        """Bin centres (GeV)."""
        return 0.5 * (self.edges[:-1] + self.edges[1:])

    @property
    def widths(self) -> np.ndarray:
        """Bin widths (GeV)."""
        return np.diff(self.edges)

    @property
    def errors(self) -> np.ndarray:
        """Poisson errors sqrt(N) for display (0 for an empty bin)."""
        return np.sqrt(self.counts)

    @property
    def fit_errors(self) -> np.ndarray:
        """Errors used in the fit: sqrt(max(N, 1)), so empty bins keep a finite weight."""
        return np.sqrt(np.maximum(self.counts, 1.0))

    @property
    def n_entries(self) -> int:
        """Entries inside the histogram range (under- and overflow excluded)."""
        return int(round(self.counts.sum()))

    def to_hist(self) -> hist.Hist:
        """Return the same histogram as a :class:`hist.Hist` (with a ``mass`` axis)."""
        widths = self.widths
        axis: hist.axis.Regular | hist.axis.Variable
        if np.allclose(widths, widths[0]):
            axis = hist.axis.Regular(
                len(self.counts), self.edges[0], self.edges[-1], name="mass", label="Dimuon mass [GeV]"
            )
        else:
            axis = hist.axis.Variable(self.edges, name="mass", label="Dimuon mass [GeV]")
        h = hist.Hist(axis, storage=hist.storage.Double())
        h.view(flow=True)[:] = np.concatenate([[self.underflow], self.counts, [self.overflow]])
        return h

    def __repr__(self) -> str:
        return (
            f"MassHistogram({len(self.counts)} bins, {self.edges[0]:g}-{self.edges[-1]:g} GeV, "
            f"{self.n_entries:,} entries, underflow {self.underflow:,}, overflow {self.overflow:,})"
        )


def _flat_values(values: Any) -> np.ndarray:
    if isinstance(values, ak.Array):
        values = ak.flatten(values, axis=None)
        return np.asarray(ak.to_numpy(values), dtype=np.float64)
    arr = np.asarray(values, dtype=np.float64)
    return arr.ravel()


def make_histogram(
    values: Any, bins: int | Sequence[float] = 60, range: tuple[float, float] = (60.0, 120.0)
) -> MassHistogram:
    """Histogram masses (GeV) with the ``hist`` library and return a :class:`MassHistogram`.

    A histogram turns a list of masses into counts per mass interval. The
    bin width is a trade-off: narrow bins resolve the shape but each holds
    few entries, so its relative Poisson error 1/sqrt(N) is large; wide bins
    average the shape away. With a Z peak of a few GeV, bins of 0.5-2 GeV
    keep several bins across the peak.

    Parameters
    ----------
    values : array-like or awkward Array
        Masses in GeV. A jagged awkward array (e.g. one list of pair masses
        per event) is flattened. Values outside ``range`` go to under- and
        overflow; NaN values are dropped (not counted anywhere).
    bins : int or sequence of float
        Number of equal bins over ``range`` (default 60, i.e. 1 GeV bins
        over 60-120 GeV), or explicit bin edges.
    range : (float, float)
        Lower and upper edge in GeV, used with an integer ``bins``.

    Raises
    ------
    ValueError
        If ``values`` is empty (no values at all).
    """
    data = _flat_values(values)
    if data.size == 0:
        raise ValueError("make_histogram() got no values; there is nothing to histogram")
    data = data[~np.isnan(data)]
    axis: hist.axis.Regular | hist.axis.Variable
    if isinstance(bins, (int, np.integer)):
        lo, hi = float(range[0]), float(range[1])
        if bins < 1 or not hi > lo:
            raise ValueError(f"need bins >= 1 and range[1] > range[0], got bins={bins}, range={range}")
        axis = hist.axis.Regular(int(bins), lo, hi, name="mass")
    else:
        axis = hist.axis.Variable(np.asarray(bins, dtype=np.float64), name="mass")
    h = hist.Hist(axis, storage=hist.storage.Double())
    h.fill(mass=data)
    flow = h.view(flow=True)
    edges = h.axes[0].edges
    return MassHistogram(h.values(), edges, underflow=int(flow[0]), overflow=int(flow[-1]))


# -- models --------------------------------------------------------------------------


def gaussian(x: Any, amplitude: float, mean: float, sigma: float) -> np.ndarray:
    """Gaussian peak density in events per GeV: amplitude * N(x; mean, sigma).

    ``amplitude`` is the total number of signal events (the integral over
    all x), ``mean`` the peak position (GeV) and ``sigma`` the standard
    deviation (GeV); the full width at half maximum is 2.3548 sigma. A
    Gaussian is what many independent small measurement errors add up to
    (the central limit theorem), so it describes detector resolution well.
    Fitted to a Z peak it absorbs the natural width too, as one effective
    width.
    """
    x = np.asarray(x, dtype=np.float64)
    return amplitude * np.exp(-0.5 * ((x - mean) / sigma) ** 2) / (sigma * math.sqrt(2.0 * math.pi))


def polynomial(x: Any, *coeffs: float, x0: float = 0.0) -> np.ndarray:
    """Polynomial background density in events per GeV: sum_k coeffs[k] * (x - x0)^k.

    A smooth, slowly varying background over a window a few tens of GeV
    wide is well described by a low-degree polynomial. Writing it in
    powers of (x - x0), with x0 the middle of the fit range, keeps the
    coefficients of similar size and nearly uncorrelated (c0 is the
    background density at x0, c1 its slope there); powers of x itself
    (x^2 ~ 8000 GeV^2 at 90 GeV) would make the fit numerically unstable.
    """
    x = np.asarray(x, dtype=np.float64)
    u = x - x0
    out = np.zeros_like(u)
    for c in reversed(coeffs):  # Horner's rule over the few coefficients, vectorized in x
        out = out * u + c
    return out


def gaussian_plus_polynomial(
    x: Any, amplitude: float, mean: float, sigma: float, *coeffs: float, x0: float = 0.0
) -> np.ndarray:
    """Signal-plus-background density: :func:`gaussian` + :func:`polynomial` (events per GeV).

    Parameters are those of the two parts: ``amplitude`` (signal events),
    ``mean`` and ``sigma`` (GeV) of the peak, then the polynomial
    coefficients c0, c1, ... about ``x0``.
    """
    return gaussian(x, amplitude, mean, sigma) + polynomial(x, *coeffs, x0=x0)


def voigt_plus_polynomial(
    x: Any, amplitude: float, mean: float, sigma: float, *coeffs: float, gamma: float | None = None, x0: float = 0.0
) -> np.ndarray:
    """Voigt peak plus polynomial background density (events per GeV).

    The signal is amplitude * V(x - mean; sigma, gamma), where the Voigt
    profile V (``scipy.special.voigt_profile``, normalised to 1) is a
    Breit-Wigner (Cauchy) curve of half width at half maximum ``gamma``
    convolved with a Gaussian of standard deviation ``sigma``.

    Why this is physically better than a Gaussian: the Z itself has a
    natural width Gamma_Z ~ 2.5 GeV (its mass distribution is a
    Breit-Wigner with gamma = Gamma_Z / 2), and the detector adds its own
    Gaussian resolution on top. The two combine by convolution, not by
    adding widths. A Breit-Wigner has much longer tails than a Gaussian, so
    a Gaussian fit has to compromise between the core and the tails. Here
    ``gamma`` defaults to half the natural Z width read from the
    ``particle`` package, and only ``sigma``, the detector resolution, is
    fitted. (This uses the non-relativistic Breit-Wigner and ignores
    final-state photon radiation, which adds a tail on the low-mass side.)
    """
    if gamma is None:
        gamma = 0.5 * pdg_mass_width("Z")[2]
    x = np.asarray(x, dtype=np.float64)
    return amplitude * special.voigt_profile(x - mean, sigma, gamma) + polynomial(x, *coeffs, x0=x0)


# -- the fit --------------------------------------------------------------------------


def _sym_error(cov: np.ndarray, grad: np.ndarray) -> float:
    return float(math.sqrt(max(float(grad @ cov @ grad), 0.0)))


@dataclass(frozen=True)
class FitResult:
    """The outcome of :func:`fit_mass_peak`.

    Densities (:meth:`model`, :meth:`signal`, :meth:`background`) are in
    events per GeV; multiply by a bin width to compare with bin counts.

    Goodness of fit. ``chi2`` is the sum over fitted bins of
    ((N - expected) / error)^2 and ``ndf`` the number of bins minus the
    number of free parameters. If the model is right and the errors are
    Gaussian, chi2 follows a chi-squared distribution with ndf degrees of
    freedom, so chi2/ndf ~ 1 and the p-value (the probability of a chi2 at
    least this large by chance) is uniform between 0 and 1. A tiny p-value
    says the model does not describe the data within the statistical
    errors; with very many events even small imperfections (the radiative
    tail, a momentum-scale shift, a slightly wrong background shape) are
    detected. A good p-value does NOT prove the model is right, only that
    the data cannot tell it apart from the truth at this precision.
    """

    model_name: str
    parameter_names: tuple[str, ...]
    values: np.ndarray
    errors: np.ndarray
    covariance: np.ndarray
    chi2: float
    ndf: int
    p_value: float
    fit_range: tuple[float, float]
    histogram: MassHistogram
    fit_mask: np.ndarray
    poly_degree: int
    x0: float
    gamma: float | None = None
    n_entries: int = 0
    warnings: tuple[FitWarning, ...] = ()
    """Problems that do not invalidate the peak position but limit other results.

    A tuple of :class:`FitWarning` (each a string with a ``code`` and
    ``details``), printed by :meth:`table`. Code ``"background_negative"``:
    the fitted background density is below zero somewhere in the fit
    range; ``details["significant"]`` says whether by more than 3 of its
    own propagated errors.
    """
    _density: Callable[..., np.ndarray] | None = field(default=None, repr=False)

    @property
    def yields_reliable(self) -> bool:
        """False if the fitted background goes below zero anywhere in the fit range.

        A negative background density is not physical. When it happens, the
        polynomial is compensating for a feature the peak model misses (in
        the 2012 data, the radiative tail below the Z), so how the events are
        split between signal and background, and hence both yields, cannot
        be trusted, even if the dip is within the statistical errors. The
        peak position and width are much less affected.
        """
        return not any(w.code == "background_negative" for w in self.warnings)

    @property
    def chi2_ndf(self) -> float:
        """chi2 divided by the number of degrees of freedom (about 1 for a good fit)."""
        return self.chi2 / self.ndf

    @property
    def parameters(self) -> dict[str, tuple[float, float]]:
        """``{name: (value, uncertainty)}`` for every free parameter."""
        return {
            n: (float(v), float(e)) for n, v, e in zip(self.parameter_names, self.values, self.errors, strict=False)
        }

    @property
    def correlation(self) -> np.ndarray:
        """Correlation matrix: covariance divided by the product of the errors."""
        return self.covariance / np.outer(self.errors, self.errors)

    def _index(self, name: str) -> int:
        return self.parameter_names.index(name)

    @property
    def peak_position(self) -> tuple[float, float]:
        """Fitted peak position ``(mean, error)`` in GeV."""
        return self.parameters["mean"]

    @property
    def resolution(self) -> tuple[float, float]:
        """Fitted Gaussian width ``(sigma, error)`` in GeV.

        For ``"voigt_poly"`` this is the detector mass resolution alone (the
        natural width is fixed separately). For ``"gauss_poly"`` it is an
        effective width that also absorbs the natural width of the Z.
        """
        return self.parameters["sigma"]

    @property
    def fwhm(self) -> tuple[float, float]:
        """Full width at half maximum of the signal ``(value, error)`` in GeV.

        Gaussian: 2 sqrt(2 ln 2) sigma = 2.3548 sigma. Voigt: the
        Olivero-Longbothum approximation 0.5346 f_L + sqrt(0.2166 f_L^2 +
        f_G^2) with f_L = 2 gamma and f_G = 2.3548 sigma (accurate to about
        0.02 %); its error comes from sigma only, since gamma is fixed.
        """
        sigma, err = self.resolution
        fg = _FWHM_PER_SIGMA * sigma
        if self.gamma is None:
            return fg, _FWHM_PER_SIGMA * err
        fl = 2.0 * self.gamma
        root = math.sqrt(0.2166 * fl**2 + fg**2)
        return 0.5346 * fl + root, (fg / root) * _FWHM_PER_SIGMA * err

    # -- component densities -----------------------------------------------------------

    def _signal_density(self, x: Any, p: np.ndarray) -> np.ndarray:
        if self.gamma is None:
            return gaussian(x, p[0], p[1], p[2])
        return p[0] * special.voigt_profile(np.asarray(x, dtype=np.float64) - p[1], p[2], self.gamma)

    def model(self, x: Any) -> np.ndarray:
        """Total fitted density (signal + background) at mass ``x``, in events per GeV."""
        return self._signal_density(x, self.values) + self.background(x)

    def signal(self, x: Any) -> np.ndarray:
        """Fitted signal density at ``x`` (events per GeV)."""
        return self._signal_density(x, self.values)

    def background(self, x: Any) -> np.ndarray:
        """Fitted polynomial background density at ``x`` (events per GeV)."""
        return polynomial(x, *self.values[3:], x0=self.x0)

    def expected_counts(self) -> np.ndarray:
        """Expected count in each fitted bin from the fitted model (bin-integrated)."""
        return cast(Callable[..., np.ndarray], self._density)(self.values)

    # -- yields ------------------------------------------------------------------------

    @property
    def signal_yield(self) -> tuple[float, float]:
        """Signal events inside the fit range ``(value, error)``.

        The signal density integrated over the fit range. The error is
        propagated from the full covariance matrix with a numerical
        gradient, sigma^2 = J C J^T, so correlations (for example between
        the signal amplitude and the background level under the peak) are
        included.
        """
        lo, hi = self.fit_range
        grid = np.linspace(lo, hi, 4001)

        def integral(p: np.ndarray) -> float:
            return float(integrate.simpson(self._signal_density(grid, p), x=grid))

        value = integral(self.values)
        grad = np.zeros_like(self.values)
        for i in range(3):  # the signal depends only on amplitude, mean, sigma
            h = 1e-4 * self.errors[i] if self.errors[i] > 0 else 1e-6
            up, down = self.values.copy(), self.values.copy()
            up[i] += h
            down[i] -= h
            grad[i] = (integral(up) - integral(down)) / (2 * h)
        return value, _sym_error(self.covariance, grad)

    @property
    def background_yield(self) -> tuple[float, float]:
        """Background events inside the fit range ``(value, error)``.

        The polynomial integrates analytically: the integral is linear in
        the coefficients, int (x - x0)^k dx = [(x - x0)^(k+1) / (k+1)], so the
        error propagation is exact.
        """
        lo, hi = self.fit_range
        k = np.arange(self.poly_degree + 1)
        basis = ((hi - self.x0) ** (k + 1) - (lo - self.x0) ** (k + 1)) / (k + 1)
        grad = np.zeros_like(self.values)
        grad[3:] = basis
        return float(basis @ self.values[3:]), _sym_error(self.covariance, grad)

    # -- display -------------------------------------------------------------------------

    def table(self) -> str:
        """A readable table of parameters, uncertainties and fit quality."""
        lines = [
            f"Fit {self.model_name} (polynomial degree {self.poly_degree}) over "
            f"{self.fit_range[0]:g}-{self.fit_range[1]:g} GeV, {int(self.fit_mask.sum())} bins, "
            f"{self.n_entries:,} entries",
            f"  {'parameter':<12}{'value':>14}{'error':>12}",
        ]
        for name, (v, e) in self.parameters.items():
            lines.append(f"  {name:<12}{v:>14.5g}{e:>12.3g}")
        if self.gamma is not None:
            lines.append(f"  {'gamma':<12}{self.gamma:>14.5g}{'fixed':>12}   (Breit-Wigner half width, GeV)")
        lines.append(
            f"  chi2 / ndf = {self.chi2:.2f} / {self.ndf} = {self.chi2_ndf:.3f},  p-value = {self.p_value:.3g}"
        )
        m, me = self.peak_position
        s, se = self.resolution
        f, fe = self.fwhm
        sy, sye = self.signal_yield
        by, bye = self.background_yield
        lines.append(
            f"  peak position {m:.4f} +- {me:.4f} GeV,  sigma {s:.4f} +- {se:.4f} GeV,  FWHM {f:.3f} +- {fe:.3f} GeV"
        )
        lines.append(
            f"  signal yield {sy:,.0f} +- {sye:,.0f},  background yield {by:,.0f} +- {bye:,.0f}  (in the fit range)"
        )
        lines.extend(f"  WARNING: {w}" for w in self.warnings)
        return "\n".join(lines)

    def __str__(self) -> str:
        return self.table()


def _bounds_hit(values: np.ndarray, lower: np.ndarray, upper: np.ndarray) -> list[int]:
    hit = []
    for i, (v, lo, hi) in enumerate(zip(values, lower, upper, strict=False)):
        for b in (lo, hi):
            if np.isfinite(b) and abs(v - b) <= 1e-6 * max(1.0, abs(b)):
                hit.append(i)
    return hit


def fit_mass_peak(
    hist_or_values: MassHistogram | Any,
    model: str = "gauss_poly",
    fit_range: tuple[float, float] = (70.0, 110.0),
    poly_degree: int = 2,
    initial: Mapping[str, float] | None = None,
    *,
    natural_width: float | None = None,
    min_significance: float = 5.0,
    bins: int | Sequence[float] = 60,
    hist_range: tuple[float, float] = (60.0, 120.0),
) -> FitResult:
    """Fit a signal-plus-background model to a dimuon mass histogram.

    The model is a peak (``"gauss_poly"``: Gaussian; ``"voigt_poly"``:
    Voigt with the natural width fixed) plus a polynomial background of
    degree ``poly_degree``. It is fitted with ``scipy.optimize.curve_fit``,
    minimising chi2 with the Poisson errors sqrt(max(N, 1)) as absolute
    uncertainties (``absolute_sigma=True``: the errors are taken as known,
    not rescaled to make chi2/ndf = 1, so the parameter uncertainties are
    the statistical ones).

    Why signal plus background: the peak sits on a continuum. A Gaussian
    alone would treat the continuum under the peak as signal and its slope
    would pull the fitted position. Modelling the background with a smooth
    polynomial lets the fit separate the two.

    Why the fit range matters: the polynomial only needs to describe the
    background over the fitted window, and a narrow window (70-110 GeV)
    keeps that easy while still including sidebands on both sides to pin
    the background down. Too narrow, and the background is not constrained;
    too wide, and a low-degree polynomial cannot follow the steeply falling
    continuum, or the sparse tails make the Poisson errors unreliable. The
    window must be chosen before looking at the result; how much the answer
    moves when it changes is a systematic uncertainty (see
    :func:`fit_stability`). Only bins that lie entirely inside
    ``fit_range`` are used, and :attr:`FitResult.fit_range` reports the
    edges actually used.

    Initial values and bounds come from the data: the background from a
    straight line through the outer sixth of the window on each side, the
    peak position from the highest background-subtracted bin, the width
    from the number of bins above half that maximum, and the amplitude from
    the background-subtracted sum. The amplitude must be >= 0, the mean
    inside the window, and sigma between a quarter of the narrowest bin
    and half the window.

    Parameters
    ----------
    hist_or_values : MassHistogram or array-like
        A histogram, or masses (GeV; jagged awkward arrays are flattened),
        which are histogrammed with ``bins`` and ``hist_range``.
    model : {"gauss_poly", "voigt_poly"}
    fit_range : (float, float)
        Mass window in GeV.
    poly_degree : int
        Degree of the background polynomial (0-5).
    initial : mapping, optional
        Starting values by parameter name (``amplitude``, ``mean``,
        ``sigma``, ``c0``, ``c1``, ...), overriding the automatic ones.
    natural_width : float, optional
        Breit-Wigner FWHM in GeV for ``"voigt_poly"`` (default: the Z width
        from the ``particle`` package).
    min_significance : float
        The fit fails unless amplitude / error >= this (default 5): a
        "peak" that could be a fluctuation has no meaningful position.

    Raises
    ------
    FitError
        If there are no entries in the window, too few bins, the fit does
        not converge, the covariance is not finite and positive, a
        parameter ends on a bound, the peak is not significant, or the
        model predicts a negative count in a bin. A background *component*
        that is significantly negative (by more than 3 of its own
        propagated errors) while the total stays positive is not an error
        but is recorded in :attr:`FitResult.warnings`: the peak position is
        still meaningful, the signal/background split is not.
    ValueError
        For invalid arguments.
    """
    if model not in MODELS:
        raise ValueError(f"model must be one of {MODELS}, got {model!r}")
    if not isinstance(poly_degree, (int, np.integer)) or not 0 <= poly_degree <= 5:
        raise ValueError(f"poly_degree must be an integer from 0 to 5, got {poly_degree!r}")
    h = (
        hist_or_values
        if isinstance(hist_or_values, MassHistogram)
        else make_histogram(hist_or_values, bins, hist_range)
    )
    lo_req, hi_req = float(fit_range[0]), float(fit_range[1])
    if not hi_req > lo_req:
        raise ValueError(f"fit_range must be (low, high) with high > low, got {fit_range}")
    eps = 1e-9 * max(1.0, abs(hi_req))
    mask = (h.edges[:-1] >= lo_req - eps) & (h.edges[1:] <= hi_req + eps)
    if not mask.any():
        raise ValueError(
            f"no bin of the histogram ({h.edges[0]:g}-{h.edges[-1]:g} GeV) lies inside fit_range {fit_range}"
        )
    edges_lo, edges_hi = h.edges[:-1][mask], h.edges[1:][mask]
    lo, hi = float(edges_lo[0]), float(edges_hi[-1])
    counts, widths = h.counts[mask], edges_hi - edges_lo
    centers = 0.5 * (edges_lo + edges_hi)
    errors = np.sqrt(np.maximum(counts, 1.0))
    n_entries = int(round(counts.sum()))
    x0 = 0.5 * (lo + hi)

    gamma = None
    if model == "voigt_poly":
        width = natural_width if natural_width is not None else pdg_mass_width("Z")[2]
        if not (np.isfinite(width) and width > 0):
            raise ValueError(f"natural_width must be a positive number of GeV, got {width!r}")
        gamma = 0.5 * float(width)
    names = ("amplitude", "mean", "sigma", *(f"c{k}" for k in range(poly_degree + 1)))
    n_par = len(names)

    if n_entries == 0:
        raise FitError(f"no entries in the fit range {lo:g}-{hi:g} GeV; there is nothing to fit")
    if len(counts) <= n_par:
        raise FitError(
            f"{len(counts)} bins in {lo:g}-{hi:g} GeV cannot constrain {n_par} parameters; "
            "use finer bins or a wider range"
        )

    def density(x: np.ndarray, p: Sequence[float]) -> np.ndarray:
        if gamma is None:
            sig = gaussian(x, p[0], p[1], p[2])
        else:
            sig = p[0] * special.voigt_profile(x - p[1], p[2], gamma)
        return sig + polynomial(x, *p[3:], x0=x0)

    # 5-point Gauss-Legendre quadrature over each bin: exact for the polynomial, very accurate for the peak.
    nodes, weights = np.polynomial.legendre.leggauss(5)
    points = centers[:, None] + 0.5 * widths[:, None] * nodes  # (bins, 5)

    def expected(p: Sequence[float]) -> np.ndarray:
        return 0.5 * widths * (density(points, p) @ weights)

    # -- data-driven starting values --------------------------------------------------
    dens = counts / widths
    n_side = max(2, len(counts) // 6)
    side = np.r_[np.arange(n_side), np.arange(len(counts) - n_side, len(counts))]
    lin = np.polyfit(centers[side] - x0, dens[side], deg=min(1, poly_degree))[::-1]
    coeffs0 = np.zeros(poly_degree + 1)
    coeffs0[: len(lin)] = lin
    excess = dens - polynomial(centers, *coeffs0, x0=x0)
    peak = int(np.argmax(excess))
    above = excess > 0.5 * excess[peak]
    sigma_lo, sigma_hi = 0.25 * float(widths.min()), 0.5 * (hi - lo)
    sigma0 = float(np.clip(widths[above].sum() / _FWHM_PER_SIGMA, 2 * sigma_lo, 0.25 * (hi - lo)))
    if gamma is not None:
        sigma0 = float(
            np.clip(math.sqrt(max(sigma0**2 - gamma**2, 0.0)) or 0.5 * sigma0, 2 * sigma_lo, 0.25 * (hi - lo))
        )
    amp0 = float(max((excess[excess > 0] * widths[excess > 0]).sum(), 1.0))
    p0 = np.array([amp0, float(centers[peak]), sigma0, *coeffs0])
    for name, value in (initial or {}).items():
        if name not in names:
            raise ValueError(f"unknown parameter {name!r} in initial; parameters are {names}")
        p0[names.index(name)] = float(value)

    lower = np.array([0.0, lo, sigma_lo, *([-np.inf] * (poly_degree + 1))])
    upper = np.array([np.inf, hi, sigma_hi, *([np.inf] * (poly_degree + 1))])
    # The trust-region solver needs a start strictly inside the bounds.
    span = np.where(np.isfinite(upper - lower), upper - lower, 1.0)
    p0 = np.clip(p0, lower + 1e-6 * span, upper - 1e-6 * span)

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", optimize.OptimizeWarning)
            values, cov = optimize.curve_fit(
                lambda _x, *p: expected(p),
                centers,
                counts,
                p0=p0,
                sigma=errors,
                absolute_sigma=True,
                bounds=(lower, upper),
                method="trf",
                max_nfev=20000,
            )
    except (RuntimeError, optimize.OptimizeWarning, ValueError) as exc:
        raise FitError(f"{model} fit over {lo:g}-{hi:g} GeV did not converge: {exc}") from exc

    if not np.all(np.isfinite(cov)) or np.any(np.diag(cov) <= 0):
        raise FitError(f"{model} fit over {lo:g}-{hi:g} GeV: the covariance matrix is not finite and positive")
    stuck = _bounds_hit(values, lower, upper)
    if stuck:
        raise FitError(
            f"{model} fit over {lo:g}-{hi:g} GeV: parameter(s) {[names[i] for i in stuck]} ended on a bound "
            f"({', '.join(f'{names[i]}={values[i]:.4g}' for i in stuck)}); there is no well-defined peak to measure"
        )
    errs = np.sqrt(np.diag(cov))
    significance = values[0] / errs[0]
    if significance < min_significance:
        raise FitError(
            f"{model} fit over {lo:g}-{hi:g} GeV: the peak amplitude {values[0]:.1f} +- {errs[0]:.1f} is only "
            f"{significance:.1f} sigma from zero (< {min_significance:g}); no significant peak"
        )
    mu = expected(values)
    if np.any(mu < 0):
        bad = int(np.argmin(mu))
        raise FitError(
            f"{model} fit over {lo:g}-{hi:g} GeV: the model predicts a negative count ({mu[bad]:.3g}) "
            f"in the bin at {centers[bad]:g} GeV, which no Poisson process can produce"
        )
    # A background density below zero is unphysical as a component, though the total can still
    # describe the data. It usually means the peak model misses a feature (e.g. the radiative tail)
    # and the polynomial bends to absorb it. The peak position survives that; the signal/background
    # split does not. Say so, loudly if the dip is significant (more than 3 of its own errors).
    notes = []
    grid = np.linspace(lo, hi, 401)
    basis = (grid[:, None] - x0) ** np.arange(poly_degree + 1)
    bkg = basis @ values[3:]
    bkg_err = np.sqrt(np.maximum(np.einsum("ij,jk,ik->i", basis, cov[3:, 3:], basis), 0.0))
    if np.any(bkg < 0):
        worst = int(np.argmin(bkg + 3.0 * bkg_err))
        significant = bool(bkg[worst] + 3.0 * bkg_err[worst] < 0)
        if not significant:
            worst = int(np.argmin(bkg))
        details = {
            "min_density": float(bkg[worst]),
            "error": float(bkg_err[worst]),
            "at_mass": float(grid[worst]),
            "significant": significant,
        }
        if significant:
            message = (
                f"the fitted background is significantly negative ({bkg[worst]:.3g} +- {bkg_err[worst]:.2g} "
                f"events/GeV at {grid[worst]:.1f} GeV): the peak model does not describe the data's shape and "
                f"the polynomial compensates, so the signal and background yields are not reliable"
            )
        else:
            message = (
                f"the fitted background dips below zero ({bkg[worst]:.3g} +- {bkg_err[worst]:.2g} events/GeV "
                f"at {grid[worst]:.1f} GeV, within 3 errors of zero): a negative background is not physical, "
                f"so the signal and background yields are not reliable"
            )
        notes.append(FitWarning("background_negative", message, **details))

    chi2 = float(np.sum(((counts - mu) / errors) ** 2))
    ndf = len(counts) - n_par
    return FitResult(
        model_name=model,
        parameter_names=names,
        values=values,
        errors=errs,
        covariance=cov,
        chi2=chi2,
        ndf=ndf,
        p_value=float(stats.chi2.sf(chi2, ndf)),
        fit_range=(lo, hi),
        histogram=h,
        fit_mask=mask,
        poly_degree=int(poly_degree),
        x0=x0,
        gamma=gamma,
        n_entries=n_entries,
        warnings=tuple(notes),
        _density=expected,
    )


# -- comparison with the PDG -----------------------------------------------------------


@dataclass(frozen=True)
class PdgComparison:
    """Fitted peak position compared with the PDG mass (all in GeV)."""

    particle: str
    pdg_mass: float
    pdg_mass_error: float
    pdg_width: float
    fitted: float
    fitted_error: float
    difference: float
    pull: float
    note: str

    @property
    def relative_difference(self) -> float:
        """(fitted - PDG) / PDG, as a fraction (multiply by 100 for percent)."""
        return self.difference / self.pdg_mass

    def __str__(self) -> str:
        return (
            f"{self.particle}: fitted {self.fitted:.4f} +- {self.fitted_error:.4f} GeV (stat-only uncertainty), "
            f"PDG {self.pdg_mass:.4f} +- {self.pdg_mass_error:.4f} GeV\n"
            f"  offset {self.difference:+.4f} GeV ({100 * self.relative_difference:+.3f} %), "
            f"pull {self.pull:+.1f} (statistical error only)\n  {self.note}"
        )


def compare_to_pdg(result: FitResult, particle: str | int = "Z") -> PdgComparison:
    """Compare a fitted peak position with the PDG mass from the ``particle`` package.

    Returns the difference (fitted - PDG) in GeV (and, as
    :attr:`PdgComparison.relative_difference`, as a fraction) and the pull,
    difference / fit uncertainty. The fit uncertainty is statistical only,
    so the pull is how many *statistical* standard deviations apart the two
    are; it is not the significance of a disagreement, which would need the
    systematic uncertainties too (the PDG uncertainty, 0.002 GeV for the Z,
    is negligible here).

    Read the result with care. The fitted peak position of a Gaussian (or of
    a symmetric Voigt) is NOT the same quantity as the PDG *pole mass*,
    which is a parameter of the full relativistic line shape, extracted
    with the photon-exchange interference, initial- and final-state
    radiation and parton luminosities taken into account. Final-state
    radiation in particular moves events below the peak. Moreover, the
    open data carry no muon momentum-scale corrections: a momentum scale
    off by 0.1 % moves the peak by about 0.09 GeV. A small offset from the
    PDG value is therefore expected and is a systematic effect of this
    simple analysis, not a contradiction of the PDG value. With tens of
    thousands of events the statistical error is so small that this
    offset can be many "sigma"; the pull then measures the size of the
    systematic effects, not a disagreement.
    """
    if not isinstance(result, FitResult):
        raise TypeError(f"compare_to_pdg() needs a FitResult, got {type(result).__name__}")
    mass, mass_err, width, _ = pdg_mass_width(particle)
    fitted, err = result.peak_position
    diff = fitted - mass
    pull = diff / err
    direction = "below" if diff < 0 else "above"
    if abs(pull) <= 2:
        verdict = "consistent with the PDG value within the statistical uncertainty"
    else:
        verdict = (
            "a statistically significant offset; with no momentum-scale corrections and a simple peak "
            "model this reflects systematic effects of the analysis, not a disagreement with the PDG"
        )
    note = (
        f"The {result.model_name} peak is {abs(diff):.3f} GeV ({100 * abs(diff) / mass:.2f} %) {direction} the PDG "
        f"mass: {verdict}. The uncertainty is statistical only (stat-only uncertainty): it leaves out the muon "
        f"momentum scale, the line-shape model and the fit choices, so the pull overstates how significant "
        f"the offset is."
    )
    name = particle if isinstance(particle, str) else Particle.from_pdgid(particle).name
    return PdgComparison(name, mass, mass_err, width, fitted, err, diff, pull, note)


# -- stability under fit choices ------------------------------------------------------------


@dataclass(frozen=True)
class StabilityResult:
    """Fitted mass for every combination of fit choices, with summary statistics.

    ``rows`` holds one dict per converged fit (``model``, ``fit_range``
    actually used, ``bin_width``, ``poly_degree``, ``mass``, ``mass_error``,
    ``chi2_ndf``, ``p_value``, ``warnings``); ``failed`` lists the combinations that raised
    :class:`FitError`, with the reason. ``mean`` and ``std`` (sample
    standard deviation, ddof = 1) and ``min``/``max`` summarise the fitted
    masses of the converged fits.
    """

    rows: tuple[dict[str, Any], ...]
    failed: tuple[dict[str, Any], ...]
    mean: float
    std: float
    min: float
    max: float

    @property
    def n_fits(self) -> int:
        """Number of combinations tried (converged + failed)."""
        return len(self.rows) + len(self.failed)

    @property
    def range(self) -> float:
        """max - min of the fitted masses (GeV)."""
        return self.max - self.min

    def __str__(self) -> str:
        lines = [
            f"  {'model':<11}{'range':>10}{'bin':>6}{'deg':>5}{'mass':>11}{'error':>9}{'chi2/ndf':>10}{'p-value':>10}"
        ]
        for r in self.rows:
            lo, hi = r["fit_range"]
            lines.append(
                f"  {r['model']:<11}{f'{lo:g}-{hi:g}':>10}{r['bin_width']:>6g}{r['poly_degree']:>5}"
                f"{r['mass']:>11.4f}{r['mass_error']:>9.4f}{r['chi2_ndf']:>10.3f}{r['p_value']:>10.3g}"
                + ("  (negative background)" if r["warnings"] else "")
            )
        for f in self.failed:
            lo, hi = f["fit_range"]
            lines.append(
                f"  {f['model']:<11}{f'{lo:g}-{hi:g}':>10}{f['bin_width']:>6g}{f['poly_degree']:>5}"
                f"   FAILED: {f['reason']}"
            )
        lines.append(
            f"  {len(self.rows)} of {self.n_fits} fits converged; fitted mass mean {self.mean:.4f} GeV, "
            f"std {self.std:.4f} GeV, range {self.min:.4f}-{self.max:.4f} GeV ({self.range:.4f} GeV)"
        )
        return "\n".join(lines)


def fit_stability(
    values: Any,
    fit_ranges: Sequence[tuple[float, float]] = ((70.0, 110.0), (75.0, 105.0), (80.0, 100.0)),
    bin_widths: Sequence[float] = (0.5, 1.0, 2.0),
    poly_degrees: Sequence[int] = (1, 2, 3),
    models: Sequence[str] = MODELS,
    hist_range: tuple[float, float] = (60.0, 120.0),
    natural_width: float | None = None,
) -> StabilityResult:
    """Refit the same masses under every combination of reasonable fit choices.

    Each choice here (window, bin width, background degree, peak model) is
    defensible, and none is uniquely right. If the fitted mass moved by
    more than its statistical error when a choice changes, the result
    depends on an arbitrary decision, and that dependence is a systematic
    uncertainty. The spread (standard deviation) of the fitted masses over
    the grid is a rough, honest estimate of it; the full min-max range is a
    more conservative one. The spread does not cover effects that every
    variation shares, such as the muon momentum scale or final-state
    radiation.

    Parameters
    ----------
    values : array-like or awkward Array
        Masses in GeV (jagged arrays are flattened).
    fit_ranges, bin_widths, poly_degrees, models : sequences
        The grid; every combination is fitted (default 3 x 3 x 3 x 2 = 54).
    hist_range : (float, float)
        Histogram range in GeV; each bin width must divide it evenly.
    natural_width : float, optional
        Breit-Wigner FWHM in GeV for the Voigt fits (default: the Z width), e.g.
        the J/psi width for a J/psi spectrum.

    Returns
    -------
    StabilityResult
        Combinations that raise :class:`FitError` are skipped in the
        statistics and listed in ``failed``.
    """
    data = _flat_values(values)
    lo, hi = hist_range
    hists = {}
    for w in bin_widths:
        n_bins = (hi - lo) / w
        if abs(n_bins - round(n_bins)) > 1e-9:
            raise ValueError(f"bin width {w} GeV does not divide the histogram range {hist_range}")
        hists[w] = make_histogram(data, bins=int(round(n_bins)), range=hist_range)
    rows, failed = [], []
    for model in models:
        for fit_range in fit_ranges:
            for w in bin_widths:
                for degree in poly_degrees:
                    config = {"model": model, "fit_range": tuple(fit_range), "bin_width": w, "poly_degree": degree}
                    try:
                        r = fit_mass_peak(
                            hists[w], model=model, fit_range=fit_range, poly_degree=degree, natural_width=natural_width
                        )
                    except FitError as exc:
                        failed.append({**config, "reason": str(exc)})
                        continue
                    m, me = r.peak_position
                    rows.append(
                        {
                            **config,
                            "fit_range": r.fit_range,
                            "mass": m,
                            "mass_error": me,
                            "chi2_ndf": r.chi2_ndf,
                            "p_value": r.p_value,
                            "warnings": r.warnings,
                        }
                    )
    masses = np.array([r["mass"] for r in rows])
    if masses.size == 0:
        nan = float("nan")
        return StabilityResult((), tuple(failed), nan, nan, nan, nan)
    std = float(np.std(masses, ddof=1)) if masses.size > 1 else 0.0
    return StabilityResult(
        tuple(rows), tuple(failed), float(masses.mean()), std, float(masses.min()), float(masses.max())
    )


# -- toys and the pull test ------------------------------------------------------------------


def toy_histogram(
    rng: np.random.Generator,
    n_signal: float = 4000.0,
    n_background: float = 4000.0,
    mean: float = 91.0,
    sigma: float = 2.0,
    slope: float = 25.0,
    bins: int = 60,
    range: tuple[float, float] = (60.0, 120.0),
) -> MassHistogram:
    """Draw a Poisson-fluctuated toy histogram with known truth.

    The expected count in each bin is a Gaussian signal of ``n_signal``
    events plus an exponentially falling background, exp(-m / slope),
    normalised to ``n_background`` events over ``range``, integrated
    exactly over the bin. Each bin is then drawn from a Poisson
    distribution with that mean, which is how real counts fluctuate. Toys
    with known truth are the standard way to check that a fit is unbiased
    and that its quoted errors are right.
    """
    edges = np.linspace(range[0], range[1], bins + 1)
    sig = n_signal * np.diff(special.ndtr((edges - mean) / sigma))
    cdf = -np.exp(-edges / slope)
    bkg = n_background * np.diff(cdf) / (cdf[-1] - cdf[0])
    return MassHistogram(rng.poisson(sig + bkg).astype(np.float64), edges)


@dataclass(frozen=True)
class PullTestResult:
    """Pulls of the fitted peak position over many toys, and their mean and standard deviation."""

    pulls: np.ndarray
    n_toys: int
    n_failed: int
    true_mean: float

    @property
    def mean(self) -> float:
        """Mean pull: about 0 if the fit is unbiased."""
        return float(np.mean(self.pulls))

    @property
    def std(self) -> float:
        """Standard deviation of the pulls: about 1 if the quoted errors are right."""
        return float(np.std(self.pulls, ddof=1))


def pull_test(n_toys: int = 1000, seed: int = 20121, model: str = "gauss_poly", **toy: Any) -> PullTestResult:
    """Fit many toys with known truth and return the pulls (fitted - true) / error of the peak position.

    If the fit is unbiased and its uncertainty is right, the pulls follow a
    standard normal distribution: mean 0 and standard deviation 1. A mean
    far from 0 is a bias; a standard deviation above 1 means the quoted
    errors are too small, below 1 too large. This is the basic check that
    an uncertainty estimate can be trusted. Toys come from
    :func:`toy_histogram` with keyword arguments ``toy`` (seeded, so the
    result is reproducible); each is fitted over 70-110 GeV with a degree 2
    background.
    """
    rng = np.random.default_rng(seed)
    true_mean = float(toy.get("mean", 91.0))
    pulls, failed = [], 0
    for _ in range(n_toys):
        h = toy_histogram(rng, **toy)
        try:
            r = fit_mass_peak(h, model=model, fit_range=(70.0, 110.0), poly_degree=2)
        except FitError:
            failed += 1
            continue
        m, e = r.peak_position
        pulls.append((m - true_mean) / e)
    return PullTestResult(np.array(pulls), n_toys, failed, true_mean)
