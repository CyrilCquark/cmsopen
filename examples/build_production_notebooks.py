"""Build notebooks/01_z_peak.ipynb, 02_jpsi_peak.ipynb and 03_modular_usage.ipynb from templates/notebooks/.

A template is Markdown: each ```python fence is a code cell and the text between fences is a markdown cell. Inside
code, ``#INCLUDE file`` inserts a shared file and ``#TAGS a b`` sets the cell's tags. In the text, ``#INCLUDE_TEXT z``
inserts the production-results table of a channel, filled from results/production.json through the placeholders of
scripts/generate_release_files.py. The outputs are cleared and the cell ids derive from the content, so a rebuild is
byte-identical.

notebooks/ is protected: scripts/apply_production.py writes the files; :func:`notebooks` only returns them.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

import nbformat
from nbformat.v4 import new_code_cell, new_markdown_cell, new_notebook

NAMES = ("01_z_peak", "02_jpsi_peak", "03_modular_usage")
_FENCE = re.compile(r"^```python\n(.*?)^```\s*$", flags=re.S | re.M)


def _source_of(template: str) -> list[tuple[str, str]]:
    """Split a template into (kind, text) cells."""
    cells: list[tuple[str, str]] = []
    position = 0
    for match in _FENCE.finditer(template):
        cells.append(("markdown", template[position : match.start()]))
        cells.append(("code", match.group(1)))
        position = match.end()
    cells.append(("markdown", template[position:]))
    return [(kind, text.strip()) for kind, text in cells if text.strip()]


def _production_text(folder: Path, key: str, values: dict[str, str]) -> str:
    from release_lib import render

    channel = {k[len(key) + 1 :]: v for k, v in values.items() if k.startswith(f"{key}.")}
    label = {"z": "Z → μ⁺μ⁻", "jpsi": "J/ψ → μ⁺μ⁻"}[key]
    scoped = {**values, **{f"c.{k}": v for k, v in channel.items()}, "c.label": label}
    return render((folder / "_production_text.md").read_text(), scoped).strip()


def _cells(folder: Path, template: str, values: dict[str, str], name: str) -> list[Any]:
    from release_lib import render

    cells = []
    for index, (kind, text) in enumerate(_source_of(template)):
        tags: list[str] = []
        if kind == "code":
            match = re.search(r"^#TAGS (.+)$", text, flags=re.M)
            if match:
                tags = match.group(1).split()
                text = text.replace(match.group(0) + "\n", "")
            text = re.sub(r"^#INCLUDE (\S+)$", lambda m: (folder / m.group(1)).read_text().strip(), text, flags=re.M)
            cell = new_code_cell(text, metadata={"tags": tags} if tags else {})
            cell["id"] = hashlib.sha256(f"{name}/{index}/{text}".encode()).hexdigest()[:12]
            cells.append(cell)
            continue
        pieces = re.split(r"^#INCLUDE_TEXT (\w+)$", text, flags=re.M)
        for j, piece in enumerate(pieces):
            if j % 2:
                body = _production_text(folder, piece, values)
                tags = ["production-text"]
                body = re.sub(r"^<!-- tags: .*? -->\n", "", body)
            else:
                body, tags = render(piece, values).strip(), []
            if body:
                cell = new_markdown_cell(body, metadata={"tags": tags} if tags else {})
                cell["id"] = hashlib.sha256(f"{name}/{index}/{j}/{body}".encode()).hexdigest()[:12]
                cells.append(cell)
    return cells


def notebooks(repo: Path, values: dict[str, str]) -> dict[str, bytes]:
    """Relative path -> content of each notebook, validated against the nbformat schema, outputs cleared."""
    out = {}
    folder = repo / "templates" / "notebooks"
    for name in NAMES:
        nb = new_notebook(
            cells=_cells(folder, (folder / f"{name}.md").read_text(), values, name),
            metadata={
                "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                "language_info": {"name": "python"},
            },
        )
        nbformat.validate(nb)
        out[f"notebooks/{name}.ipynb"] = (nbformat.writes(nb, version=4) + "\n").encode()
    return out
