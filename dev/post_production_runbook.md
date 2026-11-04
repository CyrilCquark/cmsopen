# Post-production runbook

What happens after `PRODUCTION RUN COMPLETE` (`dev/production_runbook.md`). One command writes every results-bearing
file from `results/production.json` and `docs/figures/`; nothing is typed by hand. Do these steps in this order.

Do not merge the `post-production` branch while the production run may still resume. A resume requires HEAD to be the
lock's commit and a clean tree.

## 1. Review the report with Claude

```bash
cd ~/Developer/cmsopen && source .venv/bin/activate
python scripts/production_report.py > build/production_report.txt
```

Paste the whole of `build/production_report.txt` to Claude and go through it before anything is generated: T1-T7, the
headline fits, the warnings, the validation tables. A missed benchmark is reported as missed. Nothing is refitted.

## 2. Commit the production outputs, then bring in the branch

These two steps are additions to the order in the prompt: `apply_production.py` is only on the branch, and it requires
the production commit to be an ancestor of HEAD.

```bash
git status --short
git add results/production.json results/production_run.lock results/production_run.log docs/figures
git commit -m "Production run: results and figures"
git merge --no-ff post-production
pip install -e ".[dev]"      # adds mkdocs, nbclient, jsonschema; only now, after the run, may the venv change
```

## 3. Generate everything

```bash
python scripts/apply_production.py
```

It refuses and writes nothing unless `results/production.json` passes the schema check, is not a dry run, matches the
registry hash, has a commit that is an ancestor of HEAD, and the figure captions state the same peaks.

It then writes the 13 repository files below and the application assets, and runs: `check_readme_numbers.py`,
`check_release_metadata.py`, `check_blinding.py`, the audit of numbers, `mkdocs build --strict`, and all three notebooks
top to bottom. Success ends with `APPLY COMPLETE` and lists the changed files. It does not commit.
Takes about a minute. It also prints the benchmarks not met.

| generated | from |
|---|---|
| `README.md` | `templates/README.md`, `scripts/render_results.py` (results block), `scripts/generate_release_files.py` |
| `docs/index.md` | the README, links rewritten |
| `docs/physics.md`, `user_guide.md`, `api.md`, `validation.md`, `reproducibility.md`, `changelog.md` | `templates/docs/` |
| `CITATION.cff`, `.zenodo.json` | `templates/release_metadata.json`, `templates/citation_abstract.md`, `DATA.md` |
| `notebooks/01_z_peak.ipynb`, `02_jpsi_peak.ipynb`, `03_modular_usage.ipynb` | `templates/notebooks/`, `examples/build_production_notebooks.py` |
| `~/Developer/cmsopen-application/*` | `templates/application/`, `scripts/make_application_assets.py`, `docs/figures/` |

If a check fails, the files are written but nothing is committed; report it. Do not edit a generated file: change the
template or the generator, then rerun.

Read the generated README and the application assets yourself before going on. Add your mentor's name to the email.

## 4. Commit the generated files

An addition to the prompt's order, because `run_gates.py` requires a clean tree.

```bash
git status --short
git add -A README.md CITATION.cff .zenodo.json docs notebooks
git commit -m "Generated documentation from the production run"
python scripts/apply_production.py --check   # OK: ... byte-identical
```

## 5. Run the notebooks in Chrome

The live browser check of CLAUDE.md for `notebooks/01_z_peak.ipynb`, `02_jpsi_peak.ipynb` and `03_modular_usage.ipynb`
(Layer 9): JupyterLab on `--notebook-dir notebooks`, Run All Cells, final cell `All checks passed`, screenshot and GIF in
`~/Developer/cmsopen-verification/`. Ask Claude to do this.

## 6. Run the gates once

```bash
caffeinate -dimsu python scripts/run_gates.py
```

Success prints `pytest: exit 0; ... passed`, `check_quality: exit 0; ['OK: quality gates pass']` and the record's path.
35-50 minutes. If it fails, stop and report it. Do not tag.

## 7. Benchmark registry

Under the policy in CLAUDE.md, a verified production result that beats a benchmark becomes the new benchmark, and
`dev/targets.md` is the permanent registry ("Verified production results so far: none"). Update it by hand after
reviewing the results with Claude, and commit it before step 8; `dev/targets.md` is not a protected path.
A decision is needed for χ²/ndf, because a lower value is not simply better once it is below one: a fit far below one can
mean overestimated errors. Decide with Claude whether the registry should move, and record the decision there.

## 8. Tag

First finish the open TODOs. They are harmless warnings until now, but `--release` fails on them:

- your ORCID: in `templates/release_metadata.json` set `"orcid"` to the bare identifier (`0000-0000-0000-0000` form), or to
  `""` if you have none;
- the DOI for record 31123, which `DATA.md` does not record: check the portal and set `"record_dois"` in the same file.

Then rerun `python scripts/apply_production.py`, commit, and:

```bash
python scripts/check_release_metadata.py --release
git tag -a v0.1.0 -m "cmsopen 0.1.0"
```

Any commit after step 6 that touches code means rerunning the gates.

## 9. Push

```bash
git push origin main --follow-tags
```

## Left for you

- **PyPI.** `.github/workflows/publish.yml` builds only, and its upload step is absent on purpose. Set up trusted
  publishing and add the step. README images use repository-relative paths, which PyPI does not display; decide whether to
  point them at absolute URLs for the PyPI description once the repository is public.
- **Zenodo DOI.** Connect the repository in Zenodo, then release. `.zenodo.json` must not carry `"orcid": "TODO"` at
  that point, because Zenodo may reject it (step 8 removes it). When the DOI exists, add `"doi"` to
  `templates/release_metadata.json`, rerun the apply step, and commit.
- **Making the repository public**, only when you say so. The quick start's `git clone` and the checklist for
  admissions readers work for others only after that. `CITATION.cff` publishes the email address given in the metadata.
- **GitHub Pages.** `.github/workflows/docs.yml` runs only when started by hand. Enable Pages from Actions first.
- **Cleaning up** the worktree: `git worktree remove ~/Developer/cmsopen-post`.
