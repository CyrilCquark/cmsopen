# cmsopen: reconstructing particles from public CMS collision data

{{ dry_banner }}

**Cyril Nadar** · [{{ repo_url }}]({{ repo_url }})

**What it is.** An open-source Python library that takes real proton-proton collision data from the CERN Open Data
Portal and reconstructs the Z boson and J/ψ meson as peaks in the invariant mass of muon pairs. The whole chain is covered: reading
files, selecting muons, pairing them, computing masses, fitting the peak and validating the result.

**How it was done.** All analysis choices were fixed on development data, and the production files were chosen by a
recorded rule before any of them was opened. The analysis ran once. Results are reported as they came out, including any benchmark that was missed, and generated from one
results file, so the numbers on this page can be checked against the repository.

| metric | **benchmark** | observed | status |
|---|---|---|---|
| Sample size | **{{ bench_n_files }} files** | {{ n_files }} files | {{ t4_status }} |
| Fit adequacy χ²/ndf, Z | **≤ {{ bench_chi2 }}** | {{ z.chi2_ndf }} | {{ z.t2_status }} |
| Fit adequacy χ²/ndf, J/ψ | **≤ {{ bench_chi2 }}** | {{ jpsi.chi2_ndf }} | {{ jpsi.t2_status }} |
| Repeat run identical byte for byte | **every channel** | {{ t1_observed }} | {{ t1_status }} |
| Tests, types, coverage | **{{ t7_benchmark }}** | {{ t7_observed }} | {{ t7_status }} |

**Observed peaks.** Z: {{ z.peak }} ± {{ z.stat }} (stat.) GeV, from {{ z.pairs }} muon pairs. J/ψ: {{ jpsi.peak }} ± {{ jpsi.stat }} (stat.)
GeV, from {{ jpsi.pairs }} pairs. These are not mass measurements: no momentum-scale corrections are applied, and the
offsets from the PDG masses are reported and studied.

Unofficial analysis of CMS Open Data, not a CMS result. It was built with AI coding assistance (Claude Code) under my direction.
