# Using cmsopen one layer at a time

`cmsopen.analyze` runs the whole chain. Each step is also usable by itself, so you can change one and keep the rest. This
notebook walks through them on the committed sample, using the `Z_mumu` channel's frozen configuration.

```python
#TAGS setup
#INCLUDE _setup.py
```

## Read events and select muons

`open_events` opens a file lazily. `events.muons(...)` builds muons with cuts, and `require_trigger` and `require` act on whole events.

```python
import awkward as ak
import numpy as np

from cmsopen import (
    ZMUMU_MUON_CUTS,
    best_pair,
    fit_mass_peak,
    make_histogram,
    open_events,
    opposite_sign_pairs,
    plot_mass_spectrum,
    same_sign_pairs,
)
from cmsopen.ingestion import DIMUON_TRIGGERS_2012

with open_events(SAMPLE) as events:
    print(events.summary())
    selected = events.muons(**ZMUMU_MUON_CUTS).require_trigger(*DIMUON_TRIGGERS_2012).require(2)
print(selected)
```

## Form pairs and compute masses

An event can hold more than two selected muons. `best_pair` keeps one opposite-sign pair per event with a rule that does not use
the mass, so the choice cannot sculpt a peak.

```python
opposite = opposite_sign_pairs(selected)
same = same_sign_pairs(selected)
best = best_pair(opposite, "highest_pt_sum")
masses = ak.to_numpy(ak.flatten(best.mass))
print(f"{best.n_pairs:,} opposite-sign pairs, one per event")
checks.check("at most one pair per event", best.n_pairs <= selected.n_events, f"{selected.n_events:,} events")
```

## Histogram and fit

The channel's configuration holds the frozen histogram and fit range. The model name is yours to choose. The numbers printed here are a
demonstration on the sample and are not results.

```python
config = CHANNELS["Z_mumu"]
histogram = make_histogram(masses, bins=config.bins, range=config.mass_range)
fit = fit_mass_peak(histogram, model="voigt_poly", fit_range=config.fit_range)
print(fit.table())
figure, *_ = plot_mass_spectrum(histogram, fit)
display(figure)
```

## The same fit through the pipeline

`analyze` is these steps with chunking, parallel workers, an alternate fit, and summaries. On this sample both routes must find the same pairs.

```python
result = cmsopen.analyze(SAMPLE, channel="Z_mumu", model="voigt_poly", stability=False, verbose=False)
same_masses = np.array_equal(np.sort(masses), np.sort(result.masses))
checks.check("the layers and the pipeline find the same masses", same_masses, f"{len(masses):,} masses")
checks.check("the layers and the pipeline give the same peak",
             abs(fit.peak_position[0] - result.fit.peak_position[0]) < 1e-6)
pdg_mass = pdg_mass_width(config.resonance)[0]
checks.check("the peak is within a generous window of the PDG mass", abs(fit.peak_position[0] - pdg_mass) < 1.0)
```

## Optional: your own file

If `CMSOPEN_DATA_FILE` points to a NanoAOD file, this reads its first events through the same layers.

```python
data_file = os.environ.get("CMSOPEN_DATA_FILE")
if data_file:
    with open_events(data_file) as events:
        print(events.summary())
else:
    print("CMSOPEN_DATA_FILE is not set: skipped")
```

## Production results

The same layers, run by `cmsopen.analyze` with the frozen models over the pre-registered sample, gave the values below. Benchmarks are requirements fixed before
the sample was opened; observed values are what was measured.

#INCLUDE_TEXT z

#INCLUDE_TEXT jpsi

Neither peak position is a mass measurement, because no momentum-scale corrections are applied.

```python
#TAGS self-check
NOTEBOOK = "03_modular_usage.ipynb"
NOTEBOOK_CHANNELS = ("Z_mumu", "Jpsi_mumu")
NOTEBOOK_FIGURES = ("z_peak_fit.png", "jpsi_peak_fit.png")
#INCLUDE _self_check.py
```

```python
display(Image(filename=str(FIGURES / "z_peak_fit.png"), width=720))
display(Image(filename=str(FIGURES / "jpsi_peak_fit.png"), width=720))
display(Markdown((FIGURES / "jpsi_peak_fit_caption.md").read_text()))
```

Those are the figures of the two headline fits. Their caption files in `docs/figures/`, one shown here, list every fitted parameter.

```python
#TAGS finish
#INCLUDE _finish.py
```
