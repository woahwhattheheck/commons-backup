# SPDX-License-Identifier: Apache-2.0
"""Exact-current IntegratedSelectedAgent executable-market-prefix repair.

Offline source composition only; does not load a producer, toggle a feature,
edit the production root, or apply the legacy V4 materializer.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

SOURCE_BLOB = "defa9b84c77fff28ae107bce291b6235bec5d26c"
ENGINE_BLOB = "3c202c7ee921da239356789e266b694635103fc4"

# Five exact anchors confined to _projection and transform. Raw slots are not
# filtered or compacted. In particular, [] consumes a market slot in the engine.
REPLACEMENTS = (
    ('maximum = int(cfg.get(\'maxMarketOrdersPerTurn\', 10))',
     'maximum = max(1, int(cfg.get(\'maxMarketOrdersPerTurn\', 10)))'),
    ("for o in action.get('market', [])):",
     "for o in action.get('market', [])[:maximum]):"),
    ("                raise ValueError('This continuation adapter requires the pinned one-way producer')\n",
     "                raise ValueError('This continuation adapter requires the pinned one-way producer')\n"
     "            maximum = max(1, int(cfg.get('maxMarketOrdersPerTurn', 10)))\n"),
    ("                        int(cfg.get('maxMarketOrdersPerTurn',10)))",
     "                        maximum)"),
    ("for i in edits for o in selected['market'][i+1:])",
     "for i in edits for o in selected['market'][i+1:maximum])"),
)


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def _outside_target_methods(tree: ast.AST) -> str:
    """Ensure this repair cannot silently alter unrelated runtime declarations."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "IntegratedSelectedAgent":
            for method in node.body:
                if isinstance(method, ast.FunctionDef) and method.name in ("_projection", "transform"):
                    method.body = [ast.Pass()]
    return ast.dump(tree, include_attributes=False)


def compose(source: bytes) -> bytes:
    if not isinstance(source, bytes) or git_blob(source) != SOURCE_BLOB:
        raise ValueError("integrated_selected.py source drift: exact current source required")
    text = source.decode("utf-8")
    result = text
    for old, new in REPLACEMENTS:
        if result.count(old) != 1:
            raise ValueError("ambiguous or missing source anchor")
        result = result.replace(old, new, 1)
    before, after = ast.parse(text), ast.parse(result)
    if _outside_target_methods(before) != _outside_target_methods(after):
        raise ValueError("repair escaped the two declared methods")
    compile(result, "<ordered-consumer-prefix>", "exec")
    return result.encode("utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    created = False
    try:
        if not stat.S_ISREG(args.source.lstat().st_mode):
            raise ValueError("source must be a regular non-symlink file")
        if args.output.exists() or args.output.is_symlink():
            raise ValueError("output must not exist; in-place, alias and overwrite refused")
        if args.source.resolve() == args.output.resolve():
            raise ValueError("source/output alias refused")
        source = args.source.read_bytes()
        output = compose(source)
        fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        created = True
        with os.fdopen(fd, "wb") as stream:
            stream.write(output)
            stream.flush()
            os.fsync(stream.fileno())
        if args.output.read_bytes() != output or args.source.read_bytes() != source:
            raise ValueError("source/output readback changed")
        receipt = {"schema": "titan-v4-ordered-prefix/v1", "source_blob": SOURCE_BLOB,
                   "output_blob": git_blob(output), "output_sha256": hashlib.sha256(output).hexdigest(),
                   "output_bytes": len(output), "scope": ["IntegratedSelectedAgent._projection",
                   "IntegratedSelectedAgent.transform"], "production_changed": False,
                   "feature_defaults_changed": False, "economics_proven": False}
        print(json.dumps(receipt, sort_keys=True))
        return 0
    except (OSError, ValueError, TypeError, SyntaxError, UnicodeError) as error:
        if created:
            args.output.unlink(missing_ok=True)
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
