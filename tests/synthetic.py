"""Synthetic NanoAOD-like ROOT files shared by the tests."""

from pathlib import Path

import awkward as ak
import numpy as np
import uproot

from cmsopen.ingestion import ELECTRON_BRANCHES_DEFAULT, MUON_BRANCHES_DEFAULT

REAL_FILE = Path(__file__).parents[1] / "data" / "45F7AE81-7A79-4CB1-998E-7BD156490294.root"

N_EVENTS = 6
MUON_PT = [[45.0, 38.0], [], [20.0], [50.0, 41.0, 5.0], [], [30.0, 29.0]]
MUON_CHARGE = [[1, -1], [], [1], [-1, 1, 1], [], [1, 1]]
ELECTRON_PT = [[], [25.0], [], [], [12.0, 9.0], []]
HLT_A = [True, False, False, True, False, False]
HLT_B = [True, False, True, False, False, False]

_BOOL_FIELDS = {
    "looseId",
    "mediumId",
    "tightId",
    "softId",
    "isGlobal",
    "isTracker",
    "isPFcand",
    "isEB",
    "isEE",
    "convVeto",
}


def _jagged(values, dtype):
    return ak.values_astype(ak.Array(values), dtype)


def _write_ttree(file, name: str, data: dict) -> None:
    # Plain dict assignment writes an RNTuple in uproot >= 5.7; NanoAOD is a TTree.
    file.mktree(name, {k: (v.type.content if isinstance(v, ak.Array) else v.dtype) for k, v in data.items()})
    file[name].extend(data)


def _fill_defaults(fields: dict, defaults: tuple[str, ...]) -> dict:
    """Add every missing default branch, with simple placeholder values of the right type."""
    pt = fields["pt"]
    for name in defaults:
        if name in fields:
            continue
        if name in _BOOL_FIELDS:
            fields[name] = pt > 25
        else:
            fields[name] = pt * 0 + np.float32(0.01)
    return fields


def write_nano(path: Path, full: bool = False) -> Path:
    """Write a tiny flat NanoAOD-like file with Muon/Electron collections and triggers.

    With ``full=True`` every branch in MUON_BRANCHES_DEFAULT and
    ELECTRON_BRANCHES_DEFAULT is present, so the default readers work.
    """
    muon_pt = _jagged(MUON_PT, np.float32)
    muon = {
        "pt": muon_pt,
        "eta": muon_pt * 0 + np.float32(0.5),
        "phi": muon_pt * 0 + np.float32(1.0),
        "mass": muon_pt * 0 + np.float32(0.105658),
        "charge": _jagged(MUON_CHARGE, np.int32),
        "tightId": muon_pt > 25,
    }
    ele_pt = _jagged(ELECTRON_PT, np.float32)
    electron = {"pt": ele_pt, "eta": ele_pt * 0, "cutBased": ak.values_astype(ele_pt > 10, np.int32)}
    if full:
        electron.update(phi=ele_pt * 0 + np.float32(-2.0), mass=ele_pt * 0 + np.float32(0.000511))
        electron["charge"] = ak.values_astype(ele_pt * 0 - 1, np.int32)
        _fill_defaults(muon, MUON_BRANCHES_DEFAULT)
        _fill_defaults(electron, ELECTRON_BRANCHES_DEFAULT)
    with uproot.recreate(path) as f:
        _write_ttree(
            f,
            "Events",
            {
                "run": np.full(N_EVENTS, 194050, np.uint32),
                "luminosityBlock": np.arange(N_EVENTS, dtype=np.uint32),
                "event": np.arange(100, 100 + N_EVENTS, dtype=np.uint64),
                "Muon": ak.zip(muon),
                "Electron": ak.zip(electron),
                # Run 1 quirk: a per-event scalar that shares the Electron_ prefix.
                "Electron_nNano": np.zeros(N_EVENTS, np.uint32),
                "HLT_Mu17_Mu8": np.array(HLT_A),
                "HLT_Mu17_TkMu8": np.array(HLT_B),
                "HLT_IsoMu24": np.zeros(N_EVENTS, bool),
            },
        )
    return path
