"""Reproducible synthetic scale probe; elapsed time is not an SLA or paid result."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
import hashlib
import platform
import random
import time
from .planner import SCHEMA, canonical_json, plan


def case(seed: int, count: int, nodes: int) -> dict:
    rng = random.Random(seed)
    start = datetime(2026, 9, 15, 8, tzinfo=timezone.utc)
    families = [{"id": f"f{i}", "setup_minutes": rng.randrange(3, 21),
        "setup_cash_minor": rng.randrange(500, 2500)} for i in range(8)]
    jobs = []
    for i in range(count):
        deadline = start + timedelta(minutes=rng.randrange(90, 481))
        jobs.append({"operation_id": f"synthetic-{i:03}", "family_id": f"f{i % 8}",
            "availability": "AVAILABLE", "work_units": 1,
            "minutes": rng.randrange(5, 55), "cash_cost_minor": rng.randrange(0, 1000),
            "reward_minor": rng.randrange(3000, 18000),
            "collection_probability_bp": rng.randrange(5000, 10001),
            "valuation_basis": "OWNER_SCENARIO", "evidence_ref": f"synthetic:case-{i}",
            "deadline_at": deadline.isoformat().replace("+00:00", "Z")})
    return {"schema": SCHEMA, "scenario_id": f"scale-{seed}-{count}-{nodes}",
        "currency": "USD", "start_at": "2026-09-15T08:00:00Z",
        "horizon_minutes": 480, "cash_budget_minor": 30000,
        "effort_cost_minor_per_minute": 50, "minimum_net_minor": 50000,
        "node_budget": nodes, "families": families, "jobs": jobs}


def main() -> None:
    rows = []
    for count, nodes in ((16, 100000), (64, 10000), (256, 10000)):
        scenario = case(14712, count, nodes)
        started = time.perf_counter()
        result = plan(scenario)
        elapsed = time.perf_counter() - started
        rows.append({"jobs": count, "elapsed_seconds": round(elapsed, 6),
            "input_sha256": result["input_sha256"],
            "report_sha256": hashlib.sha256(canonical_json(result).encode()).hexdigest(),
            "search": result["search"], "selected_jobs": result["batch"]["job_count"],
            "decision": result["decision"]})
    print(canonical_json({"evidence_class": "SYNTHETIC_MODEL_ONLY",
        "python": platform.python_version(), "platform": platform.platform(), "cases": rows}), end="")


if __name__ == "__main__":
    main()
