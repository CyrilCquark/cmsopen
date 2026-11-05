# User guide

{{ dry_banner }}

## Install

From a clone, with Python 3.10 or newer:

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install .            # or: pip install -e ".[dev]" to run the tests and build these docs
```

## Command line

```bash
cmsopen analyze FILE [FILE ...] --channel Z_mumu --outdir out
cmsopen analyze FILE --channel Jpsi_mumu --workers 2 --validation --outdir out
cmsopen fetch --dest data      # the development file, resumable, size and adler32 verified
```

`FILE` is a local NanoAOD file or an `https://` URL. `--model` overrides the channel's model, `--no-stability` skips
the refits over fit choices, and `--n-events` limits the events read. Run `cmsopen analyze --help` for all options.

The committed sample is small, so use `--model voigt_poly` with it: the frozen default models need far more pairs and
fail on it with a clear error.

## Python

```python
import cmsopen

result = cmsopen.analyze("file.root", channel="Z_mumu", outdir="out")
print(result.fit.table())
value, error = result.fit.peak_position
```

`analyze` returns an `AnalysisResult` with the cutflow, masses, histogram, fit, alternate fit, PDG comparison, stability
scan, figures and warnings. `result.to_dict()` is what `summary.json` holds.

On macOS, a script that uses `n_workers` needs the `if __name__ == "__main__":` guard, because worker processes
re-import it.

## Using the layers separately

Each step works on its own (see the [API reference](api.md) and `notebooks/03_modular_usage.ipynb`):

```python
from cmsopen import ZMUMU_MUON_CUTS, best_pair, fit_mass_peak, make_histogram, open_events, opposite_sign_pairs
from cmsopen.ingestion import DIMUON_TRIGGERS_2012

with open_events("file.root") as events:
    selected = events.muons(**ZMUMU_MUON_CUTS).require_trigger(*DIMUON_TRIGGERS_2012).require(2)
pairs = best_pair(opposite_sign_pairs(selected), "highest_pt_sum")
histogram = make_histogram(pairs.mass, bins=60, range=(60.0, 120.0))
fit = fit_mass_peak(histogram, model="voigt_poly", fit_range=(70.0, 110.0))
```

## Channels

`cmsopen.CHANNELS` holds the frozen configurations: `Z_mumu` and `Jpsi_mumu`. `cmsopen.register_channel` adds your own
`ChannelConfig`; the frozen ones are not changed by doing that.

## Data

The data are described in [`DATA.md`]({{ repo_url }}/blob/main/DATA.md). `data/` is gitignored and ROOT files are never
committed, apart from the small sample in `examples/data/`.
