# The Z boson peak from CMS open data

This notebook reconstructs the Z → μ⁺μ⁻ peak from real collisions. It runs from a fresh clone on the small sample in
`examples/data/`, with no large download. The last part reads the results of the production run.

```python
#TAGS setup
#INCLUDE _setup.py
```

## Why a peak?

A Z boson decays before it can reach a detector, but energy and momentum are conserved, so the two muons together have
the invariant mass of the Z. Muon pairs from other sources have no preferred mass and form a smooth background. A
histogram of the pair mass is therefore a peak on a smooth continuum.

## Analyse the sample

The sample holds the first events of one file of Run 2012C, with only the branches the analysis reads. It has few
pairs, so here we fit `voigt_poly`, a simpler line shape with one free width. The numbers this cell prints are a
demonstration and are not results.

```python
result = cmsopen.analyze(SAMPLE, channel="Z_mumu", model="voigt_poly", stability=False, verbose=False)
print(result.fit.table())
display(result.figures["mass_fit"])
```

```python
pdg_mass = pdg_mass_width(CHANNELS["Z_mumu"].resonance)[0]
peak, error = result.fit.peak_position
n_pairs = result.fit.n_entries
checks.check("the sample gives a fit with pairs in its range", n_pairs > 500, f"{n_pairs:,} pairs")
checks.check("the peak is within a generous window of the PDG mass", abs(peak - pdg_mass) < 1.0, f"{peak:.3f} GeV")
checks.check("the figures exist", {"mass_fit", "cutflow", "os_vs_ss"} <= set(result.figures))
```

## Only opposite-sign pairs make a peak

A neutral parent decays to one μ⁺ and one μ⁻. Same-sign pairs cannot come from a Z, so they show what the background
looks like.

```python
display(result.figures["os_vs_ss"])
```

## Optional: a whole file

If `CMSOPEN_DATA_FILE` points to a NanoAOD file, this cell runs the frozen default model on it (a minute or so per
file). Without it, the cell does nothing.

```python
data_file = os.environ.get("CMSOPEN_DATA_FILE")
if data_file:
    full = cmsopen.analyze(data_file, channel="Z_mumu", stability=False, verbose=False)
    print(full.fit.table())
    display(full.figures["mass_fit"])
else:
    print("CMSOPEN_DATA_FILE is not set: skipped")
```

## Production results

These come from the single run on the pre-registered sample, not from anything computed above. A benchmark is a requirement fixed
before the sample was opened; the observed values are what was measured.

#INCLUDE_TEXT z

The peak sits {{ z.relation }} the PDG mass. No muon momentum-scale corrections are applied, so this is not a measurement of
the Z mass. The scale factor S is the square root of χ²/ndf, floored at one.

```python
#TAGS self-check
NOTEBOOK = "01_z_peak.ipynb"
NOTEBOOK_CHANNELS = ("Z_mumu",)
NOTEBOOK_FIGURES = ("z_peak_fit.png", "z_os_vs_ss.png", "cutflow.png", "muon_pt.png", "muon_eta.png")
#INCLUDE _self_check.py
```

```python
display(Image(filename=str(FIGURES / "z_peak_fit.png"), width=720))
display(Markdown((FIGURES / "z_peak_fit_caption.md").read_text()))
```

The fit's lower panel shows the pulls, (data − fit) / σ per bin. If the model describes the shape, they show no pattern.

```python
display(Image(filename=str(FIGURES / "z_os_vs_ss.png"), width=720))
display(Image(filename=str(FIGURES / "cutflow.png"), width=720))
```

The first figure compares opposite-sign and same-sign pairs: a neutral parent can only give opposite-sign ones. The second shows how many events survive each selection step.

```python
#TAGS finish
#INCLUDE _finish.py
```
