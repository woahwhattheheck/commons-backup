#!/usr/bin/env python3
"""Reduce immutable revenue receipts into a fail-closed proof ledger."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

INPUT_SCHEMA = "commons-revenue-proof-input/v2"
OUTPUT_SCHEMA = "commons-revenue-proof-ledger/v2"
AUTH = {"unknown": 0, "partial": 1, "complete": 2}
DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
CURRENCY = re.compile(r"[A-Z][A-Z0-9]{2,7}\Z")
AMOUNT = re.compile(r"(?:0|[1-9][0-9]*)(?:\.[0-9]{1,18})?\Z")
IDENT = re.compile(r"[^\s]{1,300}\Z")
COMMON = {"kind", "opportunity_id", "source", "authority", "evidence_digest"}
FIELDS = {
    "opportunity": {"currency", "expected_amount", "identity_status"},
    "lookup": {"scope", "snapshot_id", "observed_at", "inventory_ids", "inventory_digest"},
    "delivery": {"delivery_id", "state", "current", "currency", "earned_amount", "credit"},
    "settlement": {"delivery_id", "settlement_id", "movement", "state", "currency", "amount"},
}


class InputError(ValueError):
    pass


def _obj(v: Any, w: str) -> dict[str, Any]:
    if not isinstance(v, dict):
        raise InputError(f"{w} must be an object")
    return v


def _id(v: Any, w: str) -> str:
    if not isinstance(v, str) or not IDENT.fullmatch(v):
        raise InputError(f"{w} must be a non-whitespace identifier")
    return v


def _enum(v: Any, allowed: set[str] | Mapping[str, int], w: str) -> str:
    if v not in allowed:
        raise InputError(f"{w} is unsupported")
    return str(v)


def _digest(v: Any, w: str) -> str:
    if not isinstance(v, str) or not DIGEST.fullmatch(v):
        raise InputError(f"{w} must be lowercase sha256:<64 hex>")
    return v


def _currency(v: Any, w: str) -> str:
    if not isinstance(v, str) or not CURRENCY.fullmatch(v):
        raise InputError(f"{w} must be an uppercase currency code")
    return v


def _amount(v: Any, w: str, *, positive: bool = False) -> Decimal:
    if not isinstance(v, str) or not AMOUNT.fullmatch(v):
        raise InputError(f"{w} must be a plain non-negative decimal string")
    try:
        d = Decimal(v)
    except InvalidOperation as exc:
        raise InputError(f"{w} is not a decimal") from exc
    if not d.is_finite() or d < 0 or (positive and d == 0):
        raise InputError(f"{w} has invalid value")
    return d


def _timestamp(v: Any, w: str) -> datetime:
    raw = _id(v, w)
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        stamp = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise InputError(f"{w} must be ISO-8601") from exc
    if stamp.tzinfo is None:
        raise InputError(f"{w} must include timezone")
    return stamp.astimezone(timezone.utc)


def _iso(stamp: datetime) -> str:
    return stamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _fmt(d: Decimal) -> str:
    if d == 0:
        return "0"
    s = format(d.normalize(), "f")
    return s.rstrip("0").rstrip(".") if "." in s else s


def _amin(values: Iterable[str]) -> str:
    rows = list(values)
    return min(rows, key=lambda x: AUTH[x]) if rows else "unknown"


def _credit(v: Any, w: str) -> dict[str, set[str]]:
    raw = {} if v is None else _obj(v, w)
    keys = {"source_authors", "reviewers", "mergers"}
    extra = sorted(set(raw) - keys)
    if extra:
        raise InputError(f"{w} has unknown fields: {', '.join(extra)}")
    out: dict[str, set[str]] = {}
    for key in keys:
        rows = raw.get(key, [])
        if not isinstance(rows, list) or any(not isinstance(x, str) or not x.strip() for x in rows):
            raise InputError(f"{w}.{key} must be an array of non-empty strings")
        out[key] = set(rows)
    return out


def _base(opp_id: str) -> dict[str, Any]:
    return {"id": opp_id, "currency": None, "expected": None, "evidence": set(), "auth": [], "issues": set()}


def inventory_digest(scope: str, snapshot_id: str, observed_at: str, inventory_ids: Sequence[str]) -> str:
    """Digest one complete lookup snapshot's identity and exact inventory."""
    canonical_ids = sorted(inventory_ids)
    canonical_observed_at = _iso(_timestamp(observed_at, "observed_at"))
    payload = {
        "scope": scope,
        "snapshot_id": snapshot_id,
        "observed_at": canonical_observed_at,
        "inventory_ids": canonical_ids,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _parse_lookup(r: Mapping[str, Any], w: str, authority: str, evidence_digest: str) -> dict[str, Any]:
    scope = _enum(r.get("scope"), {"delivery", "settlement"}, f"{w}.scope")
    snapshot_id = _id(r.get("snapshot_id"), f"{w}.snapshot_id")
    stamp = _timestamp(r.get("observed_at"), f"{w}.observed_at")
    stamp_iso = _iso(stamp)
    raw_ids = r.get("inventory_ids")
    if not isinstance(raw_ids, list):
        raise InputError(f"{w}.inventory_ids must be an array")
    ids = [_id(v, f"{w}.inventory_ids[{i}]") for i, v in enumerate(raw_ids)]
    if len(ids) != len(set(ids)):
        raise InputError(f"{w}.inventory_ids must not contain duplicates")
    claimed_inventory_digest = _digest(r.get("inventory_digest"), f"{w}.inventory_digest")
    computed_inventory_digest = inventory_digest(scope, snapshot_id, stamp_iso, ids)
    if claimed_inventory_digest != computed_inventory_digest:
        raise InputError(f"{w}.inventory_digest mismatch")
    return {
        "scope": scope,
        "snapshot_id": snapshot_id,
        "observed_at": stamp,
        "observed_at_iso": stamp_iso,
        "inventory_ids": frozenset(ids),
        "inventory_digest": claimed_inventory_digest,
        "authority": authority,
        "evidence_digest": evidence_digest,
    }


def _effective_lookup(rows: Sequence[Mapping[str, Any]], scope: str, issues: set[str]) -> tuple[str, Mapping[str, Any] | None]:
    if not rows:
        issues.add(f"{scope}_lookup_missing")
        return "unknown", None
    latest_at = max(row["observed_at"] for row in rows)
    latest = [row for row in rows if row["observed_at"] == latest_at]
    signatures = {
        (row["snapshot_id"], row["inventory_digest"], row["inventory_ids"])
        for row in latest
    }
    if len(signatures) != 1:
        issues.add(f"{scope}_lookup_snapshot_conflict")
        return "unknown", None
    return _amin(str(row["authority"]) for row in latest), latest[0]


def reduce_ledger(payload: dict[str, Any]) -> dict[str, Any]:
    payload = _obj(payload, "input")
    extra_root = sorted(set(payload) - {"schema", "receipts"})
    if extra_root:
        raise InputError(f"input has unknown fields: {', '.join(extra_root)}")
    if payload.get("schema") != INPUT_SCHEMA:
        raise InputError(f"schema must be {INPUT_SCHEMA}")
    receipts = payload.get("receipts")
    if not isinstance(receipts, list):
        raise InputError("receipts must be an array")

    opps: dict[str, dict[str, Any]] = {}
    deliveries: dict[str, dict[str, Any]] = {}
    settlements: dict[str, dict[str, Any]] = {}
    lookups: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    lookup_evidence: dict[str, set[str]] = defaultdict(set)

    for i, raw in enumerate(receipts):
        r = _obj(raw, f"receipts[{i}]")
        kind = r.get("kind")
        if kind not in FIELDS:
            raise InputError(f"receipts[{i}].kind is unsupported")
        extra = sorted(set(r) - (COMMON | FIELDS[kind]))
        if extra:
            raise InputError(f"receipts[{i}] has unknown fields: {', '.join(extra)}")
        w = f"receipts[{i}]"
        oid = _id(r.get("opportunity_id"), f"{w}.opportunity_id")
        _id(r.get("source"), f"{w}.source")
        authority = _enum(r.get("authority"), AUTH, f"{w}.authority")
        evidence_digest = _digest(r.get("evidence_digest"), f"{w}.evidence_digest")
        opp = opps.setdefault(oid, _base(oid))
        opp["evidence"].add(evidence_digest)

        if kind == "lookup":
            lookup = _parse_lookup(r, w, authority, evidence_digest)
            lookups[oid][lookup["scope"]].append(lookup)
            lookup_evidence[oid].add(evidence_digest)
            continue

        opp["auth"].append(authority)
        if kind == "opportunity":
            identity = _enum(r.get("identity_status"), {"canonical", "ambiguous"}, f"{w}.identity_status")
            if identity == "ambiguous":
                opp["issues"].add("opportunity_identity_ambiguous")
            currency = _currency(r.get("currency"), f"{w}.currency")
            expected = _amount(r.get("expected_amount"), f"{w}.expected_amount")
            if opp["currency"] is None:
                opp["currency"], opp["expected"] = currency, expected
            elif opp["currency"] != currency:
                opp["issues"].add("opportunity_currency_mismatch")
            elif opp["expected"] != expected:
                opp["issues"].add("opportunity_amount_mismatch")
            continue

        if kind == "delivery":
            did = _id(r.get("delivery_id"), f"{w}.delivery_id")
            state = _enum(r.get("state"), {"delivered", "accepted", "rejected", "superseded"}, f"{w}.state")
            current = r.get("current")
            if type(current) is not bool:
                raise InputError(f"{w}.current must be a JSON boolean")
            currency = _currency(r.get("currency"), f"{w}.currency")
            earned_raw = r.get("earned_amount")
            earned = _amount(earned_raw, f"{w}.earned_amount", positive=True) if state == "accepted" else Decimal(0)
            if state != "accepted" and earned_raw is not None and _amount(earned_raw, f"{w}.earned_amount") != 0:
                opp["issues"].add(f"nonaccepted_delivery_has_earned_amount:{did}")
            credits = _credit(r.get("credit"), f"{w}.credit")
            semantic = (oid, state, current, currency, earned)
            prev = deliveries.get(did)
            if prev is None:
                deliveries[did] = {
                    "id": did, "oid": oid, "state": state, "current": current,
                    "currency": currency, "earned": earned, "semantic": semantic,
                    "evidence": {evidence_digest}, "auth": [authority], **credits,
                }
            elif prev["semantic"] != semantic:
                opp["issues"].add(f"delivery_identity_conflict:{did}")
                prev["evidence"].add(evidence_digest)
                prev["auth"].append(authority)
            else:
                prev["evidence"].add(evidence_digest)
                prev["auth"].append(authority)
                for key in ("source_authors", "reviewers", "mergers"):
                    prev[key].update(credits[key])
            continue

        sid = _id(r.get("settlement_id"), f"{w}.settlement_id")
        did = _id(r.get("delivery_id"), f"{w}.delivery_id")
        movement = _enum(r.get("movement"), {"payment", "refund", "reversal", "dispute"}, f"{w}.movement")
        state = _enum(r.get("state"), {"settled", "pending", "failed"}, f"{w}.state")
        currency = _currency(r.get("currency"), f"{w}.currency")
        amount = _amount(r.get("amount"), f"{w}.amount", positive=True)
        semantic = (oid, did, movement, state, currency, amount)
        prev = settlements.get(sid)
        if prev is None:
            settlements[sid] = {
                "id": sid, "oid": oid, "did": did, "movement": movement,
                "state": state, "currency": currency, "amount": amount,
                "semantic": semantic, "evidence": {evidence_digest}, "auth": [authority],
            }
        elif prev["semantic"] != semantic:
            for affected in {prev["oid"], oid}:
                opps.setdefault(affected, _base(affected))["issues"].add(f"settlement_id_reused:{sid}")
            prev["evidence"].add(evidence_digest)
            prev["auth"].append(authority)
        else:
            prev["evidence"].add(evidence_digest)
            prev["auth"].append(authority)

    d_by_opp: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for d in deliveries.values():
        d_by_opp[d["oid"]].append(d)
        opp = opps.setdefault(d["oid"], _base(d["oid"]))
        opp["evidence"].update(d["evidence"])
        opp["auth"].extend(d["auth"])
    s_by_opp: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for s in settlements.values():
        s_by_opp[s["oid"]].append(s)
        opp = opps.setdefault(s["oid"], _base(s["oid"]))
        opp["evidence"].update(s["evidence"])
        opp["auth"].extend(s["auth"])

    rows: list[dict[str, Any]] = []
    totals: dict[str, dict[str, Decimal]] = defaultdict(lambda: {
        "pipeline_expected": Decimal(0), "earned_unsettled": Decimal(0),
        "cash_settled": Decimal(0), "reversed_or_disputed": Decimal(0),
    })
    for oid in sorted(opps):
        opp = opps[oid]
        issues = set(opp["issues"])
        evidence = set(opp["evidence"]) | lookup_evidence[oid]
        currency = opp["currency"]
        expected = opp["expected"] or Decimal(0)
        if "opportunity_currency_mismatch" in issues:
            currency = "UNKNOWN"
        if "opportunity_amount_mismatch" in issues:
            expected = Decimal(0)
        if currency is None or opp["expected"] is None:
            issues.add("canonical_opportunity_terms_missing")
            currency = currency or "UNKNOWN"

        delivery_lookup_auth, delivery_lookup = _effective_lookup(lookups[oid]["delivery"], "delivery", issues)
        settlement_lookup_auth, settlement_lookup = _effective_lookup(lookups[oid]["settlement"], "settlement", issues)

        ds = sorted(d_by_opp.get(oid, []), key=lambda x: x["id"])
        actual_delivery_ids = {d["id"] for d in ds}
        if delivery_lookup_auth == "complete" and delivery_lookup is not None:
            if set(delivery_lookup["inventory_ids"]) != actual_delivery_ids:
                issues.add("delivery_lookup_inventory_mismatch")

        active = [d for d in ds if d["state"] == "accepted" and d["current"]]
        if len(active) > 1:
            issues.add("ambiguous_current_accepted_delivery")
        current = active[0] if len(active) == 1 else None
        earned = current["earned"] if current else Decimal(0)
        credit = {"source_authors": set(), "reviewers": set(), "mergers": set()}
        for d in ds:
            evidence.update(d["evidence"])
            for key in credit:
                credit[key].update(d[key])
            if currency != "UNKNOWN" and d["currency"] != currency:
                issues.add(f"delivery_currency_mismatch:{d['id']}")
        if current and expected and earned > expected:
            issues.add("earned_amount_exceeds_pipeline_expected")

        gross = Decimal(0)
        reversed_amt = Decimal(0)
        settlement_ids: list[str] = []
        ss = sorted(s_by_opp.get(oid, []), key=lambda x: x["id"])
        actual_settlement_ids = {s["id"] for s in ss}
        if settlement_lookup_auth == "complete" and settlement_lookup is not None:
            if set(settlement_lookup["inventory_ids"]) != actual_settlement_ids:
                issues.add("settlement_lookup_inventory_mismatch")
        for s in ss:
            evidence.update(s["evidence"])
            settlement_ids.append(s["id"])
            if currency != "UNKNOWN" and s["currency"] != currency:
                issues.add(f"settlement_currency_mismatch:{s['id']}")
            d = deliveries.get(s["did"])
            if d is None or d["oid"] != oid:
                issues.add(f"settlement_delivery_missing:{s['id']}")
            elif current is None or d["id"] != current["id"]:
                issues.add(f"settlement_on_noncurrent_delivery:{s['id']}")
            if s["state"] == "settled":
                if s["movement"] == "payment":
                    gross += s["amount"]
                else:
                    reversed_amt += s["amount"]

        observed = gross - reversed_amt
        if observed < 0:
            issues.add("reversals_exceed_settled_payments")
        if earned and observed > earned:
            issues.add("settled_cash_exceeds_earned_amount")
        raw_auth = _amin([*opp["auth"], delivery_lookup_auth, settlement_lookup_auth])
        authority = "unknown" if issues else raw_auth
        cash = max(observed, Decimal(0)) if authority == "complete" and current else Decimal(0)
        unsettled = max(earned - cash, Decimal(0))
        snapshots = {}
        for scope, lookup in (("delivery", delivery_lookup), ("settlement", settlement_lookup)):
            snapshots[scope] = None if lookup is None else {
                "snapshot_id": lookup["snapshot_id"],
                "observed_at": lookup["observed_at_iso"],
                "inventory_digest": lookup["inventory_digest"],
                "inventory_count": len(lookup["inventory_ids"]),
            }
        row = {
            "opportunity_id": oid, "delivery_id": current["id"] if current else None,
            "currency": currency, "pipeline_expected": _fmt(expected),
            "earned_unsettled": _fmt(unsettled), "cash_settled": _fmt(cash),
            "reversed_or_disputed": _fmt(reversed_amt),
            "observed_settled_payments": _fmt(gross), "observed_net_cash": _fmt(observed),
            "authority": authority,
            "lookup_authority": {"delivery": delivery_lookup_auth, "settlement": settlement_lookup_auth},
            "lookup_snapshots": snapshots,
            "issues": sorted(issues), "evidence_digests": sorted(evidence),
            "settlement_ids": settlement_ids,
            "credit_lineage": {key: sorted(value) for key, value in credit.items()},
        }
        rows.append(row)
        if currency != "UNKNOWN":
            bucket = totals[currency]
            bucket["pipeline_expected"] += expected
            bucket["earned_unsettled"] += unsettled
            bucket["cash_settled"] += cash
            bucket["reversed_or_disputed"] += reversed_amt

    output: dict[str, Any] = {
        "schema": OUTPUT_SCHEMA,
        "authority": _amin(row["authority"] for row in rows),
        "currency_totals": {
            cur: {k: _fmt(v) for k, v in sorted(bucket.items())}
            for cur, bucket in sorted(totals.items())
        },
        "opportunities": rows,
        "issues": sorted({issue for row in rows for issue in row["issues"]}),
    }
    canonical = json.dumps(output, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    output["ledger_digest"] = "sha256:" + hashlib.sha256(canonical).hexdigest()
    return output


def render_summary(ledger: dict[str, Any]) -> str:
    if ledger.get("schema") != OUTPUT_SCHEMA:
        raise InputError(f"ledger schema must be {OUTPUT_SCHEMA}")
    lines = [
        "# Revenue proof ledger", "", f"Authority: **{ledger['authority']}**  ",
        f"Ledger digest: `{ledger['ledger_digest']}`", "",
        "| Opportunity | Delivery | Currency | Pipeline expected | Earned unsettled | Cash settled | Reversed/disputed | Authority |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in ledger["opportunities"]:
        delivery_id = row["delivery_id"] or "—"
        lines.append(
            f"| {row['opportunity_id']} | {delivery_id} | {row['currency']} | {row['pipeline_expected']} | "
            f"{row['earned_unsettled']} | {row['cash_settled']} | {row['reversed_or_disputed']} | {row['authority']} |"
        )
        if row["issues"]:
            lines.append(f"\nIssues for `{row['opportunity_id']}`: " + ", ".join(f"`{x}`" for x in row["issues"]))
        for scope, snap in row.get("lookup_snapshots", {}).items():
            if snap is not None:
                lines.append(
                    f"\n{scope.title()} lookup snapshot for `{row['opportunity_id']}`: "
                    f"`{snap['snapshot_id']}` at `{snap['observed_at']}`; "
                    f"{snap['inventory_count']} IDs; `{snap['inventory_digest']}`"
                )
    lines += ["", "## Currency totals", ""]
    for cur, bucket in sorted(ledger["currency_totals"].items()):
        lines.append(
            f"- **{cur}** — pipeline {bucket['pipeline_expected']}; earned unsettled {bucket['earned_unsettled']}; "
            f"cash settled {bucket['cash_settled']}; reversed/disputed {bucket['reversed_or_disputed']}"
        )
    return "\n".join(lines).rstrip() + "\n"


def _read(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise InputError(f"cannot read input: {exc}") from exc
    if len(raw) > 16 * 1024 * 1024:
        raise InputError("input exceeds 16 MiB")
    try:
        return _obj(
            json.loads(
                raw.decode("utf-8", "strict"),
                parse_constant=lambda x: (_ for _ in ()).throw(InputError(f"non-standard JSON constant: {x}")),
            ),
            "input",
        )
    except UnicodeDecodeError as exc:
        raise InputError("input is not valid UTF-8") from exc
    except json.JSONDecodeError as exc:
        raise InputError(f"invalid JSON: {exc}") from exc


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    try:
        data = memoryview(text.encode())
        while data:
            n = os.write(fd, data)
            if n <= 0:
                raise OSError("short write")
            data = data[n:]
        os.fsync(fd)
    finally:
        os.close(fd)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--json-out", type=Path, required=True)
    parser.add_argument("--summary-out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        ledger = reduce_ledger(_read(args.input))
        _write(args.json_out, json.dumps(ledger, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
        _write(args.summary_out, render_summary(ledger))
    except (InputError, OSError) as exc:
        parser.exit(2, f"revenue_proof_ledger: {exc}\n")
    return 0 if ledger["authority"] == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
