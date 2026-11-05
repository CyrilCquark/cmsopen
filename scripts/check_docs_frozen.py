"""Check that no protected documentation path changed since a given revision.

Protected paths (see "Documentation freeze" in CLAUDE.md): README.md,
DATA.md, LICENSE, CITATION.cff, everything under docs/ and notebooks/, and
results/production.json. A path counts as changed if it was modified,
added, deleted or renamed (either side of the rename) in a commit since
<rev>, or in the working tree or index relative to <rev>, or if it exists as
an untracked (not ignored) file.

Usage:
    python scripts/check_docs_frozen.py --since <rev>

After the production run docs/figures/ may change only through
scripts/rerender_production_figures.py: a change under docs/figures/, and the
provenance file itself, are accepted only if results/figures_rerender.json
names a commit that is an ancestor of HEAD and lists exactly the files there
with their hashes. A figure edited by hand therefore still fails.

Exit status: 0 and "OK: protected documentation unchanged since <rev>" if
nothing changed; 1 with the list of offending paths otherwise; 2 on a usage
or git error. Standard library only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

PROVENANCE = "results/figures_rerender.json"
FIGURES_DIR = "docs/figures/"
PROTECTED_FILES = ("README.md", "DATA.md", "LICENSE", "CITATION.cff", "results/production.json", PROVENANCE)
PROTECTED_DIRS = ("docs/", "notebooks/")


def is_protected(path: str) -> bool:
    """True if a repository-relative path (forward slashes) is protected."""
    return path in PROTECTED_FILES or any(path.startswith(d) for d in PROTECTED_DIRS)


def git(*args: str, cwd: Path | None = None) -> str:
    """Run git with these arguments and return its output; raise RuntimeError on failure."""
    result = subprocess.run(["git", *args], capture_output=True, text=True, cwd=cwd)
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


def provenance_problems(repo: Path) -> list[str]:
    """Why docs/figures/ does not match results/figures_rerender.json; empty if it does. The file must exist."""
    try:
        record = json.loads((repo / PROVENANCE).read_text())
        commit, listed = record["commit"], record["figures"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return [f"{PROVENANCE} cannot be read: {exc}"]
    try:
        git("merge-base", "--is-ancestor", commit, "HEAD", cwd=repo)
    except RuntimeError:
        return [f"{PROVENANCE} names commit {str(commit)[:12]}, which is not an ancestor of HEAD"]
    on_disk = {f"{FIGURES_DIR}{p.name}": p for p in (repo / FIGURES_DIR).iterdir() if p.is_file()}
    problems = [f"{name} is not listed in {PROVENANCE}" for name in sorted(set(on_disk) - set(listed))]
    problems += [f"{name} is listed in {PROVENANCE} but missing" for name in sorted(set(listed) - set(on_disk))]
    for name in sorted(set(on_disk) & set(listed)):
        if hashlib.sha256(on_disk[name].read_bytes()).hexdigest() != listed[name]:
            problems.append(f"{name} differs from its hash in {PROVENANCE}")
    return problems


def figures_problems(repo: Path) -> list[str]:
    """Why docs/figures/ is not as the production run or the rerender script left it; empty if it is.

    With the provenance file, its hashes decide. Without it, docs/figures/ must equal the commit that last added
    results/production.json (nothing can be said before that commit exists).
    """
    if (repo / PROVENANCE).exists():
        return provenance_problems(repo)
    try:
        added = git("log", "--diff-filter=A", "--format=%H", "--", "results/production.json", cwd=repo).split()
        if not added:
            return []
        changed = git("diff", "--name-only", added[0], "--", FIGURES_DIR, cwd=repo).split("\n")
        changed += git("ls-files", "--others", "--exclude-standard", "--", FIGURES_DIR, cwd=repo).split("\n")
    except RuntimeError:
        return []
    return [f"{name} changed since the production commit without {PROVENANCE}"
            for name in sorted(filter(None, changed))]


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
        repo = Path(git("rev-parse", "--show-toplevel").strip())
        has_record = (repo / PROVENANCE).exists()
        record_problems = provenance_problems(repo) if has_record else []
        accepted = has_record and not record_problems
        offenders = sorted(
            {
                (status, path)
                for status, path in changed_paths(args.since)
                if is_protected(path) and not (accepted and (path == PROVENANCE or path.startswith(FIGURES_DIR)))
            },
            key=lambda item: item[1],
        )
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    for problem in record_problems:
        print(f"FAIL: {problem}")
    if offenders:
        print(f"FAIL: protected documentation changed since {args.since}:")
        for status, path in offenders:
            print(f"  {status:<5} {path}")
    if offenders or record_problems:
        return 1
    print(f"OK: protected documentation unchanged since {args.since}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
