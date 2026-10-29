"""Run the pre-registered validation (dev/validation_plan.md) and save its tables and figures under build/.

For each channel: ``cmsopen.analyze(file, channel=..., validation=True)`` with
the channel's default model as the headline and its validation model for the
scans (dev/validation_plan.md, prompt 8 addendum), then writes into ``build/validation/<channel>/``
the analysis outputs (figures, summary.txt, summary.json), ``validation.txt``
(the per-entry table and the systematics summary) and ``validation_entries``
(png and pdf): every fitted entry's position with its statistical error,
relative to the inclusive fit, with insufficient and failed entries listed
along the axis. Nothing is tuned: the plan fixes every choice.

Usage:
    python scripts/run_validation.py [--file PATH] [--outdir build/validation] [--workers N]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from matplotlib.figure import Figure

from cmsopen import analyze
from cmsopen.datasets import DEV_FILENAME
from cmsopen.plotting import OKABE_ITO, paper_style, save_figure
from cmsopen.validation import ValidationResult

REPO = Path(__file__).resolve().parents[1]


def entries_figure(v: ValidationResult) -> Figure:
    """Position - inclusive position (with statistical errors) for every entry; unfitted entries are labelled."""
    entries = list(v.entries)
    with paper_style():
        fig = Figure(figsize=(6.5, 0.27 * len(entries) + 1.6), layout="constrained")
        ax = fig.subplots()
        incl, incl_err = v.inclusive.position, v.inclusive.error
        y = list(range(len(entries)))[::-1]
        labels = []
        for yi, e in zip(y, entries, strict=True):
            labels.append(f"{e.study}: {e.label}")
            if e.fitted and incl is not None:
                ax.errorbar(1e3 * (e.position - incl), yi, xerr=1e3 * e.error, fmt="o", color="black", ms=3)
            else:
                text = f"insufficient (n = {e.n_pairs:,})" if e.status == "insufficient" else "fit failed"
                ax.text(0.02, yi, text, transform=ax.get_yaxis_transform(), va="center", fontsize=8,
                        color=OKABE_ITO["vermillion"])
        if incl_err is not None:
            ax.axvspan(-1e3 * incl_err, 1e3 * incl_err, color=OKABE_ITO["sky_blue"], alpha=0.35, lw=0,
                       label="inclusive stat. error")
            ax.legend(loc="lower right", fontsize=8)
        ax.axvline(0.0, color="0.4", lw=0.8)
        ax.set_yticks(y, labels, fontsize=8)
        ax.set_xlabel(f"position - inclusive [MeV] ({v.model})")
        ax.set_title(f"CMS Open Data, {v.channel}: validation (development file)", fontsize=9, loc="left")
    return fig


def main(argv: list[str] | None = None) -> int:
    """Run both channels and write their outputs."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--file", type=Path, default=REPO / "data" / DEV_FILENAME)
    parser.add_argument("--outdir", type=Path, default=REPO / "build" / "validation")
    parser.add_argument("--workers", type=int, default=None)
    args = parser.parse_args(argv)
    for channel in ("Z_mumu", "Jpsi_mumu"):
        out = args.outdir / channel
        r = analyze(args.file, channel=channel, validation=True, verbose=False, n_workers=args.workers, outdir=out)
        v = r.validation
        assert v is not None
        (out / "validation.txt").write_text(v.table() + "\n")
        written = save_figure(entries_figure(v), out / "validation_entries")
        print(v.table())
        print(f"\nwritten to {out}: {', '.join(sorted(p.name for p in out.iterdir()))} ({len(written)} figure files)\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
