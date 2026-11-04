"""Validate CITATION.cff and .zenodo.json: schema, version, licence, authors, and agreement with the package.

CITATION.cff is validated against the official Citation File Format 1.2.0 JSON schema, vendored in
templates/schemas/. (cffconvert itself pins jsonschema below 4, which breaks Jupyter in the same environment, so it is
not a dependency; it passed once in a throwaway environment.) With --release, a remaining TODO is a failure: use it
just before tagging.

Usage:
    python scripts/check_release_metadata.py [--release]

Exit 0 on OK, 1 on any FAIL.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import jsonschema
import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate_release_files import package_version, parse_data_md  # noqa: E402


def problems(repo: Path, release: bool = False) -> tuple[list[str], list[str]]:
    """(failures, warnings) for the metadata files of the repository ``repo``."""
    failures: list[str] = []
    warnings: list[str] = []
    cff_path, zen_path = repo / "CITATION.cff", repo / ".zenodo.json"
    for path in (cff_path, zen_path):
        if not path.exists():
            failures.append(f"{path.name} does not exist")
    if failures:
        return failures, warnings
    meta = json.loads((repo / "templates" / "release_metadata.json").read_text())
    cff_text = cff_path.read_text()
    cff = yaml.safe_load(cff_text)
    schema = json.loads((repo / "templates" / "schemas" / "citation_cff_1.2.0.json").read_text())
    for error in jsonschema.Draft7Validator(schema, format_checker=jsonschema.FormatChecker()).iter_errors(cff):
        failures.append(f"CITATION.cff schema: {'/'.join(map(str, error.path))}: {error.message[:150]}")
    zenodo = json.loads(zen_path.read_text())
    version = package_version(repo)
    if str(cff.get("version")) != version:
        failures.append(f"CITATION.cff version {cff.get('version')!r} differs from cmsopen.__version__ {version!r}")
    if zenodo.get("version") != version:
        failures.append(f".zenodo.json version {zenodo.get('version')!r} differs from cmsopen.__version__ {version!r}")
    if cff.get("license") != "MIT" or zenodo.get("license") != "MIT":
        failures.append("the licence is not MIT in both files")
    author = (cff.get("authors") or [{}])[0]
    if (author.get("given-names"), author.get("family-names")) != (meta["given_names"], meta["family_names"]):
        failures.append("CITATION.cff author differs from templates/release_metadata.json")
    if "email" in author and author["email"] != meta["email"]:  # absent unless --include-email was given
        failures.append("CITATION.cff email differs from templates/release_metadata.json")
    if cff.get("repository-code") != meta["repository"]:
        failures.append("CITATION.cff repository URL differs from templates/release_metadata.json")
    if zenodo.get("creators", [{}])[0].get("name") != f"{meta['family_names']}, {meta['given_names']}":
        failures.append(".zenodo.json creator differs from templates/release_metadata.json")
    if cff.get("abstract") != zenodo.get("description"):
        failures.append("the abstract of CITATION.cff differs from the description of .zenodo.json")
    cite = parse_data_md(repo)
    if cite["doi"] not in cff_text or cite["quote"] not in cff_text:
        failures.append("the CMS open data citation of DATA.md is not in CITATION.cff")
    if cite["quote"] not in zenodo.get("notes", ""):
        failures.append("the CMS open data citation of DATA.md is not in .zenodo.json")
    for name, text in (("CITATION.cff", cff_text), (".zenodo.json", zen_path.read_text())):
        for match in re.findall(r"TODO[^\n\"]*", text):
            (failures if release else warnings).append(f"{name}: {match.strip()[:90]}")
    return failures, warnings


def main(argv: list[str] | None = None) -> int:
    """Print OK or the failures; warnings (the open TODOs) do not fail unless --release is given."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--release", action="store_true", help="a remaining TODO is a failure")
    args = parser.parse_args(argv)
    failures, warnings = problems(REPO, args.release)
    for warning in warnings:
        print(f"TODO: {warning}")
    for failure in failures:
        print(f"FAIL: {failure}")
    if not failures:
        print("OK: CITATION.cff follows the CFF 1.2.0 schema; CITATION.cff, .zenodo.json and the package agree")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
