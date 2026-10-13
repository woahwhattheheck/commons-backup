"""Stateless public-input and exact route-table diagnostics for frozen COK V10.

Predicate truth is not controller activation. Use the sibling
cloud-opponent-observer CokObserver for actual persisted routing state.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

SOURCE_SHA256 = "56831f3c43c9727d90016b7a7a8d4eb51d1a4c08c1120d58f061d9176e8bc109"
SOURCE_REF = "7ef67eac458cd9ecd13786063e2e581fbe7403ec"


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def load_source(path: str | Path) -> dict[str, Any]:
    """Load the explicitly supplied, pinned policy; never fetch remote code."""
    path = Path(path).resolve(strict=True)
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != SOURCE_SHA256:
        raise ValueError("COK source differs from the frozen V10 diagnostic contract")
    namespace: dict[str, Any] = {"__name__": "cok_v10_diagnostic_source", "__file__": str(path)}
    exec(compile(data, str(path), "exec"), namespace)
    return namespace


def gate_facts(namespace: Mapping[str, Any], observation: Mapping[str, Any]) -> dict[str, Any]:
    """Report public predicate inputs, without claiming the selector executed."""
    seat = namespace["_seat"](observation)
    farms = observation.get("farms")
    own = rival = None
    counts = None
    if isinstance(farms, (list, tuple)) and len(farms) >= 2:
        own = namespace["_v10_public_money"](farms[seat])
        rival = namespace["_v10_public_money"](farms[1 - seat])
        counts = namespace["_v10_opening_tile_counts"](farms[1 - seat])
    shops = list(namespace["_public_shops"](observation))
    complete = own is not None and rival is not None and counts is not None and bool(shops)
    tests = {
        "first_shop": shops[0] in ("BAKERY", "PIZZA_SHOP") if shops else False,
        "rival_cow_1": counts["COW"] == 1 if counts is not None else False,
        "rival_sheep_4": counts["SHEEP"] == 4 if counts is not None else False,
        "rival_wheat_5": counts["WHEAT"] == 5 if counts is not None else False,
        "rival_melon_4_or_5": counts["MELON"] in (4, 5) if counts is not None else False,
        "own_cash_below_rival": own < rival if own is not None and rival is not None else False,
    }
    return {"seat": seat, "shops": shops, "own_public_cash": own,
            "rival_public_cash": rival, "rival_counts": dict(counts) if counts is not None else None,
            "complete_public_inputs": complete, "conditions": tests,
            "predicate": bool(namespace["_v10_should_use_v5"](observation))}


def route_name(namespace: Mapping[str, Any], actions: Any) -> str:
    for key in ("LOW", "HIGH"):
        if actions is namespace[f"_V5_{key}_ACTIONS"]:
            return f"v5_{key.lower()}"
    for family in ("CURRENT", "LEGACY"):
        for label, candidate in namespace[f"_V7_{family}_ROUTES"].items():
            if actions is candidate:
                return f"{family.lower()}:{label}"
    return "unidentified"


def route_prefixes(namespace: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Exact action-table prefixes, not proof of controller-state compatibility."""
    routes = {f"v5_{key.lower()}": namespace[f"_V5_{key}_ACTIONS"] for key in ("LOW", "HIGH")}
    for family in ("CURRENT", "LEGACY"):
        routes.update({f"{family.lower()}:{k}": v for k, v in namespace[f"_V7_{family}_ROUTES"].items()})
    output = []
    for left, left_actions in routes.items():
        if not left.startswith("v5_"):
            continue
        for right, right_actions in routes.items():
            if left == right or (left == "v5_high" and right == "v5_low"):
                continue
            shared = min(len(left_actions), len(right_actions))
            first = next((i for i in range(shared) if left_actions[i] != right_actions[i]), None)
            if first is None and len(left_actions) != len(right_actions):
                first = shared
            output.append({"left": left, "right": right, "left_steps": len(left_actions),
                           "right_steps": len(right_actions), "first_action_difference": first,
                           "equal_before_72": first is None or first >= 72,
                           "equal_before_168": first is None or first >= 168})
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--observations", type=Path,
                        help="JSONL objects with observation; stateless facts only")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    for incoming in (args.source, args.observations):
        if incoming is None:
            continue
        try:
            aliases = args.output.resolve() == incoming.resolve()
            if args.output.exists() and incoming.exists():
                aliases = aliases or args.output.samefile(incoming)
        except (OSError, RuntimeError) as exc:
            parser.error(f"Cannot verify input/output identity: {type(exc).__name__}")
        if aliases:
            parser.error("Report output must not alias a source or observation input")
    namespace = load_source(args.source)
    facts = []
    if args.observations:
        with args.observations.open(encoding="utf-8") as stream:
            for line in stream:
                if line.strip():
                    row = json.loads(line)
                    obs = row["observation"]
                    facts.append({"step": obs.get("step"), **gate_facts(namespace, obs)})
    report = {"schema": "titan.cok-source-discriminators.v1", "source_ref": SOURCE_REF,
              "source_sha256": SOURCE_SHA256, "route_prefixes": route_prefixes(namespace),
              "public_facts": facts, "activation_measured": False}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
