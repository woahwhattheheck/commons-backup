from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from typing import Optional

from .engine import _compile_plan_at, derive_collision_key, sha256_hex

NOW = datetime(2026, 9, 13, 16, 0, tzinfo=timezone.utc)
H = "1" * 64
B = "2" * 64


def base_packet(name: str = "p"):
    return {
        "version": "commercial-portfolio-allocator/v1",
        "portfolio_id": f"portfolio-{name}",
        "portfolio_currency": "USD",
        "capacity_units": 6,
        "horizon_end": "2026-09-20T16:00:00Z",
        "evidence_max_age_seconds": 86400,
        "satisfied_dependency_keys": ["checkout-ready", "source-bound"],
        "opportunities": [],
    }


def opportunity(
    oid: str,
    *,
    gross: int = 100000,
    conversion: int = 500000,
    risk: int = 100000,
    weight: int = 1000000,
    effort: int = 2,
    deadline: str = "2026-09-18T16:00:00Z",
    observed: str = "2026-09-13T15:30:00Z",
    state: str = "ACTIVE",
    collision_key: Optional[str] = None,
    buyer_id: Optional[str] = None,
    opportunity_key: Optional[str] = None,
    requires=None,
    prereq: bool = True,
    owner_ready: bool = True,
    kind: str = "deal",
    stage: str = "QUALIFIED",
):
    if requires is None:
        requires = []
    buyer = buyer_id or f"buyer-{oid}"
    external_key = opportunity_key or f"external-{oid}"
    canonical_collision = derive_collision_key(buyer, external_key)
    return {
        "opportunity_id": oid,
        "buyer_id": buyer,
        "opportunity_key": external_key,
        "collision_key": collision_key or canonical_collision,
        "kind": kind,
        "state": state,
        "stage": stage,
        "currency": "USD",
        "gross_value_minor": gross,
        "conversion_ppm": conversion,
        "conversion_basis_ref": f"synthetic:conversion:{oid}",
        "conversion_basis_sha256": B,
        "risk_ppm": risk,
        "strategic_weight_ppm": weight,
        "effort_units": effort,
        "deadline_at": deadline,
        "evidence_observed_at": observed,
        "evidence_source_ref": f"synthetic:evidence:{oid}",
        "evidence_source_sha256": H,
        "requires_dependency_keys": list(requires),
        "prerequisites_ready": prereq,
        "owner_review_ready": owner_ready,
    }


def acceptance_summary():
    cases = []

    p = base_packet("single")
    p["opportunities"] = [opportunity("single")]
    cases.append(p)

    p = base_packet("dnr")
    p["opportunities"] = [opportunity("dnr", gross=9_000_000, conversion=1_000_000, state="DNR")]
    cases.append(p)

    p = base_packet("deps")
    p["opportunities"] = [opportunity("deps", requires=["missing-partner"])]
    cases.append(p)

    p = base_packet("knapsack")
    p["opportunities"] = [
        opportunity("big", gross=100000, conversion=1_000_000, risk=0, effort=6),
        opportunity("small-a", gross=60000, conversion=1_000_000, risk=0, effort=3),
        opportunity("small-b", gross=60000, conversion=1_000_000, risk=0, effort=3),
    ]
    cases.append(p)

    p = base_packet("stale")
    p["opportunities"] = [opportunity("stale", observed="2026-09-10T15:00:00Z")]
    cases.append(p)

    p = base_packet("expired")
    p["opportunities"] = [opportunity("expired", deadline="2026-09-13T15:59:59Z")]
    cases.append(p)

    p = base_packet("owner")
    p["opportunities"] = [opportunity("owner", owner_ready=False)]
    cases.append(p)

    p = base_packet("collision")
    p["opportunities"] = [opportunity("a", buyer_id="buyer-shared", opportunity_key="shared-rfp"), opportunity("b", buyer_id="buyer-shared", opportunity_key="shared-rfp")]
    cases.append(p)

    p = base_packet("future")
    p["opportunities"] = [opportunity("future", observed="2026-09-13T16:00:01Z")]
    cases.append(p)

    p = base_packet("zero")
    p["opportunities"] = [opportunity("zero", conversion=0)]
    cases.append(p)

    boards = [_compile_plan_at(case, now=NOW) for case in cases]
    stages = {}
    for board in boards:
        stages[board["stage"]] = stages.get(board["stage"], 0) + 1
    digest = sha256_hex(b"".join((board["receipt_sha256"] + "\n").encode("ascii") for board in boards))
    return {"count": len(boards), "stages": stages, "receipt_set_sha256": digest}


if __name__ == "__main__":
    print(json.dumps(acceptance_summary(), sort_keys=True))
