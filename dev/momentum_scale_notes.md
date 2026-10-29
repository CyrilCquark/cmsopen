# Muon momentum scale and resolution corrections for 2012 (Run 1): notes

Research notes only (Layer 6b, prompt 6, Phase E). Nothing here is
implemented in `src/`, and nothing here changes the analysis. Sources were
read on 2026-10-28; claims not confirmed by a source are marked
"unverified".

## Why it matters here

- CMS reconstructs a muon's momentum from its track curvature,
  kappa = q / pT. Two kinds of bias are expected in data that have not been
  corrected:
  - a multiplicative scale error (for example from the magnetic-field map,
    the integral of B dl), the same for both charges;
  - an additive curvature bias from tracker misalignment (twists,
    sagitta-like distortions), opposite for mu+ and mu-, and depending on
    phi and eta.
- The development-file validation (dev/benchmarks.md, 2026-10-28) shows
  both signatures as measured observations. The Z pole is 0.31 GeV below
  the PDG mass. The mu+ minus mu- peak difference changes sign around phi:
  -0.16, +0.21, +0.23 and -0.29 GeV in the four phi quarters, each with an
  error of about 0.06-0.07 GeV. This is the pattern an additive,
  phi-dependent curvature bias produces. The weighted mean over the bins is
  consistent with zero.

## What exists for 2012 data

1. **Rochester corrections** (Bodek et al., "Extracting muon momentum scale
   corrections for hadron collider experiments", Eur. Phys. J. C 72 (2012)
   2194, arXiv:1208.3710).
   - Two steps on Z -> mu mu events. Step 1 corrects each muon in bins of
     charge, eta and phi (e.g. 8 x 8 in eta x phi per charge), using the
     mean 1/pT compared with a "perfectly aligned" reference. It separates
     a multiplicative part (field) from an additive part (alignment).
   - Step 2 tunes the per-bin corrections so the Z mass is the same in
     every bin.
   - The reference is generator-level simulation smeared with a
     parameterised resolution. Reconstructed simulation gets extra pT
     smearing to match the data's Z width.
   - Data and simulation get separate corrections.
2. **The CMS Open Data MuonCorrectionsTool**
   (https://github.com/cms-legacydata-analyses/MuonCorrectionsTool,
   described in the CMS Open Data guide,
   https://cms-opendata-guide.web.cern.ch/analysis/selection/objects/muons).
   - It packages the Muon POG's Run 1 Rochester code (`rochcor2012wasym.cc`
     and `.h`, `muresolution.cc`) as ROOT macros. It needs ROOT, not CMSSW.
   - Its example reads a flat NanoAOD-like tree (`nMuon`, `Muon_pt`,
     `Muon_eta`, `Muon_phi`, `Muon_mass`, `Muon_charge`). It corrects 2012
     data, "Run2012BC_DoubleMuParked_Muons" (record 12341, derived from
     `/DoubleMuParked/Run2012B,C-22Jan2013-v1/AOD`), and an MC sample.
   - The guide says the 2012 dataset is the documented example and that
     data and MC need different corrections. The data correction takes a
     run option; the MC correction takes a track-count parameter.
   - No license is shown on the repository page (unverified whether one
     exists in the files).
3. **CMS performance papers.**
   - The 7 TeV muon performance paper (arXiv:1206.4071) shows the Z peak
     position versus muon phi with sinusoidal fits (MuScleFit). This is
     the standard pT-curvature bias study.
   - CMS proceedings for 8 TeV quote the average momentum-scale bias as
     measured to better than 0.2 % and consistent with zero. They give a
     relative pT resolution of 1.3-2.0 % in the barrel and better than 6 %
     in the endcaps (after the collaboration's calibration; whether the
     open-data reconstruction carries it is unverified).
4. **An open-data example of a simpler approach.** An 8 TeV Standard Model
   cross-section study with CMS open data (arXiv:1907.08197) fits a scale
   alpha and a resolution beta for muons in three eta regions (two endcaps
   and the barrel) by comparing Z mass spectra in data and simulation. It
   finds alpha ~ 0.998 and beta ~ 1.13 on average.
5. **KaMuCa (Kalman-filter muon calibration).** I found no source
   confirming a Run 1 (2012) KaMuCa calibration, so its applicability here
   is unverified. A 2020 talk on CMS muon calibration
   (indico.sns.it, PRIN slides) describes the same structure: a
   multiplicative and an additive correction to the curvature, fitted on
   dimuon resonances.

## Does it apply to this open data?

- Our files (record 31129, NanoAODRun1 01-Jul-22) are derived from
  `/DoubleMuParked/Run2012C-22Jan2013-v1/AOD`. The tool's example is
  derived from the same 22Jan2013 reprocessing. The Rochester 2012 tables
  are therefore the natural candidate: they were derived for that
  reconstruction (a strong expectation, unverified in the tool's
  documentation, which names no reprocessing).
- Neither record says whether any correction is already applied to
  `Muon_pt`. The measured phi-dependent mu+ minus mu- pattern suggests
  not; this should be confirmed with the NanoAODRun1 producer code
  (record 12505) before anything is applied.

## What applying a correction would take

1. Get the Rochester 2012 code and tables from the MuonCorrectionsTool,
   check their license, and pin a version (commit hash).
2. Either call the ROOT macros through PyROOT or a compiled helper (a new,
   heavy dependency), or port the lookup (per-charge eta x phi tables and
   the step 2 factors) to vectorised numpy/awkward. The port must be
   validated against the original code, muon by muon, on a sample.
3. Apply it to data before the selection, because the pT cuts must use
   corrected momenta, and record the correction version in summary.json.
4. Reproduce the tool's documented validation plot (dimuon mass) and our
   own validation (phi, eta, charge bins). The mu+ minus mu- pattern should
   flatten.
5. Decide, before looking at production data, whether the correction is
   part of the analysis. If it is, the default models and the model-choice
   rule must be re-run on the corrected development file under a new
   amendment.

## Risks

- **Wrong tables.** Tables for a different reprocessing or year, or the MC
  tables applied to data, would bias rather than correct.
- **Simulation.** Rochester's resolution and smearing parts are defined for
  simulation. We have no simulation, so only the data-scale part applies,
  and the resolution model stays as fitted.
- **Circularity.** The step 2 corrections force the Z mass to be the same
  in every bin, tuned to the Z peak. After correction the Z peak position
  is no longer an independent measurement of the momentum scale. Our
  "offset from PDG" would then partly measure the correction. The J/psi
  becomes the independent check.
- **Dependencies and a moving baseline.** A PyROOT or C++ dependency, or a
  port with its own bugs. Any correction changes every number that the
  pre-registered plans were developed with.
- **Statistics.** Deriving our own per-bin corrections from one file is not
  possible: the per-bin statistical errors (about 0.04-0.07 GeV on the
  development file) are comparable to the effects.

## Sources

- Bodek et al., Eur. Phys. J. C 72 (2012) 2194: https://arxiv.org/abs/1208.3710
  (HTML: https://ar5iv.arxiv.org/html/1208.3710)
- CMS Open Data guide, muons: https://cms-opendata-guide.web.cern.ch/analysis/selection/objects/muons
- MuonCorrectionsTool: https://github.com/cms-legacydata-analyses/MuonCorrectionsTool
- Example dataset for the tool, record 12341: https://opendata.cern.ch/record/12341
- Development-file record 31129: https://opendata.cern.ch/record/31129
- CMS muon performance at 7 TeV: https://arxiv.org/pdf/1206.4071
- 8 TeV open-data cross sections (alpha, beta scale/resolution): https://arxiv.org/pdf/1907.08197
- CMS muon calibration talk (PRIN): https://indico.sns.it/event/18/contributions/132/attachments/79/171/PRIN_7Feb_Elisabetta.pdf
- CMS 8 TeV muon performance proceedings: https://pos.sissa.it/180/124/pdf
