#!/usr/bin/env python3
"""Build the bounded ROADEF rank-traversal restart-budget candidate.

This generator is source-only. It never runs the solver or submits anything.
It accepts exactly the released cloud-rank-traversal main.cpp bytes, applies a
small scheduler-only transformation, and writes a candidate, unified diff, and
receipt.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
from pathlib import Path

BASE_SHA256 = "d85ee6187607b1e04c9d77073d42e3eba699fe42309ee3f3324f25528a8f945e"
BASE_SIZE = 50_431
SCHEMA = "roadef.rank-restart-budget.source-receipt.v1"


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise ValueError(f"{label}: expected exactly one anchor, found {count}")
    return text.replace(old, new, 1)


def transform_text(text: str) -> str:
    """Apply only the bounded scheduler/diagnostic transformation."""
    text = _replace_once(
        text,
        '        int passLimit = static_cast<int>(std::min(128.0, setting("FLEET_RANK1_PASSES", 16)));\n'
        '        int demandLimitSetting = static_cast<int>(std::min(256.0, setting("FLEET_RANK1_DEMANDS", 32)));',
        '        int passLimit = static_cast<int>(std::min(128.0, setting("FLEET_RANK1_PASSES", 16)));\n'
        '        int restartLimit = static_cast<int>(std::min(128.0, setting("FLEET_RANK1_RESTARTS", passLimit)));\n'
        '        int demandLimitSetting = static_cast<int>(std::min(256.0, setting("FLEET_RANK1_DEMANDS", 32)));',
        "restart setting",
    )
    text = _replace_once(
        text,
        '        int rankCursor = 0;\n'
        '        std::vector<int> coordinateOrder;',
        '        int rankCursor = 0;\n'
        '        int noGainPasses = 0, restartCount = 0;\n'
        '        std::vector<int> coordinateOrder;',
        "scheduler counters",
    )
    text = _replace_once(
        text,
        '        for (int pass = 0; pass < passLimit && !finished(); ++pass) {',
        '        for (int pass = 0;\n'
        '             (rankTraversal ? noGainPasses < passLimit : pass < passLimit) && !finished();\n'
        '             ++pass) {',
        "loop budget",
    )
    text = _replace_once(
        text,
        '            if (accepted != acceptedBefore) {\n'
        '                rankCursor = 0;\n'
        '            } else if (++rankCursor >= rankLimit) {\n'
        '                schedulerStop = "configured_sweep_exhaustion";\n'
        '                break;\n'
        '            }',
        '            if (accepted != acceptedBefore) {\n'
        '                ++restartCount;\n'
        '                if (restartCount >= restartLimit) {\n'
        '                    schedulerStop = "restart_budget";\n'
        '                    break;\n'
        '                }\n'
        '                rankCursor = 0;\n'
        '            } else {\n'
        '                ++noGainPasses;\n'
        '                if (++rankCursor >= rankLimit) {\n'
        '                    schedulerStop = "configured_sweep_exhaustion";\n'
        '                    break;\n'
        '                }\n'
        '            }',
        "restart accounting",
    )
    text = _replace_once(
        text,
        '                      << ",\\\"pass_limit\\\":" << passLimit << ",\\\"rank_limit\\\":" << rankLimit\n'
        '                      << ",\\\"last_selected_rank\\\":"',
        '                      << ",\\\"pass_limit\\\":" << passLimit\n'
        '                      << ",\\\"no_gain_passes\\\":" << noGainPasses\n'
        '                      << ",\\\"restart_limit\\\":" << restartLimit\n'
        '                      << ",\\\"restarts\\\":" << restartCount\n'
        '                      << ",\\\"rank_limit\\\":" << rankLimit\n'
        '                      << ",\\\"last_selected_rank\\\":"',
        "stop diagnostics",
    )
    text = _replace_once(
        text,
        '                out << ",\\\"rank_traversal\\\":true,\\\"rank_limit\\\":" << rankLimit\n'
        '                    << ",\\\"stop_reason\\\":\\\"" << schedulerStop << "\\\"";',
        '                out << ",\\\"rank_traversal\\\":true,\\\"rank_limit\\\":" << rankLimit\n'
        '                    << ",\\\"no_gain_passes\\\":" << noGainPasses\n'
        '                    << ",\\\"restart_limit\\\":" << restartLimit\n'
        '                    << ",\\\"restarts\\\":" << restartCount\n'
        '                    << ",\\\"stop_reason\\\":\\\"" << schedulerStop << "\\\"";',
        "report diagnostics",
    )
    return text


def build(base: Path, output: Path, patch: Path, receipt: Path) -> dict[str, object]:
    raw = base.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if len(raw) != BASE_SIZE or digest != BASE_SHA256:
        raise ValueError(
            f"base mismatch: expected {BASE_SIZE} bytes sha256 {BASE_SHA256}, "
            f"found {len(raw)} bytes sha256 {digest}"
        )
    source = raw.decode("utf-8")
    candidate = transform_text(source)
    out_raw = candidate.encode("utf-8")
    output.write_bytes(out_raw)
    diff = "".join(
        difflib.unified_diff(
            source.splitlines(keepends=True),
            candidate.splitlines(keepends=True),
            fromfile="cloud-rank-traversal/main.cpp",
            tofile="cloud-rank-restart-budget/main.cpp",
        )
    )
    patch.write_text(diff, encoding="utf-8")
    data: dict[str, object] = {
        "schema": SCHEMA,
        "base": {"size": len(raw), "sha256": digest},
        "candidate": {
            "size": len(out_raw),
            "sha256": hashlib.sha256(out_raw).hexdigest(),
        },
        "patch": {
            "size": len(diff.encode("utf-8")),
            "sha256": hashlib.sha256(diff.encode("utf-8")).hexdigest(),
        },
        "scheduler": {
            "pass_budget_semantics": "non-accepting rank probes",
            "restart_budget_setting": "FLEET_RANK1_RESTARTS",
            "restart_budget_default": "FLEET_RANK1_PASSES",
            "restart_budget_max": 128,
            "wall_clock_guard_changed": False,
            "acceptance_or_feasibility_changed": False,
        },
    }
    receipt.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return data


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("base", type=Path)
    parser.add_argument("--output", type=Path, default=Path("restart-budget-main.cpp"))
    parser.add_argument("--patch", type=Path, default=Path("restart-budget.patch"))
    parser.add_argument("--receipt", type=Path, default=Path("SOURCE-RECEIPT.generated.json"))
    args = parser.parse_args()
    data = build(args.base, args.output, args.patch, args.receipt)
    print(json.dumps(data, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
