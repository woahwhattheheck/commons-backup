from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

SCHEMA = "commons.swarmops-dossier/v1"
LEGACY_OUTPUT_SCHEMA = "commons.swarmops-dossier-output/v3"
OUTPUT_SCHEMA = "commons.swarmops-dossier-output/v4"

SOURCE_KINDS = {
    "GIT_COMMIT", "GIT_BLOB", "TEST_RECEIPT", "CI_RUN", "PROVIDER_RECEIPT",
    "BUYER_RECEIPT", "PAYMENT_RECEIPT", "ACCOUNTING_RECEIPT",
}
OBSERVED_STATES = {
    "LANDED_VERIFIED", "TESTED_LOCAL", "QUEUED", "RUNNING", "PENDING",
    "SENT_NOT_ACCEPTED", "BUYER_ACCEPTED", "PAID", "REVENUE_RECOGNIZED",
    "HOLD", "UNVERIFIED", "BLOCKED",
}
PROSPECT_CLASSES = {"PUBLIC", "PROSPECT_SAFE", "OWNER_APPROVAL_REQUIRED", "INTERNAL_ONLY"}
COMMERCIAL_REQUIREMENTS = {
    "SENT_NOT_ACCEPTED": "PROVIDER_RECEIPT",
    "BUYER_ACCEPTED": "BUYER_RECEIPT",
    "PAID": "PAYMENT_RECEIPT",
    "REVENUE_RECOGNIZED": "ACCOUNTING_RECEIPT",
}
TRUSTED_COMMERCIAL_STATES = {"BUYER_ACCEPTED", "PAID", "REVENUE_RECOGNIZED"}
TECHNICAL_REQUIREMENTS = {
    "LANDED_VERIFIED": {"GIT_COMMIT", "GIT_BLOB"},
    "TESTED_LOCAL": {"TEST_RECEIPT"},
    "QUEUED": {"CI_RUN"},
    "RUNNING": {"CI_RUN"},
    "PENDING": {"CI_RUN"},
}
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:+#/-]{0,159}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
SAFE_CLAIM = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 .,:;()_+/#\'-]{0,599}$")
ROW_KEYS = {
    "capability_id",
    "source_id",
    "source_kind",
    "source_ref",
    "source_sha256",
    "observed_state",
    "observed_at",
    "freshness_seconds",
    "prospect_class",
    "required",
    "claim",
}
TRUST_RECORD_KEYS = {"portfolio_id"} | (ROW_KEYS - {"source_id"})


class DossierError(ValueError):
    pass


def strict_json_loads(text: str) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in items:
            if key in out:
                raise DossierError(f"duplicate JSON key: {key}")
            out[key] = value
        return out

    def bad_constant(value: str) -> None:
        raise DossierError(f"non-finite JSON number: {value}")

    try:
        return json.loads(text, object_pairs_hook=pairs, parse_constant=bad_constant)
    except DossierError:
        raise
    except (json.JSONDecodeError, TypeError) as exc:
        raise DossierError(f"invalid JSON: {exc}") from exc


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _exact_keys(obj: dict[str, Any], expected: set[str], where: str) -> None:
    if set(obj) != expected:
        missing = sorted(expected - set(obj))
        extra = sorted(set(obj) - expected)
        raise DossierError(f"{where}: key mismatch missing={missing} extra={extra}")


def _string(value: Any, name: str, *, max_len: int = 1000, pattern: re.Pattern[str] | None = None) -> str:
    if not isinstance(value, str) or not value or len(value) > max_len or any(ord(c) < 32 for c in value):
        raise DossierError(f"{name}: invalid string")
    if pattern is not None and not pattern.fullmatch(value):
        raise DossierError(f"{name}: invalid format")
    return value


def _int(value: Any, name: str, *, lo: int, hi: int) -> int:
    if type(value) is not int or not lo <= value <= hi:
        raise DossierError(f"{name}: invalid integer")
    return value


def _bool(value: Any, name: str) -> bool:
    if type(value) is not bool:
        raise DossierError(f"{name}: invalid boolean")
    return value


def _time(value: Any, name: str) -> datetime:
    text = _string(value, name, max_len=30)
    if not text.endswith("Z"):
        raise DossierError(f"{name}: UTC Z time required")
    try:
        dt = datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as exc:
        raise DossierError(f"{name}: invalid timestamp") from exc
    if dt.microsecond:
        raise DossierError(f"{name}: whole seconds required")
    return dt


def _validate_policy(policy: Any) -> dict[str, Any]:
    if not isinstance(policy, dict):
        raise DossierError("policy must be object")
    _exact_keys(policy, {"required_capabilities", "max_evidence_age_seconds", "max_rows"}, "policy")
    required = policy["required_capabilities"]
    if not isinstance(required, list) or len(required) > 128:
        raise DossierError("policy.required_capabilities invalid")
    clean: list[str] = []
    for idx, item in enumerate(required):
        clean.append(_string(item, f"policy.required_capabilities[{idx}]", max_len=80, pattern=SAFE_ID))
    if len(set(clean)) != len(clean):
        raise DossierError("policy.required_capabilities duplicate")
    return {
        "required_capabilities": sorted(clean),
        "max_evidence_age_seconds": _int(policy["max_evidence_age_seconds"], "policy.max_evidence_age_seconds", lo=60, hi=31_536_000),
        "max_rows": _int(policy["max_rows"], "policy.max_rows", lo=1, hi=2000),
    }


def _validate_row(raw: Any, idx: int) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise DossierError(f"evidence[{idx}] must be object")
    _exact_keys(raw, ROW_KEYS, f"evidence[{idx}]")
    row = {
        "capability_id": _string(raw["capability_id"], f"evidence[{idx}].capability_id", max_len=80, pattern=SAFE_ID),
        "source_id": _string(raw["source_id"], f"evidence[{idx}].source_id", max_len=120, pattern=SAFE_ID),
        "source_kind": _string(raw["source_kind"], f"evidence[{idx}].source_kind", max_len=32),
        "source_ref": _string(raw["source_ref"], f"evidence[{idx}].source_ref", max_len=160, pattern=SAFE_ID),
        "source_sha256": _string(raw["source_sha256"], f"evidence[{idx}].source_sha256", max_len=64, pattern=SHA256),
        "observed_state": _string(raw["observed_state"], f"evidence[{idx}].observed_state", max_len=32),
        "observed_at": _string(raw["observed_at"], f"evidence[{idx}].observed_at", max_len=30),
        "freshness_seconds": _int(raw["freshness_seconds"], f"evidence[{idx}].freshness_seconds", lo=60, hi=31_536_000),
        "prospect_class": _string(raw["prospect_class"], f"evidence[{idx}].prospect_class", max_len=32),
        "required": _bool(raw["required"], f"evidence[{idx}].required"),
        "claim": _string(raw["claim"], f"evidence[{idx}].claim", max_len=600, pattern=SAFE_CLAIM),
    }
    if row["source_kind"] not in SOURCE_KINDS:
        raise DossierError(f"evidence[{idx}].source_kind unsupported")
    if row["observed_state"] not in OBSERVED_STATES:
        raise DossierError(f"evidence[{idx}].observed_state unsupported")
    if row["prospect_class"] not in PROSPECT_CLASSES:
        raise DossierError(f"evidence[{idx}].prospect_class unsupported")
    _time(row["observed_at"], f"evidence[{idx}].observed_at")
    required_source = COMMERCIAL_REQUIREMENTS.get(row["observed_state"])
    if required_source and row["source_kind"] != required_source:
        raise DossierError(f"evidence[{idx}]: {row['observed_state']} requires {required_source}")
    technical_sources = TECHNICAL_REQUIREMENTS.get(row["observed_state"])
    if technical_sources and row["source_kind"] not in technical_sources:
        raise DossierError(f"evidence[{idx}]: {row['observed_state']} incompatible with {row['source_kind']}")
    return row


def _validate_trusted_commercial_receipts(value: Any) -> dict[str, dict[str, Any]]:
    if value is None:
        return {}
    if not isinstance(value, dict) or len(value) > 2000:
        raise DossierError("trusted_commercial_receipts must be object")
    clean: dict[str, dict[str, Any]] = {}
    for raw_id, raw_authority in value.items():
        source_id = _string(raw_id, "trusted_commercial_receipts.source_id", max_len=120, pattern=SAFE_ID)
        if not isinstance(raw_authority, dict):
            raise DossierError(f"trusted_commercial_receipts[{source_id}] must be object")
        _exact_keys(raw_authority, TRUST_RECORD_KEYS, f"trusted_commercial_receipts[{source_id}]")
        portfolio_id = _string(
            raw_authority["portfolio_id"],
            f"trusted_commercial_receipts[{source_id}].portfolio_id",
            max_len=80,
            pattern=SAFE_ID,
        )
        row = _validate_row(
            {"source_id": source_id, **{key: raw_authority[key] for key in ROW_KEYS if key != "source_id"}},
            -1,
        )
        if row["observed_state"] not in TRUSTED_COMMERCIAL_STATES:
            raise DossierError(f"trusted_commercial_receipts[{source_id}].observed_state unsupported")
        clean[source_id] = {"portfolio_id": portfolio_id, **{key: row[key] for key in ROW_KEYS if key != "source_id"}}
    return dict(sorted(clean.items()))


_MISMATCH_REASON = {
    "portfolio_id": "COMMERCIAL_RECEIPT_PORTFOLIO_MISMATCH",
    "capability_id": "COMMERCIAL_RECEIPT_CAPABILITY_MISMATCH",
    "source_kind": "COMMERCIAL_RECEIPT_KIND_MISMATCH",
    "source_ref": "COMMERCIAL_RECEIPT_REF_MISMATCH",
    "source_sha256": "COMMERCIAL_RECEIPT_DIGEST_MISMATCH",
    "observed_state": "COMMERCIAL_RECEIPT_STATE_MISMATCH",
    "observed_at": "COMMERCIAL_RECEIPT_OBSERVED_AT_MISMATCH",
    "freshness_seconds": "COMMERCIAL_RECEIPT_FRESHNESS_MISMATCH",
    "prospect_class": "COMMERCIAL_RECEIPT_PROSPECT_CLASS_MISMATCH",
    "required": "COMMERCIAL_RECEIPT_REQUIRED_MISMATCH",
    "claim": "COMMERCIAL_RECEIPT_CLAIM_MISMATCH",
}


def _commercial_authority_reasons(
    row: dict[str, Any], portfolio_id: str, trusted: dict[str, dict[str, Any]]
) -> list[str]:
    authority = trusted.get(row["source_id"])
    if authority is None:
        return ["UNTRUSTED_COMMERCIAL_RECEIPT"]
    expected = {"portfolio_id": portfolio_id, **{key: row[key] for key in ROW_KEYS if key != "source_id"}}
    return [_MISMATCH_REASON[key] for key in sorted(expected) if authority[key] != expected[key]]


def _row_class(
    row: dict[str, Any], portfolio_id: str, as_of: datetime,
    policy: dict[str, Any], trusted: dict[str, dict[str, Any]],
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    observed = _time(row["observed_at"], "observed_at")
    if observed > as_of:
        reasons.append("FUTURE_EVIDENCE")
    age = int((as_of - observed).total_seconds())
    max_age = min(row["freshness_seconds"], policy["max_evidence_age_seconds"])
    if age > max_age:
        reasons.append("STALE_EVIDENCE")
    if row["prospect_class"] == "INTERNAL_ONLY":
        reasons.append("INTERNAL_ONLY")
    elif row["prospect_class"] == "OWNER_APPROVAL_REQUIRED":
        reasons.append("OWNER_APPROVAL_REQUIRED")
    if row["observed_state"] in TRUSTED_COMMERCIAL_STATES:
        reasons.extend(_commercial_authority_reasons(row, portfolio_id, trusted))
    if reasons:
        return ("HELD" if row["required"] else "LIMITED"), reasons
    if row["observed_state"] in {"LANDED_VERIFIED", "TESTED_LOCAL", "BUYER_ACCEPTED", "PAID", "REVENUE_RECOGNIZED"}:
        return "DEMONSTRATED", []
    if row["observed_state"] in {"QUEUED", "RUNNING", "PENDING", "SENT_NOT_ACCEPTED"}:
        return "LIMITED", [row["observed_state"]]
    if row["observed_state"] in {"HOLD", "BLOCKED"}:
        return "HELD", [row["observed_state"]]
    return "UNKNOWN", [row["observed_state"]]


def _compile_at(packet: Any, policy: Any, as_of: str, trusted_commercial_receipts: Any = None) -> dict[str, Any]:
    """Deterministic v3 evaluator, retained for historical content replay."""
    as_of_dt = _time(as_of, "as_of")
    clean_policy = _validate_policy(policy)
    trusted = _validate_trusted_commercial_receipts(trusted_commercial_receipts)
    if not isinstance(packet, dict):
        raise DossierError("packet must be object")
    _exact_keys(packet, {"schema", "portfolio_id", "evidence"}, "packet")
    if packet["schema"] != SCHEMA:
        raise DossierError("unsupported packet schema")
    portfolio_id = _string(packet["portfolio_id"], "packet.portfolio_id", max_len=80, pattern=SAFE_ID)
    evidence = packet["evidence"]
    if not isinstance(evidence, list) or not evidence or len(evidence) > clean_policy["max_rows"]:
        raise DossierError("packet.evidence invalid")
    rows: list[dict[str, Any]] = []
    seen_sources: dict[str, str] = {}
    seen_cap_source: set[tuple[str, str]] = set()
    commercial_source_ids: set[str] = set()
    for idx, raw in enumerate(evidence):
        row = _validate_row(raw, idx)
        row_digest = digest(row)
        prior = seen_sources.get(row["source_id"])
        if prior is not None and prior != row_digest:
            raise DossierError(f"source_id changed payload: {row['source_id']}")
        seen_sources[row["source_id"]] = row_digest
        key = (row["capability_id"], row["source_id"])
        if key in seen_cap_source:
            raise DossierError(f"duplicate capability/source: {key[0]}/{key[1]}")
        seen_cap_source.add(key)
        if row["observed_state"] in TRUSTED_COMMERCIAL_STATES:
            commercial_source_ids.add(row["source_id"])
        classification, reasons = _row_class(row, portfolio_id, as_of_dt, clean_policy, trusted)
        rows.append({**row, "classification": classification, "reasons": reasons, "row_sha256": row_digest})
    unused_trust = sorted(set(trusted) - commercial_source_ids)
    if unused_trust:
        raise DossierError(f"unused trusted commercial receipt ids: {unused_trust}")
    rows.sort(key=lambda r: (r["capability_id"], r["source_id"]))
    required = set(clean_policy["required_capabilities"])
    for row in rows:
        if row["required"]:
            required.add(row["capability_id"])
    demonstrated_caps = {
        row["capability_id"] for row in rows
        if row["classification"] == "DEMONSTRATED" and row["prospect_class"] in {"PUBLIC", "PROSPECT_SAFE"}
        and row["observed_state"] in {"LANDED_VERIFIED", "TESTED_LOCAL"}
    }
    missing_required = sorted(required - demonstrated_caps)
    prospect_rows = [row for row in rows if row["prospect_class"] in {"PUBLIC", "PROSPECT_SAFE"}]
    counts = {name: 0 for name in ("DEMONSTRATED", "LIMITED", "HELD", "UNKNOWN")}
    for row in prospect_rows:
        counts[row["classification"]] += 1
    external_truth = {
        "buyer_accepted": any(r["classification"] == "DEMONSTRATED" and r["observed_state"] == "BUYER_ACCEPTED" for r in prospect_rows),
        "paid": any(r["classification"] == "DEMONSTRATED" and r["observed_state"] == "PAID" for r in prospect_rows),
        "revenue_recognized": any(r["classification"] == "DEMONSTRATED" and r["observed_state"] == "REVENUE_RECOGNIZED" for r in prospect_rows),
    }
    what_now = [
        {"capability_id": r["capability_id"], "claim": r["claim"], "source_id": r["source_id"], "source_sha256": r["source_sha256"]}
        for r in prospect_rows
        if r["classification"] == "DEMONSTRATED" and r["observed_state"] in {"LANDED_VERIFIED", "TESTED_LOCAL"}
    ]
    what_now.sort(key=lambda x: (x["capability_id"], x["source_id"]))
    projection_rows = [{
        "capability_id": r["capability_id"], "source_id": r["source_id"], "source_kind": r["source_kind"],
        "source_ref": r["source_ref"], "source_sha256": r["source_sha256"], "observed_state": r["observed_state"],
        "observed_at": r["observed_at"], "classification": r["classification"], "reasons": r["reasons"], "claim": r["claim"],
    } for r in prospect_rows]
    dossier = {
        "schema": LEGACY_OUTPUT_SCHEMA,
        "portfolio_id": portfolio_id,
        "as_of": as_of,
        "status": "HOLD" if missing_required else "READY_FOR_OWNER_REVIEW",
        "summary": {**counts, "required_capabilities": sorted(required), "missing_required_capabilities": missing_required},
        "external_truth": external_truth,
        "what_we_can_show_now": what_now,
        "evidence": projection_rows,
        "authority": {
            "send": False, "deploy": False, "credentials": False, "proposal": False, "pricing_commitment": False,
            "buyer_acceptance": False, "payment": False, "cash_assertion": False, "revenue_recognition": False,
        },
        "packet_sha256": digest({"schema": SCHEMA, "portfolio_id": portfolio_id, "evidence": [
            {k: r[k] for k in (
                "capability_id", "source_id", "source_kind", "source_ref", "source_sha256", "observed_state",
                "observed_at", "freshness_seconds", "prospect_class",
                "required",
                "claim"
            )} for r in rows
        ]}),
        "policy_sha256": digest(clean_policy),
        "trusted_commercial_receipts_sha256": digest(trusted),
    }
    dossier["receipt_sha256"] = digest(dossier)
    return dossier


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _temporal_dossier(dossier: dict[str, Any], mode: str) -> dict[str, Any]:
    result = {key: value for key, value in dossier.items() if key != "receipt_sha256"}
    result["schema"] = OUTPUT_SCHEMA
    result["evaluation_mode"] = mode
    if mode == "HISTORICAL_REPLAY":
        result["status"] = "HISTORICAL_READY" if dossier["status"] == "READY_FOR_OWNER_REVIEW" else "HISTORICAL_HOLD"
    result["receipt_sha256"] = digest(result)
    return result


def _reject_future_observations(packet: dict[str, Any], as_of: str) -> None:
    """Call only after the evaluator has validated the complete packet."""
    instant = _time(as_of, "as_of")
    for row in packet["evidence"]:
        if _time(row["observed_at"], "observed_at") > instant:
            raise DossierError(f"source {row['source_id']}: observation is later than the evaluation time")


def compile_current_dossier(packet: Any, policy: Any, trusted_commercial_receipts: Any = None) -> dict[str, Any]:
    """Evaluate once at process UTC. No caller-supplied clock is accepted."""
    as_of = _utc_now()
    dossier = _compile_at(packet, policy, as_of, trusted_commercial_receipts)
    _reject_future_observations(packet, as_of)
    return _temporal_dossier(dossier, "CURRENT")


def compile_historical_dossier(packet: Any, policy: Any, as_of: str, trusted_commercial_receipts: Any = None) -> dict[str, Any]:
    """Replay a past instant, explicitly without a present-readiness claim."""
    if _time(as_of, "as_of") > _time(_utc_now(), "process UTC"):
        raise DossierError("historical evaluation time is in the future")
    dossier = _compile_at(packet, policy, as_of, trusted_commercial_receipts)
    _reject_future_observations(packet, as_of)
    return _temporal_dossier(dossier, "HISTORICAL_REPLAY")


def compile_dossier(packet: Any, policy: Any, as_of: str, trusted_commercial_receipts: Any = None) -> dict[str, Any]:
    """Compatibility name for historical replay; use compile_current_dossier for now."""
    return compile_historical_dossier(packet, policy, as_of, trusted_commercial_receipts)


def verify_historical_dossier(packet: Any, policy: Any, as_of: str, candidate: Any, trusted_commercial_receipts: Any = None) -> bool:
    """Check historical integrity only, including archived v3 dossiers."""
    if not isinstance(candidate, dict):
        return False
    try:
        if candidate.get("schema") == LEGACY_OUTPUT_SCHEMA:
            if _time(as_of, "as_of") > _time(_utc_now(), "process UTC"):
                return False
            expected = _compile_at(packet, policy, as_of, trusted_commercial_receipts)
            _reject_future_observations(packet, as_of)
        else:
            expected = compile_historical_dossier(packet, policy, as_of, trusted_commercial_receipts)
        return canonical_bytes(expected) == canonical_bytes(candidate)
    except (DossierError, TypeError, ValueError, RecursionError):
        return False


def verify_dossier(packet: Any, policy: Any, as_of: str, candidate: Any, trusted_commercial_receipts: Any = None) -> bool:
    """Compatibility name: historical integrity is not current verification."""
    return verify_historical_dossier(packet, policy, as_of, candidate, trusted_commercial_receipts)


def verify_current_dossier(packet: Any, policy: Any, candidate: Any, trusted_commercial_receipts: Any = None) -> bool:
    """Check integrity and today's classifications; raise DossierError on failure.

    The machine clock is sampled once. A current dossier remains valid while its
    classifications still match, rather than failing whenever the second changes.
    This reuses retained observations; it does not poll their external providers.
    """
    now = _utc_now()
    if not isinstance(candidate, dict):
        raise DossierError("candidate must be an object")
    if candidate.get("schema") != OUTPUT_SCHEMA or candidate.get("evaluation_mode") != "CURRENT":
        raise DossierError("historical or legacy dossier is not current; use compile without --as-of")
    recorded_at = candidate.get("as_of")
    if _time(recorded_at, "candidate.as_of") > _time(now, "process UTC"):
        raise DossierError("candidate evaluation time is in the future")
    retained = _compile_at(packet, policy, recorded_at, trusted_commercial_receipts)
    _reject_future_observations(packet, recorded_at)
    expected = _temporal_dossier(retained, "CURRENT")
    if canonical_bytes(expected) != canonical_bytes(candidate):
        raise DossierError("dossier content, source packet, policy or commercial authority changed; recompile")
    current = _temporal_dossier(_compile_at(packet, policy, now, trusted_commercial_receipts), "CURRENT")
    ignored = {"as_of", "receipt_sha256"}
    if canonical_bytes({k: v for k, v in current.items() if k not in ignored}) != canonical_bytes({k: v for k, v in candidate.items() if k not in ignored}):
        old_rows = {row["source_id"]: row for row in candidate["evidence"]}
        changed = [row["source_id"] for row in current["evidence"] if row != old_rows.get(row["source_id"])]
        detail = ", ".join(changed[:8]) or "evidence posture"
        raise DossierError(f"evidence expired or classifications changed at {now}: {detail}; recompile")
    return True


def render_markdown(dossier: dict[str, Any]) -> str:
    status = dossier["status"]
    historical = dossier.get("evaluation_mode") != "CURRENT"
    s = dossier["summary"]
    lines = [
        f"# SwarmOps Evidence Dossier — {dossier['portfolio_id']}", "",
        f"Status: **{status}**", f"As of: `{dossier['as_of']}`", f"Receipt: `{dossier['receipt_sha256']}`", "",
        ("**Historical replay only — not a current readiness statement.**" if historical else
         "**Current at the recorded instant. Run verify before relying on its freshness.**"), "",
        "## What was demonstrated at the recorded instant" if historical else "## What we can show now", "",
    ]
    if dossier["what_we_can_show_now"]:
        for item in dossier["what_we_can_show_now"]:
            lines.append(f"- **{item['capability_id']}** — {item['claim']} (`{item['source_id']}`)")
    else:
        lines.append("- No prospect-safe demonstrated item is evidenced at the recorded instant.")
    lines += ["", "## Evidence posture", "", f"- Demonstrated: {s['DEMONSTRATED']}", f"- Limited: {s['LIMITED']}", f"- Held: {s['HELD']}", f"- Unknown: {s['UNKNOWN']}"]
    if s["missing_required_capabilities"]:
        lines.append(f"- Missing required: {', '.join(s['missing_required_capabilities'])}")
    for row in dossier["evidence"]:
        if row["reasons"]:
            lines.append(f"- {row['source_id']}: {', '.join(row['reasons'])}")
    x = dossier["external_truth"]
    lines += ["", "## External commercial truth", "", f"- Buyer accepted: {str(x['buyer_accepted']).lower()}", f"- Paid: {str(x['paid']).lower()}", f"- Revenue recognized: {str(x['revenue_recognized']).lower()}", "", "## Authority ceiling", "", "This dossier is offline evidence for owner review. It does not authorize sends, deployment, credentials, proposals, pricing commitments, acceptance claims, payment actions, cash assertions, or revenue recognition.", ""]
    return "\n".join(lines)

