"""Synthetic production-like files: Z events and J/psi events in one NanoAOD-like file (the tests' registries).

The Z events are those of ``test_pipeline.write_z_file`` (Z triggers fired); the J/psi events follow with the J/psi
triggers fired instead, so each channel's trigger requirement keeps only its own events. Every file has the branches
of the production analysis with validation (the default muon branches, Muon_mediumId and PV_npvsGood).
"""

import awkward as ak
import numpy as np
import uproot
from synthetic import _write_ttree
from test_pipeline import M_MU, write_z_file

from cmsopen.fitting import pdg_mass_width

Z_TRIGGERS = ("HLT_Mu17_Mu8", "HLT_Mu17_TkMu8")
JPSI_TRIGGERS = ("HLT_Dimuon8_Jpsi", "HLT_Dimuon10_Jpsi")
JPSI_SIGMAS = (0.025, 0.05)  # GeV: two resolutions, half of the signal each (like barrel and endcap pairs)


def jpsi_events(n: int, seed: int) -> dict:
    """``n`` events with one J/psi-like or background pair of soft, isolated muons above 3.5 GeV.

    80 % signal: the PDG J/psi mass smeared by one of JPSI_SIGMAS, 30 % of it with a radiative tail (an exponential
    mass loss of mean 50 MeV); 20 % background, uniform in 2.6-3.6 GeV, a quarter of it same-sign. The two muons
    share their pseudorapidity (the pair centre, uniform in |eta| < 2.2, so barrel and endcap pairs exist) and their
    azimuthal opening angle gives the mass: m^2 = 2 m_mu^2 + 2 (E1 E2 - p1 . p2).
    """
    rng = np.random.default_rng(seed + 5000)
    mass = pdg_mass_width("J/psi")[0]
    sig = rng.random(n) < 0.8
    sigma = np.where(rng.random(n) < 0.5, *JPSI_SIGMAS)
    tail = np.where(rng.random(n) < 0.3, rng.exponential(0.05, n), 0.0)
    m = np.where(sig, mass + sigma * rng.standard_normal(n) - tail, rng.uniform(2.6, 3.6, n))
    same_sign = ~sig & (rng.random(n) < 0.25)
    pt1, pt2 = rng.uniform(3.5, 15.0, n), rng.uniform(3.5, 15.0, n)
    eta = rng.uniform(-2.2, 2.2, n)
    p1, p2 = pt1 * np.cosh(eta), pt2 * np.cosh(eta)
    e1, e2 = np.hypot(p1, M_MU), np.hypot(p2, M_MU)
    pz = pt1 * pt2 * np.sinh(eta) ** 2
    cos_dphi = (e1 * e2 + M_MU**2 - 0.5 * m**2 - pz) / (pt1 * pt2)  # from m^2 = 2 m_mu^2 + 2 (E1 E2 - pt1 pt2 cos - pz)
    phi1 = rng.uniform(-np.pi, np.pi, n)
    phi2 = np.mod(phi1 + np.arccos(np.clip(cos_dphi, -1, 1)) + np.pi, 2 * np.pi) - np.pi
    q = rng.choice([-1, 1], n)
    ones = np.ones((n, 2), bool)
    muon = {
        "pt": np.column_stack([pt1, pt2]), "eta": np.column_stack([eta, eta]), "phi": np.column_stack([phi1, phi2]),
        "mass": np.full((n, 2), M_MU), "charge": np.column_stack([q, np.where(same_sign, q, -q)]),
        "pfRelIso04_all": np.full((n, 2), 0.02), "pfRelIso03_all": np.full((n, 2), 0.02),
        "dxy": np.zeros((n, 2)), "dz": np.zeros((n, 2)),
        **{f: ones for f in ("tightId", "mediumId", "looseId", "softId", "isGlobal", "isTracker", "isPFcand")},
    }
    return {
        "Muon": muon,
        "PV_npvsGood": rng.integers(0, 35, n).astype(np.int32),
        "triggers": {JPSI_TRIGGERS[0]: rng.random(n) < 0.8, JPSI_TRIGGERS[1]: rng.random(n) < 0.5},
    }


def write_production_file(path, n_z: int, n_jpsi: int, seed: int):
    """A file of ``n_z`` Z events (``write_z_file`` with two resolutions and FSR) then ``n_jpsi`` J/psi events."""
    z_path = path.with_name(path.stem + ".z.root")
    write_z_file(z_path, n_z, seed=seed, fsr=0.3, wide_fraction=0.5, wide_sigma=4.0, npv=True, medium_id=True,
                 full_branches=True)
    with uproot.open(z_path) as f:
        z = f["Events"].arrays(library="ak")
    z_path.unlink()
    j = jpsi_events(n_jpsi, seed)
    fields = z["Muon"].fields if "Muon" in z.fields else [k[5:] for k in z.fields if k.startswith("Muon_")]
    z_muon = {k: z[f"Muon_{k}"] for k in fields}
    muon = {}
    for k, values in z_muon.items():
        jv = ak.values_astype(ak.Array(j["Muon"][k].tolist()), str(ak.type(values).content.content))
        muon[k] = ak.concatenate([values, jv], axis=0)
    n = n_z + n_jpsi
    branches = {
        "run": np.full(n, 194050, np.uint32), "luminosityBlock": np.arange(n, dtype=np.uint32) // 100,
        "event": np.arange(1, n + 1, dtype=np.uint64), "Muon": ak.zip(muon),
        "PV_npvsGood": np.concatenate([ak.to_numpy(z["PV_npvsGood"]), j["PV_npvsGood"]]),
    }
    for t in Z_TRIGGERS:
        branches[t] = np.concatenate([ak.to_numpy(z[t]), np.zeros(n_jpsi, bool)])
    for t in JPSI_TRIGGERS:
        branches[t] = np.concatenate([np.zeros(n_z, bool), j["triggers"][t]])
    with uproot.recreate(path) as f:
        _write_ttree(f, "Events", branches)
    return path
