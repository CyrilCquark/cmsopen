# Reproducibility

{{ dry_banner }}

## What ran

| item | value |
|---|---|
| analysis commit | `{{ git_head }}` |
| first attempt at commit | `{{ first_head }}` |
| model freeze commit | `{{ freeze_commit }}` |
| attempts | {{ n_attempts }} ({{ n_failed_attempts }} failed or interrupted, {{ n_code_fixes }} code fixes) |
| sample | {{ n_files }} files, {{ total_bytes }} bytes |
| gates at that commit | {{ gates_summary }} |

## Verify what is committed (about a minute after the install, no download)

```bash
pip install -e ".[dev]"
shasum -a 256 results/production.json results/production_files.json
python scripts/production_schema.py
python scripts/check_readme_numbers.py
python scripts/check_blinding.py
python scripts/apply_production.py --check
python scripts/production_report.py
```

`apply_production.py --check` regenerates every generated file in memory and compares bytes, so a file edited by hand
is reported.

| file | SHA-256 |
|---|---|
| `results/production.json` | `{{ production_sha }}` |
| `results/production_files.json` | `{{ registry_sha }}` |
| analysis configuration | `{{ config_sha }}` |
{{ figure_hashes }}

If `results/figures_rerender.json` exists, the figures were rendered again after the run, for layout and captions only,
by `scripts/rerender_production_figures.py`. That script reruns the analysis on the same files and writes nothing unless
every number equals `results/production.json`; the file records the commit, the check and the figure hashes.

## Run the analysis again

This needs the {{ total_gb }} GB of registered files and several hours, mostly the download. The commit that ran the
analysis has no results yet, so the production command runs there:

```bash
git clone {{ repo_url }}.git && cd cmsopen
git checkout {{ git_head }}
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python scripts/run_gates.py
python scripts/production_run.py --confirm-single-production-run
```

The file names stay in the registry and the commands do not print them. Then compare the
`channels` section of your `results/production.json` with the committed one. Byte-identical results (T1) are expected
for the same inputs and the same software; use the versions below. Timings and the environment hash differ between
machines.

## Environment

Python {{ python }} ({{ implementation }}) on {{ platform }}, environment SHA-256 `{{ env_sha }}`.

{{ packages_table }}

## Files of the sample

By index; the names are in the registry.

{{ files_table }}
