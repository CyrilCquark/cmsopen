"""Shared code of the post-production generators: template rendering and the audit of numbers.

Two independent guards keep typed numbers out of what the generators write:

- :func:`lint_template`: a template may hold a number only through a ``{{ placeholder }}``. Any numeric token left
  in its prose (fenced code, links and comments excepted) is an error, apart from the few phrases in LITERALS.
- :func:`audit_numbers`: every numeric token of a generated text must trace to a value in results/production.json,
  formatted to the number of decimals shown.

Standard library only.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any

PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z0-9_.]+)\s*\}\}")
_TOKEN = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)*(?:[eE][-+]?\d+)?%?(?![\w])")

# Facts about the data or the software that are neither results nor benchmarks (longest first when stripped).
LITERALS = ("Python 3.10", "8 TeV", "Run 2012", "2012", "CC0-1.0", "SHA-256", "shasum -a 256")


def render(template: str, values: dict[str, str]) -> str:
    """Fill every ``{{ key }}``; an unknown key is an error, so no placeholder can reach a generated file."""

    def fill(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in values:
            raise KeyError(f"unknown template placeholder {key!r}")
        return values[key]

    return PLACEHOLDER.sub(fill, template)


def prose(text: str) -> str:
    """The text without fenced code, HTML comments, link targets, URLs and list markers."""
    text = re.sub(r"^(```|~~~).*?^\1\s*$", "", text, flags=re.S | re.M)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    text = re.sub(r"\]\([^)]*\)", "]", text)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"\b10\.\d{4,}/[^\s\"'*)\]]+", "", text)  # a DOI
    text = re.sub(r"\b[0-9a-f]{7,64}\b", "", text)
    text = re.sub(r"^\s*\d+\.\s", "", text, flags=re.M)
    return text


def tokens(text: str) -> list[str]:
    """Numeric tokens of a text: 91.2, 1,234, 3e-05, 0.1.0; never the digits inside chi2, T4, 2012B or cb2_bw_exp."""
    return [t.rstrip(",") for t in _TOKEN.findall(text)]


def _strip_literals(text: str) -> str:
    for phrase in sorted(LITERALS, key=len, reverse=True):
        text = re.sub(rf"(?<![\w.,]){re.escape(phrase)}(?![\w])", "", text)
    return text


def lint_template(text: str) -> list[str]:
    """The numeric tokens typed by hand in a template's prose (an empty list means none)."""
    return tokens(_strip_literals(prose(PLACEHOLDER.sub("", text))))


def _leaves(obj: Any) -> Iterator[Any]:
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _leaves(v)
    elif isinstance(obj, list | tuple):
        for v in obj:
            yield from _leaves(v)
    else:
        yield obj


class NumberAudit:
    """The numbers a text may show: those of results/production.json, at the precision displayed."""

    def __init__(self, data: dict[str, Any], extra: tuple[Any, ...] = ()) -> None:
        self.exact: set[str] = set()
        self.floats: list[float] = []
        for leaf in [*_leaves(data), *extra]:
            if isinstance(leaf, bool) or leaf is None:
                continue
            if isinstance(leaf, int):
                self.exact.add(str(abs(leaf)))
            elif isinstance(leaf, float):
                self.floats.append(abs(leaf))
            elif isinstance(leaf, str):
                self.exact.update(t.replace(",", "") for t in tokens(leaf))
        self._by_decimals: dict[int, set[str]] = {}

    def _formatted(self, decimals: int) -> set[str]:
        if decimals not in self._by_decimals:
            self._by_decimals[decimals] = {f"{v:.{decimals}f}" for v in self.floats}
        return self._by_decimals[decimals]

    def allows(self, token: str) -> bool:
        """True if the token is a value of the file, or one of its floats at the decimals shown or as %g / %.3g."""
        plain = token.replace(",", "").rstrip("%")
        if plain in self.exact:
            return True
        if re.fullmatch(r"\d+(\.\d+)?", plain):
            decimals = len(plain.partition(".")[2])
            if plain in self._formatted(decimals):
                return True
            if plain == str(int(float(plain))) or "." in plain:
                return any(f"{v:g}" == plain or f"{v:.3g}" == plain for v in self.floats)
            return False
        return any(f"{v:.3g}" == plain or f"{v:g}" == plain for v in self.floats)


def audit_numbers(text: str, audit: NumberAudit) -> list[str]:
    """Numeric tokens of a generated text that do not trace to results/production.json."""
    return [t for t in tokens(_strip_literals(prose(text))) if not audit.allows(t)]
