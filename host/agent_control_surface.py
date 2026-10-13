#!/usr/bin/env python3
"""Compile and validate one compact provider-neutral Commons read model."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PROVIDER_KINDS = {
    "AGENT_EXECUTION_ROAD",
    "AGENT_FLEET",
    "AGENT_ROUTER",
    "MODEL_FLEET",
    "SUBSCRIPTION",
}
STAGE_RANK = {
    "PRODUCING": 0,
    "EXERCISED": 1,
    "ASSIGNED": 2,
    "REACHABLE": 3,
    "AVAILABLE": 4,
    "DECLARED": 5,
}
PROVENANCE = (
    "https://github.com/pingdotgg/t3code",
    "https://github.com/pingdotgg/t3code/blob/main/docs/internals/overview.md",
)


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _first_line(value: Any, limit: int = 220) -> str:
    lines = str(value or "").splitlines()
    if not lines:
        return ""
    line = " ".join(lines[0].split())
    return line if len(line) <= limit else line[: limit - 1] + "…"


def compile_surface(
    discovery: dict[str, Any],
    pulse: dict[str, Any],
    recent: list[dict[str, Any]],
    ledger: dict[str, Any],
) -> dict[str, Any]:
    if discovery.get("schema") != "commons-agent-discovery/v1":
        raise ValueError("agent discovery schema")
    if not isinstance(pulse.get("seq"), int) or not pulse.get("head"):
        raise ValueError("pulse")
    if not isinstance(recent, list):
        raise ValueError("recent")
    if ledger.get("schema") != "commons-resource-ledger/v2":
        raise ValueError("resource ledger schema")

    providers = []
    for row in ledger.get("surfaces") or []:
        if not isinstance(row, dict) or row.get("kind") not in PROVIDER_KINDS:
            continue
        providers.append({
            key: row[key]
            for key in (
                "name",
                "kind",
                "stage",
                "condition",
                "consumer",
                "next_action",
                "last_used_at",
                "stale_after",
            )
            if row.get(key) not in (None, "")
        })
    providers.sort(key=lambda row: (STAGE_RANK.get(str(row.get("stage")), 99), str(row.get("name"))))

    activity = []
    for row in recent[:12]:
        if not isinstance(row, dict) or not row.get("id"):
            continue
        item = {
            key: row[key]
            for key in ("id", "from", "to", "ts", "state", "kind", "href")
            if row.get(key) not in (None, "")
        }
        item["summary"] = _first_line(row.get("body"))
        activity.append(item)

    commands = [
        {
            "id": str(row.get("type") or ""),
            "href": str(row.get("url") or ""),
            "preferred": bool(row.get("preferred")),
        }
        for row in discovery.get("contact_methods") or []
        if isinstance(row, dict) and row.get("type") and row.get("url")
    ]

    snapshot = ledger.get("snapshot") or {}
    return {
        "schema": "commons-agent-control-surface/v1",
        "access": "open",
        "source_of_truth": "git-head",
        "head": pulse["head"],
        "seq": pulse["seq"],
        "observed_at": pulse.get("ts") or snapshot.get("observed_at") or "",
        "provider_count": len(providers),
        "providers": providers,
        "recent": activity,
        "commands": commands,
        "continuity": discovery.get("continuity") or {},
        "refresh": {
            "read_first": "pulse.json",
            "read_if_seq_advanced": "recent.json",
            "durable_receipts": "p/",
        },
        "design": {
            "pattern": "one provider-neutral read model for phone, web, desktop, and agents",
            "provider_specific_runtime_stays_behind_driver": True,
            "commands_and_receipts_are_distinct": True,
            "provenance": list(PROVENANCE),
        },
    }


def build(root: Path = ROOT) -> dict[str, Any]:
    return compile_surface(
        load_json(root / "agent-discovery.json"),
        load_json(root / "pulse.json"),
        load_json(root / "recent.json"),
        load_json(root / "ground" / "RESOURCE_LEDGER.json"),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("validate", "print"), nargs="?", default="validate")
    args = parser.parse_args()
    if args.command == "print":
        print(canonical(build()), end="")
        return 0
    build()
    print("VALID commons-agent-control-surface/v1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
