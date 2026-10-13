from __future__ import annotations

import argparse
import json
from pathlib import Path

from workspace import FieldServiceWorkspace, verify_digest_envelope

DEMO_TOKEN = "synthetic-demo-token-0123456789abcdef0123456789abcdef"


def run_demo(db_path: str | Path) -> dict:
    ws = FieldServiceWorkspace(db_path)
    ws.create_quote(
        quote_id="demo-quote-001",
        currency="USD",
        customer_token=DEMO_TOKEN,
        items=[
            {"item_id": "diagnostic", "description": "Diagnostic and repair labor", "quantity": 2, "unit_cents": 12_500},
            {"item_id": "component", "description": "Replacement component", "quantity": 1, "unit_cents": 8_750},
        ],
        created_at="2026-09-13T10:00:00Z",
        request_key="demo-create",
    )
    published = ws.publish_quote(
        quote_id="demo-quote-001",
        published_at="2026-09-13T10:01:00Z",
        request_key="demo-publish",
    )
    approved = ws.customer_decide_quote(
        quote_id="demo-quote-001",
        customer_token=DEMO_TOKEN,
        expected_quote_digest=published["quote_digest"],
        decision="APPROVE",
        decided_at="2026-09-13T10:02:00Z",
        request_key="demo-customer-approve",
    )
    job_id = approved["job_id"]
    assert job_id is not None
    ws.schedule_job(
        job_id=job_id,
        resource_id="crew-a",
        start_at="2026-09-13T11:00:00Z",
        end_at="2026-09-13T13:00:00Z",
        scheduled_at="2026-09-13T10:03:00Z",
        request_key="demo-schedule",
    )
    change = ws.propose_change(
        job_id=job_id,
        change_id="demo-change-001",
        items=[{"item_id": "extra-part", "description": "Customer-approved additional component", "quantity": 1, "unit_cents": 5_000}],
        proposed_at="2026-09-13T11:20:00Z",
        request_key="demo-change-propose",
    )
    ws.customer_decide_change(
        job_id=job_id,
        change_id="demo-change-001",
        customer_token=DEMO_TOKEN,
        expected_change_digest=change["change_digest"],
        decision="APPROVE",
        decided_at="2026-09-13T11:22:00Z",
        request_key="demo-change-approve",
    )
    for index, scope in enumerate(ws.job_export(job_id=job_id)["scope"]):
        ws.complete_scope_item(
            job_id=job_id,
            scope_key=scope["scope_key"],
            completed_at=f"2026-09-13T12:{10 + index:02d}:00Z",
            request_key=f"demo-scope-{index}",
        )
    ws.complete_job(
        job_id=job_id,
        completed_at="2026-09-13T12:45:00Z",
        request_key="demo-complete",
    )
    invoice = ws.invoice_draft(job_id=job_id)
    export = ws.job_export(job_id=job_id)
    if not verify_digest_envelope(invoice, "draft_digest") or not verify_digest_envelope(export, "export_digest"):
        raise AssertionError("demo digest verification failed")
    return {
        "schema": "hive-field-service-demo/v1",
        "job_id": job_id,
        "quote_digest": published["quote_digest"],
        "change_digest": change["change_digest"],
        "invoice_total_cents": invoice["total_cents"],
        "invoice_draft_digest": invoice["draft_digest"],
        "job_export_digest": export["export_digest"],
        "scope_items": len(export["scope"]),
        "operator_summary": ws.operator_summary(),
        "external_send_authorized": False,
        "payment_authorized": False,
        "accounting_post_authorized": False,
        "recognized_revenue": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a deterministic synthetic field-service workflow")
    parser.add_argument("--db", required=True)
    args = parser.parse_args()
    print(json.dumps(run_demo(args.db), sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
