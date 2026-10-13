from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from .common import digest_object, format_timestamp, sha256_bytes, sorted_unique
from .parse import ParsedCandidate, ParsedEvidence, ParsedRoot
from .policy import POLICY_SHA256, policy_dict

_POLICY_AT_IMPORT = policy_dict()
_MAX_FUTURE_SKEW_SECONDS = int(_POLICY_AT_IMPORT["max_future_skew_seconds"])
_MAX_REPLY_AGE_SECONDS = int(_POLICY_AT_IMPORT["max_reply_age_seconds"])
_MAX_SOURCE_AGE_SECONDS = int(_POLICY_AT_IMPORT["max_source_age_seconds"])
del _POLICY_AT_IMPORT


def evidence_section_digests(evidence: ParsedEvidence) -> dict[str, str]:
    return {
        "counterparty_sender_refs_sha256": digest_object(list(evidence.counterparty_sender_refs)),
        "observations_sha256": digest_object(list(evidence.observations)),
        "interpretations_sha256": digest_object(list(evidence.interpretations)),
        "assets_sha256": digest_object(list(evidence.assets)),
        "releases_sha256": digest_object(list(evidence.releases)),
        "qualification_gates_sha256": digest_object(list(evidence.qualification_gates)),
        "commitments_sha256": digest_object(list(evidence.commitments)),
        "requirements_sha256": digest_object(
            {key: list(value) for key, value in evidence.requirements.items()}
        ),
    }


def select_and_validate_root(
    candidate: ParsedCandidate,
    evidence: ParsedEvidence,
    roots: tuple[ParsedRoot, ...],
    *,
    evidence_bytes: bytes,
    now: datetime,
    _policy_sha256: str = POLICY_SHA256,
    _section_digests=evidence_section_digests,
    _sha256_bytes=sha256_bytes,
    _sorted_unique=sorted_unique,
) -> tuple[ParsedRoot | None, list[str]]:
    blockers: list[str] = []
    if candidate.opportunity_id != evidence.opportunity_id:
        blockers.append("candidate_evidence_opportunity_mismatch")
    if candidate.counterparty_ref != evidence.counterparty_ref:
        blockers.append("candidate_evidence_counterparty_mismatch")
    if candidate.thread_id != evidence.thread_id:
        blockers.append("candidate_evidence_thread_mismatch")

    matching = [root for root in roots if root.opportunity_id == candidate.opportunity_id]
    if not matching:
        blockers.append("trusted_root_missing")
        return None, _sorted_unique(blockers)
    if len(matching) != 1:
        blockers.append("trusted_root_ambiguous")
        return None, _sorted_unique(blockers)
    root = matching[0]
    row = root.value
    if root.root_id != evidence.root_id:
        blockers.append("trusted_root_id_mismatch")
    if root.generation != evidence.generation:
        blockers.append("trusted_root_generation_mismatch")
    if root.counterparty_ref != candidate.counterparty_ref:
        blockers.append("trusted_root_counterparty_mismatch")
    if root.thread_id != candidate.thread_id:
        blockers.append("trusted_root_thread_mismatch")
    if now < root.active_from:
        blockers.append("trusted_root_not_yet_active")
    if now > root.expires_at:
        blockers.append("trusted_root_expired")
    if row["policy_sha256"] != _policy_sha256:
        blockers.append("trusted_policy_identity_mismatch")
    if row["evidence_sha256"] != _sha256_bytes(evidence_bytes):
        blockers.append("trusted_evidence_bytes_mismatch")
    section_digests = _section_digests(evidence)
    for key, actual in section_digests.items():
        if row[key] != actual:
            blockers.append(f"trusted_{key.removesuffix('_sha256')}_mismatch")
    return root, _sorted_unique(blockers)


def evaluate_evidence(
    candidate: ParsedCandidate,
    evidence: ParsedEvidence,
    *,
    now: datetime,
    _max_future_skew_seconds: int = _MAX_FUTURE_SKEW_SECONDS,
    _max_reply_age_seconds: int = _MAX_REPLY_AGE_SECONDS,
    _max_source_age_seconds: int = _MAX_SOURCE_AGE_SECONDS,
    _timedelta=timedelta,
    _sorted_unique=sorted_unique,
) -> dict[str, Any]:
    future_skew = _timedelta(seconds=_max_future_skew_seconds)
    reply_age = _timedelta(seconds=_max_reply_age_seconds)
    source_age = _timedelta(seconds=_max_source_age_seconds)
    blockers: list[str] = []
    owner_actions: list[str] = []

    if candidate.opportunity_id != evidence.opportunity_id:
        blockers.append("candidate_evidence_opportunity_mismatch")
    if candidate.counterparty_ref != evidence.counterparty_ref:
        blockers.append("candidate_evidence_counterparty_mismatch")
    if candidate.thread_id != evidence.thread_id:
        blockers.append("candidate_evidence_thread_mismatch")
    if evidence.captured_at > now + future_skew:
        blockers.append("source_capture_in_future")
    if now - evidence.captured_at > source_age:
        blockers.append("source_capture_stale")

    observations = {row["observation_id"]: row for row in evidence.observations}
    roots = [row for row in evidence.observations if row["supersedes"] is None]
    children: dict[str, list[str]] = {key: [] for key in observations}
    for row in evidence.observations:
        predecessor = row["supersedes"]
        if predecessor is None:
            continue
        if predecessor not in observations:
            blockers.append(f"supersession_predecessor_missing:{row['observation_id']}")
            continue
        children[predecessor].append(row["observation_id"])
        if row["received_at"] <= observations[predecessor]["received_at"]:
            blockers.append(f"supersession_time_not_increasing:{row['observation_id']}")
    for predecessor, child_ids in children.items():
        if len(child_ids) > 1:
            blockers.append(f"supersession_fork:{predecessor}")
    if len(roots) != 1:
        blockers.append("supersession_root_count_invalid")

    terminal: dict[str, Any] | None = None
    if len(roots) == 1:
        visited: set[str] = set()
        cursor = roots[0]["observation_id"]
        while cursor not in visited:
            visited.add(cursor)
            child_ids = children.get(cursor, [])
            if len(child_ids) == 0:
                terminal = observations[cursor]
                break
            if len(child_ids) != 1:
                break
            cursor = child_ids[0]
        if cursor in visited and terminal is None and len(children.get(cursor, [])) == 1:
            blockers.append("supersession_cycle")
        if len(visited) != len(observations):
            blockers.append("supersession_disconnected_terminal")

    interpretation_by_observation = {
        row["observation_id"]: row for row in evidence.interpretations
    }
    for observation_id, observation in observations.items():
        if observation["thread_id"] != candidate.thread_id:
            blockers.append(f"observation_cross_thread:{observation_id}")
        if observation["sender_ref"] not in evidence.counterparty_sender_refs:
            blockers.append(f"observation_sender_not_counterparty:{observation_id}")
        if observation["received_at"] > evidence.captured_at:
            blockers.append(f"observation_after_capture:{observation_id}")
        if observation["received_at"] > now + future_skew:
            blockers.append(f"observation_in_future:{observation_id}")
        interpretation = interpretation_by_observation.get(observation_id)
        if interpretation is None:
            blockers.append(f"owner_interpretation_missing:{observation_id}")
            continue
        if interpretation["message_ref"] != observation["message_ref"]:
            blockers.append(f"owner_interpretation_message_mismatch:{observation_id}")
        if interpretation["content_sha256"] != observation["content_sha256"]:
            blockers.append(f"owner_interpretation_content_mismatch:{observation_id}")
        if interpretation["reviewed_at"] < observation["received_at"]:
            blockers.append(f"owner_interpretation_before_message:{observation_id}")
        if interpretation["reviewed_at"] > evidence.captured_at:
            blockers.append(f"owner_interpretation_after_capture:{observation_id}")
        if interpretation["reviewed_at"] > now + future_skew:
            blockers.append(f"owner_interpretation_in_future:{observation_id}")

    current_interpretation: dict[str, Any] | None = None
    if terminal is not None:
        current_interpretation = interpretation_by_observation.get(terminal["observation_id"])
        if terminal["received_at"] < now - reply_age:
            blockers.append("current_reply_stale")
        if terminal["sender_ref"] not in evidence.counterparty_sender_refs:
            blockers.append("current_sender_not_counterparty")
    else:
        blockers.append("current_observation_missing")

    if not observations:
        blockers.append("retained_observation_missing")
    if not evidence.counterparty_sender_refs:
        blockers.append("counterparty_sender_binding_missing")

    reply_valid_until = (
        terminal["received_at"] + reply_age if terminal is not None else evidence.captured_at
    )
    source_valid_until = evidence.captured_at + source_age
    return {
        "blockers": _sorted_unique(blockers),
        "owner_actions": _sorted_unique(owner_actions),
        "current_observation": terminal,
        "current_interpretation": current_interpretation,
        "reply_valid_until": reply_valid_until,
        "source_valid_until": source_valid_until,
    }


def summarize_observation(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "observation_id": row["observation_id"],
        "message_ref": row["message_ref"],
        "source_class": row["source_class"],
        "sender_ref": row["sender_ref"],
        "thread_id": row["thread_id"],
        "received_at": format_timestamp(row["received_at"]),
        "content_sha256": row["content_sha256"],
    }


def summarize_interpretation(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "interpretation_id": row["interpretation_id"],
        "observation_id": row["observation_id"],
        "decision": row["decision"],
        "reviewed_at": format_timestamp(row["reviewed_at"]),
        "owner_review_ref": row["owner_review_ref"],
        "owner_review_sha256": row["owner_review_sha256"],
    }
