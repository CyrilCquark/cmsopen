"""Command-line interface: ``cmsopen analyze FILE ...`` and ``cmsopen fetch`` (also via ``python -m cmsopen``).

Runs :func:`cmsopen.pipeline.analyze` and optionally saves its figures and
summaries. Exit status 0 on success, 1 on a handled error (a clear message on
stderr, no traceback), 2 on a command-line usage error.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    """The argparse parser for the cmsopen command and its subcommands."""
    from cmsopen.fitting import MODELS
    from cmsopen.pipeline import CHANNELS

    parser = argparse.ArgumentParser(
        prog="cmsopen", description="Dimuon resonance analysis of CMS Open Data NanoAOD files."
    )
    sub = parser.add_subparsers(dest="command", required=True)
    a = sub.add_parser("analyze", help="select muons, pair them, fit the resonance peak, write figures and summaries")
    a.add_argument("files", nargs="+", help="NanoAOD ROOT files or https:// URLs")
    a.add_argument("--channel", default="Z_mumu", help=f"analysis channel (registered: {', '.join(sorted(CHANNELS))})")
    a.add_argument("--outdir", type=Path, default=None, help="write figures, summary.txt and summary.json here")
    a.add_argument("--n-events", type=int, default=None, help="process at most this many events in total")
    a.add_argument("--model", default=None, choices=MODELS, help="primary peak model (default: the channel's model)")
    a.add_argument("--chunk-size", type=int, default=100_000, help="events per chunk (memory bound)")
    a.add_argument(
        "--workers",
        type=int,
        default=None,
        metavar="N",
        help=(
            "process chunks in N worker processes (identical results to serial); from your own script on macOS, "
            "calling analyze(n_workers=N) needs the `if __name__ == \"__main__\":` guard"
        ),
    )
    a.add_argument("--no-stability", action="store_true", help="skip the fit-choice stability scan")
    a.add_argument("--quiet", action="store_true", help="do not print the summary")
    f = sub.add_parser("fetch", help="download the development data file (resumable, size and adler32 verified)")
    f.add_argument("--dest", type=Path, default=Path("data"), help="directory to download into (default: data)")
    f.add_argument("--force", action="store_true", help="replace an existing file that fails verification")
    f.add_argument("--url", default=None, help="download from this URL instead of the CERN Open Data portal")
    f.add_argument("--size", type=int, default=None, help="expected size in bytes (with --url)")
    f.add_argument("--adler32", default=None, help="expected adler32 checksum, 8 hex digits (with --url)")
    return parser


def _fetch(args: argparse.Namespace) -> int:
    from cmsopen.datasets import DownloadError, fetch_example_data

    try:
        path = fetch_example_data(args.dest, url=args.url, force=args.force, size=args.size, adler32=args.adler32)
    except (DownloadError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(path)
    return 0


def main(argv: list[str] | None = None) -> int:
    """Parse the command line, run the demo or tool, and return the exit status."""
    from cmsopen.pipeline import AnalysisError, analyze

    args = build_parser().parse_args(argv)
    if args.command == "fetch":
        return _fetch(args)
    try:
        result = analyze(
            args.files if len(args.files) > 1 else args.files[0],
            channel=args.channel,
            n_events=args.n_events,
            chunk_size=args.chunk_size,
            model=args.model,
            outdir=args.outdir,
            verbose=not args.quiet,
            stability=not args.no_stability,
            n_workers=args.workers,
        )
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
