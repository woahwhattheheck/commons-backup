from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Any

SCHEMA = "TJL_REVENUE_FUNNEL_V1"
BUNDLE_SCHEMA = "TJL_REVENUE_FUNNEL_BUNDLE_V1"
AUTHORITY = MappingProxyType({
    "external_send": False,
    "muse_selection": False,
    "provider_mutation": False,
    "invoice_creation": False,
    "payment_movement": False,
    "receivable_establishment": False,
    "revenue_recognition": False,
})
LANES = frozenset({"OUTREACH", "BOUNTY", "COMPETITION", "CONTRACT", "PRODUCT", "OTHER"})
EVENT_KINDS = frozenset({
    "QUALIFIED", "PROPOSAL_SENT", "CLAIM_SUBMITTED", "ACCEPTED", "MERGED",
    "AWARDED", "INVOICE_ISSUED", "PAYMENT_RECEIVED", "OUTBOUND_SENT",
    "INBOUND_RECEIVED", "MUSE_CLEAR", "DNR", "COLLISION_HOLD",
})
SOURCE_CLASSES = frozenset({
    "PROVIDER_RECEIPT", "BUYER_MESSAGE", "SPONSOR_MESSAGE", "GITHUB", "SLACK", "INTERNAL_RETAINED",
})


class FunnelError(ValueError):
    pass


def _make_core():
    schema = "TJL_REVENUE_FUNNEL_V1"
    bundle_schema = "TJL_REVENUE_FUNNEL_BUNDLE_V1"
    authority_items = (
        ("external_send", False),
        ("muse_selection", False),
        ("provider_mutation", False),
        ("invoice_creation", False),
        ("payment_movement", False),
        ("receivable_establishment", False),
        ("revenue_recognition", False),
    )
    lanes = frozenset({"OUTREACH", "BOUNTY", "COMPETITION", "CONTRACT", "PRODUCT", "OTHER"})
    event_kinds = frozenset({
        "QUALIFIED", "PROPOSAL_SENT", "CLAIM_SUBMITTED", "ACCEPTED", "MERGED",
        "AWARDED", "INVOICE_ISSUED", "PAYMENT_RECEIVED", "OUTBOUND_SENT",
        "INBOUND_RECEIVED", "MUSE_CLEAR", "DNR", "COLLISION_HOLD",
    })
    source_classes = frozenset({
        "PROVIDER_RECEIPT", "BUYER_MESSAGE", "SPONSOR_MESSAGE", "GITHUB", "SLACK", "INTERNAL_RETAINED",
    })
    opportunity_keys = frozenset({"id", "title", "lane", "currency", "reference_amount_cents", "events"})
    event_keys = frozenset({"id", "kind", "observed_at", "source_class", "ref", "sha256", "amount_cents"})
    document_keys = frozenset({"schema", "evaluation_at", "micro_batch_threshold_cents", "opportunities"})

    json_mod = json
    hash_mod = hashlib
    os_mod = os
    stat_mod = stat
    datetime_cls = datetime
    timezone_utc = timezone.utc
    error_cls = FunnelError

    def authority() -> dict[str, bool]:
        return dict(authority_items)

    def exact_dict(value: Any, keys: frozenset[str], where: str) -> dict[str, Any]:
        if type(value) is not dict:
            raise error_cls(f"{where}: expected exact object")
        if any(type(key) is not str for key in value):
            raise error_cls(f"{where}: string keys required")
        if set(value) != keys:
            missing = sorted(keys - set(value))
            extra = sorted(set(value) - keys)
            raise error_cls(f"{where}: exact keys required; missing={missing}; extra={extra}")
        return value

    def canonical(value: Any) -> bytes:
        try:
            text = json_mod.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
                sort_keys=True,
            )
            return text.encode("utf-8", "strict")
        except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
            raise error_cls(f"not canonical JSON: {exc}") from exc

    def digest(value: Any) -> str:
        return hash_mod.sha256(canonical(value)).hexdigest()

    def parse_time(value: Any, where: str) -> datetime:
        if type(value) is not str or not value.endswith("Z") or "." in value:
            raise error_cls(f"{where}: exact whole-second UTC RFC3339 Z required")
        try:
            return datetime_cls.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone_utc)
        except ValueError as exc:
            raise error_cls(f"{where}: invalid timestamp") from exc

    def bounded_text(value: Any, where: str, *, maximum: int = 512) -> str:
        if type(value) is not str or not value or len(value) > maximum:
            raise error_cls(f"{where}: bounded nonempty string required")
        if any(ord(ch) < 32 for ch in value):
            raise error_cls(f"{where}: control characters forbidden")
        return value

    def sha256_text(value: Any, where: str) -> str:
        value = bounded_text(value, where, maximum=64)
        if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
            raise error_cls(f"{where}: lowercase sha256 required")
        return value

    def money(value: Any, where: str, *, optional: bool = False) -> int | None:
        if optional and value is None:
            return None
        if type(value) is not int or value < 0 or value > 10**15:
            raise error_cls(f"{where}: bounded nonnegative integer cents required")
        return value

    def latest(events: list[dict[str, Any]], kind: str) -> dict[str, Any] | None:
        matches = [event for event in events if event["kind"] == kind]
        return matches[-1] if matches else None

    def latest_amount(events: list[dict[str, Any]], kinds: frozenset[str]) -> tuple[int | None, str]:
        matches = [event for event in events if event["kind"] in kinds and event["amount_cents"] is not None]
        if not matches:
            return None, "UNKNOWN"
        latest_at = matches[-1]["observed_at"]
        latest_matches = [event for event in matches if event["observed_at"] == latest_at]
        claims = {(event["kind"], event["amount_cents"]) for event in latest_matches}
        if len(claims) > 1:
            raise error_cls(f"ambiguous same-time settlement claims at {latest_at}")
        ((kind, amount),) = tuple(claims)
        return amount, kind

    def settlement_target(events: list[dict[str, Any]], reference_amount: int | None) -> tuple[int | None, str]:
        for kinds in (
            frozenset({"INVOICE_ISSUED"}),
            frozenset({"AWARDED"}),
            frozenset({"PROPOSAL_SENT", "CLAIM_SUBMITTED"}),
        ):
            amount, source = latest_amount(events, kinds)
            if amount is not None:
                return amount, source
        if reference_amount is not None:
            return reference_amount, "REFERENCE_AMOUNT"
        return None, "UNKNOWN"

    def stage_for(kinds: set[str], paid_total: int, target: int | None) -> str:
        if paid_total:
            if target is None:
                return "PAYMENT_RECORDED_TARGET_UNKNOWN"
            if paid_total < target:
                return "PARTIALLY_PAID"
            if paid_total == target:
                return "PAID"
            return "OVERPAID_RECONCILE"
        if "INVOICE_ISSUED" in kinds or "AWARDED" in kinds:
            return "INVOICED_OR_AWARDED"
        if "ACCEPTED" in kinds or "MERGED" in kinds:
            return "ACCEPTED_OR_MERGED"
        if "PROPOSAL_SENT" in kinds or "CLAIM_SUBMITTED" in kinds:
            return "PROPOSED_OR_CLAIMED"
        if "QUALIFIED" in kinds:
            return "QUALIFIED"
        return "DISCOVERED"

    def next_action(stage: str, events: list[dict[str, Any]]) -> str:
        last_dnr = latest(events, "DNR")
        last_inbound = latest(events, "INBOUND_RECEIVED")
        last_outbound = latest(events, "OUTBOUND_SENT")
        last_collision = latest(events, "COLLISION_HOLD")
        last_muse = latest(events, "MUSE_CLEAR")
        if last_inbound and (not last_outbound or last_inbound["observed_at"] > last_outbound["observed_at"]):
            return "RESPOND_TO_NEW_INBOUND"
        if last_dnr and (not last_inbound or last_dnr["observed_at"] >= last_inbound["observed_at"]):
            return "INBOUND_ONLY_DNR"
        if last_collision and (not last_muse or last_collision["observed_at"] >= last_muse["observed_at"]):
            return "HOLD_COLLISION"
        if stage == "PAID":
            return "DONE_PAID"
        if stage == "OVERPAID_RECONCILE":
            return "RECONCILE_OVERPAYMENT"
        if stage in {"PARTIALLY_PAID", "PAYMENT_RECORDED_TARGET_UNKNOWN"}:
            return "RECONCILE_PAYMENT_STATE"
        if stage in {"INVOICED_OR_AWARDED", "ACCEPTED_OR_MERGED"}:
            return "COLLECTION_REVIEW"
        if stage == "PROPOSED_OR_CLAIMED":
            return "ADVANCE_ACCEPTANCE"
        if stage == "QUALIFIED":
            if last_muse and (not last_outbound or last_muse["observed_at"] > last_outbound["observed_at"]):
                return "OWNER_OUTBOUND_REVIEW"
            return "MUSE_REQUIRED_BEFORE_OUTBOUND"
        return "QUALIFY"

    def validate_event(raw: Any, opportunity_id: str, evaluation_at: datetime) -> dict[str, Any]:
        event = exact_dict(raw, event_keys, f"{opportunity_id}.event")
        event_id = bounded_text(event["id"], f"{opportunity_id}.event.id", maximum=120)
        kind = bounded_text(event["kind"], f"{event_id}.kind", maximum=40)
        if kind not in event_kinds:
            raise error_cls(f"{event_id}.kind: unsupported")
        observed = parse_time(event["observed_at"], f"{event_id}.observed_at")
        if observed > evaluation_at:
            raise error_cls(f"{event_id}: future evidence")
        source_class = bounded_text(event["source_class"], f"{event_id}.source_class", maximum=40)
        if source_class not in source_classes:
            raise error_cls(f"{event_id}.source_class: unsupported")
        ref = bounded_text(event["ref"], f"{event_id}.ref", maximum=512)
        sha = sha256_text(event["sha256"], f"{event_id}.sha256")
        amount = money(event["amount_cents"], f"{event_id}.amount_cents", optional=True)
        if kind == "PAYMENT_RECEIVED":
            if amount is None or amount <= 0:
                raise error_cls(f"{event_id}: payment needs positive amount")
            if source_class != "PROVIDER_RECEIPT":
                raise error_cls(f"{event_id}: payment requires PROVIDER_RECEIPT retained evidence")
        elif amount is not None and kind not in {"AWARDED", "INVOICE_ISSUED", "PROPOSAL_SENT", "CLAIM_SUBMITTED"}:
            raise error_cls(f"{event_id}: amount not allowed for {kind}")
        return {
            "id": event_id,
            "kind": kind,
            "observed_at": observed.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "source_class": source_class,
            "ref": ref,
            "sha256": sha,
            "amount_cents": amount,
        }

    def has_at_or_before(events: list[dict[str, Any]], current: dict[str, Any], kinds: frozenset[str]) -> bool:
        return any(event["kind"] in kinds and event["observed_at"] <= current["observed_at"] for event in events)

    def compile_opportunity(raw: Any, evaluation_at: datetime, threshold: int) -> dict[str, Any]:
        opportunity = exact_dict(raw, opportunity_keys, "opportunity")
        opportunity_id = bounded_text(opportunity["id"], "opportunity.id", maximum=120)
        title = bounded_text(opportunity["title"], f"{opportunity_id}.title", maximum=240)
        lane = bounded_text(opportunity["lane"], f"{opportunity_id}.lane", maximum=40)
        if lane not in lanes:
            raise error_cls(f"{opportunity_id}.lane: unsupported")
        currency = bounded_text(opportunity["currency"], f"{opportunity_id}.currency", maximum=8)
        if not (3 <= len(currency) <= 8 and currency.upper() == currency and currency.isalpha()):
            raise error_cls(f"{opportunity_id}.currency: uppercase alphabetic currency/unit required")
        reference_amount = money(opportunity["reference_amount_cents"], f"{opportunity_id}.reference_amount_cents", optional=True)
        if type(opportunity["events"]) is not list:
            raise error_cls(f"{opportunity_id}.events: array required")
        events = [validate_event(event, opportunity_id, evaluation_at) for event in opportunity["events"]]
        ids = [event["id"] for event in events]
        if len(ids) != len(set(ids)):
            raise error_cls(f"{opportunity_id}: duplicate event id")
        bindings = [(event["source_class"], event["ref"], event["sha256"]) for event in events]
        if len(bindings) != len(set(bindings)):
            raise error_cls(f"{opportunity_id}: duplicate retained evidence binding")
        events.sort(key=lambda event: (event["observed_at"], event["id"]))
        kinds = {event["kind"] for event in events}

        commercial = {"PROPOSAL_SENT", "CLAIM_SUBMITTED", "ACCEPTED", "MERGED", "AWARDED", "INVOICE_ISSUED", "PAYMENT_RECEIVED"}
        if kinds & commercial and "QUALIFIED" not in kinds:
            raise error_cls(f"{opportunity_id}: commercial progress requires QUALIFIED evidence")
        if kinds & {"ACCEPTED", "MERGED", "AWARDED", "INVOICE_ISSUED", "PAYMENT_RECEIVED"} and not kinds & {"PROPOSAL_SENT", "CLAIM_SUBMITTED"}:
            raise error_cls(f"{opportunity_id}: acceptance/settlement path requires proposal or claim evidence")
        if kinds & {"AWARDED", "INVOICE_ISSUED", "PAYMENT_RECEIVED"} and not kinds & {"ACCEPTED", "MERGED"}:
            raise error_cls(f"{opportunity_id}: award/invoice/payment requires accepted or merged evidence")
        if "PAYMENT_RECEIVED" in kinds and not kinds & {"AWARDED", "INVOICE_ISSUED"}:
            raise error_cls(f"{opportunity_id}: payment requires award or invoice evidence")

        for event in events:
            kind = event["kind"]
            if kind in {"PROPOSAL_SENT", "CLAIM_SUBMITTED"} and not has_at_or_before(events, event, frozenset({"QUALIFIED"})):
                raise error_cls(f"{opportunity_id}: {kind} predates qualification")
            if kind in {"ACCEPTED", "MERGED"} and not has_at_or_before(events, event, frozenset({"PROPOSAL_SENT", "CLAIM_SUBMITTED"})):
                raise error_cls(f"{opportunity_id}: {kind} predates proposal/claim")
            if kind in {"AWARDED", "INVOICE_ISSUED"} and not has_at_or_before(events, event, frozenset({"ACCEPTED", "MERGED"})):
                raise error_cls(f"{opportunity_id}: {kind} predates accepted/merged evidence")
            if kind == "PAYMENT_RECEIVED" and not has_at_or_before(events, event, frozenset({"AWARDED", "INVOICE_ISSUED"})):
                raise error_cls(f"{opportunity_id}: payment predates award/invoice")

        payment_total = sum(event["amount_cents"] or 0 for event in events if event["kind"] == "PAYMENT_RECEIVED")
        target, target_source = settlement_target(events, reference_amount)
        stage = stage_for(kinds, payment_total, target)
        action = next_action(stage, events)
        if target == 0 and stage in {"ACCEPTED_OR_MERGED", "INVOICED_OR_AWARDED"} and action == "COLLECTION_REVIEW":
            action = "DONE_ZERO_VALUE"
        economic_gap = stage in {
            "ACCEPTED_OR_MERGED", "INVOICED_OR_AWARDED", "PARTIALLY_PAID",
            "PAYMENT_RECORDED_TARGET_UNKNOWN", "OVERPAID_RECONCILE",
        }
        if target == 0 and stage in {"ACCEPTED_OR_MERGED", "INVOICED_OR_AWARDED"}:
            economic_gap = False
        micro_batch = bool(
            economic_gap and target is not None and target <= threshold
            and action in {"COLLECTION_REVIEW", "RECONCILE_PAYMENT_STATE", "RECONCILE_OVERPAYMENT"}
        )
        return {
            "id": opportunity_id,
            "title": title,
            "lane": lane,
            "currency": currency,
            "reference_amount_cents": reference_amount,
            "settlement_target_cents": target,
            "settlement_target_source": target_source,
            "events": events,
            "stage": stage,
            "next_action": action,
            "payment_received_cents": payment_total,
            "economically_unfinished": economic_gap,
            "micro_batch_candidate": micro_batch,
            "evidence_root_sha256": digest(events),
        }

    def compile_portfolio(document: Any) -> dict[str, Any]:
        doc = exact_dict(document, document_keys, "document")
        if doc["schema"] != schema:
            raise error_cls("document.schema: unsupported")
        evaluation_at = parse_time(doc["evaluation_at"], "document.evaluation_at")
        threshold = money(doc["micro_batch_threshold_cents"], "document.micro_batch_threshold_cents")
        if type(doc["opportunities"]) is not list:
            raise error_cls("document.opportunities: array required")
        opportunities = [compile_opportunity(opportunity, evaluation_at, threshold) for opportunity in doc["opportunities"]]
        ids = [opportunity["id"] for opportunity in opportunities]
        if len(ids) != len(set(ids)):
            raise error_cls("duplicate opportunity id")
        opportunities.sort(key=lambda opportunity: opportunity["id"])

        stage_counts: dict[str, int] = {}
        action_counts: dict[str, int] = {}
        payment_by_currency: dict[str, int] = {}
        unfinished = 0
        micro_batch = 0
        for opportunity in opportunities:
            stage_counts[opportunity["stage"]] = stage_counts.get(opportunity["stage"], 0) + 1
            action_counts[opportunity["next_action"]] = action_counts.get(opportunity["next_action"], 0) + 1
            payment_by_currency[opportunity["currency"]] = payment_by_currency.get(opportunity["currency"], 0) + opportunity["payment_received_cents"]
            unfinished += int(opportunity["economically_unfinished"])
            micro_batch += int(opportunity["micro_batch_candidate"])
        return {
            "schema": schema,
            "evaluation_at": evaluation_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "micro_batch_threshold_cents": threshold,
            "truth_boundary": "RETAINED_EVIDENCE_INPUT_NOT_PROVIDER_AUTHENTICATED",
            "authority": authority(),
            "opportunities": opportunities,
            "summary": {
                "opportunity_count": len(opportunities),
                "stage_counts": dict(sorted(stage_counts.items())),
                "next_action_counts": dict(sorted(action_counts.items())),
                "economically_unfinished_count": unfinished,
                "micro_batch_candidate_count": micro_batch,
                "payment_received_by_currency": dict(sorted(payment_by_currency.items())),
                "advertised_or_reference_amount_is_revenue": False,
                "merged_or_accepted_is_paid": False,
            },
        }

    def compile_bundle(document: Any) -> dict[str, Any]:
        packet = compile_portfolio(document)
        normalized_input = json_mod.loads(canonical(document).decode("utf-8"))
        receipt = {
            "schema": bundle_schema,
            "input_sha256": digest(normalized_input),
            "packet_sha256": digest(packet),
            "authority": authority(),
        }
        return {"schema": bundle_schema, "input": normalized_input, "packet": packet, "receipt": receipt}

    def verify_bundle(bundle: Any) -> bool:
        if type(bundle) is not dict or any(type(key) is not str for key in bundle) or set(bundle) != {"schema", "input", "packet", "receipt"}:
            return False
        if bundle.get("schema") != bundle_schema:
            return False
        receipt = bundle.get("receipt")
        if type(receipt) is not dict or any(type(key) is not str for key in receipt) or set(receipt) != {"schema", "input_sha256", "packet_sha256", "authority"}:
            return False
        if receipt.get("schema") != bundle_schema or receipt.get("authority") != authority():
            return False
        try:
            recomputed = compile_bundle(bundle["input"])
            return canonical(recomputed) == canonical(bundle)
        except error_cls:
            return False

    def load_json_strict(path: Path, *, limit: int = 8_000_000) -> Any:
        st = os_mod.lstat(path)
        if not stat_mod.S_ISREG(st.st_mode) or st.st_size > limit:
            raise error_cls("input must be a bounded regular file")
        flags = os_mod.O_RDONLY
        if hasattr(os_mod, "O_NOFOLLOW"):
            flags |= os_mod.O_NOFOLLOW
        fd = os_mod.open(path, flags)
        try:
            before = os_mod.fstat(fd)
            if not stat_mod.S_ISREG(before.st_mode) or before.st_size > limit:
                raise error_cls("input changed or is not regular")
            if (st.st_dev, st.st_ino, st.st_size) != (before.st_dev, before.st_ino, before.st_size):
                raise error_cls("input changed before retained read")
            chunks: list[bytes] = []
            remaining = limit + 1
            while remaining:
                chunk = os_mod.read(fd, min(131072, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            raw = b"".join(chunks)
            after = os_mod.fstat(fd)
            if len(raw) > limit or len(raw) != before.st_size or (before.st_dev, before.st_ino, before.st_size) != (after.st_dev, after.st_ino, after.st_size):
                raise error_cls("input changed while reading")
        finally:
            os_mod.close(fd)

        def reject_constant(value: str) -> None:
            raise error_cls(f"non-finite JSON constant: {value}")

        def reject_float(value: str) -> None:
            raise error_cls(f"floating JSON number forbidden: {value}")

        def bounded_int(value: str) -> int:
            digits = value[1:] if value.startswith("-") else value
            if len(digits) > 18:
                raise error_cls("JSON integer exceeds bounded parser")
            return int(value)

        def reject_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
            out: dict[str, Any] = {}
            for key, value in pairs:
                if key in out:
                    raise error_cls(f"duplicate JSON key: {key}")
                out[key] = value
            return out

        try:
            return json_mod.loads(
                raw.decode("utf-8", "strict"),
                parse_constant=reject_constant,
                parse_float=reject_float,
                parse_int=bounded_int,
                object_pairs_hook=reject_pairs,
            )
        except (UnicodeError, json_mod.JSONDecodeError, RecursionError) as exc:
            raise error_cls(f"invalid JSON: {exc}") from exc

    def write_exclusive(path: Path, data: bytes) -> None:
        flags = os_mod.O_WRONLY | os_mod.O_CREAT | os_mod.O_EXCL
        if hasattr(os_mod, "O_NOFOLLOW"):
            flags |= os_mod.O_NOFOLLOW
        fd = os_mod.open(path, flags, 0o600)
        try:
            view = memoryview(data)
            while view:
                written = os_mod.write(fd, view)
                if written <= 0:
                    raise error_cls("short write")
                view = view[written:]
            os_mod.fsync(fd)
        finally:
            os_mod.close(fd)

    return compile_portfolio, compile_bundle, verify_bundle, load_json_strict, write_exclusive, canonical


compile_portfolio, compile_bundle, verify_bundle, _load_json_strict, _write_exclusive, _canonical = _make_core()


def _make_main(compile_fn, verify_fn, load_fn, write_fn, canonical_fn):
    argparse_mod = argparse
    json_mod = json
    path_cls = Path
    error_cls = FunnelError

    def main(argv: list[str] | None = None) -> int:
        parser = argparse_mod.ArgumentParser(description="Compile/verify retained-evidence revenue funnel portfolios.")
        sub = parser.add_subparsers(dest="command", required=True)
        compile_parser = sub.add_parser("compile")
        compile_parser.add_argument("input")
        compile_parser.add_argument("output")
        verify_parser = sub.add_parser("verify")
        verify_parser.add_argument("bundle")
        args = parser.parse_args(argv)
        try:
            if args.command == "compile":
                document = load_fn(path_cls(args.input))
                bundle = compile_fn(document)
                write_fn(path_cls(args.output), canonical_fn(bundle) + b"\n")
                print(json_mod.dumps({"valid": True, "packet_sha256": bundle["receipt"]["packet_sha256"]}, sort_keys=True))
                return 0
            bundle = load_fn(path_cls(args.bundle))
            valid = verify_fn(bundle)
            print(json_mod.dumps({"valid": valid}, sort_keys=True))
            return 0 if valid else 2
        except (OSError, error_cls) as exc:
            print(json_mod.dumps({"valid": False, "error": str(exc)}, sort_keys=True))
            return 2

    return main


main = _make_main(compile_bundle, verify_bundle, _load_json_strict, _write_exclusive, _canonical)


if __name__ == "__main__":
    raise SystemExit(main())
