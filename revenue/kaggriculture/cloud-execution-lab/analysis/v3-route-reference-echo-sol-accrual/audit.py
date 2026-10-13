# SPDX-License-Identifier: Apache-2.0
"""Audit the exact current route-reference echo source seam and route surface."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
from collections.abc import Mapping, Sequence
from typing import Any

EXPECTED_FROZEN_SELECTED_BLOB = "fc7baf5c179818a55037f6a61d92984d81d1a21c"
EXPECTED_MAIN_BLOB = "4a8cf7bcda1f0fea231a144692cb84a779a9e73e"
EXPECTED_V1_SCHEDULER_BLOB = "cbc502a92fe9d790cfaf763f6990d1057bc9b82d"
EXPECTED_V2_SCHEDULER_BLOB = "7c068b7078c3d7c09bb3836590ad42b0af934cdf"
OPERATION = "titan-v3-route-reference-echo-20260909-sol-accrual-01"

PENDING_NEEDLE = (
    "pending_future=[(max(now,t),q) for t,q in self.planned.get(item,[]) if t>now]"
)
ROUTE_NEEDLE = (
    "for t in range(now+1,item_end+1):\n"
    "                for order in route[t].get('market',[]) if t<len(route) else []:\n"
    "                    if order and order[0]=='SELL' and order[1]==item and rem>0:"
)
CHECKPOINT_NEEDLE = (
    "self.planned[selected_item]=[(t,q) for t,q in selected_plan if t>now and q>0]"
)
V2_ROUTE_NEEDLE = (
    "for t in range(now+1,end+1):\n"
    "                for order in route[t].get('market',[]) if t<len(route) else []:\n"
    "                    if order and order[0]=='SELL' and order[1]==item and rem>0:"
)


class AuditError(ValueError):
    """Exact source or route surface did not match the declared lane."""


def git_blob_sha1(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(value, handle, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def exact_file(path: Path, expected_blob: str) -> tuple[bytes, dict[str, Any]]:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode):
        raise AuditError(f"not a regular file: {path}")
    data = path.read_bytes()
    blob = git_blob_sha1(data)
    if blob != expected_blob:
        raise AuditError(f"{path.name} blob mismatch: expected {expected_blob}, got {blob}")
    return data, {
        "path": path.as_posix(),
        "bytes": len(data),
        "git_blob_sha1": blob,
        "sha256": sha256(data),
    }


def require_count(text: str, needle: str, expected: int, label: str) -> None:
    actual = text.count(needle)
    if actual != expected:
        raise AuditError(f"{label} count mismatch: expected {expected}, got {actual}")


def route_census(lab: Path) -> dict[str, Any]:
    if str(lab) not in sys.path:
        sys.path.insert(0, str(lab))
    import frozen_selected

    actor = frozen_selected.FrozenSelected()
    routes = actor.controller.R
    products = set(frozen_selected.PRODUCTS)
    if isinstance(routes, Mapping):
        route_items = sorted(routes.items(), key=lambda entry: str(entry[0]))
    elif isinstance(routes, Sequence) and not isinstance(routes, (str, bytes, bytearray)):
        route_items = list(enumerate(routes))
    else:
        raise AuditError("controller route bank is not a mapping or sequence")
    rows: list[dict[str, Any]] = []
    for route_index, route in route_items:
        if not isinstance(route, Sequence) or isinstance(route, (str, bytes, bytearray)):
            raise AuditError(f"route {route_index} is not a sequence")
        for step, action in enumerate(route):
            if not isinstance(action, Mapping):
                raise AuditError(f"route {route_index} step {step} is not a mapping")
            market = action.get("market", [])
            if not isinstance(market, (list, tuple)):
                raise AuditError(f"route {route_index} step {step} market is not a sequence")
            for order_index, order in enumerate(market):
                if not order or order[0] != "SELL":
                    continue
                if len(order) < 3:
                    raise AuditError(
                        f"route {route_index} step {step} SELL row {order_index} is malformed"
                    )
                item, quantity = order[1], order[2]
                if item not in products:
                    continue
                if isinstance(quantity, bool) or not isinstance(quantity, int):
                    raise AuditError(
                        f"route {route_index} step {step} SELL quantity is not an integer"
                    )
                if quantity <= 0:
                    continue
                same_day_prior = [
                    now
                    for now in range(max(0, step - int(frozen_selected.HORIZON)), step)
                    if now // 24 == step // 24
                ]
                rows.append(
                    {
                        "route": route_index,
                        "step": step,
                        "order_index": order_index,
                        "item": item,
                        "quantity": quantity,
                        "same_day_prior_steps_within_inherited_horizon": same_day_prior,
                    }
                )
    opportunities = [row for row in rows if row["same_day_prior_steps_within_inherited_horizon"]]
    return {
        "routes": len(route_items),
        "non_operating_route_sell_rows": len(rows),
        "static_echo_opportunity_rows": len(opportunities),
        "by_product": {
            item: sum(row["quantity"] for row in rows if row["item"] == item)
            for item in sorted({row["item"] for row in rows})
        },
        "rows": rows,
    }


def audit(lab: Path, *, require_opportunity: bool = False) -> dict[str, Any]:
    lab = lab.resolve()
    frozen_data, frozen_receipt = exact_file(
        lab / "frozen_selected.py", EXPECTED_FROZEN_SELECTED_BLOB
    )
    _main_data, main_receipt = exact_file(lab / "main.py", EXPECTED_MAIN_BLOB)
    _v1_data, v1_receipt = exact_file(
        lab / "runtime/variants/v1/scheduler.py", EXPECTED_V1_SCHEDULER_BLOB
    )
    v2_data, v2_receipt = exact_file(
        lab / "runtime/variants/v2/scheduler.py", EXPECTED_V2_SCHEDULER_BLOB
    )

    frozen_text = frozen_data.decode("utf-8")
    v2_text = v2_data.decode("utf-8")
    require_count(frozen_text, PENDING_NEEDLE, 1, "current pending replay")
    require_count(frozen_text, ROUTE_NEEDLE, 1, "current inherited route injection")
    require_count(frozen_text, CHECKPOINT_NEEDLE, 1, "current total-plan checkpoint")
    require_count(v2_text, V2_ROUTE_NEEDLE, 1, "frozen V2 inherited route injection")

    census = route_census(lab)
    if require_opportunity and census["static_echo_opportunity_rows"] <= 0:
        raise AuditError("current route bank has no static route-reference echo opportunity")

    return {
        "schema_version": 1,
        "operation": OPERATION,
        "verdict": "SOURCE_AND_ROUTE_SURFACE_PRESENT",
        "source": {
            "frozen_selected": frozen_receipt,
            "main": main_receipt,
            "frozen_v1_scheduler": v1_receipt,
            "frozen_v2_scheduler": v2_receipt,
        },
        "needle_counts": {
            "pending_future": frozen_text.count(PENDING_NEEDLE),
            "route_injection": frozen_text.count(ROUTE_NEEDLE),
            "total_plan_checkpoint": frozen_text.count(CHECKPOINT_NEEDLE),
            "frozen_v2_route_injection": v2_text.count(V2_ROUTE_NEEDLE),
        },
        "route_census": census,
        "limitations": [
            "Static route opportunity is not dynamic optimizer activation.",
            "The deterministic two-turn unit test proves the state echo, not a score gain.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lab", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--require-opportunity", action="store_true")
    args = parser.parse_args()
    try:
        report = audit(args.lab, require_opportunity=args.require_opportunity)
        status = 0
    except AuditError as exc:
        report = {
            "schema_version": 1,
            "operation": OPERATION,
            "verdict": "INVALID",
            "reason": str(exc),
        }
        status = 2
    atomic_json(args.output, report)
    print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
