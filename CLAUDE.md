# CLAUDE.md

## Project goal

`cmsopen` is an open-source Python library for analyzing real CMS collision
data from [opendata.cern.ch](https://opendata.cern.ch). It reconstructs the
Z boson invariant mass peak (~91 GeV) from DoubleMuon NanoAOD files.

## Environment rules

- Always use the project venv at `.venv` (Python 3.12). Activate it before
  running anything: `source .venv/bin/activate`.
- Never use the system `python3` (3.9.6, too old).
- Install: `pip install -e ".[dev]"`
- Test: `pytest` (runs everything; this is the full run used by the
  Definition of done and by `scripts/check_quality.py`).
- Fast run for development: `pytest -m "not slow"`. The `slow` marker
  (registered in pyproject.toml) is on tests that take more than about 5 s,
  read the real data file, run the 1,000-toy pull test, or start worker
  processes (all of `tests/test_parallel.py`). Measured durations of both
  runs are in `dev/benchmarks.md`.

## Working on a new machine

Keep the project outside iCloud-synced folders (Desktop, Documents); use
`~/Developer`. Facts about the data file come from `DATA.md`.

```bash
brew install python@3.12 gh
gh auth login
mkdir -p ~/Developer && cd ~/Developer
git clone https://github.com/CyrilCquark/cmsopen.git
cd cmsopen
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
# Resumable download (~1.1 GB); rerun the same command to resume.
curl -fL -C - -o data/45F7AE81-7A79-4CB1-998E-7BD156490294.root \
  https://opendata.cern.ch/eos/opendata/cms/derived-data/NanoAODRun1/01-Jul-22/Run2012C_DoubleMuParked/45F7AE81-7A79-4CB1-998E-7BD156490294.root
stat -f %z data/45F7AE81-7A79-4CB1-998E-7BD156490294.root   # must print 1145602936
export CMSOPEN_DATA_FILE="$PWD/data/45F7AE81-7A79-4CB1-998E-7BD156490294.root"
pytest
```

If the size differs, the download is incomplete: rerun the `curl` command.

## Architecture

All modules live under `src/cmsopen/`.

| Layer | Module | Purpose |
|---|---|---|
| 1 | `ingestion.py` | Open NanoAOD ROOT files (local or XRootD) with uproot; read only the needed branches into awkward arrays, in chunks. |
| 2 | `objects.py` | Build physics objects (muons) from flat branches: pt, eta, phi, mass, charge, ID and isolation, as awkward records. |
| 3 | `selection.py` | Event and object cuts: muon ID, isolation, pt/eta thresholds, and the opposite-charge requirement. |
| 4 | `combinatorics.py` | Form muon pairs per event (all combinations or the leading two) without Python loops. |
| 5 | `kinematics.py` | Four-vector math with `vector`: invariant mass, pair pt, rapidity, ΔR. |
| 6 | `fitting.py` | Fit the dimuon mass spectrum (Breit-Wigner or Voigtian signal plus background) with scipy; extract the Z mass and width. |
| 7 | `plotting.py` | Publication-quality matplotlib/hist plots of the spectrum and fit. |
| 8 | `pipeline.py` | End-to-end driver: files → objects → selection → pairs → mass → fit → plot. |
| 9 | `notebooks/` | Worked, narrated examples that reproduce the Z peak from real data. |
| 10 | Packaging/docs | README physics explanation, pyproject metadata, release to PyPI. |

## Build order

ingestion → objects → kinematics → selection → combinatorics → fitting →
plotting → pipeline → notebooks → packaging/README

(by layer number: 1 → 2 → 5 → 3 → 4 → 6 → 7 → 8 → 9 → 10)

## Quality bar

- Anyone who clones the repo must be able to reproduce the Z peak from real
  CMS data.
- Every public function has a docstring that explains the physics, not just
  the code.
- Use vectorized numpy/awkward only. No Python loops over events.
- Energies, momenta and masses are in GeV.
- PDG Z mass and width: read at runtime from the `particle` package
  (`cmsopen.fitting.pdg_mass_width`); currently 91.1879 GeV. The 91.1876 GeV
  value this project started from is from an earlier PDG edition. Code must
  never hard-code the PDG values.
- Plots are publication quality: labeled axes with units, a legend, and a
  CMS Open Data label.
- The README explains invariant mass and why the Z peak appears where it
  does.
- Docstrings describe methods and physics and contain no numbers produced by
  running on the real data (synthetic test inputs are fine). Notebooks in
  `examples/` are committed with cleared outputs, and their markdown cells
  make no claims about measured values.
- CLAUDE.md may keep status lines but must NOT contain measured results.

## Documentation freeze

Protected paths: never edit, add, delete or regenerate them without the
user's explicit written instruction in a prompt.

- `README.md`, `DATA.md`, `LICENSE`, `CITATION.cff` (if present)
- `docs/**`, `notebooks/**`
- `results/production.json` (may only ever be created by the future
  production run)

`python scripts/check_docs_frozen.py --since <rev>` fails if any protected
path was modified, added, deleted or renamed since `<rev>`, in commits or in
the working tree (including untracked files). `examples/make_figures.py`
writes to the untracked `build/figures/` by default and writes into
`docs/figures/` only with `--production`, which must never be run without
that explicit instruction.

## Results integrity

- The README and all results-bearing documentation are written ONCE, from
  the final production run. They contain only numbers and figures produced
  by the committed code from the pre-registered production sample
  (`results/production_files.json`), whether or not those numbers look good.
- Development-file numbers never appear in them.
- Targets and controlling benchmarks (`dev/targets.md`) may appear in them
  only labelled as benchmarks, next to the observed value (see "Controlling
  benchmarks"). A missed target is reported as
  missed, with the measured value; it is not corrected after the fact.
- All analysis choices (cuts, models, fit ranges, binning) are made on the
  development file `data/45F7AE81-7A79-4CB1-998E-7BD156490294.root` before
  the production sample is opened.
- Blinding: no production filename appears in any tracked file other than
  the registry, and the registry matches `dev/registry.sha256`
  (`python scripts/check_blinding.py`). The README results block (between
  `<!-- RESULTS:BEGIN -->` and `<!-- RESULTS:END -->`) must equal the text
  rendered from `results/production.json`, and contains no digits while that
  file does not exist (`python scripts/check_readme_numbers.py`).

## Controlling benchmarks (all-time-highest policy)

Adopted from the user's AMBITION OVERRIDES. Binding on every layer, phase and
future prompt.

1. Every metric has one permanent controlling benchmark: the most ambitious
   value ever established for it, whether a target, a requirement or a
   verified production result (the largest for higher-is-better metrics, the
   smallest for lower-is-better metrics).
2. The controlling benchmark is applied consistently in all requirements,
   project descriptions, planning documents, acceptance criteria,
   specifications and future prompts. No lower value displaces it: a weaker
   measured result never replaces it, and a less ambitious value stated in a
   later prompt does not apply (the discrepancy is pointed out to the user).
   A verified production result that beats the benchmark becomes the new
   benchmark.
3. Only the user's explicit written authorization in a prompt can reduce a
   controlling benchmark.
4. Every project summary shows two clearly labelled values for each metric:
   the controlling benchmark ("benchmark", kept prominent) and the observed
   value ("observed", the measured result, with "met" or "not met"). The
   benchmark is never labelled as observed or achieved, and an observed value
   is never labelled as the benchmark.
5. Experimental output, verification logs, statistical reports and test
   results always record the accurate measured values.
6. The AMBITION OVERRIDES implementation requirements below and the
   historical benchmark registry in `dev/targets.md` are permanent and are
   updated whenever a stronger value is established.

### Mandatory AMBITION OVERRIDES requirements

Not yet in place unless the Status table says so; until measured, nothing
here may be described as achieved.

1. Production sample: 20 pre-registered files, 12 from record 31129 (Run
   2012C) and 8 from record 31123 (Run 2012B), chosen by the rule recorded in
   `results/production_files.json` (done in Phase 1; never opened before the
   production run).
2. Engineering gates: pytest-cov with `pytest --cov=cmsopen
   --cov-fail-under=90`, mypy with `disallow_untyped_defs` and
   `warn_unused_ignores`, `ruff check src/`, all enforced in CI; coverage
   from genuine tests, not exclusions.
3. Parallel processing: `n_workers` in `analyze()` (`None` serial, > 1 a
   `ProcessPoolExecutor`), deterministic merging with exactly equal masses,
   cutflow and fit results; `scripts/benchmark.py` measuring serial, 2-,
   4- and all-core throughput and peak memory, its output kept separately.
4. Test rigor: at least 1,000 pull-test toys, at least three deliberate-
   breakage checks per layer, at least 5,000 validation pairs per category.
5. J/psi channel: at least 2,000 opposite-sign pairs in 2.9-3.3 GeV, a
   clearly visible peak, sideband signal-to-background at least 1; the
   decision to pursue the channel stays evidence-based.
6. Self-checks for that phase: parallel equals serial exactly, coverage gate,
   mypy, ruff.
7. Targets T2 (chi2/ndf at most 2.0), T4 (the 20-file sample), T6 (Run 2012B
   versus 2012C consistency) and T7 (engineering) as in `dev/targets.md`.

## Workflow

- Build one layer at a time.
- Write tests with each layer.
- Commit after each layer once its tests pass.
- Never commit ROOT files. `data/` and `*.root` are gitignored.
- Confirm branch names against the real file (for example by listing
  `tree.keys()`) before relying on them.

## Definition of done

Standing rule for every layer. A layer is NOT done until ALL of these hold:

(a) pytest passes.
(b) `examples/` contains a committed demo SCRIPT and a committed demo
    NOTEBOOK for the layer. Both run the same self-checks and print
    "OK: ..." / "FAIL: ..." lines; the script exits 1 on any FAIL and
    prints "All checks passed" otherwise. The notebook's first cell reads
    the data path from the environment variable `CMSOPEN_DATA_FILE` and
    raises a clear error if it is unset. Build notebooks with nbformat,
    validate them, and commit them with outputs cleared.
(c) The demos have been run from a FRESH CLONE in a FRESH virtual
    environment with a normal, non-editable install, from a different
    working directory, and the full real output has been shown to the user.
(d) LIVE BROWSER CHECK in the user's real Chrome (see below) has been done
    and reported.
(e) The user has been given exact copy-paste commands to reproduce the
    verification themselves.
(f) The docs-freeze check passes against this layer's START commit
    (`python scripts/check_docs_frozen.py --since <START>`).
(g) `python scripts/check_blinding.py` and
    `python scripts/check_readme_numbers.py` pass.
(h) From Layer 8 onward: line coverage of `src/cmsopen` at or above 90 %,
    mypy and ruff clean, shown by `python scripts/check_quality.py` ending in
    "OK: quality gates pass" (it runs `pytest --cov=cmsopen
    --cov-fail-under=90`, `mypy src` and `ruff check src tests scripts
    examples`, configured in pyproject.toml).

Process rule (full suite before such commits): before committing ANY change
to a default, a check or an existing test, run the FULL test suite (`pytest`,
not `pytest -m "not slow"`) and show that it passes in the same step. The
fast suite is only for iteration. Commits are gated on pytest's OWN exit
status: use `set -o pipefail`, or `pytest ...; rc=$?; [ $rc -eq 0 ] && git
commit ...`. Never pipe pytest into tail, head or tee when its exit status
gates something. Before EVERY commit that touches code, notebooks or
examples, also run ruff on all files (`ruff check src tests scripts
examples`, which includes the notebooks) and `mypy`, in addition to the
tests; the full `python scripts/check_quality.py` runs before the last
commit of each phase.

Never claim success without showing real command output. If a check
fails, report the failure. Do not weaken or edit a check to make it pass.

### Live browser check (the human simulation)

1. Use the Claude in Chrome browser tools. If they are not connected,
   STOP and tell the user to run /chrome (Reconnect extension). Do not
   skip this step silently and do not fake it.
2. In the temp venv from the verification procedure, install with dev
   extras: `pip install "./clone[dev]"`.
3. Start JupyterLab as a background process from the temp dir:
   `jupyter lab --no-browser --ServerApp.ip=127.0.0.1 --port <a free port>
   --notebook-dir <temp>/clone/examples --LabApp.workspaces_dir=<temp>/ws`
   with `CMSOPEN_DATA_FILE` set to the absolute path of the real ROOT file.
   The fresh workspace directory stops JupyterLab from restoring documents
   from earlier sessions, whose unsaved state blocks closing the tab. Read
   the URL with its token from the server log. Before closing the tab, save
   the notebook (it is the temp clone's copy) so no "Leave site?" prompt
   appears.
4. PREFLIGHT, before running the notebook: in the chosen browser open the
   Jupyter URL in a new tab and confirm the page title (it must load and
   show JupyterLab). If it cannot load (the browser may be on another
   machine and unable to reach this Mac's 127.0.0.1), pick another browser
   with /chrome "Select browser" or the tool's browser-selection step. Never
   count a run in the wrong browser.
5. In Chrome, open a NEW tab to that URL, open the layer's demo notebook,
   and do what a human would: Run > Run All Cells. Wait until every cell
   has finished (no busy indicators), then read the output cells from the
   page. Confirm the final self-check cell says "All checks passed" and
   that there are no red error tracebacks. Take a screenshot and record a
   GIF of the run. Save both OUTSIDE the repo in
   `~/Developer/cmsopen-verification/` (named `layerN-chrome.png` and
   `layerN-chrome.gif`) and never commit them.
6. Browse ONLY the localhost Jupyter URL. Do not visit any other site, do
   not use the user's other tabs, never enter credentials. If a login page
   or CAPTCHA appears, pause and ask the user.
7. Afterwards, shut down only the Jupyter process you started and close
   only the tab you opened.
8. Report what you saw on screen: notebook name, how many cells ran, and
   the final check lines.

### Verification procedure (for each layer's demos)

1. In the dev venv: `pytest -q`, show the counts.
2. Create a temp dir with `mktemp -d`. Inside it: `git clone` the local
   repo (committed state only), create a fresh venv with
   `python3.12 -m venv`, and install with `pip install ./clone` (NOT -e).
3. From the temp dir (NOT the repo), run the demo SCRIPT with the temp
   venv's python and `--file` set to the absolute path of the real ROOT
   file in the original repo's `data/` folder. Also print
   `cmsopen.__file__` to prove the import comes from the temp venv's
   site-packages and not the source tree. Show the COMPLETE real output.
4. Run the live browser check above for the notebook.
5. Remove only the temp dir you created (keep the screenshot and GIF in
   `~/Developer/cmsopen-verification/`).
6. Finish with a section titled "How to verify this yourself" containing
   exact copy-paste commands for the user's own Terminal (cd, venv
   creation, install, the script command, and the `jupyter lab` command
   with the notebook path and `CMSOPEN_DATA_FILE`), the expected final
   lines of output, and what a failure would look like.

## Status

| Layer | State |
|---|---|
| 1 ingestion | Done: (a)–(e) met; live browser check 2026-10-27. |
| 2 objects | Done: (a)–(e) met; live browser check 2026-10-27. |
| 3 selection | Done: (a)–(e) met; live browser check 2026-10-27, Tier 1 (Claude in Chrome). |
| 4 combinatorics | Done: (a)–(e) met; live browser check 2026-10-27, Tier 1 (Claude in Chrome). |
| 5 kinematics | Done: (a)–(e) met; live browser check 2026-10-27. |
| 6 fitting | Done: (a)–(e) met; live browser check 2026-10-27, Tier 1 (Claude in Chrome). |
| 6b line shape and validation | Done: (a)–(h) met; live browser check 2026-10-29, browser check Tier 1 (Claude in Chrome). |
| 6c resolution mixture | Done: (a)–(h) met; live browser check 2026-10-29, browser check Tier 1 (Claude in Chrome). |
| 6d three-resolution amendment, scaled validation errors | Done: (a)–(h) met; Amendment 3 selected no model (defaults unchanged); live browser check 2026-10-29, browser check Tier 1 (Claude in Chrome). |
| 7 plotting | Done: (a)–(e) met; live browser check 2026-10-27, Tier 1 (Claude in Chrome). |
| 8 pipeline | Done: (a)–(h) met; live browser check 2026-10-28, browser check Tier 1 (Claude in Chrome). |
| 9–10 | Not started. |

## Model freeze

Recorded in full in dev/model_choice.md ("Model freeze"); summary:

Frozen at commit `35af6445db8d601972e60d3ba03f7c19a99527bb` (START11; the
configuration lives in `src/cmsopen/pipeline.py`, blob `0b910b2` at that
commit). Validation plan: dev/validation_plan.md, blob `9f9492b` at that
commit (the plan with its addenda of prompts 7, 8 and 10).

| | Z_mumu | Jpsi_mumu |
|---|---|---|
| default model | `cb2_bw_exp` (Amendment 2) | `cb2_bw_poly2` (Amendment 2) |
| cb_n (fixed) | 2 | 100 (Amendment 1) |
| validation model | `cb_bw_exp` | `cb_bw_poly2` |
| histogram range, bin width | 60-120 GeV, 1 GeV (60 bins) | 2.6-3.6 GeV, 0.02 GeV (50 bins) |
| fit range | 70-110 GeV | 2.8-3.4 GeV |
| polynomial degree (alternate fits) | 2 | 2 |
| trigger (any of) | HLT_Mu17_Mu8, HLT_Mu17_TkMu8 | HLT_Dimuon8_Jpsi, HLT_Dimuon10_Jpsi |
| muon cuts | pT > 20 GeV, abs(eta) < 2.4, tight ID, PF relative isolation (cone 0.4) < 0.12 | pT > 3 GeV, abs(eta) < 2.4, soft ID |
| events | at least two selected muons | at least two selected muons |
| pair choice | opposite charge, the pair with the highest pT sum (mass-blind) | same |
| minimum pairs in the fit range | 100 | 100 |
| stability grid: fit ranges | 70-110, 75-105, 80-100 GeV | 2.8-3.4, 2.85-3.35, 2.9-3.3 GeV |
| stability grid: bin widths | 0.5, 1, 2 GeV | 0.01, 0.02, 0.04 GeV |
| natural width | from the `particle` package | from the `particle` package |

Validation: at least 5,000 pairs per entry; categories, charge, pT, pileup
and working-point scans as in the plan; scaled errors as in its prompt 10
addendum.

Rule: from now on, any change to these requires the user's explicit
approval and a recorded amendment written before the change. A bug fix that
alters any result is reported to the user before it is committed.

## Note on branch names

The 2012 Run 1 NanoAOD branch names may differ from modern NanoAOD,
especially the isolation and ID branches (for example `Muon_pfRelIso04_all`
and `Muon_tightId`). Verify every branch name against the actual data file
before using it.
