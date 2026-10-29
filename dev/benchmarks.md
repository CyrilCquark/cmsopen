# Benchmarks: development observations (append only)

Measurements made during development, each labelled with its date, machine,
input and command. They are development observations, not results: the
README and results documents never quote them (see "Results integrity" in
CLAUDE.md). New entries are appended below; existing entries are never edited.

## 2026-10-28: Layer 8 parallel processing (development observation)

Machine: 8 cores, macOS 14.6.1 arm64, Python 3.12.15. Input: the development
file only. Analysis: Z_mumu, no stability scan, figures included. Chunk size
50,000 events.

Command: `python scripts/benchmark.py --file data/45F7AE81-7A79-4CB1-998E-7BD156490294.root`

| configuration | full analysis wall [s] | events/s | speed-up | event processing [s] | events/s | speed-up | peak RSS main [MB] | peak RSS worker [MB] | same result |
|---|---|---|---|---|---|---|---|---|---|
| serial | 4.89 | 81,058 | 1.00 | 1.90 | 208,892 | 1.00 | 305 | - | yes |
| 2 workers | 5.25 | 75,582 | 0.93 | 2.16 | 183,357 | 0.88 | 199 | 230 | yes |
| 4 workers | 5.01 | 79,239 | 0.98 | 1.89 | 210,158 | 1.01 | 201 | 204 | yes |
| 8 workers | 7.08 | 56,069 | 0.69 | 2.47 | 160,681 | 0.77 | 188 | 190 | yes |

Reading: one development file is too little work for worker processes to pay
off. Its 8 chunks take about 2 s to process, comparable to starting the worker
processes (each imports awkward, uproot and scipy). Results are identical in
every configuration.

Scaling check (ad hoc, not part of scripts/benchmark.py): the event-processing
stage alone on the development file listed 8 times (3,174,128 events, 64
chunks of 50,000), same machine:

| configuration | event processing [s] | events/s | speed-up |
|---|---|---|---|
| serial | 10.33 | 307,420 | 1.00 |
| 2 workers | 7.20 | 440,866 | 1.43 |
| 4 workers | 5.12 | 619,442 | 2.02 |
| 8 workers | 7.21 | 440,411 | 1.43 |

Before each worker kept its file open between chunks, the same check gave no
speed-up at all (2 workers 13.27 s, 4 workers 11.02 s, 8 workers 11.58 s):
opening the file costs about 0.13 s, paid once per chunk. 8 workers are slower
than 4 on this machine.

## Test-suite durations (2026-10-28, 8-core Mac, dev venv)

Development observation, measured with `time`, run one after the other:

| command | tests | wall time |
|---|---|---|
| `pytest -q -m "not slow"` | 289 passed, 28 deselected | 94.7 s |
| `pytest -q` (everything) | 317 passed | 366.7 s |

## Model choice on the development file (2026-10-28)

Development observations, labelled as such; full tables in
`dev/model_choice.md` (rule committed before the run, applied by
`scripts/model_choice.py`). Errors statistical only.

| channel | cb_n (scan) | model | eligible | chi2/ndf | p-value | peak or pole [GeV] | resolution [GeV] |
|---|---|---|---|---|---|---|---|
| Z_mumu | 2 | voigt_poly | no (background < 0) | 2.7477 | 1.9e-07 | 90.783 +- 0.018 | 1.395 +- 0.024 |
| Z_mumu | 2 | cb_bw_exp (selected) | yes | 1.6438 | 0.0104 | 90.875 +- 0.022 | 1.338 +- 0.029 |
| Z_mumu | 2 | cb_bw_poly2 | no (background < 0) | 1.4039 | 0.0618 | 90.858 +- 0.023 | 1.330 +- 0.029 |
| Jpsi_mumu | 20 | voigt_poly | yes | 6.4217 | 5.66e-21 | 3.0922 +- 0.0003 | 0.0319 +- 0.0003 |
| Jpsi_mumu | 20 | cb_bw_exp | yes | 3.3786 | 4.08e-08 | 3.0934 +- 0.0003 | 0.0309 +- 0.0003 |
| Jpsi_mumu | 20 | cb_bw_poly2 (selected) | yes | 2.9740 | 2.14e-06 | 3.0933 +- 0.0003 | 0.0306 +- 0.0003 |

chi2/ndf benchmark: <= 2.0 (T2, production sample). Observed here (development
file, selected model): Z_mumu 1.6438, Jpsi_mumu 2.9740.

## Model choice, Amendment 1 grid (2026-10-28)

Development observations; full tables in `dev/model_choice.md`
("Amendment 1 results"). cb_n grid {1, 2, 3, 5, 10, 20, 30, 50, 100}.

| channel | selected cb_n | model | chi2/ndf | p-value | peak or pole [GeV] | resolution [GeV] |
|---|---|---|---|---|---|---|
| Z_mumu | 2 | cb_bw_exp | 1.6438 | 0.0104 | 90.875 +- 0.022 | 1.338 +- 0.029 |
| Jpsi_mumu | 100 (grid edge) | cb_bw_poly2 | 2.8473 | 5.92e-06 | 3.0934 +- 0.0003 | 0.0306 +- 0.0003 |

chi2/ndf benchmark: <= 2.0 (T2, production sample). Observed here (development
file): Z_mumu 1.6438, Jpsi_mumu 2.8473.

## Validation on the development file (2026-10-28)

Development observations, labelled as such, from `python scripts/run_validation.py`
at commit 8d03f2e, exactly as pre-registered in `dev/validation_plan.md`
(nothing re-binned, re-cut or tuned after the run). Full tables: build/validation/
(untracked). Errors statistical only. Default models: Z_mumu cb_bw_exp (cb_n 2),
Jpsi_mumu cb_bw_poly2 (cb_n 100).

Z_mumu (inclusive 90.8754 +- 0.0225 GeV, resolution 1.3377 GeV, chi2/ndf 1.644):

- Regions: BB 90.9494 +- 0.0365 (resolution 0.971), BE 90.8562 +- 0.0335
  (resolution 1.458), EE insufficient statistics (n = 4,982).
- mu+ minus mu- by phi quarter: -0.158 +- 0.061, +0.208 +- 0.068,
  +0.235 +- 0.060, -0.285 +- 0.071 GeV; by eta bin: +0.053 +- 0.061,
  -0.023 +- 0.048, -0.031 +- 0.060 GeV; weighted mean +0.003 +- 0.023 GeV.
- Sub-leading pT: [20, 30) 90.765 +- 0.070, [30, 40) 90.796 +- 0.046,
  [40, 50) fit failed (alpha not constrained), [50, inf) insufficient (n = 359).
- Pileup: [0, 15) 90.881 +- 0.029, [15, 23) 90.858 +- 0.037, [23, inf)
  insufficient (n = 1,037).
- Working points: positions 90.867-90.888 GeV (spread 0.020 GeV).
- Systematics summary: offset from PDG -0.3125 +- 0.0225 GeV (stat.); eligible
  models: cb_bw_exp only; range x bin width spread 0.024 GeV (8 fits, 1 failed:
  80-100 GeV with 2 GeV bins, alpha not constrained); background variation
  (cb_bw_poly2) -0.018 GeV; BB-BE spread 0.093 GeV.

Jpsi_mumu (inclusive 3.09335 +- 0.00034 GeV, resolution 0.0306 GeV, chi2/ndf 2.847):

- Regions: BB 3.09387 +- 0.00034 (chi2/ndf 1.422), BE insufficient (n = 1,224),
  EE insufficient (n = 3,956).
- Charge: only phi [pi/2, pi] and central eta have both charges fitted;
  mu+ minus mu- -0.0001 +- 0.0010 and +0.0001 +- 0.0005 GeV.
- 21 of 31 entries insufficient (all six working points among them).
- Systematics summary: offset from PDG -0.0035 +- 0.0003 GeV (stat.); all three
  models eligible, spread 0.0013 GeV; range x bin width spread 0.0005 GeV;
  background variation (cb_bw_exp) +0.0001 GeV.

chi2/ndf benchmark: <= 2.0 (T2, production). Observed (development file):
Z_mumu inclusive 1.644; Jpsi_mumu inclusive 2.847, BB 1.422.

## Model choice, Amendment 2: resolution mixtures (2026-10-29)

Development observations; full tables in `dev/model_choice.md` ("Amendment 2
results"). Errors statistical only. Resolution = FWHM/2.355 of the whole signal.

| channel | model | role | chi2/ndf | p-value | pole [GeV] | sigma1 [GeV] | r | f | FWHM/2.355 [GeV] | AIC |
|---|---|---|---|---|---|---|---|---|---|---|
| Z_mumu | cb_bw_exp | previous default | 1.6438 | 0.0104 | 90.875 +- 0.022 | 1.338 +- 0.029 | - | - | 2.022 +- 0.025 | 67.9 |
| Z_mumu | cb2_bw_exp | selected | 0.8909 | 0.644 | 90.852 +- 0.023 | 1.218 +- 0.050 | 3.445 +- 0.577 | 0.907 +- 0.029 | 1.961 +- 0.031 | 44.5 |
| Z_mumu | cb2_bw_poly2 | information | 0.9047 | 0.619 | 90.848 +- 0.024 | 1.222 +- 0.051 | 3.471 +- 0.776 | 0.907 +- 0.028 | 1.962 +- 0.032 | 46.0 |
| Jpsi_mumu | cb_bw_poly2 | previous default | 2.8473 | 5.92e-06 | 3.0934 +- 0.0003 | 0.0306 +- 0.0003 | - | - | 0.0306 +- 0.0003 | 79.5 |
| Jpsi_mumu | cb2_bw_exp | information | 1.2298 | 0.209 | 3.0931 +- 0.0003 | 0.0248 +- 0.0017 | 1.673 +- 0.062 | 0.566 +- 0.128 | 0.0286 +- 0.0005 | 43.1 |
| Jpsi_mumu | cb2_bw_poly2 | selected | 1.2332 | 0.21 | 3.0931 +- 0.0003 | 0.0222 +- 0.0025 | 1.685 +- 0.106 | 0.376 +- 0.139 | 0.0282 +- 0.0006 | 43.9 |

chi2/ndf benchmark: <= 2.0 (T2, production sample). Observed here (development
file, selected model): Z_mumu 0.8909, Jpsi_mumu 1.2332.

## Validation rerun with the Amendment 2 defaults (2026-10-29)

Development observations, `python scripts/run_validation.py` at commit 4df6c09,
the pre-registered plan unchanged (plus the addendum: mixtures in the summary's
model list). Defaults: Z_mumu cb2_bw_exp, Jpsi_mumu cb2_bw_poly2. Resolution
column = FWHM/2.355 of the whole signal (includes the Z natural width).

Z_mumu:

- Inclusive 90.8515 +- 0.0232 GeV (was 90.8754 +- 0.0225 with cb_bw_exp),
  chi2/ndf 0.891 (was 1.644).
- 9 entries now fail to fit (was 1): BB (r on its bound), phi(mu+) [-pi/2, 0)
  (r not constrained), phi(mu-) [pi/2, pi] (exponential c0 on its bound),
  central eta for mu+ and mu- (r, and f, on bounds), all three fitted pT bins
  (r and/or f not constrained) and PV [15, 23) (r on its bound). In samples
  dominated by one resolution the second core is not determined. Insufficient
  entries unchanged (EE, pT [50, inf), PV [23, inf)).
- Fitted entries move little: BE 90.8376 +- 0.0347 (was 90.8562 +- 0.0335);
  phi(mu-) [0, pi/2) 90.6755 (was 90.7036); working points 90.852-90.856
  (spread 0.005 GeV, was 0.020).
- Systematics summary: offset from PDG -0.3364 +- 0.0232 GeV (stat.); eligible
  models cb_bw_exp, cb2_bw_exp, cb2_bw_poly2 (spread 0.027 GeV); range x bin
  width spread 0.017 GeV (6 fits, 3 failed); background variation -0.003 GeV;
  category spread n/a (BB not fitted); mu+ minus mu- now only in phi quarters
  1 and 3 (-0.151 +- 0.063, +0.236 +- 0.062 GeV) and the outer eta bins.

Jpsi_mumu:

- Inclusive 3.09307 +- 0.00034 GeV (was 3.09335), chi2/ndf 1.233 (was 2.847).
- Every sufficient entry fits; chi2/ndf lower everywhere (BB 0.744, was 1.422).
  Positions move by less than 0.0004 GeV.
- Systematics summary: offset from PDG -0.0038 +- 0.0003 GeV (stat.); all five
  models eligible, spread 0.0013 GeV; range x bin width spread 0.0002 GeV
  (6 fits, 3 failed); background variation +0.0001 GeV.

## Validation with the validation model (2026-10-29, prompt 8, development file)

dev/validation_plan.md, prompt 8 addendum: scans and their inclusive
reference use ChannelConfig.validation_model (Z_mumu cb_bw_exp, Jpsi_mumu
cb_bw_poly2); the headline remains the Amendment 2 default.

- Regression check (scripts/compare_validation.py, build/regression_prompt8.txt):
  every entry of both channels (pairs, position, resolution, chi2/ndf,
  signal, status) reproduces the prompt 6 tables exactly (largest relative
  difference 0). Z_mumu: 1 entry failed (pT [40, 50)), 3 insufficient (EE,
  pT [50, inf), PV [23, inf)), as in prompt 6.
- Everything outside the validation part (summary.json, summary.txt before
  the validation tables, figures) is identical to the prompt 7 run.
- The headline offsets are unchanged: Z_mumu -0.3364 +- 0.0232 GeV,
  Jpsi_mumu -0.0038 +- 0.0003 GeV (channel default models).

## Slow-test timeout (2026-10-29, prompt 8)

- pytest-timeout, signal method, set in tests/conftest.py: 300 s per slow
  test, 120 s per other test.
- Slowest normal tests (full suite, 407 tests, 471 s, with a download
  running alongside): Z cb2 pull test 96.6 s, two-file parallel test 48.2 s.
  The slowest fast test takes under 5 s. 300 s is about 3x the slowest.
- With the prompt 7 breakage "sigma1 used for both cores", the full suite
  ended in 21 min 44 s (11 failed, 3 errors from an unrelated new test, 1 of
  the failures a timeout at 300 s). Before the timeout, the same breakage
  ran for more than 67 minutes and was killed.

## Rehearsal on the 6-file development set (2026-10-29, prompt 9)

Every number in this section is a development observation (6-file
development set; dev/development_set.md). None of it enters README.md,
docs/, notebooks/ or results/production.json, and nothing was re-selected:
the channel defaults (Z_mumu cb2_bw_exp, Jpsi_mumu cb2_bw_poly2) and the
validation models (cb_bw_exp, cb_bw_poly2) are unchanged. The J/psi
headline chi2/ndf of 2.155 is recorded against the unchanged benchmark of
2.0 (T2 applies to production); no amendment.

Produced by `python scripts/rehearsal.py confirm` and `rest` (build/rehearsal/).
Regions in item 4: "core" is within 2 x the reported resolution (FWHM/2.355)
of the fitted position. Pulls are (N - mu) / sqrt(max(N, 1)), the fit's own
chi2 terms. Item 6 compares with the single-file validation in
build/validation/ (prompt 8).

Confirmation (production code path, 4 workers):

```
Confirmation of the defaults on the 6-file development set (development observation (6-file development set)); no re-selection

Z_mumu: model cb2_bw_exp, 173,754 pairs in the fit range
  converged: yes; parameters on a bound: none; background positive over the fit range: yes
  chi2/ndf 0.824 (benchmark <= 2.0), p-value 0.748
  pole/peak 90.8927 +- 0.0090 GeV (stat.), offset from PDG -0.2952 GeV
  signal 169,753 +- 486, background 3,975 +- 266
Jpsi_mumu: model cb2_bw_poly2, 121,689 pairs in the fit range
  converged: yes; parameters on a bound: none; background positive over the fit range: yes
  chi2/ndf 2.155 (benchmark <= 2.0), p-value 0.00161
  pole/peak 3.0934 +- 0.0001 GeV (stat.), offset from PDG -0.0035 GeV
  signal 101,824 +- 426, background 19,819 +- 316

time: 128 s for the 12 per-file runs; 6-file runs with validation: Z_mumu 79 s, Jpsi_mumu 55 s
peak memory: main process 502 MB, largest worker 359 MB
STOP: Jpsi_mumu
```

Tables:

```
Rehearsal tables (development observation (6-file development set))

== Z_mumu (headline model cb2_bw_exp) ==

1. Statistics scaling (cumulative, fixed order: the original file, then the new files by index):
  files  pairs in fit range  chi2/ndf  ndf   p-value          pole/peak [GeV]
      1              26,195     0.891   32     0.644        90.8515 +- 0.0232
      2              58,576     1.632   32    0.0134        90.8610 +- 0.0154
      4             122,872     0.839   32     0.725        90.8910 +- 0.0108
      6             173,754     0.824   32     0.748        90.8927 +- 0.0090

2. Validation (validation model cb_bw_exp, headline model cb2_bw_exp; at least 5,000 pairs per entry):
Validation (Z_mumu; scans and inclusive reference fitted with the validation model cb_bw_exp, headline model cb2_bw_exp; at least 5,000 pairs per entry)
study          entry                    pairs          position [GeV]      resolution [GeV]  chi2/ndf    signal  delta/sigma  status
inclusive      all pairs              173,754       90.9075 +- 0.0088      1.3871 +- 0.0114     3.571   169,335               fitted
region         BB                      64,738       90.9742 +- 0.0137      1.0812 +- 0.0189     0.820    63,252        +4.09  fitted
region         BE                      76,121       90.8975 +- 0.0133      1.4503 +- 0.0169     1.788    74,339        -0.63  fitted
region         EE                      32,895       90.7268 +- 0.0230      1.9658 +- 0.0273     2.346    31,811        -7.34  fitted
phi(mu+)       [-pi, -pi/2)            43,135       90.8695 +- 0.0170      1.4023 +- 0.0220     1.790    41,762        -1.99  fitted
phi(mu+)       [-pi/2, 0)              43,999       91.0087 +- 0.0182      1.3468 +- 0.0237     1.753    43,116        +4.99  fitted
phi(mu+)       [0, pi/2)               42,645       90.9603 +- 0.0178      1.3815 +- 0.0230     1.529    41,578        +2.65  fitted
phi(mu+)       [pi/2, pi]              43,975       90.8012 +- 0.0178      1.3979 +- 0.0229     1.781    42,932        -5.36  fitted
phi(mu-)       [-pi, -pi/2)            42,726       90.9426 +- 0.0181      1.3642 +- 0.0234     1.385    41,733        +1.74  fitted
phi(mu-)       [-pi/2, 0)              43,757       90.8180 +- 0.0176      1.4158 +- 0.0226     1.912    42,669        -4.55  fitted
phi(mu-)       [0, pi/2)               43,321       90.8319 +- 0.0169      1.3924 +- 0.0219     1.609    41,954        -3.96  fitted
phi(mu-)       [pi/2, pi]              43,950       91.0505 +- 0.0183      1.3468 +- 0.0238     1.812    43,041        +7.03  fitted
eta(mu+)       [-2.4, -0.8)            50,924       90.8702 +- 0.0170      1.5939 +- 0.0211     1.912    49,725        -1.95  fitted
eta(mu+)       [-0.8, 0.8)             71,168       90.9512 +- 0.0130      1.1460 +- 0.0178     1.455    69,476        +2.77  fitted
eta(mu+)       [0.8, 2.4]              51,662       90.8640 +- 0.0168      1.5500 +- 0.0211     2.189    50,162        -2.29  fitted
eta(mu-)       [-2.4, -0.8)            51,248       90.8532 +- 0.0168      1.5663 +- 0.0209     2.112    50,119        -2.87  fitted
eta(mu-)       [-0.8, 0.8)             70,402       90.9549 +- 0.0133      1.1690 +- 0.0179     0.939    68,797        +2.97  fitted
eta(mu-)       [0.8, 2.4]              52,104       90.8841 +- 0.0167      1.5380 +- 0.0211     2.713    50,517        -1.24  fitted
pT(sublead)    [20, 30) GeV            35,262       90.8098 +- 0.0270      1.2693 +- 0.0321     4.404    33,328        -3.45  fitted
pT(sublead)    [30, 40) GeV            78,133       90.8051 +- 0.0184      1.2289 +- 0.0220     9.140    75,804        -5.02  fitted
pT(sublead)    [40, 50) GeV            57,828                                                                                 fit failed: cb_bw_exp fit over 70-110 GeV: parameter(s) ['alpha'] not constrained by the data (alpha=9.124 +- 1.2e-11); the data show no radiative tail for the Crystal Ball to describe
pT(sublead)    [50, inf) GeV            2,531                                                                                 insufficient statistics (n = 2,531)
PV_npvsGood    [0, 15)                101,551       90.9159 +- 0.0118      1.3720 +- 0.0152     2.102    99,086        +0.57  fitted
PV_npvsGood    [15, 23)                62,863       90.8970 +- 0.0143      1.4121 +- 0.0185     2.508    61,190        -0.63  fitted
PV_npvsGood    [23, inf)                9,340       90.8915 +- 0.0370      1.3853 +- 0.0478     0.976     9,074        -0.42  fitted
working point  medium, iso < 0.08     125,034       90.9186 +- 0.0101      1.3595 +- 0.0132     3.053   121,564        +0.82  fitted
working point  medium, iso < 0.12     163,679       90.9071 +- 0.0091      1.3440 +- 0.0118     3.105   159,609        -0.03  fitted
working point  medium, iso < 0.2      195,402       90.8993 +- 0.0087      1.3319 +- 0.0113     2.881   191,022        -0.66  fitted
working point  tight, iso < 0.08      132,384       90.9208 +- 0.0098      1.4019 +- 0.0127     3.497   128,588        +1.00  fitted
working point  tight, iso < 0.12      173,754       90.9075 +- 0.0088      1.3871 +- 0.0114     3.571   169,335        +0.00  fitted
working point  tight, iso < 0.2       207,781       90.8973 +- 0.0085      1.3757 +- 0.0109     3.293   202,985        -0.83  fitted
delta/sigma = (entry - inclusive) / sqrt(err^2 + err_incl^2); the samples overlap, so this overstates the uncertainty of the difference

Systematics summary (Z_mumu, headline model cb2_bw_exp, validation scans cb_bw_exp); all values measured, no targets
  offset from PDG Z mass (91.1879 GeV): -0.2952 GeV +- 0.0090 (stat.)
  fit choices, model (inclusive sample):
    voigt_poly   not eligible  90.8123 +- 0.0071 GeV, chi2/ndf 13.677  (background not positive over the fit range)
    cb_bw_exp    eligible      90.9075 +- 0.0088 GeV, chi2/ndf 3.571
    cb_bw_poly2  eligible      90.8964 +- 0.0090 GeV, chi2/ndf 2.913
    cb2_bw_exp   eligible      90.8927 +- 0.0090 GeV, chi2/ndf 0.824
    cb2_bw_poly2 eligible      90.8879 +- 0.0092 GeV, chi2/ndf 0.713
    spread of the eligible models (max - min): +0.0197 GeV
  fit choices, range x bin width (5 fits, 4 failed): max - min +0.0034 GeV, std +0.0016 GeV
  background variation (cb2_bw_poly2): -0.0048 GeV relative to the headline
  from the validation scans (cb_bw_exp):
  categories BB/BE/EE: max - min +0.2474 GeV, largest |delta|/sigma 7.34
  mu+ minus mu- (bins where both charges are fitted):
    phi [-pi, -pi/2): -0.0731 GeV +- 0.0248
    phi [-pi/2, 0): +0.1907 GeV +- 0.0253
    phi [0, pi/2): +0.1283 GeV +- 0.0246
    phi [pi/2, pi]: -0.2493 GeV +- 0.0255
    eta [-2.4, -0.8): +0.0170 GeV +- 0.0239
    eta [-0.8, 0.8): -0.0038 GeV +- 0.0186
    eta [0.8, 2.4]: -0.0201 GeV +- 0.0237
    largest |difference| +0.2493 GeV; weighted mean -0.0006 GeV +- 0.0088
  working points: max - min +0.0234 GeV
  entries with insufficient statistics: 1; failed fits: 1

  per category (validation model): BB 64,738 pairs, chi2/ndf 0.820; BE 76,121 pairs, chi2/ndf 1.788; EE 32,895 pairs, chi2/ndf 2.346
  flagged entries (2): pT(sublead) [40, 50) GeV: fit failed: cb_bw_exp fit over 70-110 GeV: parameter(s) ['alpha'] not constrained by the data (alpha=9.124 +- 1.2e-11); the data show no radiative tail for the Crystal Ball to describe; pT(sublead) [50, inf) GeV: insufficient statistics (n = 2,531)

3. Per file (headline model, each file fitted on its own):
  45F7AE81-7A79-4CB1-998E-7BD156490294.root (2012C): chi2/ndf 0.891 (ndf 32), 90.8515 +- 0.0232 GeV, resolution 1.9608 +- 0.0310 GeV, 26,195 pairs
  06C1145E-99D4-4DAC-859D-F634CC8714AF.root (2012C): chi2/ndf 1.548 (ndf 32), 90.8679 +- 0.0207 GeV, resolution 2.0037 +- 0.0317 GeV, 32,381 pairs
  0995C487-F7CE-4AC4-851D-F3202F7A9712.root (2012C): chi2/ndf 0.741 (ndf 32), 90.9288 +- 0.0211 GeV, resolution 2.0011 +- 0.0346 GeV, 31,899 pairs
  0B22B275-85C5-4E44-8D89-D18B56091507.root (2012C): chi2/ndf 0.789 (ndf 32), 90.9081 +- 0.0213 GeV, resolution 2.0357 +- 0.0326 GeV, 32,397 pairs
  03C5684F-8BAF-4312-8235-2B0039F2FB93.root (2012B): chi2/ndf 1.513 (ndf 32), 90.9096 +- 0.0228 GeV, resolution 1.9870 +- 0.0370 GeV, 26,507 pairs
  12EE191C-00CB-4150-BBD9-8D1266BB7FD8.root (2012B): chi2/ndf 1.142 (ndf 32), 90.8812 +- 0.0239 GeV, resolution 1.9002 +- 0.0416 GeV, 24,375 pairs
  weighted mean 90.8921 +- 0.0090 GeV; chi2 of consistency of the 6 positions 8.83 / 5 (p = 0.116)
  2012C (4 files): fitted together 90.8910 +- 0.0108 GeV (chi2/ndf 0.839); weighted mean of the files 90.8904 +- 0.0107 GeV
  2012B (2 files): fitted together 90.8940 +- 0.0165 GeV (chi2/ndf 1.042); weighted mean of the files 90.8961 +- 0.0165 GeV
  2012C - 2012B (fitted together): -0.0031 +- 0.0197 GeV = -0.16 sigma (stat.)

4. Structure of the headline fit's residuals on the 6 files (cb2_bw_exp; pulls in build/rehearsal/Z_mumu/pulls.csv and pulls.png):
  chi2 26.4 / ndf 32 over 40 bins
  chi2 left  (70-87 GeV, 17 bins): 12.2 (0.72 per bin)
  chi2 core  (87-95 GeV, 8 bins): 4.1 (0.51 per bin)
  chi2 right (95-110 GeV, 15 bins): 10.1 (0.67 per bin)
  bins with |pull| > 3: none
  lag-1 autocorrelation of the pulls: +0.139 (1/sqrt(n) = 0.158)
  runs test on the pull signs: 21 runs (22 +, 18 -), expected 20.8, z = +0.06, p = 0.948
  chi2/ndf over the fit-range x bin-width grid (report only):
    70-110 GeV, bins 0.5 GeV: chi2/ndf 1.004, p 0.468, position 90.8919 GeV
    70-110 GeV, bins 1 GeV: chi2/ndf 0.824, p 0.748, position 90.8927 GeV
    70-110 GeV, bins 2 GeV: chi2/ndf 1.041, p 0.407, position 90.8918 GeV
    75-105 GeV, bins 0.5 GeV: chi2/ndf 1.091, p 0.303, position 90.8892 GeV
    75-105 GeV, bins 1 GeV: chi2/ndf 0.808, p 0.719, position 90.8893 GeV
    (75.0, 105.0), bins 2.0: fit failed: cb2_bw_exp fit over 76-104 GeV: parameter(s) ['r'] not constrained by the data (r=3.331 +- 3.7)
    (80.0, 100.0), bins 0.5: fit failed: cb2_bw_exp fit over 80-100 GeV: parameter(s) ['alpha'] not constrained by the data (alpha=8.022 +- 2.1e-10); the data show no radiative tail for the Crystal Ball to describe
    (80.0, 100.0), bins 1.0: fit failed: cb2_bw_exp fit over 80-100 GeV: parameter(s) ['alpha'] not constrained by the data (alpha=7.856 +- 5.8e-10); the data show no radiative tail for the Crystal Ball to describe
    (80.0, 100.0), bins 2.0: fit failed: cb2_bw_exp fit over 80-100 GeV: parameter(s) ['alpha'] not constrained by the data (alpha=8.37 +- 2.4e-10); the data show no radiative tail for the Crystal Ball to describe

6. Entries at or above 5,000 pairs on the 6 files that were insufficient on the original file (build/validation/Z_mumu/summary.json): 2
  region EE: 4,982 -> 32,895 pairs, now fitted (90.7268 +- 0.0230 GeV, chi2/ndf 2.346)
  PV_npvsGood [23, inf): 1,037 -> 9,340 pairs, now fitted (90.8915 +- 0.0370 GeV, chi2/ndf 0.976)
  still insufficient on the 6 files: pT(sublead) [50, inf) GeV (2,531)

== Jpsi_mumu (headline model cb2_bw_poly2) ==

1. Statistics scaling (cumulative, fixed order: the original file, then the new files by index):
  files  pairs in fit range  chi2/ndf  ndf   p-value          pole/peak [GeV]
      1              19,496     1.233   21      0.21         3.0931 +- 0.0003
      2              42,842     1.483   21    0.0711         3.0932 +- 0.0002
      4              90,515     1.975   21    0.0049         3.0935 +- 0.0002
      6             121,689     2.155   21   0.00161         3.0934 +- 0.0001

2. Validation (validation model cb_bw_poly2, headline model cb2_bw_poly2; at least 5,000 pairs per entry):
Validation (Jpsi_mumu; scans and inclusive reference fitted with the validation model cb_bw_poly2, headline model cb2_bw_poly2; at least 5,000 pairs per entry)
study          entry                    pairs          position [GeV]      resolution [GeV]  chi2/ndf    signal  delta/sigma  status
inclusive      all pairs              121,689      3.09361 +- 0.00014    0.02970 +- 0.00013    19.307    99,007               fitted
region         BB                      89,040      3.09402 +- 0.00014    0.02655 +- 0.00013     8.523    73,197        +2.12  fitted
region         BE                       7,950      3.09254 +- 0.00060    0.04024 +- 0.00057     1.118     6,549        -1.73  fitted
region         EE                      24,699      3.08923 +- 0.00040    0.04504 +- 0.00039     2.041    20,398       -10.44  fitted
phi(mu+)       [-pi, -pi/2)            31,245      3.09330 +- 0.00027    0.02974 +- 0.00026     5.812    25,257        -1.04  fitted
phi(mu+)       [-pi/2, 0)              29,966      3.09346 +- 0.00028    0.02995 +- 0.00026     4.962    24,311        -0.50  fitted
phi(mu+)       [0, pi/2)               29,157      3.09391 +- 0.00027    0.02954 +- 0.00026     5.791    23,770        +0.97  fitted
phi(mu+)       [pi/2, pi]              31,321      3.09379 +- 0.00028    0.02962 +- 0.00026     6.176    25,710        +0.57  fitted
phi(mu-)       [-pi, -pi/2)            31,161      3.09326 +- 0.00027    0.02963 +- 0.00025     5.549    25,203        -1.18  fitted
phi(mu-)       [-pi/2, 0)              30,121      3.09327 +- 0.00028    0.03016 +- 0.00026     4.695    24,467        -1.13  fitted
phi(mu-)       [0, pi/2)               29,041      3.09398 +- 0.00027    0.02942 +- 0.00026     5.941    23,664        +1.22  fitted
phi(mu-)       [pi/2, pi]              31,366      3.09394 +- 0.00028    0.02963 +- 0.00026     6.314    25,715        +1.06  fitted
eta(mu+)       [-2.4, -0.8)            26,374      3.09190 +- 0.00035    0.03894 +- 0.00033     2.840    21,708        -4.57  fitted
eta(mu+)       [-0.8, 0.8)             68,527      3.09402 +- 0.00015    0.02489 +- 0.00014     5.729    56,392        +2.04  fitted
eta(mu+)       [0.8, 2.4]              26,788      3.09148 +- 0.00035    0.03943 +- 0.00034     2.114    22,086        -5.65  fitted
eta(mu-)       [-2.4, -0.8)            26,464      3.09202 +- 0.00035    0.03894 +- 0.00033     2.529    21,813        -4.28  fitted
eta(mu-)       [-0.8, 0.8)             68,558      3.09400 +- 0.00015    0.02488 +- 0.00014     5.626    56,391        +1.93  fitted
eta(mu-)       [0.8, 2.4]              26,667      3.09160 +- 0.00035    0.03922 +- 0.00034     2.257    21,915        -5.36  fitted
pT(sublead)    [3, 4) GeV                 240                                                                                 insufficient statistics (n = 240)
pT(sublead)    [4, 6) GeV               6,216      3.09376 +- 0.00060    0.02867 +- 0.00058     2.177     4,901        +0.23  fitted
pT(sublead)    [6, 10) GeV             53,333      3.09355 +- 0.00020    0.02921 +- 0.00019     7.126    43,459        -0.24  fitted
pT(sublead)    [10, inf) GeV           61,900      3.09365 +- 0.00020    0.03026 +- 0.00019    12.171    50,520        +0.18  fitted
PV_npvsGood    [0, 15)                 65,725      3.09361 +- 0.00019    0.02968 +- 0.00018     9.955    53,532        -0.02  fitted
PV_npvsGood    [15, 23)                47,122      3.09351 +- 0.00022    0.02986 +- 0.00021     9.486    38,315        -0.41  fitted
PV_npvsGood    [23, inf)                8,842      3.09418 +- 0.00050    0.02915 +- 0.00048     2.297     7,181        +1.09  fitted
working point  medium, iso < 0.08       3,205                                                                                 insufficient statistics (n = 3,205)
working point  medium, iso < 0.12       5,227      3.09519 +- 0.00074    0.03240 +- 0.00071     1.464     4,163        +2.11  fitted
working point  medium, iso < 0.2        9,688      3.09402 +- 0.00051    0.03156 +- 0.00048     2.405     7,783        +0.77  fitted
working point  tight, iso < 0.08        2,948                                                                                 insufficient statistics (n = 2,948)
working point  tight, iso < 0.12        4,747                                                                                 insufficient statistics (n = 4,747)
working point  tight, iso < 0.2         8,710      3.09423 +- 0.00054    0.03128 +- 0.00052     2.127     6,998        +1.10  fitted
delta/sigma = (entry - inclusive) / sqrt(err^2 + err_incl^2); the samples overlap, so this overstates the uncertainty of the difference

Systematics summary (Jpsi_mumu, headline model cb2_bw_poly2, validation scans cb_bw_poly2); all values measured, no targets
  offset from PDG J/psi mass (3.0969 GeV): -0.0035 GeV +- 0.0001 (stat.)
  fit choices, model (inclusive sample):
    voigt_poly   eligible      3.0923 +- 0.0001 GeV, chi2/ndf 48.201
    cb_bw_exp    eligible      3.0938 +- 0.0001 GeV, chi2/ndf 27.309
    cb_bw_poly2  eligible      3.0936 +- 0.0001 GeV, chi2/ndf 19.307
    cb2_bw_exp   eligible      3.0935 +- 0.0001 GeV, chi2/ndf 2.892
    cb2_bw_poly2 eligible      3.0934 +- 0.0001 GeV, chi2/ndf 2.155
    spread of the eligible models (max - min): +0.0014 GeV
  fit choices, range x bin width (8 fits, 1 failed): max - min +0.0009 GeV, std +0.0003 GeV
  background variation (cb2_bw_exp): +0.0001 GeV relative to the headline
  from the validation scans (cb_bw_poly2):
  categories BB/BE/EE: max - min +0.0048 GeV, largest |delta|/sigma 10.44
  mu+ minus mu- (bins where both charges are fitted):
    phi [-pi, -pi/2): +0.0000 GeV +- 0.0004
    phi [-pi/2, 0): +0.0002 GeV +- 0.0004
    phi [0, pi/2): -0.0001 GeV +- 0.0004
    phi [pi/2, pi]: -0.0002 GeV +- 0.0004
    eta [-2.4, -0.8): -0.0001 GeV +- 0.0005
    eta [-0.8, 0.8): +0.0000 GeV +- 0.0002
    eta [0.8, 2.4]: -0.0001 GeV +- 0.0005
    largest |difference| +0.0002 GeV; weighted mean -0.0000 GeV +- 0.0001
  working points: max - min +0.0012 GeV
  entries with insufficient statistics: 4; failed fits: 0

  per category (validation model): BB 89,040 pairs, chi2/ndf 8.523; BE 7,950 pairs, chi2/ndf 1.118; EE 24,699 pairs, chi2/ndf 2.041
  flagged entries (4): pT(sublead) [3, 4) GeV: insufficient statistics (n = 240); working point medium, iso < 0.08: insufficient statistics (n = 3,205); working point tight, iso < 0.08: insufficient statistics (n = 2,948); working point tight, iso < 0.12: insufficient statistics (n = 4,747)

3. Per file (headline model, each file fitted on its own):
  45F7AE81-7A79-4CB1-998E-7BD156490294.root (2012C): chi2/ndf 1.233 (ndf 21), 3.0931 +- 0.0003 GeV, resolution 0.0282 +- 0.0006 GeV, 19,496 pairs
  06C1145E-99D4-4DAC-859D-F634CC8714AF.root (2012C): chi2/ndf 1.111 (ndf 21), 3.0934 +- 0.0003 GeV, resolution 0.0271 +- 0.0005 GeV, 23,346 pairs
  0995C487-F7CE-4AC4-851D-F3202F7A9712.root (2012C): chi2/ndf 1.117 (ndf 21), 3.0933 +- 0.0003 GeV, resolution 0.0271 +- 0.0005 GeV, 24,005 pairs
  0B22B275-85C5-4E44-8D89-D18B56091507.root (2012C): chi2/ndf 1.471 (ndf 21), 3.0941 +- 0.0003 GeV, resolution 0.0273 +- 0.0005 GeV, 23,668 pairs
  03C5684F-8BAF-4312-8235-2B0039F2FB93.root (2012B): chi2/ndf 0.639 (ndf 21), 3.0926 +- 0.0004 GeV, resolution 0.0272 +- 0.0005 GeV, 16,879 pairs
  12EE191C-00CB-4150-BBD9-8D1266BB7FD8.root (2012B): chi2/ndf 1.367 (ndf 21), 3.0938 +- 0.0004 GeV, resolution 0.0272 +- 0.0006 GeV, 14,295 pairs
  weighted mean 3.0934 +- 0.0001 GeV; chi2 of consistency of the 6 positions 11.44 / 5 (p = 0.0433)
  2012C (4 files): fitted together 3.0935 +- 0.0002 GeV (chi2/ndf 1.975); weighted mean of the files 3.0935 +- 0.0002 GeV
  2012B (2 files): fitted together 3.0932 +- 0.0003 GeV (chi2/ndf 1.187); weighted mean of the files 3.0932 +- 0.0003 GeV
  2012C - 2012B (fitted together): +0.0003 +- 0.0003 GeV = +1.02 sigma (stat.)

4. Structure of the headline fit's residuals on the 6 files (cb2_bw_poly2; pulls in build/rehearsal/Jpsi_mumu/pulls.csv and pulls.png):
  chi2 45.2 / ndf 21 over 30 bins
  chi2 left  (2.8-3.04 GeV, 12 bins): 20.4 (1.70 per bin)
  chi2 core  (3.04-3.14 GeV, 5 bins): 13.1 (2.63 per bin)
  chi2 right (3.14-3.4 GeV, 13 bins): 11.7 (0.90 per bin)
  bins with |pull| > 3: none
  lag-1 autocorrelation of the pulls: +0.039 (1/sqrt(n) = 0.183)
  runs test on the pull signs: 14 runs (14 +, 16 -), expected 15.9, z = -0.72, p = 0.47
  chi2/ndf over the fit-range x bin-width grid (report only):
    2.8-3.4 GeV, bins 0.01 GeV: chi2/ndf 1.380, p 0.0374, position 3.0934 GeV
    2.8-3.4 GeV, bins 0.02 GeV: chi2/ndf 2.155, p 0.00161, position 3.0934 GeV
    2.8-3.4 GeV, bins 0.04 GeV: chi2/ndf 3.157, p 0.00427, position 3.0935 GeV
    2.85-3.35 GeV, bins 0.01 GeV: chi2/ndf 1.401, p 0.0456, position 3.0933 GeV
    2.86-3.34 GeV, bins 0.02 GeV: chi2/ndf 2.433, p 0.0015, position 3.0934 GeV
    2.88-3.32 GeV, bins 0.04 GeV: chi2/ndf 1.166, p 0.312, position 3.0926 GeV
    2.9-3.3 GeV, bins 0.01 GeV: chi2/ndf 1.425, p 0.059, position 3.0933 GeV
    2.9-3.3 GeV, bins 0.02 GeV: chi2/ndf 2.594, p 0.00268, position 3.0934 GeV
    (2.9, 3.3), bins 0.04: fit failed: 9 bins in 2.92-3.28 GeV cannot constrain 9 parameters; use finer bins or a wider range

6. Entries at or above 5,000 pairs on the 6 files that were insufficient on the original file (build/validation/Jpsi_mumu/summary.json): 17
  region BE: 1,224 -> 7,950 pairs, now fitted (3.0925 +- 0.0006 GeV, chi2/ndf 1.118)
  region EE: 3,956 -> 24,699 pairs, now fitted (3.0892 +- 0.0004 GeV, chi2/ndf 2.041)
  phi(mu+) [-pi, -pi/2): 4,987 -> 31,245 pairs, now fitted (3.0933 +- 0.0003 GeV, chi2/ndf 5.812)
  phi(mu+) [-pi/2, 0): 4,821 -> 29,966 pairs, now fitted (3.0935 +- 0.0003 GeV, chi2/ndf 4.962)
  phi(mu+) [0, pi/2): 4,614 -> 29,157 pairs, now fitted (3.0939 +- 0.0003 GeV, chi2/ndf 5.791)
  phi(mu-) [-pi, -pi/2): 4,936 -> 31,161 pairs, now fitted (3.0933 +- 0.0003 GeV, chi2/ndf 5.549)
  phi(mu-) [-pi/2, 0): 4,871 -> 30,121 pairs, now fitted (3.0933 +- 0.0003 GeV, chi2/ndf 4.695)
  phi(mu-) [0, pi/2): 4,593 -> 29,041 pairs, now fitted (3.0940 +- 0.0003 GeV, chi2/ndf 5.941)
  eta(mu+) [-2.4, -0.8): 4,213 -> 26,374 pairs, now fitted (3.0919 +- 0.0003 GeV, chi2/ndf 2.840)
  eta(mu+) [0.8, 2.4]: 4,279 -> 26,788 pairs, now fitted (3.0915 +- 0.0004 GeV, chi2/ndf 2.114)
  eta(mu-) [-2.4, -0.8): 4,210 -> 26,464 pairs, now fitted (3.0920 +- 0.0003 GeV, chi2/ndf 2.529)
  eta(mu-) [0.8, 2.4]: 4,248 -> 26,667 pairs, now fitted (3.0916 +- 0.0003 GeV, chi2/ndf 2.257)
  pT(sublead) [4, 6) GeV: 1,011 -> 6,216 pairs, now fitted (3.0938 +- 0.0006 GeV, chi2/ndf 2.177)
  PV_npvsGood [23, inf): 1,031 -> 8,842 pairs, now fitted (3.0942 +- 0.0005 GeV, chi2/ndf 2.297)
  working point medium, iso < 0.12: 931 -> 5,227 pairs, now fitted (3.0952 +- 0.0007 GeV, chi2/ndf 1.464)
  working point medium, iso < 0.2: 1,708 -> 9,688 pairs, now fitted (3.0940 +- 0.0005 GeV, chi2/ndf 2.405)
  working point tight, iso < 0.2: 1,550 -> 8,710 pairs, now fitted (3.0942 +- 0.0005 GeV, chi2/ndf 2.127)
  still insufficient on the 6 files: pT(sublead) [3, 4) GeV (240); working point medium, iso < 0.08 (3,205); working point tight, iso < 0.08 (2,948); working point tight, iso < 0.12 (4,747)

```
