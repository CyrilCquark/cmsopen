"""Run the notebooks in notebooks/ and check their self-checks; nothing is written back.

By default each notebook runs top to bottom in a fresh kernel, as a reader would run it from a fresh clone. With
--self-checks-only only the cells tagged setup, self-check and finish run, which is enough to check that the numbers
in the text equal results/production.json.

Usage:
    python scripts/check_notebooks.py [--self-checks-only] [--repo DIR]

Exit 0 only if every notebook ends with "All checks passed", without a FAIL line.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import nbformat
from nbclient import NotebookClient
from nbclient.exceptions import CellExecutionError

REPO = Path(__file__).resolve().parents[1]
NAMES = ("01_z_peak", "02_jpsi_peak", "03_modular_usage")
SELF_CHECK_TAGS = {"setup", "self-check", "finish"}


def _text_of(cell: dict) -> str:
    return "".join(o.get("text", "") for o in cell.get("outputs", []) if o.get("output_type") == "stream")


def run_notebook(path: Path, self_checks_only: bool = False) -> tuple[bool, list[str]]:
    """Execute one notebook in memory from its own directory; return (passed, its OK and FAIL lines)."""
    nb = nbformat.read(path, as_version=4)
    if self_checks_only:
        nb.cells = [c for c in nb.cells if SELF_CHECK_TAGS & set(c.metadata.get("tags", []))]
    client = NotebookClient(nb, timeout=600, kernel_name="python3", resources={"metadata": {"path": str(path.parent)}})
    try:
        client.execute()
    except CellExecutionError as exc:
        return False, [f"FAIL: a cell raised: {str(exc).strip().splitlines()[-1][:200]}"]
    text = "\n".join(_text_of(c) for c in nb.cells if c.cell_type == "code")
    lines = [line for line in text.splitlines() if line.startswith(("OK:", "FAIL:", "All checks passed"))]
    passed = "All checks passed" in lines and not any(line.startswith("FAIL:") for line in lines)
    return passed, lines


def main(argv: list[str] | None = None) -> int:
    """Run every notebook and print its checks."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--self-checks-only", action="store_true")
    parser.add_argument("--repo", type=Path, default=REPO)
    args = parser.parse_args(argv)
    ok = True
    for name in NAMES:
        path = args.repo / "notebooks" / f"{name}.ipynb"
        if not path.exists():
            print(f"FAIL: {path} does not exist")
            ok = False
            continue
        start = time.perf_counter()
        passed, lines = run_notebook(path, args.self_checks_only)
        n_ok = sum(line.startswith("OK:") for line in lines)
        print(f"{'OK' if passed else 'FAIL'}: {name}: {n_ok} self-checks passed in {time.perf_counter() - start:.0f} s")
        for line in lines:
            if line.startswith("FAIL:"):
                print(f"  {line}")
        ok = ok and passed
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
