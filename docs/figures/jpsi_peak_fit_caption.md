# jpsi_peak_fit

Invariant mass of the two muons of one opposite-sign pair per event (the pair with the highest
pT sum), after the J/psi -> mu+ mu- selection (J/psi -> mu+ mu-: soft-ID muons above 3 GeV, J/psi dimuon triggers, 2.6-3.6 GeV), in 20 MeV
bins (2012B+2012C DoubleMuParked, sqrt(s) = 8 TeV), with a fit of a Breit-Wigner of the J/psi natural width (fixed) convolved with the sum of two Crystal Balls of widths sigma1 and r * sigma1 (a fraction f in the narrow one; shared alpha and fixed n) plus a quadratic background over 2.8-3.4 GeV (model
`cb2_bw_poly2`, the natural width from the `particle` package). The lower panel shows (data - fit) / sigma per
bin. The dotted line is the PDG J/psi mass, drawn for reference only; the fit does not use it.

- `cb2_bw_poly2` (shown): pole mass 3.093321 +- 0.000074 GeV (stat.), resolution (FWHM/2.355 of the signal) 0.02712 +- 0.00012 GeV, sigma1 0.02314 +- 0.00032 GeV, r 1.792 +- 0.015, f 0.543 +- 0.022, alpha 1.349 +- 0.014, n = 100 (fixed), natural width 0.0926 MeV (fixed), chi2/ndf = 63.6/21; -0.003579 GeV (-0.12 %) from the PDG mass 3.0969 GeV.
- `voigt_poly` (same data, same range, not shown): peak position 3.092421 +- 0.000061 GeV (stat.), sigma 0.030947 +- 0.000056 GeV, natural width 0.0926 MeV (fixed), chi2/ndf = 3778.8/24; -0.004479 GeV (-0.14 %) from the PDG mass 3.0969 GeV.

The signal and background yields of the fit shown are given in the figure annotation.
Uncertainties are statistical only. The offset from the PDG mass reflects the absent muon momentum-scale
corrections and the simple line shape; it is not a measurement of the J/psi mass. Unofficial analysis of CMS Open
Data.
