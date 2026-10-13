#!/usr/bin/env python3
"""Strict validator for the current public-procurement comparable corpus."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any

SCHEMA = "public-procurement-comparable-corpus/v1"
OPERATION = "PUBLIC-PROCUREMENT-AWARD-COMPARABLE-CORPUS-20260916"
TRUTH = "INTERNAL_PRICE_RESEARCH_ONLY"
SHA = re.compile(r"^[0-9a-f]{64}$")
CUR = re.compile(r"^[A-Z]{3}$")
UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
ALLOWED_PROFILES = {"LEGISTAR_AWARD_HTML_V1", "BUYER_BID_TABULATION_PDF_V1"}
ALLOWED_SOURCE_CLASS = {"BOARD_AWARD", "BID_TABULATION", "AMENDMENT", "OPTION", "RENEWAL"}
ALLOWED_KINDS = {"AWARD", "BID", "OPTION", "RENEWAL"}
ALLOWED_PROMOTABILITY = {"HOLD_RAW_SOURCE_HASH_PENDING", "LIVE_ADAPTER_READY"}
MAX_BYTES = 4_000_000


class CorpusError(ValueError):
    pass


def canonical(value: Any) -> bytes:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise CorpusError("value is not canonical JSON") from exc


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def load(path: str | Path) -> dict[str, Any]:
    raw = Path(path).read_bytes()
    if len(raw) > MAX_BYTES:
        raise CorpusError("corpus is too large")
    try:
        text_value = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CorpusError("corpus must be UTF-8") from exc
    def hook(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise CorpusError(f"duplicate JSON key {key!r}")
            result[key] = value
        return result
    try:
        value = json.loads(text_value, object_pairs_hook=hook, parse_constant=lambda token: (_ for _ in ()).throw(CorpusError(f"non-finite JSON constant {token}")))
    except json.JSONDecodeError as exc:
        raise CorpusError(f"invalid JSON: {exc}") from exc
    if type(value) is not dict:
        raise CorpusError("root must be an object")
    return value


def exact(value: Any, keys: set[str], where: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise CorpusError(f"{where} must be an object")
    got = set(value)
    if got != keys:
        raise CorpusError(f"{where} keys mismatch missing={sorted(keys-got)} extra={sorted(got-keys)}")
    return value


def text(value: Any, where: str, limit: int = 4096) -> str:
    if not isinstance(value, str) or not value or value != value.strip() or len(value) > limit or any(ord(ch) < 32 for ch in value):
        raise CorpusError(f"{where} must be a bounded trimmed string")
    return value


def utc(value: Any, where: str) -> datetime:
    value = text(value, where, 32)
    if UTC.fullmatch(value) is None:
        raise CorpusError(f"{where} must be exact UTC seconds")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise CorpusError(f"{where} invalid timestamp") from exc


def date(value: Any, where: str):
    value = text(value, where, 10)
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise CorpusError(f"{where} invalid date") from exc


def sha(value: Any, where: str) -> str:
    if not isinstance(value, str) or SHA.fullmatch(value) is None:
        raise CorpusError(f"{where} must be lowercase SHA-256")
    return value


def https(value: Any, where: str) -> str:
    value = text(value, where, 2048)
    if not value.startswith("https://") or any(ch.isspace() for ch in value):
        raise CorpusError(f"{where} must be HTTPS")
    return value


def _hash_without(value: dict[str, Any], field: str) -> str:
    body = dict(value)
    body.pop(field)
    return digest(body)


def validate(data: dict[str, Any]) -> dict[str, Any]:
    root = exact(data, {"schema","operation","generated_at_utc","truth_boundary","authority","sources","records","exclusions","summary"}, "root")
    if root["schema"] != SCHEMA: raise CorpusError("wrong schema")
    if root["operation"] != OPERATION: raise CorpusError("wrong operation")
    if root["truth_boundary"] != TRUTH: raise CorpusError("wrong truth boundary")
    generated = utc(root["generated_at_utc"], "generated_at_utc")
    authority = exact(root["authority"], {"quote_authorized","bid_authorized","submission_authorized","buyer_or_partner_contact_authorized","price_commitment_authorized","award_claimed","payment_claimed","revenue_claimed"}, "authority")
    if any(value is not False for value in authority.values()): raise CorpusError("authority ceiling must remain hard-false")

    sources = root["sources"]
    if type(sources) is not list or not 20 <= len(sources) <= 50: raise CorpusError("sources must contain 20..50 rows")
    source_by_id, uris = {}, set()
    for index, raw in enumerate(sources):
        source = exact(raw, {"id","buyer","profile","uri","source_class","observed_at_utc","web_verification_state","raw_hash_state","raw_source_sha256","record_ids","snapshot_sha256"}, f"sources[{index}]")
        sid = text(source["id"], f"sources[{index}].id", 128)
        if sid in source_by_id: raise CorpusError(f"duplicate source id {sid}")
        source_by_id[sid] = source
        text(source["buyer"], f"{sid}.buyer", 128)
        if source["profile"] not in ALLOWED_PROFILES: raise CorpusError(f"{sid}: unsupported profile")
        uri = https(source["uri"], f"{sid}.uri")
        if uri in uris: raise CorpusError(f"duplicate source URI {uri}")
        uris.add(uri)
        if source["source_class"] not in ALLOWED_SOURCE_CLASS: raise CorpusError(f"{sid}: unsupported source class")
        if utc(source["observed_at_utc"], f"{sid}.observed_at_utc") > generated: raise CorpusError(f"{sid}: observed after corpus generation")
        if source["web_verification_state"] not in {"AUTHORITATIVE_PAGE_VERIFIED","AUTHORITATIVE_PDF_VISUALLY_REVIEWED"}: raise CorpusError(f"{sid}: unsupported web verification state")
        if source["raw_hash_state"] == "PENDING_LIVE_ADAPTER_FETCH":
            if source["raw_source_sha256"] is not None: raise CorpusError(f"{sid}: pending raw source hash must be null")
        elif source["raw_hash_state"] == "VERIFIED_LIVE_ADAPTER":
            sha(source["raw_source_sha256"], f"{sid}.raw_source_sha256")
        else: raise CorpusError(f"{sid}: unsupported raw hash state")
        if type(source["record_ids"]) is not list or not source["record_ids"] or any(not isinstance(item,str) or not item for item in source["record_ids"]) or len(source["record_ids"]) != len(set(source["record_ids"])): raise CorpusError(f"{sid}: record_ids must be unique non-empty strings")
        sha(source["snapshot_sha256"], f"{sid}.snapshot_sha256")
        if _hash_without(source, "snapshot_sha256") != source["snapshot_sha256"]: raise CorpusError(f"{sid}: source snapshot digest mismatch")

    records = root["records"]
    if type(records) is not list or not 25 <= len(records) <= 50: raise CorpusError("records must contain 25..50 rows")
    record_by_id = {}
    record_keys = {"id","opportunity_id","vendor","amount_minor","event_date","price_kind","extraction_state","source_id","currency","basis","unit","term_months","source_disposition","promotability","claim_sha256"}
    for index, raw in enumerate(records):
        record = exact(raw, record_keys, f"records[{index}]")
        rid = text(record["id"], f"records[{index}].id", 160)
        if rid in record_by_id: raise CorpusError(f"duplicate record id {rid}")
        record_by_id[rid] = record
        sid = record["source_id"]
        if sid not in source_by_id: raise CorpusError(f"{rid}: unknown source")
        source = source_by_id[sid]
        if rid not in source["record_ids"]: raise CorpusError(f"{rid}: source does not bind record id")
        text(record["opportunity_id"], f"{rid}.opportunity_id", 128); text(record["vendor"], f"{rid}.vendor", 256)
        if isinstance(record["amount_minor"], bool) or not isinstance(record["amount_minor"], int) or record["amount_minor"] <= 0 or record["amount_minor"] > 10**15: raise CorpusError(f"{rid}: amount_minor must be positive integer")
        if not isinstance(record["currency"], str) or CUR.fullmatch(record["currency"]) is None: raise CorpusError(f"{rid}: invalid currency")
        if record["basis"] != "CONTRACT_TOTAL": raise CorpusError(f"{rid}: corpus v1 preserves contract-total basis only")
        if record["unit"] is not None or record["term_months"] is not None: raise CorpusError(f"{rid}: contract-total record must not invent unit/term")
        if date(record["event_date"], f"{rid}.event_date") > generated.date(): raise CorpusError(f"{rid}: future event date")
        if record["price_kind"] not in ALLOWED_KINDS: raise CorpusError(f"{rid}: unsupported price kind")
        expected_kind = "AWARD" if source["source_class"] == "BOARD_AWARD" else "BID"
        if source["source_class"] in {"BOARD_AWARD","BID_TABULATION"} and record["price_kind"] != expected_kind: raise CorpusError(f"{rid}: price kind/source class mismatch")
        text(record["extraction_state"], f"{rid}.extraction_state", 64)
        if record["source_disposition"] != "INCLUDED_BY_SOURCE": raise CorpusError(f"{rid}: included records must be INCLUDED_BY_SOURCE")
        if record["promotability"] not in ALLOWED_PROMOTABILITY: raise CorpusError(f"{rid}: unsupported promotability")
        if source["raw_hash_state"] == "PENDING_LIVE_ADAPTER_FETCH" and record["promotability"] != "HOLD_RAW_SOURCE_HASH_PENDING": raise CorpusError(f"{rid}: pending source cannot promote")
        if source["raw_hash_state"] == "VERIFIED_LIVE_ADAPTER" and record["promotability"] != "LIVE_ADAPTER_READY": raise CorpusError(f"{rid}: verified source must be LIVE_ADAPTER_READY")
        sha(record["claim_sha256"], f"{rid}.claim_sha256")
        if _hash_without(record, "claim_sha256") != record["claim_sha256"]: raise CorpusError(f"{rid}: claim digest mismatch")

    for sid, source in source_by_id.items():
        if set(source["record_ids"]) != {rid for rid,row in record_by_id.items() if row["source_id"] == sid}: raise CorpusError(f"{sid}: record binding set mismatch")

    exclusions = root["exclusions"]
    if type(exclusions) is not list: raise CorpusError("exclusions must be a list")
    exclusion_ids = set()
    for index, raw in enumerate(exclusions):
        row = exact(raw, record_keys, f"exclusions[{index}]")
        rid = text(row["id"], f"exclusions[{index}].id", 160)
        if rid in record_by_id or rid in exclusion_ids: raise CorpusError(f"duplicate/excluded record id {rid}")
        exclusion_ids.add(rid)
        if row["source_id"] not in source_by_id: raise CorpusError(f"{rid}: unknown source")
        if row["source_disposition"] != "REJECTED_BY_SOURCE": raise CorpusError(f"{rid}: exclusion must be REJECTED_BY_SOURCE")
        if row["promotability"] != "EXCLUDED_BY_SOURCE": raise CorpusError(f"{rid}: exclusion promotability mismatch")
        if isinstance(row["amount_minor"], bool) or not isinstance(row["amount_minor"], int) or row["amount_minor"] <= 0: raise CorpusError(f"{rid}: invalid excluded amount")
        if row["currency"] != "USD" or row["basis"] != "CONTRACT_TOTAL" or row["unit"] is not None or row["term_months"] is not None: raise CorpusError(f"{rid}: malformed excluded comparable dimensions")
        date(row["event_date"], f"{rid}.event_date"); sha(row["claim_sha256"], f"{rid}.claim_sha256")
        if _hash_without(row, "claim_sha256") != row["claim_sha256"]: raise CorpusError(f"{rid}: exclusion claim digest mismatch")

    expected_summary = {"record_count":len(records),"source_count":len(sources),"exclusion_count":len(exclusions),"buyer_counts":dict(sorted(Counter(source_by_id[row["source_id"]]["buyer"] for row in records).items())),"price_kind_counts":dict(sorted(Counter(row["price_kind"] for row in records).items())),"promotability_counts":dict(sorted(Counter(row["promotability"] for row in records).items())),"raw_hash_state_counts":dict(sorted(Counter(row["raw_hash_state"] for row in sources).items()))}
    if root["summary"] != expected_summary: raise CorpusError("summary drift")
    return expected_summary


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("corpus", nargs="?", default="revenue/procurement_award_price_intelligence/comparable_corpus_20260916/corpus.json"); args = parser.parse_args(argv)
    try: summary = validate(load(args.corpus))
    except (OSError, CorpusError) as exc: parser.error(str(exc))
    print(f"VALID records={summary['record_count']} sources={summary['source_count']} buyers={summary['buyer_counts']} readiness={summary['promotability_counts']}")
    return 0


if __name__ == "__main__": raise SystemExit(main())
