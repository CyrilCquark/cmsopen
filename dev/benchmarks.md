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
