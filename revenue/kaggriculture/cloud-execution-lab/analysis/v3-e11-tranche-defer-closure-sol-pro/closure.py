#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exact-source audit for the TITAN V3 E11 -> L01 tranche composition boundary.

The audit intentionally does not modify the candidate.  It executes the two public
pure-function seams in runtime order and proves whether a SELL that E11 explicitly
deferred is reintroduced by a later finalizer in the same returned action.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any, Mapping, Sequence

SCHEMA = "titan.v3-e11-tranche-defer-closure.v1"
TOKEN_SCHEMA = "titan.v3-e11-deferral-token.v1"
VULNERABLE = "VULNERABLE_REINTRODUCTION"
CLOSED = "CLOSED"
INVALID = "INVALID_EVIDENCE"

AUTHENTICATED_PACKET = {
    "slack_file_id": "F0C0JPCAAQP",
    "sha256": "f68792bf7f0fb269864ef4ab25967292e2d4cd03439dbc5c52b98dfcebd1b728",
    "bytes": 27500,
    "source_commit_seen": "0e7ea5f2bd78040dfc38758d08b149f392c1fb3b",
}
EXPECTED_SOURCE_SHA256 = {
    "apply_v3.py": "8e1093429a1bb463e2b82490963b43d9c9a4fcbd16f9d1b8d02fd75434f84436",
    "overlay/e11_rival_sell.py": "0871703888bfd128a9118c0fd59fa6c6a7b4ce509d22d803b97255622bff4816",
    "overlay/l01_mechanics.py": "65fc1841f6d00b6db78e2eb88d98e9e7b05053502e0de527bce1f1a60fbe9691",
}


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def sha256_bytes(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def action_sha256(action: Mapping[str, Any]) -> str:
    return sha256_bytes(canonical_bytes(action))


def _load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module {name!r} from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def resolve_source_paths(candidate_root: Path) -> dict[str, Path]:
    """Resolve either the source-tree shape (overlay/) or a materialized package root."""
    source_shape = {
        "apply_v3.py": candidate_root / "apply_v3.py",
        "overlay/e11_rival_sell.py": candidate_root / "overlay" / "e11_rival_sell.py",
        "overlay/l01_mechanics.py": candidate_root / "overlay" / "l01_mechanics.py",
    }
    materialized_shape = {
        "apply_v3.py": candidate_root / "apply_v3.py",
        "overlay/e11_rival_sell.py": candidate_root / "e11_rival_sell.py",
        "overlay/l01_mechanics.py": candidate_root / "l01_mechanics.py",
    }
    for shape in (source_shape, materialized_shape):
        if all(path.is_file() for path in shape.values()):
            return shape
    missing = sorted(str(path) for path in source_shape.values() if not path.is_file())
    raise FileNotFoundError("candidate root does not contain the required V3 sources: " + ", ".join(missing))


def market_limit(config: Mapping[str, Any] | None) -> int:
    """Mirror the official max(1, int(maxMarketOrdersPerTurn)) prefix rule."""
    cfg = config if isinstance(config, Mapping) else {}
    try:
        return max(1, int(cfg.get("maxMarketOrdersPerTurn", 10)))
    except (TypeError, ValueError):
        return 10


def executable_sell_items(action: Mapping[str, Any], config: Mapping[str, Any] | None) -> list[str]:
    market = action.get("market", []) if isinstance(action, Mapping) else []
    if not isinstance(market, list):
        return []
    items: list[str] = []
    for order in market[: market_limit(config)]:
        if isinstance(order, list) and len(order) > 1 and order[0] == "SELL":
            items.append(str(order[1]))
    return items


def _normalized_deferred(report: Mapping[str, Any] | None) -> tuple[str, ...]:
    if not isinstance(report, Mapping):
        return ()
    if report.get("enabled") is not True or report.get("changed") is not True:
        return ()
    reason = report.get("reason")
    raw = report.get("deferred")
    if not isinstance(reason, str) or not reason.startswith("PUBLIC_PRICE_DROP_DEFER_"):
        return ()
    if not isinstance(raw, list) or not raw:
        return ()
    values: list[str] = []
    for item in raw:
        if not isinstance(item, str) or not item:
            return ()
        if item not in values:
            values.append(item)
    expected_reason = "PUBLIC_PRICE_DROP_DEFER_" + ",".join(sorted(values))
    if reason != expected_reason:
        return ()
    return tuple(values)


def _turn_bind(context: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(context, Mapping):
        return None
    try:
        step = int(context["step"])
        player = int(context["player"])
    except (KeyError, TypeError, ValueError):
        return None
    turn_bind: dict[str, Any] = {"step": step, "player": player}
    for key in ("route_id", "candidate_id"):
        value = context.get(key)
        if value is not None:
            if not isinstance(value, (str, int)):
                return None
            turn_bind[key] = value
    return turn_bind


def make_deferral_token(
    source_action: Mapping[str, Any],
    report: Mapping[str, Any] | None,
    context: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    """Create an ephemeral, action- and turn-bound sidecar after E11 returns."""
    blocked = _normalized_deferred(report)
    turn_bind = _turn_bind(context)
    if not blocked or turn_bind is None:
        return None
    body: dict[str, Any] = {
        "schema": TOKEN_SCHEMA,
        "context": turn_bind,
        "source_action_sha256": action_sha256(source_action),
        "report_sha256": sha256_bytes(canonical_bytes(report)),
        "deferred": list(blocked),
    }
    body["token_sha256"] = sha256_bytes(canonical_bytes(body))
    return body


def deferred_authority(
    report: Mapping[str, Any] | None,
    token: Mapping[str, Any] | None,
    source_action: Mapping[str, Any] | None,
    context: Mapping[str, Any] | None,
) -> tuple[str, ...]:
    """Accept only a same-call E11 token bound to report, source action, turn and player."""
    blocked = _normalized_deferred(report)
    turn_bind = _turn_bind(context)
    if not blocked or turn_bind is None or not isinstance(token, Mapping):
        return ()
    if token.get("schema") != TOKEN_SCHEMA or token.get("context") != turn_bind:
        return ()
    if token.get("deferred") != list(blocked):
        return ()
    if token.get("report_sha256") != sha256_bytes(canonical_bytes(report)):
        return ()
    source_digest = token.get("source_action_sha256")
    if not isinstance(source_digest, str) or len(source_digest) != 64:
        return ()
    if not isinstance(source_action, Mapping) or source_digest != action_sha256(source_action):
        return ()
    claimed_token_sha = token.get("token_sha256")
    token_body = dict(token)
    token_body.pop("token_sha256", None)
    if claimed_token_sha != sha256_bytes(canonical_bytes(token_body)):
        return ()
    return blocked


def enforce_deferred_sell_ownership(
    action: Mapping[str, Any],
    e11_report: Mapping[str, Any] | None,
    authority_token: Mapping[str, Any] | None,
    e11_source_action: Mapping[str, Any] | None,
    context: Mapping[str, Any] | None,
    config: Mapping[str, Any] | None = None,
) -> tuple[Mapping[str, Any], dict[str, Any]]:
    """Narrow repair primitive for a final-action composition seam.

    Only executable SELL rows for items owned by an affirmative E11 deferral are
    blanked. Literal indices, every unrelated order, the non-executable suffix, and
    the input object remain unchanged.  Invalid/stale reports have no authority.
    """
    blocked = deferred_authority(e11_report, authority_token, e11_source_action, context)
    repair: dict[str, Any] = {
        "authority": bool(blocked),
        "blocked_items": list(blocked),
        "changed": False,
        "removed_indices": [],
        "reason": "NO_VALID_E11_AUTHORITY" if not blocked else "NO_REINTRODUCTION",
    }
    if not blocked:
        return action, repair
    market = action.get("market", []) if isinstance(action, Mapping) else []
    if not isinstance(market, list):
        repair["reason"] = "BAD_MARKET_QUEUE"
        return action, repair
    cap = market_limit(config)
    indices = [
        index
        for index, order in enumerate(market[:cap])
        if isinstance(order, list)
        and len(order) > 1
        and order[0] == "SELL"
        and str(order[1]) in blocked
    ]
    if not indices:
        return action, repair
    out = deepcopy(action)
    out_market = list(out.get("market") or [])
    for index in indices:
        out_market[index] = []
    out["market"] = out_market
    repair.update(
        changed=True,
        removed_indices=indices,
        reason="REMOVED_REINTRODUCED_DEFERRED_SELLS",
    )
    return out, repair


def synthetic_case() -> tuple[dict[str, Any], dict[str, Any], list[Any], dict[str, Any]]:
    observation = {
        "step": 696,
        "day": 29,
        "player": 0,
        "market": {"prices": {"WHEAT": 10}, "inventory": {"WHEAT": 50}},
        "town": {"unlocked_shops": ["BAKERY"]},
        "private": {"shed": {"WHEAT": 80, "CARROT": 40}},
    }
    action = {"farmer": ["PASS"], "hands": [], "market": [["SELL", "WHEAT", 4]]}
    history = [(690, {"WHEAT": 40})]
    config = {
        "episodeSteps": 720,
        "maxMarketOrdersPerTurn": 10,
        "rival_dump_lookback_steps": 8,
        "e11_min_future_absorption": 2,
    }
    return observation, action, history, config


def exact_absorption(item: str, step: int, _shops: Sequence[str], _config: Mapping[str, Any]) -> int:
    return 2 if item == "WHEAT" and step == 700 else 0


def run_probe(candidate_root: Path) -> dict[str, Any]:
    paths = resolve_source_paths(candidate_root)
    source_sha256 = {name: sha256_file(path) for name, path in sorted(paths.items())}
    source_match = {name: source_sha256[name] == expected for name, expected in EXPECTED_SOURCE_SHA256.items()}

    e11 = _load_module("audit_v3_e11_rival_sell", paths["overlay/e11_rival_sell.py"])
    l01 = _load_module("audit_v3_l01_mechanics", paths["overlay/l01_mechanics.py"])
    observation, input_action, history, config = synthetic_case()
    input_before = deepcopy(input_action)

    after_e11, e11_report = e11.apply_e11(
        observation,
        input_action,
        history,
        config,
        exact_absorption,
        enabled=True,
    )
    flags = {key: False for key in l01.FLAG_KEYS}
    flags["TRANCHE"] = True
    activations = Counter()
    after_tranche = l01.apply_tranche(
        after_e11,
        observation,
        flags,
        activations,
        shed=observation["private"]["shed"],
    )

    authority_token = make_deferral_token(after_e11, e11_report, observation)
    deferred = deferred_authority(e11_report, authority_token, after_e11, observation)
    final_sells = executable_sell_items(after_tranche, config)
    reintroduced = sorted(set(deferred).intersection(final_sells))
    status = VULNERABLE if reintroduced else CLOSED

    repaired, repair_report = enforce_deferred_sell_ownership(
        after_tranche, e11_report, authority_token, after_e11, observation, config
    )
    repaired_again, second_report = enforce_deferred_sell_ownership(
        repaired, e11_report, authority_token, after_e11, observation, config
    )
    repaired_sells = executable_sell_items(repaired, config)
    repair_invariants = {
        "input_unchanged": input_action == input_before,
        "e11_deferred_absent_immediately": not set(deferred).intersection(executable_sell_items(after_e11, config)),
        "repair_removes_all_executable_reintroductions": not set(deferred).intersection(repaired_sells),
        "repair_preserves_nondeferred_carrot": "CARROT" in repaired_sells,
        "repair_idempotent_value": repaired_again == repaired,
        "repair_second_call_object_identity": repaired_again is repaired,
        "repair_second_call_no_change": second_report["changed"] is False,
    }

    receipt: dict[str, Any] = {
        "schema": SCHEMA,
        "operation": "titan-v3-e11-tranche-defer-closure-20260910-01",
        "authenticated_packet": AUTHENTICATED_PACKET,
        "source_sha256": source_sha256,
        "expected_source_match": source_match,
        "runtime_order": ["e11_before_pending", "finish_production", "l01_tranche_finalizer"],
        "case": {
            "observation": observation,
            "input_action": input_before,
            "price_history": history,
            "config": config,
        },
        "e11": {
            "action": after_e11,
            "action_sha256": action_sha256(after_e11),
            "report": e11_report,
            "deferred_authority": list(deferred),
            "authority_token": authority_token,
        },
        "tranche": {
            "action": after_tranche,
            "action_sha256": action_sha256(after_tranche),
            "activations": dict(activations),
            "executable_sell_items": final_sells,
        },
        "classification": {
            "status": status,
            "reintroduced_deferred_items": reintroduced,
        },
        "repair_handoff": {
            "action": repaired,
            "action_sha256": action_sha256(repaired),
            "report": repair_report,
            "invariants": repair_invariants,
        },
    }
    receipt["receipt_sha256"] = sha256_bytes(canonical_bytes(receipt))
    return receipt


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-root", required=True, type=Path)
    parser.add_argument("--receipt-out", type=Path)
    parser.add_argument("--expect-status", choices=(VULNERABLE, CLOSED, INVALID))
    parser.add_argument("--require-exact-source", action="store_true")
    args = parser.parse_args(argv)

    try:
        receipt = run_probe(args.candidate_root)
    except Exception as exc:  # audit boundary: retain a deterministic invalid receipt
        receipt = {
            "schema": SCHEMA,
            "operation": "titan-v3-e11-tranche-defer-closure-20260910-01",
            "classification": {"status": INVALID, "error": type(exc).__name__, "detail": str(exc)},
        }
        receipt["receipt_sha256"] = sha256_bytes(canonical_bytes(receipt))

    text = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    if args.receipt_out:
        args.receipt_out.parent.mkdir(parents=True, exist_ok=True)
        args.receipt_out.write_text(text, encoding="utf-8")
    print(text, end="")

    status = receipt["classification"]["status"]
    if args.expect_status and status != args.expect_status:
        return 2
    if args.require_exact_source and not all(receipt.get("expected_source_match", {}).values()):
        return 3
    if status == INVALID:
        return 4
    if not all(receipt.get("repair_handoff", {}).get("invariants", {}).values()):
        return 5
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
