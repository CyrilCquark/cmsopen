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

## Results

(Filled in after running `python scripts/model_choice.py` on the
development file; see below.)
