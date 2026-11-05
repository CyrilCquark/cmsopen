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
| `docs/figures/README.md` | `8e08effcb66d10b20104d740071597ae639667918205e5272407ad61fdc55756` |
| `docs/figures/cutflow.png` | `c112b2eec1dbf6d6b02a52a82b15e18c08d82ccd0ccfd215f4f348d7245d6f1a` |
| `docs/figures/jpsi_os_vs_ss.png` | `54dfb57a2859091ee30e1992956c26ba989f341fb6c4b1d7e9fd5159b61974e1` |
| `docs/figures/jpsi_peak_fit.pdf` | `871c2dd3c7486af274e72a4b295a0c8d4d978150800c4127f1bc34c922a8c317` |
| `docs/figures/jpsi_peak_fit.png` | `e65daa79c65cbbf17ee4068f308b9d1c960c2a6cd6baf3687f88fc55522ea740` |
| `docs/figures/jpsi_peak_fit_caption.md` | `0a44603795ca95b4d8da785de5322c960c65c5a67ed97ba1d437a3db86cfde70` |
| `docs/figures/muon_eta.png` | `5c77c6fde18d48c6431de32b4e7f305ffd5e510c278090ce97cada341e9e40e9` |
| `docs/figures/muon_pt.png` | `6a0c952a4ee19c10ab8e1286d6f1349d680ab32c0dfab540aa8eab0cd3890388` |
| `docs/figures/z_os_vs_ss.png` | `b64bd1a7e02880b7ddf76c1091e46fa4929a1e32c757c4a9bfa2d228510ee31b` |
| `docs/figures/z_peak_fit.pdf` | `a680a0555799ac035e493d8d867832f6f60a9791f6420008097ccd6d097f8f6b` |
| `docs/figures/z_peak_fit.png` | `9e3dbd47b13a3bea69e5872b7795e608b4eca637fff25edde9311d35ba24d4a2` |
| `docs/figures/z_peak_fit_caption.md` | `34741c57b543bb15b0b3311be2d1a10ea8f4828e0c8a83c71a9b9ecb01788a85` |

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
