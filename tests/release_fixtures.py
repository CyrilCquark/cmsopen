"""Fixtures for the post-production tests: a production file and placeholder figures in a temporary copy.

The saved dry-run output has no figures, so the copies get placeholder images stamped as such, with captions that state
the file's peak positions (scripts/apply_production.py checks those). Nothing here is ever written to the repository.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

DRY_RUN_JSON = Path.home() / "Developer" / "cmsopen-dryrun" / "production.json"
REPO = Path(__file__).resolve().parents[1]
FIGURE_PNG_DPI = 300


def placeholder_figure(path: Path, text: str) -> None:
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib.figure import Figure

    fig = Figure(figsize=(8, 5))
    fig.text(0.5, 0.5, f"PLACEHOLDER, NOT A RESULT\n{text}", ha="center", va="center", fontsize=20, color="#a00000")
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=FIGURE_PNG_DPI, metadata={"Software": None, "CreationDate": None})


def install_production(repo: Path, data: dict) -> None:
    """Write results/production.json, placeholder figures, and the test-copy marker into a copy of the repository."""
    (repo / "results" / "production.json").write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    figures = repo / "docs" / "figures"
    shutil.rmtree(figures, ignore_errors=True)
    figures.mkdir(parents=True)
    for rel in data["figures"]:
        path = repo / rel
        if path.suffix in (".png", ".pdf"):
            placeholder_figure(path, path.name)
    for name, caption, digits in (("Z_mumu", "z_peak_fit_caption.md", 3), ("Jpsi_mumu", "jpsi_peak_fit_caption.md", 5)):
        result = data["channels"][name]["result"]
        (figures / caption).write_text(f"# Placeholder caption\n\nPeak {result['peak_position_gev']:.{digits}f} GeV.\n")
    (figures / "README.md").write_text("# Figures\n\nPlaceholders for a test copy: [caption](z_peak_fit_caption.md).\n")
    mark_test_copy(repo)


def mark_test_copy(repo: Path) -> None:
    """Mark ``repo`` as a temporary test copy (ignored by git there), as tests/test_production.py does."""
    git_dir = subprocess.run(["git", "rev-parse", "--git-dir"], cwd=repo, capture_output=True, text=True).stdout.strip()
    exclude = repo / git_dir / "info" / "exclude"
    with open(exclude, "a") as f:
        f.write("scripts/.production_test_copy\n")
    (repo / "scripts" / ".production_test_copy").write_text(str(repo.resolve()) + "\n")
