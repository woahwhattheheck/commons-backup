#!/usr/bin/env python3
"""UIOWA-102 adapters from merged specialist outputs to the common evidence register."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]

DELIVERY_SOURCE = Path("revenue/uiowa_rfq_18649_delivery_metrics/fixtures/synthetic_deployments.csv")
SECURITY_SOURCE = Path("revenue/uiowa_rfq_18649_security_event_review/fixtures/synthetic_events.json")
AI_SOURCE = Path("revenue/uiowa_rfq_18649_synthetic_collection/facts.json")

COMMON_FIELDS = [
    "evidence_id", "observation_id", "finding_id", "group", "area",
    "source_type", "source_ref", "captured_at", "represented_period",
    "claim", "scope_limit", "directness", "recency", "representativeness",
    "corroboration", "evidence_state", "confidence", "conflict_group",
    "universe_definition", "enumerator_authority", "completeness_basis",
    "follow_up",
]
EXTENSION_FIELDS = [
    "source_component", "native_id", "synthetic", "source_sha256", "extensions_json"
]
OUTPUT_FIELDS = COMMON_FIELDS + EXTENSION_FIELDS

GROUP_FROM_DELIVERY = {"synthetic-registration": "ESS"}
GROUP_FROM_SECURITY = {
    "ESS-FICTIONAL": "ESS",
    "RIS-FICTIONAL": "RIS",
    "IAM-FICTIONAL": "IAM",
}

def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))

def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected JSON object")
    return value

def _extensions(component: str, native_id: str, digest: str, native: dict[str, Any]) -> str:
    return json.dumps(
        {
            "source_component": component,
            "native_id": native_id,
            "synthetic": True,
            "source_sha256": digest,
            "native_record": native,
        },
        sort_keys=True,
        separators=(",", ":"),
    )

def _record(
    *,
    component: str,
    native_id: str,
    group: str,
    area: str,
    kind: str,
    seq: int,
    source_path: Path,
    digest: str,
    captured_at: str,
    represented_period: str,
    claim: str,
    scope_limit: str,
    directness: str,
    recency: str,
    representativeness: str,
    corroboration: str,
    evidence_state: str,
    confidence: str,
    follow_up: str,
    native: dict[str, Any],
    conflict_group: str = "",
    universe_definition: str = "",
    enumerator_authority: str = "",
    completeness_basis: str = "",
) -> dict[str, str]:
    return {
        "evidence_id": f"EV-SYN-{group}-{area}-{kind}-{seq:03d}",
        "observation_id": f"OBS-SYN-{group}-{area}-{seq:03d}",
        "finding_id": f"FND-SYN-{group}-{area}-{seq:03d}",
        "group": group,
        "area": area,
        "source_type": {
            "delivery_metrics": "deployment_metric_record",
            "security_event_review": "security_event_record",
            "ai_readiness_facts": "synthetic_fact_ledger",
        }[component],
        "source_ref": f"{source_path.as_posix()}#{native_id}",
        "captured_at": captured_at,
        "represented_period": represented_period,
        "claim": claim,
        "scope_limit": scope_limit,
        "directness": directness,
        "recency": recency,
        "representativeness": representativeness,
        "corroboration": corroboration,
        "evidence_state": evidence_state,
        "confidence": confidence,
        "conflict_group": conflict_group,
        "universe_definition": universe_definition,
        "enumerator_authority": enumerator_authority,
        "completeness_basis": completeness_basis,
        "follow_up": follow_up,
        "source_component": component,
        "native_id": native_id,
        "synthetic": "true",
        "source_sha256": digest,
        "extensions_json": _extensions(component, native_id, digest, native),
    }

def adapt_delivery(repo: Path = REPO) -> list[dict[str, str]]:
    path = repo / DELIVERY_SOURCE
    rows = sorted(_read_csv(path), key=lambda row: row["deployment_id"])
    digest = _sha(path)
    out: list[dict[str, str]] = []
    for offset, row in enumerate(rows):
        native_id = row["deployment_id"].strip()
        service = row["service"].strip()
        group = GROUP_FROM_DELIVERY.get(service)
        if not native_id or not group:
            raise ValueError(f"delivery row has missing or unmapped identity: {row!r}")
        deployed_at = row["deployed_at"].strip()
        if not deployed_at:
            raise ValueError(f"{native_id}: deployed_at is required")
        claim = (
            f"Synthetic deployment {native_id} for {group} was recorded at {deployed_at}; "
            f"intervention_required={row['intervention_required'] or 'unknown'}; "
            f"unplanned_rework={row['unplanned_rework'] or 'unknown'}."
        )
        out.append(_record(
            component="delivery_metrics",
            native_id=native_id,
            group=group,
            area="DEP",
            kind="MET",
            seq=810 + offset,
            source_path=DELIVERY_SOURCE,
            digest=digest,
            captured_at=deployed_at,
            represented_period=deployed_at[:10],
            claim=claim,
            scope_limit="One synthetic deployment event; not a population metric, maturity conclusion, or real University observation.",
            directness="DIRECT",
            recency="CURRENT",
            representativeness="SINGLE",
            corroboration="SAME_SYSTEM",
            evidence_state="SUPPORTING",
            confidence="MODERATE",
            follow_up="Define the deployment population and period before aggregating this event into a broader finding.",
            native=dict(row),
        ))
    return out

def _security_state(event: dict[str, Any]) -> tuple[str, str, str]:
    relevant = event.get("security_relevant")
    monitoring_only = event.get("monitoring_only") is True
    reviewed = bool(event.get("review_owner")) and bool(event.get("reviewed_at")) and bool(event.get("decision"))
    action = event.get("action") if isinstance(event.get("action"), dict) else {}
    action_status = action.get("status") or "unknown"
    if relevant is None:
        return (
            "NO_EVIDENCE_OBSERVED",
            "NOT_EVIDENCED",
            "Security relevance is not established in the supplied synthetic event packet.",
        )
    if relevant is True and not reviewed:
        return (
            "NO_EVIDENCE_OBSERVED",
            "NOT_EVIDENCED",
            "The event is recorded as security-relevant, but review owner/time/decision evidence is missing.",
        )
    if monitoring_only and relevant is False:
        return (
            "SUPPORTING",
            "MODERATE",
            "The event is explicitly recorded as a monitoring-only signal rather than a security review.",
        )
    return (
        "SUPPORTING",
        "MODERATE",
        f"The event records a security review; action status is {action_status}.",
    )

def adapt_security(repo: Path = REPO) -> list[dict[str, str]]:
    path = repo / SECURITY_SOURCE
    packet = _read_json(path)
    if packet.get("fictional") is not True:
        raise ValueError("security source must remain fictional=true")
    events = packet.get("events")
    if not isinstance(events, list):
        raise ValueError("security source events must be an array")
    digest = _sha(path)
    out: list[dict[str, str]] = []
    for offset, raw in enumerate(sorted(events, key=lambda e: str(e.get("event_id", "")))):
        if not isinstance(raw, dict):
            raise ValueError("security event must be an object")
        native_id = str(raw.get("event_id") or "").strip()
        group = GROUP_FROM_SECURITY.get(str(raw.get("service") or "").strip())
        occurred_at = str(raw.get("occurred_at") or "").strip()
        if not native_id or not group or not occurred_at:
            raise ValueError(f"security event missing identity/group/time: {raw!r}")
        state, confidence, claim = _security_state(raw)
        out.append(_record(
            component="security_event_review",
            native_id=native_id,
            group=group,
            area="SEC",
            kind="EVT",
            seq=840 + offset,
            source_path=SECURITY_SOURCE,
            digest=digest,
            captured_at=str(raw.get("collected_at") or occurred_at),
            represented_period=occurred_at[:10],
            claim=f"Synthetic event {native_id}: {claim}",
            scope_limit="One event from a fictional review packet; no group-wide control effectiveness or compliance conclusion.",
            directness="DIRECT",
            recency="CURRENT",
            representativeness="SINGLE",
            corroboration="NO_CORROBORATION",
            evidence_state=state,
            confidence=confidence,
            follow_up=(
                "Request the missing review/relevance evidence before drawing a security finding."
                if confidence == "NOT_EVIDENCED"
                else "Corroborate with another source before generalizing beyond this event."
            ),
            native=raw,
        ))
    return out

def adapt_ai(repo: Path = REPO) -> list[dict[str, str]]:
    path = repo / AI_SOURCE
    packet = _read_json(path)
    if packet.get("synthetic") is not True:
        raise ValueError("AI source must remain synthetic=true")
    facts = packet.get("facts")
    if not isinstance(facts, list):
        raise ValueError("AI source facts must be an array")
    selected = [f for f in facts if isinstance(f, dict) and f.get("area") == "ai_readiness"]
    digest = _sha(path)
    out: list[dict[str, str]] = []
    for offset, fact in enumerate(sorted(selected, key=lambda f: str(f.get("fact_id", "")))):
        native_id = str(fact.get("fact_id") or "").strip()
        group = str(fact.get("service") or "").strip()
        status = str(fact.get("status") or "").strip()
        claim = str(fact.get("statement") or "").strip()
        if not native_id or group not in {"ESS", "RIS", "IAM"} or not claim:
            raise ValueError(f"AI fact missing identity/group/claim: {fact!r}")
        if status == "unknown":
            state, confidence = "NO_EVIDENCE_OBSERVED", "NOT_EVIDENCED"
            follow = "Retain UNKNOWN and request underlying source evidence; do not convert missing evidence into a gap."
        elif status in {"strength", "gap"}:
            state, confidence = "SUPPORTING", "LOW"
            follow = "Resolve through the UIOWA-091 evidence manifest and underlying artifacts before elevating confidence."
        else:
            raise ValueError(f"{native_id}: unsupported status {status!r}")
        out.append(_record(
            component="ai_readiness_facts",
            native_id=native_id,
            group=group,
            area="AI",
            kind="AIF",
            seq=870 + offset,
            source_path=AI_SOURCE,
            digest=digest,
            captured_at="2026-09-19T13:45:44Z",
            represented_period="2026-09-19",
            claim=claim,
            scope_limit="Curated synthetic UIOWA-091 fact; underlying evidence remains authoritative for any later synthesis.",
            directness="NEAR_DIRECT",
            recency="CURRENT",
            representativeness="SINGLE",
            corroboration="NO_CORROBORATION",
            evidence_state=state,
            confidence=confidence,
            follow_up=follow,
            native=fact,
        ))
    return out

ADAPTERS = {
    "delivery": adapt_delivery,
    "security": adapt_security,
    "ai": adapt_ai,
}

def build(component: str, repo: Path = REPO) -> list[dict[str, str]]:
    if component == "all":
        rows: list[dict[str, str]] = []
        for name in ("delivery", "security", "ai"):
            rows.extend(ADAPTERS[name](repo))
    else:
        rows = ADAPTERS[component](repo)
    ids = [row["evidence_id"] for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("adapter evidence_id collision")
    return rows

def write_csv(rows: Iterable[dict[str, str]], path: Path) -> None:
    materialized = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(materialized)

def write_json(rows: Iterable[dict[str, str]], path: Path) -> None:
    materialized = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(materialized, indent=2, sort_keys=True) + "\n", encoding="utf-8")

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--component", choices=("delivery", "security", "ai", "all"), default="all")
    parser.add_argument("--repo", type=Path, default=REPO)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    rows = build(args.component, args.repo)
    args.out.mkdir(parents=True, exist_ok=True)
    write_csv(rows, args.out / f"{args.component}_to_register.csv")
    write_json(rows, args.out / f"{args.component}_to_register.json")
    print(f"PASS component={args.component} rows={len(rows)}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
