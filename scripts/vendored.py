"""Check the vendored engine copies under engines/ against their sources.

Each file in engines/VENDORED.json is a copy of a module published in one of
the standalone toolkit repos. The copies differ from their sources only in
the module docstring (which says where the copy came from) and, for
schedule/metrics.py, one import path. So files are compared by fingerprint:
a SHA-256 of the parsed syntax tree with the module docstring removed and
the listed import rewrites applied. Formatting and comments don't change the
fingerprint; any change to what the code does does.

Usage:
    python scripts/vendored.py check
        Local copies still match the fingerprints recorded in the manifest.
        (Also run by tests/test_vendored.py.)
    python scripts/vendored.py check-upstream [--ref main]
        Fetch each source file from GitHub at --ref and report any source
        that has moved on since it was vendored. Needs network access.
    python scripts/vendored.py record <engines/path.py> --source-commit <sha>
        After re-copying a file from its source, record the new fingerprint
        and the source commit it was copied from.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "engines" / "VENDORED.json"
RAW_URL = "https://raw.githubusercontent.com/{repo}/{ref}/{path}"


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


def fingerprint(source: str, rewrites: list[list[str]] | None = None) -> str:
    for old, new in rewrites or []:
        source = source.replace(old, new)
    tree = ast.parse(source)
    body = tree.body
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        tree.body = body[1:]
    return hashlib.sha256(_canonical(tree).encode("utf-8")).hexdigest()


def load_manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def local_mismatches(manifest: dict) -> list[str]:
    problems = []
    for rel_path, entry in manifest["files"].items():
        actual = fingerprint((ROOT / rel_path).read_text(encoding="utf-8"))
        if actual != entry["fingerprint"]:
            problems.append(
                f"{rel_path}: changed locally since it was vendored from "
                f"{entry['source_repo']}@{entry['source_commit'][:7]}"
            )
    return problems


def upstream_mismatches(manifest: dict, ref: str) -> list[str]:
    problems = []
    for rel_path, entry in manifest["files"].items():
        url = RAW_URL.format(repo=entry["source_repo"], ref=ref, path=entry["source_path"])
        with urllib.request.urlopen(url, timeout=30) as response:
            source = response.read().decode("utf-8")
        if fingerprint(source, entry.get("rewrites")) != entry["fingerprint"]:
            problems.append(
                f"{rel_path}: {entry['source_repo']}/{entry['source_path']} at {ref} "
                f"no longer matches the copy vendored from {entry['source_commit'][:7]}"
            )
    return problems


def record(rel_path: str, source_commit: str) -> None:
    manifest = load_manifest()
    if rel_path not in manifest["files"]:
        sys.exit(f"{rel_path} is not listed in {MANIFEST.relative_to(ROOT)}")
    entry = manifest["files"][rel_path]
    entry["fingerprint"] = fingerprint((ROOT / rel_path).read_text(encoding="utf-8"))
    entry["source_commit"] = source_commit
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"Recorded {rel_path} at {source_commit[:7]}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check")
    upstream = sub.add_parser("check-upstream")
    upstream.add_argument("--ref", default="main")
    rec = sub.add_parser("record")
    rec.add_argument("path")
    rec.add_argument("--source-commit", required=True)
    args = parser.parse_args()

    if args.command == "record":
        record(args.path, args.source_commit)
        return

    manifest = load_manifest()
    if args.command == "check":
        problems = local_mismatches(manifest)
    else:
        problems = upstream_mismatches(manifest, args.ref)

    for problem in problems:
        print(problem)
    if problems:
        sys.exit(1)
    print(f"All {len(manifest['files'])} vendored files match.")


if __name__ == "__main__":
    main()
