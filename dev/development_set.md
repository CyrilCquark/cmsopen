# Development set (pre-registered 2026-10-29, prompt 8, before any download)

A larger sample for rehearsing the production code path and for
development observations. It is fixed by the rule below, written and
committed before any of its files is listed, chosen or downloaded.

## Rule

- Listing: for each record, the per-file ROOT file index (not the
  merged-file index) of `https://opendata.cern.ch/api/records/<record_id>`,
  `metadata._file_indices`, the same source as the production registry
  (results/production_files.json).
- Index: as in the production registry, a file's index is its 0-based
  position in that record's file names sorted alphabetically (Python str
  ordering).
- Exclusions: the original development file
  (45F7AE81-7A79-4CB1-998E-7BD156490294.root) and every file selected in
  results/production_files.json.
- Selection: from record 31129 (Run2012C DoubleMuParked) the 3
  lowest-index files that are not excluded; from record 31123 (Run2012B
  DoubleMuParked) the 2 lowest-index files that are not excluded.
- The exclusion is done inside `scripts/development_set.py`, which prints
  only the chosen development file names and the line
  `disjoint from production: OK`, and never a production name. It writes
  the chosen files (record, index, name, size, adler32, URL) to
  `dev/development_set.json`. `scripts/check_blinding.py` also verifies
  that no development-set file coincides with a production file, without
  printing production names.
- The development set is the original development file plus these 5
  files (6 files). Fixed order wherever files are combined: the original
  file first, then the new files in index order, record 31129 before
  record 31123.
- Download: with `cmsopen fetch` (resumable, size and adler32 verified)
  into the untracked `data/` folder. Data files are never committed.

## Labelling policy

- Every number obtained from the development set is a "development
  observation (6-file development set)".
- None of it enters README.md, docs/, notebooks/ or
  results/production.json.
- It does not re-select any model, cut or default: the defaults chosen on
  the original development file are only confirmed (or a problem is
  reported).

## Files

Selected on 2026-10-29 by `scripts/development_set.py` (output: the five
names below and "disjoint from production: OK"). No lower-index file had to
be skipped: the lowest-index files of both records are neither the original
development file nor production files. Downloaded with `cmsopen fetch`
(size and adler32 verified against the values below, from the record's file
index) into `data/` (not tracked). Free disk space before downloading:
76.4 GB.

| order | file | record (run) | index | bytes | adler32 |
|---|---|---|---|---|---|
| 1 | 45F7AE81-7A79-4CB1-998E-7BD156490294.root | 31129 (2012C) | (original development file) | 1,145,602,936 | 9f7301c5 |
| 2 | 06C1145E-99D4-4DAC-859D-F634CC8714AF.root | 31129 (2012C) | 0 | 1,542,887,879 | 5dbc2549 |
| 3 | 0995C487-F7CE-4AC4-851D-F3202F7A9712.root | 31129 (2012C) | 1 | 1,591,473,515 | dad1b86b |
| 4 | 0B22B275-85C5-4E44-8D89-D18B56091507.root | 31129 (2012C) | 2 | 1,545,239,719 | 9565b142 |
| 5 | 03C5684F-8BAF-4312-8235-2B0039F2FB93.root | 31123 (2012B) | 0 | 1,454,534,615 | 07ab1c98 |
| 6 | 12EE191C-00CB-4150-BBD9-8D1266BB7FD8.root | 31123 (2012B) | 1 | 1,430,080,716 | 4f41a164 |

Total 8,709,819,380 bytes (8.71 GB). The machine-readable list is
`dev/development_set.json`.
