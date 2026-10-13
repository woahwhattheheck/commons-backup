from __future__ import annotations

import hashlib
from typing import Any

from .model import _rank_rows, _row, render_markdown
from .schema import OUTPUT_SCHEMA, RECEIPT_SCHEMA, AllocationError, sha256_document, validate_input

def compile_portfolio(
    document: Any,
    _output_schema: str = OUTPUT_SCHEMA,
    _receipt_schema: str = RECEIPT_SCHEMA,
    _validate_input=validate_input,
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    normalized = _validate_input(document)
    rows = _rank_rows([_row(c) for c in normalized["candidates"]])
    output: dict[str, Any] = {
        "schema": _output_schema,
        "portfolio_id": normalized["portfolio_id"],
        "ranking_policy": {
            "currency_policy": "NO_FX_COMPARE_WITHIN_CURRENCY_ONLY",
            "probability_policy": "EXPLICIT_OWNER_BPS_ONLY_NO_INFERENCE",
            "expected_value_formula": "floor(commercial_value_minor * probability_bps / 10000)",
            "hold_dominates_rank": True,
        },
        "counts": {
            "total": len(rows),
            "expected_value": sum(r["queue"] == "EXPECTED_VALUE" for r in rows),
            "evidence_strength": sum(r["queue"] == "EVIDENCE_STRENGTH" for r in rows),
            "hold": sum(r["queue"] == "HOLD" for r in rows),
        },
        "rows": rows,
        "external_send_authorized": False,
        "provider_mutation_authorized": False,
        "payment_or_revenue_inferred": False,
    }
    output["output_sha256"] = sha256_document(output)
    markdown = render_markdown(output)
    receipt: dict[str, Any] = {
        "schema": _receipt_schema,
        "portfolio_id": normalized["portfolio_id"],
        "input_sha256": sha256_document(normalized),
        "output_sha256": output["output_sha256"],
        "markdown_sha256": hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
        "counts": dict(output["counts"]),
        "external_send_authorized": False,
        "provider_mutation_authorized": False,
        "payment_or_revenue_inferred": False,
    }
    receipt["receipt_sha256"] = sha256_document(receipt)
    return output, markdown, receipt

def verify_bundle(
    document: Any,
    output: Any,
    markdown: str,
    receipt: Any,
) -> dict[str, Any]:
    if type(output) is not dict or type(receipt) is not dict or not isinstance(markdown, str):
        raise AllocationError("bundle types invalid")
    expected_output, expected_markdown, expected_receipt = compile_portfolio(document)
    if output != expected_output:
        raise AllocationError("output semantic verification failed")
    if markdown != expected_markdown:
        raise AllocationError("markdown semantic verification failed")
    if receipt != expected_receipt:
        raise AllocationError("receipt semantic verification failed")
    return {
        "valid": True,
        "portfolio_id": expected_output["portfolio_id"],
        "output_sha256": expected_output["output_sha256"],
        "receipt_sha256": expected_receipt["receipt_sha256"],
        "external_send_authorized": False,
        "provider_mutation_authorized": False,
        "payment_or_revenue_inferred": False,
    }

