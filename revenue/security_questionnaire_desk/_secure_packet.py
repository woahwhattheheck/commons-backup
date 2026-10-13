"""Authority-honest packet compilation, verification, and public projection."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

try:
    from . import _engine as core
    from ._secure_input import LINKED_STATE, SUPPORTED_REQUEST, prepare_input
except ImportError:
    import _engine as core  # type: ignore[no-redef]
    from _secure_input import LINKED_STATE, SUPPORTED_REQUEST, prepare_input

DeskError = core.DeskError


def _public_projection(packet: dict[str, Any]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for row in packet["rows"]:
        private = [
            evidence for evidence in row.get("evidence", [])
            if evidence.get("disclosure") != "PUBLIC"
        ]
        if private:
            rows.append({
                "question_id": row["question_id"],
                "required": row["required"],
                "state": "UNMEASURED",
                "answer": "UNMEASURED",
                "reasons": ["NON_PUBLIC_EVIDENCE_STRIPPED"],
                "public_evidence": [],
            })
            continue
        public_evidence = []
        for evidence in row.get("evidence", []):
            if evidence.get("disclosure") != "PUBLIC" or evidence.get("current_at_compile") is not True:
                continue
            projected = {
                "evidence_id": evidence["evidence_id"],
                "supports_question_id": evidence["supports_question_id"],
                "supports_question_source_sha256": evidence["supports_question_source_sha256"],
                "kind": evidence["kind"],
                "source_ref": evidence["source_ref"],
                "source_sha256": evidence["source_sha256"],
                "evidence_sha256": evidence["evidence_sha256"],
            }
            if "supports_answer_sha256" in evidence:
                projected["supports_answer_sha256"] = evidence["supports_answer_sha256"]
            public_evidence.append(projected)
        rows.append({
            "question_id": row["question_id"],
            "required": row["required"],
            "state": row["state"],
            "answer": row["answer"],
            "reasons": list(row.get("reasons", [])),
            "public_evidence": public_evidence,
        })
    return {
        "kind": "SECURITY_QUESTIONNAIRE_PUBLIC_SAFE_PROJECTION",
        "questionnaire_id": packet["questionnaire_id"],
        "status": "PUBLIC_OWNER_REVIEW_REQUIRED",
        "rows": rows,
    }


def compile_packet(raw: Any, as_of: datetime) -> dict[str, Any]:
    sanitized, binding_failures, disposition_count, lineage = prepare_input(raw)
    packet = core.compile_packet(sanitized, as_of)
    full_generation = core.sha256_hex(core.canonical_bytes({
        "core_input_generation_sha256": packet["input_generation_sha256"],
        **lineage,
    }))
    binding_by_id = {
        item["evidence_id"]: item for item in lineage["support_bindings"]
    }

    hold_count = 0
    for row in packet["rows"]:
        for evidence in row.get("evidence", []):
            binding = binding_by_id.get(evidence.get("evidence_id"))
            if (
                binding is not None
                and binding["present"]
                and type(binding["value"]) is str
            ):
                evidence["supports_answer_sha256"] = binding["value"]
        failures = binding_failures.get(row["question_id"], [])
        if failures:
            row["state"] = "HOLD"
            row["reasons"] = sorted(set(row.get("reasons", []) + failures))
        elif row["state"] == SUPPORTED_REQUEST:
            row["state"] = LINKED_STATE
        row["owner_disposition"] = None
        row["owner_disposition_status"] = "UNTRUSTED_CANDIDATE_CONTEXT_IGNORED"
        row["answer_generation_sha256"] = core.sha256_hex(core.canonical_bytes({
            "question_id": row["question_id"],
            "question_sha256": row["question_sha256"],
            "answer": row["answer"],
            "requested_state": row["requested_state"],
            "effective_state": row["state"],
            "evidence": [
                {
                    "evidence_id": evidence["evidence_id"],
                    "evidence_sha256": evidence["evidence_sha256"],
                }
                for evidence in sorted(
                    row.get("evidence", []), key=lambda item: item["evidence_id"]
                )
            ],
        }))
        if row["state"] == "HOLD":
            hold_count += 1

    packet["status"] = "HOLD" if hold_count else "READY_FOR_OWNER_REVIEW"
    packet["counts"]["holds"] = hold_count
    packet["counts"]["required_approved_for_return"] = 0
    packet["core_input_generation_sha256"] = packet["input_generation_sha256"]
    packet["input_generation_sha256"] = full_generation
    packet["review_authority"] = {
        "candidate_disposition_count": disposition_count,
        "candidate_dispositions_are_owner_authority": False,
        "owner_approval_inferred": False,
        "owner_action_required": True,
    }
    packet["evidence_authority"] = {
        "state_label": LINKED_STATE,
        "meaning": "caller evidence is content-bound to one exact question/answer generation",
        "authenticated_source_provenance": False,
    }
    packet["public_safe_projection"] = _public_projection(packet)
    packet.pop("receipt_sha256", None)
    packet["receipt_sha256"] = core.sha256_hex(core.canonical_bytes(packet))
    return packet


def verify_packet(raw_input: Any, packet: Any, trusted_now: datetime) -> dict[str, Any]:
    candidate = core._expect_dict(packet, "packet")
    if "receipt_sha256" not in candidate:
        raise DeskError("packet: missing receipt_sha256")
    receipt = core._expect_sha(candidate["receipt_sha256"], "packet.receipt_sha256")
    receipt_core = dict(candidate)
    receipt_core.pop("receipt_sha256")
    if core.sha256_hex(core.canonical_bytes(receipt_core)) != receipt:
        raise DeskError("packet receipt mismatch")

    compiled_at = core._parse_utc(candidate.get("as_of"), "packet.as_of")
    now_text = core._format_utc(trusted_now)
    now = core._parse_utc(now_text, "trusted_now")
    if compiled_at > now:
        raise DeskError("packet compile time is in the trusted future")
    recomputed = compile_packet(raw_input, compiled_at)
    if core.canonical_bytes(recomputed) != core.canonical_bytes(candidate):
        raise DeskError("packet does not match exact inputs at its bound compile time")

    sanitized, _, _, _ = prepare_input(raw_input)
    normalized = core.normalize_input(sanitized)
    evidence_map = {item.evidence_id: item for item in normalized["evidence"]}
    for row in candidate.get("rows", []):
        if row.get("state") != LINKED_STATE:
            continue
        for evidence in row.get("evidence", []):
            evidence_id = evidence.get("evidence_id")
            if evidence_id not in evidence_map:
                raise DeskError("packet references unknown evidence")
            current, reason = core._is_current(evidence_map[evidence_id], now)
            if not current:
                raise DeskError(
                    f"packet evidence linkage is no longer current: {reason}:{evidence_id}"
                )
    return {
        "verified": True,
        "receipt_sha256": receipt,
        "status": candidate["status"],
        "verified_at": now_text,
    }


def render_public_safe_json(packet: Mapping[str, Any]) -> str:
    return core.canonical_bytes(packet["public_safe_projection"]).decode("utf-8") + "\n"


def artifact_bytes(packet: Mapping[str, Any]) -> dict[str, bytes]:
    return {
        "packet.json": core.canonical_bytes(packet) + b"\n",
        "review.md": core.render_markdown(packet).encode("utf-8"),
        "answers.csv": core.render_csv(packet).encode("utf-8"),
        "public-safe.json": render_public_safe_json(packet).encode("utf-8"),
        "receipt.sha256": (packet["receipt_sha256"] + "  packet.json\n").encode("ascii"),
    }
