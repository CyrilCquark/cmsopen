"""Every benchmark of the registry with an observed value, or "not derivable" with the reason.

Read-only: nothing is written and no data file is opened. It derives what results/production.json does not report from
the production run's saved outputs (build/production/<channel>/run1/summary.json, whose histogram it reads) and from the
record of the toy tests (dev/test_metrics.json). Those summaries list input files, so nothing is copied from them except
numbers: no file name reaches the output. scripts/apply_production.py keeps the output as
results/production_extras.json, because build/ is not in the repository.

The benchmarks are read from the table in dev/targets.md, so a registry change reaches the output by itself.

J/psi sideband signal-to-background, defined here before the production files were opened (dev/targets.md): in the
saved histogram of the Jpsi_mumu channel the signal window is 2.9-3.3 GeV, the benchmark's own window, and the
sidebands are the rest of the histogram, 2.6-2.9 and 3.3-3.6 GeV. B = sideband count x (window width / sideband width),
assuming a locally flat background; S = window count - B.

Usage:
    python scripts/production_extras.py     # prints the table
"""

from __future__ import annotations

import hashlib
import json
import re
import struct
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from render_results import dry_run_banner, observed_text  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
RESULT_FILE = "results/production_extras.json"
TEST_LABEL = "from the test suite, not production data"
WINDOW = (2.9, 3.3)
SIDEBANDS = ((2.6, 2.9), (3.3, 3.6))
_EDGE_TOLERANCE = 1e-9

# Thresholds in dev/targets.md's prose ("Existing self-check thresholds"), which has no table to read them from.
THRESHOLDS = (
    ("Same-sign pairs in 88-94 GeV (fraction of opposite-sign)", "< 10 %"),
    ("Fitted Z resolution", "0.5-4 GeV"),
    ("Z stability spread over fit choices", "< 0.5 GeV"),
    ("Z peak sanity window around the PDG mass (not a mass target)", "within 1.0 GeV"),
    ("Figure file size", "> 20 kB"),
    ("PNG size equal to figsize x 300 dpi", "exact"),
    ("Layout overlaps in the figures", "0"),
    ("Byte-identical regeneration of the figures", "exact"),
)


def registry_rows(repo: Path) -> list[tuple[str, str]]:
    """(metric, controlling benchmark) of each row of the registry table in dev/targets.md."""
    text = (repo / "dev" / "targets.md").read_text()
    rows = re.findall(r"^\| ([^|]+?) \| (?:higher|lower|window|exact|reported|none) \| ([^|]+?) \|", text, flags=re.M)
    if not rows:
        raise ValueError("dev/targets.md: no registry table")
    return rows


def _row(metric: str, benchmark: str, observed: str, status: str, source: str) -> dict[str, str]:
    return {"metric": metric, "benchmark": benchmark, "observed": observed, "status": status, "source": source}


def _no(metric: str, benchmark: str, reason: str) -> dict[str, str]:
    return _row(metric, benchmark, f"not derivable: {reason}", "not derivable", "")


def _met(ok: bool) -> str:
    return "met" if ok else "not met"


def load_summary(repo: Path, data: dict[str, Any], channel: str) -> tuple[dict[str, Any] | None, str]:
    """(saved summary, "") if it belongs to this production file; otherwise (None, the reason)."""
    path = repo / "build" / "production" / channel / "run1" / "summary.json"
    if not path.exists():
        return None, "the run's saved outputs are not present (build/production/, not in the repository)"
    summary = json.loads(path.read_text())
    saved, recorded = summary["fit"]["peak_position_gev"], data["channels"][channel]["result"]["peak_position_gev"]
    if abs(saved - recorded) > 1e-9:
        return None, "the saved outputs do not belong to this production file (a different peak position)"
    return summary, ""


def _count_between(histogram: dict[str, Any], low: float, high: float) -> int | None:
    """The histogram's count from low to high; None unless both limits are bin edges."""
    edges, counts = histogram["edges_gev"], histogram["counts"]
    index = [i for i, e in enumerate(edges) if abs(e - low) < _EDGE_TOLERANCE or abs(e - high) < _EDGE_TOLERANCE]
    if len(index) != 2:
        return None
    return int(round(sum(counts[index[0] : index[1]])))


def jpsi_window_and_background(summary: dict[str, Any]) -> tuple[int, float] | None:
    """(pairs in the window, S/B), or None if the window and sidebands are not on the histogram's bin edges."""
    histogram = summary["histogram"]
    window = _count_between(histogram, *WINDOW)
    sidebands = [_count_between(histogram, *s) for s in SIDEBANDS]
    if window is None or None in sidebands:
        return None
    sideband_width = sum(high - low for low, high in SIDEBANDS)
    background = sum(c for c in sidebands if c is not None) * (WINDOW[1] - WINDOW[0]) / sideband_width
    return window, (window - background) / background if background > 0 else float("inf")


def load_test_metrics(repo: Path) -> tuple[list[dict[str, Any]] | None, str]:
    """(the toy tests, "") if the record exists and matches the fit code at HEAD; otherwise (None, the reason)."""
    path = repo / "dev" / "test_metrics.json"
    if not path.exists():
        return None, "dev/test_metrics.json is missing (scripts/record_test_metrics.py)"
    record = json.loads(path.read_text())
    blob = subprocess.run(["git", "rev-parse", "HEAD:src/cmsopen/fitting.py"], cwd=repo, capture_output=True, text=True)
    if blob.stdout.strip() != record["fitting_blob"]:
        return None, "dev/test_metrics.json was recorded for different fit code; rerun scripts/record_test_metrics.py"
    return record["tests"], ""


def _gates(data: dict[str, Any]) -> str:
    return "gates record of the production commit"


def _toy_rows(tests: list[dict[str, Any]] | None, reason: str, wanted: dict[str, str]) -> list[dict[str, str]]:
    toys, mean_name, std_name = wanted["toys"], wanted["mean"], wanted["std"]
    rows = []
    if tests is None:
        return [
            _no(name, benchmark, reason)
            for name, benchmark in (
                (toys, wanted["toys_b"]),
                (mean_name, wanted["mean_b"]),
                (std_name, wanted["std_b"]),
            )
        ]
    peak = [t["pulls"]["mean"] for t in tests]  # the pull of the fitted peak position, in every test
    others = [(k, v) for t in tests for k, v in t["pulls"].items() if k != "mean"]
    failed = max(t["n_failed"] for t in tests)
    n_toys = min(t["n_toys"] for t in tests)
    rows.append(
        _row(
            toys,
            wanted["toys_b"],
            f"{n_toys:,} toys in each of {len(tests)} tests; up to {failed} failed fits "
            "per test, whose pulls are not counted",
            _met(n_toys >= 1000),
            TEST_LABEL,
        )
    )
    worst = max(abs(p["mean"]) for p in peak)
    text = f"peak position: largest {worst:.3f}"
    if others:
        name, value = max(others, key=lambda kv: abs(kv[1]["mean"]))
        text += f"; every fitted parameter: largest {abs(value['mean']):.3f} ({name})"
    rows.append(_row(mean_name, wanted["mean_b"], text, f"{_met(worst <= 0.2)} for the peak position", TEST_LABEL))
    low, high = min(p["std"] for p in peak), max(p["std"] for p in peak)
    text = f"peak position: {low:.3f} to {high:.3f}"
    if others:
        text += (
            f"; every fitted parameter: {min(v['std'] for _, v in others):.3f} to "
            f"{max(v['std'] for _, v in others):.3f}"
        )
    rows.append(
        _row(std_name, wanted["std_b"], text, f"{_met(low >= 0.8 and high <= 1.2)} for the peak position", TEST_LABEL)
    )
    return rows


def _png_dpi(content: bytes) -> float:
    position = 8
    while position < len(content):
        length, kind = struct.unpack(">I4s", content[position : position + 8])
        if kind == b"pHYs":
            x, _, unit = struct.unpack(">IIB", content[position + 8 : position + 17])
            return x * 0.0254 if unit == 1 else 0.0
        position += length + 12
    return 0.0


def _threshold_rows(repo: Path, data: dict[str, Any]) -> list[dict[str, str]]:
    z = data["channels"]["Z_mumu"]
    res, offset = z["result"]["resolution_gev"], z["result"]["offset_from_pdg_gev"]
    spread = z["validation"]["systematics_summary"]["fit_choice_spread"]
    sizes = [(repo / f).stat().st_size for f in data["figures"] if f.endswith((".png", ".pdf"))]
    pngs = [(repo / f).read_bytes() for f in data["figures"] if f.endswith(".png")]
    dpi = [_png_dpi(p) for p in pngs]
    source = "results/production.json"
    (a, a_b), (b, b_b), (c, c_b), (d, d_b), (e, e_b), (f, f_b), (g, g_b), (h, h_b) = THRESHOLDS
    return [
        _no(
            a,
            a_b,
            "the run saves only the number of same-sign pairs, not their masses, so none can be counted in a "
            "mass window",
        ),
        _row(b, b_b, f"{res:.3f} GeV", _met(0.5 <= res <= 4), source),
        _row(
            c,
            c_b,
            f"{spread:.4f} GeV" if spread is not None else "n/a",
            _met(spread < 0.5) if spread is not None else "not derivable",
            source,
        ),
        _row(d, d_b, f"{offset:+.4f} GeV", _met(abs(offset) < 1.0), source),
        _row(e, e_b, f"smallest {min(sizes) / 1000:.0f} kB", _met(min(sizes) > 20_000), "docs/figures/"),
        _no(f, f_b, f"the run does not save figsize; the PNGs are {min(dpi):.0f} to {max(dpi):.0f} dpi"),
        _no(g, g_b, "checked by the tests on other inputs; the production figures' layout is not measured in the run"),
        _no(h, h_b, "checked by the tests on other inputs; the figures were written once in the run"),
    ]


def derive(repo: Path, data: dict[str, Any]) -> dict[str, Any]:
    """Every registry benchmark with an observed value or the reason there is none; deterministic, no file names."""
    jpsi_summary, jpsi_reason = load_summary(repo, data, "Jpsi_mumu")
    window = jpsi_window_and_background(jpsi_summary) if jpsi_summary else None
    if jpsi_summary and window is None:
        jpsi_reason = "the window and sidebands are not on the saved histogram's bin edges"
    tests, toy_reason = load_test_metrics(repo)
    targets = data["targets"]
    gates = data["gates"]
    channels = data["channels"]
    rows: list[dict[str, str]] = []
    toy: dict[str, str] = {}
    for metric, benchmark in registry_rows(repo):
        low = metric.lower()
        if low.startswith("production sample size"):
            rows.append(
                _row(
                    metric,
                    benchmark,
                    observed_text("T4", targets["T4"]["observed"]),
                    _met(targets["T4"]["met"]),
                    "results/production.json",
                )
            )
        elif low.startswith("fit adequacy"):
            text = "; ".join(
                f"{'Z' if n == 'Z_mumu' else 'J/ψ'} {channels[n]['result']['chi2_ndf']:.3f} "
                f"({_met(channels[n]['t2']['met'])})"
                for n in ("Z_mumu", "Jpsi_mumu")
            )
            rows.append(
                _row(
                    metric,
                    benchmark,
                    text,
                    "met" if all(channels[n]["t2"]["met"] for n in channels) else "not met for every channel",
                    "results/production.json",
                )
            )
        elif low.startswith("line coverage"):
            value = re.fullmatch(r"([\d.]+)%", str(gates.get("coverage_total", "")))
            if value:
                rows.append(
                    _row(metric, benchmark, f"{value.group(1)} %", _met(float(value.group(1)) >= 90), _gates(data))
                )
            else:
                rows.append(_no(metric, benchmark, f"the gates record gives coverage {gates.get('coverage_total')!r}"))
        elif low.startswith("mypy"):
            ok = gates.get("quality_rc") == 0
            rows.append(
                _row(
                    metric,
                    benchmark,
                    "0 findings (quality gates exit 0)" if ok else f"quality gates exit {gates.get('quality_rc')}",
                    _met(ok),
                    _gates(data),
                )
            )
        elif low.startswith("pull-test toys"):
            toy.update(toys=metric, toys_b=benchmark)
            rows.append({"placeholder": "toys"})
        elif low.startswith("pull mean"):
            toy.update(mean=metric, mean_b=benchmark)
            rows.append({"placeholder": "mean"})
        elif low.startswith("pull standard"):
            toy.update(std=metric, std_b=benchmark)
            rows.append({"placeholder": "std"})
        elif low.startswith("deliberate-breakage"):
            rows.append(
                _no(
                    metric,
                    benchmark,
                    "these checks were run by hand during development and no per-layer "
                    "count was recorded; the commit history does not give one",
                )
            )
        elif low.startswith("validation pairs"):
            parts = []
            ok = True
            for name in ("Z_mumu", "Jpsi_mumu"):
                fitted = [e["n_pairs"] for e in channels[name]["validation"]["entries"] if e["status"] == "fitted"]
                parts.append(f"{'Z' if name == 'Z_mumu' else 'J/ψ'} smallest fitted entry {min(fitted):,}")
                ok = ok and min(fitted) >= channels[name]["validation"]["min_pairs"]
            rows.append(_row(metric, benchmark, "; ".join(parts), _met(ok), "results/production.json"))
        elif low.startswith("j/psi opposite-sign"):
            if window:
                rows.append(
                    _row(
                        metric,
                        benchmark,
                        f"{window[0]:,} pairs (peak: see the J/ψ figure)",
                        _met(window[0] >= 2000),
                        "saved histogram of the run",
                    )
                )
            else:
                rows.append(_no(metric, benchmark, jpsi_reason))
        elif low.startswith("j/psi sideband"):
            if window:
                rows.append(
                    _row(metric, benchmark, f"{window[1]:.2f}", _met(window[1] >= 1), "saved histogram of the run")
                )
            else:
                rows.append(_no(metric, benchmark, jpsi_reason))
        elif low.startswith("parallel versus serial") or low.startswith("reproducibility"):
            rows.append(
                _row(
                    metric,
                    benchmark,
                    observed_text("T1", targets["T1"]["observed"]),
                    _met(targets["T1"]["met"]),
                    "results/production.json",
                )
            )
        elif low.startswith("run-period"):
            rows.append(
                _row(
                    metric,
                    benchmark,
                    observed_text("T6", targets["T6"]["observed"]),
                    "reported",
                    "results/production.json",
                )
            )
        elif low.startswith("mass value"):
            text = "; ".join(
                f"{'Z' if n == 'Z_mumu' else 'J/ψ'} offset from PDG "
                f"{channels[n]['result']['offset_from_pdg_gev']:+.{4 if n == 'Z_mumu' else 5}f} GeV"
                for n in ("Z_mumu", "Jpsi_mumu")
            )
            rows.append(_row(metric, benchmark, text, "reported", "results/production.json"))
        else:
            rows.append(_no(metric, benchmark, "no derivation is written for this metric yet"))
    if toy:
        generated = iter(_toy_rows(tests, toy_reason, toy))
        rows = [next(generated) if "placeholder" in r else r for r in rows]
    production_sha = hashlib.sha256((repo / "results" / "production.json").read_bytes()).hexdigest()
    label = dry_run_banner(data)
    return {
        "schema_version": 1,
        **({"label": label} if label else {}),
        "production_sha256": production_sha,
        "rows": rows + _threshold_rows(repo, data),
    }


def load_or_derive(repo: Path, data: dict[str, Any]) -> dict[str, Any]:
    """Derive from the saved outputs; where they are gone (a fresh clone), the kept file for this production file."""
    summary, _ = load_summary(repo, data, "Jpsi_mumu")
    kept = repo / RESULT_FILE
    if summary is None and kept.exists():
        saved = json.loads(kept.read_text())
        if (
            saved.get("production_sha256")
            == hashlib.sha256((repo / "results" / "production.json").read_bytes()).hexdigest()
        ):
            return saved
    return derive(repo, data)


def main(argv: list[str] | None = None) -> int:
    """Print the table; exit 1 if results/production.json is missing."""
    path = REPO / "results" / "production.json"
    if not path.exists():
        print("FAIL: results/production.json does not exist")
        return 1
    for row in derive(REPO, json.loads(path.read_text()))["rows"]:
        print(
            f"{row['metric']}\n  benchmark: {row['benchmark']}\n  observed:  {row['observed']}\n"
            f"  status:    {row['status']}" + (f" ({row['source']})" if row["source"] else "")
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
