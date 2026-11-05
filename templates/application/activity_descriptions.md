# Activity descriptions

{{ dry_banner }}

## Long version (about one hundred and fifty words)

I built cmsopen, an open-source Python library that reconstructs particles from real CERN collision data. It reads public CMS files,
selects muons, pairs them, computes their invariant mass and fits the resulting Z boson and J/ψ peaks. I treated it like a real
analysis: every choice was fixed on development data, the production files were chosen by a recorded rule before being
opened, and the analysis ran once. Benchmarks and observed values are reported side by side. For sample size the benchmark was {{ bench_n_files }} files and I
analysed {{ n_files }} ({{ t4_status }}). For fit quality the benchmark was χ²/ndf ≤ {{ bench_chi2 }}; I observed {{ z.chi2_ndf }} for the Z ({{ z.t2_status }}) and {{ jpsi.chi2_ndf }} for
the J/ψ ({{ jpsi.t2_status }}). Anyone can re-check the numbers against the repository, and a missed benchmark stays reported as
missed. It was built with AI coding assistance (Claude Code) under my direction. It is an unofficial analysis, not a CMS result.

## Short version (about fifty words)

I built cmsopen, an open-source Python library that reconstructs the Z and J/ψ from public CERN data, built with AI coding assistance (Claude Code) under my direction. Benchmarks against observed: sample {{ bench_n_files }} files, {{ n_files }} analysed ({{ t4_status }}); χ²/ndf ≤ {{ bench_chi2 }}, observed {{ z.chi2_ndf }} for the Z ({{ z.t2_status }}) and {{ jpsi.chi2_ndf }} for the J/ψ ({{ jpsi.t2_status }}).

## One line

cmsopen: my open-source Python library reconstructing the Z and J/ψ from CERN open data, built with AI coding assistance (Claude Code) under my direction (χ²/ndf benchmark ≤ {{ bench_chi2 }}; observed Z {{ z.chi2_ndf }}, {{ z.t2_status }}; J/ψ {{ jpsi.chi2_ndf }}, {{ jpsi.t2_status }}).
