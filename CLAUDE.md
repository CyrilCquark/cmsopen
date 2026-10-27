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

## Note on branch names

The 2012 Run 1 NanoAOD branch names may differ from modern NanoAOD,
especially the isolation and ID branches (for example `Muon_pfRelIso04_all`
and `Muon_tightId`). Verify every branch name against the actual data file
before using it.
