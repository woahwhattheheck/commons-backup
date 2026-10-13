#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

CANDIDATE_SCHEMA = "muse-publication-candidate/v1"
SNAPSHOT_SCHEMA = "muse-publication-arbitration-snapshot/v1"
RECEIPT_SCHEMA = "muse-publication-selection-receipt/v2"
LEGACY_RECEIPT_SCHEMA = "muse-publication-selection-receipt/v1"
LEASE_RECEIPT_SCHEMA = "outbound-send-lease-receipt/v3"
LEASE_BINDING_SCHEMA = "outbound-lease-public-binding/v1"

SELECTED = "SELECTED"
NOT_SELECTED = "NOT_SELECTED"
HOLD = "HOLD"
EVENT_TYPES = {"CANDIDATE", "SELECTED", "NOT_SELECTED", "CANCELLED"}
DECISION_EVENTS = EVENT_TYPES - {"CANDIDATE"}
ROUTES = {"EMAIL", "CONTACT_FORM", "DIRECT_MESSAGE", "PORTAL_MESSAGE"}

HEX64 = re.compile(r"^[0-9a-f]{64}$")
SLACK_ID = re.compile(r"^[A-Z][A-Z0-9]{2,31}$")
SLACK_TS = re.compile(r"^\d{10,}\.\d{6}$")
MAX_EVENTS = 256
UNAUTHENTICATED_SNAPSHOT_REASON = "SNAPSHOT_AUTHORITY_UNVERIFIED"
CURRENT_POSITIVE_DISABLED_REASON = "CURRENT_SELECTED_REQUIRES_PROVIDER_AUTHENTICATED_SNAPSHOT"


class MuseSelectionError(ValueError):
    pass


class DuplicateKeyError(MuseSelectionError):
    pass


def _pairs(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise DuplicateKeyError(f"duplicate JSON object key: {k}")
        out[k] = v
    return out


def obj(v, label):
    if type(v) is not dict:
        raise MuseSelectionError(f"{label} must be an object")
    return v


def arr(v, label):
    if type(v) is not list:
        raise MuseSelectionError(f"{label} must be a list")
    if len(v) > MAX_EVENTS:
        raise MuseSelectionError(f"{label} exceeds {MAX_EVENTS} entries")
    return v


def boolean(v, label):
    if type(v) is not bool:
        raise MuseSelectionError(f"{label} must be a boolean")
    return v


def text(v, label, n=256):
    if type(v) is not str:
        raise MuseSelectionError(f"{label} must be a string")
    v = v.strip()
    if not v:
        raise MuseSelectionError(f"{label} must not be empty")
    if len(v) > n:
        raise MuseSelectionError(f"{label} exceeds {n} characters")
    if any(ord(c) < 32 for c in v):
        raise MuseSelectionError(f"{label} contains control characters")
    return v


def slack(v, label):
    v = text(v, label, 32)
    if not SLACK_ID.fullmatch(v):
        raise MuseSelectionError(f"{label} is not a canonical Slack identifier")
    return v


def slack_ts(v, label):
    v = text(v, label, 32)
    if not SLACK_TS.fullmatch(v):
        raise MuseSelectionError(f"{label} must be a canonical Slack message timestamp")
    return v


def hex64(v, label):
    v = text(v, label, 64)
    if not HEX64.fullmatch(v):
        raise MuseSelectionError(f"{label} must be lowercase SHA-256 hex")
    return v


def keys(o, allowed, label):
    extra = set(o) - set(allowed)
    if extra:
        raise MuseSelectionError(f"{label} has unknown fields: {', '.join(sorted(extra))}")


def time(v, label):
    s = text(v, label, 64)
    s = s[:-1] + "+00:00" if s.endswith("Z") else s
    try:
        d = datetime.fromisoformat(s)
    except ValueError as e:
        raise MuseSelectionError(f"{label} must be ISO-8601") from e
    if d.tzinfo is None or d.utcoffset() is None:
        raise MuseSelectionError(f"{label} must include a timezone")
    return d.astimezone(timezone.utc)


def fmt(d):
    d = d.astimezone(timezone.utc)
    return d.isoformat(timespec="microseconds" if d.microsecond else "seconds").replace("+00:00", "Z")


def _utc_now():
    return datetime.now(timezone.utc)


def canonical_bytes(v):
    try:
        return (json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()
    except (TypeError, ValueError) as e:
        raise MuseSelectionError(f"value is not canonical JSON: {e}") from e


def digest_object(v):
    return hashlib.sha256(canonical_bytes(v)).hexdigest()


def parse_json_bytes(raw, label):
    try:
        s = raw.decode("utf-8", "strict")
    except UnicodeDecodeError as e:
        raise MuseSelectionError(f"{label} must be UTF-8 JSON") from e
    try:
        v = json.loads(s, object_pairs_hook=_pairs, parse_constant=lambda x: (_ for _ in ()).throw(MuseSelectionError(f"{label} contains non-finite number {x}")))
    except (DuplicateKeyError, MuseSelectionError):
        raise
    except json.JSONDecodeError as e:
        raise MuseSelectionError(f"{label} is not valid JSON: {e.msg}") from e
    return obj(v, label)


def normalize_lease(raw):
    o = obj(raw, "candidate.lease")
    fields = {"schema", "claimant", "claim_id", "lease_ref", "claim_capability_sha256", "receipt_sha256"}
    keys(o, fields, "candidate.lease")
    if o.get("schema") != LEASE_RECEIPT_SCHEMA:
        raise MuseSelectionError(f"candidate.lease.schema must equal {LEASE_RECEIPT_SCHEMA!r}")
    ref = text(o.get("lease_ref"), "candidate.lease.lease_ref", 512)
    if not ref.startswith("refs/heads/outbound-lease-v3/"):
        raise MuseSelectionError("candidate.lease.lease_ref must use the outbound v3 namespace")
    return {"schema": LEASE_RECEIPT_SCHEMA, "claimant": text(o.get("claimant"), "candidate.lease.claimant"), "claim_id": text(o.get("claim_id"), "candidate.lease.claim_id"), "lease_ref": ref, "claim_capability_sha256": hex64(o.get("claim_capability_sha256"), "candidate.lease.claim_capability_sha256"), "receipt_sha256": hex64(o.get("receipt_sha256"), "candidate.lease.receipt_sha256")}


def normalize_candidate(raw):
    o = obj(raw, "candidate")
    fields = {"schema_version", "candidate_id", "worker_id", "buyer_scope_sha256", "recipient_fingerprint", "offer_scope", "route_kind", "message_sha256", "requested_at", "lease"}
    keys(o, fields, "candidate")
    if o.get("schema_version") != CANDIDATE_SCHEMA:
        raise MuseSelectionError(f"candidate.schema_version must equal {CANDIDATE_SCHEMA!r}")
    route = text(o.get("route_kind"), "candidate.route_kind", 32)
    if route not in ROUTES:
        raise MuseSelectionError("candidate.route_kind must be one of " + ", ".join(sorted(ROUTES)))
    worker = text(o.get("worker_id"), "candidate.worker_id")
    lease = normalize_lease(o.get("lease"))
    if lease["claimant"] != worker:
        raise MuseSelectionError("candidate.lease.claimant must equal candidate.worker_id")
    return {"schema_version": CANDIDATE_SCHEMA, "candidate_id": text(o.get("candidate_id"), "candidate.candidate_id"), "worker_id": worker, "buyer_scope_sha256": hex64(o.get("buyer_scope_sha256"), "candidate.buyer_scope_sha256"), "recipient_fingerprint": hex64(o.get("recipient_fingerprint"), "candidate.recipient_fingerprint"), "offer_scope": text(o.get("offer_scope"), "candidate.offer_scope"), "route_kind": route, "message_sha256": hex64(o.get("message_sha256"), "candidate.message_sha256"), "requested_at": fmt(time(o.get("requested_at"), "candidate.requested_at")), "lease": lease}


def publication_key(c):
    return digest_object({"schema_version": "muse-publication-key/v1", "buyer_scope_sha256": c["buyer_scope_sha256"], "recipient_fingerprint": c["recipient_fingerprint"], "offer_scope": c["offer_scope"], "route_kind": c["route_kind"]})


def candidate_digest(c):
    return digest_object(c)


def lease_binding_digest(c):
    return digest_object({"schema_version": LEASE_BINDING_SCHEMA, **c["lease"]})


def normalize_event(raw, i):
    label = f"snapshot.events[{i}]"
    o = obj(raw, label)
    fields = {"message_id", "sender_user_id", "observed_at", "event_type", "publication_key", "candidate_digest", "candidate_id", "worker_id"}
    keys(o, fields, label)
    typ = text(o.get("event_type"), label + ".event_type", 32)
    if typ not in EVENT_TYPES:
        raise MuseSelectionError(f"{label}.event_type is invalid")
    return {"message_id": slack_ts(o.get("message_id"), label + ".message_id"), "sender_user_id": slack(o.get("sender_user_id"), label + ".sender_user_id"), "observed_at": fmt(time(o.get("observed_at"), label + ".observed_at")), "event_type": typ, "publication_key": hex64(o.get("publication_key"), label + ".publication_key"), "candidate_digest": hex64(o.get("candidate_digest"), label + ".candidate_digest"), "candidate_id": text(o.get("candidate_id"), label + ".candidate_id"), "worker_id": text(o.get("worker_id"), label + ".worker_id")}


def normalize_snapshot(raw):
    o = obj(raw, "snapshot")
    fields = {"schema_version", "complete", "conversation_id", "arbiter_user_id", "coverage_started_at", "captured_at", "events"}
    keys(o, fields, "snapshot")
    if o.get("schema_version") != SNAPSHOT_SCHEMA:
        raise MuseSelectionError(f"snapshot.schema_version must equal {SNAPSHOT_SCHEMA!r}")
    return {"schema_version": SNAPSHOT_SCHEMA, "complete": boolean(o.get("complete"), "snapshot.complete"), "conversation_id": slack(o.get("conversation_id"), "snapshot.conversation_id"), "arbiter_user_id": slack(o.get("arbiter_user_id"), "snapshot.arbiter_user_id"), "coverage_started_at": fmt(time(o.get("coverage_started_at"), "snapshot.coverage_started_at")), "captured_at": fmt(time(o.get("captured_at"), "snapshot.captured_at")), "events": [normalize_event(v, i) for i, v in enumerate(arr(o.get("events"), "snapshot.events"))]}


def event_key(e):
    return (e["observed_at"], e["message_id"], e["event_type"], e["candidate_digest"], e["candidate_id"], e["worker_id"])


def dedupe(events):
    seen = {}
    reasons = []
    for e in events:
        if e["message_id"] not in seen:
            seen[e["message_id"]] = e
        elif seen[e["message_id"]] != e:
            reasons.append(f"CONFLICTING_MESSAGE_ID:{e['message_id']}")
    return sorted(seen.values(), key=event_key), reasons


def _selection_binding(c, s, selected, valid_until):
    return digest_object({"schema_version": "muse-publication-selection-binding/v2", "publication_key": publication_key(c), "candidate_digest": candidate_digest(c), "candidate_id": c["candidate_id"], "worker_id": c["worker_id"], "conversation_id": s["conversation_id"], "arbiter_user_id": s["arbiter_user_id"], "selection_message_id": selected["message_id"], "selected_at": selected["observed_at"], "valid_until": fmt(valid_until), "lease_binding_sha256": lease_binding_digest(c)})


def _build_receipt(c, s, decision, reasons, now, selected=None, selection_ttl_seconds=600):
    pk = publication_key(c)
    cd = candidate_digest(c)
    ld = lease_binding_digest(c)
    valid_until = None
    binding = None
    if selected is not None:
        valid_until_dt = time(selected["observed_at"], "selected_at") + timedelta(seconds=selection_ttl_seconds)
        valid_until = fmt(valid_until_dt)
        binding = _selection_binding(c, s, selected, valid_until_dt)
    r = {"schema_version": RECEIPT_SCHEMA, "authority_mode": "UNAUTHENTICATED_SNAPSHOT_ANALYSIS", "publication_key": pk, "candidate_digest": cd, "candidate_id": c["candidate_id"], "worker_id": c["worker_id"], "decision": decision, "reasons": sorted(set(reasons)), "compiled_at": fmt(now), "conversation_id": s["conversation_id"], "arbiter_user_id": s["arbiter_user_id"], "selection_message_id": selected["message_id"] if selected else None, "selected_at": selected["observed_at"] if selected else None, "valid_until": valid_until, "selection_binding_sha256": binding, "lease_binding_sha256": ld, "snapshot_authenticated": False, "snapshot_authentication_sha256": None, "requires_current_worker_lease_possession": True, "requires_fresh_provider_preflight": True, "side_effects_authorized": False}
    r["receipt_digest"] = digest_object(r)
    return r


def _evaluate_selection(c, s, *, expected_conversation_id, expected_arbiter_user_id, now, max_snapshot_age_seconds, max_future_skew_seconds, max_decision_latency_seconds, selection_ttl_seconds):
    reasons = []
    req = time(c["requested_at"], "candidate.requested_at")
    cov = time(s["coverage_started_at"], "snapshot.coverage_started_at")
    cap = time(s["captured_at"], "snapshot.captured_at")
    future = now + timedelta(seconds=max_future_skew_seconds)
    if not s["complete"]:
        reasons.append("SNAPSHOT_INCOMPLETE")
    if s["conversation_id"] != expected_conversation_id:
        reasons.append("WRONG_CONVERSATION")
    if s["arbiter_user_id"] != expected_arbiter_user_id:
        reasons.append("WRONG_ARBITER_IDENTITY")
    if req > future:
        reasons.append("REQUEST_IN_FUTURE")
    if cov > req:
        reasons.append("COVERAGE_STARTS_AFTER_REQUEST")
    if cap < req:
        reasons.append("SNAPSHOT_PRECEDES_REQUEST")
    if cap > future:
        reasons.append("SNAPSHOT_IN_FUTURE")
    if now - cap > timedelta(seconds=max_snapshot_age_seconds):
        reasons.append("SNAPSHOT_STALE")
    events, dup = dedupe(s["events"])
    reasons += dup
    pk = publication_key(c)
    cd = candidate_digest(c)
    rel = [e for e in events if e["publication_key"] == pk]
    for e in rel:
        et = time(e["observed_at"], "event.observed_at")
        if et < cov or et > cap:
            reasons.append(f"EVENT_OUTSIDE_SNAPSHOT:{e['message_id']}")
        if et > future:
            reasons.append(f"EVENT_IN_FUTURE:{e['message_id']}")
        if e["event_type"] in DECISION_EVENTS and e["sender_user_id"] != expected_arbiter_user_id:
            reasons.append(f"DECISION_NOT_FROM_ARBITER:{e['message_id']}")
    requests = [e for e in rel if e["event_type"] == "CANDIDATE" and e["candidate_digest"] == cd and e["candidate_id"] == c["candidate_id"] and e["worker_id"] == c["worker_id"]]
    request = requests[0] if len(requests) == 1 else None
    if request is None:
        reasons.append("EXACT_CANDIDATE_REQUEST_COUNT_NOT_ONE")
    elif time(request["observed_at"], "request.observed_at") < req:
        reasons.append("REQUEST_EVENT_PRECEDES_CANDIDATE_TIME")
    decisions = [e for e in rel if e["event_type"] in DECISION_EVENTS and e["sender_user_id"] == expected_arbiter_user_id]
    selected = [e for e in decisions if e["event_type"] == SELECTED]
    if len({e["candidate_digest"] for e in selected}) > 1:
        reasons.append("MULTIPLE_DISTINCT_WINNERS")
    exact = sorted([e for e in decisions if e["candidate_digest"] == cd and e["candidate_id"] == c["candidate_id"] and e["worker_id"] == c["worker_id"]], key=event_key)
    other = next((e for e in selected if e["candidate_digest"] != cd), None)
    if request:
        rt = time(request["observed_at"], "request.observed_at")
        for e in exact:
            dt = time(e["observed_at"], "decision.observed_at")
            if dt < rt:
                reasons.append(f"DECISION_PRECEDES_REQUEST:{e['message_id']}")
            if dt - rt > timedelta(seconds=max_decision_latency_seconds):
                reasons.append(f"DECISION_AFTER_LATENCY_LIMIT:{e['message_id']}")
    outcome = HOLD
    winner = None
    if not reasons:
        if exact:
            latest = exact[-1]
            if latest["event_type"] == SELECTED:
                if now - time(latest["observed_at"], "selected_at") > timedelta(seconds=selection_ttl_seconds):
                    reasons.append("SELECTION_EXPIRED")
                elif other:
                    reasons.append("COMPETING_WINNER")
                else:
                    outcome = SELECTED
                    winner = latest
            else:
                outcome = NOT_SELECTED
        elif other:
            outcome = NOT_SELECTED
        else:
            reasons.append("NO_ARBITER_DECISION")
    if reasons:
        outcome = HOLD
        winner = None
    return outcome, reasons, winner


def compile_selection(candidate_raw, snapshot_raw, *, expected_conversation_id, expected_arbiter_user_id, max_snapshot_age_seconds=120, max_future_skew_seconds=30, max_decision_latency_seconds=600, selection_ttl_seconds=600):
    """Compile a fail-closed current receipt from caller-supplied raw Muse snapshot data.

    Raw snapshot JSON is not independently authenticated by this module. It may
    support fail-closed analysis/denial, but it MUST NOT mint current SELECTED
    authority. A provider-authenticated adapter is required before that positive
    machine path can be re-enabled.
    """
    c = normalize_candidate(candidate_raw)
    s = normalize_snapshot(snapshot_raw)
    expected_conversation_id = slack(expected_conversation_id, "expected_conversation_id")
    expected_arbiter_user_id = slack(expected_arbiter_user_id, "expected_arbiter_user_id")
    for label, v, lo, hi in (("max_snapshot_age_seconds", max_snapshot_age_seconds, 1, 3600), ("max_future_skew_seconds", max_future_skew_seconds, 0, 300), ("max_decision_latency_seconds", max_decision_latency_seconds, 1, 3600), ("selection_ttl_seconds", selection_ttl_seconds, 1, 3600)):
        if type(v) is not int or not lo <= v <= hi:
            raise MuseSelectionError(f"{label} must be an integer between {lo} and {hi}")
    now = _utc_now()
    outcome, reasons, winner = _evaluate_selection(c, s, expected_conversation_id=expected_conversation_id, expected_arbiter_user_id=expected_arbiter_user_id, now=now, max_snapshot_age_seconds=max_snapshot_age_seconds, max_future_skew_seconds=max_future_skew_seconds, max_decision_latency_seconds=max_decision_latency_seconds, selection_ttl_seconds=selection_ttl_seconds)
    if outcome == SELECTED:
        outcome = HOLD
        reasons = [*reasons, UNAUTHENTICATED_SNAPSHOT_REASON, CURRENT_POSITIVE_DISABLED_REASON]
        winner = None
    return _build_receipt(c, s, outcome, reasons, now, winner, selection_ttl_seconds=selection_ttl_seconds)


def verify_receipt(raw):
    """Verify a current receipt; raw-snapshot SELECTED authority is fail-closed."""
    try:
        o = obj(raw, "receipt")
        fields = {"schema_version", "authority_mode", "publication_key", "candidate_digest", "candidate_id", "worker_id", "decision", "reasons", "compiled_at", "conversation_id", "arbiter_user_id", "selection_message_id", "selected_at", "valid_until", "selection_binding_sha256", "lease_binding_sha256", "snapshot_authenticated", "snapshot_authentication_sha256", "requires_current_worker_lease_possession", "requires_fresh_provider_preflight", "side_effects_authorized", "receipt_digest"}
        keys(o, fields, "receipt")
        if o.get("schema_version") != RECEIPT_SCHEMA:
            return False
        if o.get("authority_mode") != "UNAUTHENTICATED_SNAPSHOT_ANALYSIS":
            return False
        if o.get("decision") not in {SELECTED, NOT_SELECTED, HOLD}:
            return False
        hex64(o.get("publication_key"), "receipt.publication_key")
        hex64(o.get("candidate_digest"), "receipt.candidate_digest")
        text(o.get("candidate_id"), "receipt.candidate_id")
        text(o.get("worker_id"), "receipt.worker_id")
        compiled_at = time(o.get("compiled_at"), "receipt.compiled_at")
        slack(o.get("conversation_id"), "receipt.conversation_id")
        slack(o.get("arbiter_user_id"), "receipt.arbiter_user_id")
        hex64(o.get("lease_binding_sha256"), "receipt.lease_binding_sha256")
        reasons = arr(o.get("reasons"), "receipt.reasons")
        [text(x, f"receipt.reasons[{i}]", 512) for i, x in enumerate(reasons)]
        if o.get("snapshot_authenticated") is not False:
            return False
        if o.get("snapshot_authentication_sha256") is not None:
            return False
        if o.get("requires_current_worker_lease_possession") is not True or o.get("requires_fresh_provider_preflight") is not True or o.get("side_effects_authorized") is not False:
            return False
        now = _utc_now()
        if compiled_at > now + timedelta(seconds=30):
            return False
        if o["decision"] == SELECTED:
            return False
        if any(o.get(k) is not None for k in ("selection_message_id", "selected_at", "valid_until", "selection_binding_sha256")):
            return False
        claimed = hex64(o.get("receipt_digest"), "receipt.receipt_digest")
        material = dict(o)
        material.pop("receipt_digest")
        return claimed == digest_object(material)
    except MuseSelectionError:
        return False


def verify_selected_binding(candidate_raw, receipt_raw):
    if not verify_receipt(receipt_raw):
        return False
    r = obj(receipt_raw, "receipt")
    if r["decision"] != SELECTED:
        return False
    c = normalize_candidate(candidate_raw)
    return r["publication_key"] == publication_key(c) and r["candidate_digest"] == candidate_digest(c) and r["candidate_id"] == c["candidate_id"] and r["worker_id"] == c["worker_id"] and r["lease_binding_sha256"] == lease_binding_digest(c) and r["requires_current_worker_lease_possession"] is True and r["side_effects_authorized"] is False


def load(path, label):
    try:
        raw = Path(path).read_bytes()
    except OSError as e:
        raise MuseSelectionError(f"cannot read {label}: {e}") from e
    if len(raw) > 1_000_000:
        raise MuseSelectionError(f"{label} exceeds 1,000,000 bytes")
    return parse_json_bytes(raw, label)


def write_new(path, payload):
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except OSError as e:
        raise MuseSelectionError(f"cannot create output: {e}") from e
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
    except Exception:
        try:
            os.unlink(path)
        except OSError:
            pass
        raise


def main(argv=None):
    p = argparse.ArgumentParser(description="Compile one fail-closed Muse publication-selection analysis receipt. Raw snapshot JSON cannot mint current SELECTED authority.")
    p.add_argument("--candidate", required=True)
    p.add_argument("--snapshot", required=True)
    p.add_argument("--conversation-id", required=True)
    p.add_argument("--arbiter-user-id", required=True)
    p.add_argument("--out")
    a = p.parse_args(argv)
    try:
        r = compile_selection(load(a.candidate, "candidate"), load(a.snapshot, "snapshot"), expected_conversation_id=a.conversation_id, expected_arbiter_user_id=a.arbiter_user_id)
        payload = canonical_bytes(r)
        write_new(a.out, payload) if a.out else sys.stdout.buffer.write(payload)
        return {SELECTED: 0, NOT_SELECTED: 3, HOLD: 4}[r["decision"]]
    except MuseSelectionError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
