# Reproducibility

## What ran

| item | value |
|---|---|
| analysis commit | `9ebc2e3a8b379341df8c2e4920e22448e95f27e0` |
| first attempt at commit | `9ebc2e3a8b379341df8c2e4920e22448e95f27e0` |
| model freeze commit | `35af6445db8d601972e60d3ba03f7c19a99527bb` |
| attempts | 2 (1 failed or interrupted, 0 code fixes) |
| sample | 20 files, 29,987,393,486 bytes |
| gates at that commit | 494 passed, 2 skipped in 1807.17s (0:30:07) |

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
| `results/production.json` | `12effe765b3a7fbacfb901d41cc7f2cdca0f32ad5ed079f51d1b0399124da2ec` |
| `results/production_files.json` | `0b26c081b9bc7f951c03d1af9a7735bcd0beb55a2bd69d91132a563101f085a7` |
| analysis configuration | `10247c26cb18e3e3b8288e63a259b5437b18d3c20621dec253ec457cfb81e9d1` |
| `docs/figures/README.md` | `9cd60bdec12e03f0e1ddc23516724f7f74322edb7d0870b1788499d0e1f102f8` |
| `docs/figures/cutflow.png` | `6b7a7ce666ffeff74932eed351c5fb7a046b2f5900e4bba203fe47cac0bf1b17` |
| `docs/figures/jpsi_os_vs_ss.png` | `4df1944cf981561b7c151292225fc88dd194600c200a134b1f4860df4dc46adf` |
| `docs/figures/jpsi_peak_fit.pdf` | `73ca32434f00f0c4129643b39bdaed2990c6033f3a027b112fd84f5541b97990` |
| `docs/figures/jpsi_peak_fit.png` | `db0545f0b460bc05be9f084dc70baacd11e054253803de28ee170351f2607313` |
| `docs/figures/jpsi_peak_fit_caption.md` | `63ca8f562b6bea786dd1131c63c32b8f9d8c90800986aeec5c4df2a619b62a34` |
| `docs/figures/muon_eta.png` | `a407e0ce83228f8e03d8eb5601028d8a2580f482b628a5f64e31a6267bd55994` |
| `docs/figures/muon_pt.png` | `b9bbd02bedbf28cc516ab3f987fcb974456ca3d189a8b4dca3cd28959e15b89b` |
| `docs/figures/z_os_vs_ss.png` | `9f48f57b6ac0706873aa64e47b170e774b81e97e7ceb04d77efb00450b27da90` |
| `docs/figures/z_peak_fit.pdf` | `31bd625e67b3a68f11cd7718bd35d21ecf4a186bc2bf76f585fd00cdeba71374` |
| `docs/figures/z_peak_fit.png` | `cdcb6e9f7887e1c8106ec125776b5fad098442e2d1a6e8032390ef84e7d39e2d` |
| `docs/figures/z_peak_fit_caption.md` | `2403eadaf8a7c9c32338ec4725d5120cbceb168aa351b1e9c1684192c3eb75ab` |

If `results/figures_rerender.json` exists, the figures were rendered again after the run, for layout and captions only,
by `scripts/rerender_production_figures.py`. That script reruns the analysis on the same files and writes nothing unless
every number equals `results/production.json`; the file records the commit, the check and the figure hashes.

## Run the analysis again

This needs the 29.99 GB of registered files and several hours, mostly the download. The commit that ran the
analysis has no results yet, so the production command runs there:

```bash
git clone https://github.com/CyrilCquark/cmsopen.git && cd cmsopen
git checkout 9ebc2e3a8b379341df8c2e4920e22448e95f27e0
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

Python 3.12.15 (CPython) on macOS-14.6.1-arm64-arm-64bit, environment SHA-256 `e45a4f9253192d3fffad1c14e0fcf6ac8dc8a0162fab0c9512cf90f6fe24e174`.

| package | version |
|---|---|
| awkward | 2.14.0 |
| cmsopen | 0.1.0 |
| hist | 2.12.0 |
| matplotlib | 3.11.2 |
| numpy | 2.5.4 |
| particle | 1.0.1 |
| scipy | 1.18.1 |
| uproot | 5.7.7 |
| vector | 1.9.0 |

## Files of the sample

By index; the names are in the registry.

| index | record | period | bytes | checksum |
|---|---|---|---|---|
| 3 | 31129 | Run2012C | 1,439,650,504 | `adler32:e5781397` |
| 9 | 31129 | Run2012C | 1,520,772,810 | `adler32:eec8aa1c` |
| 15 | 31129 | Run2012C | 1,542,846,675 | `adler32:cbabfaaf` |
| 21 | 31129 | Run2012C | 1,527,963,949 | `adler32:8f659920` |
| 27 | 31129 | Run2012C | 1,447,828,594 | `adler32:95193a2b` |
| 33 | 31129 | Run2012C | 1,475,659,824 | `adler32:d24d9ad0` |
| 40 | 31129 | Run2012C | 1,621,487,495 | `adler32:f447a199` |
| 46 | 31129 | Run2012C | 1,579,025,847 | `adler32:665f82cd` |
| 52 | 31129 | Run2012C | 1,560,210,288 | `adler32:39414ab4` |
| 58 | 31129 | Run2012C | 1,433,884,722 | `adler32:76cccbff` |
| 64 | 31129 | Run2012C | 1,566,976,743 | `adler32:64a74d3c` |
| 70 | 31129 | Run2012C | 1,562,551,541 | `adler32:53cfbfbc` |
| 4 | 31123 | Run2012B | 1,407,566,465 | `adler32:2fecef4d` |
| 11 | 31123 | Run2012B | 1,435,872,658 | `adler32:c25d58f3` |
| 18 | 31123 | Run2012B | 1,341,461,164 | `adler32:f11f4450` |
| 25 | 31123 | Run2012B | 1,515,001,789 | `adler32:d558c670` |
| 32 | 31123 | Run2012B | 1,481,290,146 | `adler32:7a119772` |
| 39 | 31123 | Run2012B | 1,573,571,686 | `adler32:eb9da552` |
| 46 | 31123 | Run2012B | 1,450,105,457 | `adler32:58cd5a83` |
| 53 | 31123 | Run2012B | 1,503,665,129 | `adler32:f9d38c09` |
