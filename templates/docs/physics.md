# Physics background

{{ dry_banner }}

## What is measured

The LHC collides protons. CMS records the particles that emerge, and the open data used here keep muons, which pass
through the detector almost untouched and are measured very cleanly. This analysis uses CMS proton-proton data at
8 TeV from Run 2012, in the DoubleMuParked datasets.

## Invariant mass

In units where the speed of light is one, every particle satisfies m² = E² − |p|². Energy and momentum change between reference frames, and
m does not. For a pair of muons the same combination is computed from their sum:

```text
m(μμ)² = (E₁ + E₂)² − |p₁ + p₂|²
```

If the two muons come from one parent, conservation of energy and momentum makes this the parent's mass.

From the detector's variables (transverse momentum pT, pseudorapidity η, azimuth φ), and neglecting the muon mass, this
becomes the familiar formula below. The library computes the exact expression, with the muon mass kept.

```text
m² ≈ 2 pT₁ pT₂ (cosh Δη − cos Δφ)
```

## Why a resonance gives a peak

Pairs from a resonance all have nearly the same invariant mass. Pairs from anything else (Drell-Yan production through
a virtual photon, heavy-flavour decays, misidentified muons) have no preferred mass and form a smooth, falling
continuum. The spectrum is therefore a peak on a smooth background, and the fit has one term for each.

| resonance | PDG mass (reference) | what it is |
|---|---|---|
| Z boson | {{ z.pdg }} GeV | carrier of the neutral weak force; very short-lived, so its natural width is large |
| J/ψ | {{ jpsi.pdg }} GeV | bound state of a charm quark and its antiquark; narrow, so the detector sets the observed width |

The PDG values come at run time from the `particle` package ({{ pdg_source }}) and are never used in the fit.

## The line shape

- **Natural width.** An unstable particle's true mass follows a Breit-Wigner curve whose width is set by its lifetime.
  The fit fixes this width to the PDG value.
- **Resolution.** Each momentum is measured with a finite precision that depends on where the muon went. An inclusive
  sample mixes pairs measured with different resolutions, so one Gaussian is not enough.
- **Final-state radiation.** A muon can emit a photon that is not part of the pair, moving it to lower mass. A Crystal
  Ball function, a Gaussian core with a power-law tail, describes this.

The headline models combine these: a Breit-Wigner convolved with two Crystal Ball resolution cores on a smooth
background, `{{ z.model }}` for the Z and `{{ jpsi.model }}` for the J/ψ.

## Why the peak is not a mass measurement

The observed offset of the fitted position from the PDG mass is {{ z.offset }} GeV for the Z and {{ jpsi.offset }} GeV for
the J/ψ. Measuring a mass properly needs muon momentum-scale calibration, which is not applied here, so the offset
is reported and studied (see [validation](validation.md)) and is never presented as a measurement of either mass.
