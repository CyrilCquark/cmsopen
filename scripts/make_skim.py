"""Write the small real-data sample examples/data/cmsopen_sample.root from the original development file.

The sample keeps only the branches the analysis reads (the event IDs, nMuon
and the 16 default muon fields, the four trigger paths of the Z and J/psi
channels, PV_npvsGood) for the first N events of the development file. N is
fixed by a mass-blind rule: the largest event count whose file is smaller
than 8 MB (8,000,000 bytes), found by bisection on the file size (which
grows with N). The rule looks only at the file size, never at any mass.

Also writes examples/data/SAMPLE.md (provenance, N, size, adler32, SHA-256).
The file is reproducible: the same N gives the same arrays (the ROOT file's
bytes may differ in metadata such as its creation time).

Usage:
    python scripts/make_skim.py [--source PATH] [--out PATH] [--events N]

``--events N`` writes exactly N events (skipping the bisection).
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path
from typing import Any

import awkward as ak
import uproot

from cmsopen.datasets import DEV_FILENAME, DEV_URL, adler32_of
from cmsopen.ingestion import DIMUON_TRIGGERS_2012, EVENT_BRANCHES, MUON_BRANCHES_DEFAULT

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "examples" / "data" / "cmsopen_sample.root"
SIZE_LIMIT = 8_000_000  # bytes
JPSI_TRIGGERS = ("HLT_Dimuon8_Jpsi", "HLT_Dimuon10_Jpsi")
FLAT = (*EVENT_BRANCHES, *DIMUON_TRIGGERS_2012, *JPSI_TRIGGERS, "PV_npvsGood")
MUON = tuple(f"Muon_{f}" for f in MUON_BRANCHES_DEFAULT)
RECORD_ID = 31129


def read_source(path: Path) -> dict[str, Any]:
    """Every kept branch of the whole development file."""
    with uproot.open(path) as f:
        return dict(f["Events"].arrays([*FLAT, *MUON], library="ak", how=dict))


def write_skim(arrays: dict[str, Any], n: int, path: Path) -> int:
    """Write the first ``n`` events to ``path`` (a NanoAOD-like Events tree) and return the file size in bytes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    branches: dict[str, Any] = {name: arrays[name][:n] for name in FLAT}
    branches["Muon"] = ak.zip({b.removeprefix("Muon_"): arrays[b][:n] for b in MUON})
    with uproot.recreate(path) as f:  # mktree + extend: plain assignment would write an RNTuple, not a TTree
        f.mktree("Events", {k: v.type.content for k, v in branches.items()})
        f["Events"].extend(branches)
    return path.stat().st_size


def largest_n(arrays: dict[str, Any], scratch: Path) -> int:
    """The largest event count whose skim stays below SIZE_LIMIT (bisection; the size grows with the count)."""
    lo, hi = 0, len(arrays["run"])  # size(lo) < limit; size(hi) unknown
    if write_skim(arrays, hi, scratch) < SIZE_LIMIT:
        return hi
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if write_skim(arrays, mid, scratch) < SIZE_LIMIT:
            lo = mid
        else:
            hi = mid
    return lo


def sample_md(n: int, out: Path, source: Path) -> str:
    """The provenance file of the sample."""
    data = out.read_bytes()
    return f"""# cmsopen_sample.root

A small sample of real CMS collision data for readers without the 1.1 GB
development file, written by `python scripts/make_skim.py`.

| | |
|---|---|
| source record | CERN Open Data record {RECORD_ID} (Run2012C DoubleMuParked, NanoAOD Run 1) |
| source file | `{source.name}` (the original development file; see DATA.md) |
| source URL | {DEV_URL} |
| events | the first {n:,} events of the source file (entries 0 to {n - 1:,}) |
| event-count rule | the largest N whose file is under {SIZE_LIMIT:,} bytes (mass-blind: only the size is used) |
| branches | {", ".join(FLAT)}, nMuon and Muon_{{{", ".join(MUON_BRANCHES_DEFAULT)}}} |
| size | {len(data):,} bytes |
| adler32 | {adler32_of(out)} |
| SHA-256 | {hashlib.sha256(data).hexdigest()} |

Licence: CMS open data are released under the Creative Commons CC0 waiver
(https://creativecommons.org/publicdomain/zero/1.0/). Citation: see DATA.md.

Regenerating the sample from the source file gives the same arrays (the
test `tests/test_sample.py` checks this when the source file is present);
the file's bytes can differ in ROOT metadata such as the creation time, so
the checksums above identify this committed copy.
"""


def main(argv: list[str] | None = None) -> int:
    """Write the sample and its provenance file."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", type=Path, default=REPO / "data" / DEV_FILENAME)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--events", type=int, default=None, help="write exactly this many events")
    args = parser.parse_args(argv)
    if not args.source.exists():
        print(f"error: the development file is missing: {args.source}", file=sys.stderr)
        return 2
    arrays = read_source(args.source)
    n = args.events if args.events is not None else largest_n(arrays, args.out.with_suffix(".tmp.root"))
    args.out.with_suffix(".tmp.root").unlink(missing_ok=True)
    size = write_skim(arrays, n, args.out)
    print(f"N = {n:,} events; {args.out} ({size:,} bytes)")
    if args.out.resolve() == OUT.resolve():
        (OUT.parent / "SAMPLE.md").write_text(sample_md(n, args.out, args.source))
        print(f"provenance written to {OUT.parent / 'SAMPLE.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
