from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone

from .gate import READY, digest, evaluate, verify


def fixture(now: datetime | None = None) -> tuple[dict, datetime]:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).replace(microsecond=0)
    offer = {
        "offer_id": "pilot-001",
        "buyer_scope": "example.invalid",
        "currency": "USD",
        "price_minor": 600000,
        "admission_funding_minor": 300000,
        "scope": ["deliver deterministic variance packet", "ingest owner-supplied closed-period evidence"],
        "acceptance_criteria": ["owner can reproduce receipt offline", "variance rows bind to supplied evidence hashes"],
        "issued_at": (now - timedelta(hours=2)).isoformat().replace("+00:00", "Z"),
        "expires_at": (now + timedelta(days=2)).isoformat().replace("+00:00", "Z"),
        "funding_freshness_seconds": 86400,
    }
    offer_sha = digest(offer)
    packet = {
        "schema": "paid-pilot-admission/v1",
        "offer": offer,
        "acceptance": {
            "offer_id": "pilot-001",
            "offer_sha256": offer_sha,
            "accepted_at": (now - timedelta(minutes=20)).isoformat().replace("+00:00", "Z"),
            "evidence_sha256": "a" * 64,
        },
        "funding": {
            "offer_id": "pilot-001",
            "offer_sha256": offer_sha,
            "currency": "USD",
            "status": "CAPTURED",
            "amount_minor": 300000,
            "observed_at": (now - timedelta(minutes=10)).isoformat().replace("+00:00", "Z"),
            "evidence_sha256": "b" * 64,
            "source_authority": "OWNER_VERIFIED_PROVIDER_READBACK",
        },
    }
    return packet, now


def run() -> dict:
    packet, now = fixture()
    ready = evaluate(packet)
    assert ready.status == READY
    assert verify(packet, ready.receipt)

    statuses: dict[str, str] = {"ready": ready.status}
    cases = []

    p = deepcopy(packet); p["funding"]["amount_minor"] = 299999; cases.append(("partial", p))
    p = deepcopy(packet); p["funding"]["status"] = "AUTHORIZED"; cases.append(("authorized_only", p))
    p = deepcopy(packet); p["funding"]["currency"] = "EUR"; cases.append(("currency", p))
    p = deepcopy(packet); p["funding"]["offer_id"] = "other"; cases.append(("funding_transplant", p))
    p = deepcopy(packet); p["acceptance"]["offer_id"] = "other"; cases.append(("acceptance_transplant", p))
    p = deepcopy(packet); p["acceptance"]["offer_sha256"] = "c" * 64; cases.append(("accepted_digest", p))
    p = deepcopy(packet); p["offer"]["price_minor"] += 1; cases.append(("offer_changed", p))
    p = deepcopy(packet); p["funding"]["observed_at"] = (now - timedelta(days=2)).isoformat().replace("+00:00", "Z"); cases.append(("stale", p))
    p = deepcopy(packet); p["funding"]["observed_at"] = (now + timedelta(minutes=1)).isoformat().replace("+00:00", "Z"); cases.append(("future_funding", p))
    p = deepcopy(packet); p["acceptance"]["accepted_at"] = (now + timedelta(minutes=1)).isoformat().replace("+00:00", "Z"); cases.append(("future_acceptance", p))
    p = deepcopy(packet); p["acceptance"]["accepted_at"] = (now - timedelta(minutes=5)).isoformat().replace("+00:00", "Z"); p["funding"]["observed_at"] = (now - timedelta(minutes=10)).isoformat().replace("+00:00", "Z"); cases.append(("acceptance_after_funding", p))

    for name, candidate in cases:
        result = evaluate(candidate)
        assert result.status != READY, name
        statuses[name] = result.status

    tampered = deepcopy(ready.receipt)
    tampered["status"] = "READY_FOR_OWNER_WORK_ADMISSION_TAMPERED"
    assert not verify(packet, tampered)
    return {"cases": statuses, "receipt_sha256": ready.receipt["receipt_sha256"], "verified": True}


if __name__ == "__main__":
    import json
    print(json.dumps(run(), sort_keys=True))
