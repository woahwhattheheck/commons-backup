"""Atomic custody for one commercial pursuit.

The authoritative state is an append-only Git ref generation chain. A local
receipt never proves current custody: consumers must reacquire and replay the
live ref/tag chain before relying on WHOLE or delegated internal-work custody.

This package has no buyer/provider/send/payment authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Mapping, Optional, Sequence, Tuple

SCHEMA = "commercial-opportunity-custody/v1"
EVENT_SCHEMA = "commercial-opportunity-custody-event/v1"
MUTATION_RECEIPT_SCHEMA = "commercial-opportunity-custody-mutation-receipt/v1"
AUTHORITY_SCHEMA = "commercial-opportunity-custody-authority/v1"
LEGACY_SCHEMA = "commercial-opportunity-custody-legacy-import/v1"
REF_NAMESPACE = "commercial-opportunity-custody-v1"
TAGGER_NAME = "commercial-opportunity-custody"
TAGGER_EMAIL = "custody@tokenjunkielabs.invalid"
LANES = frozenset({"source", "proposal", "outreach", "scheduling", "fulfillment", "settlement"})
ACTIONS = frozenset({
    "ACQUIRE_WHOLE",
    "TRANSFER_WHOLE",
    "RELEASE_WHOLE",
    "SET_DELEGATE",
    "REVOKE_DELEGATE",
    "UPDATE_SOURCE",
})
INDETERMINATE = frozenset({0, 408, 500, 502, 503, 504})
_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")
_MACHINE_RE = re.compile(r"^[a-z0-9][a-z0-9._:/+\-]{0,190}$")
_ACTOR_RE = re.compile(r"^[A-Z0-9][A-Z0-9._:-]{2,95}$")
_OPERATION_RE = re.compile(r"^[A-Z0-9][A-Z0-9._:/+\-]{2,191}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
_GENERATION_REF_RE = re.compile(r"^refs/tags/" + re.escape(REF_NAMESPACE) + r"/([0-9a-f]{64})/g/([0-9]{10})$")


class CustodyError(ValueError):
    """Fail-closed contract or provider-state error."""


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise CustodyError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def strict_json_loads(raw: str) -> Any:
    try:
        return json.loads(
            raw,
            object_pairs_hook=_strict_object,
            parse_constant=lambda token: (_ for _ in ()).throw(CustodyError(f"non-finite JSON number: {token}")),
        )
    except json.JSONDecodeError as exc:
        raise CustodyError("invalid JSON") from exc


def canon_json(value: Any) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise CustodyError("value is not canonical JSON") from exc


def _sha256(value: Any) -> str:
    return hashlib.sha256(canon_json(value)).hexdigest()


def _normalize_domain(value: Any, field: str) -> str:
    if type(value) is not str:
        raise CustodyError(f"{field}: string required")
    candidate = value.strip().rstrip(".").casefold()
    if not candidate or len(candidate) > 253:
        raise CustodyError(f"{field}: non-empty domain <=253 chars required")
    if "://" in candidate or any(ch in candidate for ch in "/@?#"):
        raise CustodyError(f"{field}: organization/source domain required, not URL/address")
    try:
        ascii_domain = candidate.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise CustodyError(f"{field}: invalid IDNA domain") from exc
    labels = ascii_domain.split(".")
    if len(labels) < 2:
        raise CustodyError(f"{field}: dotted registrable-style domain required")
    for label in labels:
        if not label or len(label) > 63 or label[0] == "-" or label[-1] == "-" or re.fullmatch(r"[a-z0-9-]+", label) is None:
            raise CustodyError(f"{field}: invalid domain label")
    return ascii_domain


def _machine(value: Any, field: str) -> str:
    if type(value) is not str:
        raise CustodyError(f"{field}: string required")
    token = value.strip().casefold()
    if not token or _MACHINE_RE.fullmatch(token) is None:
        raise CustodyError(f"{field}: lowercase machine token required")
    return token


def _actor(value: Any, field: str) -> str:
    if type(value) is not str or _ACTOR_RE.fullmatch(value) is None:
        raise CustodyError(f"{field}: canonical uppercase actor id required")
    return value


def _operation(value: Any, field: str) -> str:
    if type(value) is not str or _OPERATION_RE.fullmatch(value) is None:
        raise CustodyError(f"{field}: canonical uppercase operation id required")
    return value


def _sha256_hex(value: Any, field: str) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise CustodyError(f"{field}: lowercase SHA-256 required")
    return value


def _git_sha(value: Any, field: str) -> str:
    if type(value) is not str:
        raise CustodyError(f"{field}: Git object id required")
    lowered = value.casefold()
    if value != lowered or _GIT_SHA_RE.fullmatch(value) is None:
        raise CustodyError(f"{field}: lowercase 40/64-hex Git object id required")
    return value


def _rfc3339(value: Any, field: str) -> str:
    if type(value) is not str or not value:
        raise CustodyError(f"{field}: RFC3339 timestamp required")
    raw = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise CustodyError(f"{field}: invalid RFC3339 timestamp") from exc
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise CustodyError(f"{field}: timezone required")
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _repo(value: Any) -> str:
    if type(value) is not str or _REPO_RE.fullmatch(value) is None:
        raise CustodyError("repo: owner/name required")
    # GitHub owner/repository paths are case-insensitive. The custody seam must
    # therefore collapse case aliases before hashing or the same repository can
    # acquire multiple independent generation-1 chains.
    return value.casefold()


def _nullable_actor(value: Any, field: str) -> Optional[str]:
    return None if value is None else _actor(value, field)


def _nullable_operation(value: Any, field: str) -> Optional[str]:
    return None if value is None else _operation(value, field)


def _nullable_sha256(value: Any, field: str) -> Optional[str]:
    return None if value is None else _sha256_hex(value, field)


@dataclass(frozen=True)
class Identity:
    repo: str
    buyer_scope: str
    authority_scope: str
    opportunity_id: str

    @classmethod
    def parse(cls, raw: Mapping[str, Any]) -> "Identity":
        expected = {"schema", "repo", "buyer_scope", "authority_scope", "opportunity_id"}
        if type(raw) is not dict or set(raw) != expected:
            raise CustodyError("identity: exact schema,repo,buyer_scope,authority_scope,opportunity_id required")
        if raw["schema"] != SCHEMA:
            raise CustodyError(f"identity.schema must be {SCHEMA}")
        return cls(
            _repo(raw["repo"]),
            _normalize_domain(raw["buyer_scope"], "buyer_scope"),
            _normalize_domain(raw["authority_scope"], "authority_scope"),
            _machine(raw["opportunity_id"], "opportunity_id"),
        )

    @property
    def document(self) -> dict[str, str]:
        return {
            "schema": SCHEMA,
            "repo": self.repo,
            "buyer_scope": self.buyer_scope,
            "authority_scope": self.authority_scope,
            "opportunity_id": self.opportunity_id,
        }

    @property
    def seam_sha256(self) -> str:
        return _sha256(self.document)

    @property
    def ref_prefix(self) -> str:
        return f"refs/tags/{REF_NAMESPACE}/{self.seam_sha256}/g/"

    def generation_ref(self, generation: int) -> str:
        if type(generation) is not int or isinstance(generation, bool) or not (1 <= generation <= 9_999_999_999):
            raise CustodyError("generation: integer 1..9999999999 required")
        return self.ref_prefix + f"{generation:010d}"


@dataclass(frozen=True)
class State:
    identity: Identity
    generation: int
    whole_owner: Optional[str]
    whole_operation: Optional[str]
    source_generation_sha256: Optional[str]
    delegates: Dict[str, Dict[str, Any]]
    latest_tag_sha: Optional[str]
    history_sha256: str

    @property
    def authority(self) -> dict[str, Any]:
        result = {
            **self.identity.document,
            "schema": AUTHORITY_SCHEMA,
            "seam_sha256": self.identity.seam_sha256,
            "generation": self.generation,
            "whole_owner": self.whole_owner,
            "whole_operation": self.whole_operation,
            "source_generation_sha256": self.source_generation_sha256,
            "delegates": {key: dict(self.delegates[key]) for key in sorted(self.delegates)},
            "latest_tag_sha": self.latest_tag_sha,
            "history_sha256": self.history_sha256,
            "internal_work_custody_only": True,
            "external_send_authorized": False,
            "proposal_submission_authorized": False,
            "buyer_acceptance_inferred": False,
            "payment_or_revenue_inferred": False,
        }
        result["authority_sha256"] = _sha256(result)
        return result


Transport = Callable[[str, str, Optional[Mapping[str, Any]]], Tuple[int, Any]]


def empty_state(identity: Identity) -> State:
    return State(identity, 0, None, None, None, {}, None, _sha256([]))


def _event_expected_keys() -> set[str]:
    return {
        "schema", "repo", "buyer_scope", "authority_scope", "opportunity_id", "seam_sha256",
        "generation", "previous_tag_sha", "action", "actor_owner", "actor_operation",
        "target_owner", "target_operation", "lane", "source_generation_sha256", "anchor_sha",
        "observed_at", "legacy_evidence_sha256", "external_action_authority",
    }


def _validate_event(raw: Mapping[str, Any], identity: Identity) -> dict[str, Any]:
    if type(raw) is not dict or set(raw) != _event_expected_keys():
        raise CustodyError("event: exact fields required")
    if raw["schema"] != EVENT_SCHEMA:
        raise CustodyError("event: unsupported schema")
    embedded = Identity.parse({
        "schema": SCHEMA,
        "repo": raw["repo"],
        "buyer_scope": raw["buyer_scope"],
        "authority_scope": raw["authority_scope"],
        "opportunity_id": raw["opportunity_id"],
    })
    if embedded != identity or raw["seam_sha256"] != identity.seam_sha256:
        raise CustodyError("event: identity/seam transplant")
    generation = raw["generation"]
    if type(generation) is not int or isinstance(generation, bool) or generation < 1:
        raise CustodyError("event.generation: positive integer required")
    previous = raw["previous_tag_sha"]
    if previous is not None:
        previous = _git_sha(previous, "event.previous_tag_sha")
    action = raw["action"]
    if action not in ACTIONS:
        raise CustodyError("event.action: unsupported action")
    actor_owner = _actor(raw["actor_owner"], "event.actor_owner")
    actor_operation = _operation(raw["actor_operation"], "event.actor_operation")
    target_owner = _nullable_actor(raw["target_owner"], "event.target_owner")
    target_operation = _nullable_operation(raw["target_operation"], "event.target_operation")
    if (target_owner is None) != (target_operation is None):
        raise CustodyError("event: target owner and operation must appear together")
    lane = raw["lane"]
    if lane is not None and lane not in LANES:
        raise CustodyError("event.lane: unsupported bounded lane")
    source_generation = _sha256_hex(raw["source_generation_sha256"], "event.source_generation_sha256")
    anchor_sha = _git_sha(raw["anchor_sha"], "event.anchor_sha")
    observed_at = _rfc3339(raw["observed_at"], "event.observed_at")
    legacy = _nullable_sha256(raw["legacy_evidence_sha256"], "event.legacy_evidence_sha256")
    if raw["external_action_authority"] is not False:
        raise CustodyError("event: custody may never authorize external action")
    return {
        **identity.document,
        "schema": EVENT_SCHEMA,
        "seam_sha256": identity.seam_sha256,
        "generation": generation,
        "previous_tag_sha": previous,
        "action": action,
        "actor_owner": actor_owner,
        "actor_operation": actor_operation,
        "target_owner": target_owner,
        "target_operation": target_operation,
        "lane": lane,
        "source_generation_sha256": source_generation,
        "anchor_sha": anchor_sha,
        "observed_at": observed_at,
        "legacy_evidence_sha256": legacy,
        "external_action_authority": False,
    }


def _apply_event(state: State, raw_event: Mapping[str, Any], tag_sha: str) -> State:
    event = _validate_event(raw_event, state.identity)
    tag_sha = _git_sha(tag_sha, "event tag sha")
    if event["generation"] != state.generation + 1:
        raise CustodyError("history: non-contiguous generation")
    if event["previous_tag_sha"] != state.latest_tag_sha:
        raise CustodyError("history: predecessor tag mismatch")

    action = event["action"]
    if event["legacy_evidence_sha256"] is not None and not (action == "ACQUIRE_WHOLE" and state.generation == 0):
        raise CustodyError("history: legacy evidence allowed only on initial whole acquisition")
    actor_pair = (event["actor_owner"], event["actor_operation"])
    current_pair = (state.whole_owner, state.whole_operation)

    whole_owner = state.whole_owner
    whole_operation = state.whole_operation
    source_generation = state.source_generation_sha256
    delegates = {key: dict(value) for key, value in state.delegates.items()}

    if action == "ACQUIRE_WHOLE":
        if whole_owner is not None:
            raise CustodyError("history: whole custody already active")
        if event["target_owner"] != event["actor_owner"] or event["target_operation"] != event["actor_operation"]:
            raise CustodyError("history: acquire target must equal actor")
        if event["lane"] is not None:
            raise CustodyError("history: acquire has no lane")
        if state.generation > 0 and event["source_generation_sha256"] != source_generation:
            raise CustodyError("history: reacquire cannot rewrite source generation")
        whole_owner, whole_operation = actor_pair
        source_generation = event["source_generation_sha256"]
        delegates.clear()
    else:
        if whole_owner is None or actor_pair != current_pair:
            raise CustodyError("history: mutation actor is not current whole owner+operation")
        if action != "UPDATE_SOURCE" and event["source_generation_sha256"] != source_generation:
            raise CustodyError("history: stale or rewritten source generation")

        if action == "TRANSFER_WHOLE":
            if event["lane"] is not None or event["target_owner"] is None:
                raise CustodyError("history: transfer requires target and no lane")
            if (event["target_owner"], event["target_operation"]) == current_pair:
                raise CustodyError("history: no-op whole transfer")
            whole_owner = event["target_owner"]
            whole_operation = event["target_operation"]
            delegates.clear()
        elif action == "RELEASE_WHOLE":
            if event["lane"] is not None or event["target_owner"] is not None:
                raise CustodyError("history: release requires null target/lane")
            whole_owner = None
            whole_operation = None
            delegates.clear()
        elif action == "SET_DELEGATE":
            if event["lane"] not in LANES or event["target_owner"] is None:
                raise CustodyError("history: delegate requires bounded lane and target")
            if (event["target_owner"], event["target_operation"]) == current_pair:
                raise CustodyError("history: whole owner already owns every lane")
            delegates[event["lane"]] = {
                "owner": event["target_owner"],
                "operation": event["target_operation"],
                "granted_generation": event["generation"],
            }
        elif action == "REVOKE_DELEGATE":
            if event["lane"] not in LANES or event["target_owner"] is not None:
                raise CustodyError("history: revoke requires bounded lane and null target")
            if event["lane"] not in delegates:
                raise CustodyError("history: cannot revoke absent delegate")
            del delegates[event["lane"]]
        elif action == "UPDATE_SOURCE":
            if event["lane"] is not None or event["target_owner"] is not None:
                raise CustodyError("history: source update requires null target/lane")
            if event["source_generation_sha256"] == source_generation:
                raise CustodyError("history: source update must advance digest")
            source_generation = event["source_generation_sha256"]
        else:  # pragma: no cover - guarded above
            raise CustodyError("history: unsupported action")

    history_material = {
        "previous_history_sha256": state.history_sha256,
        "event": event,
        "tag_sha": tag_sha,
    }
    return State(
        state.identity,
        event["generation"],
        whole_owner,
        whole_operation,
        source_generation,
        delegates,
        tag_sha,
        _sha256(history_material),
    )


def _tag_name(event: Mapping[str, Any]) -> str:
    digest = _sha256(event)
    return f"commercial-opportunity-custody-v1-{event['seam_sha256'][:16]}-g{event['generation']:010d}-{digest[:16]}"


def _tag_payload(event: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "tag": _tag_name(event),
        "message": canon_json(event).decode("ascii") + "\n",
        "object": event["anchor_sha"],
        "type": "commit",
        "tagger": {
            "name": TAGGER_NAME,
            "email": TAGGER_EMAIL,
            "date": event["observed_at"],
        },
    }


def _object_sha(payload: Any) -> Optional[str]:
    if type(payload) is not dict:
        return None
    obj = payload.get("object")
    sha = obj.get("sha") if type(obj) is dict else None
    if type(sha) is str and _GIT_SHA_RE.fullmatch(sha.casefold()) and sha == sha.casefold():
        return sha
    return None


def _ref_name(payload: Any) -> Optional[str]:
    if type(payload) is not dict:
        return None
    value = payload.get("ref")
    return value if type(value) is str else None


def read_live_state(identity_raw: Mapping[str, Any], transport: Transport) -> State:
    identity = Identity.parse(identity_raw)
    owner, repo_name = identity.repo.split("/", 1)
    suffix = f"tags/{REF_NAMESPACE}/{identity.seam_sha256}/g/"
    quoted = urllib.parse.quote(suffix, safe="/")
    status, body = transport("GET", f"/repos/{owner}/{repo_name}/git/matching-refs/{quoted}", None)
    if status != 200 or type(body) is not list:
        raise CustodyError(f"LIVE_REF_LIST_UNPROVEN_{status}")
    if not body:
        return empty_state(identity)

    refs: dict[int, Tuple[str, str]] = {}
    for row in body:
        ref = _ref_name(row)
        sha = _object_sha(row)
        if ref is None or sha is None:
            raise CustodyError("live history: malformed ref row")
        match = _GENERATION_REF_RE.fullmatch(ref)
        if match is None or match.group(1) != identity.seam_sha256:
            raise CustodyError("live history: unexpected ref under custody prefix")
        generation = int(match.group(2))
        if generation in refs:
            raise CustodyError("live history: duplicate generation ref")
        refs[generation] = (ref, sha)

    expected_generations = list(range(1, max(refs) + 1))
    if sorted(refs) != expected_generations:
        raise CustodyError("live history: generation gap")

    state = empty_state(identity)
    for generation in expected_generations:
        ref, tag_sha = refs[generation]
        expected_ref = identity.generation_ref(generation)
        if ref != expected_ref:
            raise CustodyError("live history: generation ref mismatch")
        tag_status, tag_body = transport("GET", f"/repos/{owner}/{repo_name}/git/tags/{tag_sha}", None)
        if tag_status != 200 or type(tag_body) is not dict:
            raise CustodyError(f"LIVE_TAG_UNPROVEN_{generation}_{tag_status}")
        if tag_body.get("sha") != tag_sha:
            raise CustodyError("live history: tag SHA/body mismatch")
        tagger = tag_body.get("tagger")
        obj = tag_body.get("object")
        if type(tagger) is not dict or type(obj) is not dict:
            raise CustodyError("live history: malformed annotated tag")
        if tagger.get("name") != TAGGER_NAME or tagger.get("email") != TAGGER_EMAIL:
            raise CustodyError("live history: unexpected tagger")
        message = tag_body.get("message")
        if type(message) is not str or not message.endswith("\n") or message.count("\n") != 1:
            raise CustodyError("live history: tag message must be one canonical JSON line")
        event_value = strict_json_loads(message[:-1])
        if type(event_value) is not dict:
            raise CustodyError("live history: event must be object")
        event = _validate_event(event_value, identity)
        if tag_body.get("tag") != _tag_name(event):
            raise CustodyError("live history: tag name/event mismatch")
        if obj.get("type") != "commit" or obj.get("sha") != event["anchor_sha"]:
            raise CustodyError("live history: annotated tag target mismatch")
        if _rfc3339(tagger.get("date"), "tagger.date") != event["observed_at"]:
            raise CustodyError("live history: tag date/event mismatch")
        state = _apply_event(state, event, tag_sha)
    return state


def _plan_event(
    state: State,
    *,
    action: str,
    actor_owner: str,
    actor_operation: str,
    anchor_sha: str,
    observed_at: str,
    source_generation_sha256: str,
    target_owner: Optional[str] = None,
    target_operation: Optional[str] = None,
    lane: Optional[str] = None,
    legacy_evidence_sha256: Optional[str] = None,
) -> dict[str, Any]:
    if action not in ACTIONS:
        raise CustodyError("action: unsupported")
    event = {
        **state.identity.document,
        "schema": EVENT_SCHEMA,
        "seam_sha256": state.identity.seam_sha256,
        "generation": state.generation + 1,
        "previous_tag_sha": state.latest_tag_sha,
        "action": action,
        "actor_owner": _actor(actor_owner, "actor_owner"),
        "actor_operation": _operation(actor_operation, "actor_operation"),
        "target_owner": _nullable_actor(target_owner, "target_owner"),
        "target_operation": _nullable_operation(target_operation, "target_operation"),
        "lane": lane,
        "source_generation_sha256": _sha256_hex(source_generation_sha256, "source_generation_sha256"),
        "anchor_sha": _git_sha(anchor_sha, "anchor_sha"),
        "observed_at": _rfc3339(observed_at, "observed_at"),
        "legacy_evidence_sha256": _nullable_sha256(legacy_evidence_sha256, "legacy_evidence_sha256"),
        "external_action_authority": False,
    }
    # Reuse the same state machine for pure preflight. Synthetic tag id is valid hex.
    _apply_event(state, event, "0" * 40)
    return _validate_event(event, state.identity)


def _publish_planned_event(identity: Identity, event: Mapping[str, Any], transport: Transport) -> dict[str, Any]:
    event = _validate_event(event, identity)
    owner, repo_name = identity.repo.split("/", 1)
    tag_payload = _tag_payload(event)
    tag_status, tag_body = transport("POST", f"/repos/{owner}/{repo_name}/git/tags", tag_payload)
    if tag_status != 201 or type(tag_body) is not dict:
        return _mutation_hold(identity, event, f"TAG_OBJECT_CREATE_FAILED_{tag_status}", None, None)
    try:
        tag_sha = _git_sha(tag_body.get("sha"), "tag response sha")
    except CustodyError:
        return _mutation_hold(identity, event, "TAG_OBJECT_CREATE_MALFORMED", None, None)

    ref = identity.generation_ref(event["generation"])
    ref_status, ref_body = transport("POST", f"/repos/{owner}/{repo_name}/git/refs", {"ref": ref, "sha": tag_sha})
    observed_sha = _object_sha(ref_body) if ref_status == 201 else None
    if ref_status == 201 and observed_sha == tag_sha:
        return _mutation_receipt(identity, event, tag_sha, observed_sha, True, "APPENDED_CREATE_201")

    if ref_status == 201 or ref_status == 422 or ref_status in INDETERMINATE:
        suffix = urllib.parse.quote(ref.removeprefix("refs/"), safe="/")
        read_status, read_body = transport("GET", f"/repos/{owner}/{repo_name}/git/ref/{suffix}", None)
        if read_status == 200:
            observed_sha = _object_sha(read_body)
            if observed_sha == tag_sha:
                return _mutation_receipt(identity, event, tag_sha, observed_sha, True, "APPENDED_READBACK_SELF")
            if observed_sha is not None:
                return _mutation_receipt(identity, event, tag_sha, observed_sha, False, "GENERATION_HELD_BY_OTHER")
            return _mutation_receipt(identity, event, tag_sha, None, False, "READBACK_OBJECT_INVALID")
        if read_status == 404:
            return _mutation_receipt(identity, event, tag_sha, None, False, "APPEND_OUTCOME_UNPROVEN")
        return _mutation_receipt(identity, event, tag_sha, None, False, f"READBACK_FAILED_{read_status}")

    return _mutation_receipt(identity, event, tag_sha, None, False, f"APPEND_REJECTED_{ref_status}")


def _mutation_hold(identity: Identity, event: Mapping[str, Any], reason: str, tag_sha: Optional[str], observed_sha: Optional[str]) -> dict[str, Any]:
    return _mutation_receipt(identity, event, tag_sha, observed_sha, False, reason)


def _mutation_receipt(identity: Identity, event: Mapping[str, Any], tag_sha: Optional[str], observed_sha: Optional[str], appended: bool, reason: str) -> dict[str, Any]:
    receipt = {
        **identity.document,
        "schema": MUTATION_RECEIPT_SCHEMA,
        "seam_sha256": identity.seam_sha256,
        "generation": event["generation"],
        "action": event["action"],
        "actor_owner": event["actor_owner"],
        "actor_operation": event["actor_operation"],
        "event_sha256": _sha256(event),
        "event_ref": identity.generation_ref(event["generation"]),
        "tag_object_sha": tag_sha,
        "observed_ref_sha": observed_sha,
        "event_appended": appended,
        "decision": "APPENDED_NOT_CURRENT_AUTHORITY" if appended else "HOLD",
        "reason": reason,
        "must_reread_live_authority_before_work": True,
        "external_send_authorized": False,
        "proposal_submission_authorized": False,
        "payment_or_revenue_inferred": False,
    }
    receipt["receipt_sha256"] = _sha256(receipt)
    return receipt


def verify_mutation_receipt(raw: Mapping[str, Any]) -> bool:
    expected = {
        "schema", "repo", "buyer_scope", "authority_scope", "opportunity_id", "seam_sha256",
        "generation", "action", "actor_owner", "actor_operation", "event_sha256", "event_ref",
        "tag_object_sha", "observed_ref_sha", "event_appended", "decision", "reason",
        "must_reread_live_authority_before_work", "external_send_authorized",
        "proposal_submission_authorized", "payment_or_revenue_inferred", "receipt_sha256",
    }
    if type(raw) is not dict or set(raw) != expected:
        raise CustodyError("mutation receipt: exact fields required")
    if raw["schema"] != MUTATION_RECEIPT_SCHEMA:
        raise CustodyError("mutation receipt: unsupported schema")
    identity = Identity.parse({key: raw[key] for key in ("schema", "repo", "buyer_scope", "authority_scope", "opportunity_id")} | {"schema": SCHEMA})
    if raw["seam_sha256"] != identity.seam_sha256:
        raise CustodyError("mutation receipt: seam mismatch")
    generation = raw["generation"]
    if type(generation) is not int or isinstance(generation, bool) or generation < 1:
        raise CustodyError("mutation receipt: bad generation")
    if raw["event_ref"] != identity.generation_ref(generation):
        raise CustodyError("mutation receipt: ref mismatch")
    if raw["action"] not in ACTIONS:
        raise CustodyError("mutation receipt: bad action")
    _actor(raw["actor_owner"], "receipt actor_owner")
    _operation(raw["actor_operation"], "receipt actor_operation")
    appended = raw["event_appended"]
    if type(appended) is not bool:
        raise CustodyError("mutation receipt: event_appended must be bool")
    if appended:
        _sha256_hex(raw["event_sha256"], "receipt event_sha256")
    elif raw["event_sha256"] is not None:
        _sha256_hex(raw["event_sha256"], "receipt event_sha256")
    if raw["tag_object_sha"] is not None:
        _git_sha(raw["tag_object_sha"], "receipt tag_object_sha")
    if raw["observed_ref_sha"] is not None:
        _git_sha(raw["observed_ref_sha"], "receipt observed_ref_sha")
    if raw["decision"] != ("APPENDED_NOT_CURRENT_AUTHORITY" if appended else "HOLD"):
        raise CustodyError("mutation receipt: decision mismatch")
    if appended and raw["tag_object_sha"] != raw["observed_ref_sha"]:
        raise CustodyError("mutation receipt: appended generation must bind exact live ref")
    if raw["must_reread_live_authority_before_work"] is not True:
        raise CustodyError("mutation receipt: live reread requirement immutable")
    if raw["external_send_authorized"] is not False or raw["proposal_submission_authorized"] is not False or raw["payment_or_revenue_inferred"] is not False:
        raise CustodyError("mutation receipt: external authority forbidden")
    digest = _sha256_hex(raw["receipt_sha256"], "receipt_sha256")
    material = dict(raw)
    del material["receipt_sha256"]
    if _sha256(material) != digest:
        raise CustodyError("mutation receipt: digest mismatch")
    return True


def _mutate(identity_raw: Mapping[str, Any], transport: Transport, **kwargs: Any) -> dict[str, Any]:
    identity = Identity.parse(identity_raw)
    state = read_live_state(identity.document, transport)
    try:
        event = _plan_event(state, **kwargs)
    except CustodyError as exc:
        # No Git object/ref mutation on an already-invalid request.
        return {
            **identity.document,
            "schema": MUTATION_RECEIPT_SCHEMA,
            "seam_sha256": identity.seam_sha256,
            "generation": state.generation + 1,
            "action": kwargs.get("action"),
            "actor_owner": kwargs.get("actor_owner"),
            "actor_operation": kwargs.get("actor_operation"),
            "event_sha256": None,
            "event_ref": identity.generation_ref(state.generation + 1),
            "tag_object_sha": None,
            "observed_ref_sha": None,
            "event_appended": False,
            "decision": "HOLD",
            "reason": f"PRECONDITION_{str(exc)}",
            "must_reread_live_authority_before_work": True,
            "external_send_authorized": False,
            "proposal_submission_authorized": False,
            "payment_or_revenue_inferred": False,
            "receipt_sha256": "",  # filled below
        }
    return _publish_planned_event(identity, event, transport)


def _seal_precondition_hold(receipt: dict[str, Any]) -> dict[str, Any]:
    material = dict(receipt)
    material.pop("receipt_sha256", None)
    receipt["receipt_sha256"] = _sha256(material)
    return receipt


def acquire_whole(identity_raw: Mapping[str, Any], *, actor_owner: str, actor_operation: str, source_generation_sha256: str, anchor_sha: str, observed_at: str, transport: Transport, legacy_evidence_sha256: Optional[str] = None) -> dict[str, Any]:
    return _mutate_sealed(identity_raw, transport,
        action="ACQUIRE_WHOLE", actor_owner=actor_owner, actor_operation=actor_operation,
        target_owner=actor_owner, target_operation=actor_operation, lane=None,
        source_generation_sha256=source_generation_sha256, anchor_sha=anchor_sha,
        observed_at=observed_at, legacy_evidence_sha256=legacy_evidence_sha256)


def transfer_whole(identity_raw: Mapping[str, Any], *, actor_owner: str, actor_operation: str, target_owner: str, target_operation: str, source_generation_sha256: str, anchor_sha: str, observed_at: str, transport: Transport) -> dict[str, Any]:
    return _mutate_sealed(identity_raw, transport,
        action="TRANSFER_WHOLE", actor_owner=actor_owner, actor_operation=actor_operation,
        target_owner=target_owner, target_operation=target_operation, lane=None,
        source_generation_sha256=source_generation_sha256, anchor_sha=anchor_sha,
        observed_at=observed_at, legacy_evidence_sha256=None)


def release_whole(identity_raw: Mapping[str, Any], *, actor_owner: str, actor_operation: str, source_generation_sha256: str, anchor_sha: str, observed_at: str, transport: Transport) -> dict[str, Any]:
    return _mutate_sealed(identity_raw, transport,
        action="RELEASE_WHOLE", actor_owner=actor_owner, actor_operation=actor_operation,
        target_owner=None, target_operation=None, lane=None,
        source_generation_sha256=source_generation_sha256, anchor_sha=anchor_sha,
        observed_at=observed_at, legacy_evidence_sha256=None)


def set_delegate(identity_raw: Mapping[str, Any], *, actor_owner: str, actor_operation: str, lane: str, target_owner: str, target_operation: str, source_generation_sha256: str, anchor_sha: str, observed_at: str, transport: Transport) -> dict[str, Any]:
    return _mutate_sealed(identity_raw, transport,
        action="SET_DELEGATE", actor_owner=actor_owner, actor_operation=actor_operation,
        target_owner=target_owner, target_operation=target_operation, lane=lane,
        source_generation_sha256=source_generation_sha256, anchor_sha=anchor_sha,
        observed_at=observed_at, legacy_evidence_sha256=None)


def revoke_delegate(identity_raw: Mapping[str, Any], *, actor_owner: str, actor_operation: str, lane: str, source_generation_sha256: str, anchor_sha: str, observed_at: str, transport: Transport) -> dict[str, Any]:
    return _mutate_sealed(identity_raw, transport,
        action="REVOKE_DELEGATE", actor_owner=actor_owner, actor_operation=actor_operation,
        target_owner=None, target_operation=None, lane=lane,
        source_generation_sha256=source_generation_sha256, anchor_sha=anchor_sha,
        observed_at=observed_at, legacy_evidence_sha256=None)


def update_source(identity_raw: Mapping[str, Any], *, actor_owner: str, actor_operation: str, new_source_generation_sha256: str, anchor_sha: str, observed_at: str, transport: Transport) -> dict[str, Any]:
    return _mutate_sealed(identity_raw, transport,
        action="UPDATE_SOURCE", actor_owner=actor_owner, actor_operation=actor_operation,
        target_owner=None, target_operation=None, lane=None,
        source_generation_sha256=new_source_generation_sha256, anchor_sha=anchor_sha,
        observed_at=observed_at, legacy_evidence_sha256=None)


def _mutate_sealed(identity_raw: Mapping[str, Any], transport: Transport, **kwargs: Any) -> dict[str, Any]:
    result = _mutate(identity_raw, transport, **kwargs)
    if result.get("receipt_sha256") == "":
        return _seal_precondition_hold(result)
    return result


def authorize_internal_work(identity_raw: Mapping[str, Any], *, actor_owner: str, actor_operation: str, lane: str, transport: Transport) -> dict[str, Any]:
    state = read_live_state(identity_raw, transport)
    actor = (_actor(actor_owner, "actor_owner"), _operation(actor_operation, "actor_operation"))
    if lane == "whole":
        allowed = actor == (state.whole_owner, state.whole_operation)
        basis = "WHOLE" if allowed else "NO_CURRENT_CUSTODY"
    else:
        if lane not in LANES:
            raise CustodyError("lane: expected whole or supported bounded lane")
        if actor == (state.whole_owner, state.whole_operation):
            allowed, basis = True, "WHOLE"
        else:
            delegate = state.delegates.get(lane)
            allowed = delegate is not None and actor == (delegate["owner"], delegate["operation"])
            basis = f"DELEGATE:{lane}" if allowed else "NO_CURRENT_CUSTODY"
    result = {
        "schema": "commercial-opportunity-custody-work-check/v1",
        "seam_sha256": state.identity.seam_sha256,
        "generation": state.generation,
        "history_sha256": state.history_sha256,
        "actor_owner": actor[0],
        "actor_operation": actor[1],
        "lane": lane,
        "internal_work_authorized": bool(allowed),
        "basis": basis,
        "external_send_authorized": False,
        "proposal_submission_authorized": False,
        "payment_or_revenue_inferred": False,
    }
    result["check_sha256"] = _sha256(result)
    return result


def compile_legacy_import(identity_raw: Mapping[str, Any], *, prior_owner: str, prior_operation: str, evidence_sha256: str, observed_at: str) -> dict[str, Any]:
    identity = Identity.parse(identity_raw)
    result = {
        **identity.document,
        "schema": LEGACY_SCHEMA,
        "seam_sha256": identity.seam_sha256,
        "prior_owner": _actor(prior_owner, "prior_owner"),
        "prior_operation": _operation(prior_operation, "prior_operation"),
        "evidence_sha256": _sha256_hex(evidence_sha256, "evidence_sha256"),
        "observed_at": _rfc3339(observed_at, "observed_at"),
        "decision": "LEGACY_CUSTODY_REQUIRES_CANONICAL_OWNER_SEED",
        "custody_authorized": False,
        "external_send_authorized": False,
        "proposal_submission_authorized": False,
        "payment_or_revenue_inferred": False,
    }
    result["receipt_sha256"] = _sha256(result)
    return result


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> Any:
        return None


class GitHubTransport:
    """Narrow Git data transport. Token is read by caller from environment."""

    def __init__(self, token: str, *, timeout: float = 15.0) -> None:
        if not token:
            raise CustodyError("GitHub token required")
        self._token = token
        self._timeout = timeout
        context = ssl.create_default_context()
        self._opener = urllib.request.build_opener(_NoRedirect(), urllib.request.HTTPSHandler(context=context))

    def __call__(self, method: str, path: str, body: Optional[Mapping[str, Any]]) -> Tuple[int, Any]:
        if method not in {"GET", "POST"} or not path.startswith("/repos/"):
            raise CustodyError("unsupported GitHub transport request")
        data = canon_json(body) if body is not None else None
        request = urllib.request.Request(
            "https://api.github.com" + path,
            data=data,
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
                "User-Agent": "tjlabs-commercial-opportunity-custody/1",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            with self._opener.open(request, timeout=self._timeout) as response:
                raw = response.read()
                return int(response.status), json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            try:
                payload = json.loads(raw) if raw else None
            except json.JSONDecodeError:
                payload = None
            return int(exc.code), payload
        except (urllib.error.URLError, TimeoutError, OSError):
            return 0, None


def _load_identity(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        raw = handle.read(65537)
    if len(raw.encode("utf-8")) > 65536:
        raise CustodyError("identity file exceeds 64 KiB")
    value = strict_json_loads(raw)
    if type(value) is not dict:
        raise CustodyError("identity file must contain an object")
    return value


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Read or mutate commercial-opportunity custody")
    parser.add_argument("identity_json", help="strict identity JSON file")
    parser.add_argument("command", choices=["read", "authorize", "legacy-import"])
    parser.add_argument("--actor")
    parser.add_argument("--operation")
    parser.add_argument("--lane", default="whole")
    parser.add_argument("--evidence-sha256")
    parser.add_argument("--observed-at")
    parser.add_argument("--token-env", default="GITHUB_TOKEN")
    args = parser.parse_args(argv)
    try:
        identity_raw = _load_identity(args.identity_json)
        if args.command == "legacy-import":
            if None in (args.actor, args.operation, args.evidence_sha256, args.observed_at):
                raise CustodyError("legacy-import requires actor, operation, evidence sha256, observed-at")
            result = compile_legacy_import(identity_raw, prior_owner=args.actor, prior_operation=args.operation, evidence_sha256=args.evidence_sha256, observed_at=args.observed_at)
        else:
            token = os.environ.get(args.token_env, "")
            transport = GitHubTransport(token)
            if args.command == "read":
                result = read_live_state(identity_raw, transport).authority
            else:
                if None in (args.actor, args.operation):
                    raise CustodyError("authorize requires actor and operation")
                result = authorize_internal_work(identity_raw, actor_owner=args.actor, actor_operation=args.operation, lane=args.lane, transport=transport)
    except (OSError, CustodyError) as exc:
        print(f"HOLD: {exc}", file=sys.stderr)
        return 2
    print(canon_json(result).decode("ascii"))
    if args.command == "authorize" and not result["internal_work_authorized"]:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
