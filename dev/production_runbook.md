# Production runbook

The production analysis is run **once**, by the user, on the pre-registered
production sample (`results/production_files.json`: 20 files, 12 from record
31129 = Run2012C and 8 from record 31123 = Run2012B). Nothing in this file has
been run on the production sample. The commands print no production file name.

## Before you start

- Power and sleep: plug the Mac in and keep it awake for the long steps
  (the gates and the production run). Run them under `caffeinate -dimsu`,
  which keeps the display, the system and the disk awake while the command
  runs (and asserts the user is active), for example
  `caffeinate -dimsu python scripts/production_run.py --confirm-single-production-run`.
  Do not close the lid. If the Mac sleeps anyway, nothing is lost: run the
  same command again (see "If something goes wrong").
- Disk: the download is 29.99 GB; the preflight requires at least twice that
  free (59.98 GB). On 2026-10-30 the machine had about 53-59 GB free (the
  preflight measured 58.9 GB on 2026-10-29): the disk check FAILS today. Free
  space first; candidates (sizes measured 2026-10-30; nothing was deleted):
  the five extra development-set files in `data/` (7.6 GB of the 8.7 GB
  there, dev/development_set.md; the original development file is still
  needed by the development tests), `brew cleanup` (about 2.4 GB), and
  caches such as `~/Library/Containers/com.docker.docker` (43.8 GB, Docker's
  disk image), `~/.cache/huggingface` (9.5 GB) and `~/.npm` (4.5 GB).
- Time, from the measurements of 2026-10-30:
  - download: four files at a time (`--download-workers 4`, the default).
    `python scripts/measure_throughput.py` (50 MB range requests to the
    development files only) gave 0.61 MB/s for 1 stream, 1.27 for 2, 1.70 for
    3 and 1.86 MB/s for 4 streams in total (3.05 times one stream). At
    1.86 MB/s the 29.99 GB take about 4.5 hours; at that day's single-stream
    rate they would take about 14 hours (on 2026-10-29 one stream gave
    1.5-1.8 MB/s: the portal's rate varies from day to day);
  - analysis and figures: the 6-file dry run of the production command
    (8.71 GB, both channels, 4 workers) took 5.3 minutes after the download
    (Z_mumu 145 s, Jpsi_mumu 131 s, figures 26 s; peak resident memory
    0.88 GB). Scaled to 20 files (29.99 GB): about 15-20 minutes, plus about
    a minute to re-verify the 20 checksums on every attempt;
  - gates (`scripts/run_gates.py`): 35-50 minutes.
- Use the project venv: `cd ~/Developer/cmsopen && source .venv/bin/activate`.

## Commands, in order

1. Make sure the working tree is clean and pushed:

   ```bash
   git status --short        # prints nothing
   ```

2. Record the full test suite and the quality gates at HEAD (35-50 minutes):

   ```bash
   caffeinate -dimsu python scripts/run_gates.py
   ```

   Success prints `pytest: exit 0; ... passed`, `check_quality: exit 0;
   ['OK: quality gates pass']` and `recorded in build/gates/<HEAD>.json`.

3. Preflight:

   ```bash
   python scripts/production_preflight.py
   ```

   Success: twelve `PASS:` lines and `PREFLIGHT PASSED`.

4. The production run (download, analysis, figures, results/production.json;
   about 5 hours):

   ```bash
   caffeinate -dimsu python scripts/production_run.py --confirm-single-production-run
   ```

   Success prints `run state: not started`, the preflight's `PASS:` lines,
   `attempt 1 started`, then
   `downloaded and verified file k/20 (record ..., index ...), ... bytes` for
   each file in the order the downloads finish,
   `run lock written: results/production_run.lock`, one line per channel
   (`Z_mumu: cb2_bw_exp, peak ... GeV, chi2/ndf ...; T1 True`, then the same
   for `Jpsi_mumu`), `figures written: 12 files in docs/figures/ (figures,
   captions, README)`, `written: results/production.json (attempt 1, total ... s)`
   and finally `PRODUCTION RUN COMPLETE`.

5. Read the results and paste them back for review:

   ```bash
   python scripts/production_report.py > build/production_report.txt
   less build/production_report.txt
   ```

   The report names no file. It has: the run (commits, environment, every
   attempt and code fix); the T1-T7 table, each target with its controlling
   benchmark, the observed value and met / NOT MET; per channel the headline
   fit with the raw and the scaled statistical error, the offset from the PDG
   mass, the fit-choice spread and the alternate fit; Run 2012B versus Run
   2012C (T6); the validation table and systematics summary; the per-file
   fits; the cutflow; the timings. **Paste back the whole of
   `build/production_report.txt`** (and the last lines of the command's output
   if anything failed). A target that is not met is reported as not met;
   nothing is refitted.

6. Review, then commit the outputs yourself:

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
     `build/production/` (the per-channel outputs, which list the input files).

   The README results block is updated by hand from the `render_results.py`
   output (README.md is protected); `scripts/check_readme_numbers.py` then
   checks it.

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
