"""Select the development set by the pre-registered rule of dev/development_set.md.

For each record, list the per-file ROOT file index from the CERN Open Data
API, sort the names alphabetically (a name's index is its 0-based position,
as in the production registry), drop the original development file and
every production file of results/production_files.json, and take the
lowest-index names: 3 from record 31129, 2 from record 31123. Writes
dev/development_set.json and prints ONLY the chosen names and
"disjoint from production: OK". Production names are compared in memory
and never printed. Standard library only.

Usage:
    python scripts/development_set.py [--listing-dir DIR]

``--listing-dir`` reads ``<record_id>.json`` (the API response) from DIR
instead of downloading it.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
REGISTRY = REPO / "results" / "production_files.json"
OUT = REPO / "dev" / "development_set.json"
API = "https://opendata.cern.ch/api/records/{}"
ORIGINAL = "45F7AE81-7A79-4CB1-998E-7BD156490294.root"
TAKE = {31129: 3, 31123: 2}


def listing(record_id: int, listing_dir: Path | None) -> list[dict[str, Any]]:
    """The per-file ROOT file index of a record (not the merged-file index)."""
    if listing_dir is not None:
        data = json.loads((listing_dir / f"{record_id}.json").read_text())
    else:
        with urllib.request.urlopen(API.format(record_id), timeout=60) as response:
            data = json.load(response)
    indices = [x for x in data["metadata"]["_file_indices"]
               if x["key"].endswith("_root_file_index.json") and "_merged_" not in x["key"]]
    if len(indices) != 1:
        raise RuntimeError(f"record {record_id}: expected one per-file ROOT file index, found {len(indices)}")
    return list(indices[0]["files"])


def https_url(uri: str) -> str:
    """root://eospublic.cern.ch//eos/opendata/... -> https://opendata.cern.ch/eos/opendata/..."""
    prefix = "root://eospublic.cern.ch/"
    if not uri.startswith(prefix):
        raise ValueError(f"unexpected file URI scheme: {uri[:40]}")
    return "https://opendata.cern.ch" + uri[len(prefix):].replace("//", "/")


def main(argv: list[str] | None = None) -> int:
    """Apply the rule, write dev/development_set.json and print the chosen names."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--listing-dir", type=Path, default=None)
    args = parser.parse_args(argv)
    registry = json.loads(REGISTRY.read_text())
    production = {e["filename"] for r in registry["records"] for e in r["selected"]}
    chosen: list[dict[str, Any]] = []
    for record_id, k in TAKE.items():
        files = sorted(listing(record_id, args.listing_dir), key=lambda f: f["filename"])
        names = [f["filename"] for f in files]
        if len(set(names)) != len(names):
            raise RuntimeError(f"record {record_id}: duplicate file names in the index")
        picked = [(i, f) for i, (n, f) in enumerate(zip(names, files, strict=True))
                  if n != ORIGINAL and n not in production][:k]
        if len(picked) != k:
            raise RuntimeError(f"record {record_id}: only {len(picked)} eligible files")
        for index, f in picked:
            chosen.append({"record_id": record_id, "index": index, "filename": f["filename"],
                           "size_bytes": int(f["size"]), "checksum": f["checksum"], "https_url": https_url(f["uri"])})
    overlap = sum(c["filename"] in production for c in chosen) + (ORIGINAL in production)
    if overlap:
        print(f"FAIL: {overlap} development-set file(s) coincide with production files")
        return 1
    OUT.write_text(json.dumps({"rule": "dev/development_set.md", "original_development_file": ORIGINAL,
                               "files": chosen}, indent=2) + "\n")
    for c in chosen:
        print(c["filename"])
    print("disjoint from production: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
