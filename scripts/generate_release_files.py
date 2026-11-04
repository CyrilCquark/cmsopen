"""Generate every protected, results-bearing text file from results/production.json and the templates.

:func:`text_outputs` returns relative path -> bytes for README.md, docs/*.md, CITATION.cff and .zenodo.json. Nothing is
written here: scripts/apply_production.py writes and checks them. :func:`build_values` is the only place where a value
of the production file becomes text, and the templates in templates/ may hold numbers only through its placeholders
(scripts/release_lib.py, lint_template). Generation is deterministic: no clock, no random state.

Standard library only.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from release_lib import render
from render_results import (
    CHANNEL_LABELS,
    channel_digits,
    dry_run_banner,
    fmt,
    headline_table,
    is_dry_run,
    met_text,
    render_results_block,
    targets_table,
)

KEYS = {"z": "Z_mumu", "jpsi": "Jpsi_mumu"}
DOC_PAGES = ("physics", "user_guide", "api", "validation", "reproducibility", "changelog")


def sha256(path: Path) -> str:
    """SHA-256 of a file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def package_version(repo: Path) -> str:
    """cmsopen.__version__, read from the source file of this repository, without importing an installed copy."""
    m = re.search(r'^__version__ = "([^"]+)"', (repo / "src" / "cmsopen" / "__init__.py").read_text(), flags=re.M)
    if not m:
        raise ValueError("no __version__ in src/cmsopen/__init__.py")
    return m.group(1)


def parse_data_md(repo: Path) -> dict[str, str]:
    """The citation text of DATA.md ("How to cite") and the facts of its record table; nothing is typed elsewhere."""
    text = (repo / "DATA.md").read_text()
    section = text.split("## How to cite", 1)[1]
    quote = " ".join(line[1:].strip() for line in section.splitlines() if line.startswith(">"))
    doi = re.search(r"\*\*(10\.[^*\s]+)\*\*", section)
    rows = dict(re.findall(r"^\| ([^|]+?) \| (.+?) \|$", text, flags=re.M))
    if not quote or not doi:
        raise ValueError("DATA.md: no citation quote or DOI under 'How to cite'")
    return {
        "quote": quote,
        "doi": doi.group(1),
        "record_title": rows["Title"],
        "authors": rows["Authors"],
        "publisher": rows["Publisher"],
        "published": rows["Published"],
    }


def registry_records(repo: Path) -> list[dict[str, Any]]:
    """Record id, run period, title and URL of each registered record. File names are deliberately not read out."""
    registry = json.loads((repo / "results" / "production_files.json").read_text())
    return [{k: r.get(k) for k in ("record_id", "run_period", "title", "record_url")} for r in registry["records"]]


def _cell(text: Any) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def _table(header: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(_cell(c) for c in row) + " |" for row in rows]
    return "\n".join(lines)


def _opt(value: Any, spec: str) -> str:
    return "" if value is None else format(value, spec)


def _validation_table(channel: dict[str, Any]) -> str:
    d = channel_digits(channel)
    rows = []
    for e in channel["validation"]["entries"]:
        fitted = e["status"] == "fitted"
        rows.append(
            [
                e["study"],
                e["label"],
                f"{e['n_pairs']:,}",
                f"{e['position']:.{d}f} ± {e['error']:.{d}f}" if fitted else "",
                _opt(e.get("chi2_ndf"), ".3f") if fitted else "",
                _opt(e.get("delta_sigma"), "+.2f"),
                _opt(e.get("scale_factor"), ".2f"),
                _opt(e.get("delta_sigma_scaled"), "+.2f"),
                e.get("status_text") or e["status"],
            ]
        )
    return _table(["study", "entry", "pairs", "position [GeV]", "χ²/ndf", "d/s", "S", "d/s scaled", "status"], rows)


def _fit_choice_table(channel: dict[str, Any]) -> str:
    d = channel_digits(channel)
    s = channel["validation"]["systematics_summary"]
    rows = [
        [
            f"{r['fit_range'][0]:g}-{r['fit_range'][1]:g}",
            f"{r['bin_width']:g}",
            f"{r['mass']:.{d}f} ± {r['mass_error']:.{d}f}",
            fmt(r["chi2_ndf"], ".3f"),
            fmt(r["p_value"], ".3g"),
        ]
        for r in s["fit_choice_rows"]
    ]
    return _table(["fit range [GeV]", "bin width [GeV]", "peak [GeV]", "χ²/ndf", "p-value"], rows)


def _fit_choice_failed(channel: dict[str, Any]) -> str:
    failed = channel["validation"]["systematics_summary"]["fit_choice_failed"]
    if not failed:
        return "Every fit choice converged."
    return "Fit choices that did not give a fit:\n\n" + "\n".join(f"- {f['reason']}" for f in failed)


def _per_file_table(channel: dict[str, Any]) -> str:
    d = channel_digits(channel)
    rows = [
        [
            str(f["index"]),
            str(f["record_id"]),
            f["run_period"],
            f"{f['n_pairs_in_fit_range']:,}",
            f"{f['peak_position_gev']:.{d}f} ± {f['stat_error_gev']:.{d}f}",
            f"{f['chi2_ndf']:.3f}",
            f["status"],
        ]
        if f["status"] == "fitted"
        else [str(f["index"]), str(f["record_id"]), f["run_period"], "", "", "", f["status"]]
        for f in channel["per_file"]
    ]
    return _table(["index", "record", "period", "pairs", "peak [GeV]", "χ²/ndf", "status"], rows)


def _cutflow_table(channel: dict[str, Any]) -> str:
    rows = [[c["cut"], f"{c['n_events']:,}", f"{c['n_particles']:,}"] for c in channel["cutflow"]]
    return _table(["step", "events", "muons"], rows)


def _warnings(channel: dict[str, Any]) -> str:
    return "\n".join(f"- {w}" for w in channel["warnings"]) or "None."


def _systematics_table(data: dict[str, Any]) -> str:
    channels = (data["channels"]["Z_mumu"], data["channels"]["Jpsi_mumu"])

    def summary(c: dict[str, Any]) -> dict[str, Any]:
        return c["validation"]["systematics_summary"]

    def row(label: str, key: str) -> list[str]:
        return [label, *(f"{fmt(summary(c)[key], f'.{channel_digits(c)}f')} GeV" for c in channels)]

    def background(c: dict[str, Any]) -> str:
        variation = summary(c)["background_variation"] or {}
        difference = fmt(variation.get("difference"), f"+.{channel_digits(c)}f")
        return f"{difference} GeV ({variation.get('model', 'no fit')})"

    def largest(c: dict[str, Any]) -> str:
        raw = fmt(summary(c)["category_max_delta_sigma"], ".2f")
        return f"{raw} raw, {fmt(summary(c)['category_max_delta_sigma_scaled'], '.2f')} scaled"

    rows = [
        row("Spread over barrel/endcap categories", "category_spread"),
        ["Largest category deviation, in σ", *(largest(c) for c in channels)],
        row("Largest μ⁺ minus μ⁻ difference", "charge_max_difference"),
        row("Spread over working points", "working_point_spread"),
        row("Spread over signal models", "model_spread"),
        row("Fit-choice standard deviation", "fit_choice_std"),
        ["Other background shape", *(background(c) for c in channels)],
    ]
    return _table(["study (observed)", CHANNEL_LABELS["Z_mumu"], CHANNEL_LABELS["Jpsi_mumu"]], rows)


def _periods_table(data: dict[str, Any]) -> str:
    rows = []
    for name in ("Z_mumu", "Jpsi_mumu"):
        c = data["channels"][name]
        spec = f".{channel_digits(c)}f"
        for key, label in (
            ("peak_position_gev_difference_2012B_minus_2012C", "peak"),
            ("resolution_gev_difference_2012B_minus_2012C", "resolution"),
        ):
            if key in c["t6"]:
                v = c["t6"][key]
                value = fmt(v["value"], f"+{spec}")
                rows.append([f"{CHANNEL_LABELS[name]} {label}", f"{value} ± {fmt(v['error'], spec)} GeV",
                             f"{fmt(v['in_sigma'], '+.2f')} σ"])
    return _table(["difference (observed)", "value", "in σ"], rows)


def _method_table(data: dict[str, Any]) -> str:
    rows = []
    for name, cut_text in (("Z_mumu", "tight ID and PF isolation"), ("Jpsi_mumu", "soft ID")):
        r = data["channels"][name]["result"]
        rows.append(
            [CHANNEL_LABELS[name], r["model"], f"{r['fit_range_gev'][0]:g}-{r['fit_range_gev'][1]:g} GeV", cut_text]
        )
    return _table(["channel", "model", "fit range", "muon quality"], rows)


def _channel_values(prefix: str, c: dict[str, Any], data: dict[str, Any]) -> dict[str, str]:
    r, d = c["result"], channel_digits(c)
    alt = c.get("alternate_fit") or {}
    values = {
        "peak": f"{r['peak_position_gev']:.{d}f}",
        "stat": f"{r['stat_error_gev']:.{d}f}",
        "stat_scaled": f"{r['stat_error_scaled_gev']:.{d}f}",
        "scale": f"{r['scale_factor']:.3f}",
        "res": f"{r['resolution_gev']:.{d}f}",
        "res_err": f"{r['resolution_error_gev']:.{d}f}",
        "chi2": f"{r['chi2']:.1f}",
        "ndf": str(r["ndf"]),
        "chi2_ndf": f"{r['chi2_ndf']:.3f}",
        "p_value": fmt(r["p_value"], ".3g"),
        "pdg": f"{r['pdg_mass_gev']:.4f}",
        "offset": f"{r['offset_from_pdg_gev']:+.{d}f}",
        "spread": fmt(c["fit_choice_spread_gev"], f".{d}f"),
        "pairs": f"{r['n_pairs_in_fit_range']:,}",
        "events": f"{r['n_events']:,}",
        "model": r["model"],
        "fit_lo": f"{r['fit_range_gev'][0]:g}",
        "fit_hi": f"{r['fit_range_gev'][1]:g}",
        "alt_model": alt.get("model", "failed"),
        "alt_peak": f"{alt['peak_position_gev']:.{d}f}" if alt else "",
        "alt_chi2_ndf": f"{alt['chi2_ndf']:.3f}" if alt else "",
        "relation": "below" if r["offset_from_pdg_gev"] < 0 else "above",
        "t2_status": "met" if c["t2"]["met"] else "not met",
        "min_pairs": f"{c['validation']['min_pairs']:,}",
        "validation_table": _validation_table(c),
        "fit_choice_table": _fit_choice_table(c),
        "fit_choice_failed": _fit_choice_failed(c),
        "per_file_table": _per_file_table(c),
        "cutflow_table": _cutflow_table(c),
        "warnings": _warnings(c),
    }
    return {f"{prefix}.{k}": v for k, v in values.items()}


def not_met(data: dict[str, Any]) -> list[str]:
    """Readable names of the benchmarks the observed values did not meet."""
    out = []
    for name, target in sorted(data["targets"].items()):
        met = target["met"]
        if isinstance(met, dict):
            out += [
                f"{name} ({CHANNEL_LABELS[k].split(' ')[0]})" for k, v in sorted(met.items(), reverse=True) if not v
            ]
        elif not met:
            out.append(name)
    return out


def _limitations(data: dict[str, Any]) -> str:
    z, j = data["channels"]["Z_mumu"], data["channels"]["Jpsi_mumu"]
    items = [
        "**Not mass measurements.** No muon momentum-scale calibration is applied. The observed offsets from the PDG "
        f"masses ({z['result']['offset_from_pdg_gev']:+.4f} GeV for the Z, {j['result']['offset_from_pdg_gev']:+.5f} "
        "GeV for the J/ψ) are studied and reported, not corrected.",
        "**Statistical errors only.** The quoted errors are statistical. The studies under validation show how the "
        "peak moves with analysis choices, but they are not combined into a systematic uncertainty. "
        "The observed spread over detector categories is "
        f"{fmt(z['validation']['systematics_summary']['category_spread'], '.4f')} "
        f"GeV for the Z, against a statistical error of {z['result']['stat_error_gev']:.4f} GeV, and "
        f"{fmt(j['validation']['systematics_summary']['category_spread'], '.5f')} GeV for the J/ψ, against "
        f"{j['result']['stat_error_gev']:.5f} GeV.",
        "**The fit is a description.** The line shapes are physically motivated but simple, with no simulation of the "
        "detector. There are no efficiency or acceptance corrections, so no cross-section or absolute rate is derived.",
        f"**A subset of the data.** The sample is {data['sample']['n_files']} files of two run periods of the "
        "DoubleMuParked datasets, not the full records.",
        "**Unofficial.** This work is independent, has had no review by the CMS Collaboration, and is not a CMS "
        "result.",
    ]
    missed = not_met(data)
    if missed:
        items.insert(
            0,
            f"**Benchmarks not met in this run:** {', '.join(missed)}. They stay reported as not met; "
            "nothing was refitted or tuned afterwards.",
        )
    warnings = [
        f"{CHANNEL_LABELS[n].split(' ')[0]}: {w}"
        for n in ("Z_mumu", "Jpsi_mumu")
        for w in data["channels"][n]["warnings"]
    ]
    if warnings:
        items.append("**Analysis warnings recorded by the run:** " + " ".join(f"({w})" for w in warnings))
    return "\n".join(f"- {i}" for i in items)


def build_values(repo: Path, data: dict[str, Any]) -> dict[str, str]:
    """Every placeholder a template can use."""
    meta = json.loads((repo / "templates" / "release_metadata.json").read_text())
    cite = parse_data_md(repo)
    env = data["environment"]
    total = sum(int(f["size_bytes"]) for f in data["files"])
    t2, t4 = data["channels"]["Z_mumu"]["t2"], data["targets"]["T4"]
    records = registry_records(repo)
    packages = sorted(env["packages"].items())
    missed = not_met(data)
    values = {
        "dry_banner": dry_run_banner(data),
        "dry_prefix": "DRY-RUN DATA, NOT RESULTS. " if is_dry_run(data) else "",
        "results_block": render_results_block(data),
        "version": package_version(repo),
        "repo_url": meta["repository"],
        "n_files": str(data["sample"]["n_files"]),
        "n_events": f"{data['sample']['n_events']:,}",
        "total_bytes": f"{total:,}",
        "total_gb": f"{total / 1e9:.2f}",
        "bench_n_files": str(t4["benchmark"]["n_files"]),
        "t4_status": met_text(t4["met"]),
        "bench_chi2": f"{t2['benchmark']:.1f}",
        "not_met_sentence": (
            "**Benchmarks not met in this run: " + ", ".join(missed) + ".** They are reported as not "
            "met, with the measured values; nothing was refitted or tuned afterwards."
        )
        if missed
        else "All benchmarks in the table were met in this run.",
        "targets_table": targets_table(data),
        "headline_table": headline_table(data),
        "method_table": _method_table(data),
        "systematics_table": _systematics_table(data),
        "periods_table": _periods_table(data),
        "limitations": _limitations(data),
        "git_head": data["git_head"],
        "git_head_short": data["git_head"][:12],
        "first_head": data["first_head"],
        "freeze_commit": data["freeze_commit"],
        "freeze_short": data["freeze_commit"][:12],
        "n_attempts": str(data["attempts"]["n"]),
        "n_failed_attempts": str(len(data["attempts"]["failed"])),
        "n_code_fixes": str(len(data["attempts"]["code_fixes"])),
        "gates_summary": _cell(data["gates"]["summary"]),
        "production_sha": sha256(repo / "results" / "production.json"),
        "registry_sha": data["registry_sha256"],
        "config_sha": data["analysis_config_sha256"],
        "env_sha": env["sha256"],
        "python": env["python"],
        "implementation": str(env.get("implementation", "")),
        "platform": env["platform"],
        "pdg_source": data["pdg"]["source"],
        "packages_inline": "Packages: " + ", ".join(f"{k} {v}" for k, v in packages) + ".",
        "packages_table": _table(["package", "version"], [[k, str(v)] for k, v in packages]),
        "figure_hashes": "\n".join(f"| `{f}` | `{sha256(repo / f)}` |" for f in sorted(data["figures"])),
        "files_table": _table(
            ["index", "record", "period", "bytes", "checksum"],
            [
                [
                    str(f.get("index", "")),
                    str(f["record_id"]),
                    f["run_period"],
                    f"{f['size_bytes']:,}",
                    f"`{f['checksum']}`",
                ]
                for f in data["files"]
            ],
        ),
        "data_section": "\n".join(
            f"- [{r['title']}]({r['record_url']}), {sum(1 for f in data['files'] if f['record_id'] == r['record_id'])} "
            f"of its files (CMS proton-proton collisions at 8 TeV)."
            for r in records
        ),
        "data_citation_quote": cite["quote"],
        "data_citation_note": (
            f"[DATA.md](DATA.md) records the DOI of the parent dataset of record 31129: "
            f"[{cite['doi']}](https://doi.org/{cite['doi']})."
        ),
    }
    for prefix, name in KEYS.items():
        values.update(_channel_values(prefix, data["channels"][name], data))
    values["abstract"] = render((repo / "templates" / "citation_abstract.md").read_text(), values).strip()
    return values


def docs_home(readme: str, repo_url: str) -> str:
    """The README as the site's home page: the same text, with its links rewritten to work from docs/."""
    text = readme
    text = text.replace("](docs/figures/", "](figures/").replace("](docs/", "](")

    def outside(match: re.Match[str]) -> str:
        return f"]({repo_url}/blob/main/{match.group(1)})"

    return re.sub(r"\]\(((?:notebooks|results|examples)/[^)]+|DATA\.md|LICENSE|CITATION\.cff)\)", outside, text)


def _yaml(text: str) -> str:
    return json.dumps(text, ensure_ascii=False)


def citation_cff(repo: Path, values: dict[str, str]) -> str:
    """CITATION.cff. An ORCID that is still "TODO" is a comment, because the schema rejects it as a field value."""
    meta = json.loads((repo / "templates" / "release_metadata.json").read_text())
    cite = parse_data_md(repo)
    orcid = meta["orcid"]
    orcid_line = (
        '    # orcid: "https://orcid.org/TODO"  # TODO: add your ORCID in templates/release_metadata.json'
        if orcid == "TODO"
        else f"    orcid: {_yaml(orcid)}"
    )
    lines = [
        "# Generated by scripts/apply_production.py from results/production.json; do not edit by hand.",
        "cff-version: 1.2.0",
        'message: "If you use this software, please cite it using these metadata, and cite the CMS open data used."',
        "type: software",
        f"title: {_yaml(meta['title'])}",
        f"version: {_yaml(values['version'])}",
        "authors:",
        f"  - given-names: {_yaml(meta['given_names'])}",
        f"    family-names: {_yaml(meta['family_names'])}",
        f"    email: {_yaml(meta['email'])}",
        orcid_line,
        f"abstract: {_yaml(values['abstract'])}",
        "keywords:",
        *(f"  - {_yaml(k)}" for k in meta["keywords"]),
        f"license: {meta['license']}",
        f"repository-code: {_yaml(meta['repository'])}",
        *([f"doi: {_yaml(meta['doi'])}"] if meta.get("doi") else []),
        "references:",
    ]
    for record in registry_records(repo):
        lines += [
            "  - type: data",
            f"    title: {_yaml(record['title'])}",
            "    authors:",
            f"      - name: {_yaml(cite['authors'])}",
            f"    publisher:\n      name: {_yaml(cite['publisher'])}",
            f"    url: {_yaml(record['record_url'])}",
            '    license: "CC0-1.0"',
        ]
        if record["record_id"] == 31129:
            lines += [
                f"    doi: {_yaml(cite['doi'])}",
                f"    notes: {_yaml('DOI of the parent AOD dataset. ' + cite['quote'])}",
            ]
        else:
            lines += ['    notes: "TODO: DATA.md records no DOI for this record; check the portal before release."']
    return "\n".join(lines) + "\n"


def zenodo_json(repo: Path, values: dict[str, str]) -> str:
    """.zenodo.json, with the same metadata as CITATION.cff."""
    meta = json.loads((repo / "templates" / "release_metadata.json").read_text())
    cite = parse_data_md(repo)
    creator = {"name": f"{meta['family_names']}, {meta['given_names']}", "orcid": meta["orcid"]}
    record = {
        "title": meta["title"],
        "version": values["version"],
        "upload_type": "software",
        "creators": [creator],
        "description": values["abstract"],
        "keywords": meta["keywords"],
        "license": "MIT",
        "access_right": "open",
        "notes": "CMS open data citation: " + cite["quote"],
        "related_identifiers": [
            {"identifier": meta["repository"], "relation": "isSupplementTo", "scheme": "url"},
            {"identifier": cite["doi"], "relation": "references", "scheme": "doi"},
        ],
    }
    return json.dumps(record, indent=2, ensure_ascii=False) + "\n"


def text_outputs(repo: Path, data: dict[str, Any]) -> dict[str, bytes]:
    """Relative path -> content of every generated text file except the notebooks."""
    values = build_values(repo, data)
    templates = repo / "templates"
    readme = _tidy(render((templates / "README.md").read_text(), values))
    out = {"README.md": readme, "docs/index.md": _tidy(docs_home(readme, values["repo_url"]))}
    for page in DOC_PAGES:
        out[f"docs/{page}.md"] = _tidy(render((templates / "docs" / f"{page}.md").read_text(), values))
    out["CITATION.cff"] = citation_cff(repo, values)
    out[".zenodo.json"] = zenodo_json(repo, values)
    return {k: v.encode() for k, v in out.items()}


def _tidy(text: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"
