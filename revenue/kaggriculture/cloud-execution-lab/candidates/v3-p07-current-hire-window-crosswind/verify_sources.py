# SPDX-License-Identifier: Apache-2.0
"""Exact source custody and interpreter-order theorem for SOL-CROSSWIND P07."""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
LAB = HERE.parents[1]
PINS_PATH = HERE / "SOURCE-PINS.json"


def git_blob_sha1(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def function_source(source: str, name: str) -> str:
    tree = ast.parse(source)
    node = next(
        item for item in tree.body
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == name
    )
    segment = ast.get_source_segment(source, node)
    if segment is None:
        raise AssertionError(f"could not recover function source: {name}")
    return segment


def main() -> int:
    pins = json.loads(PINS_PATH.read_text(encoding="utf-8"))
    actual = {}
    for name, receipt in sorted(pins["sources"].items()):
        path = LAB / receipt["path"]
        data = path.read_bytes()
        digest = git_blob_sha1(data)
        if digest != receipt["git_blob_sha1"]:
            raise AssertionError(
                f"{name} blob moved: expected {receipt['git_blob_sha1']}, got {digest}"
            )
        actual[name] = {
            "path": receipt["path"],
            "git_blob_sha1": digest,
            "bytes": len(data),
        }

    base_source = (LAB / pins["sources"]["p07_joint_actors"]["path"]).read_text(
        encoding="utf-8"
    )
    base_window = function_source(base_source, "_window")
    current_hire_rejection = (
        "if any(a and a[0] == 'HIRE' for a in selected.get('market', []) or []):"
        in base_window
        and "return None" in base_window
    )
    if not current_hire_rejection:
        raise AssertionError("predecessor discriminator disappeared")

    engine_source = (LAB / pins["sources"]["official_engine"]["path"]).read_text(
        encoding="utf-8"
    )
    interpreter = function_source(engine_source, "interpreter")
    unit_index = interpreter.index("_apply_unit_action")
    market_index = interpreter.index("_process_market")
    if unit_index >= market_index:
        raise AssertionError("official interpreter no longer settles units before market")
    hire = function_source(engine_source, "_do_hire")
    if 'farm["hands"].append' not in hire or 'private["inventories"].append' not in hire:
        raise AssertionError("official HIRE append semantics moved")

    successor = (HERE / "current_hire_joint_actors.py").read_text(encoding="utf-8")
    successor_tree = ast.parse(successor)
    range_bound = "for worker in range(existing_actor_count):" in successor
    if not range_bound:
        raise AssertionError("successor lost existing-actor prefix range")
    forbidden_imports = {"subprocess", "socket", "requests", "urllib", "httpx"}
    imported = set()
    for node in ast.walk(successor_tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    if imported & forbidden_imports:
        raise AssertionError(f"forbidden runtime imports: {sorted(imported & forbidden_imports)}")

    report = {
        "operation": pins["operation"],
        "base_main_sha": pins["base_main_sha"],
        "sources": actual,
        "theorems": {
            "predecessor_rejects_any_current_hire": True,
            "official_units_before_market": True,
            "official_hire_appends_actor_and_inventory": True,
            "successor_pair_loop_bound_to_observed_actor_prefix": True,
            "successor_forbidden_runtime_imports": [],
        },
        "mutation_boundary": pins["mutation_boundary"],
    }
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
