"""Measure the aggregate download throughput from the CERN Open Data portal for 1-4 concurrent streams.

Uses ONLY the development set (dev/development_set.json, plus the original
development file of DATA.md), never a production URL: each stream requests
one byte range (default 50 MB, ``Range: bytes=a-b``) of a different
development file, at a different offset for each stream count so no range is
requested twice. Nothing is written to disk. Prints one line per stream count
(bytes, wall time, aggregate MB/s, ratio to one stream) and the decision rule
of prompt 12: parallel downloads are worth adding if 4 streams give at least
1.5x the aggregate throughput of 1 stream.

Usage:
    python scripts/measure_throughput.py [--mb 50] [--streams 1 2 3 4]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DECISION_RATIO = 1.5


def development_urls() -> list[str]:
    """HTTPS URLs of the development set (never the production registry)."""
    sys.path.insert(0, str(REPO / "src"))
    from cmsopen.datasets import DEV_URL

    listing = json.loads((REPO / "dev" / "development_set.json").read_text())
    return [DEV_URL, *(f["https_url"] for f in listing["files"])]


def fetch_range(url: str, start: int, size: int) -> int:
    """Read ``size`` bytes from ``start`` with one Range request and return the number of bytes received."""
    req = urllib.request.Request(url, headers={"User-Agent": "cmsopen", "Range": f"bytes={start}-{start + size - 1}"})
    got = 0
    with urllib.request.urlopen(req, timeout=60) as resp:
        if resp.status != 206:
            raise RuntimeError(f"server ignored the Range request (status {resp.status})")
        while block := resp.read(1 << 20):
            got += len(block)
    return got


def measure(urls: list[str], n: int, size: int, offset: int) -> tuple[int, float]:
    """``n`` concurrent streams, one per development file, each reading ``size`` bytes at ``offset``."""
    t = time.perf_counter()
    with ThreadPoolExecutor(n) as pool:
        got = sum(pool.map(lambda u: fetch_range(u, offset, size), urls[:n]))
    return got, time.perf_counter() - t


def main(argv: list[str] | None = None) -> int:
    """Measure and print the table and the decision."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mb", type=int, default=50, help="megabytes per stream (default 50)")
    parser.add_argument("--streams", type=int, nargs="+", default=[1, 2, 3, 4])
    args = parser.parse_args(argv)
    urls = development_urls()
    size = args.mb * 1_000_000
    rates = {}
    print(f"{'streams':>7} {'bytes':>13} {'seconds':>8} {'MB/s':>7} {'x 1 stream':>10}")
    for k, n in enumerate(args.streams):
        got, secs = measure(urls, n, size, offset=(k + 1) * size)  # a fresh range for every stream count
        rates[n] = got / secs / 1e6
        ratio = rates[n] / rates[args.streams[0]]
        print(f"{n:>7} {got:>13,} {secs:>8.1f} {rates[n]:>7.2f} {ratio:>10.2f}", flush=True)
    if 1 in rates and 4 in rates:
        ratio = rates[4] / rates[1]
        verdict = "parallel downloads (4 streams)" if ratio >= DECISION_RATIO else "sequential downloads"
        print(f"decision: 4 streams / 1 stream = {ratio:.2f} (rule: >= {DECISION_RATIO}) -> {verdict}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
