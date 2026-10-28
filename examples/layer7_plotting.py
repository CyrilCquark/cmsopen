"""Layer 7 demo: publication-quality figures with cmsopen.plotting.

Runs the full analysis on the real file and writes the final figures (the
same ones examples/make_figures.py writes to docs/figures/) into a new
temporary directory, prints their paths and sizes, then checks them: every
file exists and is non-trivial, PNGs have the pixel size figsize x 300 dpi,
no legend or annotation covers the data and no text is clipped (measured on
the real-data figures), the annotated peak position equals the fitted one
to the displayed precision, and regenerating every figure from scratch
gives byte-identical files.

Usage:
    python examples/layer7_plotting.py [--file PATH]

Exits 1 if any check fails.
"""

from __future__ import annotations

import argparse
import re
import struct
import sys
import tempfile
from pathlib import Path

import cmsopen
from cmsopen.plotting import LAYOUT_DPI, layout_overlaps

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_figures  # noqa: E402  (the figure recipe shared with examples/make_figures.py)

MIN_BYTES = 20_000


class Checks:
    """Collects self-check results and prints one OK/FAIL/SKIP line each."""

    def __init__(self) -> None:
        self.failures: list[str] = []

    def check(self, name: str, ok: bool, detail: str) -> None:
        print(f"{'OK' if ok else 'FAIL'}: {name} ({detail})")
        if not ok:
            self.failures.append(name)

    def skip(self, name: str, reason: str) -> None:
        print(f"SKIP: {name} ({reason})")


def png_size(path: Path) -> tuple[int, int]:
    """Width and height in pixels, read from the PNG header (IHDR chunk)."""
    data = path.read_bytes()[:24]
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"{path} is not a PNG")
    return struct.unpack(">II", data[16:24])


def annotated_peak(fig) -> tuple[str, str] | None:
    for text in fig.axes[0].texts:
        if text.get_gid() == "annotation":
            m = re.search(r"m_\{\\mathrm\{peak\}\}\$ = ([0-9.]+) \$\\pm\$ ([0-9.]+) GeV", text.get_text())
            return (m.group(1), m.group(2)) if m else None
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--file", type=Path, default=None, help="NanoAOD ROOT file (default: first data/*.root)")
    path = (parser.parse_args().file or make_figures.default_file()).resolve()
    if not path.exists():
        sys.exit(f"error: file not found: {path}")

    print(f"cmsopen imported from: {cmsopen.__file__}")
    outdir = Path(tempfile.mkdtemp(prefix="cmsopen-figures-"))
    figs = make_figures.write(make_figures.build(path), outdir)
    print(f"Figures written to {outdir}:")
    for files in figs.files.values():
        for f in files:
            print(f"  {f.name:<20} {f.stat().st_size:>9,} bytes")
    print()
    main_fit = figs.fits[make_figures.MAIN_MODEL]
    print(main_fit.table())
    print()

    checks = Checks()
    expected = [outdir / f"{name}.{fmt}" for name, fmts in make_figures.EXPECTED.items() for fmt in fmts]
    sizes = {p.name: (p.stat().st_size if p.exists() else 0) for p in expected}
    checks.check(
        f"every expected file exists and is larger than {MIN_BYTES:,} bytes",
        all(size > MIN_BYTES for size in sizes.values()),
        ", ".join(f"{name} {size:,}" for name, size in sizes.items()),
    )

    dims = []
    for name, fig in figs.figures.items():
        png = outdir / f"{name}.png"
        w_in, h_in = fig.get_size_inches()
        want = (round(w_in * LAYOUT_DPI), round(h_in * LAYOUT_DPI))
        dims.append((name, png_size(png), want))
    checks.check(
        f"PNG pixel size equals figsize x {LAYOUT_DPI} dpi",
        all(got == want for _, got, want in dims),
        "; ".join(f"{n} {g[0]}x{g[1]} (expected {w[0]}x{w[1]})" for n, g, w in dims),
    )

    problems = {name: layout_overlaps(fig) for name, fig in figs.figures.items()}
    checks.check(
        "no legend or annotation overlaps data, error bars or curves, and no text is clipped (real-data figures)",
        not any(problems.values()),
        "; ".join(f"{n}: {len(p)} problems" + (f" ({p[0]})" if p else "") for n, p in problems.items()),
    )

    shown = annotated_peak(figs.figures["z_peak_fit"])
    m, me = main_fit.peak_position
    if shown is None:
        checks.check("annotated peak position equals the fit to the displayed precision", False, "no peak line found")
    else:
        digits = len(shown[0].split(".")[1]) if "." in shown[0] else 0
        ok = float(shown[0]) == round(m, digits) and float(shown[1]) == round(me, digits)
        checks.check(
            "annotated peak position equals the fit to the displayed precision",
            ok,
            f"annotation {shown[0]} +- {shown[1]} GeV, fit {m:.6f} +- {me:.6f} GeV rounded to {digits} decimals",
        )

    again = Path(tempfile.mkdtemp(prefix="cmsopen-figures-again-"))
    figs2 = make_figures.write(make_figures.build(path), again)
    pairs = [(a, again / a.name) for files in figs.files.values() for a in files]
    pairs += [(outdir / n, again / n) for n in ("z_peak_fit_caption.md", "README.md")]
    differ = [a.name for a, b in pairs if a.read_bytes() != b.read_bytes()]
    checks.check(
        "regenerating every figure from the data gives byte-identical files",
        not differ and len(figs2.files) == len(figs.files),
        f"{len(pairs) - len(differ)} of {len(pairs)} files identical" + (f"; differ: {differ}" if differ else ""),
    )

    if checks.failures:
        print(f"{len(checks.failures)} check(s) failed: {', '.join(checks.failures)}")
        return 1
    print("All checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
