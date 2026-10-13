# SPDX-License-Identifier: Apache-2.0
"""Measure bounded interval-history coverage on the retained history-v2 bank.

The saved result JSON is the only experiment input. Exact historical source
and the current joint-capacity bridge are reused through the landed
``joint-capacity/reanalyze.py`` consumer. No actor, engine, trace, current
rival action, policy default, canonical archive, or provider is invoked.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any

HERE = Path(__file__).resolve().parent
BANK = HERE.parent
JOINT_CAPACITY = BANK / "joint-capacity" / "reanalyze.py"


def load_path(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


intervals = load_path(HERE / "interval_family.py", "birch_interval_family")
prior = load_path(JOINT_CAPACITY, "birch_joint_capacity_reanalysis")


def scenario_projection(family: dict[str, Any]) -> list[dict[str, Any]]:
    """The economic scenario inputs; provenance wording is intentionally omitted."""
    return sorted(
        ({"shed": deepcopy(row["shed"]), "market": deepcopy(row["market"])}
         for row in family.get("scenarios", ())),
        key=lambda row: json.dumps(row, sort_keys=True, separators=(",", ":")),
    )


def analyze(root: Path) -> dict[str, Any]:
    freeze = json.loads((BANK / "SOURCE-FREEZE.json").read_text(encoding="utf-8"))
    if freeze["merge_commit"] != prior.HISTORY_REF:
        raise AssertionError("history-v2 source ref changed")

    flow_source = prior.source_at(root, prior.HISTORY_REF, prior.FLOW_PATH)
    joint_source = prior.source_at(root, prior.HISTORY_REF, prior.JOINT_PATH)
    if prior.sha256(flow_source) != prior.expected_runtime_hash(
            freeze, "/reference/titan-history/flow.py"):
        raise AssertionError("frozen FlowHistory bytes do not match SOURCE-FREEZE")
    if prior.sha256(joint_source) != prior.expected_runtime_hash(
            freeze, "/reference/titan-history/joint_terminal_history.py"):
        raise AssertionError("frozen terminal-family bytes do not match SOURCE-FREEZE")

    bridge_path = root / prior.BRIDGE_PATH
    if prior.git_blob(bridge_path) != prior.CURRENT_BRIDGE_BLOB:
        raise AssertionError("current bridge is not the PR10364 adopted blob")
    flow = prior.load_bytes(
        flow_source, "birch_interval_history_flow",
        f"{prior.HISTORY_REF}:{prior.FLOW_PATH}",
    )
    joint = prior.load_bytes(
        joint_source, "birch_interval_history_joint",
        f"{prior.HISTORY_REF}:{prior.JOINT_PATH}",
    )
    bridge = prior.load_path(bridge_path, "birch_interval_history_bridge")
    config = freeze["config_on"]

    rows: list[dict[str, Any]] = []
    reproduction_failures: list[str] = []
    exact_parity_failures: list[str] = []
    for path in sorted((BANK / "results").glob("*/history_on-*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        saved_family = ((record.get("terminal") or {}).get("diagnostics") or {}).get(
            "history", {}).get("family", {})
        original_intervals = prior.saved_intervals(flow, record)
        tightened_intervals, tightening_diagnostics = prior.tighten_all(
            flow, bridge, original_intervals, 100,
        )
        history = prior.history_from(flow, tightened_intervals)
        exact_family = prior.build_family(joint, history, config)
        if prior.family_projection(exact_family) != prior.family_projection(saved_family):
            reproduction_failures.append(str(path.relative_to(BANK)))

        interval_family = intervals.build_interval_terminal_scenarios(
            history, prior.PRODUCTS, 718,
            capacity=100,
            max_orders=10,
            max_scenarios=32,
            **deepcopy(config["history_hypotheses"]),
        )
        if exact_family.get("ready"):
            parity = intervals.build_interval_terminal_scenarios(
                history, prior.PRODUCTS, 718,
                capacity=100,
                max_orders=10,
                max_scenarios=32,
                candidate_lags=exact_family["historical_lags"],
                **deepcopy(config["history_hypotheses"]),
            )
            if (not parity.get("ready")
                    or scenario_projection(parity) != scenario_projection(exact_family)):
                exact_parity_failures.append(str(path.relative_to(BANK)))

        newly_ready = not exact_family.get("ready") and interval_family.get("ready")
        rows.append({
            "receipt": str(path.relative_to(BANK)),
            "seed": record["seed"],
            "opponent": record["opponent"],
            "seat": record["candidate_seat"],
            "exact_status": exact_family["status"],
            "exact_joint_support": exact_family["joint_support"],
            "exact_scenarios": len(exact_family["scenarios"]),
            "interval_status": interval_family["status"],
            "interval_joint_support": interval_family["joint_support"],
            "interval_lags": interval_family["historical_lags"],
            "interval_scenarios": len(interval_family["scenarios"]),
            "newly_ready": newly_ready,
            "vector_counts": interval_family.get("vector_counts", []),
            "unique_vectors_at_least": interval_family.get("unique_vectors_at_least"),
            "unique_scenarios_at_least": interval_family.get("unique_scenarios_at_least"),
            "tightening_steps": len(tightening_diagnostics),
        })

    if reproduction_failures:
        raise AssertionError(
            "saved family reproduction differs for: " + ", ".join(reproduction_failures)
        )
    if exact_parity_failures:
        raise AssertionError(
            "interval consumer changed exact scenario inputs for: "
            + ", ".join(exact_parity_failures)
        )
    statuses = Counter(row["interval_status"] for row in rows)
    newly_ready = [row for row in rows if row["newly_ready"]]
    exact_unready = [row for row in rows if row["exact_status"] != "ready"]
    implication = (
        "At least one formerly incomplete family is now fully enumerated; only "
        "the listed retained receipts should advance to terminal input/selector execution."
        if newly_ready else
        "No formerly incomplete family fits the complete bounded interval family; "
        "the existing fallback remains correct and no terminal selector execution is needed."
    )
    return {
        "schema": "titan.consumer-history-v2.interval-family-scan.v1",
        "scope": "64 committed result JSON records; zero actor, game, engine, trace or provider calls",
        "historical_archive_sha256": freeze["archive_sha256"],
        "historical_source_ref": prior.HISTORY_REF,
        "current_bridge_git_blob": prior.git_blob(bridge_path),
        "records": len(rows),
        "exact_unready_records": len(exact_unready),
        "interval_statuses": dict(sorted(statuses.items())),
        "newly_ready_records": len(newly_ready),
        "newly_ready_receipts": [row["receipt"] for row in newly_ready],
        "terminal_implication": implication,
        "rows": rows,
    }


def markdown(result: dict[str, Any]) -> str:
    lines = [
        "# Complete interval-family scan of retained history-v2 evidence",
        "",
        "The scan first reproduces every saved family with the frozen exact-history source, then applies the current shared-capacity bridge and the complete bounded interval-family consumer.",
        "",
        f"- Records: **{result['records']}**.",
        f"- Exact-history incomplete records: **{result['exact_unready_records']}**.",
        f"- Interval-family statuses: `{json.dumps(result['interval_statuses'], sort_keys=True)}`.",
        f"- Newly ready records: **{result['newly_ready_records']}**.",
        "",
        result["terminal_implication"],
        "",
        "No marginal endpoints are combined independently. Every reported ready interval family enumerates its complete feasible integer set under one shared shed-capacity constraint. Vector or scenario overflow returns no partial family.",
        "",
        "## Reproduce",
        "",
        "```bash",
        "python -B revenue/kaggriculture/cloud-market-game-theory/consumer-history-v2/interval-family/test_interval_family.py -v",
        "python -B revenue/kaggriculture/cloud-market-game-theory/consumer-history-v2/interval-family/scan_bank.py --output /tmp/history-v2-interval-family",
        "```",
    ]
    if result["newly_ready_receipts"]:
        lines.extend(["", "Newly ready receipts:", ""])
        lines.extend(f"- `{path}`" for path in result["newly_ready_receipts"])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = prior.repository_root()
    result = analyze(root)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "SCAN.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (args.output / "SCAN.md").write_text(markdown(result), encoding="utf-8")
    compact = {key: value for key, value in result.items() if key != "rows"}
    print(json.dumps(compact, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
