# Figures

Final figures of the cmsopen Z -> mu+ mu- analysis of real CMS Open Data. Unofficial analysis of CMS Open
Data: these are not CMS results.

| file | content |
|---|---|
| `z_peak_fit.png`, `z_peak_fit.pdf` | Dimuon mass spectrum with the Voigt + quadratic fit, background, signal band, PDG Z mass and pull panel. Caption: [`z_peak_fit_caption.md`](z_peak_fit_caption.md). |
| `z_os_vs_ss.png` | Opposite- vs same-sign pair masses (all candidates) for a loose selection (pT > 20 GeV, abs(eta) < 2.4, dimuon trigger, no ID or isolation), log scale: the peak is opposite-sign only. |
| `muon_pt.png` | Muon pT: every muon in the file vs the muons passing the full selection. |
| `muon_eta.png` | Muon eta: every muon vs the selected muons, with the abs(eta) = 2.4 acceptance edges. |
| `cutflow.png` | Events left after each step of the selection, with the percentage of all events. |

## Regenerate

From the repository root, with the package installed (`pip install -e ".[dev]"`):

```bash
python examples/make_figures.py --file data/45F7AE81-7A79-4CB1-998E-7BD156490294.root
```

The output is deterministic: rerunning on the same data and software gives byte-identical files.

## Data

`45F7AE81-7A79-4CB1-998E-7BD156490294.root` (1,145,602,936 bytes): Run2012C DoubleMuParked, NanoAOD Run 1, from the CERN Open Data
portal; see `DATA.md`.

## Software

Generated from commit `cf4cb35` with Python 3.12.15:

| package | version |
|---|---|
| cmsopen | 0.1.0 |
| numpy | 2.5.4 |
| awkward | 2.14.0 |
| uproot | 5.7.7 |
| scipy | 1.18.1 |
| matplotlib | 3.11.2 |
| hist | 2.12.0 |
| particle | 1.0.1 |
