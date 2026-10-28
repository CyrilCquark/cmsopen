# z_peak_fit

Invariant mass of the two muons of one opposite-sign pair per event (the pair with the highest
pT sum), after the Z -> mu+ mu- selection, in 1 GeV bins, with a fit of a Voigt peak (the Breit-Wigner
natural width of the Z fixed to 2.4955 GeV from the `particle` package, Gaussian resolution
free) plus a quadratic background over 70-110 GeV. The lower panel shows
(data - fit) / sigma per bin. The dotted line is the PDG Z mass, drawn for reference only; the fit does not
use it.

- Voigt + pol2 (shown): peak position 90.783 +- 0.018 GeV (stat.), sigma 1.395 +- 0.024 GeV, chi2/ndf = 93.4/34; -0.405 GeV (-0.44 %) from the PDG mass 91.1879 GeV.
- Gaussian + pol2 (same data, same range, not shown): peak position 90.781 +- 0.018 GeV (stat.), sigma 2.267 +- 0.017 GeV, chi2/ndf = 500.2/34; -0.407 GeV (-0.45 %) from the PDG mass 91.1879 GeV.

Signal and background yields are not quoted: in both fits the fitted quadratic background goes below zero inside the fit range, most likely because the symmetric peak model does not describe the radiative tail below the Z and the background bends to absorb it.
Uncertainties are statistical only. The offset from the PDG mass reflects the absent muon momentum-scale
corrections and the simple line shape; it is not a measurement of the Z mass. Unofficial analysis of CMS Open
Data.
