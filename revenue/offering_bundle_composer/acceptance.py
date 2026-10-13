from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone

try:
    from .composer import compile_bundle, sha256_json, verify_receipt
except ImportError:
    from composer import compile_bundle, sha256_json, verify_receipt

NOW = datetime(2026, 9, 13, 10, 0, tzinfo=timezone.utc)
FAMILIES = ("product", "service", "expertise", "data")


def z(value: datetime) -> str:
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def digest(label: str) -> str:
    return sha256_json({"label": label})


def entry(index: int, family: str, *, pricing: str = "FIXED") -> dict:
    entry_id = f"{family}-{index:03d}"
    return {
        "entry_id": entry_id,
        "family": family,
        "version": f"1.0.{index}",
        "source": {
            "repository": "woahwhattheheck/commons",
            "commit": (f"{index + 1:040x}")[-40:],
            "path": f"revenue/demo/{entry_id}.json",
            "content_sha256": digest(f"content-{entry_id}"),
        },
        "evidence": {
            "receipt_sha256": digest(f"evidence-{entry_id}"),
            "verified_at": z(NOW - timedelta(minutes=5)),
            "max_age_seconds": 3600,
        },
        "deliverables": [{
            "deliverable_id": f"deliverable-{index:03d}",
            "description": f"Bounded {family} deliverable {index}",
            "acceptance_criteria": [f"Verifier reproduces bounded evidence {index}"],
        }],
        "exclusions": ["No external buyer action"],
        "depends_on": [],
        "conflicts_with": [],
        "pricing": (
            {"mode": "FIXED", "currency": "USD", "amount_minor": 10000 + index}
            if pricing == "FIXED"
            else {"mode": "QUOTE_REQUIRED", "currency": None, "amount_minor": None}
        ),
        "authority": {
            "buyer_contact": False,
            "external_send": False,
            "contract_execution": False,
            "buyer_acceptance": False,
            "checkout_or_payment": False,
            "fulfillment": False,
            "revenue_recognition": False,
        },
    }


def ready_manifest(index: int) -> dict:
    count = 2 + (index % 3)
    chosen = [FAMILIES[(index + offset) % len(FAMILIES)] for offset in range(count)]
    entries = [entry(index * 10 + offset, family, pricing="QUOTE_REQUIRED" if index % 5 == 0 and offset == count - 1 else "FIXED") for offset, family in enumerate(chosen)]
    for pos in range(1, len(entries)):
        entries[pos]["depends_on"] = [entries[pos - 1]["entry_id"]]
    return {
        "schema": "commons-offering-bundle-input/v1",
        "bundle_id": f"bundle-{index:03d}",
        "title": f"Cross-family bundle {index}",
        "entries": entries,
    }


def mutate_hold(manifest: dict, family: str) -> None:
    if family == "STALE_EVIDENCE":
        manifest["entries"][0]["evidence"]["verified_at"] = z(NOW - timedelta(hours=2))
        manifest["entries"][0]["evidence"]["max_age_seconds"] = 60
    elif family == "FUTURE_EVIDENCE":
        manifest["entries"][0]["evidence"]["verified_at"] = z(NOW + timedelta(seconds=1))
    elif family == "MISSING_DEPENDENCY":
        manifest["entries"][0]["depends_on"] = ["missing-entry"]
    elif family == "DEPENDENCY_CYCLE":
        a, b = manifest["entries"][0], manifest["entries"][1]
        a["depends_on"] = [b["entry_id"]]
        b["depends_on"] = [a["entry_id"]]
    elif family == "ENTRY_CONFLICT":
        manifest["entries"][0]["conflicts_with"] = [manifest["entries"][1]["entry_id"]]
    elif family == "MIXED_CURRENCY":
        for item in manifest["entries"]:
            item["pricing"] = {"mode": "FIXED", "currency": "USD", "amount_minor": 1000}
        manifest["entries"][1]["pricing"]["currency"] = "EUR"
    elif family == "MUTABLE_SOURCE_REF":
        manifest["entries"][0]["source"]["commit"] = "main"
    elif family == "SENSITIVE_METADATA":
        manifest["entries"][0]["deliverables"][0]["description"] = "send api_key=super-secret-value"
    else:
        raise AssertionError(family)


def main() -> int:
    rows = []
    for index in range(120):
        manifest = ready_manifest(index)
        receipt = compile_bundle(manifest, trusted_as_of=z(NOW))
        if receipt["status"] != "READY_FOR_HUMAN_BUNDLE_REVIEW":
            raise AssertionError((index, receipt))
        if not verify_receipt(manifest, trusted_as_of=z(NOW), receipt=receipt):
            raise AssertionError("ready receipt verification failed")
        rows.append({"index": index, "family": "CONTROL", "status": receipt["status"], "receipt_digest": receipt["receipt_digest"]})

    hold_families = (
        "STALE_EVIDENCE", "FUTURE_EVIDENCE", "MISSING_DEPENDENCY", "DEPENDENCY_CYCLE",
        "ENTRY_CONFLICT", "MIXED_CURRENCY", "MUTABLE_SOURCE_REF", "SENSITIVE_METADATA",
    )
    for offset in range(40):
        family = hold_families[offset // 5]
        manifest = deepcopy(ready_manifest(120 + offset))
        mutate_hold(manifest, family)
        receipt = compile_bundle(manifest, trusted_as_of=z(NOW))
        if receipt["status"] != "HOLD":
            raise AssertionError((family, receipt))
        if not verify_receipt(manifest, trusted_as_of=z(NOW), receipt=receipt):
            raise AssertionError("hold receipt verification failed")
        rows.append({"index": 120 + offset, "family": family, "status": receipt["status"], "receipt_digest": receipt["receipt_digest"]})

    summary = {
        "schema": "commons-offering-bundle-acceptance/v1",
        "ready": sum(row["status"] == "READY_FOR_HUMAN_BUNDLE_REVIEW" for row in rows),
        "hold": sum(row["status"] == "HOLD" for row in rows),
        "families": {name: sum(row["family"] == name for row in rows) for name in sorted(set(row["family"] for row in rows))},
        "results_digest": sha256_json(rows),
    }
    print(json.dumps(summary, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
