#!/usr/bin/env python3
"""Synthetic acceptance harness for an Archives AI proof-of-concept.

This module validates evidence properties that are useful regardless of the final
University-selected AI approach: source/version provenance, abstention, explicit
human-review routing, deterministic replay, and change control. It does not make
legal/privacy claims and it does not authorize production use.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

DISPOSITIONS = {"ANSWER", "ABSTAIN", "REVIEW"}
HANDLING_STATES = {"OPEN_FOR_SYNTHETIC_POC", "REVIEW_REQUIRED"}


class AcceptanceError(ValueError):
    pass


def _sha_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def corpus_snapshot(records: list[dict[str, Any]]) -> str:
    material: list[dict[str, str]] = []
    seen: set[str] = set()
    for record in records:
        if not isinstance(record, dict):
            raise AcceptanceError("record must be an object")
        rid = record.get("record_id")
        version = record.get("version")
        text = record.get("text")
        handling = record.get("handling")
        if not isinstance(rid, str) or not rid:
            raise AcceptanceError("record_id must be a non-empty string")
        if rid in seen:
            raise AcceptanceError(f"duplicate record_id: {rid}")
        seen.add(rid)
        if not isinstance(version, str) or not version:
            raise AcceptanceError(f"{rid}: version must be a non-empty string")
        if not isinstance(text, str) or not text:
            raise AcceptanceError(f"{rid}: text must be a non-empty string")
        if handling not in HANDLING_STATES:
            raise AcceptanceError(f"{rid}: invalid handling state")
        material.append({"record_id": rid, "version": version, "text_sha256": _sha_text(text), "handling": handling})
    raw = json.dumps(sorted(material, key=lambda row: row["record_id"]), sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def citation_for(record: dict[str, Any]) -> dict[str, str]:
    return {"record_id": record["record_id"], "version": record["version"], "text_sha256": _sha_text(record["text"])}


def _result_signature(result: dict[str, Any]) -> str:
    material = {
        "disposition": result.get("disposition"),
        "citations": result.get("citations"),
        "retrieved_record_ids": result.get("retrieved_record_ids"),
        "corpus_snapshot_sha256": result.get("corpus_snapshot_sha256"),
        "model_version": result.get("model_version"),
        "prompt_version": result.get("prompt_version"),
        "human_review_required": result.get("human_review_required"),
        "policy_version": result.get("policy_version"),
    }
    raw = json.dumps(material, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(raw).hexdigest()


def evaluate_fixture(fixture: dict[str, Any], results: list[dict[str, Any]]) -> dict[str, Any]:
    errors: list[str] = []
    records_raw = fixture.get("records")
    cases_raw = fixture.get("cases")
    if not isinstance(records_raw, list) or not isinstance(cases_raw, list):
        return {"status": "FAIL", "errors": ["fixture requires records and cases lists"], "authority": "synthetic PoC evidence only"}
    try:
        snapshot = corpus_snapshot(records_raw)
    except AcceptanceError as exc:
        return {"status": "FAIL", "errors": [str(exc)], "authority": "synthetic PoC evidence only"}

    record_by_id = {r["record_id"]: r for r in records_raw}
    case_by_id: dict[str, dict[str, Any]] = {}
    for case in cases_raw:
        if not isinstance(case, dict):
            errors.append("case must be an object")
            continue
        cid = case.get("case_id")
        if not isinstance(cid, str) or not cid:
            errors.append("case_id must be a non-empty string")
            continue
        if cid in case_by_id:
            errors.append(f"duplicate case_id: {cid}")
        case_by_id[cid] = case

    result_by_id: dict[str, dict[str, Any]] = {}
    for result in results:
        if not isinstance(result, dict):
            errors.append("result must be an object")
            continue
        cid = result.get("case_id")
        if not isinstance(cid, str) or not cid:
            errors.append("result case_id must be a non-empty string")
            continue
        if cid in result_by_id:
            errors.append(f"duplicate result case_id: {cid}")
        result_by_id[cid] = result

    missing = sorted(set(case_by_id) - set(result_by_id))
    extra = sorted(set(result_by_id) - set(case_by_id))
    if missing:
        errors.append("missing results: " + ", ".join(missing))
    if extra:
        errors.append("unexpected results: " + ", ".join(extra))

    for cid in sorted(set(case_by_id) & set(result_by_id)):
        case = case_by_id[cid]
        result = result_by_id[cid]
        disposition = result.get("disposition")
        if disposition not in DISPOSITIONS:
            errors.append(f"{cid}: invalid disposition")
            continue
        expected = case.get("expected_disposition")
        if expected not in DISPOSITIONS:
            errors.append(f"{cid}: invalid expected disposition in fixture")
        elif disposition != expected:
            errors.append(f"{cid}: disposition mismatch")

        for key in ("model_version", "prompt_version", "policy_version"):
            value = result.get(key)
            if not isinstance(value, str) or not value.strip():
                errors.append(f"{cid}: missing {key}")
        if result.get("corpus_snapshot_sha256") != snapshot:
            errors.append(f"{cid}: corpus snapshot mismatch")
        if not isinstance(result.get("human_review_required"), bool):
            errors.append(f"{cid}: human_review_required must be boolean")

        allowed = case.get("allowed_record_ids", [])
        if not isinstance(allowed, list) or any(not isinstance(v, str) or not v for v in allowed):
            errors.append(f"{cid}: allowed_record_ids must be a string list")
            allowed = []
        allowed_set = set(allowed)
        unknown_allowed = sorted(allowed_set - set(record_by_id))
        if unknown_allowed:
            errors.append(f"{cid}: unknown allowed record(s): {', '.join(unknown_allowed)}")

        retrieved = result.get("retrieved_record_ids", [])
        if not isinstance(retrieved, list) or any(not isinstance(v, str) or not v for v in retrieved):
            errors.append(f"{cid}: retrieved_record_ids must be a string list")
            retrieved = []
        if len(set(retrieved)) != len(retrieved):
            errors.append(f"{cid}: duplicate retrieved_record_ids")
        if not set(retrieved).issubset(allowed_set):
            errors.append(f"{cid}: retrieval escaped allowed record set")

        citations = result.get("citations")
        if not isinstance(citations, list):
            errors.append(f"{cid}: citations must be a list")
            citations = []
        seen_citations: set[str] = set()
        cited_ids: set[str] = set()
        for citation in citations:
            if not isinstance(citation, dict):
                errors.append(f"{cid}: malformed citation")
                continue
            rid = citation.get("record_id")
            if not isinstance(rid, str) or not rid:
                errors.append(f"{cid}: citation record_id missing")
                continue
            if rid in seen_citations:
                errors.append(f"{cid}: duplicate citation for {rid}")
            seen_citations.add(rid)
            cited_ids.add(rid)
            record = record_by_id.get(rid)
            if record is None or rid not in allowed_set:
                errors.append(f"{cid}: citation outside allowed corpus")
                continue
            if citation != citation_for(record):
                errors.append(f"{cid}: citation version/hash mismatch for {rid}")

        required = case.get("required_citation_ids", [])
        if not isinstance(required, list) or any(not isinstance(v, str) or not v for v in required):
            errors.append(f"{cid}: required_citation_ids must be a string list")
            required = []
        if not set(required).issubset(cited_ids):
            errors.append(f"{cid}: missing required citation")

        review_records = [record_by_id[rid] for rid in allowed_set if rid in record_by_id and record_by_id[rid]["handling"] == "REVIEW_REQUIRED"]
        if review_records and disposition != "REVIEW":
            errors.append(f"{cid}: review-required source cannot be emitted as {disposition}")
        if disposition == "REVIEW" and result.get("human_review_required") is not True:
            errors.append(f"{cid}: REVIEW must require human review")
        if disposition != "REVIEW" and result.get("human_review_required") is not False:
            errors.append(f"{cid}: non-REVIEW disposition must not assert pending human review")
        if disposition == "ANSWER" and not citations:
            errors.append(f"{cid}: ANSWER requires citations")
        if disposition == "ABSTAIN" and citations:
            errors.append(f"{cid}: ABSTAIN must not carry answer citations")
        if disposition == "REVIEW" and result.get("answer") not in (None, ""):
            errors.append(f"{cid}: REVIEW must not emit a final answer")

    for cid, case in case_by_id.items():
        replay_of = case.get("replay_of")
        if not replay_of:
            continue
        if replay_of not in result_by_id or cid not in result_by_id:
            continue
        if _result_signature(result_by_id[cid]) != _result_signature(result_by_id[replay_of]):
            errors.append(f"{cid}: replay evidence diverges from {replay_of}")

    return {
        "status": "PASS" if not errors else "FAIL",
        "cases": len(case_by_id),
        "results": len(result_by_id),
        "corpus_snapshot_sha256": snapshot,
        "errors": errors,
        "authority": (
            "synthetic technical PoC evidence only; no production-data access, privacy/legal conclusion, "
            "University acceptance, deployment, submission, contract, award, or revenue authority"
        ),
    }
