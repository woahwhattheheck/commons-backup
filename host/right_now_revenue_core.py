#!/usr/bin/env python3
"""Compile Commons revenue truth into one deterministic execution queue.

This control plane composes existing public artifacts.  It does not contact a
prospect, create a checkout, accept a scope, deliver work, or claim cash.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from host import settled_awards, settled_cash, smart_outreach  # noqa: E402


CATALOG_PATH = ROOT / "revenue" / "right_now" / "catalog.json"
DIAGNOSTIC_PATH = ROOT / "revenue" / "right_now" / "diagnostic_offer.json"
SETTLED_AWARDS_PATH = ROOT / "revenue" / "right_now" / "settled_awards.json"
SETTLED_CASH_PATH = ROOT / "revenue" / "right_now" / "settled_cash.json"
OUTREACH_PATH = ROOT / "revenue" / "smart_outreach" / "candidates.json"
PAYMENT_PATH = ROOT / "revenue" / "payment_ready" / "current_receipt.json"
HUMAN_PATH = ROOT / "revenue" / "human_outcomes" / "offers.json"
SURVIVAL_PATH = ROOT / "revenue" / "production_survival" / "offer.json"
RECEIPTS_PATH = ROOT / "revenue" / "payment_ready" / "outreach_receipts"
SCHEMA_VERSION = "commons-right-now-control/v3"
DECISION_PRIORITY = {
    "READY_TO_DRAFT": 0,
    "RESEARCH_REQUIRED": 1,
    "HOLD_OCCUPIED": 2,
    "HOLD_DO_NOT_RESEND": 3,
    "HOLD_DO_NOT_CONTACT": 4,
    "DISQUALIFIED": 5,
}
LIVE_CASH_CITE = "goat-right-now-catalog-json-live-cash-20260909-01"
LIVE_CASH_PRODUCTS = (
    {"name": "Dealer Service Lead Rescue", "price_usd": 199, "path": "dealer-service-lead-rescue.html"},
    {"name": "Referral Intake Completeness", "price_usd": 199, "path": "referral-intake-completeness.html"},
    {"name": "Repair Booking Preflight", "price_usd": 199, "path": "repair-booking-preflight.html"},
    {"name": "Plant Downtime Handoff", "price_usd": 199, "path": "plant-downtime-handoff.html"},
)
LIVE_CASH_LARGER_FIXED = (
    {
        "days": 10,
        "name": "GGUF diagnostic",
        "path": "diagnostic.html",
        "price_usd": 12000,
    },
    {
        "days": 30,
        "name": "White Box pilot",
        "path": "commercial.html",
        "price_usd": 30000,
    },
)


class ControlError(ValueError):
    """A source artifact violates the revenue control contract."""


class _CheckoutAnchorParser(HTMLParser):
    """Collect buyer-visible checkout hrefs without executing page JavaScript."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        values = dict(attrs)
        href = values.get("href")
        if "data-checkout" in values and isinstance(href, str):
            self.hrefs.append(href)


def canonical_text(value: Any) -> str:
    return json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ControlError(f"cannot read {path}: {error}") from error
    if not isinstance(value, dict):
        raise ControlError(f"{path} must contain one JSON object")
    return value


def sha256_file(path: Path) -> str:
    # Hash LF-normalized bytes so Windows working copies and Linux CI agree.
    data = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(data).hexdigest()


def _positive_integer(value: Any, where: str) -> int:
    if type(value) is not int or value <= 0:
        raise ControlError(f"{where} must be a positive integer")
    return value


def _latest_as_of(*values: Any) -> str:
    parsed: list[datetime] = []
    for index, value in enumerate(values):
        if not isinstance(value, str):
            raise ControlError(f"as_of[{index}] must be canonical UTC seconds")
        try:
            moment = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=timezone.utc
            )
        except ValueError as error:
            raise ControlError(f"as_of[{index}] must be canonical UTC seconds") from error
        if moment.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
            raise ControlError(f"as_of[{index}] must be canonical UTC seconds")
        parsed.append(moment)
    return max(parsed).strftime("%Y-%m-%dT%H:%M:%SZ")


def _provider_utc(value: Any, where: str) -> datetime:
    if not isinstance(value, str):
        raise ControlError(f"{where} must be a UTC timestamp")
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ControlError(f"{where} must be a UTC timestamp") from error
    if moment.tzinfo is None or moment.utcoffset() != timezone.utc.utcoffset(moment):
        raise ControlError(f"{where} must be UTC")
    return moment.astimezone(timezone.utc)


def validate_live_cash(value: Any) -> dict[str, Any]:
    """Keep the leftover live-cash shelf inside the control contract.

    GOAT added verified product-page cites on the catalog. Exact-set
    validation used to reject that extra field. Expand the contract so
    the four public checkouts stay measured instead of being dropped.
    Catalog JSON KEEP (#15021) added live_cash.larger_fixed
    (diagnostic.html/$12k · commercial.html/$30k). Exact-set used to
    reject that extra field too, wiping Larger fixed on every control
    compile while $199 stayed. KEEP Larger fixed so remints
    cannot drop those doors. Paths only — no invented Stripe URLs.
    """
    if not isinstance(value, dict):
        raise ControlError("live_cash must be an object")
    required = {"cite", "note", "products", "larger_fixed"}
    if set(value) != required:
        raise ControlError("live_cash fields differ from the control contract")
    cite = value["cite"]
    if (
        not isinstance(cite, list)
        or not cite
        or not all(isinstance(item, str) and item.strip() for item in cite)
    ):
        raise ControlError("live_cash.cite must be a non-empty list of strings")
    if LIVE_CASH_CITE not in cite:
        raise ControlError("live_cash.cite missing the right-now catalog cite")
    note = value["note"]
    if not isinstance(note, str) or not note.strip():
        raise ControlError("live_cash.note must be a non-empty string")
    lowered = note.lower()
    if "buy.stripe.com" in lowered or "donate.stripe.com" in lowered:
        raise ControlError("live_cash must not invent Stripe URLs")
    if "Larger fixed" not in note:
        raise ControlError("live_cash.note must keep Larger fixed engagements")
    products = value["products"]
    if not isinstance(products, list) or len(products) != len(LIVE_CASH_PRODUCTS):
        raise ControlError("live_cash.products must list the four verified product pages")
    for actual, expected in zip(products, LIVE_CASH_PRODUCTS):
        if not isinstance(actual, dict):
            raise ControlError("live_cash.products entries must be objects")
        if set(actual) != {"name", "price_usd", "path"}:
            raise ControlError("live_cash.products entry fields differ from the control contract")
        if actual.get("name") != expected["name"]:
            raise ControlError("live_cash.products name drift")
        if actual.get("price_usd") != expected["price_usd"]:
            raise ControlError("live_cash.products price drift")
        if actual.get("path") != expected["path"]:
            raise ControlError("live_cash.products path drift")
    larger = value["larger_fixed"]
    if not isinstance(larger, list) or len(larger) != len(LIVE_CASH_LARGER_FIXED):
        raise ControlError(
            "live_cash.larger_fixed must list the two verified Larger-fixed product pages"
        )
    for actual, expected in zip(larger, LIVE_CASH_LARGER_FIXED):
        if not isinstance(actual, dict):
            raise ControlError("live_cash.larger_fixed entries must be objects")
        if set(actual) != {"days", "name", "path", "price_usd"}:
            raise ControlError(
                "live_cash.larger_fixed entry fields differ from the control contract"
            )
        if actual.get("name") != expected["name"]:
            raise ControlError("live_cash.larger_fixed name drift")
        if actual.get("price_usd") != expected["price_usd"]:
            raise ControlError("live_cash.larger_fixed price drift")
        if actual.get("days") != expected["days"]:
            raise ControlError("live_cash.larger_fixed days drift")
        if actual.get("path") != expected["path"]:
            raise ControlError("live_cash.larger_fixed path drift")
        blob = json.dumps(actual, sort_keys=True)
        if "buy.stripe.com" in blob or "donate.stripe.com" in blob or "plink_" in blob:
            raise ControlError("live_cash.larger_fixed must not invent Stripe URLs")
    return value


def validate_catalog(
    catalog: dict[str, Any],
) -> dict[str, Any]:
    required = {
        "schema_version", "kind", "as_of", "canonical_page", "purpose",
        "truth", "ranking_rule", "portfolio", "offers",
        "preserved_long_horizon_routes", "live_cash",
    }
    if set(catalog) != required:
        raise ControlError("catalog fields differ from the control contract")
    if catalog["kind"] != "RIGHT_NOW_REVENUE_CATALOG":
        raise ControlError("unsupported catalog kind")
    truth = catalog["truth"]
    for field in ("collected_cash_usd", "verified_positive_replies", "accepted_scopes"):
        if type(truth.get(field)) is not int or truth[field] < 0:
            raise ControlError(f"truth.{field} must be a non-negative integer")
    if type(truth.get("active_chargeable_checkout")) is not bool:
        raise ControlError("truth.active_chargeable_checkout must be boolean")

    human = read_object(HUMAN_PATH)
    survival = read_object(SURVIVAL_PATH)
    diagnostic = read_object(DIAGNOSTIC_PATH)
    canonical = {row["id"]: row for row in human["offers"]}
    entry = survival["entry_offer"]
    canonical[entry["id"]] = entry
    canonical[diagnostic["id"]] = diagnostic
    allowed_payment_states = {
        "BUYER_SPECIFIC_HANDOFF_REQUIRED",
    }
    offers = catalog["offers"]
    if not isinstance(offers, list) or not offers:
        raise ControlError("catalog.offers must be non-empty")
    if [row.get("rank") for row in offers] != list(range(1, len(offers) + 1)):
        raise ControlError("offer rank must be unique and contiguous")
    seen: set[str] = set()
    for row in offers:
        offer_id = row.get("id")
        if not isinstance(offer_id, str) or offer_id in seen:
            raise ControlError("offer ids must be unique non-empty strings")
        seen.add(offer_id)
        if offer_id not in canonical:
            raise ControlError(f"offer lacks canonical source: {offer_id}")
        price = _positive_integer(row.get("price_usd"), f"offers.{offer_id}.price_usd")
        if price != canonical[offer_id]["fixed_amount"]:
            raise ControlError(f"offer price drift: {offer_id}")
        payment_state = row.get("payment_state")
        if payment_state not in allowed_payment_states:
            raise ControlError(f"unexpected payment state: {offer_id}")
        for field in (
            "delivery_window", "buyer_input", "deliverable", "start_route",
            "source", "next_external_event", "founder_bottleneck", "commons_bottleneck",
        ):
            if not isinstance(row.get(field), str) or not row[field].strip():
                raise ControlError(f"offers.{offer_id}.{field} must be non-empty")
    if catalog["truth"]["active_chargeable_checkout"] is not False:
        raise ControlError(
            "truth.active_chargeable_checkout must be false (no live public checkout)"
        )
    validate_live_cash(catalog["live_cash"])
    return catalog


def payment_truth(value: dict[str, Any]) -> dict[str, Any]:
    """Project one offer-specific payment receipt without making it global cash truth."""
    facts = value.get("facts")
    if not isinstance(facts, dict):
        raise ControlError("payment receipt facts must be an object")
    cash = facts.get("collected_cash_usd")
    if type(cash) is not int or cash < 0:
        raise ControlError("payment receipt cash must be a non-negative integer")
    cash_claimed = value.get("cash_claimed")
    if type(cash_claimed) is not bool:
        raise ControlError("payment receipt cash_claimed must be boolean")
    if cash_claimed != (cash > 0):
        raise ControlError("offer-specific payment receipt cash claim is inconsistent")
    processor = facts.get("processor_payment")
    return {
        "receipt_id": value.get("receipt_id"),
        "offer_id": value.get("offer_id"),
        "stage": value.get("stage"),
        "state": value.get("state"),
        "next_stage": value.get("next_stage"),
        "processor_payment": processor,
        "collected_cash_usd": cash,
        "cash_claimed": cash_claimed,
    }


def build_control() -> dict[str, Any]:
    raw_catalog = read_object(CATALOG_PATH)
    catalog = validate_catalog(raw_catalog)
    payment = payment_truth(read_object(PAYMENT_PATH))
    awards = settled_awards.summarize_ledger(
        settled_awards.read_ledger(SETTLED_AWARDS_PATH)
    )
    cash = settled_cash.summarize_ledger(
        settled_cash.read_ledger(SETTLED_CASH_PATH)
    )
    outreach = smart_outreach.build_plan(
        smart_outreach.read_object(OUTREACH_PATH), RECEIPTS_PATH
    )
    catalog_cash = catalog["truth"]["collected_cash_usd"]
    if cash["settled_usd"] != str(catalog_cash):
        raise ControlError("global cash truth differs from the settled-cash ledger")

    offers = []
    for row in catalog["offers"]:
        offers.append({
            "rank": row["rank"],
            "id": row["id"],
            "name": row["name"],
            "price_usd": row["price_usd"],
            "delivery_window": row["delivery_window"],
            "start_route": row["start_route"],
            "payment_state": row["payment_state"],
            "next_external_event": row["next_external_event"],
            "founder_bottleneck": row["founder_bottleneck"],
            "commons_bottleneck": row["commons_bottleneck"],
        })

    queue = []
    for item in outreach["items"]:
        queue.append({
            "prospect_id": item["prospect_id"],
            "organization": item["organization"],
            "offer_id": outreach["offer"]["sku_id"],
            "decision": item["decision"],
            "fit_score": item["score"],
            "source_url": item["evidence"]["source_url"],
            "observed_at": item["evidence"]["observed_at"],
            "route_state": item["route"]["state"],
            "collision_receipts": item["collision_receipts"],
            "missing": item["missing"],
            "next_action": item["next_action"],
            "transport_authorized": False,
        })
    queue.sort(key=lambda row: (
        DECISION_PRIORITY.get(row["decision"], 99),
        -row["fit_score"],
        row["prospect_id"],
    ))
    for rank, item in enumerate(queue, 1):
        item["rank"] = rank

    counts = outreach["truth"]["decision_counts"]
    blockers = [
        {
            "rank": 1,
            "id": "DIRECT_OFFER_PAYMENT_EVIDENCE",
            "owner": "FOUNDER_OR_CONNECTED_PROCESSOR_LANE",
            "condition": "A current Commons offer records its own chargeable buyer payment receipt.",
            "current": payment["processor_payment"],
        },
        {
            "rank": 2,
            "id": "QUALIFIED_UNCONTACTED_DEMAND",
            "owner": "COMMONS_RESEARCH_AND_OUTREACH_LANES",
            "condition": "At least one non-colliding evidence-bound prospect reaches READY_TO_DRAFT.",
            "current": counts["READY_TO_DRAFT"],
        },
        {
            "rank": 3,
            "id": "BUYER_ACCEPTANCE",
            "owner": "REAL_BUYER",
            "condition": "A real buyer accepts one exact scope and delivery window.",
            "current": catalog["truth"]["accepted_scopes"],
        },
    ]

    source_paths = [
        CATALOG_PATH,
        DIAGNOSTIC_PATH,
        SETTLED_AWARDS_PATH,
        SETTLED_CASH_PATH,
        OUTREACH_PATH,
        PAYMENT_PATH,
        HUMAN_PATH,
        SURVIVAL_PATH,
    ]
    sources = [
        {"path": path.relative_to(ROOT).as_posix(), "sha256": sha256_file(path)}
        for path in source_paths
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "RIGHT_NOW_REVENUE_CONTROL",
        "as_of": _latest_as_of(catalog["as_of"], awards["as_of"], cash["as_of"]),
        "truth": {
            "collected_cash_usd": catalog_cash,
            "verified_positive_replies": catalog["truth"]["verified_positive_replies"],
            "accepted_scopes": catalog["truth"]["accepted_scopes"],
            "active_chargeable_checkout": False,
            "prospects_evaluated": outreach["truth"]["prospects_evaluated"],
            "ready_to_draft": counts["READY_TO_DRAFT"],
            "transport_actions": outreach["truth"]["transport_actions"],
            "settled_cash_receipts": cash["settled_receipts"],
            "settled_cash_usd": cash["settled_usd"],
            "cash_bank_availability_asserted": cash["bank_availability_asserted"],
            "cash_withdrawability_asserted": cash["withdrawability_asserted"],
            "paid_awards": awards["paid_awards"],
            "settled_amounts_by_currency": awards["totals_by_currency"],
            "usd_conversion_asserted": awards["usd_conversion_asserted"],
            "award_bank_availability_asserted": awards["bank_availability_asserted"],
            "award_withdrawability_asserted": awards["withdrawability_asserted"],
        },
        "payment": payment,
        "settled_cash": cash,
        "settled_awards": awards,
        "offers": offers,
        "execution_queue": queue,
        "blockers": blockers,
        "preserved_portfolio": catalog["portfolio"],
        "source_receipts": sources,
    }


def validate_control(value: dict[str, Any]) -> None:
    expected = build_control()
    if value != expected:
        raise ControlError("committed control snapshot differs from compiled sources")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("compile", "validate"))
    parser.add_argument(
        "--snapshot",
        type=Path,
        default=ROOT / "revenue" / "right_now" / "control.json",
    )
    args = parser.parse_args()
    try:
        control = build_control()
        if args.command == "compile":
            sys.stdout.write(canonical_text(control))
        else:
            validate_control(read_object(args.snapshot))
            totals = ", ".join(
                f"{row['amount']} {row['currency']}"
                for row in control["settled_awards"]["totals_by_currency"]
            )
            print(
                "VALID "
                f"{len(control['offers'])} offers "
                f"{len(control['execution_queue'])} opportunities "
                f"{control['truth']['transport_actions']} transports "
                f"USD {control['truth']['collected_cash_usd']} cash · "
                f"{control['truth']['settled_cash_receipts']} provider receipt · "
                f"{control['truth']['paid_awards']} paid award · {totals} settled"
            )
    except (
        ControlError,
        settled_awards.SettlementError,
        settled_cash.CashSettlementError,
        smart_outreach.OutreachError,
    ) as error:
        print(f"INVALID: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
