# The J/ψ peak from CMS open data

The J/ψ is a bound state of a charm quark and its antiquark, far lighter than the Z. Its natural width is so small that the
width of its peak comes almost entirely from the detector, which makes it a direct view of the muon momentum resolution.

```python
#TAGS setup
#INCLUDE _setup.py
```

## Analyse the sample

The J/ψ channel has its own trigger and softer muon cuts, because its muons have much lower momentum than those from a
Z. The sample is small, so we fit `voigt_poly` here; the numbers below are a demonstration and are not results.

```python
config = CHANNELS["Jpsi_mumu"]
print(config.description)
result = cmsopen.analyze(SAMPLE, channel="Jpsi_mumu", model="voigt_poly", stability=False, verbose=False)
print(result.fit.table())
display(result.figures["mass_fit"])
```

```python
pdg_mass = pdg_mass_width(config.resonance)[0]
peak, error = result.fit.peak_position
checks.check("the sample gives a fit with pairs in its range", result.fit.n_entries > 500, f"{result.fit.n_entries:,} pairs")
checks.check("the peak is within a generous window of the PDG mass", abs(peak - pdg_mass) < 0.02, f"{peak:.4f} GeV")
```

## What the frozen model does on so few pairs

The production model has two resolution cores, and the sample may not have enough pairs to determine the second one.
The library either fits it or fails with a clear `AnalysisError`, and it does not return a fit it cannot trust.

```python
try:
    frozen = cmsopen.analyze(SAMPLE, channel="Jpsi_mumu", stability=False, verbose=False)
    outcome, ok = f"fitted: {frozen.fit.model_name}", frozen.fit.model_name == config.model
except cmsopen.AnalysisError as exc:
    outcome, ok = f"AnalysisError: {str(exc)[:110]}", "fit failed" in str(exc)
print(outcome)
checks.check("the frozen default fits or fails with the documented AnalysisError", ok)
```

## Optional: a whole file

If `CMSOPEN_DATA_FILE` points to a NanoAOD file, this cell runs the frozen default model on it.

```python
data_file = os.environ.get("CMSOPEN_DATA_FILE")
if data_file:
    full = cmsopen.analyze(data_file, channel="Jpsi_mumu", stability=False, verbose=False)
    print(full.fit.table())
    display(full.figures["mass_fit"])
else:
    print("CMSOPEN_DATA_FILE is not set: skipped")
```

## Production results

These come from the single run on the pre-registered sample. A benchmark is a requirement fixed before the sample was opened; the
observed values are what was measured.

#INCLUDE_TEXT jpsi

This peak lies {{ jpsi.relation }} the PDG mass. No momentum-scale corrections are applied, so this is not a measurement of the
J/ψ mass. Compare the statistical error, raw and scaled: when χ²/ndf is above one, the scaled error is the more honest of the two.

```python
#TAGS self-check
NOTEBOOK = "02_jpsi_peak.ipynb"
NOTEBOOK_CHANNELS = ("Jpsi_mumu",)
NOTEBOOK_FIGURES = ("jpsi_peak_fit.png", "jpsi_os_vs_ss.png")
#INCLUDE _self_check.py
```

```python
display(Image(filename=str(FIGURES / "jpsi_peak_fit.png"), width=720))
display(Markdown((FIGURES / "jpsi_peak_fit_caption.md").read_text()))
display(Image(filename=str(FIGURES / "jpsi_os_vs_ss.png"), width=720))
```

The lower panel of the fit shows the pulls. A pattern in them would show where the line shape falls short; read it together with
the χ²/ndf above.

```python
#TAGS finish
#INCLUDE _finish.py
```
