# Method targets

These are targets: requirements fixed before the production sample is
analysed. They are not results. This file contains no measured values, and a
target is never reported as achieved unless the measurement shows it was met
(see "Results integrity" in CLAUDE.md).

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
