# Validation and systematics

All values on this page are **observed** on the production sample and generated from `results/production.json`.
Benchmarks are labelled as such. Scans use the channel's validation model, which has one resolution core, because each
scan entry has fewer pairs than the inclusive sample; their reference is the same model on all pairs. Entries need at
least 5,000 pairs (the controlling benchmark for validation pairs per category).

`d/s` is the difference from that reference in units of the raw statistical error; `S` is the scale factor
sqrt(χ²/ndf), floored at one, and `d/s scaled` uses the scaled error. A large `d/s` means the peak depends on the
category, which uncorrected momentum scales can produce. Values are reported as they came out.

## Benchmarks and observed values

| target | **controlling benchmark** | observed | status |
|---|---|---|---|
| T1 Reproducibility | **summary.json byte-identical on a repeated run (parallel, then serial), every channel** | Z: byte-identical; J/ψ: byte-identical | met |
| T2 Fit adequacy | **chi2/ndf <= 2.0 with a positive background in the fit range** | Z: χ²/ndf 1.518, background positive; J/ψ: χ²/ndf 3.028, background positive | Z: met; J/ψ: not met |
| T3 Peak offset reported | **offset from PDG with raw and scaled stat. errors, fit-choice spread and the diagnostic studies (barrel/endcap, mu+ vs mu-) reported; no numeric target on the mass** | Z: -0.2879 ± 0.0050 (stat.) GeV, fit-choice spread 0.0028 GeV, 8 diagnostic studies; J/ψ: -0.00358 ± 0.00007 (stat.) GeV, fit-choice spread 0.00006 GeV, 8 diagnostic studies | met |
| T4 Statistics | **20 files (12 from record 31129, 8 from record 31123)** | 20 files (12 from record 31129, 8 from record 31123) | met |
| T5 Transparency | **cutflow, files by record and size, commit, environment hash, attempts and timings recorded; the README block is checked afterwards by scripts/check_readme_numbers.py** | recorded: attempts, cutflow, environment sha256, files by record and size, git head, timings | met |
| T6 Run-period consistency | **2012B and 2012C peak and resolution with differences and combined stat. errors, every channel (reported, no threshold)** | Z peak -0.0184 ± 0.0103 GeV (-1.78 σ); Z resolution -0.0059 ± 0.0157 GeV (-0.38 σ); J/ψ peak +0.00000 ± 0.00016 GeV (+0.02 σ); J/ψ resolution +0.00001 ± 0.00026 GeV (+0.03 σ) | met |
| T7 Engineering | **full test suite and quality gates (coverage >= 90 %, mypy and ruff clean) passed at the production HEAD** | record for commit 9ebc2e3a8b37: pytest exit 0, quality exit 0, coverage 96.7%; 494 passed, 2 skipped in 1807.17s (0:30:07) | met |

## Every benchmark in the registry

| metric | **controlling benchmark** | observed | status | source of the observed value |
|---|---|---|---|---|
| Production sample size | **20 files (12 from record 31129, 8 from 31123)** | 20 files (12 from record 31129, 8 from record 31123) | met | results/production.json |
| Fit adequacy chi2/ndf (final model, production) | **<= 2.0, with a positive background everywhere in the fit range** | Z 1.518 (met); J/ψ 3.028 (not met) | not met for every channel | results/production.json |
| Line coverage of src/cmsopen | **>= 90 % (`--cov-fail-under=90`)** | 96.7 % | met | gates record of the production commit |
| mypy / ruff findings | **0 (mypy `disallow_untyped_defs`, `warn_unused_ignores`; `ruff check src/`), enforced in CI** | 0 findings (quality gates exit 0) | met | gates record of the production commit |
| Pull-test toys per pull test | **>= 1,000** | 1,000 toys in each of 6 tests; up to 34 failed fits per test, whose pulls are not counted | met | from the test suite, not production data |
| Pull mean, abs value | **<= 0.2** | peak position: largest 0.103; every fitted parameter: largest 0.439 (g) | met for the peak position | from the test suite, not production data |
| Pull standard deviation | **0.8 to 1.2** | peak position: 0.976 to 1.039; every fitted parameter: 0.860 to 1.086 | met for the peak position | from the test suite, not production data |
| Deliberate-breakage checks per layer | **>= 3, each confirmed to fail a test** | not derivable: these checks were run by hand during development and no per-layer count was recorded; the commit history does not give one | not derivable | n/a |
| Validation pairs per category (minimum fitted) | **>= 5,000** | Z smallest fitted entry 35,439; J/ψ smallest fitted entry 9,704 | met | results/production.json |
| J/psi opposite-sign pairs in 2.9-3.3 GeV | **>= 2,000, clearly visible peak** | 380,964 pairs (peak: see the J/ψ figure) | met | saved histogram of the run |
| J/psi sideband signal-to-background | **>= 1** | 12.16 (cross-check only, not the benchmark's method: fitted background in the window 44,908, S/B 7.48) | met | saved histogram of the run; cross-check from the saved fit |
| Parallel versus serial results | **identical masses, cutflow and fit results** | Z: byte-identical; J/ψ: byte-identical | met | results/production.json |
| Reproducibility of summary.json | **byte-identical on identical inputs** | Z: byte-identical; J/ψ: byte-identical | met | results/production.json |
| Run-period consistency | **2012B and 2012C peak and resolution, differences with combined stat. uncertainties** | Z peak -0.0184 ± 0.0103 GeV (-1.78 σ); Z resolution -0.0059 ± 0.0157 GeV (-0.38 σ); J/ψ peak +0.00000 ± 0.00016 GeV (+0.02 σ); J/ψ resolution +0.00001 ± 0.00026 GeV (+0.03 σ) | reported | results/production.json |
| Mass value | **no numeric target (T3)** | Z offset from PDG -0.2879 GeV; J/ψ offset from PDG -0.00358 GeV | reported | results/production.json |
| Same-sign pairs in 88-94 GeV (fraction of opposite-sign) | **< 10 %** | not derivable: the run saves only the number of same-sign pairs, not their masses, so none can be counted in a mass window | not derivable | n/a |
| Fitted Z resolution | **0.5-4 GeV** | 1.982 GeV | met | results/production.json |
| Z stability spread over fit choices | **< 0.5 GeV** | 0.0068 GeV | met | results/production.json |
| Z peak sanity window around the PDG mass (not a mass target) | **within 1.0 GeV** | -0.2879 GeV | met | results/production.json |
| Figure file size | **> 20 kB** | smallest 57 kB | met | docs/figures/ |
| PNG size equal to figsize x 300 dpi | **exact** | not derivable: the run does not save figsize; the PNGs are 300 to 300 dpi | not derivable | n/a |
| Layout overlaps in the figures | **0** | not derivable: checked by the tests on other inputs; the production figures' layout is not measured in the run | not derivable | n/a |
| Byte-identical regeneration of the figures | **exact** | not derivable: checked by the tests on other inputs; the figures were written once in the run | not derivable | n/a |

**Not met:** Fit adequacy chi2/ndf (final model, production). **Not derivable:** Deliberate-breakage checks per layer; Same-sign pairs in 88-94 GeV (fraction of opposite-sign); PNG size equal to figsize x 300 dpi; Layout overlaps in the figures; Byte-identical regeneration of the figures.

## Summary

| study (observed) | Z → μ⁺μ⁻ | J/ψ → μ⁺μ⁻ |
|---|---|---|
| Spread over barrel/endcap categories | 0.2444 GeV | 0.00465 GeV |
| Largest category deviation, in σ | 11.99 raw, 5.74 scaled | 18.63 raw, 6.03 scaled |
| Largest μ⁺ minus μ⁻ difference | 0.2469 GeV | 0.00015 GeV |
| Spread over working points | 0.0221 GeV | 0.00024 GeV |
| Spread over signal models | 0.0189 GeV | 0.00130 GeV |
| Fit-choice standard deviation | 0.0028 GeV | 0.00006 GeV |
| Other background shape | -0.0046 GeV (cb2_bw_poly2) | +0.00006 GeV (cb2_bw_exp) |

## Run-period consistency (T6)

| difference (observed) | value | in σ |
|---|---|---|
| Z → μ⁺μ⁻ peak | -0.0184 ± 0.0103 GeV | -1.78 σ |
| Z → μ⁺μ⁻ resolution | -0.0059 ± 0.0157 GeV | -0.38 σ |
| J/ψ → μ⁺μ⁻ peak | +0.00000 ± 0.00016 GeV | +0.02 σ |
| J/ψ → μ⁺μ⁻ resolution | +0.00001 ± 0.00026 GeV | +0.03 σ |

## Z: scans

| study | entry | pairs | position [GeV] | χ²/ndf | d/s | S | d/s scaled | status |
|---|---|---|---|---|---|---|---|---|
| region | BB | 217,808 | 90.9975 ± 0.0077 | 3.040 | +9.14 | 1.74 | +3.93 | fitted |
| region | BE | 255,067 | 90.8889 ± 0.0072 | 4.217 | -2.93 | 2.05 | -1.15 | fitted |
| region | EE | 111,841 | 90.7532 ± 0.0125 | 3.300 | -11.99 | 1.82 | -5.74 | fitted |
| phi(mu+) | [-pi, -pi/2) | 144,952 | 90.8836 ± 0.0096 | 4.653 | -2.85 | 2.16 | -1.16 | fitted |
| phi(mu+) | [-pi/2, 0) | 147,792 | 91.0013 ± 0.0098 | 3.010 | +7.95 | 1.73 | +3.68 | fitted |
| phi(mu+) | [0, pi/2) | 144,138 | 90.9897 ± 0.0099 | 3.002 | +6.83 | 1.73 | +3.17 | fitted |
| phi(mu+) | [pi/2, pi] | 147,834 | 90.7888 ± 0.0095 | 5.408 | -11.72 | 2.33 | -4.55 | fitted |
| phi(mu-) | [-pi, -pi/2) | 144,314 | 90.9474 ± 0.0100 | 2.666 | +2.99 | 1.63 | +1.43 | fitted |
| phi(mu-) | [-pi/2, 0) | 147,933 | 90.8354 ± 0.0095 | 6.427 | -7.36 | 2.54 | -2.70 | fitted |
| phi(mu-) | [0, pi/2) | 143,953 | 90.8425 ± 0.0096 | 3.722 | -6.68 | 1.93 | -2.90 | fitted |
| phi(mu-) | [pi/2, pi] | 148,516 | 91.0357 ± 0.0098 | 2.835 | +11.12 | 1.68 | +5.23 | fitted |
| eta(mu+) | [-2.4, -0.8) | 171,511 | 90.8696 ± 0.0093 | 4.069 | -4.27 | 2.02 | -1.80 | fitted |
| eta(mu+) | [-0.8, 0.8) | 239,639 | 90.9595 ± 0.0072 | 3.036 | +5.19 | 1.74 | +2.19 | fitted |
| eta(mu+) | [0.8, 2.4] | 173,566 | 90.8801 ± 0.0092 | 4.888 | -3.28 | 2.21 | -1.31 | fitted |
| eta(mu-) | [-2.4, -0.8) | 173,108 | 90.8538 ± 0.0091 | 3.771 | -5.86 | 1.94 | -2.51 | fitted |
| eta(mu-) | [-0.8, 0.8) | 236,245 | 90.9764 ± 0.0074 | 3.129 | +7.01 | 1.77 | +2.96 | fitted |
| eta(mu-) | [0.8, 2.4] | 175,363 | 90.8771 ± 0.0091 | 4.939 | -3.61 | 2.22 | -1.43 | fitted |
| pT(sublead) | [20, 30) GeV | 118,639 | 90.8315 ± 0.0150 | 12.403 | -5.24 | 3.52 | -1.49 | fitted |
| pT(sublead) | [30, 40) GeV | 262,500 |  |  |  |  |  | fit failed: cb_bw_exp fit over 70-110 GeV: the covariance matrix is not finite and positive |
| pT(sublead) | [40, 50) GeV | 194,985 |  |  |  |  |  | fit failed: cb_bw_exp fit over 70-110 GeV: parameter(s) ['alpha'] not constrained by the data (alpha=9.95 +- 7.8e-11); the data show no radiative tail for the Crystal Ball to describe |
| pT(sublead) | [50, inf) GeV | 8,592 |  |  |  |  |  | fit failed: cb_bw_exp fit over 70-110 GeV: parameter(s) ['alpha'] not constrained by the data (alpha=6.578 +- 6.3e+06); the data show no radiative tail for the Crystal Ball to describe |
| PV_npvsGood | [0, 15) | 332,737 | 90.9098 ± 0.0065 | 6.073 | -0.56 | 2.46 | -0.20 | fitted |
| PV_npvsGood | [15, 23) | 216,540 | 90.9224 ± 0.0079 | 4.996 | +0.87 | 2.24 | +0.34 | fitted |
| PV_npvsGood | [23, inf) | 35,439 | 90.9136 ± 0.0189 | 1.998 | -0.03 | 1.41 | -0.02 | fitted |
| working point | medium, iso < 0.08 | 418,525 | 90.9307 ± 0.0055 | 8.568 | +2.23 | 2.93 | +0.71 | fitted |
| working point | medium, iso < 0.12 | 550,080 | 90.9169 ± 0.0050 | 9.265 | +0.39 | 3.04 | +0.12 | fitted |
| working point | medium, iso < 0.2 | 658,879 | 90.9118 ± 0.0048 | 9.683 | -0.36 | 3.11 | -0.11 | fitted |
| working point | tight, iso < 0.08 | 443,662 | 90.9283 ± 0.0054 | 10.422 | +1.93 | 3.23 | +0.59 | fitted |
| working point | tight, iso < 0.12 | 584,716 | 90.9143 ± 0.0049 | 11.419 | +0.00 | 3.38 | +0.00 | fitted |
| working point | tight, iso < 0.2 | 701,612 | 90.9086 ± 0.0047 | 12.421 | -0.85 | 3.52 | -0.25 | fitted |

## Z: fit-choice stability

| fit range [GeV] | bin width [GeV] | peak [GeV] | χ²/ndf | p-value |
|---|---|---|---|---|
| 70-110 | 0.5 | 90.9001 ± 0.0049 | 1.277 | 0.0566 |
| 70-110 | 1 | 90.9000 ± 0.0050 | 1.518 | 0.0305 |
| 70-110 | 2 | 90.8989 ± 0.0052 | 1.622 | 0.0779 |
| 75-105 | 0.5 | 90.8959 ± 0.0051 | 1.242 | 0.113 |
| 75-105 | 1 | 90.8955 ± 0.0051 | 1.400 | 0.1 |
| 76-104 | 2 | 90.8933 ± 0.0055 | 1.128 | 0.343 |

Fit choices that did not give a fit:

- cb2_bw_exp fit over 80-100 GeV: parameter(s) ['alpha'] not constrained by the data (alpha=8.093 +- 2.6e-08); the data show no radiative tail for the Crystal Ball to describe
- cb2_bw_exp fit over 80-100 GeV: parameter(s) ['alpha'] not constrained by the data (alpha=7.751 +- 8.9e-09); the data show no radiative tail for the Crystal Ball to describe
- cb2_bw_exp fit over 80-100 GeV: parameter(s) ['alpha', 'f'] not constrained by the data (alpha=9.397 +- 4.9e-09, f=0.4683 +- 0.51); the data show no radiative tail for the Crystal Ball to describe

## Z: per-file fits (files by index)

| index | record | period | pairs | peak [GeV] | χ²/ndf | status |
|---|---|---|---|---|---|---|
| 3 | 31129 | Run2012C | 31,197 | 90.9159 ± 0.0217 | 0.731 | fitted |
| 9 | 31129 | Run2012C | 32,008 | 90.9069 ± 0.0220 | 0.410 | fitted |
| 15 | 31129 | Run2012C | 33,238 | 90.9069 ± 0.0206 | 1.162 | fitted |
| 21 | 31129 | Run2012C | 29,334 | 90.8801 ± 0.0222 | 1.191 | fitted |
| 27 | 31129 | Run2012C | 30,896 | 90.9210 ± 0.0216 | 1.288 | fitted |
| 33 | 31129 | Run2012C | 28,958 | 90.8965 ± 0.0224 | 0.706 | fitted |
| 40 | 31129 | Run2012C | 29,423 | 90.9486 ± 0.0219 | 0.910 | fitted |
| 46 | 31129 | Run2012C |  |  |  | failed |
| 52 | 31129 | Run2012C | 29,627 | 90.8997 ± 0.0220 | 0.618 | fitted |
| 58 | 31129 | Run2012C | 31,480 | 90.8870 ± 0.0212 | 0.836 | fitted |
| 64 | 31129 | Run2012C | 30,188 | 90.9160 ± 0.0219 | 1.042 | fitted |
| 70 | 31129 | Run2012C | 32,940 | 90.8692 ± 0.0206 | 1.149 | fitted |
| 4 | 31123 | Run2012B | 26,725 | 90.9222 ± 0.0236 | 0.807 | fitted |
| 11 | 31123 | Run2012B |  |  |  | failed |
| 18 | 31123 | Run2012B | 27,066 | 90.8861 ± 0.0231 | 0.867 | fitted |
| 25 | 31123 | Run2012B | 26,827 | 90.9153 ± 0.0235 | 0.911 | fitted |
| 32 | 31123 | Run2012B | 31,605 | 90.8884 ± 0.0214 | 0.830 | fitted |
| 39 | 31123 | Run2012B | 28,485 | 90.8382 ± 0.0223 | 1.117 | fitted |
| 46 | 31123 | Run2012B | 22,901 | 90.9134 ± 0.0253 | 1.316 | fitted |
| 53 | 31123 | Run2012B | 24,184 | 90.8556 ± 0.0236 | 1.272 | fitted |

## Z: cutflow

| step | events | muons |
|---|---|---|
| all events | 9,780,165 | 46,183,962 |
| trigger(HLT_Mu17_Mu8 OR HLT_Mu17_TkMu8) | 5,186,366 | 24,933,339 |
| min_pt(20) | 5,186,366 | 4,534,207 |
| max_eta(2.4) | 5,186,366 | 4,520,057 |
| quality_id(tight) | 5,186,366 | 3,745,825 |
| max_rel_iso(0.12, cone=0.4) | 5,186,366 | 1,844,107 |
| require(>= 2) | 634,846 | 1,269,756 |

## Z: warnings

- voigt_poly: the fitted background is significantly negative (-201 +- 17 events/GeV at 110.0 GeV): the peak model does not describe the data's shape and the polynomial compensates, so the signal and background yields are not reliable
- 3 of 9 stability fits failed (listed in the stability table)

## J/ψ: scans

| study | entry | pairs | position [GeV] | χ²/ndf | d/s | S | d/s scaled | status |
|---|---|---|---|---|---|---|---|---|
| region | BB | 294,604 | 3.09401 ± 0.00008 | 31.118 | +4.10 | 5.58 | +0.59 | fitted |
| region | BE | 26,501 | 3.09300 ± 0.00034 | 1.389 | -1.66 | 1.18 | -0.80 | fitted |
| region | EE | 81,815 | 3.08936 ± 0.00021 | 2.914 | -18.63 | 1.71 | -6.03 | fitted |
| phi(mu+) | [-pi, -pi/2) | 103,405 | 3.09329 ± 0.00015 | 19.855 | -1.71 | 4.46 | -0.32 | fitted |
| phi(mu+) | [-pi/2, 0) | 100,433 | 3.09340 ± 0.00015 | 15.900 | -1.07 | 3.99 | -0.21 | fitted |
| phi(mu+) | [0, pi/2) | 96,129 | 3.09385 ± 0.00015 | 15.688 | +1.62 | 3.96 | +0.32 | fitted |
| phi(mu+) | [pi/2, pi] | 102,953 | 3.09377 ± 0.00015 | 16.298 | +1.20 | 4.04 | +0.23 | fitted |
| phi(mu-) | [-pi, -pi/2) | 103,237 | 3.09338 ± 0.00015 | 19.372 | -1.18 | 4.40 | -0.22 | fitted |
| phi(mu-) | [-pi/2, 0) | 100,755 | 3.09325 ± 0.00015 | 16.267 | -1.98 | 4.03 | -0.39 | fitted |
| phi(mu-) | [0, pi/2) | 96,012 | 3.09389 ± 0.00015 | 15.730 | +1.87 | 3.97 | +0.37 | fitted |
| phi(mu-) | [pi/2, pi] | 102,916 | 3.09379 ± 0.00015 | 16.381 | +1.30 | 4.05 | +0.25 | fitted |
| eta(mu+) | [-2.4, -0.8) | 86,615 | 3.09183 ± 0.00019 | 4.383 | -8.53 | 2.09 | -2.43 | fitted |
| eta(mu+) | [-0.8, 0.8) | 227,751 | 3.09405 ± 0.00008 | 19.233 | +4.37 | 4.39 | +0.69 | fitted |
| eta(mu+) | [0.8, 2.4] | 88,554 | 3.09181 ± 0.00019 | 5.655 | -8.66 | 2.38 | -2.36 | fitted |
| eta(mu-) | [-2.4, -0.8) | 86,603 | 3.09193 ± 0.00019 | 4.489 | -8.03 | 2.12 | -2.29 | fitted |
| eta(mu-) | [-0.8, 0.8) | 227,684 | 3.09405 ± 0.00008 | 20.038 | +4.31 | 4.48 | +0.68 | fitted |
| eta(mu-) | [0.8, 2.4] | 88,633 | 3.09188 ± 0.00019 | 4.761 | -8.35 | 2.18 | -2.34 | fitted |
| pT(sublead) | [3, 4) GeV | 808 |  |  |  |  |  | insufficient statistics (n = 808) |
| pT(sublead) | [4, 6) GeV | 20,645 | 3.09402 ± 0.00034 | 4.058 | +1.28 | 2.01 | +0.49 | fitted |
| pT(sublead) | [6, 10) GeV | 177,503 | 3.09358 ± 0.00011 | 30.276 | +0.05 | 5.50 | +0.01 | fitted |
| pT(sublead) | [10, inf) GeV | 203,964 | 3.09353 ± 0.00011 | 32.195 | -0.38 | 5.67 | -0.06 | fitted |
| PV_npvsGood | [0, 15) | 207,328 | 3.09365 ± 0.00010 | 33.377 | +0.58 | 5.78 | +0.09 | fitted |
| PV_npvsGood | [15, 23) | 162,502 | 3.09341 ± 0.00012 | 26.627 | -1.18 | 5.16 | -0.19 | fitted |
| PV_npvsGood | [23, inf) | 33,090 | 3.09392 ± 0.00026 | 6.759 | +1.28 | 2.60 | +0.38 | fitted |
| working point | medium, iso < 0.08 | 10,737 | 3.09423 ± 0.00050 | 2.905 | +1.30 | 1.70 | +0.63 | fitted |
| working point | medium, iso < 0.12 | 17,319 | 3.09447 ± 0.00038 | 3.281 | +2.30 | 1.81 | +0.98 | fitted |
| working point | medium, iso < 0.2 | 31,978 | 3.09433 ± 0.00027 | 6.880 | +2.69 | 2.62 | +0.82 | fitted |
| working point | tight, iso < 0.08 | 9,704 | 3.09426 ± 0.00053 | 2.660 | +1.28 | 1.63 | +0.65 | fitted |
| working point | tight, iso < 0.12 | 15,551 | 3.09446 ± 0.00041 | 3.887 | +2.15 | 1.97 | +0.89 | fitted |
| working point | tight, iso < 0.2 | 28,699 | 3.09425 ± 0.00029 | 7.444 | +2.25 | 2.73 | +0.68 | fitted |

## J/ψ: fit-choice stability

| fit range [GeV] | bin width [GeV] | peak [GeV] | χ²/ndf | p-value |
|---|---|---|---|---|
| 2.8-3.4 | 0.01 | 3.09331 ± 0.00007 | 1.733 | 0.000909 |
| 2.8-3.4 | 0.02 | 3.09332 ± 0.00007 | 3.028 | 3.59e-06 |
| 2.8-3.4 | 0.04 | 3.09341 ± 0.00008 | 3.170 | 0.00413 |
| 2.85-3.35 | 0.01 | 3.09328 ± 0.00007 | 1.630 | 0.00657 |
| 2.86-3.34 | 0.02 | 3.09329 ± 0.00007 | 3.129 | 3.78e-05 |
| 2.88-3.32 | 0.04 | 3.09341 ± 0.00008 | 2.190 | 0.112 |
| 2.9-3.3 | 0.01 | 3.09326 ± 0.00007 | 1.656 | 0.0123 |
| 2.9-3.3 | 0.02 | 3.09327 ± 0.00007 | 3.288 | 0.000158 |

Fit choices that did not give a fit:

- 9 bins in 2.92-3.28 GeV cannot constrain 9 parameters; use finer bins or a wider range

## J/ψ: per-file fits (files by index)

| index | record | period | pairs | peak [GeV] | χ²/ndf | status |
|---|---|---|---|---|---|---|
| 3 | 31129 | Run2012C | 22,922 | 3.09324 ± 0.00031 | 1.512 | fitted |
| 9 | 31129 | Run2012C | 23,927 | 3.09313 ± 0.00030 | 1.212 | fitted |
| 15 | 31129 | Run2012C | 24,843 | 3.09302 ± 0.00029 | 0.769 | fitted |
| 21 | 31129 | Run2012C | 22,745 | 3.09354 ± 0.00032 | 0.624 | fitted |
| 27 | 31129 | Run2012C | 22,644 | 3.09325 ± 0.00031 | 1.566 | fitted |
| 33 | 31129 | Run2012C | 21,864 | 3.09348 ± 0.00032 | 0.962 | fitted |
| 40 | 31129 | Run2012C | 22,677 | 3.09336 ± 0.00031 | 1.546 | fitted |
| 46 | 31129 | Run2012C | 24,336 | 3.09311 ± 0.00030 | 1.114 | fitted |
| 52 | 31129 | Run2012C | 22,722 | 3.09336 ± 0.00032 | 1.316 | fitted |
| 58 | 31129 | Run2012C | 23,341 | 3.09371 ± 0.00031 | 1.185 | fitted |
| 64 | 31129 | Run2012C | 22,738 | 3.09328 ± 0.00031 | 1.134 | fitted |
| 70 | 31129 | Run2012C | 24,976 | 3.09338 ± 0.00031 | 0.945 | fitted |
| 4 | 31123 | Run2012B | 14,580 | 3.09313 ± 0.00039 | 1.035 | fitted |
| 11 | 31123 | Run2012B | 13,589 | 3.09347 ± 0.00042 | 1.185 | fitted |
| 18 | 31123 | Run2012B | 18,344 | 3.09376 ± 0.00035 | 1.238 | fitted |
| 25 | 31123 | Run2012B | 14,477 | 3.09315 ± 0.00038 | 1.275 | fitted |
| 32 | 31123 | Run2012B | 13,932 | 3.09247 ± 0.00038 | 0.841 | fitted |
| 39 | 31123 | Run2012B | 16,306 | 3.09374 ± 0.00037 | 0.973 | fitted |
| 46 | 31123 | Run2012B | 15,629 | 3.09321 ± 0.00037 | 0.944 | fitted |
| 53 | 31123 | Run2012B | 16,328 | 3.09340 ± 0.00036 | 1.100 | fitted |

## J/ψ: cutflow

| step | events | muons |
|---|---|---|
| all events | 9,780,165 | 46,183,962 |
| trigger(HLT_Dimuon8_Jpsi OR HLT_Dimuon10_Jpsi) | 505,124 | 2,136,873 |
| min_pt(3) | 505,124 | 1,335,001 |
| max_eta(2.4) | 505,124 | 1,331,292 |
| quality_id(soft) | 505,124 | 1,080,157 |
| require(>= 2) | 470,475 | 1,046,951 |

## J/ψ: warnings

- 1 of 9 stability fits failed (listed in the stability table)
