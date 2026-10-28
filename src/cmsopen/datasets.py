"""Download the development data file, so a fresh clone can reproduce the analysis.

CMS releases its collision data through the CERN Open Data portal
(opendata.cern.ch) under the CC0 waiver. This project develops its analysis
on one file of the Run 2012C DoubleMuParked dataset in the Run 1
NanoAOD-like format (record 31129); DATA.md documents it. That file is
about 1.1 GB and is never committed to the repository, so anyone who clones
the project fetches it with :func:`fetch_example_data` (or
``cmsopen fetch``) and then runs the analysis on exactly the same input.

The download uses only the Python standard library. It is resumable: an
interrupted download is continued with an HTTP Range request rather than
restarted. When it finishes, the file's size and its adler32 checksum (the
checksum the portal publishes for every file) are compared with the
recorded values, so a truncated or corrupted copy is never mistaken for the
real data.
"""

from __future__ import annotations

import sys
import urllib.error
import urllib.request
import zlib
from pathlib import Path
from typing import TextIO

__all__ = [
    "DEV_ADLER32",
    "DEV_FILENAME",
    "DEV_SIZE",
    "DEV_URL",
    "DownloadError",
    "adler32_of",
    "fetch_example_data",
]

DEV_FILENAME = "45F7AE81-7A79-4CB1-998E-7BD156490294.root"
"""The development file's name (DATA.md)."""
DEV_URL = (
    "https://opendata.cern.ch/eos/opendata/cms/derived-data/NanoAODRun1/01-Jul-22/"
    "Run2012C_DoubleMuParked/45F7AE81-7A79-4CB1-998E-7BD156490294.root"
)
"""HTTPS location of the development file on the CERN Open Data portal (DATA.md)."""
DEV_SIZE = 1_145_602_936
"""Size of the development file in bytes (DATA.md)."""
DEV_ADLER32 = "9f7301c5"
"""adler32 checksum of the development file, as published by the portal (DATA.md)."""

_BLOCK = 1 << 20  # 1 MiB


class DownloadError(RuntimeError):
    """The download failed, or the file on disk does not match the expected size or checksum."""


def adler32_of(path: str | Path) -> str:
    """The adler32 checksum of a file as 8 lowercase hex digits, read in 1 MiB blocks.

    adler32 is the fast checksum the CERN Open Data portal lists for each
    file. It detects corruption and truncation; it is not a cryptographic
    hash.
    """
    value = 1
    with open(path, "rb") as f:
        while block := f.read(_BLOCK):
            value = zlib.adler32(block, value)
    return f"{value & 0xFFFFFFFF:08x}"


def _verify(path: Path, size: int, adler32: str) -> str | None:
    """None if ``path`` has the expected size and checksum, else the reason it does not."""
    actual = path.stat().st_size
    if actual != size:
        return f"size {actual:,} bytes, expected {size:,}"
    checksum = adler32_of(path)
    if checksum != adler32.lower():
        return f"adler32 {checksum}, expected {adler32.lower()}"
    return None


def _report(out: TextIO | None, done: int, total: int, last: list[int]) -> None:
    if out is None:
        return
    percent = int(100 * done / total) if total else 100
    if percent != last[0]:
        last[0] = percent
        out.write(f"\r  {done / 1e6:,.1f} / {total / 1e6:,.1f} MB ({percent}%)")
        out.flush()


def fetch_example_data(
    dest: str | Path = "data",
    *,
    url: str | None = None,
    force: bool = False,
    size: int | None = None,
    adler32: str | None = None,
    filename: str | None = None,
    progress: bool = True,
    timeout: float = 60.0,
) -> Path:
    """Download the development data file into ``dest`` (resumable, verified) and return its path.

    Steps:

    1. If the file is already there with the right size and checksum, it is
       returned without any download.
    2. If a shorter file is there (an interrupted download), the rest is
       requested with an HTTP ``Range: bytes=<size>-`` header and appended.
       A server that ignores the Range header (status 200) is handled by
       starting again from the first byte.
    3. If the file is there but fails verification (right size with a wrong
       checksum, or too large), it is NOT overwritten unless ``force=True``;
       with ``force=True`` it is deleted and downloaded again.
    4. After the download the size and the adler32 checksum are checked.

    Parameters
    ----------
    dest : str or Path
        Directory to download into (created if needed).
    url : str, optional
        Source URL; default :data:`DEV_URL`.
    force : bool
        Replace an existing file that fails verification.
    size, adler32 : optional
        Expected size in bytes and adler32 (8 hex digits); default the
        development file's :data:`DEV_SIZE` and :data:`DEV_ADLER32`.
    filename : str, optional
        File name in ``dest``; default the last component of ``url``.
    progress : bool
        Print progress to stderr.
    timeout : float
        Network timeout in seconds.

    Raises
    ------
    DownloadError
        Network failure, an existing file that fails verification (without
        ``force``), or a downloaded file with the wrong size or checksum.
    """
    url = url or DEV_URL
    size = DEV_SIZE if size is None else int(size)
    adler32 = (DEV_ADLER32 if adler32 is None else adler32).lower()
    name = filename or url.rstrip("/").rsplit("/", 1)[-1]
    target = Path(dest) / name
    target.parent.mkdir(parents=True, exist_ok=True)
    out = sys.stderr if progress else None

    if target.exists():
        have = target.stat().st_size
        if have >= size:
            problem = _verify(target, size, adler32)
            if problem is None:
                if out:
                    out.write(f"{target} is already present and verified\n")
                return target
            if not force:
                raise DownloadError(
                    f"{target} exists but fails verification ({problem}); not overwriting it. "
                    "Pass force=True (cmsopen fetch --force) to replace it."
                )
            target.unlink()

    offset = target.stat().st_size if target.exists() else 0
    request = urllib.request.Request(url, headers={"User-Agent": "cmsopen"})
    if offset:
        request.add_header("Range", f"bytes={offset}-")
    if out:
        out.write(f"Downloading {url}\n  to {target}" + (f" (resuming at byte {offset:,})" if offset else "") + "\n")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = getattr(response, "status", 200)
            if offset and status != 206:
                offset = 0  # the server ignored the Range request: start again from the beginning
            mode = "ab" if offset else "wb"
            done, last = offset, [-1]
            with open(target, mode) as f:
                while block := response.read(_BLOCK):
                    f.write(block)
                    done += len(block)
                    _report(out, done, size, last)
    except urllib.error.HTTPError as exc:
        raise DownloadError(f"download of {url} failed: HTTP {exc.code} {exc.reason}") from None
    except (urllib.error.URLError, OSError) as exc:
        raise DownloadError(f"download of {url} failed: {exc}; run again to resume") from None
    if out:
        out.write("\n")
    problem = _verify(target, size, adler32)
    if problem is not None:
        raise DownloadError(f"downloaded {target} fails verification ({problem})")
    if out:
        out.write(f"Verified {target}: {size:,} bytes, adler32 {adler32}\n")
    return target
