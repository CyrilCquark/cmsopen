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
