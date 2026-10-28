"""Tests for cmsopen.datasets: a local HTTP server on a thread stands in for the portal (no network)."""

import http.server
import re
import subprocess
import sys
import threading
import zlib
from pathlib import Path

import pytest

import cmsopen
from cmsopen.datasets import DEV_ADLER32, DEV_FILENAME, DEV_SIZE, DEV_URL, DownloadError, adler32_of, fetch_example_data

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
