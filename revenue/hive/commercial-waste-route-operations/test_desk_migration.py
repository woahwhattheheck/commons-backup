#!/usr/bin/env python3

from test_support import *
from desk import canon, digest


class MigrationAuthTests(WasteRouteDeskTestBase):
    def _prepare_legacy_invoice_fixture(self):
        prior = self._monday_route(self.prior_monday, "migration-prior-route")
        current = self._monday_route(self.current_monday, "migration-current-route")
        self._settle_customer(prior, "ACME", "migration-prior")
        current_stops = self._settle_customer(current, "ACME", "migration-current")
        invoice = self.desk.draft_invoice(
            "ACME",
            self.prior_monday.isoformat(),
            self.prior_monday.isoformat(),
            "migration-legacy-invoice",
        )
        substitute = self.desk.conn.execute(
            """
            SELECT st.id stop_id,r.service_date,st.customer_id,st.plan_id,
                   st.site_id,st.container_id,p.service_code,st.status,st.charge_minor
            FROM stops st
            JOIN routes r ON r.id=st.route_id
            JOIN plans p ON p.id=st.plan_id
            WHERE st.id=?
            """,
            (current_stops[0]["id"],),
        ).fetchone()
        substitute_line = dict(substitute)
        old_invoice_id = invoice["invoice_id"]

        self.desk.close()
        self.desk = None
        raw = sqlite3.connect(self.db)
        raw.row_factory = sqlite3.Row
        raw.execute("PRAGMA foreign_keys=OFF")
        raw.execute("DROP TRIGGER IF EXISTS invoice_drafts_no_update")
        raw.execute("DROP TRIGGER IF EXISTS invoice_drafts_no_delete")
        raw.execute("DROP TRIGGER IF EXISTS events_no_update")
        raw.execute("DROP TRIGGER IF EXISTS events_no_delete")
        raw.execute("DROP TABLE invoice_lines")

        draft = raw.execute(
            "SELECT * FROM invoice_drafts WHERE id=?", (old_invoice_id,)
        ).fetchone()
        payload = json.loads(draft["payload_json"])
        payload.pop("business_date")
        for line in payload["lines"]:
            line.pop("resolution")
            line.pop("makeup_service_date")
        basis = {
            "customer_id": payload["customer_id"],
            "period_start": payload["period_start"],
            "period_end": payload["period_end"],
            "currency": payload["currency"],
            "lines": payload["lines"],
            "total_minor": payload["total_minor"],
        }
        receipt = digest(basis)
        legacy_invoice_id = "inv:" + receipt[:24]
        payload["invoice_id"] = legacy_invoice_id
        payload["receipt_digest"] = receipt
        raw.execute(
            """
            UPDATE invoice_drafts
            SET id=?,receipt_digest=?,payload_json=?
            WHERE id=?
            """,
            (legacy_invoice_id, receipt, canon(payload), old_invoice_id),
        )

        event = raw.execute(
            """
            SELECT id,op_key,event_type,entity_kind
            FROM events
            WHERE entity_id=? AND event_type='INVOICE_DRAFT_CREATED'
            """,
            (old_invoice_id,),
        ).fetchone()
        event_payload = {
            "invoice_id": legacy_invoice_id,
            "customer_id": payload["customer_id"],
            "total_minor": payload["total_minor"],
            "currency": payload["currency"],
            "receipt_digest": receipt,
        }
        event_digest = digest(
            {
                "op_key": event["op_key"],
                "event_type": event["event_type"],
                "entity_kind": event["entity_kind"],
                "entity_id": legacy_invoice_id,
                "payload": event_payload,
            }
        )
        raw.execute(
            """
            UPDATE events
            SET entity_id=?,payload_json=?,event_digest=?
            WHERE id=?
            """,
            (legacy_invoice_id, canon(event_payload), event_digest, event["id"]),
        )
        raw.commit()
        raw.close()
        return {
            "invoice_id": legacy_invoice_id,
            "payload": payload,
            "substitute_line": substitute_line,
            "expanded_period_end": self.current_monday.isoformat(),
        }

    def _assert_failed_backfill_left_no_claims(self, expected_message=None):
        with self.assertRaises(StateConflict) as caught:
            WasteRouteDesk(self.db)
        if expected_message is not None:
            self.assertIn(expected_message, str(caught.exception))
        raw = sqlite3.connect(self.db)
        count = raw.execute("SELECT COUNT(*) FROM invoice_lines").fetchone()[0]
        raw.close()
        self.assertEqual(count, 0)

    def test_authentic_legacy_invoice_backfills_only_authenticated_lines(self):
        fixture = self._prepare_legacy_invoice_fixture()
        self.desk = WasteRouteDesk(self.db)
        claims = self.desk.conn.execute(
            "SELECT invoice_id,stop_id FROM invoice_lines ORDER BY stop_id"
        ).fetchall()
        self.assertEqual(len(claims), 2)
        self.assertEqual(
            {row["invoice_id"] for row in claims}, {fixture["invoice_id"]}
        )

    def test_payload_only_stop_substitution_fails_closed_without_minting_custody(self):
        fixture = self._prepare_legacy_invoice_fixture()
        raw = sqlite3.connect(self.db)
        raw.row_factory = sqlite3.Row
        draft = raw.execute(
            "SELECT payload_json FROM invoice_drafts WHERE id=?",
            (fixture["invoice_id"],),
        ).fetchone()
        payload = json.loads(draft["payload_json"])
        payload["lines"][0]["stop_id"] = fixture["substitute_line"]["stop_id"]
        raw.execute(
            "UPDATE invoice_drafts SET payload_json=? WHERE id=?",
            (canon(payload), fixture["invoice_id"]),
        )
        raw.commit()
        raw.close()
        self._assert_failed_backfill_left_no_claims("retained stop generation")

    def test_payload_and_row_receipt_rewrite_cannot_override_immutable_event(self):
        fixture = self._prepare_legacy_invoice_fixture()
        raw = sqlite3.connect(self.db)
        raw.row_factory = sqlite3.Row
        draft = raw.execute(
            "SELECT * FROM invoice_drafts WHERE id=?", (fixture["invoice_id"],)
        ).fetchone()
        payload = json.loads(draft["payload_json"])
        payload["lines"][0] = fixture["substitute_line"]
        payload["period_end"] = fixture["expanded_period_end"]
        basis = {
            "customer_id": payload["customer_id"],
            "period_start": payload["period_start"],
            "period_end": payload["period_end"],
            "currency": payload["currency"],
            "lines": payload["lines"],
            "total_minor": payload["total_minor"],
        }
        forged_receipt = digest(basis)
        forged_invoice_id = "inv:" + forged_receipt[:24]
        payload["invoice_id"] = forged_invoice_id
        payload["receipt_digest"] = forged_receipt
        raw.execute(
            """
            UPDATE invoice_drafts
            SET id=?,period_end=?,receipt_digest=?,payload_json=?
            WHERE id=?
            """,
            (
                forged_invoice_id,
                payload["period_end"],
                forged_receipt,
                canon(payload),
                fixture["invoice_id"],
            ),
        )
        raw.commit()
        raw.close()
        self._assert_failed_backfill_left_no_claims("immutable invoice creation event")
