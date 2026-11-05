# Method targets

These are targets and controlling benchmarks: requirements fixed before the
production sample is analysed. The only measured values here are the verified
production results promoted to benchmarks under the policy below, each with its
source; other observed values are reported separately, next to the benchmarks
(see "Controlling benchmarks" and "Results integrity" in CLAUDE.md).

## Controlling benchmarks (all-time-highest policy)

Policy: "Controlling benchmarks" in CLAUDE.md. This table is the permanent
historical benchmark registry. Each metric's controlling benchmark is the most
ambitious value ever established for it, whether a target, a requirement or a
verified production result. No lower value displaces it; a verified production
result that beats it becomes the new benchmark; only the user's explicit
written authorization can reduce it. Requirements, project descriptions,
planning documents, acceptance criteria, specifications and prompts use the
controlling value. Summaries show the benchmark (prominent) and the observed
value (measured, met or not met), each clearly labelled.

Verified production results so far: the run of 2026-11-04 (git HEAD
9ebc2e3a8b37; `results/production.json`). The benchmarks it raised are listed
under "Promoted from the production run"; every other benchmark below comes from
targets and requirements.

| metric | direction | controlling benchmark | history (source) |
|---|---|---|---|
| Production sample size | higher | 20 files (12 from record 31129, 8 from 31123) | 20 (AMBITION OVERRIDES 1, T4) |
| Fit adequacy chi2/ndf (final model, production) | lower | <= 2.0, with a positive background everywhere in the fit range | 2.0 (T2, AMBITION OVERRIDES 2) |
| Line coverage of src/cmsopen | higher | >= 96.7 % | 90 % (DoD (h), AMBITION OVERRIDES 2 and 3; `--cov-fail-under=90`), 96.7 % (production run) |
| mypy / ruff findings | lower | 0 (mypy `disallow_untyped_defs`, `warn_unused_ignores`; `ruff check src/`), enforced in CI | 0 (T7, AMBITION OVERRIDES 3) |
| Pull-test toys per pull test | higher | >= 1,000 | 300 (Layer 6 and 6b prompts), 1,000 (AMBITION OVERRIDES 5) |
| Pull mean, abs value | lower | <= 0.2 | 0.2 (Layer 6 and 6b prompts) |
| Pull standard deviation | window | 0.8 to 1.2 | 0.8-1.2 (Layer 6 and 6b prompts) |
| Deliberate-breakage checks per layer | higher | >= 3, each confirmed to fail a test | 2 (Layer 4, 6, 7, 6b prompts), 3 (AMBITION OVERRIDES 5) |
| Validation pairs per category (minimum fitted) | higher | >= 9,704 | 1,500 (Layer 6b prompt default), 5,000 (AMBITION OVERRIDES 5), 9,704 (production run) |
| J/psi opposite-sign pairs in 2.9-3.3 GeV | higher | >= 380,964, clearly visible peak | 2,000 (AMBITION OVERRIDES 6), 380,964 (production run) |
| J/psi sideband signal-to-background | higher | >= 12.16 | 1 (AMBITION OVERRIDES 6), 12.16 (production run) |
| Parallel versus serial results | exact | identical masses, cutflow and fit results | exact (AMBITION OVERRIDES 4 and 7) |
| Reproducibility of summary.json | exact | byte-identical on identical inputs | exact (T1) |
| Run-period consistency | reported | 2012B and 2012C peak and resolution, differences with combined stat. uncertainties | T6 (AMBITION OVERRIDES 2) |
| Mass value | none | no numeric target (T3) | T3 |

### Promoted from the production run

Updated 2026-11-05 on the owner's instruction, for the metrics whose observed value measures the registry's definition
like for like.

| metric | definition | old benchmark | new benchmark | source |
|---|---|---|---|---|
| Line coverage of src/cmsopen | total line coverage of `src/cmsopen` from the full test suite | >= 90 % | >= 96.7 % | gates record of the production commit (`gates.coverage_total` in `results/production.json`) |
| Validation pairs per category (minimum fitted) | smallest number of pairs in a fitted validation entry, over both channels (Z 35,439; J/psi 9,704) | >= 5,000 | >= 9,704 | `results/production_extras.json` |
| J/psi opposite-sign pairs in 2.9-3.3 GeV | opposite-sign pairs in the window, in the Jpsi_mumu channel's saved histogram | >= 2,000 | >= 380,964 | `results/production_extras.json` |
| J/psi sideband signal-to-background | the sideband definition below | >= 1 | >= 12.16 | `results/production_extras.json` |

These benchmarks bind later productions and summaries. They change no analysis choice (the model freeze holds: the
analysis's own minimum of 5,000 pairs per validation entry is unchanged) and no recorded result of the run.

Not promoted:

- **Z stability spread over fit choices** (benchmark < 0.5 GeV, observed 0.0068 GeV): 3 of its 9 grid fits failed, so the
  observed spread does not measure the same grid as the benchmark.
- **chi2/ndf** stays at <= 2.0: it is a consistency window, not a lower-is-better metric, so the Z's observed 1.518 does
  not replace it. The J/psi's observed 3.028 is not met.

J/psi sideband signal-to-background, as evaluated by `scripts/production_extras.py` (the registry gave no formula; this
was written on 2026-11-04, before any production file was opened): in the Jpsi_mumu channel's saved histogram, the signal
window is 2.9-3.3 GeV and the sidebands are the rest of the histogram, 2.6-2.9 and 3.3-3.6 GeV. B is the sideband count
scaled by width (a locally flat background), S is the window count minus B.
This definition was confirmed by the owner on 2026-11-04, before any production file was opened.
Beside it, as a labelled cross-check only (it never sets met or not met): the fitted background integrated over the
window, from the fit parameters in the saved summary. The summary's own `background_yield` covers the fit range, 2.8-3.4
GeV, not the window, and the summary has no covariance matrix, so this cross-check has no uncertainty.

Existing self-check thresholds in examples/ are also benchmarks and may not
be loosened: same-sign pairs in 88-94 GeV below 10 % of opposite-sign pairs
(Layer 4); fitted resolution 0.5-4 GeV, stability spread below 0.5 GeV and the
1.0 GeV sanity window around the PDG mass (Layer 6; a sanity bound, not a
mass target); figure files above 20 kB, PNG size equal to figsize x 300 dpi,
zero layout overlaps, byte-identical regeneration (Layer 7).

## Evaluation

T2, T3, T4 and T6 are evaluated ONCE, on the pre-registered production sample
(`results/production_files.json`). A target that is not met is reported as not
met, together with the measured value; it is not corrected after the fact by
changing the analysis, the sample or the target.

## T1 Reproducibility

A fresh clone, plus fetching the registered input files, plus running
`analyze` reproduces `summary.json` byte for byte on identical inputs.

Check: two independent runs (fresh clone, fresh environment) compared with
`cmp`; any difference fails.

## T2 Fit adequacy

The final signal model gives a positive background everywhere in the fit
range (`FitResult.yields_reliable` is True) and chi2/ndf <= 2.0 on the
production sample, using a physically motivated model only: no ad hoc
parameters added just to improve chi2.

Check: read `yields_reliable`, chi2 and ndf from the production fit result;
the model and its parameters are fixed on the development file beforehand.

## T3 Peak offset

The offset of the fitted peak (or pole) position from the PDG value is
reported with its statistical uncertainty, the fit-choice spread
(`fit_stability`), and at least one diagnostic study of its origin (barrel
versus endcap, mu+ versus mu-). There is NO numeric target on the mass value
itself.

Check: the production summary contains the offset, the statistical error, the
stability spread and the diagnostic tables.

## T4 Statistics

The production sample is the 20 registered files: 12 from CMS Open Data
record 31129 (Run 2012C DoubleMuParked) and 8 from record 31123 (Run 2012B
DoubleMuParked), chosen by the rule recorded in `results/production_files.json`
before any of them is opened.

Check: the production run reads exactly the registered files (names and
checksums) and no others; `scripts/check_blinding.py` confirms the registry is
unchanged.

## T5 Transparency

Every plot and number in the README is reproducible from one command.

Check: the README results block equals the text rendered from
`results/production.json` (`scripts/check_readme_numbers.py`), and the figures
are produced by one documented command.

## T6 Run-period consistency

Peak position and resolution are reported separately for Run 2012B and Run
2012C, with their differences and the combined statistical uncertainties of
those differences, evaluated on the production sample.

Check: the production summary contains both periods' fits, the differences
and their uncertainties.

## T7 Engineering

Line coverage of `src/cmsopen` of at least 90 % from genuine tests (no
coverage exclusions to reach it), `pytest --cov=cmsopen --cov-fail-under=90`;
mypy clean with `disallow_untyped_defs` and `warn_unused_ignores`;
`ruff check src/` clean; all enforced in CI.

Check: the CI run's output. The coverage reported is the measured percentage,
whatever it is.
