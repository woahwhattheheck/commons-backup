from __future__ import annotations

from typing import Any

from .codec_v2 import ClaimError, canonical, exact, utc
from .compiler_v2 import COMPILER_ID, REPORT_SCHEMA, compile_normalized
from .schema_v2 import normalize


def verify_artifacts(document: Any, report: Any, markdown: str, receipt: Any) -> bool:
    try:
        doc = normalize(document)
        row = exact(report, {"schema", "compiler_id", "mode", "evaluation_at", "claim_id", "claimant_id", "counterparty_id", "opportunity_id", "work_id", "state", "blockers", "payment_request", "authority", "input_sha256"}, "report")
        if row["schema"] != REPORT_SCHEMA or row["compiler_id"] != COMPILER_ID or row["mode"] not in ("CURRENT", "HISTORICAL_REPLAY"):
            return False
        _, now = utc(row["evaluation_at"], "report.evaluation_at")
        expected = compile_normalized(doc, now, row["mode"] == "HISTORICAL_REPLAY")
        return canonical(report) == canonical(expected[0]) and type(markdown) is str and markdown == expected[1] and canonical(receipt) == canonical(expected[2])
    except (ClaimError, TypeError, ValueError, UnicodeError):
        return False
