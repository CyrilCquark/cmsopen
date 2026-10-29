"""Check that no protected documentation path changed since a given revision.

Protected paths (see "Documentation freeze" in CLAUDE.md): README.md,
DATA.md, LICENSE, CITATION.cff, everything under docs/ and notebooks/, and
results/production.json. A path counts as changed if it was modified,
added, deleted or renamed (either side of the rename) in a commit since
<rev>, or in the working tree or index relative to <rev>, or if it exists as
an untracked (not ignored) file.

Usage:
    python scripts/check_docs_frozen.py --since <rev>

Exit status: 0 and "OK: protected documentation unchanged since <rev>" if
nothing changed; 1 with the list of offending paths otherwise; 2 on a usage
or git error. Standard library only.
"""

from __future__ import annotations

import argparse
import subprocess
import sys

PROTECTED_FILES = ("README.md", "DATA.md", "LICENSE", "CITATION.cff", "results/production.json")
PROTECTED_DIRS = ("docs/", "notebooks/")


def is_protected(path: str) -> bool:
    """True if a repository-relative path (forward slashes) is protected."""
    return path in PROTECTED_FILES or any(path.startswith(d) for d in PROTECTED_DIRS)


def git(*args: str) -> str:
    """Run git with these arguments and return its output; raise RuntimeError on failure."""
    result = subprocess.run(["git", *args], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def changed_paths(rev: str) -> list[tuple[str, str]]:
    """(status, path) for every path that differs from <rev>: commits, index, working tree, untracked."""
    changes: list[tuple[str, str]] = []
    # `git diff <rev>` compares <rev> with the working tree, which covers commits since <rev>, staged
    # and unstaged changes in one listing. -M reports renames; both sides are checked.
    for line in git("diff", "--name-status", "-M", "--no-color", rev, "--").splitlines():
        parts = line.split("\t")
        status = parts[0]
        for path in parts[1:]:
            changes.append((status, path))
    for path in git("ls-files", "--others", "--exclude-standard").splitlines():
        changes.append(("??", path))
    return changes


def main(argv: list[str] | None = None) -> int:
    """Parse the command line, run the demo or tool, and return the exit status."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--since", required=True, metavar="REV", help="baseline revision (e.g. the layer's START commit)"
    )
    args = parser.parse_args(argv)
    try:
        git("rev-parse", "--verify", "--quiet", f"{args.since}^{{commit}}")
    except RuntimeError:
        print(f"error: {args.since!r} is not a commit in this repository", file=sys.stderr)
        return 2
    try:
        offenders = sorted(
            {(status, path) for status, path in changed_paths(args.since) if is_protected(path)},
            key=lambda item: item[1],
        )
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if offenders:
        print(f"FAIL: protected documentation changed since {args.since}:")
        for status, path in offenders:
            print(f"  {status:<5} {path}")
        return 1
    print(f"OK: protected documentation unchanged since {args.since}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
