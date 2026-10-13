from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .authority_v2 import authority
from .codec_v2 import sha_bytes, sha_value, utc
from .decision_v2 import decide
from .render_v2 import render
from .schema_v2 import normalize

REPORT_SCHEMA = "TJL_MERGED_WORK_PAYMENT_CLAIM_REPORT_V2"
RECEIPT_SCHEMA = "TJL_MERGED_WORK_PAYMENT_CLAIM_RECEIPT_V2"
COMPILER_ID = "merged-work-payment-claim/v2"


def compile_normalized(doc: dict[str, Any], now: datetime, historical_replay: bool) -> tuple[dict[str, Any], str, dict[str, Any]]:
    now = now.astimezone(timezone.utc).replace(microsecond=0)
    evaluation_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    state, blockers, request = decide(doc, now, historical_replay=historical_replay)
    report = {
        "schema": REPORT_SCHEMA,
        "compiler_id": COMPILER_ID,
        "mode": "HISTORICAL_REPLAY" if historical_replay else "CURRENT",
        "evaluation_at": evaluation_at,
        "claim_id": doc["claim_id"],
        "claimant_id": doc["claimant_id"],
        "counterparty_id": doc["counterparty_id"],
        "opportunity_id": doc["opportunity_id"],
        "work_id": doc["work"]["work_id"],
        "state": state,
        "blockers": blockers,
        "payment_request": request,
        "authority": authority(),
        "input_sha256": sha_value(doc),
    }
    markdown = render(report)
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "compiler_id": COMPILER_ID,
        "mode": report["mode"],
        "evaluation_at": evaluation_at,
        "input_sha256": report["input_sha256"],
        "report_sha256": sha_value(report),
        "markdown_sha256": sha_bytes(markdown.encode("utf-8")),
        "state": state,
    }
    return report, markdown, receipt


def compile_current(document: Any) -> tuple[dict[str, Any], str, dict[str, Any]]:
    doc = normalize(document)
    return compile_normalized(doc, datetime.now(timezone.utc), False)


def compile_replay(document: Any, evaluation_at: str) -> tuple[dict[str, Any], str, dict[str, Any]]:
    doc = normalize(document)
    _, now = utc(evaluation_at, "evaluation_at")
    return compile_normalized(doc, now, True)
