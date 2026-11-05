# z_peak_fit

Invariant mass of the two muons of one opposite-sign pair per event (the pair with the highest
pT sum), after the Z -> mu+ mu- selection, in 1 GeV bins (2012B+2012C DoubleMuParked, sqrt(s) = 8 TeV), with a fit of
a Breit-Wigner of the Z natural width (fixed) convolved with the sum of two Crystal Balls of widths sigma1 and r * sigma1 (a fraction f in the narrow one; shared alpha and fixed n), for the mix of muon momentum resolutions, plus an exponential background over 70-110 GeV (model `cb2_bw_exp`, the
natural width from the `particle` package). The lower panel shows (data - fit) / sigma per bin. The dotted
line is the PDG Z mass, drawn for reference only; the fit does not use it.

- `cb2_bw_exp` (shown): pole mass 90.900 +- 0.005 GeV (stat.), resolution (FWHM/2.355 of the signal) 1.982 +- 0.008 GeV, sigma1 1.167 +- 0.024 GeV, r 2.288 +- 0.083, f 0.820 +- 0.026, alpha 1.750 +- 0.014, n = 2 (fixed), natural width 2.4955 GeV (fixed), chi2/ndf = 48.6/32; -0.288 GeV (-0.32 %) from the PDG mass 91.1879 GeV.
- `voigt_poly` (same data, same range, not shown): peak position 90.812 +- 0.004 GeV (stat.), sigma 1.444 +- 0.005 GeV, natural width 2.4955 GeV (fixed), chi2/ndf = 1690.2/34; -0.376 GeV (-0.41 %) from the PDG mass 91.1879 GeV.

Signal and background yields are not quoted: in the voigt_poly fit the fitted background goes below zero inside the fit range, most likely because the peak model does not describe the radiative tail below the Z and the background bends to absorb it.
Uncertainties are statistical only. The offset from the PDG mass reflects the absent muon momentum-scale
corrections and the simple line shape; it is not a measurement of the Z mass. Unofficial analysis of CMS Open
Data.
