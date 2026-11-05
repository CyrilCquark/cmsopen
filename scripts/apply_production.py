"""The one command after the production run: write every protected, results-bearing file, then check them.

Reads results/production.json, docs/figures/ and the run's saved outputs in build/production/, and writes README.md,
README_PYPI.md, DATA.md (the record facts), docs/ (the MkDocs pages), CITATION.cff, .zenodo.json, notebooks/,
results/production_extras.json and the application assets outside the repository. It does not commit.

Refuses, and writes nothing, unless:

1. results/production.json exists and passes the schema check (scripts/production_schema.py);
2. it is real: not marked as a dry run, its registry hash equals dev/registry.sha256 and the registry, and its commit
   is an ancestor of HEAD. Dry-run data are accepted only with --dry-run-data inside a marked temporary test copy
   (scripts/.production_test_copy holding that copy's own path); every generated file then says DRY-RUN DATA;
3. every figure it lists is in docs/figures/, and the fit captions there state this file's peak positions and models
   (so stale figures from development are not published under production numbers);
4. no template holds a typed number (scripts/release_lib.py, lint_template).

After writing it runs scripts/check_readme_numbers.py, scripts/check_release_metadata.py, the audit of numbers,
mkdocs build --strict and the notebooks, then prints the list of files it changed. Rerunning is byte-identical.
The address in templates/release_metadata.json goes into CITATION.cff only with --include-email; .zenodo.json has no
field for it.

Usage:
    python scripts/apply_production.py --rehearse  # all of it in a throwaway copy; this tree is not touched
    python scripts/apply_production.py [--application-dir DIR] [--self-checks-only] [--include-email]
    python scripts/apply_production.py --check     # write nothing; fail if a generated file differs
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "examples"))
import make_application_assets  # noqa: E402, I001
from build_production_notebooks import notebooks  # noqa: E402
from generate_release_files import build_values, not_met, text_outputs  # noqa: E402
from production_extras import RESULT_FILE, load_or_derive  # noqa: E402
from production_schema import validate  # noqa: E402
from release_lib import NumberAudit, audit_numbers, lint_template  # noqa: E402
from render_results import is_dry_run  # noqa: E402

TEST_COPY_MARKER = HERE / ".production_test_copy"
PRODUCTION = REPO / "results" / "production.json"


def is_test_copy() -> bool:
    """True only in a temporary test copy: the marker holds this repository's own resolved path."""
    return TEST_COPY_MARKER.is_file() and TEST_COPY_MARKER.read_text().strip() == str(REPO.resolve())


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True)


def refusal(data: Any, *, dry_run_data: bool) -> str | None:
    """Why this production file must not be applied, or None."""
    errors = validate(data)
    if errors:
        return "results/production.json fails the schema check:\n  " + "\n  ".join(errors[:20])
    registry = REPO / "results" / "production_files.json"
    actual = hashlib.sha256(registry.read_bytes()).hexdigest()
    recorded = (REPO / "dev" / "registry.sha256").read_text().split()[0]
    real = (
        not is_dry_run(data)
        and data["registry_sha256"] == recorded == actual
        and _git("merge-base", "--is-ancestor", data["git_head"], "HEAD").returncode == 0
    )
    if not real:
        if not dry_run_data:
            return (
                "results/production.json is not the production result: it is marked as a dry run, or its registry "
                "hash differs from dev/registry.sha256, or its commit is not an ancestor of HEAD"
            )
        if not is_test_copy():
            return "--dry-run-data is accepted only inside a marked temporary test copy"
    return _figure_problem(data)


def _figure_problem(data: dict[str, Any]) -> str | None:
    missing = [f for f in data["figures"] if not (REPO / f).is_file() or (REPO / f).stat().st_size == 0]
    if missing:
        return f"figures missing from docs/figures/: {', '.join(missing)}"
    for name, caption, digits in (("Z_mumu", "z_peak_fit_caption.md", 3), ("Jpsi_mumu", "jpsi_peak_fit_caption.md", 5)):
        result = data["channels"][name]["result"]
        path = REPO / "docs" / "figures" / caption
        text = path.read_text() if path.exists() else ""
        peak = f"{result['peak_position_gev']:.{digits}f}"
        if peak not in text:
            return (
                f"docs/figures/{caption} does not state the peak {peak} GeV of results/production.json: "
                "the figures do not belong to this production file"
            )
    return None


def template_problems() -> list[str]:
    """Numbers typed by hand in the templates, as 'file: token'."""
    out = []
    for path in sorted((REPO / "templates").rglob("*.md")):
        text = path.read_text()
        if path.parent.name == "notebooks":
            text = "\n".join(p for i, p in enumerate(text.split("```")) if not i % 2)  # only the text cells
        out += [f"{path.relative_to(REPO)}: {token}" for token in lint_template(text)]
    return out


def all_outputs(data: dict[str, Any], include_email: bool = False) -> dict[str, bytes]:
    """Relative path -> content of every generated file inside the repository."""
    return {**text_outputs(REPO, data, include_email), **notebooks(REPO, build_values(REPO, data))}


def _strings(extras: dict[str, Any]) -> list[str]:
    return [value for row in extras["rows"] for value in row.values()]


def audit_problems(data: dict[str, Any], outputs: dict[str, bytes]) -> list[str]:
    """Numbers in generated text that do not trace to results/production.json, as 'file: token'."""
    total = sum(int(f["size_bytes"]) for f in data["files"])
    # beyond the file: its total size, the citation format's version, and the table of registry benchmarks
    extras = load_or_derive(REPO, data)
    audit = NumberAudit(data, extra=(total, round(total / 1e9, 2), "1.2.0", *_strings(extras)))
    problems = []
    for name, content in outputs.items():
        if name.endswith((".png", ".pdf")) or name in ("DATA.md", RESULT_FILE):  # portal facts; the source table itself
            continue
        text = content.decode()
        if name.endswith(".ipynb"):
            text = "\n".join("".join(c["source"]) for c in json.loads(text)["cells"] if c["cell_type"] == "markdown")
        problems += [f"{name}: {token}" for token in audit_numbers(text, audit)]
    return problems


def run_check(*command: str) -> bool:
    """Run one check from the repository root and print its output."""
    out = subprocess.run(command, cwd=REPO, capture_output=True, text=True)
    print(out.stdout.strip())
    if out.returncode != 0 and out.stderr.strip():  # a kernel's start-up messages on stderr are not news otherwise
        print(out.stderr.strip())
    return out.returncode == 0


def docs_build_failure() -> str | None:
    """Why mkdocs build --strict failed, or None. A missing docs extra is a failure, never a silent skip."""
    if importlib.util.find_spec("mkdocs") is None or importlib.util.find_spec("mkdocstrings") is None:
        return 'mkdocs is not installed: pip install -e ".[dev,docs]" (or pass --skip-docs-build in a test)'
    with tempfile.TemporaryDirectory() as site:
        mkdocs = subprocess.run(
            [sys.executable, "-m", "mkdocs", "build", "--strict", "--quiet", "--site-dir", site],
            cwd=REPO,
            capture_output=True,
            text=True,
        )
    return None if mkdocs.returncode == 0 else mkdocs.stderr[-2000:]


def rehearse(args: argparse.Namespace) -> int:
    """The full apply step in a throwaway copy of this tree; print the checks and what it would change here."""
    flags = [
        ("--dry-run-data", args.dry_run_data),
        ("--self-checks-only", args.self_checks_only),
        ("--include-email", args.include_email),
        ("--skip-docs-build", args.skip_docs_build),
    ]
    real_application = args.application_dir or make_application_assets.DEFAULT_OUTDIR
    environment = {**os.environ, "GIT_OPTIONAL_LOCKS": "0", "PYTHONDONTWRITEBYTECODE": "1"}
    with tempfile.TemporaryDirectory(prefix="cmsopen-rehearse-") as tmp:
        copy, application = Path(tmp) / "repo", Path(tmp) / "application"
        subprocess.run(["git", "clone", "-q", "--no-hardlinks", str(REPO), str(copy)], check=True, env=environment)
        files = _git("ls-files", "-co", "--exclude-standard").stdout.splitlines()
        for rel in files:  # the tree as it is, with uncommitted production outputs
            if (REPO / rel).is_file():
                (copy / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(REPO / rel, copy / rel)
            else:
                (copy / rel).unlink(missing_ok=True)
        for summary in (REPO / "build" / "production").glob("*/run1/summary.json"):
            target = copy / summary.relative_to(REPO)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(summary, target)
        if is_test_copy():  # dry-run data stay acceptable in the copy of a marked copy, and nowhere else
            with open(copy / ".git" / "info" / "exclude", "a") as exclude:
                exclude.write("scripts/.production_test_copy\n")
            (copy / "scripts" / ".production_test_copy").write_text(str(copy.resolve()) + "\n")
        command = [sys.executable, str(copy / "scripts" / "apply_production.py"), "--application-dir", str(application)]
        command += [flag for flag, chosen in flags if chosen]
        print("== rehearsal in a throwaway copy; this tree is not changed")
        result = subprocess.run(command, cwd=copy, capture_output=True, text=True, env=environment)
        stdout = result.stdout.replace(str(application), "<application directory>")
        print(stdout.strip())
        if result.stderr.strip() and result.returncode != 0:
            print(result.stderr.strip()[-2000:])
        assets = sorted(p.relative_to(application).as_posix() for p in application.rglob("*") if p.is_file())
        different = [
            a
            for a in assets
            if not (real_application / a).exists()
            or (real_application / a).read_bytes() != (application / a).read_bytes()
        ]
        if result.returncode == 0:
            print(f"== it would change {len(different)} of {len(assets)} files in {real_application}")
            print("REHEARSAL PASSED: nothing was changed; now run the same command without --rehearse")
        else:
            print(f"REHEARSAL FAILED (exit {result.returncode}): nothing was changed; do not run the real apply")
    return result.returncode


def write_outputs(outputs: dict[str, bytes]) -> list[str]:
    """Write the files whose content differs; return those paths."""
    changed = []
    for name, content in outputs.items():
        path = REPO / name
        if not path.exists() or path.read_bytes() != content:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            changed.append(name)
    return changed


def main(argv: list[str] | None = None) -> int:
    """Refuse, or generate and check; see the module docstring. Exit 0 only if every check passed."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--application-dir",
        type=Path,
        default=None,
        help=f"where the application assets go (default {make_application_assets.DEFAULT_OUTDIR})",
    )
    parser.add_argument(
        "--self-checks-only",
        action="store_true",
        help="run only the notebooks' self-check cells, not the whole notebooks",
    )
    parser.add_argument("--dry-run-data", action="store_true", help="accept dry-run data in a marked test copy")
    parser.add_argument("--check", action="store_true", help="write nothing; fail if a generated file differs")
    parser.add_argument(
        "--rehearse", action="store_true", help="the whole step in a throwaway copy; touches nothing here"
    )
    parser.add_argument("--include-email", action="store_true", help="put the author's email address in CITATION.cff")
    parser.add_argument("--skip-docs-build", action="store_true", help="for tests without the docs extra")
    args = parser.parse_args(argv)

    if args.rehearse:
        return rehearse(args)
    if not PRODUCTION.exists():
        print("REFUSED: results/production.json does not exist (only the production run creates it)")
        return 2
    try:
        data = json.loads(PRODUCTION.read_text())
    except json.JSONDecodeError as exc:
        print(f"REFUSED: results/production.json is not valid JSON: {exc}")
        return 2
    reason = refusal(data, dry_run_data=args.dry_run_data or args.check)
    if reason:
        print(f"REFUSED: {reason}")
        return 2
    typed = template_problems()
    if typed:
        print("REFUSED: numbers typed by hand in the templates (use a placeholder):\n  " + "\n  ".join(typed))
        return 2
    if is_dry_run(data) and args.application_dir is None and not args.check:
        print("REFUSED: dry-run data never go to the default application directory; pass --application-dir")
        return 2

    citation = REPO / "CITATION.cff"
    has_email = args.check and citation.exists() and "    email:" in citation.read_text()
    outputs = all_outputs(data, args.include_email or has_email)
    if args.check:
        different = [n for n, c in outputs.items() if not (REPO / n).exists() or (REPO / n).read_bytes() != c]
        for name in different:
            print(f"FAIL: {name} differs from what results/production.json generates")
        if not different:
            print(f"OK: {len(outputs)} generated files are byte-identical to what results/production.json generates")
        return 1 if different else 0

    changed = write_outputs(outputs)
    application_dir = args.application_dir or make_application_assets.DEFAULT_OUTDIR
    assets = make_application_assets.outputs(REPO, data)
    changed_assets = make_application_assets.write(REPO, data, application_dir)

    print("== checks")
    python = sys.executable
    ok = run_check(python, str(HERE / "check_readme_numbers.py"))
    ok = run_check(python, str(HERE / "check_release_metadata.py")) and ok
    ok = run_check(python, str(HERE / "check_blinding.py")) and ok
    unaudited = audit_problems(data, {**outputs, **{f"application/{k}": v for k, v in assets.items()}})
    print(
        "OK: every number traces to results/production.json"
        if not unaudited
        else "FAIL: numbers that do not trace to results/production.json:\n  " + "\n  ".join(unaudited)
    )
    ok = ok and not unaudited
    if args.skip_docs_build:
        print("SKIPPED: mkdocs build --strict (--skip-docs-build)")
    else:
        failure = docs_build_failure()
        print("OK: mkdocs build --strict" if failure is None else f"FAIL: mkdocs build --strict\n{failure}")
        ok = ok and failure is None
    notebook_args = ["--self-checks-only"] if args.self_checks_only else []
    ok = run_check(python, str(HERE / "check_notebooks.py"), *notebook_args) and ok

    print(f"== changed in the repository ({len(changed)} files; nothing is committed)")
    for name in sorted(changed):
        print(f"  {name}")
    print(f"== changed in {application_dir} ({len(changed_assets)} files)")
    for name in sorted(changed_assets):
        print(f"  {name}")
    missed = not_met(data)
    print("== benchmarks not met, reported as not met: " + (", ".join(missed) if missed else "none"))
    print(
        "== benchmark registry: if a verified result beats a benchmark, dev/targets.md is updated by hand; see "
        "dev/post_production_runbook.md"
    )
    shutil.rmtree(REPO / "site", ignore_errors=True)
    print("APPLY COMPLETE" if ok else "APPLY FAILED: see the FAIL lines; the files are written but not committed")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
