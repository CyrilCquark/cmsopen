"""Command-line interface: ``cmsopen analyze FILE ...`` or ``python -m cmsopen analyze FILE ...``.

Runs :func:`cmsopen.pipeline.analyze` and optionally saves its figures and
summaries. Exit status 0 on success, 1 on a handled error (a clear message on
stderr, no traceback), 2 on a command-line usage error.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    from cmsopen.fitting import MODELS
    from cmsopen.pipeline import CHANNELS

    parser = argparse.ArgumentParser(prog="cmsopen", description="Dimuon resonance analysis of CMS Open Data NanoAOD files.")
    sub = parser.add_subparsers(dest="command", required=True)
    a = sub.add_parser("analyze", help="select muons, pair them, fit the resonance peak, write figures and summaries")
    a.add_argument("files", nargs="+", help="NanoAOD ROOT files or https:// URLs")
    a.add_argument("--channel", default="Z_mumu", help=f"analysis channel (registered: {', '.join(sorted(CHANNELS))})")
    a.add_argument("--outdir", type=Path, default=None, help="write figures, summary.txt and summary.json here")
    a.add_argument("--n-events", type=int, default=None, help="process at most this many events in total")
    a.add_argument("--model", default="voigt_poly", choices=MODELS, help="primary peak model")
    a.add_argument("--chunk-size", type=int, default=100_000, help="events per chunk (memory bound)")
    a.add_argument("--no-stability", action="store_true", help="skip the fit-choice stability scan")
    a.add_argument("--quiet", action="store_true", help="do not print the summary")
    return parser


def main(argv: list[str] | None = None) -> int:
    from cmsopen.pipeline import AnalysisError, analyze

    args = build_parser().parse_args(argv)
    try:
        result = analyze(args.files if len(args.files) > 1 else args.files[0], channel=args.channel,
                         n_events=args.n_events, chunk_size=args.chunk_size, model=args.model,
                         outdir=args.outdir, verbose=not args.quiet, stability=not args.no_stability)
    except (AnalysisError, ValueError, TypeError, OSError, KeyError) as exc:
        message = exc.args[0] if isinstance(exc, KeyError) and exc.args else exc
        print(f"error: {message}", file=sys.stderr)
        return 1
    if args.outdir is not None and not args.quiet:
        print(f"Wrote figures, summary.txt and summary.json to {args.outdir}")
    del result
    return 0


if __name__ == "__main__":
    sys.exit(main())
