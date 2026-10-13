#!/usr/bin/env python3
"""Outcome Commerce Bridge for Commons.

Normalizes existing offers without replacing their canonical terms, quotes
composable pricing plans, and reconciles append-only economic events.  It does
not move money and never promotes a charge candidate to payment truth.

Examples:

  python3 host/outcome_commerce.py validate
  python3 host/outcome_commerce.py catalog
  python3 host/outcome_commerce.py quote --listing ho-issue-to-pr
  python3 host/outcome_commerce.py quote --catalog revenue/outcome_commerce/examples/hybrid_catalog.json \
      --listing synthetic-hybrid-agent --metric platform=1 --metric actions=1350 --metric outcomes=4
  python3 host/outcome_commerce.py statement --catalog revenue/outcome_commerce/examples/hybrid_catalog.json \
      --events revenue/outcome_commerce/examples/hybrid_events.json
  python3 host/outcome_commerce.py project \
      --events revenue/outcome_commerce/examples/commercial_events.json
  python3 host/outcome_commerce.py export-a2a
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DEFAULT_CATALOG = ROOT / "revenue" / "outcome_commerce" / "catalog.json"
DEFAULT_A2A = ROOT / "revenue" / "outcome_commerce" / "a2a-skills.json"
DEFAULT_COMMERCIAL_EVENTS = ROOT / "revenue" / "outcome_commerce" / "examples" / "commercial_events.json"

ID_RE = re.compile(r"^[A-Za-z0-9._-]{8,80}$")
CURRENCY_RE = re.compile(r"^[A-Z][A-Z0-9._-]{1,31}$")
DECIMAL_RE = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]{1,8})?$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
BLOB_SHA_RE = re.compile(r"[0-9a-f]{40}\Z")
ARTIFACT_PATH_RE = re.compile(
    r"(?!/)(?![A-Za-z]:)(?!.*(?:^|/)\.\.(?:/|$))[A-Za-z0-9._/-]+\Z"
)
CHECKOUT_STATUS_RE = re.compile(r"(?!LIVE\Z)[A-Za-z0-9._-]+\Z")
STRIPE_CHECKOUT_RE = re.compile(
    r"https://(?:buy|donate)\.stripe\.com/[A-Za-z0-9_-]+\Z"
)
KINDS = {
    "fixed",
    "subscription",
    "usage",
    "outcome",
    "milestone",
    "take_rate",
    "license",
    "sponsorship",
}
EVENT_FOR_KIND = {
    "fixed": "FIXED_ACTIVATED",
    "subscription": "SUBSCRIPTION_CYCLE",
    "usage": "USAGE_RECORDED",
    "outcome": "OUTCOME_VERIFIED",
    "milestone": "MILESTONE_ACCEPTED",
    "take_rate": "GROSS_REVENUE_RECORDED",
    "license": "LICENSE_ACTIVATED",
    "sponsorship": "SPONSORSHIP_DELIVERED",
}
EVENT_STATES = {"RECORDED", "VERIFIED", "ACCEPTED", "REVERSED"}
NONCHARGEABLE_OUTCOME_EVENTS = {"OUTCOME_CANDIDATE", "OUTCOME_FAILED", "OUTCOME_ESCALATED"}
JOB_STATES = {
    "DISCOVERED", "QUALIFIED", "QUOTED", "FUNDED", "RUNNING", "SUBMITTED",
    "ACCEPTED", "REJECTED", "SETTLED", "BANK_AVAILABLE", "EXPIRED",
    "REFUNDED", "UNKNOWN_EFFECT",
}
FUNNEL_STAGE_ORDER = (
    "DISCOVERED", "QUALIFIED", "QUOTED", "FUNDED", "RUNNING", "SUBMITTED",
    "ACCEPTED", "SETTLED", "BANK_AVAILABLE",
)
FUNNEL_READINESS = {
    "READY_FOR_CHECKOUT", "READY_FOR_QUALIFICATION", "NEEDS_DEFINITION",
    "BLOCKED_PROVIDER_CAPABILITY",
}
ALLOWED_JOB_TRANSITIONS = {
    None: {"DISCOVERED"},
    "DISCOVERED": {"QUALIFIED"},
    "QUALIFIED": {"QUOTED"},
    "QUOTED": {"FUNDED", "EXPIRED"},
    "FUNDED": {"RUNNING", "REFUNDED"},
    "RUNNING": {"SUBMITTED", "UNKNOWN_EFFECT"},
    "UNKNOWN_EFFECT": {"RUNNING", "SUBMITTED"},
    "SUBMITTED": {"ACCEPTED", "REJECTED"},
    "REJECTED": {"RUNNING"},
    "ACCEPTED": {"SETTLED"},
    "SETTLED": {"BANK_AVAILABLE"},
    "BANK_AVAILABLE": set(),
    "EXPIRED": set(),
    "REFUNDED": set(),
}
ACTION_TARGETS = {
    "OPPORTUNITY": {"DISCOVERED"},
    "QUALIFY": {"QUALIFIED"},
    "QUOTE": {"QUOTED"},
    "FUND": {"FUNDED"},
    "FULFILL": {"RUNNING"},
    "DELIVER": {"SUBMITTED"},
    "ACCEPT": {"ACCEPTED", "REJECTED"},
    "EXPIRE": {"EXPIRED"},
    "REFUND": {"REFUNDED"},
    "SETTLE": {"SETTLED"},
    "PAYOUT": {"BANK_AVAILABLE"},
    "RECONCILE": {"RUNNING", "SUBMITTED"},
}
EFFECT_STATUS_TRANSITIONS = {
    "REQUESTED": {"CONFIRMED", "FAILED", "UNKNOWN_EFFECT"},
    "UNKNOWN_EFFECT": {"CONFIRMED", "FAILED"},
    "CONFIRMED": set(),
    "FAILED": set(),
}
MONEY_QUANTUM = Decimal("0.01")


class CommerceError(ValueError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _load_json(path: str | os.PathLike[str]) -> Any:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle, parse_float=lambda value: (_ for _ in ()).throw(
            CommerceError("JSON money and quantities must be decimal strings, not floats: %s" % value)
        ))


def _load_events(path: str | os.PathLike[str]) -> list[dict[str, Any]]:
    text = Path(path).read_text(encoding="utf-8")
    try:
        value = json.loads(text, parse_float=lambda value: (_ for _ in ()).throw(
            CommerceError("event decimals must be strings, not floats: %s" % value)
        ))
    except json.JSONDecodeError:
        value = [json.loads(line) for line in text.splitlines() if line.strip()]
    if isinstance(value, dict):
        value = value.get("events")
    if not isinstance(value, list) or not all(isinstance(row, dict) for row in value):
        raise CommerceError("events must be a JSON array, an {events:[...]} object, or JSON Lines")
    return value


def _decimal(value: Any, field: str, *, signed: bool = False) -> Decimal:
    if not isinstance(value, str) or not DECIMAL_RE.fullmatch(value):
        raise CommerceError("%s must be a decimal string with at most 8 fractional digits" % field)
    try:
        out = Decimal(value)
    except InvalidOperation as exc:
        raise CommerceError("%s is not a decimal" % field) from exc
    if not signed and out < 0:
        raise CommerceError("%s must be non-negative" % field)
    return out


def _money(value: Decimal) -> str:
    return format(value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP), "f")


def _quantity(value: Decimal) -> str:
    out = format(value.normalize(), "f")
    return "0" if out in {"-0", "-0.0"} else out


def _id(value: Any, field: str) -> str:
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise CommerceError("%s must be 8-80 characters: A-Z a-z 0-9 . _ -" % field)
    return value


def _timestamp(value: Any, field: str) -> str:
    if not isinstance(value, str) or not (value.endswith("Z") or re.search(r"[+-]\d\d:\d\d$", value)):
        raise CommerceError("%s must be an offset-aware ISO-8601 timestamp" % field)
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    if "." in text:
        head, rest = text.split(".", 1)
        digits = []
        tz = rest
        for i, ch in enumerate(rest):
            if ch.isdigit():
                digits.append(ch)
                continue
            tz = rest[i:]
            break
        else:
            tz = ""
        frac = "".join(digits)[:6].ljust(6, "0")
        text = "%s.%s%s" % (head, frac, tz)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise CommerceError("%s is not a real timestamp" % field) from exc
    if parsed.utcoffset() is None:
        raise CommerceError("%s must include an offset" % field)
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _resolve_pointer(value: Any, pointer: str) -> Any:
    if pointer == "":
        return value
    if not isinstance(pointer, str) or not pointer.startswith("/"):
        raise CommerceError("source.pointer must be a JSON Pointer")
    node = value
    for raw in pointer.split("/")[1:]:
        part = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(node, list):
            try:
                node = node[int(part)]
            except (ValueError, IndexError) as exc:
                raise CommerceError("source.pointer does not resolve: %s" % pointer) from exc
        elif isinstance(node, dict) and part in node:
            node = node[part]
        else:
            raise CommerceError("source.pointer does not resolve: %s" % pointer)
    return node


def _component_errors(component: Any, prefix: str) -> list[str]:
    errors: list[str] = []
    if not isinstance(component, dict):
        return [prefix + " must be an object"]
    try:
        _id(component.get("id"), prefix + ".id")
    except CommerceError as exc:
        errors.append(str(exc))
    kind = component.get("kind")
    if kind not in KINDS:
        errors.append(prefix + ".kind must be one of " + ", ".join(sorted(KINDS)))
        return errors
    try:
        if kind in {"fixed", "subscription", "milestone", "license"}:
            _decimal(component.get("amount"), prefix + ".amount")
        elif kind in {"usage", "outcome", "sponsorship"}:
            if not isinstance(component.get("meter"), str) or not component["meter"].strip():
                errors.append(prefix + ".meter missing")
            _decimal(component.get("unit_amount"), prefix + ".unit_amount")
            if "included" in component:
                _decimal(component["included"], prefix + ".included")
        elif kind == "take_rate":
            if not isinstance(component.get("meter"), str) or not component["meter"].strip():
                errors.append(prefix + ".meter missing")
            bps = component.get("rate_bps")
            if not isinstance(bps, int) or isinstance(bps, bool) or not 0 <= bps <= 10000:
                errors.append(prefix + ".rate_bps must be an integer from 0 through 10000")
    except CommerceError as exc:
        errors.append(str(exc))
    return errors


def _string_list_errors(value: Any, field: str) -> list[str]:
    if not isinstance(value, list):
        return [field + " must be an array"]
    errors = []
    if len(value) != len({_canonical(item) for item in value}):
        errors.append(field + " must not contain duplicates")
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            errors.append("%s[%d] must be a non-empty string" % (field, index))
    return errors


def _funnel_errors(catalog: dict[str, Any], listings: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    present = {key for key in ("funnel_stage_order", "funnel_truth", "funnels") if key in catalog}
    if not present:
        return ["funnel_stage_order, funnel_truth, and funnels are required"]
    if present != {"funnel_stage_order", "funnel_truth", "funnels"}:
        return ["funnel_stage_order, funnel_truth, and funnels must appear together"]
    stages = catalog["funnel_stage_order"]
    if not isinstance(stages, list) or tuple(stages) != FUNNEL_STAGE_ORDER:
        errors.append("funnel_stage_order must match the canonical job state chain")

    truth = catalog["funnel_truth"]
    truth_fields = {
        "as_of", "source", "distinct_targets", "delivered_transports",
        "unclassified_response_signals", "verified_positive_replies",
        "accepted_scopes", "paid_deliveries", "collected_cash_usd", "next_edge",
    }
    if not isinstance(truth, dict) or set(truth) != truth_fields:
        errors.append("funnel_truth fields are invalid")
    else:
        try:
            _timestamp(truth["as_of"], "funnel_truth.as_of")
            _decimal(truth["collected_cash_usd"], "funnel_truth.collected_cash_usd")
        except CommerceError as exc:
            errors.append(str(exc))
        if not isinstance(truth["source"], str) or not truth["source"].strip():
            errors.append("funnel_truth.source must be a non-empty string")
        for field in (
            "distinct_targets", "delivered_transports", "unclassified_response_signals",
            "verified_positive_replies", "accepted_scopes", "paid_deliveries",
        ):
            if not isinstance(truth[field], int) or isinstance(truth[field], bool) or truth[field] < 0:
                errors.append("funnel_truth.%s must be a non-negative integer" % field)
        if truth["next_edge"] != "QUALIFIED_BUYER":
            errors.append("funnel_truth.next_edge must be QUALIFIED_BUYER")

    funnels = catalog["funnels"]
    if not isinstance(funnels, dict):
        return errors + ["funnels must be an object"]
    listing_by_id = {row.get("id"): row for row in listings if isinstance(row, dict)}
    if set(funnels) != set(listing_by_id):
        errors.append("funnels keys must exactly match listing ids")
    priorities: list[int] = []
    funnel_fields = {
        "priority", "readiness", "buyer", "trigger", "acquisition", "qualification",
        "conversion", "fulfillment", "measurement", "next_offer", "gaps",
    }
    nested_fields = {
        "acquisition": {"primary_channel", "alternate_channels", "message", "route", "cta"},
        "qualification": {"route", "required", "state_after"},
        "conversion": {"mode", "status", "next_step", "state_after", "evidence_required"},
        "fulfillment": {"deliverables", "acceptance", "refund"},
        "measurement": {"dom_action", "click_truth", "first_evidence_state", "success_state"},
    }
    for listing_id, funnel in funnels.items():
        prefix = "funnels.%s" % listing_id
        if not isinstance(funnel, dict) or set(funnel) != funnel_fields:
            errors.append(prefix + " fields are invalid")
            continue
        priority = funnel["priority"]
        if not isinstance(priority, int) or isinstance(priority, bool) or priority < 1:
            errors.append(prefix + ".priority must be a positive integer")
        else:
            priorities.append(priority)
        if funnel["readiness"] not in FUNNEL_READINESS:
            errors.append(prefix + ".readiness is invalid")
        for field in ("buyer", "trigger"):
            if not isinstance(funnel[field], str) or not funnel[field].strip():
                errors.append(prefix + "." + field + " must be a non-empty string")
        for section, fields in nested_fields.items():
            value = funnel[section]
            if not isinstance(value, dict) or set(value) != fields:
                errors.append(prefix + "." + section + " fields are invalid")
        if any(not isinstance(funnel[name], dict) for name in nested_fields):
            continue
        acquisition = funnel["acquisition"]
        for field in ("primary_channel", "message", "route", "cta"):
            if not isinstance(acquisition[field], str) or not acquisition[field].strip():
                errors.append(prefix + ".acquisition." + field + " must be a non-empty string")
        errors.extend(_string_list_errors(acquisition["alternate_channels"], prefix + ".acquisition.alternate_channels"))

        qualification = funnel["qualification"]
        if not isinstance(qualification["route"], str) or not qualification["route"].strip():
            errors.append(prefix + ".qualification.route must be a non-empty string")
        errors.extend(_string_list_errors(qualification["required"], prefix + ".qualification.required"))
        if qualification["state_after"] != "QUALIFIED":
            errors.append(prefix + ".qualification.state_after must be QUALIFIED")

        conversion = funnel["conversion"]
        listing = listing_by_id.get(listing_id, {})
        checkout = listing.get("checkout")
        checkout_status = checkout.get("status") if isinstance(checkout, dict) else None
        if checkout_status == "ACTIVE_CHARGEABLE":
            expected_mode = "ACTIVE_STRIPE_LINK"
            expected_status = "ACTIVE_CHARGEABLE"
            checkout_first = funnel["readiness"] == "READY_FOR_CHECKOUT"
            expected_action = "checkout-open" if checkout_first else "qualification-open"
            expected_click_truth = "INTENT_ONLY"
            expected_first = "FUNDED" if checkout_first else "DISCOVERED"
        elif checkout_status == "LIVEMODE_URL_RECORDED":
            expected_mode = "RECORDED_STRIPE_LINK"
            expected_status = "CAPABILITY_UNVERIFIED"
            expected_action = "provider-capability-unverified"
            expected_click_truth = "NO_CLICK_SURFACE"
            expected_first = "DISCOVERED"
        else:
            expected_mode = "CUSTOMER_SPECIFIC_INVOICE"
            expected_status = "NOT_ISSUED"
            expected_action = "qualification-open"
            expected_click_truth = "INTENT_ONLY"
            expected_first = "DISCOVERED"
        if conversion["mode"] != expected_mode or conversion["status"] != expected_status:
            errors.append(prefix + ".conversion must match the listing checkout state")
        if conversion["state_after"] != "FUNDED":
            errors.append(prefix + ".conversion.state_after must be FUNDED")
        for field in ("next_step", "evidence_required"):
            if not isinstance(conversion[field], str) or not conversion[field].strip():
                errors.append(prefix + ".conversion." + field + " must be a non-empty string")

        fulfillment = funnel["fulfillment"]
        errors.extend(_string_list_errors(fulfillment["deliverables"], prefix + ".fulfillment.deliverables"))
        errors.extend(_string_list_errors(fulfillment["acceptance"], prefix + ".fulfillment.acceptance"))
        if not isinstance(fulfillment["refund"], str) or not fulfillment["refund"].strip():
            errors.append(prefix + ".fulfillment.refund must be a non-empty string")

        measurement = funnel["measurement"]
        if measurement["dom_action"] != expected_action:
            errors.append(prefix + ".measurement.dom_action does not match conversion mode")
        if measurement["click_truth"] != expected_click_truth:
            errors.append(prefix + ".measurement.click_truth does not match conversion mode")
        if measurement["first_evidence_state"] != expected_first:
            errors.append(prefix + ".measurement.first_evidence_state does not match conversion mode")
        if measurement["success_state"] != "BANK_AVAILABLE":
            errors.append(prefix + ".measurement.success_state must be BANK_AVAILABLE")

        errors.extend(_string_list_errors(funnel["next_offer"], prefix + ".next_offer"))
        if isinstance(funnel["next_offer"], list):
            for next_id in funnel["next_offer"]:
                if next_id not in listing_by_id:
                    errors.append(prefix + ".next_offer contains unknown listing " + str(next_id))
        errors.extend(_string_list_errors(funnel["gaps"], prefix + ".gaps"))
        if funnel["readiness"] == "NEEDS_DEFINITION" and not funnel["gaps"]:
            errors.append(prefix + ".gaps must name the missing definition")
    if sorted(priorities) != list(range(1, len(listings) + 1)):
        errors.append("funnel priorities must be the unique sequence 1..%d" % len(listings))
    return errors


def catalog_errors(catalog: Any, *, root: Path | None = ROOT, check_sources: bool = True) -> list[str]:
    errors: list[str] = []
    if not isinstance(catalog, dict):
        return ["catalog must be an object"]
    if catalog.get("schema_version") != "outcome-commerce/v1":
        errors.append("schema_version must be outcome-commerce/v1")
    if catalog.get("kind") != "OUTCOME_COMMERCE_CATALOG":
        errors.append("kind must be OUTCOME_COMMERCE_CATALOG")
    listings = catalog.get("listings")
    if not isinstance(listings, list) or not listings:
        return errors + ["listings must be a non-empty array"]
    seen: set[str] = set()
    for index, listing in enumerate(listings):
        prefix = "listings[%d]" % index
        if not isinstance(listing, dict):
            errors.append(prefix + " must be an object")
            continue
        try:
            listing_id = _id(listing.get("id"), prefix + ".id")
            if listing_id in seen:
                errors.append("duplicate listing id %s" % listing_id)
            seen.add(listing_id)
        except CommerceError as exc:
            errors.append(str(exc))
        pricing = listing.get("pricing")
        if not isinstance(pricing, dict):
            errors.append(prefix + ".pricing must be an object")
            continue
        currency = pricing.get("currency")
        if not isinstance(currency, str) or not CURRENCY_RE.fullmatch(currency):
            errors.append(prefix + ".pricing.currency is invalid")
        components = pricing.get("components")
        if not isinstance(components, list) or not components:
            errors.append(prefix + ".pricing.components must be non-empty")
        else:
            component_ids: set[str] = set()
            for cindex, component in enumerate(components):
                errors.extend(_component_errors(component, prefix + ".pricing.components[%d]" % cindex))
                if isinstance(component, dict) and isinstance(component.get("id"), str):
                    if component["id"] in component_ids:
                        errors.append("duplicate component id %s in %s" % (component["id"], listing.get("id")))
                    component_ids.add(component["id"])
        source = listing.get("source")
        source_artifact = listing.get("source_artifact")
        if (source is None) == (source_artifact is None):
            errors.append(prefix + " requires exactly one of source or source_artifact")
        if source is not None:
            if not isinstance(source, dict) or not source.get("path") or "pointer" not in source:
                errors.append(prefix + ".source requires path and pointer")
            elif check_sources and root is not None:
                path = root / str(source["path"])
                if not path.is_file():
                    errors.append("source path missing: %s" % source["path"])
                else:
                    try:
                        node = _resolve_pointer(_load_json(path), source["pointer"])
                        expected = source.get("offer_id")
                        if expected:
                            actual = None
                            if isinstance(node, dict):
                                actual = node.get("id", node.get("offer_id"))
                            if actual != expected:
                                errors.append("source offer id mismatch for %s: %r" % (listing.get("id"), actual))
                    except (CommerceError, OSError, json.JSONDecodeError) as exc:
                        errors.append("source read failed for %s: %s" % (source["path"], exc))
        if source_artifact is not None:
            if not isinstance(source_artifact, dict):
                errors.append(prefix + ".source_artifact must be an object")
            elif set(source_artifact) != {"path", "blob_sha", "terms_authority"}:
                errors.append(prefix + ".source_artifact has invalid fields")
            else:
                artifact_path = source_artifact.get("path")
                blob_sha = source_artifact.get("blob_sha")
                if (
                    not isinstance(artifact_path, str)
                    or not ARTIFACT_PATH_RE.fullmatch(artifact_path)
                ):
                    errors.append(prefix + ".source_artifact.path is invalid")
                if not isinstance(blob_sha, str) or not BLOB_SHA_RE.fullmatch(blob_sha):
                    errors.append(prefix + ".source_artifact.blob_sha is invalid")
                if source_artifact.get("terms_authority") != "source":
                    errors.append(prefix + ".source_artifact.terms_authority must be source")
                if (
                    check_sources
                    and root is not None
                    and isinstance(artifact_path, str)
                    and ARTIFACT_PATH_RE.fullmatch(artifact_path)
                    and isinstance(blob_sha, str)
                    and BLOB_SHA_RE.fullmatch(blob_sha)
                ):
                    try:
                        resolved_root = root.resolve()
                        resolved_path = (resolved_root / artifact_path).resolve()
                    except (OSError, ValueError) as exc:
                        errors.append(
                            "source artifact path failed for %s: %s" % (artifact_path, exc)
                        )
                        continue
                    try:
                        resolved_path.relative_to(resolved_root)
                    except ValueError:
                        errors.append("source artifact escapes root: %s" % artifact_path)
                    else:
                        if not resolved_path.is_file():
                            errors.append("source artifact missing: %s" % artifact_path)
                        else:
                            try:
                                actual = subprocess.run(
                                    ["git", "hash-object", str(resolved_path)],
                                    cwd=resolved_root,
                                    capture_output=True,
                                    text=True,
                                    check=True,
                                ).stdout.strip()
                            except (OSError, subprocess.CalledProcessError) as exc:
                                errors.append(
                                    "source artifact hash failed for %s: %s"
                                    % (artifact_path, exc)
                                )
                            else:
                                if actual != blob_sha:
                                    errors.append(
                                        "source artifact blob mismatch for %s: %s"
                                        % (listing.get("id"), actual)
                                    )
        checkout = listing.get("checkout")
        if checkout is not None:
            if not isinstance(checkout, dict):
                errors.append(prefix + ".checkout must be an object")
            else:
                status = checkout.get("status")
                if status in {"ACTIVE_CHARGEABLE", "LIVEMODE_URL_RECORDED"}:
                    required = {
                        "status", "provider", "url",
                        "link_active", "account_charges_enabled",
                    }
                    if status == "ACTIVE_CHARGEABLE":
                        required.add("capability_evidence")
                        required.add("account_payouts_enabled")
                    if set(checkout) != required:
                        errors.append(prefix + ".checkout Stripe fields are invalid")
                    if checkout.get("provider") != "stripe":
                        errors.append(prefix + ".checkout provider must be stripe")
                    url = checkout.get("url")
                    if not isinstance(url, str) or not STRIPE_CHECKOUT_RE.fullmatch(url):
                        errors.append(prefix + ".checkout url is invalid")
                    if status == "ACTIVE_CHARGEABLE":
                        if checkout.get("link_active") is not True:
                            errors.append(prefix + ".checkout link_active must be true")
                        if checkout.get("account_charges_enabled") is not True:
                            errors.append(prefix + ".checkout account_charges_enabled must be true")
                        if checkout.get("account_payouts_enabled") is not True:
                            errors.append(prefix + ".checkout account_payouts_enabled must be true")
                        evidence = checkout.get("capability_evidence")
                        if not isinstance(evidence, dict) or set(evidence) != {"reference", "observed_at"}:
                            errors.append(prefix + ".checkout capability_evidence fields are invalid")
                        else:
                            reference = evidence.get("reference")
                            if not isinstance(reference, str) or not reference.strip():
                                errors.append(prefix + ".checkout capability_evidence.reference is required")
                            try:
                                _timestamp(
                                    evidence.get("observed_at"),
                                    prefix + ".checkout.capability_evidence.observed_at",
                                )
                            except CommerceError as exc:
                                errors.append(str(exc))
                    else:
                        if checkout.get("link_active") != "UNVERIFIED":
                            errors.append(prefix + ".checkout recorded link_active must be UNVERIFIED")
                        if checkout.get("account_charges_enabled") is not False:
                            errors.append(prefix + ".checkout recorded account_charges_enabled must be false")
                elif status == "NOT_MINTED":
                    if set(checkout) != {"status"}:
                        errors.append(prefix + ".checkout NOT_MINTED fields are invalid")
                else:
                    errors.append(prefix + ".checkout status is invalid")
    errors.extend(_funnel_errors(catalog, listings))
    return errors


def canonical_catalog_errors(catalog: Any, *, root: Path | None = ROOT, check_sources: bool = True) -> list[str]:
    """Validate the canonical catalog, including its per-SKU funnel contract.

    catalog.schema.json intentionally remains reusable by synthetic quote and
    statement fixtures. The live catalog has the stricter all-SKU requirement.
    """
    errors = catalog_errors(catalog, root=root, check_sources=check_sources)
    if isinstance(catalog, dict):
        required = {"funnel_stage_order", "funnel_truth", "funnels"}
        missing = sorted(required - set(catalog))
        if missing:
            errors.append("canonical catalog missing funnel fields: " + ", ".join(missing))
    return errors


def _catalog(path: str | os.PathLike[str]) -> dict[str, Any]:
    value = _load_json(path)
    if not isinstance(value, dict):
        raise CommerceError("catalog must be an object")
    return value


def _listing(catalog: dict[str, Any], listing_id: str) -> dict[str, Any]:
    for listing in catalog.get("listings", []):
        if listing.get("id") == listing_id:
            return listing
    raise CommerceError("listing not found: %s" % listing_id)


def _metric_args(values: list[str]) -> dict[str, Decimal]:
    metrics: dict[str, Decimal] = {}
    for raw in values:
        if "=" not in raw:
            raise CommerceError("--metric must be component_id=decimal")
        key, value = raw.split("=", 1)
        _id(key, "metric component id")
        if key in metrics:
            raise CommerceError("duplicate --metric for %s" % key)
        metrics[key] = _decimal(value, "metric %s" % key)
    return metrics


def _line_for_component(component: dict[str, Any], quantity: Decimal) -> dict[str, Any]:
    kind = component["kind"]
    amount = Decimal("0")
    basis = _quantity(quantity)
    if kind in {"fixed", "subscription", "milestone", "license"}:
        amount = _decimal(component["amount"], component["id"] + ".amount") * quantity
    elif kind in {"usage", "outcome", "sponsorship"}:
        included = _decimal(component.get("included", "0"), component["id"] + ".included")
        billable = max(Decimal("0"), quantity - included)
        amount = _decimal(component["unit_amount"], component["id"] + ".unit_amount") * billable
        basis = "%s %s; %s billable after %s included" % (
            _quantity(quantity), component.get("meter", "units"), _quantity(billable), _quantity(included)
        )
    elif kind == "take_rate":
        amount = quantity * Decimal(component["rate_bps"]) / Decimal("10000")
        basis = "%s gross at %s bps" % (_money(quantity), component["rate_bps"])
    return {
        "component_id": component["id"],
        "kind": kind,
        "basis": basis,
        "amount": _money(amount),
    }


def quote(catalog: dict[str, Any], listing_id: str, metrics: dict[str, Decimal]) -> dict[str, Any]:
    listing = _listing(catalog, listing_id)
    known = {row["id"] for row in listing["pricing"]["components"]}
    unknown = sorted(set(metrics) - known)
    if unknown:
        raise CommerceError("metrics name unknown components: %s" % ", ".join(unknown))
    lines = []
    for component in listing["pricing"]["components"]:
        default = (
            Decimal("1")
            if component["kind"] in {"fixed", "subscription", "milestone", "license"}
            else Decimal("0")
        )
        lines.append(_line_for_component(component, metrics.get(component["id"], default)))
    total = sum((_decimal(row["amount"], "line amount") for row in lines), Decimal("0"))
    digest = _sha256_text(_canonical({"listing_id": listing_id, "metrics": {k: str(v) for k, v in sorted(metrics.items())}}))
    return {
        "schema_version": "outcome-commerce-statement/v1",
        "kind": "COMMERCE_QUOTE",
        "statement_id": "quote-" + digest[:24],
        "created_at": _utc_now(),
        "listing_id": listing_id,
        "listing_state": listing.get("state", "UNMEASURED"),
        "currency": listing["pricing"]["currency"],
        "line_items": lines,
        "gross_amount": _money(total),
        "credits_applied": "0.00",
        "net_amount": _money(total),
        "economic_state": "QUOTED",
        "payment_truth": {
            "authorization": "UNMEASURED",
            "settlement": "UNMEASURED",
            "payout": "UNMEASURED",
            "bank_available": "UNMEASURED",
            "cash_claimed": False,
        },
    }


def _validate_event(event: dict[str, Any], listings: dict[str, dict[str, Any]]) -> dict[str, Any]:
    ident = _id(event.get("event_id"), "event_id")
    if event.get("schema_version") != "outcome-commerce-event/v1":
        raise CommerceError("%s schema_version must be outcome-commerce-event/v1" % ident)
    _id(event.get("idempotency_key"), "idempotency_key")
    _id(event.get("correlation_id"), "correlation_id")
    if event.get("causation_id") is not None:
        _id(event.get("causation_id"), "causation_id")
    listing_id = _id(event.get("listing_id"), "listing_id")
    if listing_id not in listings:
        raise CommerceError("%s references unknown listing %s" % (ident, listing_id))
    state = event.get("state")
    if state not in EVENT_STATES:
        raise CommerceError("%s state is invalid" % ident)
    event_type = event.get("event_type")
    if not isinstance(event_type, str):
        raise CommerceError("%s event_type missing" % ident)
    occurred_at = _timestamp(event.get("occurred_at"), "occurred_at")
    normalized = dict(event)
    normalized["occurred_at"] = occurred_at
    if state == "REVERSED":
        _id(event.get("reverses_event_id"), "reverses_event_id")
        return normalized
    if event_type in {"CREDIT_GRANTED", "ADJUSTMENT"}:
        _decimal(event.get("amount"), "amount", signed=event_type == "ADJUSTMENT")
        if event.get("currency") != listings[listing_id]["pricing"]["currency"]:
            raise CommerceError("%s currency does not match listing" % ident)
        return normalized
    component_id = _id(event.get("component_id"), "component_id")
    components = {row["id"]: row for row in listings[listing_id]["pricing"]["components"]}
    if component_id not in components:
        raise CommerceError("%s references unknown component %s" % (ident, component_id))
    component = components[component_id]
    if event_type in NONCHARGEABLE_OUTCOME_EVENTS:
        if component["kind"] != "outcome" or state != "RECORDED":
            raise CommerceError("%s non-chargeable outcome must target an outcome component in RECORDED state" % ident)
        _decimal(event.get("quantity", "1"), "quantity")
        return normalized
    expected_type = EVENT_FOR_KIND[component["kind"]]
    if event_type != expected_type:
        raise CommerceError("%s event_type must be %s for %s" % (ident, expected_type, component["kind"]))
    _decimal(event.get("quantity", "1"), "quantity")
    evidence = event.get("evidence", [])
    if not isinstance(evidence, list):
        raise CommerceError("%s evidence must be an array" % ident)
    if component["kind"] == "outcome" and state != "VERIFIED":
        raise CommerceError("%s outcome must be VERIFIED to become chargeable" % ident)
    if component["kind"] in {"fixed", "milestone", "license"} and state != "ACCEPTED":
        raise CommerceError("%s %s event must be ACCEPTED" % (ident, component["kind"]))
    if component["kind"] in {"outcome", "milestone"} and not evidence:
        raise CommerceError("%s requires outcome evidence" % ident)
    return normalized


def statement(catalog: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    if not events:
        raise CommerceError("statement requires at least one event")
    listings = {row["id"]: row for row in catalog["listings"]}
    unique: dict[str, dict[str, Any]] = {}
    duplicates: list[str] = []
    for raw in events:
        event = _validate_event(raw, listings)
        ident = event["event_id"]
        if ident in unique:
            if _canonical(unique[ident]) != _canonical(event):
                raise CommerceError("conflicting duplicate event_id %s" % ident)
            duplicates.append(ident)
        else:
            unique[ident] = event
    effect_keys: dict[str, str] = {}
    for event in unique.values():
        key = event["idempotency_key"]
        if key in effect_keys:
            raise CommerceError(
                "metering idempotency_key %s appears on both %s and %s" %
                (key, effect_keys[key], event["event_id"])
            )
        effect_keys[key] = event["event_id"]
    reversed_ids: set[str] = set()
    for event in sorted(unique.values(), key=lambda row: row["event_id"]):
        if event["state"] == "REVERSED":
            target = event["reverses_event_id"]
            if target not in unique:
                raise CommerceError("reversal %s targets unknown event %s" % (event["event_id"], target))
            if unique[target]["state"] == "REVERSED":
                raise CommerceError("reversal chains are not valid: %s" % event["event_id"])
            reversed_ids.add(target)

    grouped: dict[str, list[dict[str, Any]]] = {}
    for event in sorted(unique.values(), key=lambda row: row["event_id"]):
        if event["state"] != "REVERSED" and event["event_id"] not in reversed_ids:
            grouped.setdefault(event["listing_id"], []).append(event)

    listing_rows = []
    nonchargeable_event_ids: list[str] = []
    currency_seen: set[str] = set()
    for listing_id in sorted(grouped):
        listing = listings[listing_id]
        currency = listing["pricing"]["currency"]
        currency_seen.add(currency)
        source_events = grouped[listing_id]
        components = {row["id"]: row for row in listing["pricing"]["components"]}
        quantities = {key: Decimal("0") for key in components}
        adjustments = Decimal("0")
        credits = Decimal("0")
        evidence: list[dict[str, Any]] = []
        for event in source_events:
            if event["event_type"] == "CREDIT_GRANTED":
                credits += _decimal(event["amount"], "credit amount")
            elif event["event_type"] == "ADJUSTMENT":
                adjustments += _decimal(event["amount"], "adjustment amount", signed=True)
            elif event["event_type"] in NONCHARGEABLE_OUTCOME_EVENTS:
                nonchargeable_event_ids.append(event["event_id"])
            else:
                quantities[event["component_id"]] += _decimal(event.get("quantity", "1"), "quantity")
                evidence.extend(event.get("evidence", []))
        lines = [_line_for_component(component, quantities[component_id]) for component_id, component in components.items()]
        if adjustments:
            lines.append({"component_id": "adjustment", "kind": "adjustment", "basis": "accepted adjustment events", "amount": _money(adjustments)})
        gross = sum((_decimal(row["amount"], "line amount", signed=True) for row in lines), Decimal("0"))
        if gross < 0:
            gross = Decimal("0")
        applied = min(gross, credits)
        net = gross - applied
        listing_rows.append({
            "listing_id": listing_id,
            "currency": currency,
            "event_ids": sorted(event["event_id"] for event in source_events),
            "line_items": lines,
            "gross_amount": _money(gross),
            "credits_available": _money(credits),
            "credits_applied": _money(applied),
            "credit_balance": _money(credits - applied),
            "net_amount": _money(net),
            "evidence": evidence,
        })
    if len(currency_seen) > 1:
        raise CommerceError("one statement cannot sum mixed currencies: %s" % ", ".join(sorted(currency_seen)))
    currency = next(iter(currency_seen), "UNMEASURED")
    gross = sum((_decimal(row["gross_amount"], "gross") for row in listing_rows), Decimal("0"))
    applied = sum((_decimal(row["credits_applied"], "credits") for row in listing_rows), Decimal("0"))
    digest = _sha256_text(_canonical({key: unique[key] for key in sorted(unique)}))
    return {
        "schema_version": "outcome-commerce-statement/v1",
        "kind": "COMMERCE_STATEMENT",
        "statement_id": "statement-" + digest[:24],
        "created_at": max(event["occurred_at"] for event in unique.values()),
        "catalog_sha256": _sha256_text(_canonical(catalog)),
        "currency": currency,
        "source_event_count": len(events),
        "unique_event_count": len(unique),
        "deduped_event_ids": sorted(set(duplicates)),
        "reversed_event_ids": sorted(reversed_ids),
        "nonchargeable_event_ids": sorted(nonchargeable_event_ids),
        "listings": listing_rows,
        "gross_amount": _money(gross),
        "credits_applied": _money(applied),
        "net_amount": _money(gross - applied),
        "economic_state": "CHARGEABLE",
        "payment_truth": {
            "authorization": "UNMEASURED",
            "settlement": "UNMEASURED",
            "payout": "UNMEASURED",
            "bank_available": "UNMEASURED",
            "cash_claimed": False,
        },
    }


def _nullable_commercial_id(value: Any, field: str) -> str | None:
    if value is None:
        return None
    return _id(value, field)


def _validate_hash(value: Any, field: str, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise CommerceError("%s must be a lowercase SHA-256 digest" % field)
    return value


def _validate_commercial_event(event: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(event, dict):
        raise CommerceError("commercial event must be an object")
    ident = _id(event.get("event_id"), "event_id")
    if event.get("schema_version") != "commons-commercial-event/v1":
        raise CommerceError("%s schema_version must be commons-commercial-event/v1" % ident)
    if event.get("kind") != "COMMERCIAL_EVENT":
        raise CommerceError("%s kind must be COMMERCIAL_EVENT" % ident)
    _id(event.get("job_id"), "job_id")
    _id(event.get("correlation_id"), "correlation_id")
    _id(event.get("idempotency_key"), "idempotency_key")
    for field in ("attempt_id", "offer_id", "order_id", "receipt_id", "parent_event_id", "causation_id", "reconciles_event_id"):
        _nullable_commercial_id(event.get(field), field)
    occurred_at = _timestamp(event.get("occurred_at"), "occurred_at")
    observed_at = _timestamp(event.get("observed_at"), "observed_at")
    if observed_at < occurred_at:
        raise CommerceError("%s observed_at precedes occurred_at" % ident)
    from_state = event.get("from_state")
    to_state = event.get("to_state")
    if from_state is not None and from_state not in JOB_STATES:
        raise CommerceError("%s from_state is invalid" % ident)
    if to_state not in JOB_STATES:
        raise CommerceError("%s to_state is invalid" % ident)
    action_type = event.get("action_type")
    if action_type not in {
        "OPPORTUNITY", "QUALIFY", "QUOTE", "FUND", "FULFILL", "DELIVER",
        "ACCEPT", "EXPIRE", "REFUND", "EMAIL", "DEPLOY", "SETTLE",
        "PAYOUT", "RECONCILE", "OTHER",
    }:
        raise CommerceError("%s action_type is invalid" % ident)
    status = event.get("status")
    if status not in EFFECT_STATUS_TRANSITIONS:
        raise CommerceError("%s status is invalid" % ident)
    provider = event.get("provider")
    if not isinstance(provider, dict) or not isinstance(provider.get("name"), str) or not provider["name"].strip():
        raise CommerceError("%s provider.name is required" % ident)
    receipt = provider.get("external_receipt_id")
    if receipt is not None and (not isinstance(receipt, str) or not receipt.strip() or len(receipt) > 240):
        raise CommerceError("%s provider.external_receipt_id is invalid" % ident)
    amount = event.get("amount")
    currency = event.get("currency")
    if amount is None:
        if currency is not None:
            raise CommerceError("%s currency must be null when amount is null" % ident)
    else:
        _decimal(amount, "amount")
        if not isinstance(currency, str) or not CURRENCY_RE.fullmatch(currency):
            raise CommerceError("%s currency is invalid" % ident)
    _validate_hash(event.get("input_hash"), "input_hash", nullable=True)
    _validate_hash(event.get("output_hash"), "output_hash", nullable=True)
    evidence = event.get("evidence_refs")
    if not isinstance(evidence, list):
        raise CommerceError("%s evidence_refs must be an array" % ident)
    for index, ref in enumerate(evidence):
        if not isinstance(ref, dict) or not isinstance(ref.get("uri"), str) or not ref["uri"].strip():
            raise CommerceError("%s evidence_refs[%d].uri is required" % (ident, index))
        _validate_hash(ref.get("sha256"), "evidence_refs[%d].sha256" % index)
        if not isinstance(ref.get("claim"), str) or not ref["claim"].strip():
            raise CommerceError("%s evidence_refs[%d].claim is required" % (ident, index))
    if event.get("public_safe") is not True:
        raise CommerceError("%s public_safe must be true" % ident)
    for field in ("claims", "non_claims"):
        values = event.get(field)
        if not isinstance(values, list) or not all(isinstance(value, str) and value.strip() for value in values):
            raise CommerceError("%s %s must be an array of nonempty strings" % (ident, field))
    if not event.get("non_claims"):
        raise CommerceError("%s non_claims must name at least one limit" % ident)
    runtime = event.get("runtime")
    if runtime is not None:
        if not isinstance(runtime, dict) or not isinstance(runtime.get("label"), str) or not runtime["label"].strip():
            raise CommerceError("%s runtime.label is required" % ident)
        for field in ("workflow_version", "skill_lock_digest"):
            value = runtime.get(field)
            if value != "UNMEASURED" and not (
                isinstance(value, str) and value.startswith("sha256:") and SHA256_RE.fullmatch(value[7:])
            ):
                raise CommerceError("%s runtime.%s must be sha256:<digest> or UNMEASURED" % (ident, field))
        workspace = runtime.get("workspace_sha")
        if workspace != "UNMEASURED" and not (isinstance(workspace, str) and re.fullmatch(r"[0-9a-f]{40}", workspace)):
            raise CommerceError("%s runtime.workspace_sha must be a git SHA or UNMEASURED" % ident)
    normalized = dict(event)
    normalized["occurred_at"] = occurred_at
    normalized["observed_at"] = observed_at
    return normalized


def _validate_transition(event: dict[str, Any], current: str | None) -> None:
    ident = event["event_id"]
    before = event["from_state"]
    after = event["to_state"]
    status = event["status"]
    if before != current:
        raise CommerceError("%s from_state %r does not match current state %r" % (ident, before, current))
    if status in {"REQUESTED", "FAILED"} and before == after:
        if before is None:
            raise CommerceError("%s cannot record an effect before DISCOVERED" % ident)
        return
    if status == "UNKNOWN_EFFECT":
        if before != "RUNNING" or after != "UNKNOWN_EFFECT":
            raise CommerceError("%s UNKNOWN_EFFECT must transition RUNNING to UNKNOWN_EFFECT" % ident)
        return
    if status == "FAILED" and before == "UNKNOWN_EFFECT" and after == "RUNNING":
        if event.get("action_type") != "RECONCILE":
            raise CommerceError("%s unknown-effect absence must use RECONCILE" % ident)
        return
    if status != "CONFIRMED":
        raise CommerceError("%s cannot advance state with status %s" % (ident, status))
    if after not in ALLOWED_JOB_TRANSITIONS.get(before, set()):
        raise CommerceError("%s transition %r -> %s is invalid" % (ident, before, after))
    targets = ACTION_TARGETS.get(event["action_type"])
    if targets is not None and after not in targets:
        raise CommerceError("%s action_type %s cannot enter %s" % (ident, event["action_type"], after))
    evidence_states = {"FUNDED", "SUBMITTED", "ACCEPTED", "SETTLED", "BANK_AVAILABLE", "REFUNDED"}
    if after in evidence_states:
        if not event["evidence_refs"]:
            raise CommerceError("%s transition to %s requires evidence" % (ident, after))
        if not event["provider"].get("external_receipt_id"):
            raise CommerceError("%s transition to %s requires an external/public receipt reference" % (ident, after))


def commercial_projection(events: list[dict[str, Any]]) -> dict[str, Any]:
    if not events:
        raise CommerceError("commercial projection requires at least one event")
    unique: dict[str, dict[str, Any]] = {}
    duplicates: list[str] = []
    for raw in events:
        event = _validate_commercial_event(raw)
        ident = event["event_id"]
        if ident in unique:
            if _canonical(unique[ident]) != _canonical(event):
                raise CommerceError("conflicting duplicate event_id %s" % ident)
            duplicates.append(ident)
        else:
            unique[ident] = event
    grouped: dict[str, list[dict[str, Any]]] = {}
    for event in unique.values():
        grouped.setdefault(event["job_id"], []).append(event)
    jobs: list[dict[str, Any]] = []
    for job_id in sorted(grouped):
        rows = sorted(grouped[job_id], key=lambda row: (row["occurred_at"], row["event_id"]))
        correlation_id = rows[0]["correlation_id"]
        current: str | None = None
        previous_event_id: str | None = None
        effects: dict[str, dict[str, Any]] = {}
        for event in rows:
            if event["correlation_id"] != correlation_id:
                raise CommerceError("job %s mixes correlation IDs" % job_id)
            if event["parent_event_id"] != previous_event_id:
                raise CommerceError(
                    "%s parent_event_id %r does not match predecessor %r" %
                    (event["event_id"], event["parent_event_id"], previous_event_id)
                )
            _validate_transition(event, current)
            key = event["idempotency_key"]
            if key in effects:
                prior = effects[key]
                if event.get("causation_id") != prior["latest_event_id"]:
                    raise CommerceError("%s reuses %s without causal linkage" % (event["event_id"], key))
                allowed = EFFECT_STATUS_TRANSITIONS[prior["status"]]
                if event["status"] not in allowed:
                    raise CommerceError(
                        "%s effect status %s cannot follow %s" %
                        (event["event_id"], event["status"], prior["status"])
                    )
                if event["provider"]["name"] != prior["provider"]:
                    raise CommerceError("%s changes provider for idempotency_key %s" % (event["event_id"], key))
                if event["action_type"] != prior["action_type"] and event["action_type"] != "RECONCILE":
                    raise CommerceError("%s changes action for idempotency_key %s" % (event["event_id"], key))
            if event["from_state"] == "UNKNOWN_EFFECT":
                target = event.get("reconciles_event_id")
                if not target or target not in unique or unique[target]["status"] != "UNKNOWN_EFFECT":
                    raise CommerceError("%s must reconcile a named UNKNOWN_EFFECT event" % event["event_id"])
            effects[key] = {
                "idempotency_key": key,
                "action_type": effects.get(key, {}).get("action_type", event["action_type"]),
                "provider": event["provider"]["name"],
                "status": event["status"],
                "latest_event_id": event["event_id"],
                "external_receipt_id": event["provider"].get("external_receipt_id"),
            }
            current = event["to_state"]
            previous_event_id = event["event_id"]
        confirmed_targets = {row["to_state"] for row in rows if row["status"] == "CONFIRMED"}
        bank = "BANK_AVAILABLE" in confirmed_targets
        jobs.append({
            "job_id": job_id,
            "correlation_id": correlation_id,
            "current_state": current,
            "event_ids": [row["event_id"] for row in rows],
            "effects": [effects[key] for key in sorted(effects)],
            "payment_truth": {
                "confirmation": "CONFIRMED" if "FUNDED" in confirmed_targets else "UNMEASURED",
                "settlement": "CONFIRMED" if "SETTLED" in confirmed_targets else "UNMEASURED",
                "payout": "CONFIRMED" if bank else "UNMEASURED",
                "bank_available": "CONFIRMED" if bank else "UNMEASURED",
                "cash_claimed": bool(bank and current == "BANK_AVAILABLE"),
            },
        })
    digest = _sha256_text(_canonical({key: unique[key] for key in sorted(unique)}))
    return {
        "schema_version": "commons-commercial-projection/v1",
        "kind": "COMMERCIAL_EVENT_PROJECTION",
        "projection_id": "projection-" + digest[:24],
        "created_at": max(event["observed_at"] for event in unique.values()),
        "source_event_count": len(events),
        "unique_event_count": len(unique),
        "deduped_event_ids": sorted(set(duplicates)),
        "jobs": jobs,
        "claims": ["The projection is a deterministic fold of the named public-safe events."],
        "non_claims": [
            "The projector did not call a payment, email, deployment, delivery, CRM, or treasury provider.",
            "A provider reference proves only the state named by its event and evidence.",
            "Commercial metadata is never an admission, identity, permission, approval, or access gate.",
        ],
    }


def _write_or_print(value: Any, path: str | None) -> None:
    text = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if path:
        dest = Path(path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
        print(str(dest))
    else:
        sys.stdout.write(text)


def cmd_validate(args: argparse.Namespace) -> int:
    catalog = _catalog(args.catalog)
    errors = canonical_catalog_errors(catalog, root=ROOT, check_sources=not args.no_source_check)
    if errors:
        for error in errors:
            print("INVALID " + error)
        return 2
    print("OK %d listings; pricing=%s" % (len(catalog["listings"]), ",".join(sorted(KINDS))))
    print("CHARGEABLE != AUTHORIZATION != SETTLEMENT != PAYOUT != BANK_AVAILABLE")
    return 0


def cmd_catalog(args: argparse.Namespace) -> int:
    catalog = _catalog(args.catalog)
    for listing in catalog.get("listings", []):
        kinds = "+".join(row["kind"] for row in listing["pricing"]["components"])
        print("%s  %-15s %-9s %s" % (listing["id"], listing.get("state", "UNMEASURED"), listing["pricing"]["currency"], kinds))
        if listing.get("source"):
            print("  source %s#%s" % (listing["source"]["path"], listing["source"]["pointer"]))
        elif listing.get("source_artifact"):
            print(
                "  source %s@%s"
                % (
                    listing["source_artifact"]["path"],
                    listing["source_artifact"]["blob_sha"],
                )
            )
    return 0


def cmd_quote(args: argparse.Namespace) -> int:
    catalog = _catalog(args.catalog)
    errors = catalog_errors(catalog, root=ROOT, check_sources=False)
    if errors:
        raise CommerceError("invalid catalog: " + "; ".join(errors))
    _write_or_print(quote(catalog, args.listing, _metric_args(args.metric)), args.out)
    return 0


def cmd_statement(args: argparse.Namespace) -> int:
    catalog = _catalog(args.catalog)
    errors = catalog_errors(catalog, root=ROOT, check_sources=False)
    if errors:
        raise CommerceError("invalid catalog: " + "; ".join(errors))
    _write_or_print(statement(catalog, _load_events(args.events)), args.out)
    return 0


def cmd_project(args: argparse.Namespace) -> int:
    _write_or_print(commercial_projection(_load_events(args.events)), args.out)
    return 0


def cmd_export_a2a(args: argparse.Namespace) -> int:
    fragment = _load_json(args.fragment)
    if fragment.get("kind") != "A2A_SKILLS_FRAGMENT" or fragment.get("is_agent_card") is not False:
        raise CommerceError("A2A export must remain a skills fragment, not a false server card")
    _write_or_print(fragment, args.out)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="host/outcome_commerce.py")
    parser.add_argument("--catalog", default=str(DEFAULT_CATALOG))
    sub = parser.add_subparsers(dest="command", required=True)

    validate_parser = sub.add_parser("validate")
    validate_parser.add_argument("--no-source-check", action="store_true")

    sub.add_parser("catalog")

    quote_parser = sub.add_parser("quote")
    quote_parser.add_argument("--listing", required=True)
    quote_parser.add_argument("--metric", action="append", default=[])
    quote_parser.add_argument("--out")

    statement_parser = sub.add_parser("statement")
    statement_parser.add_argument("--events", required=True)
    statement_parser.add_argument("--out")

    project_parser = sub.add_parser("project")
    project_parser.add_argument("--events", default=str(DEFAULT_COMMERCIAL_EVENTS))
    project_parser.add_argument("--out")

    a2a_parser = sub.add_parser("export-a2a")
    a2a_parser.add_argument("--fragment", default=str(DEFAULT_A2A))
    a2a_parser.add_argument("--out")

    args = parser.parse_args(argv)
    try:
        if args.command == "validate":
            return cmd_validate(args)
        if args.command == "catalog":
            return cmd_catalog(args)
        if args.command == "quote":
            return cmd_quote(args)
        if args.command == "statement":
            return cmd_statement(args)
        if args.command == "project":
            return cmd_project(args)
        if args.command == "export-a2a":
            return cmd_export_a2a(args)
    except (CommerceError, OSError, json.JSONDecodeError) as exc:
        print("INVALID %s" % exc, file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
