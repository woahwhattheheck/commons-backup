#!/usr/bin/env python3
"""Synthetic end-to-end demo for the local podcast sponsorship flight desk."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from podcast_flight_ops import Desk, verify_bundle


def run_demo(root: Path) -> dict:
    db = root / "demo.sqlite3"
    out = root / "handoff"
    with Desk(db) as desk:
        desk.add_show("demo-show", "2026-10-01T12:00:00Z", show_id="signal-hour", name="Signal Hour")
        desk.add_slot("demo-slot-1", "2026-10-01T12:01:00Z", slot_id="signal-101-mid",
                      show_id="signal-hour", air_date="2026-10-10", position="midroll-1")
        desk.add_slot("demo-slot-2", "2026-10-01T12:02:00Z", slot_id="signal-102-mid",
                      show_id="signal-hour", air_date="2026-10-17", position="midroll-1")
        desk.add_slot("demo-slot-3", "2026-10-01T12:03:00Z", slot_id="signal-103-mid",
                      show_id="signal-hour", air_date="2026-10-24", position="midroll-1")
        desk.add_campaign("demo-campaign", "2026-10-01T12:04:00Z", campaign_id="acme-oct",
                          advertiser_ref="owner:advertiser-acme", currency="USD",
                          start_date="2026-10-01", end_date="2026-10-31",
                          contracted_insertions=2, unit_rate_cents=125000,
                          io_reference="owner:io-acme-2026-10")
        desk.add_creative("demo-creative", "2026-10-01T12:05:00Z", creative_id="acme-read",
                          revision=1, campaign_id="acme-oct", source_sha256="1" * 64)
        desk.approve_creative("demo-approve", "2026-10-01T12:06:00Z", creative_id="acme-read",
                              revision=1, approval_ref="owner:approval-acme-r1")
        desk.book("demo-book-1", "2026-10-01T12:07:00Z", booking_id="placement-101",
                  campaign_id="acme-oct", slot_id="signal-101-mid", creative_id="acme-read",
                  creative_revision=1)
        desk.book("demo-book-2", "2026-10-01T12:08:00Z", booking_id="placement-102",
                  campaign_id="acme-oct", slot_id="signal-102-mid", creative_id="acme-read",
                  creative_revision=1)
        desk.mark_delivery("demo-deliver-1", "2026-10-11T12:00:00Z", booking_id="placement-101",
                           evidence_ref="owner:episode-101-delivery")
        desk.mark_missed("demo-miss-2", "2026-10-18T12:00:00Z", booking_id="placement-102",
                         evidence_ref="owner:missed-placement-102")
        desk.makegood("demo-mg-book", "2026-10-18T12:01:00Z", booking_id="placement-103-mg",
                      missed_booking_id="placement-102", slot_id="signal-103-mid",
                      creative_id="acme-read", creative_revision=1)
        desk.mark_delivery("demo-mg-deliver", "2026-10-25T12:00:00Z", booking_id="placement-103-mg",
                           evidence_ref="owner:episode-103-makegood-delivery")
        desk.verify_db()
        desk.export_bundle(out)
        snapshot = desk.snapshot()
    verified = verify_bundle(out)
    return {"invoice": snapshot["invoice_drafts"][0], "bundle": verified}


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp:
        print(json.dumps(run_demo(Path(tmp)), sort_keys=True, indent=2))
