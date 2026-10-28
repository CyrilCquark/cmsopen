"""cmsopen: end-to-end analysis of CMS open data.

Reads DoubleMuon NanoAOD ROOT files from the CERN Open Data Portal, builds
muon pairs, and reconstructs the dimuon invariant mass spectrum to reveal the
Z boson resonance near 91 GeV.
"""

from cmsopen.ingestion import EventCollection, open_events
from cmsopen.kinematics import (
    delta_eta,
    delta_phi,
    delta_r,
    invariant_mass,
    invariant_mass_squared,
    pair_eta,
    pair_phi,
    pair_pt,
    pair_rapidity,
    pair_summary,
    sum_four_momenta,
)
from cmsopen.objects import Electron, FourMomentum, Muon

__version__ = "0.1.0"

__all__ = [
    "Electron",
    "EventCollection",
    "FourMomentum",
    "Muon",
    "__version__",
    "delta_eta",
    "delta_phi",
    "delta_r",
    "invariant_mass",
    "invariant_mass_squared",
    "open_events",
    "pair_eta",
    "pair_phi",
    "pair_pt",
    "pair_rapidity",
    "pair_summary",
    "sum_four_momenta",
]
