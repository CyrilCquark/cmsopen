"""Write the application assets, outside the repository, from results/production.json and docs/figures/.

Writes to ~/Developer/cmsopen-application/ (or --outdir): a one-page summary (PDF and Markdown), a hero figure and two
supporting figures (copies of the production PNGs), three lengths of activity description, a 10-minute verification
checklist, an email draft to a mentor, and a list of the headline numbers. Every number comes through the placeholders
of scripts/generate_release_files.py. Dry-run data never go to the default directory: --outdir is then required.

Usage:
    python scripts/make_application_assets.py [--outdir DIR]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import textwrap
from io import BytesIO
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate_release_files import build_values, not_met  # noqa: E402
from release_lib import render  # noqa: E402
from render_results import benchmark_text, is_dry_run, met_text, observed_text  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUTDIR = Path.home() / "Developer" / "cmsopen-application"
FIGURES = {
    "figures/hero_z_peak_fit.png": "docs/figures/z_peak_fit.png",
    "figures/supporting_jpsi_peak_fit.png": "docs/figures/jpsi_peak_fit.png",
    "figures/supporting_z_os_vs_ss.png": "docs/figures/z_os_vs_ss.png",
}
TEXTS = {
    "one_page_summary.md": "one_page_summary.md",
    "activity_descriptions.md": "activity_descriptions.md",
    "verify_in_10_minutes.md": "verify_in_10_minutes.md",
    "email_to_mentor.md": "email_to_mentor.md",
    "numbers.md": "numbers.md",
}


def _values(repo: Path, data: dict[str, Any]) -> dict[str, str]:
    values = build_values(repo, data)
    t1, t7 = data["targets"]["T1"], data["targets"]["T7"]
    missed = not_met(data)
    values.update(
        {
            "t1_observed": observed_text("T1", t1["observed"]),
            "t1_status": met_text(t1["met"]),
            "t7_benchmark": benchmark_text(t7),
            "t7_observed": f"coverage {t7['observed'].get('coverage_total', 'not recorded')}, pytest exit "
            f"{t7['observed'].get('pytest_rc')}, quality exit {t7['observed'].get('quality_rc')}"
            + ("; placeholder record" if is_dry_run(data) else ""),
            "t7_status": met_text(t7["met"]),
            "not_met_inline": (", ".join(missed) + " in this run.") if missed else "none in this run.",
        }
    )
    return values


def _plain(markdown: str) -> str:
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", lambda m: m.group(1), markdown)
    return text.replace("**", "").replace("`", "").removeprefix("> ")


def _pdf(summary_md: str, hero: Path) -> bytes:
    """A one-page Letter PDF of the summary with the hero figure, drawn with matplotlib (no extra dependency)."""
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib.backends.backend_pdf import PdfPages
    from matplotlib.figure import Figure
    from matplotlib.image import imread

    line_height, left, width = 0.0148, 0.08, 0.84
    columns = ((0.0, 25), (0.28, 25), (0.57, 27), (0.87, 9))  # x position (fraction of the width), characters
    with matplotlib.rc_context({"pdf.fonttype": 42, "font.family": "DejaVu Sans"}):
        fig = Figure(figsize=(8.5, 11))
        y = 0.965
        for block in re.split(r"\n\s*\n", summary_md.strip()):
            if block.startswith("# "):
                fig.text(left, y, block[2:], fontsize=13.5, fontweight="bold", va="top")
                y -= 0.03
            elif block.startswith("|"):
                rows = [
                    [_plain(c).strip() for c in row.strip("|").split("|")]
                    for row in block.splitlines()
                    if not set(row) <= set("|-")
                ]
                for r, row in enumerate(rows):
                    wrapped = [textwrap.wrap(c, width=w) for c, (_, w) in zip(row, columns, strict=True)]
                    for c, (lines, (x, _)) in enumerate(zip(wrapped, columns, strict=True)):
                        fig.text(
                            left + x * width,
                            y,
                            "\n".join(lines),
                            fontsize=8,
                            va="top",
                            linespacing=1.3,
                            fontweight="bold" if r == 0 or c == 1 else "normal",
                        )
                    y -= line_height * max(len(lines) for lines in wrapped) + 0.004
                    fig.add_artist(
                        matplotlib.lines.Line2D(
                            [left, left + width], [y + 0.002, y + 0.002], linewidth=0.4, color="#888888"
                        )
                    )
                y -= 0.008
            else:
                text = textwrap.fill(_plain(" ".join(block.split())), width=102)
                fig.text(
                    left,
                    y,
                    text,
                    fontsize=8.8,
                    va="top",
                    linespacing=1.3,
                    color="#a00000" if "DRY-RUN" in block else "black",
                )
                y -= line_height * (text.count("\n") + 1) + 0.008
        axes = fig.add_axes((left, 0.03, width, y - 0.04))
        axes.imshow(imread(str(hero)), interpolation="antialiased")
        axes.axis("off")
        buffer = BytesIO()
        metadata = {"CreationDate": None, "ModDate": None, "Creator": "cmsopen", "Producer": "cmsopen"}
        with PdfPages(buffer, metadata=metadata) as pdf:
            pdf.savefig(fig, dpi=200)
    return buffer.getvalue()


def outputs(repo: Path, data: dict[str, Any]) -> dict[str, bytes]:
    """Relative path (inside the output directory) -> content of every asset."""
    values = _values(repo, data)
    folder = repo / "templates" / "application"
    out: dict[str, bytes] = {}
    for name, template in TEXTS.items():
        text = render((folder / template).read_text(), values)
        out[name] = (re.sub(r"\n{3,}", "\n\n", text).strip() + "\n").encode()
    for name, source in FIGURES.items():
        out[name] = (repo / source).read_bytes()
    out["one_page_summary.pdf"] = _pdf(
        out["one_page_summary.md"].decode(), repo / FIGURES["figures/hero_z_peak_fit.png"]
    )
    return out


def write(repo: Path, data: dict[str, Any], outdir: Path) -> list[str]:
    """Write the assets; return the names of those that changed."""
    changed = []
    for name, content in outputs(repo, data).items():
        path = outdir / name
        if not path.exists() or path.read_bytes() != content:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            changed.append(name)
    return changed


def main(argv: list[str] | None = None) -> int:
    """Parse the command line, write the assets and print what changed."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--outdir", type=Path, default=None, help=f"default {DEFAULT_OUTDIR}")
    args = parser.parse_args(argv)
    data = json.loads((REPO / "results" / "production.json").read_text())
    if is_dry_run(data) and args.outdir is None:
        print("REFUSED: dry-run data never go to the default application directory; pass --outdir")
        return 2
    outdir = args.outdir or DEFAULT_OUTDIR
    for name in write(REPO, data, outdir):
        print(f"wrote {outdir / name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
