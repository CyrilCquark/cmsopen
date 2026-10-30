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
- Time: the download runs four files at a time (`--download-workers 4`, the
  default). Measured on 2026-10-30 with 50 MB range requests to the
  development files (`python scripts/measure_throughput.py`): 1 stream
  0.61 MB/s, 2 streams 1.27, 3 streams 1.70, 4 streams 1.86 MB/s in total
  (3.05 times one stream). At 1.86 MB/s the 29.99 GB take about 4.5 hours; at
  that day's single-stream rate they would take about 14 hours (on
  2026-10-29 a single stream gave 1.5-1.8 MB/s: the portal's rate varies from
  day to day). Then about 40-60 minutes of analysis
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

   Success: twelve `PASS:` lines and `PREFLIGHT PASSED`.

4. The production run (download, figures, analysis, results/production.json):

   ```bash
   python scripts/production_run.py --confirm-single-production-run
   ```

   Success prints `run state: not started`, the preflight's `PASS:` lines,
   `attempt 1 started`, then
   `downloaded and verified file k/20 (record ..., index ...), ... bytes` for
   each file in the order the downloads finish, `run lock written: results/production_run.lock`, one line per
   channel (`Z_mumu: cb2_bw_exp, peak ... GeV, chi2/ndf ...; T1 True`, then the
   same for `Jpsi_mumu`), `figures written: 12 files in docs/figures/ (figures,
   captions, README)`, `written: results/production.json (total ... s)` and
   finally `PRODUCTION RUN COMPLETE`.

5. Review, then commit the outputs yourself:

   ```bash
   git status --short
   python scripts/render_results.py   # the README results block, generated from results/production.json
   ```

   The run creates or modifies exactly these paths in the repository:

   - modified (protected): `docs/figures/README.md`, `docs/figures/cutflow.png`,
     `docs/figures/muon_eta.png`, `docs/figures/muon_pt.png`,
     `docs/figures/z_os_vs_ss.png`, `docs/figures/z_peak_fit.pdf`,
     `docs/figures/z_peak_fit.png`, `docs/figures/z_peak_fit_caption.md`;
   - new (protected): `docs/figures/jpsi_os_vs_ss.png`,
     `docs/figures/jpsi_peak_fit.pdf`, `docs/figures/jpsi_peak_fit.png`,
     `docs/figures/jpsi_peak_fit_caption.md`, `results/production.json`;
   - new: `results/production_run.lock` and `results/production_run.log` (the
     run's state and its log of attempts; commit both with the results);
   - gitignored: `data/production/` (the 20 downloads) and
     `build/production/` (the per-channel outputs, which list the input files). The README results block is
   updated by hand from the `render_results.py` output (README.md is
   protected); `scripts/check_readme_numbers.py` then checks it.

## States of the run

| state | what exists | what the command does |
|---|---|---|
| not started | nothing | starts attempt 1 |
| downloaded | the verified files in `data/production/`, the log | starts the next attempt (re-verifies every file, then writes the lock) |
| analysis started | `results/production_run.lock` (the files have been opened), the log | resumes, under the conditions below |
| complete | `results/production.json` | refuses (`REFUSED: single-run guard`, exit 3) |

Only "complete" blocks a new run. Every attempt is numbered and logged in
`results/production_run.log` (one JSON object per line: time, attempt, phase,
exception type, commits; no file names). A killed attempt (power, kill -9,
a closed lid that stopped the process) has no end line; the next attempt
records it as `interrupted` in the phase where it stopped.
`results/production.json` carries `attempts`: the count, every failed or
interrupted attempt (time, phase, exception type) and every code fix.

## If something goes wrong

Every failure is fixed by running the same command again (step 4), unless
it says otherwise. The log and the lock are the run's own state: the
preflight and `scripts/run_gates.py` do not count them as changes, and they
must not be deleted.

- **The download is interrupted** (network error, laptop asleep): run the
  same command again. Nothing has been opened yet. Every file already in
  `data/production/` is verified again by size and adler32 on every attempt;
  a truncated file is resumed with an HTTP Range request, a corrupted one is
  fetched again from the first byte (never trusted). Network errors are
  retried three times per file, after 10, 30 and 90 seconds.
- **A preflight check fails** (`FAIL:` lines, `REFUSED: the preflight
  failed`): fix the cause it names (commit or stash changes; rerun
  `scripts/run_gates.py` after a new commit; free disk space; wait for the
  network) and start again from that step. Do not edit a check.
- **`FAIL: the production analysis failed in phase '...'`** (after the lock),
  or the process was killed: the files have been opened. If the cause was
  outside the code (memory, sleep, a full disk, Ctrl-C), run the same
  command again: it resumes if HEAD is still the lock's commit, the working
  tree is clean apart from the lock and the log, and the Python environment
  is unchanged. Partial figures of the failed attempt in `docs/figures/` are
  restored to HEAD automatically before the checks.
- **A code fix is needed** after such a failure: report the message first.
  Commit the fix (no analysis choice may change: the channel configurations
  and the validation plan's constants are compared with the lock's hash, and
  the command refuses if they differ), run `python scripts/run_gates.py` for
  the new HEAD, then
  `python scripts/production_run.py --confirm-single-production-run --code-fix-reason "<what was fixed and why>"`.
  The new commit and the reason are recorded in the lock, the log and
  `results/production.json`. Without the flag a changed HEAD is refused
  (`REFUSED: HEAD ... differs from the lock's commit`, exit 8). Any change of
  an analysis choice is an amendment (dev/model_choice.md, "Model freeze") and
  is not possible through a resume.
- **`REFUSED: resuming needs a clean working tree`** (exit 8): commit or stash
  the changes it counts, then run again.
- **`REFUSED: single-run guard`** (exit 3): the run is complete. Do not delete
  results/production.json to run again; report it.
- **`FAIL: T1`**: the results are written, but the two runs differ; report it.

## Once only

This command completes once. The single-run guard (results/production.json)
enforces it; a run after completion is refused. A failed attempt is not a
second run: it is resumed, and every attempt is recorded. The evaluation of
the targets (T1-T7 in dev/targets.md) is read from results/production.json as
it is; nothing is refitted or tuned afterwards.
