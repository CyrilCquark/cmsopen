# Figures

Final figures of the cmsopen Z -> mu+ mu- and J/psi -> mu+ mu- analysis of real CMS Open Data. Unofficial analysis of CMS Open
Data: these are not CMS results.

| file | content |
|---|---|
| `z_peak_fit.png`, `z_peak_fit.pdf` | Dimuon mass spectrum with the fit (model `cb2_bw_exp`), background, signal band, PDG Z mass and pull panel. Caption: [`z_peak_fit_caption.md`](z_peak_fit_caption.md). |
| `z_os_vs_ss.png` | Opposite- vs same-sign pair masses (all candidates) for a loose selection (pT > 20 GeV, abs(eta) < 2.4, dimuon trigger, no ID or isolation), log scale: the peak is opposite-sign only. |
| `muon_pt.png` | Muon pT: every muon in the file vs the muons passing the full selection (Z selection). |
| `muon_eta.png` | Muon eta: every muon vs the selected muons, with the abs(eta) = 2.4 acceptance edges (Z selection). |
| `cutflow.png` | Events left after each step of the selection, with the percentage of all events (Z selection). |
| `jpsi_peak_fit.png`, `jpsi_peak_fit.pdf` | J/psi dimuon mass spectrum with the fit (model `cb2_bw_poly2`), background, signal band, PDG J/psi mass and pull panel. Caption: [`jpsi_peak_fit_caption.md`](jpsi_peak_fit_caption.md). |
| `jpsi_os_vs_ss.png` | Opposite- vs same-sign pair masses after the full J/psi selection: the peak is opposite-sign only. |

## Regenerate

From the repository root, with the package installed (`pip install -e ".[dev]"`):

```bash
python scripts/production_run.py --confirm-single-production-run   # once; dev/production_runbook.md
```

The output is deterministic: rerunning on the same data and software gives byte-identical files.

## Data

20 files of the pre-registered production sample (2012B+2012C DoubleMuParked, sqrt(s) = 8 TeV), 29,987,393,486 bytes in all,
analysed in registry order; their names, sizes and checksums are in `results/production_files.json`.

## Software

Generated from commit `9ebc2e3` with Python 3.12.15:

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
