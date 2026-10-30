"""Build the sdist and wheel, check their metadata and contents, and install the wheel into a fresh venv.

Checks (one PASS/FAIL line each; exit 1 if any fails):

- ``python -m build`` makes one sdist and one wheel; ``twine check`` passes;
- the sizes of both archives are printed;
- LICENSE is in both; ``cmsopen/py.typed`` is in the wheel;
- the wheel holds only the ``cmsopen`` package and its ``.dist-info``;
- neither archive contains data or internals: no ``*.root``, nothing from
  ``data/``, ``build/``, ``dev/``, ``results/``, ``examples/``, ``docs/`` or
  ``tests/`` (the tests need the repository; MANIFEST.in prunes them);
- no file in either archive mentions a production file of the registry
  (results/production_files.json; compared in memory, only a count is
  printed);
- the wheel's metadata version equals ``cmsopen.__version__`` in the source;
- installed into a fresh venv and run from another directory, ``cmsopen
  --help`` works, ``import cmsopen`` imports from that venv, and
  ``cmsopen.__version__`` equals the metadata version.

``--offline`` builds without build isolation and installs the wheel without
its dependencies into a venv that sees this interpreter's site-packages (so
no network is needed); otherwise the build backend and the dependencies come
from the package index.

Usage:
    python scripts/check_package.py [--offline] [--keep]
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import subprocess
import sys
import sysconfig
import tarfile
import tempfile
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FORBIDDEN_DIRS = ("data/", "build/", "dev/", "results/", "examples/", "docs/")


class Report:
    """PASS/FAIL lines and the failures."""

    def __init__(self) -> None:
        self.failures: list[str] = []

    def check(self, name: str, ok: bool, detail: str = "") -> bool:
        """Print one PASS or FAIL line, remember a failure, and return ``ok``."""
        print(f"{'PASS' if ok else 'FAIL'}: {name}" + (f" ({detail})" if detail else ""))
        if not ok:
            self.failures.append(name)
        return ok


def run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run a command in ``cwd`` and capture its output (without colour codes); a missing program is exit 127."""
    try:
        return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, env={**os.environ, "NO_COLOR": "1"})
    except FileNotFoundError as exc:
        return subprocess.CompletedProcess(cmd, 127, "", f"not found: {exc.filename}")


def source_version() -> str:
    """``__version__`` from src/cmsopen/__init__.py, read without importing the package."""
    tree = ast.parse((REPO / "src" / "cmsopen" / "__init__.py").read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "__version__" for t in node.targets):
            return str(ast.literal_eval(node.value))
    raise RuntimeError("no __version__ in src/cmsopen/__init__.py")


def production_stems() -> list[bytes]:
    """The registry's production file stems, kept in memory only (never printed)."""
    registry = json.loads((REPO / "results" / "production_files.json").read_text())
    return [e["filename"].removesuffix(".root").encode() for r in registry["records"] for e in r["selected"]]


def archive_members(path: Path) -> dict[str, bytes]:
    """Every regular file of a wheel or sdist with its content, names relative to the archive root."""
    out: dict[str, bytes] = {}
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as z:
            for name in z.namelist():
                if not name.endswith("/"):
                    out[name] = z.read(name)
    else:
        with tarfile.open(path) as t:
            for m in t.getmembers():
                if m.isfile():
                    f = t.extractfile(m)
                    out[m.name.split("/", 1)[1] if "/" in m.name else m.name] = f.read() if f else b""
    return out


def main(argv: list[str] | None = None) -> int:
    """Run every check and return the exit status."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--offline", action="store_true", help="no network: no build isolation, no dependency install")
    parser.add_argument("--keep", action="store_true", help="keep the temporary directory")
    args = parser.parse_args(argv)
    report = Report()
    tmp = Path(tempfile.mkdtemp(prefix="cmsopen-package-"))
    dist = tmp / "dist"

    build = [sys.executable, "-m", "build", "--sdist", "--wheel", "--outdir", str(dist)]
    result = run(build + (["--no-isolation"] if args.offline else []) + [str(REPO)], cwd=tmp)
    wheels, sdists = sorted(dist.glob("*.whl")), sorted(dist.glob("*.tar.gz"))
    if not report.check("python -m build makes one sdist and one wheel",
                        result.returncode == 0 and len(wheels) == 1 and len(sdists) == 1,
                        f"exit {result.returncode}" + ("" if result.returncode == 0 else f": {result.stderr[-400:]}")):
        return 1
    wheel, sdist = wheels[0], sdists[0]
    print(f"     {sdist.name}: {sdist.stat().st_size:,} bytes; {wheel.name}: {wheel.stat().st_size:,} bytes")
    twine = run([sys.executable, "-m", "twine", "check", "--strict", str(sdist), str(wheel)], cwd=tmp)
    report.check("twine check --strict", twine.returncode == 0,
                 f"{twine.stdout.count('PASSED')} of 2 archives PASSED" if twine.returncode == 0
                 else twine.stdout[-300:])

    stems = production_stems()
    for label, archive in (("wheel", wheel), ("sdist", sdist)):
        members = archive_members(archive)
        names = sorted(members)
        report.check(f"{label}: LICENSE included", any(n.endswith("LICENSE") for n in names),
                     ", ".join(n for n in names if n.endswith("LICENSE")))
        bad = [n for n in names if n.endswith(".root") or n.startswith("tests/")
               or any(n.startswith(d) or f"/{d}" in n for d in FORBIDDEN_DIRS)]
        report.check(f"{label}: no data files or repository internals", not bad, ", ".join(bad[:5]) or
                     f"{len(names)} files")
        leaks = sum(1 for content in members.values() for s in stems if s in content or s.lower() in content.lower())
        report.check(f"{label}: no production file referenced", leaks == 0, f"{leaks} references (names not printed)")
        if label == "wheel":
            outside = [n for n in names if not (n.startswith("cmsopen/") or ".dist-info/" in n)]
            report.check("wheel: only the cmsopen package and its metadata", not outside, ", ".join(outside[:5]))
            report.check("wheel: cmsopen/py.typed included", "cmsopen/py.typed" in names)
            meta = next(members[n] for n in names if n.endswith(".dist-info/METADATA")).decode()
            version = next(line.split(":", 1)[1].strip() for line in meta.splitlines() if line.startswith("Version:"))
            report.check("wheel metadata version equals cmsopen.__version__ in the source",
                         version == source_version(), f"metadata {version}, source {source_version()}")
            entry = next((members[n].decode() for n in names if n.endswith(".dist-info/entry_points.txt")), "")
            report.check("wheel declares the cmsopen console script", "cmsopen = cmsopen.__main__:main" in entry,
                         entry.strip().replace("\n", "; ") or "no entry_points.txt")

    venv = tmp / "venv"
    run([sys.executable, "-m", "venv", str(venv)], cwd=tmp)
    vpy = venv / "bin" / "python"
    if args.offline:  # the dependencies come from this interpreter's environment
        purelib = run([str(vpy), "-c", "import sysconfig; print(sysconfig.get_paths()['purelib'])"], cwd=tmp)
        Path(purelib.stdout.strip(), "_cmsopen_check_deps.pth").write_text(sysconfig.get_paths()["purelib"] + "\n")
        install = run([str(vpy), "-m", "pip", "install", "--no-deps", "--no-index", str(wheel)], cwd=tmp)
    else:
        install = run([str(vpy), "-m", "pip", "install", str(wheel)], cwd=tmp)
    report.check("the wheel installs into a fresh venv", install.returncode == 0,
                 "" if install.returncode == 0 else install.stderr[-300:])
    elsewhere = tmp / "elsewhere"
    elsewhere.mkdir()
    cli = run([str(venv / "bin" / "cmsopen"), "--help"], cwd=elsewhere)
    report.check("cmsopen --help works from another directory", cli.returncode == 0 and "analyze" in cli.stdout,
                 f"exit {cli.returncode}" + ("" if cli.returncode == 0 else f": {cli.stderr[-200:]}"))
    probe = run([str(vpy), "-c", "import cmsopen, importlib.metadata as m; "
                 "print(cmsopen.__version__); print(m.version('cmsopen')); print(cmsopen.__file__)"], cwd=elsewhere)
    lines = probe.stdout.split()
    ok = probe.returncode == 0 and len(lines) == 3
    report.check("import cmsopen from the fresh venv's site-packages",
                 ok and str(venv) in lines[2] and "/src/" not in lines[2], lines[2] if ok else probe.stderr[-200:])
    report.check("cmsopen.__version__ equals the installed metadata version", ok and lines[0] == lines[1],
                 f"__version__ {lines[0]}, metadata {lines[1]}" if ok else "import failed")

    if not args.keep:
        import shutil

        shutil.rmtree(tmp, ignore_errors=True)
    if report.failures:
        print(f"FAIL: {len(report.failures)} package check(s) failed: {', '.join(report.failures)}")
        return 1
    print("OK: package checks pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
