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

## Amendment 2 results (development file, 2026-10-29)

Development observations from `python scripts/model_choice.py --amendment2` at
commit 8323935 (Amendment 2 committed at 5e9f276, before any mixture fit on
real data). Errors statistical only. FWHM/2.355 is the numerical FWHM of the
whole fitted signal divided by 2.355; for the Z it includes the natural width,
so it is not comparable with a single-core sigma.

#### Z_mumu (Amendment 2; cb_n = 2, current default cb_bw_exp)

| model | role | eligible | converged | on bound | background > 0 | chi2 / ndf | chi2/ndf | p-value | pole [GeV] | sigma1 [GeV] | r | f | FWHM/2.355 [GeV] | signal yield | background yield | k | AIC |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| cb_bw_exp | current default | yes | yes | none | yes | 55.9 / 34 | 1.6438 | 0.0104 | 90.875 +- 0.022 | 1.338 +- 0.029 | - | - | 2.022 +- 0.025 | 25,531 +- 184 | 608 +- 95 | 6 | 67.9 |
| cb2_bw_exp | candidate | yes | yes | none | yes | 28.5 / 32 | 0.8909 | 0.644 | 90.852 +- 0.023 | 1.218 +- 0.050 | 3.445 +- 0.577 | 0.907 +- 0.029 | 1.961 +- 0.031 | 25,740 +- 224 | 427 +- 158 | 8 | 44.5 |
| cb2_bw_poly2 | information only | yes | yes | none | yes | 28.0 / 31 | 0.9047 | 0.619 | 90.848 +- 0.024 | 1.222 +- 0.051 | 3.471 +- 0.776 | 0.907 +- 0.028 | 1.962 +- 0.032 | 25,710 +- 380 | 457 +- 345 | 9 | 46.0 |

cb2_bw_exp: (a) converged: yes; (b) no parameter on a bound: yes; (c) background positive over the fit range: yes; (d) AIC 44.5 <= 67.9 - 10 = 57.9: yes.
Selected: cb2_bw_exp (changes the default).

#### Jpsi_mumu (Amendment 2; cb_n = 100, current default cb_bw_poly2)

| model | role | eligible | converged | on bound | background > 0 | chi2 / ndf | chi2/ndf | p-value | pole [GeV] | sigma1 [GeV] | r | f | FWHM/2.355 [GeV] | signal yield | background yield | k | AIC |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| cb_bw_poly2 | current default | yes | yes | none | yes | 65.5 / 23 | 2.8473 | 5.92e-06 | 3.0934 +- 0.0003 | 0.0306 +- 0.0003 | - | - | 0.0306 +- 0.0003 | 16,031 +- 145 | 3,399 +- 91 | 7 | 79.5 |
| cb2_bw_exp | information only | yes | yes | none | yes | 27.1 / 22 | 1.2298 | 0.209 | 3.0931 +- 0.0003 | 0.0248 +- 0.0017 | 1.673 +- 0.062 | 0.566 +- 0.128 | 0.0286 +- 0.0005 | 16,427 +- 142 | 3,042 +- 82 | 8 | 43.1 |
| cb2_bw_poly2 | candidate | yes | yes | none | yes | 25.9 / 21 | 1.2332 | 0.21 | 3.0931 +- 0.0003 | 0.0222 +- 0.0025 | 1.685 +- 0.106 | 0.376 +- 0.139 | 0.0282 +- 0.0006 | 16,289 +- 159 | 3,181 +- 111 | 9 | 43.9 |

cb2_bw_poly2: (a) converged: yes; (b) no parameter on a bound: yes; (c) background positive over the fit range: yes; (d) AIC 43.9 <= 79.5 - 10 = 69.5: yes.
Selected: cb2_bw_poly2 (changes the default).

#### Outcome of Amendment 2

- Z_mumu: default cb_bw_exp changes to cb2_bw_exp.
- Jpsi_mumu: default cb_bw_poly2 changes to cb2_bw_poly2.

Notes on Amendment 2:

- Both mixture variants converge with no parameter on a bound and a positive
  background, on both channels. For Z_mumu, cb2_bw_poly2's quadratic
  background is now positive over the fit range (cb_bw_poly2's was not).
- Z_mumu: a narrow core with about 91 % of the signal and a wide core at
  about 3.4 times its width.
- Jpsi_mumu: about 38 % (cb2_bw_poly2) to 57 % (cb2_bw_exp) in the narrow
  core, the wide core about 1.7 times wider.
- Outcome: both defaults change (separate commit): Z_mumu cb_bw_exp ->
  cb2_bw_exp, Jpsi_mumu cb_bw_poly2 -> cb2_bw_poly2; cb_n unchanged.

## Amendment 3: a three-resolution model (written and committed 2026-10-29, prompt 10, before any three-resolution fit)

Motivation (development observations, dev/benchmarks.md, prompt 9): on the
6-file development set the J/psi headline fit (`cb2_bw_poly2`) has chi2/ndf
2.155 (ndf 21) against the benchmark of 2.0. Its residuals show no run
structure (runs test p = 0.47, lag-1 autocorrelation +0.04); the excess chi2
is concentrated in the core and on the left of the peak, and chi2/ndf grows
with the bin width. The momentum resolution varies continuously with
pseudorapidity and transverse momentum, and two Gaussian cores are the
coarsest approximation of that continuum; a third core is the next one. This
amendment tests it under the rule below, written before any three-resolution
fit. The user made no prediction of the outcome.

### Models

- `cb3_bw_exp` and `cb3_bw_poly2`. Signal: a Breit-Wigner (pole M free,
  natural width fixed from the `particle` package) convolved with
  f1 * CB(sigma1) + (1 - f1) * [g * CB(r2 * sigma1) + (1 - g) * CB(r2 * s * sigma1)].
  The three Crystal Balls share M, alpha and n; n = the channel's current
  `cb_n` (Z 2, J/psi 100), not re-scanned. Free parameters beyond the
  two-resolution model: s and g.
- Bounds (fixed now): r2 in [1.2, 3.0], s in [1.2, 3.0], f1 in [0.05, 0.90],
  g in [0.05, 0.95]; all other bounds as for the two-resolution models. With
  r2 > 1 and s > 1 the three widths sigma1 < r2 * sigma1 < r2 * s * sigma1
  are ordered by construction.
- The Gamma < 0.05 sigma1 branch applies (decided once, from sigma1, for all
  three components).
- Backgrounds as for the existing CB models: positive exponential
  (`cb3_bw_exp`) or quadratic (`cb3_bw_poly2`).
- Operational details (fixed now): each component is normalised separately
  over the fit bins, so f1 is the fraction of the in-range signal in the
  narrowest component and g the fraction of the remainder in the middle one;
  the amplitude is the number of signal events in the fit range. The
  reported resolution is the numerical FWHM of the fitted signal divided by
  2.355, with sigma1, r2, s, f1 and g beside it.

### Evaluation set

The 6-file development set (dev/development_set.md), in its fixed order;
identifiability of a third core needs the statistics. The original
development file alone is fitted and reported for information only.

### Rule, per channel

The default stays the current one (Z_mumu `cb2_bw_exp`, Jpsi_mumu
`cb2_bw_poly2`) unless the three-resolution variant with the SAME background
(Z_mumu: `cb3_bw_exp`; Jpsi_mumu: `cb3_bw_poly2`), fitted to the same 6-file
histogram and fit range, is

  (a) converged (`fit_mass_peak` returns without `FitError`),
  (b) has no parameter on a bound (`FitResult.on_bound` empty) and passes the
      unconstrained-parameter check (also part of `fit_mass_peak`),
  (c) has a positive background over the fit range (`yields_reliable`), and
  (d) has AIC_cb3 <= AIC_default - 10, with AIC = chi2 + 2k and k the number
      of free parameters of each fit.

The other cb3 model is fitted and reported for information only. No other
parameter, cut, bin width or fit range changes. The rule is not altered
after the results are seen.

### Statement

This is the last J/psi line-shape amendment before the production run. If
the rule does not select a cb3 model, or the selected model's chi2/ndf stays
above the benchmark of 2.0, that is the recorded observation; the benchmark
is not lowered or reinterpreted.

## Amendment 3 results (2026-10-29, prompt 10)

Applied with `python scripts/model_choice.py --amendment3` (6-file
development set) and `--amendment3 --single` (original development file,
information only), at the channels' current cb_n. A model that raises
FitError has no fitted values to tabulate; its row gives the reason.

### 6-file development set (the evaluation set)

#### Z_mumu

| model | role | eligible | chi2 / ndf | chi2/ndf | p-value | pole [GeV] | sigma1 [GeV] | r (r2) | s | f (f1) | g | FWHM/2.355 [GeV] | signal yield | background yield | k | AIC | on a bound |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| cb2_bw_exp | current default | yes | 26.4 / 32 | 0.8237 | 0.748 | 90.893 +- 0.009 | 1.157 +- 0.053 | 2.166 +- 0.131 | - | 0.786 +- 0.061 | - | 1.991 +- 0.014 | 169,753 +- 486 | 3,975 +- 266 | 8 | 42.4 | none |
| cb3_bw_exp | candidate | no: cb3_bw_exp fit over 70-110 GeV: parameter(s) ['s', 'g'] ended on a bound (s=3, g=0.95); there is no well-defined peak to measure | | | | | | | | | | | | | | | |
| cb3_bw_poly2 | information only | no: cb3_bw_poly2 fit over 70-110 GeV: parameter(s) ['r2', 's', 'f1', 'g'] not constrained by the data (r2=1.2 +- 26, s=1.766 +- 47, f1=0.6001 +- 38, g=0.3771 +- 56) | | | | | | | | | | | | | | | |

(a)/(b) cb3_bw_exp raised FitError (not converged, a parameter on a bound or not constrained): not eligible. Selected: cb2_bw_exp (unchanged).

#### Jpsi_mumu

| model | role | eligible | chi2 / ndf | chi2/ndf | p-value | pole [GeV] | sigma1 [GeV] | r (r2) | s | f (f1) | g | FWHM/2.355 [GeV] | signal yield | background yield | k | AIC | on a bound |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| cb2_bw_poly2 | current default | yes | 45.2 / 21 | 2.1546 | 0.00161 | 3.0934 +- 0.0001 | 0.0238 +- 0.0006 | 1.783 +- 0.030 | - | 0.581 +- 0.041 | - | 0.0274 +- 0.0002 | 101,824 +- 426 | 19,819 +- 316 | 9 | 63.2 | none |
| cb3_bw_exp | information only | no: cb3_bw_exp fit over 2.8-3.4 GeV: parameter(s) ['s'] ended on a bound (s=3); there is no well-defined peak to measure | | | | | | | | | | | | | | | |
| cb3_bw_poly2 | candidate | no: cb3_bw_poly2 fit over 2.8-3.4 GeV: parameter(s) ['f1'] ended on a bound (f1=0.05); there is no well-defined peak to measure | | | | | | | | | | | | | | | |

(a)/(b) cb3_bw_poly2 raised FitError (not converged, a parameter on a bound or not constrained): not eligible. Selected: cb2_bw_poly2 (unchanged).

Outcome: neither cb3 model is eligible in either channel ((a)/(b): a
parameter ends on a bound, or is not constrained by the data). The rule
selects nothing: Z_mumu stays `cb2_bw_exp`, Jpsi_mumu stays `cb2_bw_poly2`.
As stated in the amendment, the J/psi headline chi2/ndf of 2.155 on the
6-file development set, above the benchmark of 2.0, is the recorded
observation; the benchmark is not lowered or reinterpreted. This was the
last J/psi line-shape amendment before the production run.

### Original development file (information only)

#### Z_mumu

| model | role | eligible | chi2 / ndf | chi2/ndf | p-value | pole [GeV] | sigma1 [GeV] | r (r2) | s | f (f1) | g | FWHM/2.355 [GeV] | signal yield | background yield | k | AIC | on a bound |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| cb2_bw_exp | current default | yes | 28.5 / 32 | 0.8909 | 0.644 | 90.852 +- 0.023 | 1.218 +- 0.050 | 3.445 +- 0.577 | - | 0.907 +- 0.029 | - | 1.961 +- 0.031 | 25,740 +- 224 | 427 +- 158 | 8 | 44.5 | none |
| cb3_bw_exp | candidate | no: cb3_bw_exp fit over 70-110 GeV: parameter(s) ['r2', 's', 'f1', 'g'] not constrained by the data (r2=1.2 +- 4.6e+02, s=2.876 +- 1.1e+03, f1=0.9 +- 29, g=0.07016 +- 2.7e+02) | | | | | | | | | | | | | | | |
| cb3_bw_poly2 | information only | no: cb3_bw_poly2 fit over 70-110 GeV: parameter(s) ['r2', 'f1'] ended on a bound (r2=1.2, f1=0.9); there is no well-defined peak to measure | | | | | | | | | | | | | | | |

(a)/(b) cb3_bw_exp raised FitError (not converged, a parameter on a bound or not constrained): not eligible. Selected: cb2_bw_exp (unchanged).

#### Jpsi_mumu

| model | role | eligible | chi2 / ndf | chi2/ndf | p-value | pole [GeV] | sigma1 [GeV] | r (r2) | s | f (f1) | g | FWHM/2.355 [GeV] | signal yield | background yield | k | AIC | on a bound |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| cb2_bw_poly2 | current default | yes | 25.9 / 21 | 1.2332 | 0.21 | 3.0931 +- 0.0003 | 0.0222 +- 0.0025 | 1.685 +- 0.106 | - | 0.376 +- 0.139 | - | 0.0282 +- 0.0006 | 16,289 +- 159 | 3,181 +- 111 | 9 | 43.9 | none |
| cb3_bw_exp | information only | no: cb3_bw_exp fit over 2.8-3.4 GeV: parameter(s) ['f1'] ended on a bound (f1=0.05); there is no well-defined peak to measure | | | | | | | | | | | | | | | |
| cb3_bw_poly2 | candidate | no: cb3_bw_poly2 fit over 2.8-3.4 GeV: parameter(s) ['f1'] ended on a bound (f1=0.05); there is no well-defined peak to measure | | | | | | | | | | | | | | | |

(a)/(b) cb3_bw_poly2 raised FitError (not converged, a parameter on a bound or not constrained): not eligible. Selected: cb2_bw_poly2 (unchanged).

### Diagnostics of the standing defaults (information)

No default changed. The statistics-scaling table, the per-file chi2/ndf and
poles, the chi2/ndf over the fit-range x bin-width grid and the
core/left/right chi2 split were recomputed (`scripts/rehearsal.py rest`) and
are identical to the prompt 9 values in dev/benchmarks.md.

## Model freeze (2026-10-29, prompt 11)

Frozen at commit `35af6445db8d601972e60d3ba03f7c19a99527bb` (START11; the
configuration lives in `src/cmsopen/pipeline.py`, blob `0b910b2` at that
commit). Validation plan: dev/validation_plan.md, blob `9f9492b` at that
commit (the plan with its addenda of prompts 7, 8 and 10).

| | Z_mumu | Jpsi_mumu |
|---|---|---|
| default model | `cb2_bw_exp` (Amendment 2) | `cb2_bw_poly2` (Amendment 2) |
| cb_n (fixed) | 2 | 100 (Amendment 1) |
| validation model | `cb_bw_exp` | `cb_bw_poly2` |
| histogram range, bin width | 60-120 GeV, 1 GeV (60 bins) | 2.6-3.6 GeV, 0.02 GeV (50 bins) |
| fit range | 70-110 GeV | 2.8-3.4 GeV |
| polynomial degree (alternate fits) | 2 | 2 |
| trigger (any of) | HLT_Mu17_Mu8, HLT_Mu17_TkMu8 | HLT_Dimuon8_Jpsi, HLT_Dimuon10_Jpsi |
| muon cuts | pT > 20 GeV, abs(eta) < 2.4, tight ID, PF relative isolation (cone 0.4) < 0.12 | pT > 3 GeV, abs(eta) < 2.4, soft ID |
| events | at least two selected muons | at least two selected muons |
| pair choice | opposite charge, the pair with the highest pT sum (mass-blind) | same |
| minimum pairs in the fit range | 100 | 100 |
| stability grid: fit ranges | 70-110, 75-105, 80-100 GeV | 2.8-3.4, 2.85-3.35, 2.9-3.3 GeV |
| stability grid: bin widths | 0.5, 1, 2 GeV | 0.01, 0.02, 0.04 GeV |
| natural width | from the `particle` package | from the `particle` package |

Validation: at least 5,000 pairs per entry; categories, charge, pT, pileup
and working-point scans as in the plan; scaled errors as in its prompt 10
addendum.

Rule: from now on, any change to these requires the user's explicit
approval and a recorded amendment written before the change. A bug fix that
alters any result is reported to the user before it is committed.
