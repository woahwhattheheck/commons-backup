from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
import os
import stat
import sys
from pathlib import Path
from typing import Any, Iterable

DIAGNOSTIC_SCHEMA = "commons.completed-diagnostic/v1"
CATALOG_SCHEMA = "commons.owner-review-offer-catalog/v1"
PACKET_SCHEMA = "commons.diagnostic-followon-ladder/v1"
COMMERCIAL_STATE = "PROPOSED_NOT_ACCEPTED"
MAX_BYTES = 4_000_000
MAX_FINDINGS = 100
MAX_OFFERS = 100
MAX_EVIDENCE = 200
MAX_TEXT = 4096

STATUSES = {
    "NO_NEXT_STEP",
    "OWNER_REVIEW_UPSELL_CANDIDATE",
    "HOLD_EVIDENCE_INSUFFICIENT",
    "HOLD_UNRESOLVED_BLOCKER",
    "HOLD_SCOPE_CONTRADICTION",
    "HOLD_CATALOG_INVALID",
    "HOLD_SOURCE_DRIFT",
}

AUTHORITY_KEYS = (
    "external_send_authorized",
    "buyer_contact_authorized",
    "buyer_acceptance_inferred",
    "contract_acceptance_authorized",
    "change_acceptance_authorized",
    "invoice_creation_authorized",
    "invoice_send_authorized",
    "payment_request_authorized",
    "payment_link_creation_authorized",
    "provider_mutation_authorized",
    "customer_result_claimed",
    "savings_claimed",
    "accounting_revenue_recognition_authorized",
    "cash_or_revenue_claimed",
)

DIAGNOSTIC_KEYS = {
    "schema",
    "diagnostic_id",
    "source_product",
    "completed_at",
    "buyer_scope",
    "findings",
    "holds",
}
SOURCE_PRODUCT_KEYS = {"product_id", "version", "source_ref", "source_sha256"}
BUYER_SCOPE_KEYS = {
    "scope_id",
    "authorized_finding_classes",
    "source_ref",
    "source_sha256",
}
FINDING_KEYS = {
    "finding_id",
    "finding_class",
    "summary",
    "contradicted",
    "evidence",
}
EVIDENCE_KEYS = {
    "evidence_id",
    "source_ref",
    "sha256",
    "observed_at",
    "valid_through",
    "sufficiency",
}
HOLD_KEYS = {"hold_id", "state", "blocking", "reason"}
CATALOG_KEYS = {
    "schema",
    "catalog_id",
    "source_generation",
    "source_ref",
    "source_sha256",
    "observed_at",
    "valid_through",
    "offers",
}
OFFER_KEYS = {
    "offer_id",
    "version",
    "source_ref",
    "source_sha256",
    "state",
    "commercial_state",
    "eligible_source_products",
    "match_mode",
    "applicable_finding_classes",
    "scope",
    "effort_band",
    "price",
    "priority",
}
SCOPE_KEYS = {"objective", "deliverables", "acceptance", "exclusions"}
EFFORT_KEYS = {"min_hours", "max_hours"}
PRICE_KEYS = {"currency", "amount_minor", "basis"}


class LadderError(ValueError):
    pass


def _strict_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise LadderError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def _reject_constant(token: str) -> None:
    raise LadderError(f"non-finite JSON number: {token}")


def _reject_float(token: str) -> None:
    raise LadderError(f"floating-point JSON number forbidden: {token}")


def loads_strict(text: str) -> Any:
    if type(text) is not str:
        raise LadderError("JSON input must be text")
    try:
        raw = text.encode("utf-8", "strict")
    except UnicodeError as exc:
        raise LadderError("invalid UTF-8 JSON text") from exc
    if len(raw) > MAX_BYTES:
        raise LadderError("JSON input exceeds size limit")
    if text.startswith("\ufeff"):
        raise LadderError("JSON BOM is forbidden")
    try:
        return json.loads(
            text,
            object_pairs_hook=_strict_pairs,
            parse_constant=_reject_constant,
            parse_float=_reject_float,
        )
    except LadderError:
        raise
    except (json.JSONDecodeError, UnicodeError, RecursionError) as exc:
        raise LadderError(f"invalid JSON: {exc}") from None


def canonical(value: Any) -> bytes:
    try:
        return (
            json.dumps(
                value,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
                allow_nan=False,
            )
            + "\n"
        ).encode("ascii")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise LadderError(f"value is not canonical JSON: {exc}") from None


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_value(value: Any) -> str:
    return sha256_bytes(canonical(value))


def _authority() -> dict[str, bool]:
    return {key: False for key in AUTHORITY_KEYS}


def _exact_keys(value: Any, expected: set[str], label: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise LadderError(f"{label}: expected object")
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise LadderError(f"{label}: keys mismatch missing={missing} extra={extra}")
    return value


def _text(value: Any, label: str, *, max_len: int = MAX_TEXT) -> str:
    if type(value) is not str or not value.strip():
        raise LadderError(f"{label}: expected non-empty text")
    if len(value) > max_len:
        raise LadderError(f"{label}: text too long")
    if any(ord(ch) < 32 for ch in value):
        raise LadderError(f"{label}: control characters forbidden")
    return value


def _bool(value: Any, label: str) -> bool:
    if type(value) is not bool:
        raise LadderError(f"{label}: expected boolean")
    return value


def _int(value: Any, label: str, *, minimum: int | None = None) -> int:
    if type(value) is not int:
        raise LadderError(f"{label}: expected integer")
    if minimum is not None and value < minimum:
        raise LadderError(f"{label}: expected >= {minimum}")
    return value


def _sha(value: Any, label: str) -> str:
    text = _text(value, label, max_len=64)
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise LadderError(f"{label}: expected lowercase sha256 hex")
    return text


def _time(value: Any, label: str) -> dt.datetime:
    text = _text(value, label, max_len=80)
    try:
        parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        raise LadderError(f"{label}: invalid ISO-8601 timestamp") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise LadderError(f"{label}: timezone required")
    return parsed.astimezone(dt.timezone.utc)


def _time_text(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _string_list(value: Any, label: str, *, min_items: int = 0, max_items: int = 100) -> list[str]:
    if type(value) is not list or not min_items <= len(value) <= max_items:
        raise LadderError(f"{label}: expected list length {min_items}..{max_items}")
    out: list[str] = []
    seen: set[str] = set()
    for idx, item in enumerate(value):
        text = _text(item, f"{label}[{idx}]", max_len=256)
        if text in seen:
            raise LadderError(f"{label}: duplicate value {text}")
        seen.add(text)
        out.append(text)
    return out


def _currency(value: Any, label: str) -> str:
    text = _text(value, label, max_len=3)
    if len(text) != 3 or not text.isascii() or not text.isalpha() or text.upper() != text:
        raise LadderError(f"{label}: expected uppercase three-letter currency")
    return text


def _validate_diagnostic(raw: Any, now: dt.datetime) -> dict[str, Any]:
    d = _exact_keys(raw, DIAGNOSTIC_KEYS, "diagnostic")
    if d["schema"] != DIAGNOSTIC_SCHEMA:
        raise LadderError("diagnostic.schema: unsupported")
    _text(d["diagnostic_id"], "diagnostic.diagnostic_id", max_len=128)
    product = _exact_keys(d["source_product"], SOURCE_PRODUCT_KEYS, "diagnostic.source_product")
    _text(product["product_id"], "diagnostic.source_product.product_id", max_len=128)
    _text(product["version"], "diagnostic.source_product.version", max_len=128)
    _text(product["source_ref"], "diagnostic.source_product.source_ref")
    _sha(product["source_sha256"], "diagnostic.source_product.source_sha256")
    completed_at = _time(d["completed_at"], "diagnostic.completed_at")
    if completed_at > now:
        raise LadderError("diagnostic.completed_at: future completion")

    scope = _exact_keys(d["buyer_scope"], BUYER_SCOPE_KEYS, "diagnostic.buyer_scope")
    _text(scope["scope_id"], "diagnostic.buyer_scope.scope_id", max_len=128)
    authorized = _string_list(
        scope["authorized_finding_classes"],
        "diagnostic.buyer_scope.authorized_finding_classes",
        min_items=1,
        max_items=100,
    )
    _text(scope["source_ref"], "diagnostic.buyer_scope.source_ref")
    _sha(scope["source_sha256"], "diagnostic.buyer_scope.source_sha256")
    authorized_set = set(authorized)

    findings = d["findings"]
    if type(findings) is not list or not 1 <= len(findings) <= MAX_FINDINGS:
        raise LadderError("diagnostic.findings: expected non-empty bounded list")
    finding_ids: set[str] = set()
    evidence_ids: set[str] = set()
    for fidx, row in enumerate(findings):
        f = _exact_keys(row, FINDING_KEYS, f"diagnostic.findings[{fidx}]")
        fid = _text(f["finding_id"], f"diagnostic.findings[{fidx}].finding_id", max_len=128)
        if fid in finding_ids:
            raise LadderError(f"diagnostic.findings: duplicate finding_id {fid}")
        finding_ids.add(fid)
        fclass = _text(f["finding_class"], f"diagnostic.findings[{fidx}].finding_class", max_len=128)
        if fclass not in authorized_set:
            raise LadderError(f"diagnostic.findings[{fidx}]: finding_class outside buyer-authorized scope")
        _text(f["summary"], f"diagnostic.findings[{fidx}].summary")
        _bool(f["contradicted"], f"diagnostic.findings[{fidx}].contradicted")
        evidence = f["evidence"]
        if type(evidence) is not list or not 1 <= len(evidence) <= MAX_EVIDENCE:
            raise LadderError(f"diagnostic.findings[{fidx}].evidence: expected non-empty bounded list")
        for eidx, erow in enumerate(evidence):
            e = _exact_keys(erow, EVIDENCE_KEYS, f"diagnostic.findings[{fidx}].evidence[{eidx}]")
            eid = _text(e["evidence_id"], f"diagnostic.findings[{fidx}].evidence[{eidx}].evidence_id", max_len=128)
            if eid in evidence_ids:
                raise LadderError(f"diagnostic evidence: duplicate evidence_id {eid}")
            evidence_ids.add(eid)
            _text(e["source_ref"], f"diagnostic.findings[{fidx}].evidence[{eidx}].source_ref")
            _sha(e["sha256"], f"diagnostic.findings[{fidx}].evidence[{eidx}].sha256")
            observed = _time(e["observed_at"], f"diagnostic.findings[{fidx}].evidence[{eidx}].observed_at")
            valid = _time(e["valid_through"], f"diagnostic.findings[{fidx}].evidence[{eidx}].valid_through")
            if observed > now:
                raise LadderError(f"diagnostic.findings[{fidx}].evidence[{eidx}]: future evidence")
            if valid < observed:
                raise LadderError(f"diagnostic.findings[{fidx}].evidence[{eidx}]: validity precedes observation")
            if e["sufficiency"] not in {"VERIFIED", "PARTIAL", "UNKNOWN"}:
                raise LadderError(f"diagnostic.findings[{fidx}].evidence[{eidx}].sufficiency: unsupported")

    holds = d["holds"]
    if type(holds) is not list or len(holds) > 100:
        raise LadderError("diagnostic.holds: expected bounded list")
    hold_ids: set[str] = set()
    for idx, row in enumerate(holds):
        h = _exact_keys(row, HOLD_KEYS, f"diagnostic.holds[{idx}]")
        hid = _text(h["hold_id"], f"diagnostic.holds[{idx}].hold_id", max_len=128)
        if hid in hold_ids:
            raise LadderError(f"diagnostic.holds: duplicate hold_id {hid}")
        hold_ids.add(hid)
        if h["state"] not in {"OPEN", "RESOLVED"}:
            raise LadderError(f"diagnostic.holds[{idx}].state: unsupported")
        _bool(h["blocking"], f"diagnostic.holds[{idx}].blocking")
        _text(h["reason"], f"diagnostic.holds[{idx}].reason")
    return d


def _validate_catalog(raw: Any, now: dt.datetime) -> dict[str, Any]:
    c = _exact_keys(raw, CATALOG_KEYS, "catalog")
    if c["schema"] != CATALOG_SCHEMA:
        raise LadderError("catalog.schema: unsupported")
    _text(c["catalog_id"], "catalog.catalog_id", max_len=128)
    _text(c["source_generation"], "catalog.source_generation", max_len=128)
    _text(c["source_ref"], "catalog.source_ref")
    _sha(c["source_sha256"], "catalog.source_sha256")
    observed = _time(c["observed_at"], "catalog.observed_at")
    valid = _time(c["valid_through"], "catalog.valid_through")
    if observed > now:
        raise LadderError("catalog.observed_at: future catalog")
    if valid < observed:
        raise LadderError("catalog.valid_through: precedes observation")
    offers = c["offers"]
    if type(offers) is not list or not 1 <= len(offers) <= MAX_OFFERS:
        raise LadderError("catalog.offers: expected non-empty bounded list")
    offer_ids: set[str] = set()
    for idx, row in enumerate(offers):
        o = _exact_keys(row, OFFER_KEYS, f"catalog.offers[{idx}]")
        oid = _text(o["offer_id"], f"catalog.offers[{idx}].offer_id", max_len=128)
        if oid in offer_ids:
            raise LadderError(f"catalog.offers: duplicate offer_id {oid}")
        offer_ids.add(oid)
        _text(o["version"], f"catalog.offers[{idx}].version", max_len=128)
        _text(o["source_ref"], f"catalog.offers[{idx}].source_ref")
        _sha(o["source_sha256"], f"catalog.offers[{idx}].source_sha256")
        if o["state"] not in {"CURRENT", "WITHDRAWN", "HOLD"}:
            raise LadderError(f"catalog.offers[{idx}].state: unsupported")
        if o["commercial_state"] != COMMERCIAL_STATE:
            raise LadderError(f"catalog.offers[{idx}].commercial_state: must be {COMMERCIAL_STATE}")
        _string_list(o["eligible_source_products"], f"catalog.offers[{idx}].eligible_source_products", min_items=1, max_items=50)
        if o["match_mode"] not in {"ANY", "ALL"}:
            raise LadderError(f"catalog.offers[{idx}].match_mode: unsupported")
        _string_list(o["applicable_finding_classes"], f"catalog.offers[{idx}].applicable_finding_classes", min_items=1, max_items=100)
        scope = _exact_keys(o["scope"], SCOPE_KEYS, f"catalog.offers[{idx}].scope")
        _text(scope["objective"], f"catalog.offers[{idx}].scope.objective")
        _string_list(scope["deliverables"], f"catalog.offers[{idx}].scope.deliverables", min_items=1, max_items=50)
        _string_list(scope["acceptance"], f"catalog.offers[{idx}].scope.acceptance", min_items=1, max_items=50)
        _string_list(scope["exclusions"], f"catalog.offers[{idx}].scope.exclusions", min_items=1, max_items=50)
        effort = _exact_keys(o["effort_band"], EFFORT_KEYS, f"catalog.offers[{idx}].effort_band")
        lo = _int(effort["min_hours"], f"catalog.offers[{idx}].effort_band.min_hours", minimum=1)
        hi = _int(effort["max_hours"], f"catalog.offers[{idx}].effort_band.max_hours", minimum=1)
        if hi < lo:
            raise LadderError(f"catalog.offers[{idx}].effort_band: max_hours < min_hours")
        price = _exact_keys(o["price"], PRICE_KEYS, f"catalog.offers[{idx}].price")
        _currency(price["currency"], f"catalog.offers[{idx}].price.currency")
        _int(price["amount_minor"], f"catalog.offers[{idx}].price.amount_minor", minimum=0)
        _text(price["basis"], f"catalog.offers[{idx}].price.basis", max_len=256)
        _int(o["priority"], f"catalog.offers[{idx}].priority", minimum=0)
    return c


def _finding_snapshot(diagnostic: dict[str, Any], now: dt.datetime) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    usable: list[dict[str, Any]] = []
    evidence_holds: list[str] = []
    contradictions: list[str] = []
    for finding in diagnostic["findings"]:
        if finding["contradicted"]:
            contradictions.append(finding["finding_id"])
            continue
        refs: list[dict[str, str]] = []
        fully_verified = True
        for ev in finding["evidence"]:
            valid = _time(ev["valid_through"], "evidence.valid_through")
            if ev["sufficiency"] != "VERIFIED" or valid < now:
                fully_verified = False
                evidence_holds.append(ev["evidence_id"])
            refs.append(
                {
                    "evidence_id": ev["evidence_id"],
                    "source_ref": ev["source_ref"],
                    "sha256": ev["sha256"],
                    "valid_through": ev["valid_through"],
                }
            )
        if fully_verified:
            usable.append(
                {
                    "finding_id": finding["finding_id"],
                    "finding_class": finding["finding_class"],
                    "summary": finding["summary"],
                    "evidence": refs,
                }
            )
    return usable, sorted(set(evidence_holds)), sorted(contradictions)


def _matches(offer: dict[str, Any], source_product_id: str, finding_classes: set[str]) -> bool:
    if offer["state"] != "CURRENT":
        return False
    if source_product_id not in offer["eligible_source_products"]:
        return False
    required = set(offer["applicable_finding_classes"])
    if offer["match_mode"] == "ALL":
        return required.issubset(finding_classes)
    return bool(required & finding_classes)


def _candidate(offer: dict[str, Any], findings: list[dict[str, Any]]) -> dict[str, Any]:
    allowed = set(offer["applicable_finding_classes"])
    matched = [row for row in findings if row["finding_class"] in allowed]
    evidence_refs = []
    for row in matched:
        for ev in row["evidence"]:
            evidence_refs.append(
                {
                    "finding_id": row["finding_id"],
                    "evidence_id": ev["evidence_id"],
                    "source_ref": ev["source_ref"],
                    "sha256": ev["sha256"],
                    "valid_through": ev["valid_through"],
                }
            )
    evidence_refs.sort(key=lambda row: (row["finding_id"], row["evidence_id"]))
    return {
        "offer_id": offer["offer_id"],
        "offer_version": offer["version"],
        "offer_source_ref": offer["source_ref"],
        "offer_source_sha256": offer["source_sha256"],
        "commercial_state": COMMERCIAL_STATE,
        "matched_finding_ids": sorted(row["finding_id"] for row in matched),
        "matched_finding_classes": sorted({row["finding_class"] for row in matched}),
        "evidence_refs": evidence_refs,
        "scope": copy.deepcopy(offer["scope"]),
        "effort_band": copy.deepcopy(offer["effort_band"]),
        "price": copy.deepcopy(offer["price"]),
        "priority": offer["priority"],
        "selection_authority": "OWNER_REVIEW_ONLY",
    }


def compile_ladder(
    diagnostic_raw: Any,
    catalog_raw: Any,
    *,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    now = (now or dt.datetime.now(dt.timezone.utc)).astimezone(dt.timezone.utc)
    diagnostic = _validate_diagnostic(copy.deepcopy(diagnostic_raw), now)
    catalog = _validate_catalog(copy.deepcopy(catalog_raw), now)

    reasons: list[str] = []
    candidates: list[dict[str, Any]] = []
    usable, weak_evidence, contradictions = _finding_snapshot(diagnostic, now)
    open_blockers = sorted(
        hold["hold_id"]
        for hold in diagnostic["holds"]
        if hold["blocking"] and hold["state"] != "RESOLVED"
    )

    catalog_expired = _time(catalog["valid_through"], "catalog.valid_through") < now
    catalog_predates_completion = (
        _time(catalog["observed_at"], "catalog.observed_at")
        < _time(diagnostic["completed_at"], "diagnostic.completed_at")
    )

    if contradictions:
        status = "HOLD_SCOPE_CONTRADICTION"
        reasons.append("CONTRADICTED_DELIVERED_FINDING")
    elif open_blockers:
        status = "HOLD_UNRESOLVED_BLOCKER"
        reasons.append("UNRESOLVED_BLOCKING_DIAGNOSTIC_HOLD")
    elif weak_evidence or not usable:
        status = "HOLD_EVIDENCE_INSUFFICIENT"
        reasons.append("DELIVERED_FINDING_EVIDENCE_NOT_CURRENT_AND_VERIFIED")
    elif catalog_expired:
        status = "HOLD_CATALOG_INVALID"
        reasons.append("OFFER_CATALOG_EXPIRED")
    elif catalog_predates_completion:
        status = "HOLD_SOURCE_DRIFT"
        reasons.append("CATALOG_GENERATION_PREDATES_DIAGNOSTIC_COMPLETION")
    else:
        finding_classes = {row["finding_class"] for row in usable}
        source_product_id = diagnostic["source_product"]["product_id"]
        for offer in catalog["offers"]:
            if _matches(offer, source_product_id, finding_classes):
                candidates.append(_candidate(offer, usable))
        candidates.sort(key=lambda row: (-row["priority"], row["offer_id"], row["offer_version"]))
        if candidates:
            status = "OWNER_REVIEW_UPSELL_CANDIDATE"
            reasons.append("CURRENT_OFFER_MATCHES_VERIFIED_DELIVERED_FINDING")
        else:
            status = "NO_NEXT_STEP"
            reasons.append("NO_CURRENT_OFFER_MATCHES_VERIFIED_DELIVERED_FINDING")

    if status != "OWNER_REVIEW_UPSELL_CANDIDATE":
        candidates = []

    packet: dict[str, Any] = {
        "schema": PACKET_SCHEMA,
        "status": status,
        "reasons": reasons,
        "evaluated_at": _time_text(now),
        "diagnostic_id": diagnostic["diagnostic_id"],
        "diagnostic_source": {
            "product_id": diagnostic["source_product"]["product_id"],
            "version": diagnostic["source_product"]["version"],
            "source_ref": diagnostic["source_product"]["source_ref"],
            "source_sha256": diagnostic["source_product"]["source_sha256"],
            "diagnostic_input_sha256": sha256_value(diagnostic),
        },
        "buyer_scope": {
            "scope_id": diagnostic["buyer_scope"]["scope_id"],
            "source_ref": diagnostic["buyer_scope"]["source_ref"],
            "source_sha256": diagnostic["buyer_scope"]["source_sha256"],
            "authorized_finding_classes": sorted(diagnostic["buyer_scope"]["authorized_finding_classes"]),
        },
        "catalog_source": {
            "catalog_id": catalog["catalog_id"],
            "source_generation": catalog["source_generation"],
            "source_ref": catalog["source_ref"],
            "source_sha256": catalog["source_sha256"],
            "catalog_input_sha256": sha256_value(catalog),
            "valid_through": catalog["valid_through"],
        },
        "evidence_summary": {
            "usable_finding_ids": sorted(row["finding_id"] for row in usable),
            "weak_or_stale_evidence_ids": weak_evidence,
            "contradicted_finding_ids": contradictions,
            "open_blocking_hold_ids": open_blockers,
        },
        "candidates": candidates,
        "source_authentication": "RETAINED_DIGEST_REFERENCE_NOT_PROVIDER_AUTHENTICATED",
        "authority": _authority(),
    }
    if packet["status"] not in STATUSES:
        raise LadderError("internal status error")
    packet["receipt_sha256"] = sha256_value(packet)
    return packet


def verify_ladder(
    diagnostic_raw: Any,
    catalog_raw: Any,
    packet_raw: Any,
    *,
    now: dt.datetime | None = None,
) -> bool:
    if type(packet_raw) is not dict:
        raise LadderError("packet: expected object")
    packet = copy.deepcopy(packet_raw)
    receipt = packet.pop("receipt_sha256", None)
    if type(receipt) is not str or receipt != sha256_value(packet):
        raise LadderError("packet receipt mismatch")
    evaluated = _time(packet.get("evaluated_at"), "packet.evaluated_at")
    expected = compile_ladder(diagnostic_raw, catalog_raw, now=evaluated)
    if canonical(expected) != canonical(packet_raw):
        raise LadderError("packet semantic mismatch")

    runtime_now = (now or dt.datetime.now(dt.timezone.utc)).astimezone(dt.timezone.utc)
    if runtime_now < evaluated:
        raise LadderError("verification clock predates packet evaluation")
    if packet_raw.get("status") == "OWNER_REVIEW_UPSELL_CANDIDATE":
        current = compile_ladder(diagnostic_raw, catalog_raw, now=runtime_now)
        if current["status"] != "OWNER_REVIEW_UPSELL_CANDIDATE":
            raise LadderError(f"candidate no longer current: {current['status']}")
        if canonical(current["candidates"]) != canonical(packet_raw["candidates"]):
            raise LadderError("candidate set changed under current evidence/catalog")
    return True


def render_markdown(packet: dict[str, Any]) -> str:
    if type(packet) is not dict or packet.get("schema") != PACKET_SCHEMA:
        raise LadderError("invalid packet for markdown")
    lines = [
        f"# Diagnostic follow-on ladder — `{packet['diagnostic_id']}`",
        "",
        f"Status: **`{packet['status']}`**",
        "",
        "This is owner-review commercial decision support. It is not a buyer message, accepted scope, invoice, payment request, savings claim, cash receipt, or revenue recognition.",
        "",
    ]
    if packet["candidates"]:
        lines += ["## Owner-review candidates", ""]
        for idx, candidate in enumerate(packet["candidates"], 1):
            price = candidate["price"]
            lines += [
                f"### {idx}. `{candidate['offer_id']}` / `{candidate['offer_version']}`",
                "",
                f"Commercial state: `{candidate['commercial_state']}`",
                f"Matched findings: {', '.join('`'+x+'`' for x in candidate['matched_finding_ids'])}",
                f"Objective: {candidate['scope']['objective']}",
                f"Effort: {candidate['effort_band']['min_hours']}–{candidate['effort_band']['max_hours']} hours",
                f"Catalog price: `{price['currency']} {price['amount_minor']} minor units` ({price['basis']})",
                f"Offer source: `{candidate['offer_source_ref']}` / `{candidate['offer_source_sha256']}`",
                "",
                "Deliverables:",
            ]
            lines += [f"- {item}" for item in candidate["scope"]["deliverables"]]
            lines += ["", "Acceptance criteria:"]
            lines += [f"- {item}" for item in candidate["scope"]["acceptance"]]
            lines += ["", "Exclusions:"]
            lines += [f"- {item}" for item in candidate["scope"]["exclusions"]]
            lines.append("")
    else:
        lines += ["## Reasons", ""] + [f"- `{reason}`" for reason in packet["reasons"]] + [""]
    lines += [
        "## Authority ceiling",
        "",
        "All outbound, buyer acceptance, contract/change acceptance, invoice, payment, provider mutation, customer-result, savings, accounting, cash, and revenue authority flags are false.",
        "",
        f"Receipt SHA-256: `{packet['receipt_sha256']}`",
        "",
    ]
    return "\n".join(lines)


def _read_regular(path: Path) -> bytes:
    st = path.lstat()
    if not stat.S_ISREG(st.st_mode) or st.st_size > MAX_BYTES:
        raise LadderError(f"{path}: input must be a bounded regular file")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        fst = os.fstat(fd)
        if (fst.st_dev, fst.st_ino) != (st.st_dev, st.st_ino):
            raise LadderError(f"{path}: input changed while opening")
        chunks: list[bytes] = []
        total = 0
        while True:
            part = os.read(fd, min(65536, MAX_BYTES + 1 - total))
            if not part:
                break
            chunks.append(part)
            total += len(part)
            if total > MAX_BYTES:
                raise LadderError(f"{path}: input exceeds size limit")
        return b"".join(chunks)
    finally:
        os.close(fd)


def _read_json(path: Path) -> Any:
    try:
        return loads_strict(_read_regular(path).decode("utf-8", "strict"))
    except UnicodeError as exc:
        raise LadderError(f"{path}: invalid UTF-8") from exc


def _write_exclusive(path: Path, data: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    try:
        view = memoryview(data)
        while view:
            count = os.write(fd, view)
            if count <= 0:
                raise LadderError(f"{path}: short write")
            view = view[count:]
        os.fsync(fd)
    finally:
        os.close(fd)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compile/verify an evidence-bound diagnostic follow-on ladder")
    sub = parser.add_subparsers(dest="command", required=True)
    compile_p = sub.add_parser("compile")
    compile_p.add_argument("--diagnostic", required=True)
    compile_p.add_argument("--catalog", required=True)
    compile_p.add_argument("--out", required=True)
    compile_p.add_argument("--markdown")
    verify_p = sub.add_parser("verify")
    verify_p.add_argument("--diagnostic", required=True)
    verify_p.add_argument("--catalog", required=True)
    verify_p.add_argument("--packet", required=True)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = _parser().parse_args(list(argv) if argv is not None else None)
    try:
        diagnostic = _read_json(Path(args.diagnostic))
        catalog = _read_json(Path(args.catalog))
        if args.command == "compile":
            packet = compile_ladder(diagnostic, catalog)
            _write_exclusive(Path(args.out), canonical(packet))
            if args.markdown:
                _write_exclusive(Path(args.markdown), render_markdown(packet).encode("utf-8"))
            print(packet["status"])
            return 0
        packet = _read_json(Path(args.packet))
        verify_ladder(diagnostic, catalog, packet)
        print("VERIFIED")
        return 0
    except (LadderError, OSError, UnicodeError, TypeError, ValueError, RecursionError) as exc:
        print(f"DIAGNOSTIC_UPSELL_LADDER_ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
