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

To be filled in after selection and download (name, record, index, size
in bytes, adler32).
