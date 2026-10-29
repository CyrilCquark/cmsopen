"""Check that the pre-registered production files stay blind.

Fails (exit 1, listing the offenders) if

(a) any production filename from the registry results/production_files.json
    appears in any file of the repository other than the registry itself.
    Tracked files and untracked, non-ignored files are scanned (src/, tests/,
    examples/, scripts/, CLAUDE.md, dev/, ...). A name matches by its stem
    (the UUID without ".root"), so partial references are caught too; or

(b) the SHA-256 of the registry differs from the hash recorded in
    dev/registry.sha256, or either file is missing.

Otherwise prints "OK: no production file referenced outside the registry;
registry intact" and exits 0. Exit 2 on a git error. Standard library only.

Usage:
    python scripts/check_blinding.py
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

REGISTRY = "results/production_files.json"
HASH_FILE = "dev/registry.sha256"


def repo_root() -> Path:
    """The top-level directory of the git repository containing the working directory."""
    out = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(f"not inside a git repository: {out.stderr.strip()}")
    return Path(out.stdout.strip())


def production_names(registry: dict) -> list[str]:
    """Every selected production filename in the registry."""
    return [entry["filename"] for record in registry["records"] for entry in record["selected"]]


def repo_files(root: Path) -> list[str]:
    """Tracked and untracked (not ignored) files of the repository, relative to its root."""
    out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=root,
                         capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(f"git ls-files failed: {out.stderr.strip()}")
    return sorted(set(out.stdout.splitlines()))


def main() -> int:
    """Run the blinding check on the current repository and return the exit status."""
    try:
        root = repo_root()
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    problems: list[str] = []
    registry_path, hash_path = root / REGISTRY, root / HASH_FILE
    if not registry_path.exists():
        print(f"FAIL: the registry {REGISTRY} is missing")
        return 1
    data = registry_path.read_bytes()
    if not hash_path.exists():
        problems.append(f"{HASH_FILE} is missing")
    else:
        recorded = hash_path.read_text().split()[0] if hash_path.read_text().split() else ""
        actual = hashlib.sha256(data).hexdigest()
        if recorded != actual:
            problems.append(f"registry SHA-256 {actual} differs from {HASH_FILE} ({recorded or 'empty'})")
    try:
        names = production_names(json.loads(data))
    except (ValueError, KeyError, TypeError) as exc:
        print(f"FAIL: cannot read the production filenames from {REGISTRY}: {exc}")
        return 1
    stems = {name: name.removesuffix(".root").encode() for name in names}
    try:
        files = repo_files(root)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    for rel in files:
        if rel == REGISTRY:
            continue
        path = root / rel
        if not path.is_file():
            continue  # deleted in the working tree
        content = path.read_bytes()
        for name, stem in stems.items():
            if stem in content or stem.lower() in content.lower():
                problems.append(f"{rel}: references production file {name}")
    if problems:
        print("FAIL: blinding check")
        for p in problems:
            print(f"  {p}")
        return 1
    print("OK: no production file referenced outside the registry; registry intact")
    return 0


if __name__ == "__main__":
    sys.exit(main())
