# Post-production runbook

What happens after `PRODUCTION RUN COMPLETE` (`dev/production_runbook.md`). One command writes every results-bearing
file from `results/production.json`, `docs/figures/` and the run's saved outputs in `build/production/`; nothing is typed
by hand. Do these steps in this order.

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

`apply_production.py` is only on the branch, and it requires the production commit to be an ancestor of HEAD.

```bash
git status --short
git add results/production.json results/production_run.lock results/production_run.log docs/figures
git commit -m "Production run: results and figures"
git merge --no-ff post-production
pip install -e ".[dev,docs]"   # dev adds nbclient and jsonschema, docs adds mkdocs; only now may the venv change
```

## 3. See the extra benchmark values

Read-only: it opens no data file and writes nothing.

```bash
python scripts/production_extras.py
```

Every registry benchmark with its observed value, or `not derivable` with the reason: the J/psi pairs in 2.9-3.3 GeV and
sideband S/B from the saved histogram (definition in `dev/targets.md`, with the fit-based value beside it as a labelled
cross-check only), and the toy results, labelled "from the test
suite, not production data". Review these with Claude as well: the report in step 1 does not have them.

## 4. Rehearse

```bash
python scripts/apply_production.py --rehearse
```

The whole apply step in a throwaway copy of this tree, including all three notebooks: nothing here changes. Success ends
with `REHEARSAL PASSED` and lists the files it would change. **Go on only if it passes.** If it fails, stop and report it.

## 5. Generate everything

```bash
python scripts/apply_production.py
git diff DATA.md
```

It refuses and writes nothing unless `results/production.json` passes the schema check, is not a dry run, matches the
registry hash, has a commit that is an ancestor of HEAD, and the figure captions state the same peaks.

It then writes the 16 repository files below and the application assets, and runs: `check_readme_numbers.py`,
`check_release_metadata.py`, `check_blinding.py`, the audit of numbers, `mkdocs build --strict`, and all three notebooks
top to bottom. Success ends with `APPLY COMPLETE` and lists the changed files. It does not commit. Takes about a minute.

Your email address stays out by default. To put it in `CITATION.cff`, add `--include-email` to both commands of steps 4
and 5. `.zenodo.json` has no field for it.

| generated | from |
|---|---|
| `README.md` | `templates/README.md`, `scripts/render_results.py` (results block), `scripts/generate_release_files.py` |
| `README_PYPI.md` (the package's long description) | the README, images and links pinned to tag `v<version>` |
| `DATA.md` | the existing file plus `templates/DATA_md_addition.txt` and `templates/DATA_md_citation_addition.txt` |
| `results/production_extras.json` | `scripts/production_extras.py`, kept because `build/` is not in the repository |
| `docs/index.md` | the README, links rewritten |
| `docs/physics.md`, `user_guide.md`, `api.md`, `validation.md`, `reproducibility.md`, `changelog.md` | `templates/docs/` |
| `CITATION.cff`, `.zenodo.json` | `templates/release_metadata.json`, `templates/citation_abstract.md`, `DATA.md` |
| `notebooks/01_z_peak.ipynb`, `02_jpsi_peak.ipynb`, `03_modular_usage.ipynb` | `templates/notebooks/`, `examples/build_production_notebooks.py` |
| `~/Developer/cmsopen-application/*` | `templates/application/`, `scripts/make_application_assets.py`, `docs/figures/` |

If a check fails, the files are written but nothing is committed; report it. Do not edit a generated file: change the
template or the generator, then rerun. Read the generated README and the application assets yourself before going on,
and add your mentor's name to the email.

## 6. Commit the generated files

`run_gates.py` requires a clean tree.

```bash
git status --short
git add -A README.md README_PYPI.md DATA.md CITATION.cff .zenodo.json docs notebooks results/production_extras.json
git commit -m "Generated documentation from the production run"
python scripts/apply_production.py --check   # OK: ... byte-identical
```

## 7. Run the notebooks in Chrome

The live browser check of CLAUDE.md for `notebooks/01_z_peak.ipynb`, `02_jpsi_peak.ipynb` and `03_modular_usage.ipynb`
(Layer 9): JupyterLab on `--notebook-dir notebooks`, Run All Cells, final cell `All checks passed`, screenshot and GIF in
`~/Developer/cmsopen-verification/`. Ask Claude to do this.

## 8. Run the gates once

```bash
caffeinate -dimsu python scripts/run_gates.py
```

Success prints `pytest: exit 0; ... passed`, `check_quality: exit 0; ['OK: quality gates pass']` and the record's path.
If it fails, stop and report it. Do not tag.

## 9. Benchmark registry

Under the policy in CLAUDE.md, a verified production result that beats a benchmark becomes the new benchmark, and
`dev/targets.md` is the permanent registry ("Verified production results so far: none"). Check each row of step 3 with
Claude, update the file by hand where a result beats its benchmark, and commit it before step 10; it is not protected.

chi2/ndf stays at <= 2.0: a lower observed value is reported as observed and does not replace the benchmark, because
chi2/ndf is a consistency window, not a higher-is-better metric.

A change to `dev/targets.md` changes the generated table, so rerun steps 4 to 6 afterwards.

## 10. Tag

First set your ORCID, the one TODO left: in `templates/release_metadata.json` set `"orcid"` to the bare identifier
(`0000-0000-0000-0000` form), or to `""` if you have none. Then rerun steps 4 to 6 and:

```bash
python scripts/check_release_metadata.py --release
git tag -a v0.1.0 -m "cmsopen 0.1.0"
```

The tag must be `v` plus `cmsopen.__version__`: `README_PYPI.md` is pinned to it. Any commit after step 8 that touches
code means rerunning the gates.

## 11. Push

```bash
git push origin main --follow-tags
```

## Left for you

- **PyPI.** `.github/workflows/publish.yml` builds only, and its upload step is absent on purpose. Set up trusted
  publishing and add the step. The images in the long description load only once the tag is pushed and the repository is
  public, so publish to PyPI after both.
- **Zenodo DOI.** Connect the repository in Zenodo, then release. `.zenodo.json` must not carry `"orcid": "TODO"` at
  that point, because Zenodo may reject it (step 10 removes it). When the DOI exists, add `"doi"` to
  `templates/release_metadata.json`, rerun the apply step, and commit.
- **Making the repository public**, only when you say so. The quick start's `git clone` and the checklist for
  admissions readers work for others only after that. Your email address is still the author address of every commit and
  is in `templates/release_metadata.json`, whatever `CITATION.cff` says.
- **GitHub Pages.** `.github/workflows/docs.yml` runs only when started by hand. Enable Pages from Actions first.
- **Cleaning up** the worktree: `git worktree remove ~/Developer/cmsopen-post`.
