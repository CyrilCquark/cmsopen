# How an admissions reader can verify this in ten minutes

{{ dry_banner }}

No physics background or large download is needed. Times are rough.

**Two minutes, in a browser.**

- [ ] Open [{{ repo_url }}]({{ repo_url }}). The README's table lists each benchmark next to its observed value and says met or not met.
- [ ] Find any target marked not met. A project reporting honestly leaves those visible: {{ not_met_inline }}
- [ ] Open `results/production.json`, search for `peak_position_gev`, and compare the Z value with the README ({{ z.peak }} GeV after rounding).

**Five minutes, on a laptop with Python 3.10 or newer.**

- [ ] Run the quick start from the README: clone, `pip install .`, then the three commands, on the small committed sample.
- [ ] Check that the last command ends with `All checks passed`, and open `out/z/mass_fit.png` to see the peak.
- [ ] Run `pip install jupyter`, open `notebooks/01_z_peak.ipynb` and run all cells: the last cell prints `All checks passed`.

**Three minutes, checking that the numbers were not typed by hand.**

- [ ] Run `pip install -e ".[dev]"`, which adds the checking tools.
- [ ] Run `shasum -a 256 results/production.json`. It should print `{{ production_sha }}`.
- [ ] Run `python scripts/check_readme_numbers.py`. It should print `OK`.
- [ ] Run `python scripts/apply_production.py --check`, which regenerates every generated file and compares bytes.
- [ ] Look at the commit history: the analysis commit `{{ git_head_short }}` comes before the results, and the file list `results/production_files.json` is older than both.

**What this shows and what it does not.** It shows that the code runs, the numbers match the recorded run and the process was
pre-registered. It does not show that the physics is right: that needs an expert's review, and this is an unofficial analysis, not a CMS result.
