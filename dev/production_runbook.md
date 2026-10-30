# Production runbook

The production analysis is run **once**, by the user, on the pre-registered
production sample (`results/production_files.json`: 20 files, 12 from record
31129 = Run2012C and 8 from record 31123 = Run2012B). Nothing in this file has
been run on the production sample. The commands print no production file name.

## Before you start

- Disk: the download is 29.99 GB; the preflight requires at least twice that
  free (59.98 GB). On 2026-10-29 the machine had 62.4 GB free, a thin margin.
  If you need room, the five extra development-set files in `data/` (7.6 GB,
  dev/development_set.md) can be deleted; the original development file is
  still needed by the development tests.
- Time: about 5 hours for the download at the 1.5-1.8 MB/s measured from the
  CERN Open Data portal on 2026-10-29, then about 40-60 minutes of analysis
  and figures (estimated from the 6-file development set: per channel about
  1 minute per 6 files for the analysis with validation using 4 workers, the
  serial repeat about twice that, plus the per-period fits and the figures).
- Use the project venv: `cd ~/Developer/cmsopen && source .venv/bin/activate`.

## Commands, in order

1. Make sure the working tree is clean and pushed:

   ```bash
   git status --short        # prints nothing
   ```

2. Record the full test suite and the quality gates at HEAD (35-50 minutes):

   ```bash
   python scripts/run_gates.py
   ```

   Success prints `pytest: exit 0; ... passed`, `check_quality: exit 0;
   ['OK: quality gates pass']` and `recorded in build/gates/<HEAD>.json`.

3. Preflight:

   ```bash
   python scripts/production_preflight.py
   ```

   Success: eleven `PASS:` lines and `PREFLIGHT PASSED`.

4. The production run (download, figures, analysis, results/production.json):

   ```bash
   python scripts/production_run.py --confirm-single-production-run
   ```

   Success prints the preflight's `PASS:` lines, then
   `downloaded and verified file k/20 (record ..., index ..., ... bytes)` for
   each file, `run lock written: results/production_run.lock`,
   `figures written: 6 figure files, the caption and the README in docs/figures/`, one line per channel
   (`Z_mumu: cb2_bw_exp, peak ... GeV, chi2/ndf ...; T1 True`, then the same
   for `Jpsi_mumu`), `written: results/production.json (total ... s)` and
   finally `PRODUCTION RUN COMPLETE`.

5. Review, then commit the outputs yourself:

   ```bash
   git status --short
   python scripts/render_results.py   # the README results block, generated from results/production.json
   ```

   The run creates or modifies exactly these paths in the repository:
   `results/production.json` (protected, new), `results/production_run.lock`
   (new), and `docs/figures/README.md`, `docs/figures/cutflow.png`,
   `docs/figures/muon_eta.png`, `docs/figures/muon_pt.png`,
   `docs/figures/z_os_vs_ss.png`, `docs/figures/z_peak_fit.pdf`,
   `docs/figures/z_peak_fit.png`, `docs/figures/z_peak_fit_caption.md`
   (protected, modified). It also writes the 20 downloads to `data/production/`
   and the per-channel outputs (which list the input files) to
   `build/production/`; both are gitignored. The README results block is
   updated by hand from the `render_results.py` output (README.md is
   protected); `scripts/check_readme_numbers.py` then checks it.

## If something goes wrong

- **The download is interrupted** (network error, laptop asleep): run the
  same command again (step 4). Nothing has been opened yet: the run lock is
  written only after every file is downloaded and verified. Partial files in
  `data/production/` are resumed (the preflight accepts files there and
  nowhere else). A file that fails its size or checksum check is reported as
  `FAIL: download of file k/20 ...`; run the command again to retry.
- **A preflight check fails** (`FAIL:` lines, `REFUSED: the preflight
  failed`): fix the cause it names (commit or stash changes; rerun
  `scripts/run_gates.py` after a new commit; free disk space; wait for the
  network) and start again from that step. Do not edit a check.
- **`REFUSED: single-run guard`**: the production run has already started
  (the lock or results/production.json exists). Do not delete them to run
  again; report it.
- **`FAIL: the production analysis failed`** after the lock was written: the
  files have been opened. Do not rerun; report the message. Any change after
  this point is an amendment (dev/model_choice.md, "Model freeze").
- **`FAIL: T1`**: the results are written, but the two runs differ; report it.

## Once only

This command must be run once. The single-run guard (the lock and
results/production.json) enforces it; a second run is refused. The
evaluation of the targets (T1, T2, T4, T6 in dev/targets.md) is read from
results/production.json as it is; nothing is refitted or tuned afterwards.
