# cmsopen

{{ dry_banner }}

**From public CMS collision data to the Z and J/ψ mass peaks, in one Python library.**

`cmsopen` reads NanoAOD files from the [CERN Open Data Portal](https://opendata.cern.ch), selects muons, pairs them,
computes each pair's invariant mass, fits the resonance peak and reports the fit with its uncertainties and
validation studies. This is an independent, unofficial analysis of CMS Open Data; nothing here is a CMS result.

## The physics in two minutes

**Invariant mass.** A particle's energy and momentum depend on who is measuring them, but one combination does not:
its mass. In the units particle physicists use, where the speed of light is one,

```text
m² = E² − |p|²
```

Now take a particle that decays to two muons. Energy and momentum are conserved, so the two muons together carry
exactly the parent's energy and momentum. Apply the same formula to the pair,

```text
m(μμ)² = (E₁ + E₂)² − |p₁ + p₂|²
```

and the answer is the mass of the parent, even though the parent itself lived too briefly to reach any detector. Two
measured tracks tell you the mass of something nobody saw.

**Why a peak appears.** Most muon pairs in a collision have no common parent, or come from processes with no preferred
mass, so their invariant masses form a smooth, falling continuum. Pairs from a real particle all land near that
particle's mass. Histogram every pair and the particle shows up as a bump on a smooth background: a *resonance peak*.
The neutral Z boson (PDG mass {{ z.pdg }} GeV) and the J/ψ meson (PDG mass {{ jpsi.pdg }} GeV) both decay to one μ⁺ and
one μ⁻, which is why the analysis keeps opposite-sign pairs.

**Why the peak has a width and a shape.** Three effects set its shape. A short-lived particle has no perfectly sharp
mass: this *natural width* is a Breit-Wigner curve, large for the Z and tiny for the J/ψ. The detector measures each
momentum imperfectly, which smears the mass by the *resolution*. And a muon can radiate a photon the pair does not
include, which moves some pairs to lower mass and creates a tail on the low side of the peak. The fit models all three
on top of a smooth background.

[More physics background](docs/physics.md).

## Quick start (under five minutes, no large download)

The repository includes a small sample of real collisions, `examples/data/cmsopen_sample.root`. With Python 3.10 or
newer:

```bash
git clone {{ repo_url }}.git
cd cmsopen
python3.12 -m venv .venv && source .venv/bin/activate
pip install .
```

Then three commands:

```bash
cmsopen analyze examples/data/cmsopen_sample.root --channel Z_mumu --model voigt_poly --no-stability --outdir out/z
cmsopen analyze examples/data/cmsopen_sample.root --channel Jpsi_mumu --model voigt_poly --no-stability --outdir out/jpsi
python examples/layer9_sample_demo.py
```

The first two print a fit summary and write `mass_fit.png`, `cutflow.png`, `os_vs_ss.png`, `summary.txt` and
`summary.json` to `out/`. The third runs the whole chain again with self-checks and ends with `All checks passed`.
The sample is small, so its numbers are a demonstration and are not the results below, and it uses the simpler
`voigt_poly` line shape, because the frozen production models need far more pairs to pin down their parameters.

Worked notebooks: [Z peak](notebooks/01_z_peak.ipynb), [J/ψ peak](notebooks/02_jpsi_peak.ipynb),
[using each module on its own](notebooks/03_modular_usage.ipynb). To run them, `pip install jupyter` first.

## Production results

<!-- RESULTS:BEGIN -->
{{ results_block }}
<!-- RESULTS:END -->

{{ not_met_sentence }}

## Figures

![Z peak fit](docs/figures/z_peak_fit.png)

*The dimuon mass spectrum around the Z with the fit and pulls.* [Caption with every fit parameter](docs/figures/z_peak_fit_caption.md).

![J/psi peak fit](docs/figures/jpsi_peak_fit.png)

*The same around the J/ψ.* [Caption](docs/figures/jpsi_peak_fit_caption.md).

![Opposite-sign versus same-sign pairs](docs/figures/z_os_vs_ss.png)

*Opposite-sign and same-sign pairs for a loose selection: the peak appears only in opposite-sign pairs, as expected
from a neutral parent.* The [figures directory](docs/figures/README.md) also has the cutflow and the muon pT and η
distributions, and PDF versions.

## Method

{{ method_table }}

For each event the analysis requires a channel trigger, applies the muon cuts, keeps events with at least two selected
muons and takes one opposite-sign pair: the one with the highest pT sum, a rule that does not look at the mass. All
analysis choices were fixed on development data and frozen at commit `{{ freeze_short }}`, and the files of the
production sample were chosen by a recorded rule before any of them was opened
([registry](results/production_files.json)). The code is vectorised and processes files in chunks, and results do not
depend on the chunk size or the number of workers.

## Validation and systematics

Observed values on the production sample. Each row is a spread of the fitted peak under a change of analysis choice; these
are studies of the offset, and no systematic uncertainty is combined into the quoted errors.

{{ systematics_table }}

Run-period consistency (Run 2012B minus Run 2012C, observed):

{{ periods_table }}

### Every benchmark in the registry

{{ registry_table }}

Coverage, validation pairs, J/ψ pairs and J/ψ sideband S/B were raised to this run's own observed values after the run, under the all-time-highest benchmark policy (`dev/targets.md` lists the old values). For those four, "met" here is true by construction; each was above its earlier benchmark.

{{ registry_not_met }}

Every category, charge, pT, pileup and working-point entry is listed under
[validation and systematics](docs/validation.md).

## Reproducibility

The analysis ran once, at commit `{{ git_head }}`, in {{ n_attempts }} attempt(s). To verify what is committed (about a
minute after the install, no data download):

```bash
pip install -e ".[dev]"
shasum -a 256 results/production.json results/production_files.json
python scripts/production_schema.py
python scripts/check_readme_numbers.py
python scripts/check_blinding.py
python scripts/apply_production.py --check
python scripts/production_report.py
```

| item | SHA-256 |
|---|---|
| `results/production.json` | `{{ production_sha }}` |
| `results/production_files.json` (the registry) | `{{ registry_sha }}` |
| analysis configuration | `{{ config_sha }}` |
| software environment | `{{ env_sha }}` |

Environment: Python {{ python }} on {{ platform }}. {{ packages_inline }}

Re-running the analysis itself needs the registered files ({{ total_gb }} GB) and is described in
[reproducibility](docs/reproducibility.md), with the checksums of every figure.

## Data and citation

{{ data_section }}

To cite the software use [`CITATION.cff`](CITATION.cff). CMS open data are released under the CC0 waiver. The portal
asks for the dataset DOI to be cited:

> {{ data_citation_quote }}

{{ data_citation_note }}

## Limitations

{{ limitations }}

## Licence

MIT, see [LICENSE](LICENSE). The sample in `examples/data/` is CMS open data under CC0 ([details](examples/data/SAMPLE.md)).
