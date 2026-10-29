"""Compare two validation runs entry by entry (the prompt 8 regression check of dev/validation_plan.md).

Reads ``<dir>/<channel>/summary.json`` of a reference run and a new run (both
written by scripts/run_validation.py) and prints, per entry, the pairs,
position, resolution, chi2/ndf, signal yield and status of both, side by
side, with the largest differences. Exits 1 if any entry differs beyond the
tolerances: pairs and status exactly, the other quantities to a relative
1e-6 (fits of the same histogram with the same model and start values are
deterministic up to floating-point summation order).

Usage:
    python scripts/compare_validation.py REFERENCE_DIR NEW_DIR [--out FILE]
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

QUANTITIES = ("position", "resolution", "chi2_ndf", "signal_yield")
RTOL = 1e-6


def _entries(path: Path) -> tuple[str, list[dict[str, Any]]]:
    v = json.loads(path.read_text())["validation"]
    return v["model"], [v["inclusive"], *v["entries"]]


def _same(a: float | None, b: float | None) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return math.isclose(a, b, rel_tol=RTOL, abs_tol=0.0)


def compare(reference: Path, new: Path) -> tuple[list[str], int]:
    """The side-by-side lines of one channel and the number of entries that differ."""
    ref_model, ref = _entries(reference)
    new_model, cur = _entries(new)
    lines = [f"reference model {ref_model}, new validation model {new_model}"]
    lines.append(
        f"{'entry':<34}{'pairs':>14}  {'position ref | new [GeV]':>27}  {'resolution ref | new':>21}  "
        f"{'chi2/ndf ref | new':>17}  {'signal ref | new':>17}  status ref | new"
    )
    n_diff = 0
    max_rel = dict.fromkeys(QUANTITIES, 0.0)
    for r, c in zip(ref, cur, strict=True):
        name = f"{r['study']}: {r['label']}"
        ok = (r["study"], r["label"], r["n_pairs"], r["status"]) == (c["study"], c["label"], c["n_pairs"], c["status"])
        for q in QUANTITIES:
            ok &= _same(r.get(q), c.get(q))
            if r.get(q) is not None and c.get(q) is not None and r[q] != 0:
                max_rel[q] = max(max_rel[q], abs(c[q] - r[q]) / abs(r[q]))
        n_diff += not ok

        def pair(q: str, fmt: str, e1: dict[str, Any] = r, e2: dict[str, Any] = c) -> str:
            a, b = e1.get(q), e2.get(q)
            return "-" if a is None and b is None else f"{'-' if a is None else format(a, fmt)} | " \
                f"{'-' if b is None else format(b, fmt)}"

        pairs = f"{r['n_pairs']:,} | {c['n_pairs']:,}" if r["n_pairs"] != c["n_pairs"] else f"{r['n_pairs']:,}"
        lines.append(
            f"{name:<34}{pairs:>14}  {pair('position', '.4f'):>27}  {pair('resolution', '.4f'):>21}  "
            f"{pair('chi2_ndf', '.3f'):>17}  {pair('signal_yield', ',.0f'):>17}  "
            f"{r['status']} | {c['status']}{'' if ok else '   <-- DIFFERS'}"
        )
    lines.append("largest relative difference: " + ", ".join(f"{q} {v:.1e}" for q, v in max_rel.items()))
    return lines, n_diff


def main(argv: list[str] | None = None) -> int:
    """Compare both channels and print the result."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("reference", type=Path)
    parser.add_argument("new", type=Path)
    parser.add_argument("--out", type=Path, default=None, help="also write the comparison to this file")
    args = parser.parse_args(argv)
    out: list[str] = []
    total = 0
    for channel in ("Z_mumu", "Jpsi_mumu"):
        lines, n_diff = compare(args.reference / channel / "summary.json", args.new / channel / "summary.json")
        total += n_diff
        out += [f"== {channel} ==", *lines, f"{channel}: {n_diff} entries differ", ""]
    out.append("OK: the validation tables reproduce" if total == 0 else f"FAIL: {total} entries differ")
    text = "\n".join(out)
    print(text)
    if args.out is not None:
        args.out.write_text(text + "\n")
    return 0 if total == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
