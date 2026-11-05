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
| Events (whole record) | 35,455,705 in 74 files (73 separate files and one file that merges them) |
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

## Records of the production sample

Record-level facts from the [CERN Open Data Portal](https://opendata.cern.ch) record pages, read on 2026-11-04. The
production files are listed in `results/production_files.json`.

| Record | Run period | Title | Events | Files on the portal | Files to choose from | Parent AOD record | Parent DOI |
|---|---|---|---|---|---|---|---|
| [31129](https://opendata.cern.ch/record/31129) | Run2012C | Run2012C_DoubleMuParked dataset in Run1 NanoAOD-like format | 35,455,705 | 74 | 73 | [6030](https://opendata.cern.ch/record/6030) | [10.7483/OPENDATA.CMS.M5AD.Y3V3](https://doi.org/10.7483/OPENDATA.CMS.M5AD.Y3V3) |
| [31123](https://opendata.cern.ch/record/31123) | Run2012B | Run2012B_DoubleMuParked dataset in Run1 NanoAOD-like format | 26,084,708 | 57 | 56 | [6004](https://opendata.cern.ch/record/6004) | [10.7483/OPENDATA.CMS.YLIC.86ZZ](https://doi.org/10.7483/OPENDATA.CMS.YLIC.86ZZ) |

**File counts.** Each record holds its separate files plus one file that, in the portal's words, "contains the separate
files merged into one file". So the portal's count is one more than the count of separate files. The production sample
is chosen from the per-file index only (`results/production_files.json`, "rule"), which is why it counts 73 and 56.

Both records are released under the Creative Commons Zero v1.0 Universal licence (CC0-1.0).

## How to cite

The portal's [About CMS](https://opendata.cern.ch/docs/about-cms) page says:

> All datasets will have a unique DOI that you are requested to cite in any
> applications or publications.

Record 31129 does not list a DOI in its metadata. Its parent AOD dataset,
record 6030, does: **10.7483/OPENDATA.CMS.M5AD.Y3V3**.

Records 31129 and 31123 list no DOI of their own, so cite their parent AOD datasets. The portal's "Cite as" text for each:

- Record 6030 (parent of 31129): CMS collaboration (2017). DoubleMuParked primary dataset in AOD format from Run of 2012
  (/DoubleMuParked/Run2012C-22Jan2013-v1/AOD). CERN Open Data Portal. DOI: 10.7483/OPENDATA.CMS.M5AD.Y3V3
- Record 6004 (parent of 31123): CMS collaboration (2017). DoubleMuParked primary dataset in AOD format from Run of 2012
  (/DoubleMuParked/Run2012B-22Jan2013-v1/AOD). CERN Open Data Portal. DOI: 10.7483/OPENDATA.CMS.YLIC.86ZZ
