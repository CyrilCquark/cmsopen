# Changelog

## {{ version }}

First release, built from the production run at commit `{{ git_head_short }}`.

- Reads CMS NanoAOD files (local or remote), with selections, opposite-sign pairing and invariant masses as vectorised
  layers that also work on their own.
- `cmsopen.analyze` and the `cmsopen` command line: the whole chain for the `Z_mumu` and `Jpsi_mumu` channels, with
  parallel processing that gives results identical to serial.
- Peak fits with a Breit-Wigner, Crystal Ball resolution cores and a smooth background; stability scans and pre-registered
  validation studies.
- A small committed real-data sample, three notebooks, this site, and release metadata generated from
  `results/production.json`.

Results of the release are on the [home page](index.md).
