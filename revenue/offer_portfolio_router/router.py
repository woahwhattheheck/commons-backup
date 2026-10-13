#!/usr/bin/env python3
"""Deterministic portfolio allocator for one-organization/one-paid-offer targeting.

This module is deliberately upstream of every external side effect.  It consumes
normalized commercial evidence and produces an internal target/offer queue.  It
never authorizes a send, contact, lease, payment, acceptance, or revenue claim.
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
import os
import re
import stat
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

INPUT_SCHEMA = "commons-offer-portfolio-router-input/v1"
OUTPUT_SCHEMA = "commons-offer-portfolio-router-output/v1"
POLICY_VERSION = "commons-offer-portfolio-router-policy/1"

RELATIONSHIP_STATES = {
    "UNCONTACTED",
    "ACTIVE_OUTREACH",
    "WAITING_REPLY",
    "HOT_REQUIRES_OWNER",
    "HUMAN_REPLY",
    "HARD_DNR",
    "CLOSED",
    "PROVIDER_EVENT_ONLY",
}
ROUTE_STATES = {"LIVE", "DEAD", "UNKNOWN"}
BUYING_SIGNALS = {
    "ACTIVE_PROCUREMENT": 80,
    "PUBLISHED_NEED": 60,
    "PUBLIC_PAIN": 40,
    "RESEARCH_ONLY": 10,
}
PAYMENT_PATH_STATES = {"READY", "NOT_READY", "UNKNOWN"}
FAMILIES = {"PRODUCT", "SERVICE", "EXPERTISE", "DATA"}
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,95}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
TAG = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
UTC_SECONDS = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


class RouterError(ValueError):
    pass


def _pairs_no_dupes(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise RouterError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def load_json_strict_bytes(raw: bytes) -> Any:
    if len(raw) > 2_000_000:
        raise RouterError("input exceeds 2,000,000 bytes")
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise RouterError("input must be UTF-8") from exc
    try:
        return json.loads(
            text,
            object_pairs_hook=_pairs_no_dupes,
            parse_constant=lambda token: (_ for _ in ()).throw(
                RouterError(f"non-finite JSON number: {token}")
            ),
        )
    except json.JSONDecodeError as exc:
        raise RouterError(f"invalid JSON: {exc.msg}") from exc


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _expect_exact_keys(obj: dict[str, Any], keys: Iterable[str], where: str) -> None:
    expected = set(keys)
    actual = set(obj)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise RouterError(f"{where} keys mismatch; missing={missing} extra={extra}")


def _dict(value: Any, where: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise RouterError(f"{where} must be an object")
    return value


def _list(value: Any, where: str, *, max_items: int = 500) -> list[Any]:
    if type(value) is not list:
        raise RouterError(f"{where} must be an array")
    if len(value) > max_items:
        raise RouterError(f"{where} exceeds {max_items} items")
    return value


def _bool(value: Any, where: str) -> bool:
    if type(value) is not bool:
        raise RouterError(f"{where} must be a boolean")
    return value


def _int(value: Any, where: str, low: int, high: int) -> int:
    if type(value) is not int:
        raise RouterError(f"{where} must be an integer")
    if value < low or value > high:
        raise RouterError(f"{where} must be between {low} and {high}")
    return value


def _id(value: Any, where: str) -> str:
    if type(value) is not str or not SAFE_ID.fullmatch(value):
        raise RouterError(f"{where} must be a safe identifier")
    return value


def _sha(value: Any, where: str) -> str:
    if type(value) is not str or not SHA256.fullmatch(value):
        raise RouterError(f"{where} must be a lowercase sha256")
    return value


def _enum(value: Any, allowed: set[str] | dict[str, int], where: str) -> str:
    if type(value) is not str or value not in allowed:
        raise RouterError(f"{where} must be one of {sorted(allowed)}")
    return value


def _tag_list(value: Any, where: str) -> list[str]:
    items = _list(value, where, max_items=32)
    out: list[str] = []
    seen: set[str] = set()
    for i, item in enumerate(items):
        if type(item) is not str or not TAG.fullmatch(item):
            raise RouterError(f"{where}[{i}] must be a normalized tag")
        if item in seen:
            raise RouterError(f"duplicate tag {item} in {where}")
        seen.add(item)
        out.append(item)
    return out


def _safe_label(value: Any, where: str, max_len: int = 160) -> str:
    if type(value) is not str or not (1 <= len(value) <= max_len):
        raise RouterError(f"{where} must be 1..{max_len} characters")
    lowered = value.lower()
    if any(ch in value for ch in ("\r", "\n", "\x00")):
        raise RouterError(f"{where} contains control characters")
    if "@" in value or "http://" in lowered or "https://" in lowered or "mailto:" in lowered:
        raise RouterError(f"{where} may not contain addresses or URLs")
    return value


def _utc(value: Any, where: str) -> dt.datetime:
    if type(value) is not str or not UTC_SECONDS.fullmatch(value):
        raise RouterError(f"{where} must be UTC seconds like 2026-09-14T03:00:00Z")
    try:
        parsed = dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
    except ValueError as exc:
        raise RouterError(f"{where} is not a valid UTC timestamp") from exc
    return parsed


def _utc_string(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _age_hours(observed: dt.datetime, as_of: dt.datetime) -> int:
    delta = as_of - observed
    if delta.total_seconds() < 0:
        return -1
    return int(delta.total_seconds() // 3600)


def validate_input(packet: Any, *, as_of: dt.datetime) -> dict[str, Any]:
    root = _dict(packet, "root")
    _expect_exact_keys(root, {"schema", "campaign", "policy", "organizations", "offers"}, "root")
    if root["schema"] != INPUT_SCHEMA:
        raise RouterError(f"unsupported schema: {root['schema']!r}")

    campaign = _dict(root["campaign"], "campaign")
    _expect_exact_keys(campaign, {"campaign_id", "campaign_generation_sha256", "max_selected_total"}, "campaign")
    _id(campaign["campaign_id"], "campaign.campaign_id")
    _sha(campaign["campaign_generation_sha256"], "campaign.campaign_generation_sha256")
    _int(campaign["max_selected_total"], "campaign.max_selected_total", 1, 100)

    policy = _dict(root["policy"], "policy")
    _expect_exact_keys(policy, {"max_source_age_hours", "max_per_family", "max_per_offer"}, "policy")
    _int(policy["max_source_age_hours"], "policy.max_source_age_hours", 1, 24 * 365)
    mpf = _dict(policy["max_per_family"], "policy.max_per_family")
    if not mpf or set(mpf) - FAMILIES:
        raise RouterError("policy.max_per_family contains unsupported families")
    for family, limit in mpf.items():
        _int(limit, f"policy.max_per_family.{family}", 0, 100)
    mpo = _dict(policy["max_per_offer"], "policy.max_per_offer")
    for offer_id, limit in mpo.items():
        _id(offer_id, "policy.max_per_offer key")
        _int(limit, f"policy.max_per_offer.{offer_id}", 0, 100)

    orgs = _list(root["organizations"], "organizations", max_items=500)
    offers = _list(root["offers"], "offers", max_items=200)
    if not orgs:
        raise RouterError("organizations must not be empty")
    if not offers:
        raise RouterError("offers must not be empty")

    org_ids: set[str] = set()
    buyer_scopes: set[str] = set()
    for i, raw_org in enumerate(orgs):
        where = f"organizations[{i}]"
        org = _dict(raw_org, where)
        _expect_exact_keys(
            org,
            {
                "org_id",
                "buyer_scope",
                "relationship_state",
                "relationship_generation_sha256",
                "relationship_observed_at",
                "route_state",
                "route_evidence_sha256",
                "named_decision_authority",
                "decision_authority_evidence_sha256",
                "buying_signal",
                "pain_tags",
                "pain_evidence_sha256",
            },
            where,
        )
        org_id = _id(org["org_id"], f"{where}.org_id")
        buyer_scope = _id(org["buyer_scope"], f"{where}.buyer_scope")
        if org_id in org_ids:
            raise RouterError(f"duplicate org_id: {org_id}")
        if buyer_scope in buyer_scopes:
            raise RouterError(f"duplicate buyer_scope: {buyer_scope}")
        org_ids.add(org_id)
        buyer_scopes.add(buyer_scope)
        _enum(org["relationship_state"], RELATIONSHIP_STATES, f"{where}.relationship_state")
        _sha(org["relationship_generation_sha256"], f"{where}.relationship_generation_sha256")
        observed = _utc(org["relationship_observed_at"], f"{where}.relationship_observed_at")
        if observed > as_of:
            raise RouterError(f"{where}.relationship_observed_at is in the future")
        _enum(org["route_state"], ROUTE_STATES, f"{where}.route_state")
        _sha(org["route_evidence_sha256"], f"{where}.route_evidence_sha256")
        _bool(org["named_decision_authority"], f"{where}.named_decision_authority")
        _sha(org["decision_authority_evidence_sha256"], f"{where}.decision_authority_evidence_sha256")
        _enum(org["buying_signal"], BUYING_SIGNALS, f"{where}.buying_signal")
        tags = _tag_list(org["pain_tags"], f"{where}.pain_tags")
        if not tags:
            raise RouterError(f"{where}.pain_tags must not be empty")
        _sha(org["pain_evidence_sha256"], f"{where}.pain_evidence_sha256")

    offer_ids: set[str] = set()
    for i, raw_offer in enumerate(offers):
        where = f"offers[{i}]"
        offer = _dict(raw_offer, where)
        _expect_exact_keys(
            offer,
            {
                "offer_id",
                "offer_generation_sha256",
                "family",
                "price_minor",
                "currency",
                "paid_scope_label",
                "scope_sha256",
                "acceptance_criteria_sha256",
                "fit_tags",
                "proof_ready",
                "proof_evidence_sha256",
                "fulfillment_ready",
                "fulfillment_evidence_sha256",
                "payment_path_state",
                "payment_path_evidence_sha256",
            },
            where,
        )
        offer_id = _id(offer["offer_id"], f"{where}.offer_id")
        if offer_id in offer_ids:
            raise RouterError(f"duplicate offer_id: {offer_id}")
        offer_ids.add(offer_id)
        _sha(offer["offer_generation_sha256"], f"{where}.offer_generation_sha256")
        _enum(offer["family"], FAMILIES, f"{where}.family")
        _int(offer["price_minor"], f"{where}.price_minor", 1, 1_000_000_000)
        if offer["currency"] != "USD":
            raise RouterError(f"{where}.currency: v1 supports USD only")
        _safe_label(offer["paid_scope_label"], f"{where}.paid_scope_label")
        _sha(offer["scope_sha256"], f"{where}.scope_sha256")
        _sha(offer["acceptance_criteria_sha256"], f"{where}.acceptance_criteria_sha256")
        tags = _tag_list(offer["fit_tags"], f"{where}.fit_tags")
        if not tags:
            raise RouterError(f"{where}.fit_tags must not be empty")
        _bool(offer["proof_ready"], f"{where}.proof_ready")
        _sha(offer["proof_evidence_sha256"], f"{where}.proof_evidence_sha256")
        _bool(offer["fulfillment_ready"], f"{where}.fulfillment_ready")
        _sha(offer["fulfillment_evidence_sha256"], f"{where}.fulfillment_evidence_sha256")
        _enum(offer["payment_path_state"], PAYMENT_PATH_STATES, f"{where}.payment_path_state")
        _sha(offer["payment_path_evidence_sha256"], f"{where}.payment_path_evidence_sha256")

    unknown_caps = set(mpo) - offer_ids
    if unknown_caps:
        raise RouterError(f"policy.max_per_offer references unknown offers: {sorted(unknown_caps)}")
    return copy.deepcopy(root)


def _candidate_base_reasons(org: dict[str, Any], offer: dict[str, Any], *, age_hours: int, max_age: int) -> list[str]:
    reasons: list[str] = []
    if age_hours > max_age:
        reasons.append("SOURCE_REFRESH_REQUIRED")
    if org["relationship_state"] != "UNCONTACTED":
        reasons.append(f"RELATIONSHIP_{org['relationship_state']}")
    if org["route_state"] != "LIVE":
        reasons.append(f"ROUTE_{org['route_state']}")
    if not org["named_decision_authority"]:
        reasons.append("DECISION_AUTHORITY_UNPROVEN")
    overlap = sorted(set(org["pain_tags"]) & set(offer["fit_tags"]))
    if not overlap:
        reasons.append("NO_EVIDENCED_FIT")
    if not offer["proof_ready"]:
        reasons.append("PROOF_NOT_READY")
    if not offer["fulfillment_ready"]:
        reasons.append("FULFILLMENT_NOT_READY")
    if offer["payment_path_state"] != "READY":
        reasons.append(f"PAYMENT_PATH_{offer['payment_path_state']}")
    return reasons


def _rank_key(candidate: dict[str, Any]) -> tuple[Any, ...]:
    # Preserve scarce portfolio options first, then let evidence/fit dominate.
    # Price is intentionally only a late tiebreaker.
    return (
        candidate["org_eligible_option_count"],
        candidate["offer_eligible_org_count"],
        -candidate["fit_tag_count"],
        -candidate["buying_signal_points"],
        -candidate["fit_coverage_bp"],
        -candidate["price_minor"],
        candidate["org_id"],
        candidate["offer_id"],
    )


def compile_portfolio(packet: Any, *, as_of: dt.datetime) -> dict[str, Any]:
    if as_of.tzinfo is None or as_of.utcoffset() != dt.timedelta(0):
        raise RouterError("as_of must be timezone-aware UTC")
    if as_of.microsecond:
        raise RouterError("as_of must be whole seconds")
    data = validate_input(packet, as_of=as_of)
    # The portfolio is a set keyed by immutable IDs, not an ordered caller list.
    # Normalize those semantic sets before both receipt custody and evaluation.
    data["organizations"] = sorted(data["organizations"], key=lambda x: x["org_id"])
    data["offers"] = sorted(data["offers"], key=lambda x: x["offer_id"])
    input_digest = sha256_bytes(canonical_bytes(data))
    policy = data["policy"]
    max_age = policy["max_source_age_hours"]
    offer_caps = policy["max_per_offer"]
    family_caps = policy["max_per_family"]
    campaign_cap = data["campaign"]["max_selected_total"]

    candidates: list[dict[str, Any]] = []
    for org in sorted(data["organizations"], key=lambda x: x["org_id"]):
        age = _age_hours(_utc(org["relationship_observed_at"], "relationship_observed_at"), as_of)
        for offer in sorted(data["offers"], key=lambda x: x["offer_id"]):
            overlap = sorted(set(org["pain_tags"]) & set(offer["fit_tags"]))
            coverage_bp = (len(overlap) * 10_000) // len(offer["fit_tags"])
            base_reasons = _candidate_base_reasons(org, offer, age_hours=age, max_age=max_age)
            candidates.append(
                {
                    "org_id": org["org_id"],
                    "buyer_scope": org["buyer_scope"],
                    "offer_id": offer["offer_id"],
                    "family": offer["family"],
                    "price_minor": offer["price_minor"],
                    "currency": offer["currency"],
                    "paid_scope_label": offer["paid_scope_label"],
                    "fit_tags": overlap,
                    "fit_tag_count": len(overlap),
                    "fit_coverage_bp": coverage_bp,
                    "buying_signal": org["buying_signal"],
                    "buying_signal_points": BUYING_SIGNALS[org["buying_signal"]],
                    "relationship_state": org["relationship_state"],
                    "route_state": org["route_state"],
                    "source_age_hours": age,
                    "org_evidence": {
                        "relationship_generation_sha256": org["relationship_generation_sha256"],
                        "route_evidence_sha256": org["route_evidence_sha256"],
                        "decision_authority_evidence_sha256": org["decision_authority_evidence_sha256"],
                        "pain_evidence_sha256": org["pain_evidence_sha256"],
                    },
                    "offer_evidence": {
                        "offer_generation_sha256": offer["offer_generation_sha256"],
                        "scope_sha256": offer["scope_sha256"],
                        "acceptance_criteria_sha256": offer["acceptance_criteria_sha256"],
                        "proof_evidence_sha256": offer["proof_evidence_sha256"],
                        "fulfillment_evidence_sha256": offer["fulfillment_evidence_sha256"],
                        "payment_path_evidence_sha256": offer["payment_path_evidence_sha256"],
                    },
                    "base_reasons": base_reasons,
                }
            )

    eligible = [c for c in candidates if not c["base_reasons"]]
    org_option_counts = Counter(c["org_id"] for c in eligible)
    offer_org_counts = Counter(c["offer_id"] for c in eligible)
    for candidate in candidates:
        candidate["org_eligible_option_count"] = org_option_counts[candidate["org_id"]]
        candidate["offer_eligible_org_count"] = offer_org_counts[candidate["offer_id"]]
    eligible.sort(key=_rank_key)
    selected_pairs: set[tuple[str, str]] = set()
    selected_orgs: set[str] = set()
    offer_counts: Counter[str] = Counter()
    family_counts: Counter[str] = Counter()
    capacity_reasons: dict[tuple[str, str], list[str]] = {}

    for candidate in eligible:
        key = (candidate["org_id"], candidate["offer_id"])
        reasons: list[str] = []
        if candidate["org_id"] in selected_orgs:
            reasons.append("ORG_ALREADY_SELECTED")
        if len(selected_pairs) >= campaign_cap:
            reasons.append("CAMPAIGN_CAPACITY_REACHED")
        offer_cap = offer_caps.get(candidate["offer_id"], campaign_cap)
        if offer_counts[candidate["offer_id"]] >= offer_cap:
            reasons.append("OFFER_CAPACITY_REACHED")
        family_cap = family_caps.get(candidate["family"], campaign_cap)
        if family_counts[candidate["family"]] >= family_cap:
            reasons.append("FAMILY_CAPACITY_REACHED")
        if reasons:
            capacity_reasons[key] = reasons
            continue
        selected_pairs.add(key)
        selected_orgs.add(candidate["org_id"])
        offer_counts[candidate["offer_id"]] += 1
        family_counts[candidate["family"]] += 1

    decisions: list[dict[str, Any]] = []
    for candidate in sorted(candidates, key=lambda x: (x["org_id"], x["offer_id"])):
        key = (candidate["org_id"], candidate["offer_id"])
        if candidate["base_reasons"]:
            state = "HOLD"
            reasons = candidate["base_reasons"]
        elif key in selected_pairs:
            state = "SELECTED_FOR_OWNER_REVIEW"
            reasons = ["ONE_ORG_ONE_PAID_OFFER_SELECTED"]
        else:
            state = "HOLD"
            reasons = capacity_reasons.get(key, ["NOT_SELECTED_BY_DETERMINISTIC_PRIORITY"])
        decisions.append(
            {
                **{k: v for k, v in candidate.items() if k != "base_reasons"},
                "state": state,
                "reason_codes": reasons,
                "commercial_intent": "PAID_SCOPE_ONLY",
                "external_send_authorized": False,
                "buyer_acceptance_evidenced": False,
                "payment_evidenced": False,
                "revenue_evidenced": False,
            }
        )

    selected = [d for d in decisions if d["state"] == "SELECTED_FOR_OWNER_REVIEW"]
    result: dict[str, Any] = {
        "schema": OUTPUT_SCHEMA,
        "policy_version": POLICY_VERSION,
        "as_of": _utc_string(as_of),
        "campaign_id": data["campaign"]["campaign_id"],
        "campaign_generation_sha256": data["campaign"]["campaign_generation_sha256"],
        "input_sha256": input_digest,
        "summary": {
            "organization_count": len(data["organizations"]),
            "offer_count": len(data["offers"]),
            "candidate_count": len(decisions),
            "selected_count": len(selected),
            "campaign_capacity": campaign_cap,
            "one_offer_per_org": True,
            "external_send_authorized": False,
        },
        "selected": selected,
        "decisions": decisions,
        "authority": {
            "external_send_authorized": False,
            "lease_or_slot_authorized": False,
            "buyer_contact_authorized": False,
            "acceptance_or_contract_authorized": False,
            "payment_or_cash_authorized": False,
            "revenue_recognition_authorized": False,
        },
    }
    result["receipt_sha256"] = sha256_bytes(canonical_bytes(result))
    return result


def verify_portfolio(packet: Any, compiled: Any, *, as_of: dt.datetime) -> bool:
    """Verify exact historical compilation while enforcing current source freshness.

    ``as_of`` is trusted current UTC.  The packet's own ``as_of`` is part of its
    immutable compilation identity; verification recompiles at that instant, but
    refuses a packet once the normalized relationship source has aged past policy.
    """
    if type(compiled) is not dict or compiled.get("schema") != OUTPUT_SCHEMA:
        return False
    try:
        compiled_as_of = _utc(compiled.get("as_of"), "compiled.as_of")
        if compiled_as_of > as_of:
            return False
        current = validate_input(packet, as_of=as_of)
        max_age = current["policy"]["max_source_age_hours"]
        for org in current["organizations"]:
            observed = _utc(org["relationship_observed_at"], "relationship_observed_at")
            if _age_hours(observed, as_of) > max_age:
                return False
        expected = compile_portfolio(packet, as_of=compiled_as_of)
    except RouterError:
        return False
    return canonical_bytes(expected) == canonical_bytes(compiled)


def render_markdown(compiled: dict[str, Any]) -> str:
    if compiled.get("schema") != OUTPUT_SCHEMA:
        raise RouterError("cannot render unsupported output schema")
    lines = [
        "# Offer Portfolio Router — Owner Review Queue",
        "",
        f"Campaign: `{compiled['campaign_id']}`",
        f"As of: `{compiled['as_of']}`",
        f"Receipt: `{compiled['receipt_sha256']}`",
        "",
        "This artifact selects at most one paid offer per canonical organization. It grants **no send authority**.",
        "",
        "## Selected",
        "",
    ]
    if not compiled["selected"]:
        lines.append("No organizations selected.")
    else:
        lines.append("| Organization | Offer | Family | Price | Fit | Signal |")
        lines.append("|---|---|---|---:|---|---|")
        for row in compiled["selected"]:
            dollars = f"${row['price_minor'] // 100:,}.{row['price_minor'] % 100:02d}"
            tags = ", ".join(row["fit_tags"])
            lines.append(
                f"| `{row['org_id']}` | `{row['offer_id']}` | {row['family']} | {dollars} | {tags} | {row['buying_signal']} |"
            )
    holds = [d for d in compiled["decisions"] if d["state"] == "HOLD"]
    lines.extend(["", "## Holds", "", "| Organization | Offer | Reasons |", "|---|---|---|"])
    for row in holds:
        lines.append(f"| `{row['org_id']}` | `{row['offer_id']}` | {', '.join(row['reason_codes'])} |")
    lines.extend(
        [
            "",
            "## Authority ceiling",
            "",
            "- `external_send_authorized=false`",
            "- no lease or initial-outreach slot is created",
            "- no buyer contact, acceptance, payment, cash, or revenue is inferred",
            "- canonical relationship/custody/send controls remain authoritative",
            "",
        ]
    )
    return "\n".join(lines)


def _read_regular_file(path: Path) -> bytes:
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError as exc:
        raise RouterError(f"cannot open input safely: {path}") from exc
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise RouterError(f"input is not a regular file: {path}")
        if st.st_size > 2_000_000:
            raise RouterError("input exceeds 2,000,000 bytes")
        chunks: list[bytes] = []
        remaining = st.st_size + 1
        while remaining > 0:
            chunk = os.read(fd, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        if len(raw) != st.st_size:
            raise RouterError("input changed while reading")
        return raw
    finally:
        os.close(fd)


def _write_exclusive(path: Path, raw: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags, 0o644)
    except OSError as exc:
        raise RouterError(f"refusing to overwrite/nonexclusive output: {path}") from exc
    try:
        total = 0
        while total < len(raw):
            total += os.write(fd, raw[total:])
        os.fsync(fd)
    finally:
        os.close(fd)


def _now_utc_seconds() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("compile", help="compile a current owner-review queue")
    c.add_argument("--input", required=True)
    c.add_argument("--json-out", required=True)
    c.add_argument("--md-out", required=True)
    v = sub.add_parser("verify", help="verify a packet at current trusted UTC")
    v.add_argument("--input", required=True)
    v.add_argument("--packet", required=True)
    args = parser.parse_args(argv)
    try:
        source = load_json_strict_bytes(_read_regular_file(Path(args.input)))
        now = _now_utc_seconds()
        if args.cmd == "compile":
            compiled = compile_portfolio(source, as_of=now)
            _write_exclusive(Path(args.json_out), canonical_bytes(compiled) + b"\n")
            _write_exclusive(Path(args.md_out), render_markdown(compiled).encode("utf-8"))
            print(compiled["receipt_sha256"])
            return 0
        candidate = load_json_strict_bytes(_read_regular_file(Path(args.packet)))
        ok = verify_portfolio(source, candidate, as_of=now)
        print("VERIFIED" if ok else "HOLD")
        return 0 if ok else 2
    except RouterError as exc:
        print(f"HOLD: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli())
