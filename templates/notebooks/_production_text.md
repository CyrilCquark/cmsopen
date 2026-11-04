<!-- tags: production-text -->
{{ dry_banner }}

Measured on {{ n_files }} files (controlling **benchmark**: {{ bench_n_files }} pre-registered files, {{ t4_status }}).

| {{ c.label }} | value |
|---|---|
| Model and fit range | `{{ c.model }}`, {{ c.fit_lo }}-{{ c.fit_hi }} GeV |
| Events read, pairs in the fit range | {{ c.events }}, {{ c.pairs }} |
| Peak (pole) position, observed | {{ c.peak }} GeV |
| Statistical error, raw | {{ c.stat }} GeV |
| Statistical error, scaled by S = {{ c.scale }} | {{ c.stat_scaled }} GeV |
| Resolution, observed | {{ c.res }} ± {{ c.res_err }} GeV |
| χ²/ndf **benchmark** | ≤ {{ bench_chi2 }} |
| χ²/ndf, observed | {{ c.chi2 }} / {{ c.ndf }} = {{ c.chi2_ndf }} ({{ c.t2_status }}) |
| PDG mass (reference only) | {{ c.pdg }} GeV |
| Offset from PDG, observed | {{ c.offset }} GeV |
| Fit-choice spread, observed | {{ c.spread }} GeV |
