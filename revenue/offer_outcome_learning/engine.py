from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal, ROUND_FLOOR, localcontext
from typing import Any, Mapping

INPUT_SCHEMA = "commons.offer-outcome-learning/input-v1"
PACKAGE_SCHEMA = "commons.offer-outcome-learning/package-v1"
CURRENT_MAX_AGE_SECONDS = 900
SAFE_INT_MAX = 9_007_199_254_740_991
ID_RE = re.compile(r"^[a-z0-9][a-z0-9._:-]{0,127}$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
POSITIVE = ("SENT", "HUMAN_REPLY", "QUALIFIED", "PILOT_ACCEPTED", "PAYMENT_REPORTED", "PAYMENT_CONFIRMED")
RANK = {v: i for i, v in enumerate(POSITIVE)}
TERMINAL = {"LOST", "DNR"}
CAMPAIGN_KEYS = {"campaign_id", "org_id", "offer_id", "proof_id", "price_band_id", "proposed_minor", "currency", "created_at", "source_ref", "source_sha256"}
EVENT_REQUIRED = {"event_id", "campaign_id", "stage", "occurred_at", "source_ref", "source_sha256"}
EVENT_OPTIONAL = {"amount_minor", "settlement_ref", "settlement_sha256"}


class LearningError(ValueError):
    pass


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise LearningError(f"DUPLICATE_JSON_KEY:{key}")
        out[key] = value
    return out


def loads_strict(text: str) -> Any:
    try:
        return json.loads(text, object_pairs_hook=_pairs)
    except LearningError:
        raise
    except json.JSONDecodeError as exc:
        raise LearningError(f"INVALID_JSON:{exc.msg}") from exc


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def _freeze(value: Any) -> Any:
    try:
        return loads_strict(canonical_json(value))
    except (TypeError, ValueError) as exc:
        raise LearningError("NON_JSON_INPUT") from exc


def _obj(value: Any, where: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise LearningError(f"EXPECTED_OBJECT:{where}")
    return value


def _keys(row: Mapping[str, Any], required: set[str], optional: set[str], where: str) -> None:
    missing, extra = required - set(row), set(row) - required - optional
    if missing:
        raise LearningError(f"MISSING_KEYS:{where}:{','.join(sorted(missing))}")
    if extra:
        raise LearningError(f"UNKNOWN_KEYS:{where}:{','.join(sorted(extra))}")


def _ident(value: Any, where: str) -> str:
    if type(value) is not str or not ID_RE.fullmatch(value):
        raise LearningError(f"INVALID_ID:{where}")
    return value


def _sha(value: Any, where: str) -> str:
    if type(value) is not str or not SHA_RE.fullmatch(value):
        raise LearningError(f"INVALID_SHA256:{where}")
    return value


def _money(value: Any, where: str, minimum: int = 0) -> int:
    if type(value) is not int or not minimum <= value <= SAFE_INT_MAX:
        raise LearningError(f"INVALID_INTEGER:{where}")
    return value


def _utc(value: Any, where: str) -> datetime:
    if type(value) is not str or not value.endswith("Z"):
        raise LearningError(f"INVALID_UTC:{where}")
    try:
        dt = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise LearningError(f"INVALID_UTC:{where}") from exc
    if dt.tzinfo != timezone.utc or dt.microsecond or value != dt.strftime("%Y-%m-%dT%H:%M:%SZ"):
        raise LearningError(f"NONCANONICAL_UTC:{where}")
    return dt


def _fmt(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _claim_digest(owner: dict[str, tuple[str, str]], digest: str, kind: str, ref: str) -> None:
    prior = owner.get(digest)
    current = (kind, ref)
    if prior is not None and prior != current:
        raise LearningError(f"SOURCE_DIGEST_ALIAS:{digest}")
    owner[digest] = current


def _normalize(raw: Any, at: datetime) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    top = _obj(_freeze(raw), "input")
    _keys(top, {"schema", "currency", "campaigns", "events"}, set(), "input")
    if top["schema"] != INPUT_SCHEMA:
        raise LearningError("UNSUPPORTED_INPUT_SCHEMA")
    currency = top["currency"]
    if type(currency) is not str or not CURRENCY_RE.fullmatch(currency):
        raise LearningError("INVALID_CURRENCY:input.currency")
    if type(top["campaigns"]) is not list or not top["campaigns"] or len(top["campaigns"]) > 50_000:
        raise LearningError("INVALID_CAMPAIGNS")
    if type(top["events"]) is not list or len(top["events"]) > 250_000:
        raise LearningError("INVALID_EVENTS")

    campaigns: list[dict[str, Any]] = []
    by_campaign: dict[str, dict[str, Any]] = {}
    source_refs: dict[str, str] = {}
    settlement_refs: dict[str, str] = {}
    digest_owner: dict[str, tuple[str, str]] = {}
    for i, raw_row in enumerate(top["campaigns"]):
        row = _obj(raw_row, f"campaigns[{i}]")
        _keys(row, CAMPAIGN_KEYS, set(), f"campaigns[{i}]")
        cid = _ident(row["campaign_id"], f"campaigns[{i}].campaign_id")
        if cid in by_campaign:
            raise LearningError(f"DUPLICATE_CAMPAIGN_ID:{cid}")
        created = _utc(row["created_at"], f"campaigns[{i}].created_at")
        if created > at:
            raise LearningError(f"CAMPAIGN_FROM_FUTURE:{cid}")
        if row["currency"] != currency:
            raise LearningError(f"CURRENCY_MISMATCH:{cid}")
        ref = _ident(row["source_ref"], f"campaigns[{i}].source_ref")
        digest = _sha(row["source_sha256"], f"campaigns[{i}].source_sha256")
        if ref in source_refs and source_refs[ref] != digest:
            raise LearningError(f"SOURCE_REF_DIGEST_CONFLICT:{ref}")
        source_refs[ref] = digest
        _claim_digest(digest_owner, digest, "campaign", cid)
        c = {
            "campaign_id": cid,
            "org_id": _ident(row["org_id"], f"campaigns[{i}].org_id"),
            "offer_id": _ident(row["offer_id"], f"campaigns[{i}].offer_id"),
            "proof_id": _ident(row["proof_id"], f"campaigns[{i}].proof_id"),
            "price_band_id": _ident(row["price_band_id"], f"campaigns[{i}].price_band_id"),
            "proposed_minor": _money(row["proposed_minor"], f"campaigns[{i}].proposed_minor", 1),
            "currency": currency, "created_at": _fmt(created), "source_ref": ref, "source_sha256": digest,
        }
        campaigns.append(c); by_campaign[cid] = c

    unique_events: dict[str, dict[str, Any]] = {}
    for i, raw_row in enumerate(top["events"]):
        row = _obj(raw_row, f"events[{i}]")
        _keys(row, EVENT_REQUIRED, EVENT_OPTIONAL, f"events[{i}]")
        eid = _ident(row["event_id"], f"events[{i}].event_id")
        prior = unique_events.get(eid)
        if prior is not None:
            if canonical_json(prior) != canonical_json(row):
                raise LearningError(f"EVENT_ID_CONFLICT:{eid}")
            continue
        unique_events[eid] = row

    events: list[dict[str, Any]] = []
    stages: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    terminal: dict[str, dict[str, Any]] = {}
    for eid, row in sorted(unique_events.items()):
        cid = _ident(row["campaign_id"], f"event:{eid}.campaign_id")
        c = by_campaign.get(cid)
        if c is None:
            raise LearningError(f"UNKNOWN_CAMPAIGN:{cid}")
        stage = row["stage"]
        if type(stage) is not str or stage not in set(POSITIVE) | TERMINAL:
            raise LearningError(f"INVALID_STAGE:{eid}")
        occurred = _utc(row["occurred_at"], f"event:{eid}.occurred_at")
        if occurred < _utc(c["created_at"], "created"):
            raise LearningError(f"EVENT_BEFORE_CAMPAIGN:{eid}")
        if occurred > at:
            raise LearningError(f"EVENT_FROM_FUTURE:{eid}")
        ref = _ident(row["source_ref"], f"event:{eid}.source_ref")
        digest = _sha(row["source_sha256"], f"event:{eid}.source_sha256")
        if ref in source_refs and source_refs[ref] != digest:
            raise LearningError(f"SOURCE_REF_DIGEST_CONFLICT:{ref}")
        source_refs[ref] = digest; _claim_digest(digest_owner, digest, "event", eid)
        e = {"event_id": eid, "campaign_id": cid, "stage": stage, "occurred_at": _fmt(occurred), "source_ref": ref, "source_sha256": digest}
        amount = row.get("amount_minor")
        if stage in {"PILOT_ACCEPTED", "PAYMENT_REPORTED", "PAYMENT_CONFIRMED"}:
            e["amount_minor"] = _money(amount, f"event:{eid}.amount_minor", 1)
        elif amount is not None:
            raise LearningError(f"UNEXPECTED_AMOUNT:{eid}")
        if stage == "PAYMENT_CONFIRMED":
            sref = _ident(row.get("settlement_ref"), f"event:{eid}.settlement_ref")
            ssha = _sha(row.get("settlement_sha256"), f"event:{eid}.settlement_sha256")
            if sref in settlement_refs and settlement_refs[sref] != ssha:
                raise LearningError(f"SETTLEMENT_REF_DIGEST_CONFLICT:{sref}")
            settlement_refs[sref] = ssha
            _claim_digest(digest_owner, ssha, "settlement", eid)
            e.update(settlement_ref=sref, settlement_sha256=ssha)
        elif row.get("settlement_ref") is not None or row.get("settlement_sha256") is not None:
            raise LearningError(f"UNEXPECTED_SETTLEMENT_EVIDENCE:{eid}")
        if stage in TERMINAL:
            if cid in terminal:
                raise LearningError(f"MULTIPLE_TERMINAL_EVENTS:{cid}")
            terminal[cid] = e
        else:
            if stage in stages[cid]:
                raise LearningError(f"DUPLICATE_STAGE:{cid}:{stage}")
            stages[cid][stage] = e
        events.append(e)

    required = {
        "HUMAN_REPLY": ("SENT",), "QUALIFIED": ("SENT", "HUMAN_REPLY"),
        "PILOT_ACCEPTED": ("SENT", "HUMAN_REPLY", "QUALIFIED"),
        "PAYMENT_REPORTED": ("SENT", "HUMAN_REPLY", "QUALIFIED", "PILOT_ACCEPTED"),
        "PAYMENT_CONFIRMED": ("SENT", "HUMAN_REPLY", "QUALIFIED", "PILOT_ACCEPTED"),
    }
    for c in campaigns:
        cid, smap = c["campaign_id"], stages[c["campaign_id"]]
        if "SENT" not in smap:
            raise LearningError(f"MISSING_SENT:{cid}")
        for stage, preds in required.items():
            if stage in smap:
                for pred in preds:
                    if pred not in smap:
                        raise LearningError(f"STAGE_PREDECESSOR_MISSING:{cid}:{stage}:{pred}")
        ordered = sorted((RANK[s], _utc(e["occurred_at"], "event"), s) for s, e in smap.items())
        for (_, t0, s0), (_, t1, s1) in zip(ordered, ordered[1:]):
            if t1 < t0:
                raise LearningError(f"STAGE_CHRONOLOGY:{cid}:{s0}:{s1}")
        accepted, reported, confirmed = smap.get("PILOT_ACCEPTED"), smap.get("PAYMENT_REPORTED"), smap.get("PAYMENT_CONFIRMED")
        if reported and reported["amount_minor"] > accepted["amount_minor"]:
            raise LearningError(f"REPORTED_PAYMENT_EXCEEDS_ACCEPTED:{cid}")
        if confirmed and confirmed["amount_minor"] > accepted["amount_minor"]:
            raise LearningError(f"CONFIRMED_PAYMENT_EXCEEDS_ACCEPTED:{cid}")
        if reported and confirmed and reported["amount_minor"] != confirmed["amount_minor"]:
            raise LearningError(f"PAYMENT_REPORT_CONFIRM_MISMATCH:{cid}")
        if cid in terminal:
            terminal_at = _utc(terminal[cid]["occurred_at"], "terminal")
            for e in smap.values():
                if _utc(e["occurred_at"], "event") > terminal_at:
                    raise LearningError(f"EVENT_AFTER_TERMINAL:{cid}:{e['stage']}")

    campaigns.sort(key=lambda x: x["campaign_id"])
    events.sort(key=lambda x: (x["campaign_id"], x["occurred_at"], x["stage"], x["event_id"]))
    return currency, campaigns, events


def _wilson(success: int, total: int) -> int:
    if not total:
        return 0
    with localcontext() as ctx:
        ctx.prec = 40
        n, z = Decimal(total), Decimal("1.96")
        p, z2 = Decimal(success) / n, z * z
        lower = (p + z2/(2*n) - z*((p*(1-p)/n)+(z2/(4*n*n))).sqrt()) / (1 + z2/n)
        return max(0, int((lower * 10_000).to_integral_value(rounding=ROUND_FLOOR)))


def _bps(num: int, den: int) -> int:
    return (num * 10_000) // den if den else 0


def _payload(raw: Any, at: datetime, mode: str) -> dict[str, Any]:
    currency, campaigns, events = _normalize(raw, at)
    evs: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for e in events: evs[e["campaign_id"]].append(e)
    projections = []
    for c in campaigns:
        smap = {e["stage"]: e for e in evs[c["campaign_id"]] if e["stage"] not in TERMINAL}
        terminal = next((e for e in evs[c["campaign_id"]] if e["stage"] in TERMINAL), None)
        projections.append({**{k: c[k] for k in ("campaign_id", "org_id", "offer_id", "proof_id", "price_band_id", "proposed_minor")},
            "accepted_minor": smap.get("PILOT_ACCEPTED", {}).get("amount_minor", 0),
            "reported_payment_minor": smap.get("PAYMENT_REPORTED", {}).get("amount_minor", 0),
            "confirmed_payment_minor": smap.get("PAYMENT_CONFIRMED", {}).get("amount_minor", 0),
            "reply": "HUMAN_REPLY" in smap, "qualified": "QUALIFIED" in smap, "accepted": "PILOT_ACCEPTED" in smap,
            "reported": "PAYMENT_REPORTED" in smap, "paid": "PAYMENT_CONFIRMED" in smap, "terminal": terminal["stage"] if terminal else None})
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for p in projections: grouped[(p["offer_id"], p["proof_id"], p["price_band_id"])].append(p)
    cohorts = []
    for (offer, proof, band), rows in sorted(grouped.items()):
        n, orgs = len(rows), {r["org_id"] for r in rows}
        paid = [r for r in rows if r["paid"]]
        paid_org_counts = Counter(r["org_id"] for r in paid)
        paid_money = Counter()
        for r in paid: paid_money[r["org_id"]] += r["confirmed_payment_minor"]
        paid_minor = sum(paid_money.values())
        dominant = max(((v*10_000)//paid_minor for v in paid_money.values()), default=0)
        lower = _wilson(len(paid), n)
        if n < 5 or len(orgs) < 3: state = "INSUFFICIENT_EVIDENCE"
        elif not paid: state = "OBSERVED_NO_CONFIRMED_PAYMENT_SIGNAL"
        elif len(paid_org_counts) < 2 or dominant > 6000: state = "OBSERVED_SIGNAL_CONCENTRATED"
        elif lower >= 500: state = "OWNER_REVIEW_OBSERVED_SIGNAL"
        else: state = "OBSERVED_SIGNAL_WEAK"
        cohorts.append({"offer_id": offer, "proof_id": proof, "price_band_id": band, "campaigns": n, "unique_orgs": len(orgs),
            "reply_count": sum(r["reply"] for r in rows), "qualified_count": sum(r["qualified"] for r in rows),
            "accepted_count": sum(r["accepted"] for r in rows), "payment_report_count": sum(r["reported"] for r in rows),
            "payment_confirmed_count": len(paid), "paid_orgs": len(paid_org_counts), "proposed_minor": sum(r["proposed_minor"] for r in rows),
            "accepted_minor": sum(r["accepted_minor"] for r in rows), "reported_payment_minor": sum(r["reported_payment_minor"] for r in rows),
            "confirmed_payment_minor": paid_minor, "reply_rate_bps": _bps(sum(r["reply"] for r in rows), n),
            "qualified_rate_bps": _bps(sum(r["qualified"] for r in rows), n), "accepted_rate_bps": _bps(sum(r["accepted"] for r in rows), n),
            "confirmed_payment_rate_bps": _bps(len(paid), n), "confirmed_payment_wilson95_lower_bps": lower,
            "dominant_paid_org_share_bps": dominant, "leave_one_org_out_confirmed_count_floor": max(0, len(paid)-max(paid_org_counts.values(), default=0)),
            "evidence_state": state})
    priority = {"OWNER_REVIEW_OBSERVED_SIGNAL":0, "OBSERVED_SIGNAL_WEAK":1, "OBSERVED_SIGNAL_CONCENTRATED":2, "OBSERVED_NO_CONFIRMED_PAYMENT_SIGNAL":3, "INSUFFICIENT_EVIDENCE":4}
    actions = {"OWNER_REVIEW_OBSERVED_SIGNAL":"OWNER_REVIEW_FOR_TARGETING_STRATEGY", "OBSERVED_SIGNAL_WEAK":"GATHER_MORE_EVIDENCE_BEFORE_STRATEGY_CHANGE",
        "OBSERVED_SIGNAL_CONCENTRATED":"DIVERSIFY_EVIDENCE_BEFORE_GENERALIZING", "OBSERVED_NO_CONFIRMED_PAYMENT_SIGNAL":"OWNER_REVIEW_NO_CONFIRMED_PAYMENT_SIGNAL",
        "INSUFFICIENT_EVIDENCE":"GATHER_MORE_EVIDENCE"}
    queue = [{"offer_id":c["offer_id"], "proof_id":c["proof_id"], "price_band_id":c["price_band_id"], "evidence_state":c["evidence_state"], "owner_action":actions[c["evidence_state"]]}
        for c in sorted(cohorts, key=lambda c:(priority[c["evidence_state"]], -c["confirmed_payment_wilson95_lower_bps"], -c["paid_orgs"], -c["payment_confirmed_count"], c["offer_id"], c["proof_id"], c["price_band_id"]))]
    normalized = {"schema": INPUT_SCHEMA, "currency": currency, "campaigns": campaigns, "events": events}
    return {"schema": PACKAGE_SCHEMA, "mode": mode, "evaluated_at": _fmt(at), "currency": currency, "input_sha256": sha256_json(normalized),
        "campaign_count": len(campaigns), "event_count": len(events), "cohorts": cohorts, "strategy_queue": queue,
        "measurement_contract": {"causal_claim": False, "payment_report_is_cash": False, "payment_confirmed_requires_settlement_evidence": True,
            "denominators_exposed": True, "concentration_guard": "LEAVE_ONE_ORG_OUT_AND_DOMINANT_PAID_SHARE"},
        "authority": {"scope":"INTERNAL_STRATEGY_MEASUREMENT_ONLY", "external_send_authorized":False, "outreach_lease_authorized":False,
            "customer_contact_authorized":False, "pricing_change_authorized":False, "acceptance_authorized":False, "payment_authorized":False,
            "revenue_recognition_authorized":False}}


def compile_historical(raw: Any, evaluated_at: str) -> dict[str, Any]:
    payload = _payload(raw, _utc(evaluated_at, "evaluated_at"), "HISTORICAL")
    return {"payload": payload, "receipt_sha256": sha256_json(payload)}


def compile_current(raw: Any) -> dict[str, Any]:
    payload = _payload(raw, _utc_now(), "CURRENT")
    return {"payload": payload, "receipt_sha256": sha256_json(payload)}


def verify_package(raw: Any, package: Any, *, now: str | None = None) -> dict[str, Any]:
    pkg = _obj(_freeze(package), "package")
    _keys(pkg, {"payload", "receipt_sha256"}, set(), "package")
    payload = _obj(pkg["payload"], "package.payload")
    receipt = _sha(pkg["receipt_sha256"], "package.receipt_sha256")
    if payload.get("schema") != PACKAGE_SCHEMA: raise LearningError("UNSUPPORTED_PACKAGE_SCHEMA")
    if sha256_json(payload) != receipt: raise LearningError("PACKAGE_RECEIPT_MISMATCH")
    at, mode = _utc(payload.get("evaluated_at"), "package.evaluated_at"), payload.get("mode")
    if mode not in {"CURRENT", "HISTORICAL"}: raise LearningError("INVALID_PACKAGE_MODE")
    rebuilt = _payload(raw, at, mode)
    if payload.get("input_sha256") != rebuilt["input_sha256"]: raise LearningError("PACKAGE_INPUT_MISMATCH")
    if canonical_json(payload) != canonical_json(rebuilt): raise LearningError("PACKAGE_SEMANTIC_MISMATCH")
    if mode == "CURRENT":
        if now is not None:
            raise LearningError("CURRENT_PACKAGE_STALE:CALLER_CLOCK_OVERRIDE_FORBIDDEN")
        current = _utc_now()
        if at > current: raise LearningError("PACKAGE_FROM_FUTURE")
        if (current-at).total_seconds() > CURRENT_MAX_AGE_SECONDS: raise LearningError("CURRENT_PACKAGE_STALE")
    return {"valid": True, "mode": mode, "evaluated_at": _fmt(at), "receipt_sha256": receipt, "external_send_authorized": False}


def render_markdown(package: Mapping[str, Any]) -> str:
    pkg = _obj(_freeze(package), "package"); p = _obj(pkg.get("payload"), "package.payload")
    lines = ["# Offer Outcome Learning", "", f"Evaluation: `{p['evaluated_at']}` ({p['mode']})", f"Currency: `{p['currency']}`",
        f"Campaigns: **{p['campaign_count']}** · Evidence events: **{p['event_count']}**", "",
        "> Observational measurement only. This packet does not authorize outreach, pricing, acceptance, payment, or revenue recognition and makes no causal claim.", "",
        "## Cohorts", "", "| Offer | Proof | Price band | Campaigns | Paid | Paid orgs | Paid rate | Wilson 95% lower | Concentration | Evidence state |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---|"]
    for c in p["cohorts"]:
        lines.append(f"| `{c['offer_id']}` | `{c['proof_id']}` | `{c['price_band_id']}` | {c['campaigns']} | {c['payment_confirmed_count']} | {c['paid_orgs']} | {c['confirmed_payment_rate_bps']/100:.2f}% | {c['confirmed_payment_wilson95_lower_bps']/100:.2f}% | {c['dominant_paid_org_share_bps']/100:.2f}% | `{c['evidence_state']}` |")
    lines += ["", "## Owner strategy queue", ""]
    for q in p["strategy_queue"]:
        lines.append(f"- `{q['offer_id']}` / `{q['proof_id']}` / `{q['price_band_id']}` — **{q['evidence_state']}** → `{q['owner_action']}`")
    lines += ["", f"Receipt: `{pkg['receipt_sha256']}`", ""]
    return "\n".join(lines)