"""Benchmark cmsopen.analyze: wall time, events per second and peak memory, serial versus parallel.

Runs the Z_mumu analysis (no stability scan, figures included) on one file
for: serial, 2 workers, 4 workers and the machine's core count. It also
times the event-processing stage alone (reading, selection, pairing and
masses: the part that runs in the workers), separately from the full
analysis, which adds the fits and figures in the main process. Each
configuration runs in a fresh Python subprocess, because peak resident
memory (``resource.getrusage(...).ru_maxrss``) is a high-water mark for the
lifetime of a process: it reports the main process and, separately, the
largest worker process. Prints a plain table.

Usage:
    python scripts/benchmark.py --file data/<development file>.root [--n-events N] [--chunk-size N]
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import resource
import subprocess
import sys
import time


def _rss_mb(usage: resource.struct_rusage) -> float:
    # ru_maxrss is in bytes on macOS and in kilobytes on Linux.
    scale = 1.0 if sys.platform == "darwin" else 1024.0
    return usage.ru_maxrss * scale / 1e6


def _one(path: str, n_events: int | None, chunk_size: int, workers: int | None) -> dict:
    import cmsopen
    from cmsopen.pipeline import CHANNELS, _execute, _muon_fields, _plan

    cfg = CHANNELS["Z_mumu"]
    fields = _muon_fields(cfg.muon_cuts)
    t0 = time.perf_counter()
    units, n_done = _plan([path], cfg, n_events, chunk_size, fields)
    _execute(units, cfg, fields, workers)
    stage = time.perf_counter() - t0
    t0 = time.perf_counter()
    result = cmsopen.analyze(path, n_events=n_events, chunk_size=chunk_size, n_workers=workers,
                             verbose=False, stability=False)
    wall = time.perf_counter() - t0
    return {
        "workers": workers, "events": result.n_events, "wall_s": wall, "events_per_s": result.n_events / wall,
        "stage_s": stage, "stage_events_per_s": n_done / stage,
        "rss_main_mb": _rss_mb(resource.getrusage(resource.RUSAGE_SELF)),
        "rss_worker_mb": _rss_mb(resource.getrusage(resource.RUSAGE_CHILDREN)),
        "peak": result.fit.peak_position[0],
    }


def main(argv: list[str] | None = None) -> int:
    """Parse the command line, run the demo or tool, and return the exit status."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--file", required=True, help="NanoAOD file to analyse")
    parser.add_argument("--n-events", type=int, default=None, help="process at most this many events")
    parser.add_argument("--chunk-size", type=int, default=50_000, help="events per chunk (default 50,000)")
    parser.add_argument("--_one", type=int, default=None, help=argparse.SUPPRESS)  # internal: run one config
    args = parser.parse_args(argv)
    if args._one is not None:
        workers = None if args._one == 0 else args._one
        print(json.dumps(_one(args.file, args.n_events, args.chunk_size, workers)))
        return 0

    cores = os.cpu_count() or 1
    configs = [0, 2, 4] + ([cores] if cores not in (2, 4) else [])
    rows = []
    for w in configs:
        cmd = [sys.executable, os.path.abspath(__file__), "--file", args.file, "--chunk-size", str(args.chunk_size),
               "--_one", str(w)]
        if args.n_events:
            cmd += ["--n-events", str(args.n_events)]
        out = subprocess.run(cmd, capture_output=True, text=True)
        if out.returncode != 0:
            print(out.stderr, file=sys.stderr)
            return 1
        rows.append(json.loads(out.stdout.strip().splitlines()[-1]))
    serial = rows[0]
    print(f"cmsopen analyze benchmark: {os.path.basename(args.file)}, {serial['events']:,} events, "
          f"chunk size {args.chunk_size:,}, {cores} cores, Python {platform.python_version()}, {platform.platform()}")
    print(f"{'configuration':<16}{'wall [s]':>10}{'events/s':>12}{'speed-up':>10}{'processing [s]':>16}"
          f"{'events/s':>12}{'speed-up':>10}{'peak RSS main [MB]':>21}{'peak RSS worker [MB]':>23}{'same result':>13}")
    print(f"{'':<16}{'(full analysis)':>32}{'(event processing only)':>38}")
    for r in rows:
        name = "serial" if r["workers"] is None else f"{r['workers']} workers"
        worker_rss = "-" if r["workers"] is None else f"{r['rss_worker_mb']:.0f}"
        print(f"{name:<16}{r['wall_s']:>10.2f}{r['events_per_s']:>12,.0f}{serial['wall_s'] / r['wall_s']:>10.2f}"
              f"{r['stage_s']:>16.2f}{r['stage_events_per_s']:>12,.0f}{serial['stage_s'] / r['stage_s']:>10.2f}"
              f"{r['rss_main_mb']:>21.0f}{worker_rss:>23}{'yes' if r['peak'] == serial['peak'] else 'NO':>13}")
    return 0 if all(r["peak"] == serial["peak"] for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
