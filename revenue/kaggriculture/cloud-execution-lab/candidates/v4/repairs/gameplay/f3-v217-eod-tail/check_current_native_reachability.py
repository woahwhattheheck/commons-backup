#!/usr/bin/env python3
"""Fail-closed current-native reachability audit for the F3/opening-book family.

This tool is deliberately read-only. It does not compose, activate, rewrite, or run
any candidate policy. It answers a narrower question first: can the canonical
production package actually call the recovered F3 V217, NIGHT-FEED, or opening-book
research seams? If not, any native economics run for those seams would be synthetic.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
from typing import Iterable

CORE = ("main.py", "titan_runtime.py", "TITAN-CONFIG.json")
EXCLUDED_TOP = {
    ".git", "__pycache__", "candidates", "checks", "research", "tests", "test",
    "artifacts", "archive", "archives",
}

TARGETS = {
    "f3_v217": {
        "module_tokens": ("r04_full_router", "f3_v217", "v217_eod_tail"),
        "call_tokens": ("_v217_plan",),
    },
    "night_feed": {
        "module_tokens": ("night_feed_frontier", "night_feed"),
        "call_tokens": ("propose_feed_tails",),
    },
    "opening_book": {
        "module_tokens": ("opening_book_rebound",),
        "call_tokens": ("OpeningBookRebound",),
    },
}
OPENING_LIFECYCLE = {"prepare", "record_returned", "apply"}
LOADER_NAMES = {"load", "spec_from_file_location", "SourceFileLoader"}


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        left = _call_name(node.value)
        return f"{left}.{node.attr}" if left else node.attr
    return ""


def _static_expr(node: ast.AST) -> str:
    """Best-effort source text for loader arguments; comments are never inspected."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        left = _static_expr(node.value)
        return f"{left}.{node.attr}" if left else node.attr
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Div)):
        left, right = _static_expr(node.left), _static_expr(node.right)
        return f"{left}/{right}" if left and right else left or right
    if isinstance(node, ast.Call):
        name = _call_name(node.func)
        args = ",".join(_static_expr(arg) for arg in node.args)
        return f"{name}({args})"
    try:
        return ast.unparse(node)
    except Exception:
        return ""


def _production_python(root: Path) -> Iterable[Path]:
    """Scan executable package roots while excluding research/evidence trees."""
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root)
        if rel.parts and rel.parts[0] in EXCLUDED_TOP:
            continue
        # Production wiring is rooted at top-level modules. Nested vendor/reference
        # code cannot activate a candidate without a root loader/import first.
        if len(rel.parts) != 1:
            continue
        yield path


def _scan_python(path: Path, root: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(path))
    rel = str(path.relative_to(root))
    imports: list[str] = []
    loaders: list[str] = []
    calls: list[str] = []
    attrs: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            imports.append(base)
            imports.extend(f"{base}.{alias.name}" if base else alias.name for alias in node.names)
        elif isinstance(node, ast.Call):
            name = _call_name(node.func)
            calls.append(name)
            if name.rsplit(".", 1)[-1] in LOADER_NAMES:
                loaders.append(" | ".join(_static_expr(arg) for arg in node.args))
        elif isinstance(node, ast.Attribute):
            attrs.append(node.attr)
    raw = text.encode()
    return {
        "path": rel,
        "imports": imports,
        "loaders": loaders,
        "calls": calls,
        "attrs": attrs,
        "git_blob": git_blob(raw),
        "sha256": sha256(raw),
        "bytes": len(raw),
    }


def _contains_any(values: Iterable[str], tokens: Iterable[str]) -> list[str]:
    toks = tuple(tok.lower() for tok in tokens)
    return sorted({value for value in values if any(tok in value.lower() for tok in toks)})


def _classify(scans: list[dict], config: dict) -> dict:
    result = {}
    for family, spec in TARGETS.items():
        module_hits = []
        call_hits = []
        for row in scans:
            imp = _contains_any(row["imports"], spec["module_tokens"])
            loader = _contains_any(row["loaders"], spec["module_tokens"])
            call = _contains_any(row["calls"], spec["call_tokens"])
            if imp or loader:
                module_hits.append({"path": row["path"], "imports": imp, "loaders": loader})
            if call:
                call_hits.append({"path": row["path"], "calls": call})

        if family == "opening_book":
            lifecycle = []
            for row in scans:
                methods = sorted(set(row["attrs"]) & OPENING_LIFECYCLE)
                if methods:
                    lifecycle.append({"path": row["path"], "methods": methods})
            reached = bool(module_hits and call_hits and lifecycle)
            result[family] = {
                "reachable": reached,
                "module_binding": module_hits,
                "constructor_calls": call_hits,
                "lifecycle_calls": lifecycle,
                "rule": "module binding + OpeningBookRebound construction + lifecycle call",
            }
        else:
            reached = bool(call_hits)
            result[family] = {
                "reachable": reached,
                "module_binding": module_hits,
                "call_sites": call_hits,
                "rule": f"actual call to {spec['call_tokens'][0]}; comments/strings/import-only do not count",
            }

    config_keys = [str(key) for key in config]
    result["config_target_keys"] = sorted(
        key for key in config_keys
        if any(tok.lower() in key.lower()
               for spec in TARGETS.values()
               for tok in (*spec["module_tokens"], *spec["call_tokens"]))
    )
    return result


def audit(root: Path) -> dict:
    root = root.resolve()
    missing = [name for name in CORE if not (root / name).is_file()]
    if missing:
        raise ValueError(f"missing native package files: {missing}")

    raw_config = (root / "TITAN-CONFIG.json").read_bytes()
    config = json.loads(raw_config)
    if type(config) is not dict:
        raise ValueError("TITAN-CONFIG.json must be an object")

    scans = [_scan_python(path, root) for path in _production_python(root)]
    by_path = {row["path"]: row for row in scans}
    if "main.py" not in by_path or "titan_runtime.py" not in by_path:
        raise ValueError("production scanner failed to cover main.py/titan_runtime.py")

    main_text = (root / "main.py").read_text(encoding="utf-8")
    runtime_text = (root / "titan_runtime.py").read_text(encoding="utf-8")
    call_chain = {
        "main_constructs_titan": (
            "from titan_runtime import TitanAgent, Features, load" in main_text
            and "return FinalPressureAgent(" in main_text
        ),
        "main_calls_act": "instance.act(" in main_text,
        "runtime_selects_frozen": (
            "from frozen_selected import FrozenSelected" in runtime_text
            and "self.consumer = FrozenSelected()" in runtime_text
        ),
        "config_consumer_frozen": config.get("consumer") == "frozen",
    }
    family = _classify(scans, config)
    reachable = {name: bool(family[name]["reachable"]) for name in TARGETS}
    any_reachable = any(reachable.values())
    chain_recognized = all(call_chain.values())

    if not chain_recognized:
        disposition = "BLOCKED_UNRECOGNIZED_NATIVE_CHAIN"
    elif any_reachable:
        disposition = "BOUND_REQUIRES_RUNTIME_GATE"
    else:
        disposition = "BLOCKED_AT_NATIVE_ASSEMBLY"

    generic_seed_budget = []
    for row in scans:
        hits = _contains_any(
            row["imports"] + row["loaders"] + row["calls"], ("SeedBudget", "seed_budget")
        )
        if hits:
            generic_seed_budget.append({"path": row["path"], "hits": hits})

    return {
        "schema": "titan-v4-f3-current-native-reachability/v1",
        "native_root": str(root),
        "call_chain": call_chain,
        "native_chain_recognized": chain_recognized,
        "production_python_scanned": [row["path"] for row in scans],
        "source_identities": {
            row["path"]: {
                "git_blob": row["git_blob"],
                "sha256": row["sha256"],
                "bytes": row["bytes"],
            }
            for row in scans
        },
        "config": {
            "git_blob": git_blob(raw_config),
            "sha256": sha256(raw_config),
            "bytes": len(raw_config),
            "keys": sorted(config),
        },
        "family": family,
        "reachable": reachable,
        "generic_seed_budget_signals_ignored_for_opening_book": generic_seed_budget,
        "disposition": disposition,
        "economics_run": False,
        "economics_reason": (
            "native economics would be synthetic until a callable recovered seam exists"
            if not any_reachable else
            "this checker proves binding only; current-native execution/economics remains a separate gate"
        ),
        "scope": "read-only source binding/reachability; no composition, activation, gameplay, or EV claim",
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("native", type=Path)
    ap.add_argument("--output", type=Path)
    ap.add_argument("--require-disposition", choices=(
        "BLOCKED_AT_NATIVE_ASSEMBLY",
        "BLOCKED_UNRECOGNIZED_NATIVE_CHAIN",
        "BOUND_REQUIRES_RUNTIME_GATE",
    ))
    args = ap.parse_args(argv)
    try:
        report = audit(args.native)
    except (OSError, SyntaxError, ValueError, json.JSONDecodeError) as exc:
        ap.exit(2, f"f3-native-reachability: {exc}\n")
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    if args.require_disposition and report["disposition"] != args.require_disposition:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
