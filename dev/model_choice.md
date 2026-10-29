# Model choice rule (Layer 6b)

Written and committed BEFORE any `cb_bw_*` fit was run on real data. The rule
is applied, unchanged, to the development file
`data/45F7AE81-7A79-4CB1-998E-7BD156490294.root` only, by
`python scripts/model_choice.py`. It is not altered after the results are
seen.

## Rule (as specified by the user)

For each channel separately (`Z_mumu`, `Jpsi_mumu`):

1. Scan the Crystal Ball exponent `cb_n` in {1, 2, 3, 5, 10, 20} and choose
   the value with the lowest chi2/ndf.
2. Then compare `voigt_poly`, `cb_bw_exp` and `cb_bw_poly2` on that channel.
   A model is eligible only if
   (a) the fit converged,
   (b) no free parameter is on a bound,
   (c) the background is positive over the fit range.
   Among eligible models choose the lowest chi2/ndf; if two differ by less
   than 5 %, choose the one with the lower AIC.
3. No parameters may be added beyond those listed, and no cut may change.

## How each step is carried out (fixed before running)

These make the rule's wording operational; they were decided before any
result was seen.

- Inputs: the channel's registered `ChannelConfig` (cuts, triggers, histogram
  range and bins, fit range, polynomial degree), all events of the
  development file, through `cmsopen.analyze(..., stability=False)`. Only
  `cb_n` (step 1) and the primary model (step 2) change.
- Step 1 uses `cb_bw_exp`, the model with a positive background by
  construction. The chosen `cb_n` is then used for both `cb_bw_exp` and
  `cb_bw_poly2` in step 2 and stored as the channel's `ChannelConfig.cb_n`.
  A `cb_n` whose fit fails (raises `FitError`: not converged, a parameter on
  a bound or not constrained by the data, peak not significant) is excluded
  from the scan. Ties in chi2/ndf (equal to 4 decimals) go to the smaller n.
- (a) converged: `fit_mass_peak` returned without raising `FitError`.
- (b) no parameter on a bound: `fit_mass_peak` raises `FitError` for a
  parameter on a bound (and for one the data do not constrain), so a model
  that passes (a) passes (b); the check is recorded explicitly anyway by
  comparing each parameter with its bounds.
- (c) positive background: `FitResult.yields_reliable` is True, i.e. no
  `background_negative` warning, which is raised for ANY point of the fit
  range where the fitted background density is below zero (significant or
  not). The exponential of `cb_bw_exp` is positive by construction.
- Selection: the eligible model with the lowest chi2/ndf is the provisional
  choice. Every other eligible model whose chi2/ndf is within 5 % of it
  (chi2/ndf < 1.05 x the lowest) competes with it on AIC; the lowest AIC
  among them wins.
- AIC = chi2 + 2k, with k the number of free parameters: for a binned
  chi2 fit with Gaussian bin errors, -2 ln L = chi2 + constant.
- If no model is eligible, the default stays unchanged and this is reported.
- Outcome: a channel's default model changes (in a separate commit) only if
  the rule selects a model other than its current default (`voigt_poly`).
  `ChannelConfig.cb_n` is set to the scanned value in any case, since step 1
  defines it.

## Results (development file, 2026-10-28)

Development observations from `python scripts/model_choice.py` at commit
5d43970 (rule and script committed before this run). Errors are statistical
only. These are not results of the analysis: they fix analysis choices.

### Z_mumu

Histogram: MassHistogram(60 bins, 60-120 GeV, 26,902 entries, underflow 1,117, overflow 508); fit range 70-110 GeV.

Step 1, cb_n scan (cb_bw_exp):

| cb_n | chi2 / ndf | chi2/ndf | p-value | pole M [GeV] | sigma [GeV] | alpha |
|---|---|---|---|---|---|---|
| 1 | 63.3 / 34 | 1.8619 | 0.00167 | 90.844 +- 0.020 | 1.381 +- 0.026 | 2.114 +- 0.054 |
| 2 | 55.9 / 34 | 1.6438 | 0.0104 | 90.875 +- 0.022 | 1.338 +- 0.029 | 1.728 +- 0.055 |
| 3 | 57.7 / 34 | 1.6974 | 0.00677 | 90.897 +- 0.025 | 1.314 +- 0.032 | 1.516 +- 0.059 |
| 5 | 64.3 / 34 | 1.8898 | 0.0013 | 90.921 +- 0.029 | 1.291 +- 0.036 | 1.311 +- 0.064 |
| 10 | 73.6 / 34 | 2.1647 | 9.66e-05 | 90.943 +- 0.033 | 1.273 +- 0.039 | 1.148 +- 0.067 |
| 20 | 79.7 / 34 | 2.3435 | 1.57e-05 | 90.955 +- 0.036 | 1.265 +- 0.041 | 1.070 +- 0.068 |

Chosen cb_n: 2.0

Step 2, model comparison (cb_n = 2):

| model | eligible | converged | on bound | background > 0 | chi2 / ndf | chi2/ndf | p-value | peak or pole [GeV] | resolution [GeV] | signal yield | background yield | yields reliable | k | AIC |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| voigt_poly | no | yes | none | no | 93.4 / 34 | 2.7477 | 1.9e-07 | 90.783 +- 0.018 | 1.395 +- 0.024 | 24,353 +- 191 | 1,748 +- 118 | no | 6 | 105.4 |
| cb_bw_exp | yes | yes | none | yes | 55.9 / 34 | 1.6438 | 0.0104 | 90.875 +- 0.022 | 1.338 +- 0.029 | 25,531 +- 184 | 608 +- 95 | yes | 6 | 67.9 |
| cb_bw_poly2 | no | yes | none | no | 46.3 / 33 | 1.4039 | 0.0618 | 90.858 +- 0.023 | 1.330 +- 0.029 | 25,114 +- 227 | 1,035 +- 165 | no | 7 | 60.3 |

Eligible: cb_bw_exp. Lowest chi2/ndf: cb_bw_exp (1.6438).
Within 5 % of it: cb_bw_exp.
Selected: cb_bw_exp.

### Jpsi_mumu

Histogram: MassHistogram(50 bins, 2.6-3.6 GeV, 20,587 entries, underflow 171, overflow 1,830); fit range 2.8-3.4 GeV.

Step 1, cb_n scan (cb_bw_exp):

| cb_n | chi2 / ndf | chi2/ndf | p-value | pole M [GeV] | sigma [GeV] | alpha |
|---|---|---|---|---|---|---|
| 1 | 144.1 / 24 | 6.0048 | 4.07e-19 | 3.0925 +- 0.0003 | 0.0321 +- 0.0003 | 2.082 +- 0.048 |
| 2 | 117.6 / 24 | 4.8982 | 2.64e-14 | 3.0927 +- 0.0003 | 0.0317 +- 0.0003 | 1.826 +- 0.047 |
| 3 | 104.2 / 24 | 4.3437 | 5.61e-12 | 3.0929 +- 0.0003 | 0.0314 +- 0.0003 | 1.670 +- 0.045 |
| 5 | 92.0 / 24 | 3.8314 | 6.83e-10 | 3.0931 +- 0.0003 | 0.0312 +- 0.0003 | 1.526 +- 0.044 |
| 10 | 84.0 / 24 | 3.4981 | 1.41e-08 | 3.0933 +- 0.0003 | 0.0310 +- 0.0003 | 1.402 +- 0.044 |
| 20 | 81.1 / 24 | 3.3786 | 4.08e-08 | 3.0934 +- 0.0003 | 0.0309 +- 0.0003 | 1.334 +- 0.043 |

Chosen cb_n: 20.0

Step 2, model comparison (cb_n = 20):

| model | eligible | converged | on bound | background > 0 | chi2 / ndf | chi2/ndf | p-value | peak or pole [GeV] | resolution [GeV] | signal yield | background yield | yields reliable | k | AIC |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| voigt_poly | yes | yes | none | yes | 154.1 / 24 | 6.4217 | 5.66e-21 | 3.0922 +- 0.0003 | 0.0319 +- 0.0003 | 15,658 +- 138 | 3,684 +- 83 | yes | 6 | 166.1 |
| cb_bw_exp | yes | yes | none | yes | 81.1 / 24 | 3.3786 | 4.08e-08 | 3.0934 +- 0.0003 | 0.0309 +- 0.0003 | 16,252 +- 137 | 3,163 +- 75 | yes | 6 | 93.1 |
| cb_bw_poly2 | yes | yes | none | yes | 68.4 / 23 | 2.9740 | 2.14e-06 | 3.0933 +- 0.0003 | 0.0306 +- 0.0003 | 16,061 +- 146 | 3,367 +- 93 | yes | 7 | 82.4 |

Eligible: voigt_poly, cb_bw_exp, cb_bw_poly2. Lowest chi2/ndf: cb_bw_poly2 (2.9740).
Within 5 % of it: cb_bw_poly2.
Selected: cb_bw_poly2.

### Outcome of the rule

- Z_mumu: cb_n = 2.0; selected model cb_bw_exp; default model changes from voigt_poly to cb_bw_exp.
- Jpsi_mumu: cb_n = 20.0; selected model cb_bw_poly2; default model changes from voigt_poly to cb_bw_poly2.

Notes:

- Z_mumu: cb_bw_poly2 has the lowest chi2/ndf but its fitted quadratic
  background is negative somewhere in the fit range, so it fails criterion
  (c) and is not eligible; voigt_poly fails (c) as well.
- Jpsi_mumu: chi2/ndf falls monotonically with cb_n over the whole grid, so
  the chosen value is the largest one scanned (20). The rule fixes the grid;
  it was not extended after seeing this.
- chi2/ndf: benchmark <= 2.0 (T2, evaluated once, on the production sample).
  Observed on the development file with the selected models: Z_mumu
  cb_bw_exp 1.64 (within the benchmark), Jpsi_mumu cb_bw_poly2 2.97 (not
  within it). Development observations only.

## Amendment 1 (written and committed before any amended fit was run)

Reason: on the development file the Jpsi_mumu cb_n scan ended at the edge of
the original grid (n = 20) with chi2/ndf still falling, so the grid did not
contain the minimum the rule asks for.

Change: the cb_n grid is extended, for BOTH channels, to
{1, 2, 3, 5, 10, 20, 30, 50, 100}. Every other part of the rule and of "How
each step is carried out" above is unchanged (the scan uses cb_bw_exp; the
eligibility criteria (a)-(c); lowest chi2/ndf, AIC within 5 %; ties to the
smaller n; no added parameters; no changed cut).

The original Prompt 5 tables and outcome above are kept as they were. The
amended results are added below under "Amendment 1 results", produced by
`python scripts/model_choice.py --grid amended`. A default (cb_n or model)
changes only if the unchanged rule, on the amended grid, selects something
different, in a separate commit with the full test suite passing.

## Amendment 1 results (development file, 2026-10-28)

Development observations from `python scripts/model_choice.py --grid amended`
at commit 6f045bc (Amendment 1 committed before this run). The original
Prompt 5 results above are unchanged.

#### Z_mumu

Histogram: MassHistogram(60 bins, 60-120 GeV, 26,902 entries, underflow 1,117, overflow 508); fit range 70-110 GeV.

Step 1, cb_n scan (cb_bw_exp), grid amended (1, 2, 3, 5, 10, 20, 30, 50, 100):

| cb_n | chi2 / ndf | chi2/ndf | p-value | pole M [GeV] | sigma [GeV] | alpha |
|---|---|---|---|---|---|---|
| 1 | 63.3 / 34 | 1.8619 | 0.00167 | 90.844 +- 0.020 | 1.381 +- 0.026 | 2.114 +- 0.054 |
| 2 | 55.9 / 34 | 1.6438 | 0.0104 | 90.875 +- 0.022 | 1.338 +- 0.029 | 1.728 +- 0.055 |
| 3 | 57.7 / 34 | 1.6974 | 0.00677 | 90.897 +- 0.025 | 1.314 +- 0.032 | 1.516 +- 0.059 |
| 5 | 64.3 / 34 | 1.8898 | 0.0013 | 90.921 +- 0.029 | 1.291 +- 0.036 | 1.311 +- 0.064 |
| 10 | 73.6 / 34 | 2.1647 | 9.66e-05 | 90.943 +- 0.033 | 1.273 +- 0.039 | 1.148 +- 0.067 |
| 20 | 79.7 / 34 | 2.3435 | 1.57e-05 | 90.955 +- 0.036 | 1.265 +- 0.041 | 1.070 +- 0.068 |
| 30 | 81.9 / 34 | 2.4077 | 7.97e-06 | 90.959 +- 0.037 | 1.262 +- 0.042 | 1.045 +- 0.068 |
| 50 | 83.7 / 34 | 2.4604 | 4.55e-06 | 90.962 +- 0.038 | 1.260 +- 0.043 | 1.025 +- 0.068 |
| 100 | 85.0 / 34 | 2.5004 | 2.95e-06 | 90.964 +- 0.039 | 1.259 +- 0.043 | 1.011 +- 0.068 |

Chosen cb_n: 2.0

Step 2, model comparison (cb_n = 2):

| model | eligible | converged | on bound | background > 0 | chi2 / ndf | chi2/ndf | p-value | peak or pole [GeV] | resolution [GeV] | signal yield | background yield | yields reliable | k | AIC |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| voigt_poly | no | yes | none | no | 93.4 / 34 | 2.7477 | 1.9e-07 | 90.783 +- 0.018 | 1.395 +- 0.024 | 24,353 +- 191 | 1,748 +- 118 | no | 6 | 105.4 |
| cb_bw_exp | yes | yes | none | yes | 55.9 / 34 | 1.6438 | 0.0104 | 90.875 +- 0.022 | 1.338 +- 0.029 | 25,531 +- 184 | 608 +- 95 | yes | 6 | 67.9 |
| cb_bw_poly2 | no | yes | none | no | 46.3 / 33 | 1.4039 | 0.0618 | 90.858 +- 0.023 | 1.330 +- 0.029 | 25,114 +- 227 | 1,035 +- 165 | no | 7 | 60.3 |

Eligible: cb_bw_exp. Lowest chi2/ndf: cb_bw_exp (1.6438).
Within 5 % of it: cb_bw_exp.
Selected: cb_bw_exp.

#### Jpsi_mumu

Histogram: MassHistogram(50 bins, 2.6-3.6 GeV, 20,587 entries, underflow 171, overflow 1,830); fit range 2.8-3.4 GeV.

Step 1, cb_n scan (cb_bw_exp), grid amended (1, 2, 3, 5, 10, 20, 30, 50, 100):

| cb_n | chi2 / ndf | chi2/ndf | p-value | pole M [GeV] | sigma [GeV] | alpha |
|---|---|---|---|---|---|---|
| 1 | 144.1 / 24 | 6.0048 | 4.07e-19 | 3.0925 +- 0.0003 | 0.0321 +- 0.0003 | 2.082 +- 0.048 |
| 2 | 117.6 / 24 | 4.8982 | 2.64e-14 | 3.0927 +- 0.0003 | 0.0317 +- 0.0003 | 1.826 +- 0.047 |
| 3 | 104.2 / 24 | 4.3437 | 5.61e-12 | 3.0929 +- 0.0003 | 0.0314 +- 0.0003 | 1.670 +- 0.045 |
| 5 | 92.0 / 24 | 3.8314 | 6.83e-10 | 3.0931 +- 0.0003 | 0.0312 +- 0.0003 | 1.526 +- 0.044 |
| 10 | 84.0 / 24 | 3.4981 | 1.41e-08 | 3.0933 +- 0.0003 | 0.0310 +- 0.0003 | 1.402 +- 0.044 |
| 20 | 81.1 / 24 | 3.3786 | 4.08e-08 | 3.0934 +- 0.0003 | 0.0309 +- 0.0003 | 1.334 +- 0.043 |
| 30 | 80.4 / 24 | 3.3494 | 5.28e-08 | 3.0934 +- 0.0003 | 0.0309 +- 0.0003 | 1.311 +- 0.043 |
| 50 | 79.9 / 24 | 3.3303 | 6.25e-08 | 3.0934 +- 0.0003 | 0.0308 +- 0.0003 | 1.292 +- 0.043 |
| 100 | 79.6 / 24 | 3.3187 | 6.92e-08 | 3.0934 +- 0.0003 | 0.0308 +- 0.0003 | 1.277 +- 0.043 |

Chosen cb_n: 100.0

Step 2, model comparison (cb_n = 100):

| model | eligible | converged | on bound | background > 0 | chi2 / ndf | chi2/ndf | p-value | peak or pole [GeV] | resolution [GeV] | signal yield | background yield | yields reliable | k | AIC |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| voigt_poly | yes | yes | none | yes | 154.1 / 24 | 6.4217 | 5.66e-21 | 3.0922 +- 0.0003 | 0.0319 +- 0.0003 | 15,658 +- 138 | 3,684 +- 83 | yes | 6 | 166.1 |
| cb_bw_exp | yes | yes | none | yes | 79.6 / 24 | 3.3187 | 6.92e-08 | 3.0934 +- 0.0003 | 0.0308 +- 0.0003 | 16,227 +- 136 | 3,189 +- 74 | yes | 6 | 91.6 |
| cb_bw_poly2 | yes | yes | none | yes | 65.5 / 23 | 2.8473 | 5.92e-06 | 3.0934 +- 0.0003 | 0.0306 +- 0.0003 | 16,031 +- 145 | 3,399 +- 91 | yes | 7 | 79.5 |

Eligible: voigt_poly, cb_bw_exp, cb_bw_poly2. Lowest chi2/ndf: cb_bw_poly2 (2.8473).
Within 5 % of it: cb_bw_poly2.
Selected: cb_bw_poly2.

#### Outcome of the unchanged rule on the amended grid

- Z_mumu: selected cb_n = 2.0 (unchanged); selected model cb_bw_exp (unchanged).
- Jpsi_mumu: selected cb_n = 100.0 (differs from the registered 20); selected model cb_bw_poly2 (unchanged).

Notes on Amendment 1:

- Z_mumu: the extended grid changes nothing; chi2/ndf rises monotonically
  above n = 2.
- Jpsi_mumu: chi2/ndf keeps falling up to the new edge (n = 100), but only
  slowly (3.3303 at n = 50, 3.3187 at n = 100; pole and sigma unchanged to
  0.1 MeV). The rule selects n = 100, the new edge. A Crystal Ball with such
  a large n has an essentially exponential tail. No further amendment is
  made here.
- Outcome: Jpsi_mumu cb_n changes from 20 to 100 (separate commit); its
  model (cb_bw_poly2) and everything for Z_mumu are unchanged.

## Amendment 2: a resolution-mixture model (written and committed before any mixture fit on real data)

Motivation (development observations, dev/benchmarks.md and dev/validation_plan.md
results): the per-category fits are adequate (chi2/ndf Z BB 1.12, Z BE 1.00,
J/psi BB 1.42) but the inclusive fits are not (Z 1.64, J/psi 2.85). Barrel and
endcap muons have different momentum resolutions (on the development file the
fitted Z resolution is about 0.97 GeV in BB and 1.46 GeV in BE), so the
inclusive sample is a mixture of resolutions that one Gaussian core cannot
describe. A physically motivated resolution mixture is tested under the rule
below, written before any mixture fit. The user made no prediction of the
outcome.

### Models

- `cb2_bw_exp` and `cb2_bw_poly2`. Signal: a Breit-Wigner (pole M free,
  natural width fixed from the `particle` package) convolved with
  f * CB(sigma1, alpha, n) + (1 - f) * CB(r * sigma1, alpha, n).
  M, alpha and n are shared by the two components; n = the channel's current
  `cb_n` (Z 2, J/psi 100), not re-scanned. Free parameters beyond the
  single-resolution model: r and f. Bounds: r in [1.2, 4.0], f in
  [0.05, 0.95] (all other bounds as for the single-resolution models).
- The Gamma < 0.05 sigma1 branch applies as before (the Crystal Balls alone,
  without the Breit-Wigner, when the natural width is below 0.05 sigma1;
  since r > 1 the wider component is then also far above the width).
- Backgrounds as for the existing CB models: positive exponential
  (`cb2_bw_exp`) or quadratic (`cb2_bw_poly2`).
- Operational details (fixed now): each component is normalised separately
  over the fit bins, so f is the fraction of the in-range signal in the
  narrow component and the amplitude is the number of signal events in the
  fit range; sigma1 is the narrow core (r >= 1.2 > 1 by the bounds).

### Rule, per channel

The default stays the current one unless the mixture variant with the SAME
background as the current default (Z_mumu: `cb2_bw_exp` against `cb_bw_exp`;
Jpsi_mumu: `cb2_bw_poly2` against `cb_bw_poly2`) is

  (a) converged (`fit_mass_peak` returns without `FitError`, which also covers
      a parameter not constrained by the data),
  (b) has no parameter on a bound, including r and f (`FitResult.on_bound`
      empty),
  (c) has a positive background over the fit range (`yields_reliable`), and
  (d) has AIC_mixture <= AIC_default - 10, with AIC = chi2 + 2k and k the
      number of free parameters of each fit, both fitted to the same
      histogram and fit range.

The other mixture model is fitted and reported for information only. No other
parameters, cuts or grids change. The rule is not altered after the results
are seen.

### Reporting

The reported resolution of a mixture fit is the numerical FWHM of the fitted
signal divided by 2.355 (the existing numerical FWHM); sigma1, r and f are
reported beside it.
