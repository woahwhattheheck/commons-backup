# SPDX-License-Identifier: Apache-2.0
"""Native executable-prefix port of the existing operating-stock mechanism.

No controller, key, default or economics is added.  The helper preimage is exact;
the runtime check binds only the incumbent method, preserving unrelated concurrent
runtime repairs.  CLI writes a NEW directory only; it never edits live sources.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path

HELPER_BEFORE = "781aa90da0d85d0ba23c665e29d6087d182c085e"
ENGINE_BLOB = "3c202c7ee921da239356789e266b694635103fc4"
RUNTIME_REFERENCE = "b952c9c228ecbde592bf3d2df01638677abb0d24"
CALLER_BEFORE = "365a88dae11472e6fa1e07f4fbc6150f2bf2ca2f"


def git_blob(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def _replace_once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise ValueError(f"ambiguous or missing source anchor: {old!r}")
    return text.replace(old, new, 1)


def _function(source: str, name: str, owner: str | None = None):
    tree = ast.parse(source)
    body = tree.body
    if owner is not None:
        owners = [n for n in body if isinstance(n, ast.ClassDef) and n.name == owner]
        if len(owners) != 1:
            raise ValueError(f"expected one class {owner}")
        body = owners[0].body
    found = [n for n in body if isinstance(n, ast.FunctionDef) and n.name == name]
    if len(found) != 1 or found[0].decorator_list:
        raise ValueError(f"expected one undecorated function {name}")
    node = found[0]
    lines = source.splitlines(keepends=True)
    start = sum(map(len, lines[:node.lineno - 1]))
    end = sum(map(len, lines[:node.end_lineno]))
    return start, end, source[start:end].rstrip("\r\n")


def _replace_function(source: str, name: str, transform, owner=None) -> str:
    start, end, old = _function(source, name, owner)
    trailing = source[start:end][len(old):]
    return source[:start] + transform(old) + trailing + source[end:]


def port_helper(source: str) -> str:
    """Change only FERT-prefix reads/rewrites and shared FERT cap normalization."""
    if git_blob(source.encode()) != HELPER_BEFORE:
        raise ValueError("operating_stock.py preimage mismatch")

    def fertilizer(text):
        edits = (
            ("    orders = selected.get('market') or []",
             "    max_orders = max(1, int((configuration or {}).get('maxMarketOrdersPerTurn', 10)))\n"
             "    orders = (selected.get('market') or [])[:max_orders]"),
            ("for o in route[step].get('market', [])):",
             "for o in route[step].get('market', [])[:max_orders]):"),
            ("for order in row.get('market', []):",
             "for order in row.get('market', [])[:max_orders]:"),
            ("reservation_bound = min(len(obligations), max(0, int(cfg.get('maxMarketOrdersPerTurn', 10))))",
             "reservation_bound = min(len(obligations), max_orders)"),
            ("enumerate(out['market']):", "enumerate(out['market'][:max_orders]):"),
        )
        for old, new in edits:
            text = _replace_once(text, old, new)
        return text

    source = _replace_function(source, "protect_operating_stock", fertilizer)
    source = _replace_function(source, "_bonus_water_service", lambda text: _replace_once(
        text, "[:int(cfg.get('maxMarketOrdersPerTurn', 10))]",
        "[:max(1, int(cfg.get('maxMarketOrdersPerTurn', 10)))]"))
    source = _replace_function(source, "_operating_stock_commitments", lambda text: _replace_once(
        text, "max_orders = int(cfg.get('maxMarketOrdersPerTurn', 10))",
        "max_orders = max(1, int(cfg.get('maxMarketOrdersPerTurn', 10)))"))
    compile(source, "operating_stock.py", "exec")
    return source


def port_runtime(source: str) -> str:
    """Keep all runtime bytes except the exact incumbent admission predicate."""
    def caller(text):
        if git_blob(text.encode()) != CALLER_BEFORE:
            raise ValueError("TitanAgent._operating_stock_selected preimage mismatch")
        return _replace_once(text, "for o in selected.get('market', [])):",
            "for o in selected.get('market', [])[:max(1, int(cfg.get('maxMarketOrdersPerTurn', 10)))]):")
    result = _replace_function(source, "_operating_stock_selected", caller, "TitanAgent")
    compile(result, "titan_runtime.py", "exec")
    return result


def materialize(source_root: Path, engine: Path, output: Path) -> dict:
    """Verify inputs before creating an exclusive output; no source overwrite."""
    helper_bytes = (source_root / "operating_stock.py").read_bytes()
    runtime_bytes = (source_root / "titan_runtime.py").read_bytes()
    if git_blob(engine.read_bytes()) != ENGINE_BLOB:
        raise ValueError("official engine preimage mismatch")
    helper = port_helper(helper_bytes.decode()).encode()
    runtime = port_runtime(runtime_bytes.decode()).encode()
    receipt = {
        "helper_before": git_blob(helper_bytes), "helper_after": git_blob(helper),
        "runtime_before": git_blob(runtime_bytes), "runtime_after": git_blob(runtime),
        "runtime_reference": RUNTIME_REFERENCE,
        "runtime_binding": "exact _operating_stock_selected method, other bytes retained",
        "engine": ENGINE_BLOB, "production_modified": False,
        "defaults_modified": False, "game_economics_proven": False,
    }
    # mkdir is exclusive even for aliases/symlinks to existing directories.
    output.mkdir(parents=False, exist_ok=False)
    for name, data in (("operating_stock.py", helper), ("titan_runtime.py", runtime),
                       ("NATIVE-PORT.json", (json.dumps(receipt, indent=2)+"\n").encode())):
        with (output / name).open("xb") as stream:
            stream.write(data)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--engine", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        receipt = materialize(args.source_root, args.engine, args.output)
    except (OSError, ValueError, SyntaxError, UnicodeError) as error:
        parser.exit(2, f"native port rejected: {error}\n")
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
