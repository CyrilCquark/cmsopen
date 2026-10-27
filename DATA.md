# Data

Development uses one file from a CMS 2012 open data record. All details below
are taken from the [CERN Open Data Portal](https://opendata.cern.ch) record
metadata.

**The ROOT file is not in git.** Download it into `data/` (gitignored) as shown below.

## Record

| Field | Value |
|---|---|
| Record ID | [31129](https://opendata.cern.ch/record/31129) |
| Title | Run2012C_DoubleMuParked dataset in Run1 NanoAOD-like format |
| Authors | CMS Open Data group |
| Publisher | CERN Open Data Portal |
| Published | 2024 |
| Collision | pp, 8TeV (data taken in 2012) |
| Format | `nanoaod-run1`, `root` |
| Events (whole record) | 35,455,705 in 74 files |
| License | CC0-1.0 |
| DOI | None listed in the record metadata |
| OAI identifier | `oai:cernopendata.cern:31129` |
| Derived from | Record [6030](https://opendata.cern.ch/record/6030), `/DoubleMuParked/Run2012C-22Jan2013-v1/AOD`, DOI [10.7483/OPENDATA.CMS.M5AD.Y3V3](https://doi.org/10.7483/OPENDATA.CMS.M5AD.Y3V3) |
| Production software | Record [12505](https://opendata.cern.ch/record/12505) |

## File used for development

| Field | Value |
|---|---|
| Filename | `45F7AE81-7A79-4CB1-998E-7BD156490294.root` |
| Size | 1,145,602,936 bytes |
| Checksum | `adler32:9f7301c5` |
| HTTPS | https://opendata.cern.ch/eos/opendata/cms/derived-data/NanoAODRun1/01-Jul-22/Run2012C_DoubleMuParked/45F7AE81-7A79-4CB1-998E-7BD156490294.root |
| XRootD | `root://eospublic.cern.ch//eos/opendata/cms/derived-data/NanoAODRun1/01-Jul-22/Run2012C_DoubleMuParked/45F7AE81-7A79-4CB1-998E-7BD156490294.root` |

Download (resumable):

```bash
curl -fL -C - -o data/45F7AE81-7A79-4CB1-998E-7BD156490294.root \
  https://opendata.cern.ch/eos/opendata/cms/derived-data/NanoAODRun1/01-Jul-22/Run2012C_DoubleMuParked/45F7AE81-7A79-4CB1-998E-7BD156490294.root
```

## How to cite

The portal's [About CMS](https://opendata.cern.ch/docs/about-cms) page says:

> All datasets will have a unique DOI that you are requested to cite in any
> applications or publications.

Record 31129 does not list a DOI in its metadata. Its parent AOD dataset,
record 6030, does: **10.7483/OPENDATA.CMS.M5AD.Y3V3**.
