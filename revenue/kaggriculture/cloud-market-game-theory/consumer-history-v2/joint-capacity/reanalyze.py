# SPDX-License-Identifier: Apache-2.0
"""Recompute the retained history-v2 terminal families after joint-capacity tightening.

This is an offline consumer of committed result JSON.  It does not invoke an
actor, replay a game, read a realized rival queue, or alter a policy.  The
historical FlowHistory and terminal-family builder are loaded from the exact
frozen history-v2 source commit; only ``tighten_joint_sales`` comes from the
current landed bridge.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any

HISTORY_REF = "2fc1418f3724ac09232e35a2a583414ce0ee8f84"
CURRENT_BRIDGE_BLOB = "7967fb43c64bc3154fe7da609497873163c773eb"
FLOW_PATH = "revenue/kaggriculture/cloud-execution-lab/reference/titan-history/flow.py"
JOINT_PATH = "revenue/kaggriculture/cloud-execution-lab/reference/titan-history/joint_terminal_history.py"
BRIDGE_PATH = "revenue/kaggriculture/cloud-market-response/selected_action_history.py"
PRODUCTS = ("WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON",
            "EGG", "MILK", "WOOL", "FERTILIZER")
NONBUYABLE = frozenset(PRODUCTS) - {"WHEAT", "FERTILIZER"}


def repository_root() -> Path:
    text = subprocess.check_output(
        ["git", "rev-parse", "--show-toplevel"], text=True,
        cwd=Path(__file__).resolve().parent,
    )
    return Path(text.strip())


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_blob(path: Path) -> str:
    return subprocess.check_output(
        ["git", "hash-object", str(path)], text=True,
        cwd=repository_root(),
    ).strip()


def source_at(root: Path, ref: str, path: str) -> bytes:
    return subprocess.check_output(["git", "show", f"{ref}:{path}"], cwd=root)


def load_bytes(data: bytes, name: str, filename: str):
    module = type(sys)(name)
    module.__file__ = filename
    sys.modules[name] = module
    exec(compile(data, filename, "exec"), module.__dict__)
    return module


def load_path(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def expected_runtime_hash(freeze: dict[str, Any], suffix: str) -> str:
    matches = [value for path, value in freeze["runtime_files"].items()
               if path.endswith(suffix)]
    if len(matches) != 1:
        raise ValueError(f"expected one frozen source ending {suffix!r}, got {len(matches)}")
    return matches[0]


def family_projection(family: dict[str, Any]) -> dict[str, Any]:
    """Fields that determine whether the downstream terminal consumer runs."""
    keys = (
        "schema", "ready", "status", "now", "minimum", "joint_support",
        "observed_products", "unobserved_products", "historical_lags",
        "product_support", "scenarios", "scenario_probabilities",
    )
    return {key: deepcopy(family.get(key)) for key in keys}


def as_interval(flow, row: dict[str, Any]):
    return flow.FlowInterval(
        int(row["step"]), row["product"], int(row["lower"]), int(row["upper"]),
        int(row["admitted_lower"]), int(row["admitted_upper"]), row["reason"],
    )


def saved_intervals(flow, record: dict[str, Any]):
    rows = []
    terminal = record.get("terminal") or {}
    for product, by_step in terminal.get("history_records", {}).items():
        for step, value in by_step.items():
            row = dict(value)
            row["step"] = int(step)
            row["product"] = product
            rows.append(as_interval(flow, row))
    return sorted(rows, key=lambda item: (item.step, PRODUCTS.index(item.product)))


def history_from(flow, intervals):
    history = flow.FlowHistory(period=24, window=5, minimum=3)
    for interval in intervals:
        history.add(interval)
    return history


def tighten_all(flow, bridge, intervals, capacity: int):
    by_step: dict[int, list[Any]] = defaultdict(list)
    for interval in intervals:
        by_step[interval.step].append(interval)
    output = []
    diagnostics = []
    for step in sorted(by_step):
        rows = sorted(by_step[step], key=lambda item: PRODUCTS.index(item.product))
        eligible = [row for row in rows if row.product in NONBUYABLE]
        ineligible = [row for row in rows if row.product not in NONBUYABLE]
        tightened, diagnostic = bridge.tighten_joint_sales(
            eligible, capacity, flow.FlowInterval,
        )
        output.extend(ineligible)
        output.extend(tightened)
        if diagnostic is not None:
            diagnostics.append(diagnostic)
    output.sort(key=lambda item: (item.step, PRODUCTS.index(item.product)))
    return output, diagnostics


def interval_delta(original, tightened):
    old = {(row.step, row.product): row for row in original}
    new = {(row.step, row.product): row for row in tightened}
    if old.keys() != new.keys():
        raise AssertionError("joint tightening changed the set of history records")
    changes = []
    for key in sorted(old, key=lambda item: (item[0], PRODUCTS.index(item[1]))):
        before, after = old[key], new[key]
        a = (before.lower, before.upper, before.admitted_lower,
             before.admitted_upper, before.reason, before.exact)
        b = (after.lower, after.upper, after.admitted_lower,
             after.admitted_upper, after.reason, after.exact)
        if a == b:
            continue
        changes.append({
            "step": key[0], "product": key[1],
            "before": {"lower": before.lower, "upper": before.upper,
                       "admitted_lower": before.admitted_lower,
                       "admitted_upper": before.admitted_upper,
                       "reason": before.reason, "exact": before.exact},
            "after": {"lower": after.lower, "upper": after.upper,
                      "admitted_lower": after.admitted_lower,
                      "admitted_upper": after.admitted_upper,
                      "reason": after.reason, "exact": after.exact},
        })
    return changes


def build_family(joint, history, config: dict[str, Any]):
    hypotheses = deepcopy(config["history_hypotheses"])
    return joint.build_joint_terminal_scenarios(
        history, PRODUCTS, 718,
        capacity=100, max_orders=10, **hypotheses,
    )


def analyze(root: Path) -> dict[str, Any]:
    bank = root / "revenue/kaggriculture/cloud-market-game-theory/consumer-history-v2"
    freeze = json.loads((bank / "SOURCE-FREEZE.json").read_text(encoding="utf-8"))
    if freeze["merge_commit"] != HISTORY_REF:
        raise AssertionError("history-v2 source ref changed")

    flow_source = source_at(root, HISTORY_REF, FLOW_PATH)
    joint_source = source_at(root, HISTORY_REF, JOINT_PATH)
    if sha256(flow_source) != expected_runtime_hash(freeze, "/reference/titan-history/flow.py"):
        raise AssertionError("frozen FlowHistory bytes do not match SOURCE-FREEZE")
    if sha256(joint_source) != expected_runtime_hash(
            freeze, "/reference/titan-history/joint_terminal_history.py"):
        raise AssertionError("frozen terminal-family bytes do not match SOURCE-FREEZE")

    bridge_path = root / BRIDGE_PATH
    if git_blob(bridge_path) != CURRENT_BRIDGE_BLOB:
        raise AssertionError("current bridge is not the PR10364 adopted blob")
    flow = load_bytes(flow_source, "birch_history_v2_flow", f"{HISTORY_REF}:{FLOW_PATH}")
    joint = load_bytes(joint_source, "birch_history_v2_joint", f"{HISTORY_REF}:{JOINT_PATH}")
    bridge = load_path(bridge_path, "birch_current_history_bridge")
    config = freeze["config_on"]

    rows = []
    original_reproduction_failures = []
    for path in sorted((bank / "results").glob("*/history_on-*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        saved_family = ((record.get("terminal") or {}).get("diagnostics") or {}).get(
            "history", {}).get("family", {})
        original_intervals = saved_intervals(flow, record)
        original_history = history_from(flow, original_intervals)
        original_family = build_family(joint, original_history, config)
        if family_projection(original_family) != family_projection(saved_family):
            original_reproduction_failures.append(str(path.relative_to(bank)))

        tightened_intervals, diagnostics = tighten_all(
            flow, bridge, original_intervals, 100,
        )
        tightened_history = history_from(flow, tightened_intervals)
        tightened_family = build_family(joint, tightened_history, config)
        changes = interval_delta(original_intervals, tightened_intervals)
        family_changed = family_projection(original_family) != family_projection(tightened_family)
        rows.append({
            "receipt": str(path.relative_to(bank)),
            "seed": record["seed"], "opponent": record["opponent"],
            "seat": record["candidate_seat"],
            "original_status": original_family["status"],
            "tightened_status": tightened_family["status"],
            "original_joint_support": original_family["joint_support"],
            "tightened_joint_support": tightened_family["joint_support"],
            "original_historical_lags": original_family["historical_lags"],
            "tightened_historical_lags": tightened_family["historical_lags"],
            "original_scenario_count": len(original_family["scenarios"]),
            "tightened_scenario_count": len(tightened_family["scenarios"]),
            "family_changed": family_changed,
            "interval_changes": changes,
            "tightening_diagnostics": diagnostics,
        })

    if original_reproduction_failures:
        raise AssertionError(
            "historical family reproduction differs for: "
            + ", ".join(original_reproduction_failures)
        )
    changed_rows = [row for row in rows if row["interval_changes"]]
    family_rows = [row for row in rows if row["family_changed"]]
    newly_ready = [row for row in rows
                   if row["original_status"] != "ready"
                   and row["tightened_status"] == "ready"]
    newly_exact = [change for row in rows for change in row["interval_changes"]
                   if not change["before"]["exact"] and change["after"]["exact"]]
    product_changes = Counter(
        change["product"] for row in rows for change in row["interval_changes"]
    )
    status_before = Counter(row["original_status"] for row in rows)
    status_after = Counter(row["tightened_status"] for row in rows)
    implication = (
        "No terminal consumer re-execution is needed: every family projection, "
        "scenario and readiness result is byte-equivalent after tightening."
        if not family_rows else
        "At least one terminal family changed; the listed receipts require a "
        "separate source-pinned terminal-input/selector execution."
    )
    return {
        "schema": "titan.consumer-history-v2.joint-capacity.v1",
        "scope": "retained result JSON only; zero actor, game, engine or provider calls",
        "historical_archive_sha256": freeze["archive_sha256"],
        "historical_source_ref": HISTORY_REF,
        "historical_flow_sha256": sha256(flow_source),
        "historical_joint_sha256": sha256(joint_source),
        "current_bridge_git_blob": git_blob(bridge_path),
        "current_helper": "tighten_joint_sales",
        "records": len(rows),
        "status_before": dict(status_before),
        "status_after": dict(status_after),
        "rows_with_interval_changes": len(changed_rows),
        "interval_changes": sum(len(row["interval_changes"]) for row in rows),
        "newly_exact_intervals": len(newly_exact),
        "changes_by_product": dict(sorted(product_changes.items())),
        "rows_with_family_changes": len(family_rows),
        "newly_ready_rows": len(newly_ready),
        "terminal_implication": implication,
        "changed_family_receipts": [row["receipt"] for row in family_rows],
        "newly_ready_receipts": [row["receipt"] for row in newly_ready],
        "rows": rows,
    }


def markdown(result: dict[str, Any]) -> str:
    lines = [
        "# Shared-capacity follow-through on the retained history-v2 bank",
        "",
        "## Result",
        "",
        f"The offline consumer reproduced all **{result['records']}** original terminal-family records from the exact frozen history-v2 source before applying the landed shared-capacity refinement.",
        "",
        f"- Family status before: `{json.dumps(result['status_before'], sort_keys=True)}`.",
        f"- Family status after: `{json.dumps(result['status_after'], sort_keys=True)}`.",
        f"- Rows with tightened intervals: **{result['rows_with_interval_changes']}**.",
        f"- Individual interval changes: **{result['interval_changes']}**; newly exact: **{result['newly_exact_intervals']}**.",
        f"- Rows whose terminal family/scenarios changed: **{result['rows_with_family_changes']}**; newly ready: **{result['newly_ready_rows']}**.",
        "",
        result["terminal_implication"],
        "",
        "## Source boundary",
        "",
        f"- Historical archive: `{result['historical_archive_sha256']}`.",
        f"- Historical source ref: `{result['historical_source_ref']}`.",
        f"- Frozen FlowHistory SHA-256: `{result['historical_flow_sha256']}`.",
        f"- Frozen terminal-family SHA-256: `{result['historical_joint_sha256']}`.",
        f"- Current bridge Git blob: `{result['current_bridge_git_blob']}`.",
        "",
        "The script reads committed `history_on-*.json` files only. It does not decompress traces, inspect realized rival actions, invoke an actor, replay an engine transition, or alter current policy/default/package state.",
        "",
        "## Reproduce",
        "",
        "```bash",
        "python -B revenue/kaggriculture/cloud-market-game-theory/consumer-history-v2/joint-capacity/reanalyze.py --output /tmp/history-v2-joint-capacity",
        "```",
        "",
        "The JSON output retains every per-receipt interval and family delta.",
    ]
    if result["changes_by_product"]:
        lines.extend(["", "Changes by product: `" + json.dumps(
            result["changes_by_product"], sort_keys=True) + "`."])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = repository_root()
    result = analyze(root)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "RESULT.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (args.output / "RESULT.md").write_text(markdown(result), encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "rows"},
                     sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
