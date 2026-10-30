# cmsopen_sample.root

A small sample of real CMS collision data for readers without the 1.1 GB
development file, written by `python scripts/make_skim.py`.

| | |
|---|---|
| source record | CERN Open Data record 31129 (Run2012C DoubleMuParked, NanoAOD Run 1) |
| source file | `45F7AE81-7A79-4CB1-998E-7BD156490294.root` (the original development file; see DATA.md) |
| source URL | https://opendata.cern.ch/eos/opendata/cms/derived-data/NanoAODRun1/01-Jul-22/Run2012C_DoubleMuParked/45F7AE81-7A79-4CB1-998E-7BD156490294.root |
| events | the first 47,229 events of the source file (entries 0 to 47,228) |
| event-count rule | the largest N whose file is under 8,000,000 bytes (mass-blind: only the size is used) |
| branches | run, luminosityBlock, event, HLT_Mu17_Mu8, HLT_Mu17_TkMu8, HLT_Dimuon8_Jpsi, HLT_Dimuon10_Jpsi, PV_npvsGood, nMuon and Muon_{pt, eta, phi, mass, charge, pfRelIso04_all, pfRelIso03_all, looseId, mediumId, tightId, softId, isGlobal, isTracker, isPFcand, dxy, dz} |
| size | 7,999,790 bytes |
| adler32 | 08b9d77d |
| SHA-256 | 9e4114cc51be4186cdb54cd944fe17f0d55b5f91be5f19327e991b6516b872dd |

Licence: CMS open data are released under the Creative Commons CC0 waiver
(https://creativecommons.org/publicdomain/zero/1.0/). Citation: see DATA.md.

Regenerating the sample from the source file gives the same arrays (the
test `tests/test_sample.py` checks this when the source file is present);
the file's bytes can differ in ROOT metadata such as the creation time, so
the checksums above identify this committed copy.
