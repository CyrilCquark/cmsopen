"""Check that the README's results block contains only numbers rendered from the production run.

The block is delimited by the lines ``<!-- RESULTS:BEGIN -->`` and
``<!-- RESULTS:END -->``.

- README without the markers: print "SKIP: README has no results block yet",
  exit 0 (the README is protected; this script never edits it).
- Markers malformed (missing one, repeated, or END before BEGIN): FAIL.
- results/production.json missing: FAIL if the block contains any digit
  (no numbers may appear before the production run).
- results/production.json present: FAIL unless the block text equals
  ``render_results_block(production.json)`` (scripts/render_results.py),
  ignoring leading and trailing blank lines.

Usage:
    python scripts/check_readme_numbers.py [--readme README.md] [--production results/production.json]

Exit 0 on OK or SKIP, 1 on FAIL. Standard library only.
"""

from __future__ import annotations

import argparse
import difflib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from render_results import BEGIN, END, render_results_block  # noqa: E402


def extract_block(text: str) -> str | None:
    """The text between the markers, or None if there are no markers. Raises ValueError if malformed."""
    lines = text.splitlines()
    begins = [i for i, line in enumerate(lines) if line.strip() == BEGIN]
    ends = [i for i, line in enumerate(lines) if line.strip() == END]
    if not begins and not ends:
        return None
    if len(begins) != 1 or len(ends) != 1 or ends[0] < begins[0]:
        raise ValueError(f"malformed results markers: {len(begins)} BEGIN and {len(ends)} END lines")
    return "\n".join(lines[begins[0] + 1:ends[0]]).strip("\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--readme", type=Path, default=Path("README.md"))
    parser.add_argument("--production", type=Path, default=Path("results/production.json"))
    args = parser.parse_args(argv)
    if not args.readme.exists():
        print(f"FAIL: {args.readme} does not exist")
        return 1
    try:
        block = extract_block(args.readme.read_text())
    except ValueError as exc:
        print(f"FAIL: {exc}")
        return 1
    if block is None:
        print("SKIP: README has no results block yet")
        return 0
    if not args.production.exists():
        digits = sorted({c for c in block if c.isdigit()})
        if digits:
            print(f"FAIL: the results block contains digits ({''.join(digits)}) but {args.production} does not exist")
            return 1
        print(f"OK: results block has no numbers and {args.production} does not exist yet")
        return 0
    try:
        expected = render_results_block(json.loads(args.production.read_text())).strip("\n")
    except (ValueError, KeyError, TypeError) as exc:
        print(f"FAIL: cannot render {args.production}: {exc}")
        return 1
    if block.strip("\n") != expected:
        print("FAIL: the README results block differs from the text rendered from the production results:")
        for line in difflib.unified_diff(expected.splitlines(), block.splitlines(), "rendered", "README", lineterm=""):
            print(f"  {line}")
        return 1
    print(f"OK: README results block equals the text rendered from {args.production}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
