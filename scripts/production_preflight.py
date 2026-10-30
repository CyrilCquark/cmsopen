"""Production preflight: every condition for the single production run, one PASS/FAIL line each.

Never prints a production file name (the registry is read in memory; only
counts, sizes and hosts are printed). Checks:

1. the git working tree is clean; HEAD is recorded;
2. dev/registry.sha256 matches results/production_files.json;
3. no production file exists in the repository (with ``--allow-downloaded``:
   only in the download directory data/production/, where an interrupted
   download is resumed; such files are downloaded, not opened);
4. the "Model freeze" section exists in dev/model_choice.md and its commit is
   an ancestor of HEAD;
5. the docs-freeze check (since the freeze commit) and the blinding check pass;
6. the single-run guard: results/production.json and the run lock
   results/production_run.lock do not exist;
7. free disk space is at least twice the registered download volume;
8. the data server is reachable (host only);
9. the full test suite and the quality gates passed at HEAD: a record
   build/gates/<HEAD>.json written by ``scripts/run_gates.py`` (``--run-gates``
   runs them now);
10. the environment (Python, platform, package versions) and its SHA-256.

Usage:
    python scripts/production_preflight.py [--allow-downloaded] [--run-gates] [--no-network]

Exit 0 if every check passes, 1 otherwise.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from importlib import metadata
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
REGISTRY = Path("results") / "production_files.json"
HASH_FILE = Path("dev") / "registry.sha256"
PRODUCTION_JSON = Path("results") / "production.json"
LOCK = Path("results") / "production_run.lock"
DOWNLOAD_DIR = Path("data") / "production"
GATES_DIR = Path("build") / "gates"
PACKAGES = ("cmsopen", "numpy", "awkward", "uproot", "scipy", "matplotlib", "hist", "particle", "vector")


@dataclass
class Preflight:
    """The outcome of every check, the recorded HEAD and the environment."""

    lines: list[tuple[str, bool, str]] = field(default_factory=list)
    head: str = ""
    freeze_commit: str = ""
    environment: dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        """True if every check passed."""
        return all(ok for _, ok, _ in self.lines)

    def add(self, name: str, ok: bool, detail: str = "") -> bool:
        """Record and print one check."""
        self.lines.append((name, ok, detail))
        print(f"{'PASS' if ok else 'FAIL'}: {name}" + (f" ({detail})" if detail else ""), flush=True)
        return ok


def git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run git in ``repo``."""
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True)


def load_registry(repo: Path) -> dict[str, Any]:
    """The production registry (kept in memory; its file names are never printed)."""
    return json.loads((repo / REGISTRY).read_text())


def selected(registry: dict[str, Any]) -> list[dict[str, Any]]:
    """The registered production files in registry order (record by record, then by j)."""
    return [{**e, "record_id": r["record_id"], "run_period": r["run_period"]}
            for r in registry["records"] for e in sorted(r["selected"], key=lambda e: e["j"])]


def environment() -> dict[str, Any]:
    """Python, platform and package versions, with the SHA-256 of their canonical JSON."""
    env: dict[str, Any] = {
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "packages": {p: _version(p) for p in PACKAGES},
    }
    env["sha256"] = hashlib.sha256(json.dumps(env, sort_keys=True).encode()).hexdigest()
    return env


def _version(package: str) -> str:
    try:
        return metadata.version(package)
    except metadata.PackageNotFoundError:
        return "not installed"


def run_preflight(repo: Path = REPO, *, allow_downloaded: bool = False, run_gates: bool = False,
                  network: bool = True) -> Preflight:
    """Run every check on the repository ``repo`` and print PASS/FAIL lines."""
    pf = Preflight()
    status = git(repo, "status", "--porcelain")
    pf.head = git(repo, "rev-parse", "HEAD").stdout.strip()
    dirty = [line for line in status.stdout.splitlines() if line.strip()]
    pf.add("git working tree is clean", status.returncode == 0 and not dirty,
           f"HEAD {pf.head[:12]}" + (f"; {len(dirty)} changed or untracked paths" if dirty else ""))

    data = (repo / REGISTRY).read_bytes() if (repo / REGISTRY).exists() else b""
    recorded = (repo / HASH_FILE).read_text().split()[0] if (repo / HASH_FILE).exists() else ""
    pf.add("dev/registry.sha256 matches results/production_files.json",
           bool(data) and hashlib.sha256(data).hexdigest() == recorded, f"sha256 {recorded[:16]}...")
    files = selected(json.loads(data)) if data else []
    names = {e["filename"] for e in files}

    found = [p for p in repo.rglob("*.root") if p.name in names and ".git" not in p.parts]
    in_download = [p for p in found if p.parent == repo / DOWNLOAD_DIR]
    elsewhere = [p for p in found if p.parent != repo / DOWNLOAD_DIR]
    if allow_downloaded:
        pf.add("no production file outside the download directory", not elsewhere,
               f"{len(in_download)} of {len(files)} in {DOWNLOAD_DIR}/, {len(elsewhere)} elsewhere (names not printed)")
    else:
        pf.add("none of the production files exists locally", not found,
               f"{len(found)} of {len(files)} present (names not printed)")

    text = (repo / "dev" / "model_choice.md").read_text() if (repo / "dev" / "model_choice.md").exists() else ""
    m = re.search(r"^## Model freeze.*?Frozen at commit `([0-9a-f]{40})`", text, flags=re.M | re.S)
    pf.freeze_commit = m.group(1) if m else ""
    ancestor = bool(m) and git(repo, "merge-base", "--is-ancestor", pf.freeze_commit, "HEAD").returncode == 0
    pf.add("model freeze recorded and its commit is an ancestor of HEAD", ancestor,
           f"freeze {pf.freeze_commit[:12]}" if m else "no 'Model freeze' section with a commit")

    if pf.freeze_commit:
        docs = subprocess.run([sys.executable, str(repo / "scripts" / "check_docs_frozen.py"), "--since",
                               pf.freeze_commit], cwd=repo, capture_output=True, text=True)
        pf.add("docs-freeze check since the freeze commit", docs.returncode == 0, docs.stdout.strip()[:100])
    else:
        pf.add("docs-freeze check since the freeze commit", False, "no freeze commit")
    blind = subprocess.run([sys.executable, str(repo / "scripts" / "check_blinding.py")], cwd=repo,
                           capture_output=True, text=True)
    pf.add("blinding check", blind.returncode == 0, blind.stdout.strip().replace("\n", "; ")[:120])

    pf.add("single-run guard: results/production.json and the run lock do not exist",
           not (repo / PRODUCTION_JSON).exists() and not (repo / LOCK).exists(),
           ", ".join(str(p) for p in (PRODUCTION_JSON, LOCK) if (repo / p).exists()) or "neither exists")

    volume = sum(int(e["size_bytes"]) for e in files)
    have = sum(p.stat().st_size for p in in_download)
    free = shutil.disk_usage(repo).free
    pf.add("free disk is at least twice the expected download", free >= 2 * volume,
           f"download {volume / 1e9:.2f} GB ({have / 1e9:.2f} GB already present), free {free / 1e9:.1f} GB, "
           f"need {2 * volume / 1e9:.2f} GB")

    hosts = sorted({urllib.parse.urlsplit(e["https_url"]).netloc or "local files" for e in files})
    if not network:
        pf.add("data server reachable", True, "not checked (--no-network)")
    else:
        reachable = []
        for e in files[:1] + files[-1:]:
            url = urllib.parse.urlsplit(e["https_url"])
            if url.scheme == "file":
                reachable.append(Path(urllib.request.url2pathname(url.path)).parent.is_dir())
                continue
            try:
                req = urllib.request.Request(f"{url.scheme}://{url.netloc}/", method="HEAD")
                with urllib.request.urlopen(req, timeout=20) as resp:
                    reachable.append(resp.status < 500)
            except Exception:  # any network error: not reachable
                reachable.append(False)
        pf.add("data server reachable", all(reachable) and bool(reachable), f"host(s): {', '.join(hosts)}")

    if run_gates:
        subprocess.run([sys.executable, str(repo / "scripts" / "run_gates.py")], cwd=repo)
    record = repo / GATES_DIR / f"{pf.head}.json"
    gates = json.loads(record.read_text()) if record.exists() else {}
    ok = gates.get("head") == pf.head and gates.get("pytest_rc") == 0 and gates.get("quality_rc") == 0
    pf.add("full test suite and quality gates passed at HEAD", ok,
           f"record {GATES_DIR}/{pf.head[:12]}.json: pytest {gates.get('summary', '?')}, quality rc "
           f"{gates.get('quality_rc', '?')}" if gates else "no record for HEAD (run scripts/run_gates.py)")

    pf.environment = environment()
    pf.add("environment captured", True, f"Python {pf.environment['python']}, sha256 "
                                         f"{pf.environment['sha256'][:16]}...")
    return pf


def main(argv: list[str] | None = None) -> int:
    """Run the preflight on this repository."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--allow-downloaded", action="store_true",
                        help="accept production files in data/production/ (a resumed download)")
    parser.add_argument("--run-gates", action="store_true", help="run the full suite and quality gates first")
    parser.add_argument("--no-network", action="store_true", help="skip the reachability check")
    args = parser.parse_args(argv)
    pf = run_preflight(REPO, allow_downloaded=args.allow_downloaded, run_gates=args.run_gates,
                       network=not args.no_network)
    print("PREFLIGHT PASSED" if pf.passed else "PREFLIGHT FAILED")
    return 0 if pf.passed else 1


if __name__ == "__main__":
    sys.exit(main())
