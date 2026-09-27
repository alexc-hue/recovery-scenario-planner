"""The shared chart core has to stay identical across all six toolkit repos.

chart_style.py says CHART_BG, INK, GRID, SERIES_1 and apply_chrome() are the
same in every github.com/alexc-hue project-controls repo, with
project-controls-dashboard as the canonical copy. Each repo carries its own
file, so nothing enforced that until now: one repo was in fact missing
SERIES_1. This test pins the canonical values and a fingerprint of
apply_chrome(), and the same test runs in all six repos.

apply_chrome() is compared by its parsed syntax tree, so formatting and
comments don't matter but any change to what it does does. If the canonical
version changes on purpose, update APPLY_CHROME_FINGERPRINT here and in the
other five repos in the same pass.
"""

from __future__ import annotations

import ast
import hashlib
import inspect

from engines import chart_style

CANONICAL_CORE = {
    "CHART_BG": "#fcfcfb",
    "INK": "#10182b",
    "GRID": "#e1e0d9",
    "SERIES_1": "#2a78d6",
}
APPLY_CHROME_FINGERPRINT = "a5fe2b4a197df22f7072379972891d283b54e7b2c9b27204c3ab0f757ac76df8"


def _canonical(node) -> str:
    """Serialize a syntax tree the same way on every supported Python version.

    ast.dump() output changed in 3.12 (new fields) and 3.13 (empty fields
    omitted), so it can't be hashed directly. This skips fields that are None
    or empty, which is where those versions differ.
    """
    if isinstance(node, ast.AST):
        parts = [
            f"{name}={_canonical(value)}"
            for name in node._fields
            if (value := getattr(node, name, None)) is not None and value != []
        ]
        return f"{type(node).__name__}({', '.join(parts)})"
    if isinstance(node, list):
        return "[" + ", ".join(_canonical(item) for item in node) + "]"
    return repr(node)


def test_core_palette_matches_canonical_values():
    actual = {name: getattr(chart_style, name, None) for name in CANONICAL_CORE}
    assert actual == CANONICAL_CORE


def test_apply_chrome_matches_canonical_version():
    tree = ast.parse(inspect.getsource(chart_style.apply_chrome))
    fingerprint = hashlib.sha256(_canonical(tree).encode()).hexdigest()
    assert fingerprint == APPLY_CHROME_FINGERPRINT
