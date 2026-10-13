from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable, Mapping

INPUT_SCHEMA = "outreach-cohort-attribution-input/v1"
PACKET_SCHEMA = "outreach-cohort-attribution-packet/v1"
RECEIPT_SCHEMA = "outreach-cohort-attribution-receipt/v1"

EVENT_TYPES = {
    "MUSE_SELECTED", "SENT", "BOUNCE", "ROUTE_RECOVERED", "HUMAN_REPLY",
    "QUALIFIED", "PROPOSED", "ACCEPTED", "INVOICED", "PAID", "REJECTED", "DNR",
}
MONEY_EVENT_TYPES = {"PROPOSED", "ACCEPTED", "INVOICED", "PAID"}
SINGLETON_EVENT_TYPES = {
    "BOUNCE", "ROUTE_RECOVERED", "QUALIFIED", "PROPOSED", "ACCEPTED",
    "INVOICED", "PAID", "REJECTED", "DNR",
}
DISPOSITIONS = {
    "UNDER_OBSERVED", "EXPAND_CAUTIOUSLY", "PAUSE_ROUTE_QUALITY",
    "PAUSE_CONVERSION", "HOLD_COLLISION_OR_DNR",
}
TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
CURRENCY_RE = re.compile(r"^[A-Z][A-Z0-9]{1,7}$")


class AttributionError(ValueError):
    pass


def _reject_float(token: str) -> None:
    raise AttributionError(f"floats/non-finite numbers are forbidden: {token}")


def _parse_int(token: str) -> int:
    digits = token[1:] if token.startswith("-") else token
    if len(digits) > 128:
        raise AttributionError("integer token too long")
    return int(token)


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise AttributionError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def strict_json_loads(raw: str) -> Any:
    if not isinstance(raw, str):
        raise AttributionError("JSON source must be text")
    try:
        return json.loads(raw, object_pairs_hook=_pairs, parse_float=_reject_float,
                          parse_int=_parse_int, parse_constant=_reject_float)
    except AttributionError:
        raise
    except (json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise AttributionError(f"invalid JSON: {exc}") from None


def canonical_json(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                          allow_nan=False) + "\n"
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise AttributionError(f"cannot canonicalize: {exc}") from None


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _expect_map(value: Any, where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise AttributionError(f"{where} must be an object")
    return value


def _expect_list(value: Any, where: str, *, max_items: int) -> list[Any]:
    if not isinstance(value, list) or len(value) > max_items:
        raise AttributionError(f"{where} must be an array of <= {max_items} items")
    return value


def _exact_keys(obj: Mapping[str, Any], expected: set[str], where: str) -> None:
    actual = set(obj)
    if actual != expected:
        raise AttributionError(
            f"{where} keys mismatch; missing={sorted(expected-actual)} extra={sorted(actual-expected)}"
        )


def _plain_str(value: Any, where: str, *, max_len: int) -> str:
    if not isinstance(value, str) or not value or len(value) > max_len:
        raise AttributionError(f"{where} must be non-empty text <= {max_len}")
    if any(ch in value for ch in ("\x00", "\r", "\n")):
        raise AttributionError(f"{where} must be one line without NUL")
    try:
        value.encode("utf-8", "strict")
    except UnicodeEncodeError:
        raise AttributionError(f"{where} must be Unicode scalar text") from None
    return value


def _token(value: Any, where: str) -> str:
    value = _plain_str(value, where, max_len=128)
    if not TOKEN_RE.fullmatch(value):
        raise AttributionError(f"{where} has invalid token characters")
    return value


def _int(value: Any, where: str, *, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise AttributionError(f"{where} must be an integer")
    if value < low or value > high:
        raise AttributionError(f"{where} out of range [{low}, {high}]")
    return value


def _timestamp(value: Any, where: str) -> tuple[str, datetime]:
    text = _plain_str(value, where, max_len=64)
    candidate = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        raise AttributionError(f"{where} must be ISO-8601") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise AttributionError(f"{where} must include timezone")
    return text, parsed.astimezone(timezone.utc)


def _refs(value: Any, where: str) -> list[str]:
    items = _expect_list(value, where, max_items=32)
    out: list[str] = []
    for i, ref in enumerate(items):
        ref = _plain_str(ref, f"{where}[{i}]", max_len=256)
        if ref in out:
            raise AttributionError(f"{where} contains duplicate evidence ref")
        out.append(ref)
    if not out:
        raise AttributionError(f"{where} must contain at least one evidence ref")
    return out


def _money(value: Any, where: str) -> dict[str, Any]:
    obj = _expect_map(value, where)
    _exact_keys(obj, {"amount_minor", "currency", "decimals"}, where)
    currency = _plain_str(obj["currency"], f"{where}.currency", max_len=8)
    if not CURRENCY_RE.fullmatch(currency):
        raise AttributionError(f"{where}.currency must be 2-8 uppercase letters/digits")
    return {
        "amount_minor": _int(obj["amount_minor"], f"{where}.amount_minor", low=1, high=10**18),
        "currency": currency,
        "decimals": _int(obj["decimals"], f"{where}.decimals", low=0, high=8),
    }


def _policy(value: Any) -> dict[str, int]:
    obj = _expect_map(value, "policy")
    _exact_keys(obj, {"observation_hours", "min_mature_sends", "expand_reply_rate_bp", "max_bounce_rate_bp"}, "policy")
    return {
        "observation_hours": _int(obj["observation_hours"], "policy.observation_hours", low=1, high=24 * 90),
        "min_mature_sends": _int(obj["min_mature_sends"], "policy.min_mature_sends", low=1, high=10000),
        "expand_reply_rate_bp": _int(obj["expand_reply_rate_bp"], "policy.expand_reply_rate_bp", low=0, high=10000),
        "max_bounce_rate_bp": _int(obj["max_bounce_rate_bp"], "policy.max_bounce_rate_bp", low=0, high=10000),
    }


def _event(raw: Any, where: str, *, previous_dt: datetime | None) -> tuple[dict[str, Any], datetime]:
    obj = _expect_map(raw, where)
    _exact_keys(obj, {"type", "at", "evidence_refs", "amount"}, where)
    event_type = _plain_str(obj["type"], f"{where}.type", max_len=32)
    if event_type not in EVENT_TYPES:
        raise AttributionError(f"{where}.type invalid")
    at_text, at_dt = _timestamp(obj["at"], f"{where}.at")
    if previous_dt is not None and at_dt < previous_dt:
        raise AttributionError(f"{where}.at reverses chronology")
    refs = _refs(obj["evidence_refs"], f"{where}.evidence_refs")
    if event_type in MONEY_EVENT_TYPES:
        if obj["amount"] is None:
            raise AttributionError(f"{where}.amount required for {event_type}")
        amount = _money(obj["amount"], f"{where}.amount")
    else:
        if obj["amount"] is not None:
            raise AttributionError(f"{where}.amount must be null for {event_type}")
        amount = None
    return {"type": event_type, "at": at_text, "evidence_refs": refs, "amount": amount}, at_dt


def _latest_index(events: list[dict[str, Any]], event_type: str) -> int | None:
    for i in range(len(events) - 1, -1, -1):
        if events[i]["type"] == event_type:
            return i
    return None


def _has_before(events: list[dict[str, Any]], event_type: str, index: int) -> bool:
    return any(event["type"] == event_type for event in events[:index])


def _validate_transitions(events: list[dict[str, Any]], where: str) -> None:
    counts: dict[str, int] = defaultdict(int)
    last_sent_index: int | None = None
    last_muse_index: int | None = None
    last_reply_index: int | None = None
    for i, event in enumerate(events):
        typ = event["type"]
        counts[typ] += 1
        if typ in SINGLETON_EVENT_TYPES and counts[typ] > 1:
            raise AttributionError(f"{where} contains duplicate singleton event {typ}")
        if typ == "MUSE_SELECTED":
            last_muse_index = i
        elif typ == "SENT":
            if last_muse_index is None or (last_sent_index is not None and last_muse_index <= last_sent_index):
                raise AttributionError(f"{where} SENT requires a fresh preceding MUSE_SELECTED")
            if last_sent_index is not None and (last_reply_index is None or last_reply_index <= last_sent_index):
                raise AttributionError(f"{where} repeat SENT requires HUMAN_REPLY after the previous SENT")
            last_sent_index = i
        elif typ == "BOUNCE":
            if last_sent_index is None:
                raise AttributionError(f"{where} BOUNCE requires prior SENT")
        elif typ == "ROUTE_RECOVERED":
            if not (_has_before(events, "BOUNCE", i) or _has_before(events, "DNR", i)):
                raise AttributionError(f"{where} ROUTE_RECOVERED requires prior BOUNCE or DNR")
        elif typ == "HUMAN_REPLY":
            if last_sent_index is None:
                raise AttributionError(f"{where} HUMAN_REPLY requires prior SENT")
            last_reply_index = i
        elif typ == "QUALIFIED":
            if last_reply_index is None:
                raise AttributionError(f"{where} QUALIFIED requires prior HUMAN_REPLY")
        elif typ == "PROPOSED":
            if last_sent_index is None:
                raise AttributionError(f"{where} PROPOSED requires prior SENT")
        elif typ == "ACCEPTED":
            if not _has_before(events, "PROPOSED", i) or last_reply_index is None:
                raise AttributionError(f"{where} ACCEPTED requires prior PROPOSED and HUMAN_REPLY")
        elif typ == "INVOICED":
            if not _has_before(events, "ACCEPTED", i):
                raise AttributionError(f"{where} INVOICED requires prior ACCEPTED")
        elif typ == "PAID":
            if not _has_before(events, "INVOICED", i):
                raise AttributionError(f"{where} PAID requires prior INVOICED")
        elif typ == "REJECTED":
            if last_reply_index is None:
                raise AttributionError(f"{where} REJECTED requires prior HUMAN_REPLY")
        elif typ == "DNR":
            if last_sent_index is None:
                raise AttributionError(f"{where} DNR requires prior SENT")


def _money_event(events: list[dict[str, Any]], typ: str) -> dict[str, Any] | None:
    for event in events:
        if event["type"] == typ:
            return event["amount"]
    return None


def _validate_money_chain(events: list[dict[str, Any]], where: str) -> None:
    money = {typ: _money_event(events, typ) for typ in MONEY_EVENT_TYPES}
    present = [m for m in money.values() if m is not None]
    if not present:
        return
    currencies = {m["currency"] for m in present}
    decimals = {(m["currency"], m["decimals"]) for m in present}
    if len(currencies) != 1 or len(decimals) != 1:
        raise AttributionError(f"{where} money events must preserve one native currency/decimals")
    proposed, accepted, invoiced, paid = money["PROPOSED"], money["ACCEPTED"], money["INVOICED"], money["PAID"]
    if proposed and accepted and accepted["amount_minor"] > proposed["amount_minor"]:
        raise AttributionError(f"{where} accepted amount cannot exceed proposed amount")
    if accepted and invoiced and invoiced["amount_minor"] > accepted["amount_minor"]:
        raise AttributionError(f"{where} invoiced amount cannot exceed accepted amount")
    if invoiced and paid and paid["amount_minor"] > invoiced["amount_minor"]:
        raise AttributionError(f"{where} paid amount cannot exceed invoiced amount")


def _campaign(raw: Any, where: str, *, as_of_dt: datetime, observation_hours: int) -> dict[str, Any]:
    obj = _expect_map(raw, where)
    _exact_keys(obj, {"campaign_id", "offer_id", "segment", "target_org", "route", "purpose", "events"}, where)
    campaign_id = _token(obj["campaign_id"], f"{where}.campaign_id")
    offer_id = _token(obj["offer_id"], f"{where}.offer_id")
    segment = _token(obj["segment"], f"{where}.segment")
    target_org = _plain_str(obj["target_org"], f"{where}.target_org", max_len=160)
    route = _plain_str(obj["route"], f"{where}.route", max_len=256)
    purpose = _token(obj["purpose"], f"{where}.purpose")
    raw_events = _expect_list(obj["events"], f"{where}.events", max_items=64)
    if not raw_events:
        raise AttributionError(f"{where}.events cannot be empty")
    events: list[dict[str, Any]] = []
    event_dts: list[datetime] = []
    previous_dt: datetime | None = None
    for i, raw_event in enumerate(raw_events):
        event, dt = _event(raw_event, f"{where}.events[{i}]", previous_dt=previous_dt)
        events.append(event)
        event_dts.append(dt)
        previous_dt = dt
    if event_dts[-1] > as_of_dt:
        raise AttributionError(f"{where} has event after as_of")
    _validate_transitions(events, where)
    _validate_money_chain(events, where)

    sent_indices = [i for i, e in enumerate(events) if e["type"] == "SENT"]
    sent_count = len(sent_indices)
    sent = sent_count > 0
    last_sent_index = sent_indices[-1] if sent else None
    last_sent_dt = event_dts[last_sent_index] if last_sent_index is not None else None
    human_reply_index = _latest_index(events, "HUMAN_REPLY")
    bounce_index = _latest_index(events, "BOUNCE")
    route_recovered_index = _latest_index(events, "ROUTE_RECOVERED")
    dnr_index = _latest_index(events, "DNR")
    human_reply = human_reply_index is not None
    ever_bounced = bounce_index is not None
    active_bounce = bounce_index is not None and (route_recovered_index is None or route_recovered_index < bounce_index)
    latest_clear_index = max([i for i in (human_reply_index, route_recovered_index) if i is not None], default=-1)
    dnr_active = dnr_index is not None and dnr_index > latest_clear_index
    hold_contact = active_bounce or dnr_active
    terminal_response = human_reply or _latest_index(events, "REJECTED") is not None
    age_hours = None
    if sent and last_sent_dt is not None:
        age_seconds = int((as_of_dt - last_sent_dt).total_seconds())
        if age_seconds < 0:
            raise AttributionError(f"{where} SENT occurs after as_of")
        age_hours = age_seconds // 3600
    mature = bool(sent and (terminal_response or ever_bounced or (age_hours or 0) >= observation_hours))
    pending = bool(sent and not mature)
    return {
        "campaign_id": campaign_id,
        "offer_id": offer_id,
        "segment": segment,
        "target_org": target_org,
        "route": route,
        "purpose": purpose,
        "events": events,
        "summary": {
            "sent_count": sent_count,
            "mature": mature,
            "pending": pending,
            "ever_bounced": ever_bounced,
            "active_bounce": active_bounce,
            "human_reply": human_reply,
            "qualified": _latest_index(events, "QUALIFIED") is not None,
            "proposed": _latest_index(events, "PROPOSED") is not None,
            "accepted": _latest_index(events, "ACCEPTED") is not None,
            "invoiced": _latest_index(events, "INVOICED") is not None,
            "paid": _latest_index(events, "PAID") is not None,
            "rejected": _latest_index(events, "REJECTED") is not None,
            "dnr_active": dnr_active,
            "next_contact_disposition": "HOLD_COLLISION_OR_DNR" if hold_contact else "OWNER_REVIEW_ONLY",
            "age_hours_since_last_send": age_hours,
        },
    }


def _rate_bp(numerator: int, denominator: int) -> int | None:
    if denominator <= 0:
        return None
    return numerator * 10000 // denominator


def _add_money(totals: dict[str, dict[str, int]], money: Mapping[str, Any] | None, stage: str,
               decimals_by_currency: dict[str, int]) -> None:
    if money is None:
        return
    currency = str(money["currency"])
    decimals = int(money["decimals"])
    prior = decimals_by_currency.get(currency)
    if prior is not None and prior != decimals:
        raise AttributionError(f"currency {currency} has inconsistent decimals")
    decimals_by_currency[currency] = decimals
    bucket = totals.setdefault(currency, {"decimals": decimals, "proposed_minor": 0,
                                          "accepted_minor": 0, "invoiced_minor": 0, "paid_minor": 0})
    bucket[f"{stage.lower()}_minor"] += int(money["amount_minor"])


def _cohort(key: tuple[str, str], campaigns: list[dict[str, Any]], *, policy: Mapping[str, int]) -> dict[str, Any]:
    offer_id, segment = key
    sent_campaigns = [c for c in campaigns if c["summary"]["sent_count"] > 0]
    mature = [c for c in sent_campaigns if c["summary"]["mature"]]
    pending = [c for c in sent_campaigns if c["summary"]["pending"]]
    bounced = [c for c in sent_campaigns if c["summary"]["ever_bounced"]]
    # A retained human reply demonstrates delivery even if the campaign also
    # has bounce history. Every reply counted below must share this denominator.
    delivered_mature = [c for c in mature
                        if not c["summary"]["ever_bounced"] or c["summary"]["human_reply"]]
    human_reply = [c for c in campaigns if c["summary"]["human_reply"]]
    qualified = [c for c in campaigns if c["summary"]["qualified"]]
    proposed = [c for c in campaigns if c["summary"]["proposed"]]
    accepted = [c for c in campaigns if c["summary"]["accepted"]]
    invoiced = [c for c in campaigns if c["summary"]["invoiced"]]
    paid = [c for c in campaigns if c["summary"]["paid"]]
    held = [c for c in sent_campaigns if c["summary"]["next_contact_disposition"] == "HOLD_COLLISION_OR_DNR"]
    totals: dict[str, dict[str, int]] = {}
    decimals_by_currency: dict[str, int] = {}
    for campaign in campaigns:
        for typ in MONEY_EVENT_TYPES:
            _add_money(totals, _money_event(campaign["events"], typ), typ, decimals_by_currency)
    sent_count = len(sent_campaigns)
    mature_count = len(mature)
    bounce_rate = _rate_bp(len(bounced), sent_count)
    reply_rate = _rate_bp(len(human_reply), len(delivered_mature))
    accept_rate = _rate_bp(len(accepted), len(human_reply))
    paid_rate = _rate_bp(len(paid), len(accepted))
    if sent_count > 0 and len(held) == sent_count:
        disposition = "HOLD_COLLISION_OR_DNR"
    elif mature_count < policy["min_mature_sends"]:
        disposition = "UNDER_OBSERVED"
    elif bounce_rate is not None and bounce_rate > policy["max_bounce_rate_bp"]:
        disposition = "PAUSE_ROUTE_QUALITY"
    elif reply_rate is not None and reply_rate >= policy["expand_reply_rate_bp"]:
        disposition = "EXPAND_CAUTIOUSLY"
    else:
        disposition = "PAUSE_CONVERSION"
    return {
        "offer_id": offer_id, "segment": segment, "campaign_count": len(campaigns),
        "sent_targets": sent_count, "mature_targets": mature_count,
        "delivered_mature_targets": len(delivered_mature), "pending_targets": len(pending),
        "bounced_targets": len(bounced), "human_reply_targets": len(human_reply),
        "qualified_targets": len(qualified), "proposed_targets": len(proposed),
        "accepted_targets": len(accepted), "invoiced_targets": len(invoiced),
        "paid_targets": len(paid), "held_contact_targets": len(held),
        "reply_rate_bp": reply_rate, "bounce_rate_bp": bounce_rate,
        "accept_rate_bp": accept_rate, "paid_rate_bp": paid_rate,
        "money_by_currency": {k: totals[k] for k in sorted(totals)},
        "disposition": disposition,
    }


def _validate_unique_keys(campaigns: Iterable[Mapping[str, Any]]) -> None:
    ids: set[str] = set()
    route_keys: dict[tuple[str, str, str], str] = {}
    for campaign in campaigns:
        cid = str(campaign["campaign_id"])
        if cid in ids:
            raise AttributionError(f"duplicate campaign_id: {cid}")
        ids.add(cid)
        key = (str(campaign["target_org"]).casefold(), str(campaign["route"]).casefold(),
               str(campaign["purpose"]).casefold())
        if key in route_keys:
            raise AttributionError(f"duplicate target×route×purpose ledger: {route_keys[key]} and {cid}")
        route_keys[key] = cid


def compile_attribution(payload: Any) -> dict[str, Any]:
    obj = _expect_map(payload, "input")
    _exact_keys(obj, {"schema", "as_of", "policy", "campaigns"}, "input")
    if obj["schema"] != INPUT_SCHEMA:
        raise AttributionError("input.schema invalid")
    as_of_text, as_of_dt = _timestamp(obj["as_of"], "input.as_of")
    policy = _policy(obj["policy"])
    raw_campaigns = _expect_list(obj["campaigns"], "input.campaigns", max_items=10000)
    campaigns = [_campaign(raw, f"input.campaigns[{i}]", as_of_dt=as_of_dt,
                           observation_hours=policy["observation_hours"])
                 for i, raw in enumerate(raw_campaigns)]
    _validate_unique_keys(campaigns)
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for campaign in campaigns:
        grouped[(campaign["offer_id"], campaign["segment"])].append(campaign)
    cohorts = [_cohort(key, sorted(items, key=lambda c: c["campaign_id"]), policy=policy)
               for key, items in sorted(grouped.items())]
    packet: dict[str, Any] = {
        "schema": PACKET_SCHEMA,
        "as_of": as_of_text,
        "policy": policy,
        "campaigns": sorted(campaigns, key=lambda c: c["campaign_id"]),
        "cohorts": cohorts,
        "authority": {
            "external_send_authorized": False,
            "muse_selection_granted": False,
            "pricing_commitment_authorized": False,
            "buyer_acceptance_claimed": False,
            "invoice_creation_authorized": False,
            "payment_mutation_authorized": False,
            "revenue_recognition_authorized": False,
            "automatic_scaling_authorized": False,
        },
    }
    packet["receipt"] = {"schema": RECEIPT_SCHEMA, "sha256": _sha256_text(canonical_json(packet)),
                         "verified_by_recompile": True}
    return packet


def verify_attribution(payload: Any, packet: Any) -> bool:
    try:
        expected = compile_attribution(payload)
        actual = _expect_map(packet, "packet")
        return canonical_json(actual) == canonical_json(expected)
    except AttributionError:
        return False


def _load_json_file(path: str) -> Any:
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise AttributionError(f"cannot read {path}: {exc}") from None
    return strict_json_loads(raw)


def _write_json_file(path: str, value: Any) -> None:
    try:
        Path(path).write_text(canonical_json(value), encoding="utf-8")
    except OSError as exc:
        raise AttributionError(f"cannot write {path}: {exc}") from None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compile/verify evidence-bound outreach cohort attribution packets")
    sub = parser.add_subparsers(dest="command", required=True)
    cp = sub.add_parser("compile"); cp.add_argument("input_json"); cp.add_argument("output_json")
    vp = sub.add_parser("verify"); vp.add_argument("input_json"); vp.add_argument("packet_json")
    args = parser.parse_args(argv)
    try:
        payload = _load_json_file(args.input_json)
        if args.command == "compile":
            _write_json_file(args.output_json, compile_attribution(payload)); return 0
        return 0 if verify_attribution(payload, _load_json_file(args.packet_json)) else 2
    except AttributionError as exc:
        parser.error(str(exc)); return 2


if __name__ == "__main__":
    raise SystemExit(main())
