#!/usr/bin/env python3

from test_support import *


class BillingDeskTests(WasteRouteDeskTestBase):
    def test_invoice_blocks_if_a_later_due_route_was_never_generated(self):
        route = self._monday_route(self.prior_monday, "week1-route")
        self._settle_customer(route, "ACME", "week1")
        with self.assertRaises(BillingBlocked):
            self.desk.draft_invoice(
                "ACME",
                self.prior_monday.isoformat(),
                self.current_monday.isoformat(),
                "two-week-too-early",
            )

        route2 = self._monday_route(self.current_monday, "week2-route")
        self._settle_customer(route2, "ACME", "week2")
        invoice = self.desk.draft_invoice(
            "ACME",
            self.prior_monday.isoformat(),
            self.current_monday.isoformat(),
            "two-week-ready",
        )
        self.assertEqual(invoice["total_minor"], 45600)
        self.assertEqual(len(invoice["lines"]), 4)

    def test_invoice_stays_blocked_if_other_stop_is_pending(self):
        route = self._monday_route()
        first_acme = [s for s in route["stops"] if s["customer_id"] == "ACME"][0]
        self.desk.record_stop(first_acme["id"], "SERVICED", "only-one")
        with self.assertRaises(BillingBlocked):
            self.desk.draft_invoice(
                "ACME",
                self.current_monday.isoformat(),
                self.current_monday.isoformat(),
                "too-early",
            )

    def test_future_route_may_be_planned_but_not_terminalized_or_billed(self):
        route = self._monday_route(self.next_monday, "future-route")
        acme = [s for s in route["stops"] if s["customer_id"] == "ACME"]
        with self.assertRaises(StateConflict):
            self.desk.record_stop(acme[0]["id"], "SERVICED", "future-service")
        with self.assertRaises(StateConflict):
            self.desk.record_stop(
                acme[1]["id"],
                "SKIPPED",
                "future-skip",
                exception_code="BLOCKED_ACCESS",
            )

        self.desk.conn.execute(
            """
            UPDATE stops
            SET status='SERVICE_CONFIRMED',
                charge_minor=(SELECT price_minor FROM plans WHERE plans.id=stops.plan_id)
            WHERE customer_id='ACME' AND route_id=?
            """,
            (route["route_id"],),
        )
        with self.assertRaises(BillingBlocked):
            self.desk.draft_invoice(
                "ACME",
                self.next_monday.isoformat(),
                self.next_monday.isoformat(),
                "forced-future-invoice",
            )

    def test_overlapping_period_cannot_reuse_settled_stops(self):
        prior = self._monday_route(self.prior_monday, "overlap-prior-route")
        current = self._monday_route(self.current_monday, "overlap-current-route")
        self._settle_customer(prior, "ACME", "overlap-prior")
        self._settle_customer(current, "ACME", "overlap-current")
        first = self.desk.draft_invoice(
            "ACME",
            self.prior_monday.isoformat(),
            self.prior_monday.isoformat(),
            "overlap-first",
        )
        self.assertEqual(first["total_minor"], 22800)
        with self.assertRaises(BillingBlocked):
            self.desk.draft_invoice(
                "ACME",
                self.prior_monday.isoformat(),
                self.current_monday.isoformat(),
                "overlap-second",
            )
        claims = self.desk.conn.execute(
            "SELECT stop_id FROM invoice_lines ORDER BY stop_id"
        ).fetchall()
        self.assertEqual(len(claims), 2)

    def test_concurrent_overlapping_invoice_claim_has_one_winner(self):
        prior = self._monday_route(self.prior_monday, "claim-prior-route")
        current = self._monday_route(self.current_monday, "claim-current-route")
        self._settle_customer(prior, "ACME", "claim-prior")
        self._settle_customer(current, "ACME", "claim-current")
        barrier = threading.Barrier(2)

        def worker(kind):
            with WasteRouteDesk(self.db) as desk:
                barrier.wait()
                try:
                    if kind == "short":
                        out = desk.draft_invoice(
                            "ACME",
                            self.prior_monday.isoformat(),
                            self.prior_monday.isoformat(),
                            "claim-short",
                        )
                    else:
                        out = desk.draft_invoice(
                            "ACME",
                            self.prior_monday.isoformat(),
                            self.current_monday.isoformat(),
                            "claim-long",
                        )
                    return ("ok", out["invoice_id"])
                except (BillingBlocked, StateConflict) as exc:
                    return ("blocked", str(exc))

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(worker, ["short", "long"]))
        self.assertEqual(sorted(r[0] for r in results), ["blocked", "ok"])
        count = self.desk.conn.execute(
            "SELECT COUNT(*) count FROM invoice_drafts WHERE customer_id='ACME'"
        ).fetchone()["count"]
        self.assertEqual(count, 1)

    def test_existing_invoice_payload_backfills_line_custody_on_restart(self):
        route = self._monday_route(self.prior_monday, "backfill-route")
        self._settle_customer(route, "ACME", "backfill")
        invoice = self.desk.draft_invoice(
            "ACME",
            self.prior_monday.isoformat(),
            self.prior_monday.isoformat(),
            "backfill-invoice",
        )
        self.desk.close()
        self.desk = None
        raw = sqlite3.connect(self.db)
        raw.execute("PRAGMA foreign_keys=ON")
        raw.execute("DROP TABLE invoice_lines")
        raw.commit()
        raw.close()
        self.desk = WasteRouteDesk(self.db)
        claims = self.desk.conn.execute(
            "SELECT invoice_id,stop_id FROM invoice_lines ORDER BY stop_id"
        ).fetchall()
        self.assertEqual(len(claims), 2)
        self.assertEqual({r["invoice_id"] for r in claims}, {invoice["invoice_id"]})

    def test_existing_overlapping_invoice_payloads_fail_closed_on_restart(self):
        route = self._monday_route(self.prior_monday, "legacy-route")
        acme_stops = self._settle_customer(route, "ACME", "legacy")
        first = self.desk.draft_invoice(
            "ACME",
            self.prior_monday.isoformat(),
            self.prior_monday.isoformat(),
            "legacy-first",
        )
        duplicate_payload = dict(first)
        duplicate_payload["invoice_id"] = "inv:legacy-overlap"
        duplicate_payload["period_start"] = (
            self.prior_monday - timedelta(days=1)
        ).isoformat()
        duplicate_payload["receipt_digest"] = "legacy-overlap-digest"
        self.desk.conn.execute(
            "INSERT INTO invoice_drafts VALUES(?,?,?,?,?,?,?,?)",
            (
                duplicate_payload["invoice_id"],
                "ACME",
                duplicate_payload["period_start"],
                self.prior_monday.isoformat(),
                duplicate_payload["total_minor"],
                "USD",
                duplicate_payload["receipt_digest"],
                json.dumps(duplicate_payload, sort_keys=True),
            ),
        )
        self.assertEqual(len(acme_stops), 2)
        self.desk.close()
        self.desk = None
        raw = sqlite3.connect(self.db)
        raw.execute("DROP TABLE invoice_lines")
        raw.commit()
        raw.close()
        with self.assertRaises(StateConflict):
            WasteRouteDesk(self.db)

    def test_manifest_rejects_bad_nested_types_money_and_timezone(self):
        bad = json.loads(json.dumps(MANIFEST))
        bad["customers"][0]["sites"][0]["containers"][0]["plans"][0][
            "price_minor"
        ] = 12.5
        with self.assertRaises(ValidationError):
            WasteRouteDesk._normalize_manifest(bad)
        bad = json.loads(json.dumps(MANIFEST))
        bad["customers"][0]["sites"][0]["containers"][0]["plans"][0][
            "price_minor"
        ] = MAX_SQLITE_INTEGER + 1
        with self.assertRaises(ValidationError):
            WasteRouteDesk._normalize_manifest(bad)
        bad = json.loads(json.dumps(MANIFEST))
        bad["customers"][0]["sites"][0]["containers"][0]["plans"][0][
            "weekday"
        ] = True
        with self.assertRaises(ValidationError):
            WasteRouteDesk._normalize_manifest(bad)
        bad = json.loads(json.dumps(MANIFEST))
        bad["customers"][0]["sites"][0] = "not-an-object"
        with self.assertRaises(ValidationError):
            WasteRouteDesk._normalize_manifest(bad)
        bad = json.loads(json.dumps(MANIFEST))
        bad["business_timezone"] = "Definitely/Not_A_Zone"
        with self.assertRaises(ValidationError):
            WasteRouteDesk._normalize_manifest(bad)

    def test_invalid_resolution_or_duplicate_route_is_rejected(self):
        self._monday_route()
        with self.assertRaises(StateConflict):
            self.desk.generate_route(
                self.current_monday.isoformat(), "route-duplicate"
            )
        with self.assertRaises(ValidationError):
            self.desk.resolve_exception(
                "whatever", "FORGE_CHARGE", "bad-resolution"
            )

