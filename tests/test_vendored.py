"""The vendored engine copies have to match what engines/VENDORED.json records.

Each engine module is a copy of a module published in a standalone toolkit
repo. The manifest records which repo, file and commit each copy came from,
plus a fingerprint of its code (module docstring excluded). If a copy is
edited here without re-vendoring it from its source, this fails.

Whether the sources themselves have moved on since is a separate, networked
check: `python scripts/vendored.py check-upstream`, run by the
vendored-sync workflow.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

_spec = importlib.util.spec_from_file_location("vendored", ROOT / "scripts" / "vendored.py")
vendored = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vendored)

# chart_style.py is deliberately not a straight copy (each repo adds its own
# extra colors); its shared core is checked by tests/test_chart_style_core.py.
NOT_VENDORED = {"chart_style.py", "__init__.py"}


def test_vendored_copies_match_the_manifest():
    assert vendored.local_mismatches(vendored.load_manifest()) == []


def test_every_engine_module_is_listed_in_the_manifest():
    listed = set(vendored.load_manifest()["files"])
    on_disk = {
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "engines").rglob("*.py")
        if path.name not in NOT_VENDORED
    }
    assert on_disk == listed
