#!/usr/bin/env python3
"""Synthetic, local-only walkthrough for the waste route operations desk."""

import json
import tempfile
from pathlib import Path

from desk import BillingBlocked, WasteRouteDesk
from test_desk import MANIFEST


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "demo.sqlite3"
        with WasteRouteDesk(db) as desk:
            desk.import_manifest(MANIFEST, "demo-manifest")
            route = desk.generate_route("2026-09-14", "demo-route")
            acme = [s for s in route["stops"] if s["customer_id"] == "ACME"]
            beta = [s for s in route["stops"] if s["customer_id"] == "BETA"][0]

            desk.record_stop(acme[0]["id"], "SERVICED", "demo-acme-service")
            desk.record_stop(
                acme[1]["id"],
                "SKIPPED",
                "demo-acme-skip",
                exception_code="BLOCKED_ACCESS",
            )
            desk.record_stop(beta["id"], "SERVICED", "demo-beta-service")

            blocked = False
            try:
                desk.draft_invoice(
                    "ACME", "2026-09-14", "2026-09-14", "demo-too-early"
                )
            except BillingBlocked:
                blocked = True

            desk.resolve_exception(
                acme[1]["id"],
                "NO_SERVICE_NO_CHARGE",
                "demo-resolve",
            )
            acme_invoice = desk.draft_invoice(
                "ACME",
                "2026-09-14",
                "2026-09-14",
                "demo-acme-invoice",
            )
            beta_invoice = desk.draft_invoice(
                "BETA",
                "2026-09-14",
                "2026-09-14",
                "demo-beta-invoice",
            )
            claim_count = desk.conn.execute(
                "SELECT COUNT(*) count FROM invoice_lines"
            ).fetchone()["count"]

            print(
                json.dumps(
                    {
                        "ok": True,
                        "synthetic": True,
                        "business_date": desk.business_date().isoformat(),
                        "route_stop_count": route["stop_count"],
                        "premature_invoice_blocked": blocked,
                        "acme_total_minor": acme_invoice["total_minor"],
                        "beta_total_minor": beta_invoice["total_minor"],
                        "invoice_line_claim_count": claim_count,
                        "event_count": len(desk.event_log()),
                        "external_provider_calls": 0,
                        "outreach_sent": False,
                        "payment_mutation": False,
                    },
                    sort_keys=True,
                )
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
