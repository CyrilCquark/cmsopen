"""Schema check of results/production.json as written by scripts/production_run.py.

scripts/apply_production.py refuses to generate anything from a file that fails this check. It lists every field a
generator reads, so a missing field is reported here, by path, and not as a KeyError half way through writing the
README. Standard library only.

Usage:
    python scripts/production_schema.py [results/production.json]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

CHANNELS = ("Z_mumu", "Jpsi_mumu")
TARGETS = ("T1", "T2", "T3", "T4", "T5", "T6", "T7")

TOP = {
    "schema_version": int,
    "git_head": str,
    "first_head": str,
    "freeze_commit": str,
    "registry_sha256": str,
    "analysis_config_sha256": str,
    "sample": dict,
    "fit": dict,
    "pdg": dict,
    "environment": dict,
    "figures": list,
    "files": list,
    "attempts": dict,
    "gates": dict,
    "targets": dict,
    "channels": dict,
    "timing_s": dict,
}
SECTION = {
    "sample": ("n_files", "n_events", "n_pairs"),
    "fit": (
        "model",
        "fit_range_gev",
        "peak_position_gev",
        "stat_error_gev",
        "resolution_gev",
        "resolution_error_gev",
        "chi2",
        "ndf",
    ),
    "pdg": ("mass_gev", "source"),
    "environment": ("python", "platform", "sha256", "packages"),
    "attempts": ("n", "failed", "code_fixes"),
    "gates": ("head", "pytest_rc", "quality_rc", "summary"),
}
RESULT = (
    "model",
    "fit_range_gev",
    "peak_position_gev",
    "stat_error_gev",
    "stat_error_scaled_gev",
    "scale_factor",
    "resolution_gev",
    "resolution_error_gev",
    "chi2",
    "ndf",
    "chi2_ndf",
    "p_value",
    "pdg_mass_gev",
    "offset_from_pdg_gev",
    "n_events",
    "n_pairs_in_fit_range",
    "yields_reliable",
)
CHANNEL = (
    "result",
    "t1",
    "t2",
    "t6",
    "cutflow",
    "per_file",
    "validation",
    "warnings",
    "fit_choice_spread_gev",
    "n_files",
)
SYSTEMATICS = (
    "category_spread",
    "category_max_delta_sigma",
    "category_max_delta_sigma_scaled",
    "charge_max_difference",
    "charge_weighted_mean",
    "charge_weighted_mean_error",
    "working_point_spread",
    "model_spread",
    "fit_choice_std",
    "fit_choice_spread",
    "background_variation",
    "fit_choice_rows",
    "fit_choice_failed",
)
ENTRY = ("study", "label", "n_pairs", "status")


def _need(errors: list[str], obj: Any, path: str, keys: tuple[str, ...]) -> None:
    if not isinstance(obj, dict):
        errors.append(f"{path}: expected an object")
        return
    errors.extend(f"{path}.{k}: missing" for k in keys if k not in obj)


def validate(data: Any) -> list[str]:
    """Every problem found, by path; an empty list means the file follows the schema."""
    if not isinstance(data, dict):
        return ["top level: expected an object"]
    errors = [f"{k}: missing or not {t.__name__}" for k, t in TOP.items() if not isinstance(data.get(k), t)]
    if errors:
        return errors
    if data["schema_version"] != 1:
        errors.append(f"schema_version: {data['schema_version']!r}, expected 1")
    for section, keys in SECTION.items():
        _need(errors, data[section], section, keys)
    for name in TARGETS:
        _need(errors, data["targets"].get(name), f"targets.{name}", ("benchmark", "observed", "met"))
    for name in CHANNELS:
        channel = data["channels"].get(name)
        path = f"channels.{name}"
        _need(errors, channel, path, CHANNEL)
        if errors and errors[-1].startswith(f"{path}"):
            continue
        _need(errors, channel["result"], f"{path}.result", RESULT)
        _need(errors, channel["t2"], f"{path}.t2", ("benchmark", "met"))
        _need(errors, channel["validation"], f"{path}.validation", ("entries", "systematics_summary", "min_pairs"))
        if isinstance(channel["validation"], dict) and "entries" in channel["validation"]:
            _need(
                errors,
                channel["validation"].get("systematics_summary"),
                f"{path}.validation.systematics_summary",
                SYSTEMATICS,
            )
            for i, entry in enumerate(channel["validation"]["entries"]):
                _need(errors, entry, f"{path}.validation.entries[{i}]", ENTRY)
    if not data["figures"]:
        errors.append("figures: empty")
    for f in data["figures"]:
        if not isinstance(f, str) or not f.startswith("docs/figures/"):
            errors.append(f"figures: {f!r} is not under docs/figures/")
    if not data["files"]:
        errors.append("files: empty")
    for i, f in enumerate(data["files"]):
        _need(errors, f, f"files[{i}]", ("record_id", "run_period", "size_bytes", "checksum"))
    return errors


def main(argv: list[str] | None = None) -> int:
    """Print the problems of the file given (default results/production.json); exit 0 only if there are none."""
    args = sys.argv[1:] if argv is None else argv
    path = Path(args[0] if args else "results/production.json")
    if not path.exists():
        print(f"FAIL: {path} does not exist")
        return 1
    errors = validate(json.loads(path.read_text()))
    for error in errors:
        print(f"FAIL: {error}")
    if not errors:
        print(f"OK: {path} follows the schema")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
