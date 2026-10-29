# Validation plan (Layer 6b)

Pre-registered: written and committed BEFORE any validation fit on real data
(and before any category or bin was counted). Every edge, threshold and
definition below is fixed here and is not changed after the results are seen.
It applies to the development file
`data/45F7AE81-7A79-4CB1-998E-7BD156490294.root` now and to the production
sample later, unchanged. There is NO numeric target on the mass: everything
is reported as measured.

## Inputs

For each channel (`Z_mumu`, `Jpsi_mumu`) the channel's registered
`ChannelConfig` is used unchanged: trigger, muon cuts, candidate strategy
(one opposite-sign pair per event, `highest_pt_sum`), histogram range and
bins, fit range, polynomial degree, `cb_n` and the default model
(`cb_bw_exp` for Z_mumu, `cb_bw_poly2` for Jpsi_mumu, chosen by
dev/model_choice.md). The "inclusive" entry is the fit of all selected pairs
with that model: exactly `cmsopen.analyze(file, channel=...)`.

A "pair" below is the chosen opposite-sign pair of an event; its mu+ and
mu- are its positive and negative muon. Only pairs whose mass is inside the
channel's fit range count towards an entry's size.

## Categories and bins

1. Detector regions (a partition of all pairs). Barrel: |eta| < 1.2;
   endcap: 1.2 <= |eta| <= 2.4 (the selection already requires
   |eta| < 2.4 for both channels). A pair is
   - BB if both muons are barrel,
   - BE if one is barrel and the other endcap,
   - EE if both are endcap.
2. Charge studies (each a partition of all pairs):
   - phi of the mu+, 4 equal bins: [-pi, -pi/2), [-pi/2, 0), [0, pi/2),
     [pi/2, pi];
   - phi of the mu-, the same 4 bins;
   - signed eta of the mu+, 3 bins with edges -2.4, -0.8, 0.8, 2.4
     ([-2.4, -0.8), [-0.8, 0.8), [0.8, 2.4]);
   - signed eta of the mu-, the same 3 bins.
3. Transverse momentum of the sub-leading muon (the lower-pT muon of the
   pair), fixed physical edges per channel (a partition):
   - Z_mumu: [20, 30), [30, 40), [40, 50), [50, inf) GeV. The selection
     cut is 20 GeV; Z muons peak near m_Z / 2 ~ 45 GeV (the Jacobian
     peak), so the bins cover the turn-on region, the rise, the peak and
     the high tail.
   - Jpsi_mumu: [3, 4), [4, 6), [6, 10), [10, inf) GeV. The selection cut
     is 3 GeV; soft J/psi muons are mostly below 10 GeV, and the bins
     double in width as the spectrum falls.
4. Pileup, on the event's `PV_npvsGood` (number of good primary vertices):
   [0, 15), [15, 23), [23, inf) (a partition).
5. Working points (overlapping samples, NOT partitions): the full
   selection is rerun with `quality_id` in {medium, tight} crossed with
   `max_rel_iso` (pfRelIso04_all) in {0.08, 0.12, 0.20}: six samples.
   The working point replaces the channel's `quality_id` and `max_rel_iso`
   cuts; every other cut, the trigger and the pair choice are unchanged.
   For Z_mumu the nominal working point (tight, 0.12) is one of the six;
   for Jpsi_mumu the nominal selection (soft ID, no isolation) is not, so
   all six are variations of it (medium/tight ID and an isolation cut are
   tighter than the J/psi nominal).

## Minimum size

Every category, bin and working-point sample must have at least 5,000
pairs in the fit range. Otherwise the entry is reported as
"insufficient statistics (n = <pairs>)", it is NOT fitted, and the
threshold is NOT lowered: the production run will fill these entries.

A fit of a sufficient entry that fails (raises `FitError`, for example a
parameter the data do not constrain) is reported as "fit failed: <reason>";
it is not refitted with another model, range or binning.

## Reported per entry

Model; pole (cb_bw_*) or peak (voigt_poly) position and its statistical
error; resolution and its error; chi2/ndf; pairs in the fit range; signal
yield (with "yields not reliable" where the fit's background goes
negative). Plus the difference to the inclusive result,
Delta = m_entry - m_inclusive, in units of the combined statistical error
sqrt(sigma_entry^2 + sigma_inclusive^2). Caveat, stated with the numbers:
an entry is a subset of the inclusive sample (or, for working points,
overlaps it), so the two errors are correlated and this combined error
OVERSTATES the uncertainty of the difference; the number is a simple,
conservative measure of consistency, not a significance.

## systematics_summary (per channel)

Reported as measured, with no target on the mass:

- Peak (pole) offset from the PDG mass (`particle` package), with the
  statistical error, for the inclusive default-model fit.
- Fit-choice spread:
  - model: voigt_poly, cb_bw_exp and cb_bw_poly2 on the inclusive sample,
    each labelled eligible or not by the criteria of dev/model_choice.md
    ((a) converged, (b) no parameter on a bound, (c) background positive
    over the fit range); the spread is max - min over the eligible ones;
  - fit range and bin width: the default model over the channel's
    `stability_fit_ranges` x `stability_bin_widths` grid (9 fits), spread
    max - min and standard deviation;
  - background: the default model's signal shape with the other
    background (cb_bw_exp <-> cb_bw_poly2) at the nominal range and
    binning, reported as the difference to the nominal.
- Largest category spread: max - min of the fitted BB, BE, EE positions
  (fitted entries only), and the largest |Delta| / combined error.
- mu+ minus mu- difference: for each charge-study binning (phi, signed
  eta), the bin-by-bin difference m(mu+ in bin) - m(mu- in bin) with its
  combined error, for bins where both are fitted; reported are every
  difference, the largest |difference|, and the inverse-variance weighted
  mean of the differences over all such bins.
- Working-point spread: max - min of the fitted positions over the six
  working points.

A measured offset or spread is a measured shift, not an error bar: it is
reported as what it is, and turning it into a systematic uncertainty (or a
correction) is a separate, later decision.

## Expected sizes on the development file

(Counts only, no fits; added in a separate commit after this plan was
committed. They do not change anything above.)
