"""Tests for cmsopen.datasets: a local HTTP server on a thread stands in for the portal (no network)."""

import http.server
import json
import re
import subprocess
import sys
import threading
import zlib
from pathlib import Path

import pytest

import cmsopen
from cmsopen import datasets
from cmsopen.datasets import (
    DEV_ADLER32,
    DEV_FILENAME,
    DEV_SIZE,
    DEV_URL,
    DownloadError,
    adler32_of,
    fetch_example_data,
    fetch_many,
    fetch_verified,
)

REPO = Path(__file__).resolve().parents[1]
PAYLOAD = bytes((i * 7 + i // 251) % 256 for i in range(3 * (1 << 20) + 12345))  # ~3 MB, spans several blocks
PAYLOAD_ADLER = f"{zlib.adler32(PAYLOAD) & 0xFFFFFFFF:08x}"


class _Handler(http.server.BaseHTTPRequestHandler):
    """Serves PAYLOAD at /data/sample.root; honours Range unless the server says not to."""

    def do_GET(self):
        self.server.requests.append({"path": self.path, "range": self.headers.get("Range")})
        if self.path != "/data/sample.root":
            self.send_error(404)
            return
        body, status = PAYLOAD, 200
        rng = self.headers.get("Range")
        if rng and self.server.honour_range:
            start = int(re.fullmatch(r"bytes=(\d+)-", rng).group(1))
            body, status = PAYLOAD[start:], 206
        self.send_response(status)
        self.send_header("Content-Length", str(len(body)))
        if status == 206:
            self.send_header("Content-Range", f"bytes {len(PAYLOAD) - len(body)}-{len(PAYLOAD) - 1}/{len(PAYLOAD)}")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture
def server():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    srv.requests, srv.honour_range = [], True
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield srv, f"http://127.0.0.1:{srv.server_address[1]}/data/sample.root"
    srv.shutdown()
    srv.server_close()


def fetch(dest, url, **kw):
    return fetch_example_data(dest, url=url, size=len(PAYLOAD), adler32=PAYLOAD_ADLER, progress=False, **kw)


def test_constants_match_data_md():
    """DATA.md is protected: this test only reads it."""
    text = (REPO / "DATA.md").read_text()
    size = int(re.search(r"\| Size \| ([\d,]+) bytes \|", text).group(1).replace(",", ""))
    checksum = re.search(r"\| Checksum \| `adler32:([0-9a-f]{8})` \|", text).group(1)
    https = re.search(r"\| HTTPS \| (https://\S+) \|", text).group(1)
    filename = re.search(r"\| Filename \| `([^`]+)` \|", text).group(1)
    assert (DEV_SIZE, DEV_ADLER32, DEV_URL, DEV_FILENAME) == (size, checksum, https, filename)
    assert DEV_URL.endswith("/" + DEV_FILENAME)


def test_full_download(tmp_path, server, capsys):
    srv, url = server
    path = fetch_example_data(tmp_path / "data", url=url, size=len(PAYLOAD), adler32=PAYLOAD_ADLER)
    assert path == tmp_path / "data" / "sample.root" and path.read_bytes() == PAYLOAD
    assert srv.requests == [{"path": "/data/sample.root", "range": None}]
    err = capsys.readouterr().err
    assert "100%" in err and "Verified" in err
    assert adler32_of(path) == PAYLOAD_ADLER


def test_resume_after_truncation_uses_range(tmp_path, server):
    srv, url = server
    path = fetch(tmp_path, url)
    keep = len(PAYLOAD) // 3 + 17
    path.write_bytes(PAYLOAD[:keep])
    srv.requests.clear()
    assert fetch(tmp_path, url).read_bytes() == PAYLOAD
    assert srv.requests == [{"path": "/data/sample.root", "range": f"bytes={keep}-"}]


def test_server_ignoring_range_restarts_cleanly(tmp_path, server):
    srv, url = server
    srv.honour_range = False
    (tmp_path / "sample.root").write_bytes(PAYLOAD[:1000])
    assert fetch(tmp_path, url).read_bytes() == PAYLOAD


def test_already_present_and_verified_makes_no_request(tmp_path, server):
    srv, url = server
    fetch(tmp_path, url)
    srv.requests.clear()
    assert fetch(tmp_path, url).read_bytes() == PAYLOAD
    assert srv.requests == []


def test_size_mismatch(tmp_path, server):
    _, url = server
    with pytest.raises(DownloadError, match="size"):
        fetch_example_data(tmp_path, url=url, size=len(PAYLOAD) + 1, adler32=PAYLOAD_ADLER, progress=False)


def test_checksum_mismatch(tmp_path, server):
    _, url = server
    with pytest.raises(DownloadError, match="adler32"):
        fetch_example_data(tmp_path, url=url, size=len(PAYLOAD), adler32="00000001", progress=False)


def test_no_overwrite_without_force_then_force_replaces(tmp_path, server):
    srv, url = server
    bad = bytearray(PAYLOAD)
    bad[12345] ^= 0xFF  # same size, wrong content
    target = tmp_path / "sample.root"
    target.write_bytes(bytes(bad))
    with pytest.raises(DownloadError, match="fails verification.*not overwriting"):
        fetch(tmp_path, url)
    assert target.read_bytes() == bytes(bad) and srv.requests == []  # untouched, nothing downloaded
    too_big = tmp_path / "big" / "sample.root"
    too_big.parent.mkdir()
    too_big.write_bytes(PAYLOAD + b"extra")
    with pytest.raises(DownloadError, match="not overwriting"):
        fetch(too_big.parent, url)
    assert fetch(tmp_path, url, force=True).read_bytes() == PAYLOAD
    assert fetch(too_big.parent, url, force=True).read_bytes() == PAYLOAD


def test_network_errors_are_download_errors(tmp_path, server):
    _, url = server
    with pytest.raises(DownloadError, match="HTTP 404"):
        fetch(tmp_path, url.replace("sample.root", "missing.root"))
    with pytest.raises(DownloadError, match="failed"):
        fetch(tmp_path, "http://127.0.0.1:9/nothing.root", timeout=2)


def test_cli_fetch(tmp_path, server):
    _, url = server
    base = [sys.executable, "-m", "cmsopen", "fetch", "--dest", str(tmp_path / "d"), "--url", url,
            "--size", str(len(PAYLOAD)), "--adler32", PAYLOAD_ADLER]
    out = subprocess.run(base, capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == str(tmp_path / "d" / "sample.root")
    assert (tmp_path / "d" / "sample.root").read_bytes() == PAYLOAD
    (tmp_path / "d" / "sample.root").write_bytes(PAYLOAD[:-1] + b"\x00")  # same size, wrong content
    bad = subprocess.run(base, capture_output=True, text=True)
    assert bad.returncode == 1 and bad.stderr.startswith("error: ") and "Traceback" not in bad.stderr
    forced = subprocess.run([*base, "--force"], capture_output=True, text=True)
    assert forced.returncode == 0 and (tmp_path / "d" / "sample.root").read_bytes() == PAYLOAD


def test_export():
    assert "fetch_example_data" in cmsopen.__all__ and cmsopen.fetch_example_data is fetch_example_data


# -- fetch_verified and fetch_many (production downloads: re-verified, re-fetched when bad, concurrent) -------------

FILES = {f"/many/f{k}.root": bytes((i * (k + 3) + k) % 256 for i in range((1 << 20) + 1000 * k)) for k in range(5)}


class _ManyHandler(http.server.BaseHTTPRequestHandler):
    """Serves FILES with Range support (bytes=a- and bytes=a-b); the first ``fail_first`` requests get HTTP 503."""

    def do_GET(self):
        with self.server.lock:
            self.server.requests.append({"path": self.path, "range": self.headers.get("Range")})
            failing = self.server.fail_first > 0
            self.server.fail_first -= failing
        if failing:
            self.send_error(503)
            return
        data = FILES[self.path]
        body, status = data, 200
        if rng := self.headers.get("Range"):
            a, b = re.fullmatch(r"bytes=(\d+)-(\d*)", rng).groups()
            body, status = data[int(a): int(b) + 1 if b else None], 206
        self.send_response(status)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        for i in range(0, len(body), 1 << 16):  # slowly, so concurrent downloads overlap
            self.wfile.write(body[i: i + (1 << 16)])
            threading.Event().wait(0.002)

    def log_message(self, *args):
        pass


@pytest.fixture
def many():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _ManyHandler)
    srv.requests, srv.fail_first, srv.lock = [], 0, threading.Lock()
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    entries = [{"url": base + path, "size": len(data), "adler32": f"{zlib.adler32(data) & 0xFFFFFFFF:08x}"}
               for path, data in FILES.items()]
    yield srv, entries
    srv.shutdown()
    srv.server_close()


def test_fetch_verified_resumes_a_truncated_file_with_a_range_request(many, tmp_path):
    srv, entries = many
    data = FILES["/many/f1.root"]
    (tmp_path / "f1.root").write_bytes(data[:300_000])
    path = fetch_verified(tmp_path, url=entries[1]["url"], size=entries[1]["size"], adler32=entries[1]["adler32"])
    assert path.read_bytes() == data and srv.requests == [{"path": "/many/f1.root", "range": "bytes=300000-"}]


@pytest.mark.parametrize("bad", ["same_size", "truncated", "too_large"])
def test_fetch_verified_never_trusts_a_corrupted_copy(many, tmp_path, bad):
    srv, entries = many
    data = FILES["/many/f2.root"]
    corrupt = bytes([data[0] ^ 0xFF]) + data[1:]
    (tmp_path / "f2.root").write_bytes({"same_size": corrupt, "truncated": corrupt[:500_000],
                                        "too_large": data + b"x"}[bad])
    path = fetch_verified(tmp_path, url=entries[2]["url"], size=entries[2]["size"], adler32=entries[2]["adler32"],
                          backoff=0.01)
    assert path.read_bytes() == data
    if bad == "truncated":  # resumed first, then found corrupted and fetched again from the first byte
        assert [r["range"] for r in srv.requests] == ["bytes=500000-", None]
    else:
        assert [r["range"] for r in srv.requests] == [None]


def test_fetch_verified_retries_a_network_error_with_backoff(many, tmp_path):
    srv, entries = many
    srv.fail_first = 2
    path = fetch_verified(tmp_path, url=entries[0]["url"], size=entries[0]["size"], adler32=entries[0]["adler32"],
                          retries=2, backoff=0.01)
    assert path.read_bytes() == FILES["/many/f0.root"] and len(srv.requests) == 3
    srv.fail_first, srv.requests[:] = 5, []
    with pytest.raises(DownloadError, match="HTTP 503"):
        fetch_verified(tmp_path / "x", url=entries[0]["url"], size=entries[0]["size"],
                       adler32=entries[0]["adler32"], retries=1, backoff=0.01)
    assert len(srv.requests) == 2


def test_fetch_many_downloads_concurrently_in_order_and_resumes(many, tmp_path, monkeypatch):
    srv, entries = many
    (tmp_path / "f3.root").write_bytes(FILES["/many/f3.root"][:100_000])  # an interrupted earlier call
    real, lock, active = datasets.fetch_example_data, threading.Lock(), [0, 0]  # [now, peak] downloads in progress

    def counting(*args, **kw):
        with lock:
            active[0] += 1
            active[1] = max(active)
        try:
            return real(*args, **kw)
        finally:
            with lock:
                active[0] -= 1

    monkeypatch.setattr(datasets, "fetch_example_data", counting)
    done = []
    paths = fetch_many(entries, tmp_path, workers=4, on_done=lambda k, p: done.append(k))
    assert [p.name for p in paths] == [f"f{k}.root" for k in range(5)] and sorted(done) == list(range(5))
    assert all(p.read_bytes() == FILES[f"/many/{p.name}"] for p in paths)
    assert active[1] == 4  # four downloads at once, never more
    assert {"path": "/many/f3.root", "range": "bytes=100000-"} in srv.requests
    srv.requests[:] = []
    assert fetch_many(entries, tmp_path, workers=2) == paths and srv.requests == []  # all present and verified


def test_fetch_many_limits_and_failures(many, tmp_path):
    srv, entries = many
    for workers in (0, 5, True):
        with pytest.raises(ValueError, match="between 1 and 4"):
            fetch_many(entries, tmp_path, workers=workers)
    bad = [*entries[:2], {**entries[2], "adler32": "00000001"}]
    with pytest.raises(DownloadError, match="1 of 3 downloads failed; the first \\(entry 2\\)"):
        fetch_many(bad, tmp_path, workers=3, retries=1, backoff=0.01)
    assert (tmp_path / "f0.root").exists() and (tmp_path / "f1.root").exists() and not (tmp_path / "f2.root").exists()


def test_cli_fetch_listing_with_download_workers(many, tmp_path, capsys):
    """cmsopen fetch --listing: every file of a development-set-style listing, concurrently, resumable, verified."""
    from cmsopen.__main__ import main

    srv, entries = many
    listing = tmp_path / "listing.json"
    listing.write_text(json.dumps({"files": [{"https_url": e["url"], "size_bytes": e["size"],
                                              "checksum": f"adler32:{e['adler32']}"} for e in entries]}))
    (tmp_path / "out").mkdir()
    (tmp_path / "out" / "f4.root").write_bytes(FILES["/many/f4.root"][:5000])
    assert main(["fetch", "--listing", str(listing), "--dest", str(tmp_path / "out"), "--download-workers", "3"]) == 0
    printed = capsys.readouterr().out.split()
    assert [Path(p).name for p in printed] == [f"f{k}.root" for k in range(5)]
    assert all(Path(p).read_bytes() == FILES[f"/many/{Path(p).name}"] for p in printed)
    assert {"path": "/many/f4.root", "range": "bytes=5000-"} in srv.requests
    with pytest.raises(SystemExit):
        main(["fetch", "--listing", str(listing), "--download-workers", "5"])
    assert "invalid choice" in capsys.readouterr().err
    listing.write_text(json.dumps({"files": [{"https_url": entries[0]["url"]}]}))
    assert main(["fetch", "--listing", str(listing), "--dest", str(tmp_path / "x")]) == 1
    assert "error: listing entry without 'size_bytes'" in capsys.readouterr().err
