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
- Test: `pytest`

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
- PDG Z mass: 91.1876 GeV.
- Plots are publication quality: labeled axes with units, a legend, and a
  CMS Open Data label.
- The README explains invariant mass and why the Z peak appears where it
  does.

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
   --notebook-dir <temp>/clone/examples` with `CMSOPEN_DATA_FILE` set to the
   absolute path of the real ROOT file. Read the URL with its token from
   the server log.
4. In Chrome, open a NEW tab to that URL, open the layer's demo notebook,
   and do what a human would: Run > Run All Cells. Wait until every cell
   has finished (no busy indicators), then read the output cells from the
   page. Confirm the final self-check cell says "All checks passed" and
   that there are no red error tracebacks. Take a screenshot and record a
   GIF of the run. Save both OUTSIDE the repo in
   `~/Developer/cmsopen-verification/` (named `layerN-chrome.png` and
   `layerN-chrome.gif`) and never commit them.
5. Browse ONLY the localhost Jupyter URL. Do not visit any other site, do
   not use the user's other tabs, never enter credentials. If a login page
   or CAPTCHA appears, pause and ask the user.
6. Afterwards, shut down only the Jupyter process you started and close
   only the tab you opened.
7. Report what you saw on screen: notebook name, how many cells ran, and
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
| 5 kinematics | Done: (a)–(e) met; live browser check 2026-10-27. |
| 3, 4, 6–10 | Not started. |

## Note on branch names

The 2012 Run 1 NanoAOD branch names may differ from modern NanoAOD,
especially the isolation and ID branches (for example `Muon_pfRelIso04_all`
and `Muon_tightId`). Verify every branch name against the actual data file
before using it.
