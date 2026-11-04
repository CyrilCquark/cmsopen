{{ dry_banner }}

Subject: Could you review the code of my CMS open data project?

Dear [mentor's name],

I have finished a first version of cmsopen, a Python library that reconstructs the Z and J/ψ peaks from public CMS data: {{ repo_url }}

Would you be willing to review the code and the analysis? I built it with AI coding assistance, so an expert's eye matters all the more. I'd value your view on three things in particular:

1. Whether the method holds up: the selection, the line-shape model and how I handle the offset from the PDG mass.
2. Whether the numbers are reported fairly. Against my benchmarks, the sample was {{ n_files }} of {{ bench_n_files }} files ({{ t4_status }}), and χ²/ndf against ≤ {{ bench_chi2 }} was {{ z.chi2_ndf }} for the Z ({{ z.t2_status }}) and {{ jpsi.chi2_ndf }} for the J/ψ ({{ jpsi.t2_status }}).
3. Anything in the code a physicist would do differently.

The README's quick start takes under five minutes, and `src/cmsopen/pipeline.py` is a good place to begin reading. An hour of your time would help a lot, and any part of the above would be useful if that's too much.

Thank you,
Cyril Nadar
