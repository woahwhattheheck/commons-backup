#!/usr/bin/env python3

from test_support import *


class CoreDeskTests(WasteRouteDeskTestBase):
    def test_manifest_route_order_and_exports_are_deterministic(self):
        first = self.desk.import_manifest(MANIFEST, "manifest-v2")
        self.assertEqual(
            first["counts"],
            {"customers": 2, "sites": 3, "containers": 3, "plans": 3},
        )
        self.assertEqual(first["business_timezone"], "UTC")
        route = self._monday_route()
        self.assertEqual(route["stop_count"], 3)
        self.assertEqual(
            [s["plan_id"] for s in route["stops"]],
            ["PLAN-ACME-DOWNTOWN", "PLAN-ACME-MARKET", "PLAN-BETA-HQ"],
        )
        snap = self.desk.route_snapshot(self.current_monday.isoformat())
        self.assertEqual(snap["external_provider_calls"], 0)
        self.assertFalse(snap["autonomous_dispatch"])
        csv_a = self.desk.route_csv(self.current_monday.isoformat())
        csv_b = self.desk.route_csv(self.current_monday.isoformat())
        self.assertEqual(csv_a, csv_b)
        self.assertIn("makeup_service_date", csv_a.splitlines()[0])
        self.assertIn("PLAN-BETA-HQ", csv_a)
        md = self.desk.route_markdown(self.current_monday.isoformat())
        self.assertIn("| 1 | Acme Coffee Group | Downtown Cafe | Rear 8yd |", md)

    def test_distinct_manifest_operation_does_not_reinitialize_workspace(self):
        with self.assertRaises(StateConflict):
            self.desk.import_manifest(MANIFEST, "manifest-second-key")

    def test_manifest_operation_key_binds_admitted_payload_before_normalization(self):
        exact = self.desk.import_manifest(MANIFEST, "manifest-v2")
        alias = json.loads(json.dumps(MANIFEST))
        alias["customers"][0]["currency"] = "usd"
        with self.assertRaises(OperationConflict):
            self.desk.import_manifest(alias, "manifest-v2")
        whitespace = json.loads(json.dumps(MANIFEST))
        whitespace["customers"][0]["name"] = " Acme Coffee Group "
        with self.assertRaises(OperationConflict):
            self.desk.import_manifest(whitespace, "manifest-v2")
        self.assertEqual(exact, self.desk.import_manifest(MANIFEST, "manifest-v2"))

    def test_manifest_grammar_rejects_unknown_fields_at_every_level(self):
        paths = [
            ([], "unexpected"),
            (["customers", 0], "unexpected"),
            (["customers", 0, "sites", 0], "unexpected"),
            (["customers", 0, "sites", 0, "containers", 0], "unexpected"),
            (
                [
                    "customers",
                    0,
                    "sites",
                    0,
                    "containers",
                    0,
                    "plans",
                    0,
                ],
                "unexpected",
            ),
        ]
        for index, (path, key) in enumerate(paths):
            bad = json.loads(json.dumps(MANIFEST))
            target = bad
            for part in path:
                target = target[part]
            target[key] = f"ignored-{index}"
            with self.subTest(path=path):
                with self.assertRaises(ValidationError):
                    self.desk.import_manifest(bad, "manifest-v2")

    def test_operation_key_exact_retry_and_changed_input_conflict(self):
        route = self._monday_route()
        stop = route["stops"][0]["id"]
        result = self.desk.record_stop(stop, "SERVICED", "outcome-1")
        replay = self.desk.record_stop(stop, "SERVICED", "outcome-1")
        self.assertEqual(result, replay)
        with self.assertRaises(OperationConflict):
            self.desk.record_stop(
                stop,
                "SKIPPED",
                "outcome-1",
                exception_code="BLOCKED_ACCESS",
            )

    def test_unresolved_or_pending_service_blocks_invoice(self):
        route = self._monday_route()
        acme_stops = [s for s in route["stops"] if s["customer_id"] == "ACME"]
        self.desk.record_stop(acme_stops[0]["id"], "SERVICED", "acme-service")
        self.desk.record_stop(
            acme_stops[1]["id"],
            "SKIPPED",
            "acme-skip",
            exception_code="BLOCKED_ACCESS",
        )
        with self.assertRaises(BillingBlocked):
            self.desk.draft_invoice(
                "ACME",
                self.current_monday.isoformat(),
                self.current_monday.isoformat(),
                "inv-acme",
            )
        self.desk.resolve_exception(
            acme_stops[1]["id"], "NO_SERVICE_NO_CHARGE", "acme-resolve"
        )
        invoice = self.desk.draft_invoice(
            "ACME",
            self.current_monday.isoformat(),
            self.current_monday.isoformat(),
            "inv-acme",
        )
        self.assertEqual(invoice["total_minor"], 12900)
        self.assertEqual(invoice["business_date"], self.today.isoformat())
        self.assertFalse(invoice["payment_mutation"])
        self.assertEqual(len(invoice["lines"]), 2)
        self.assertEqual(
            {line["status"] for line in invoice["lines"]},
            {"SERVICE_CONFIRMED", "RESOLVED_NO_CHARGE"},
        )

    def test_customer_invoice_isolation_and_billable_makeup(self):
        route = self._monday_route()
        acme = [s for s in route["stops"] if s["customer_id"] == "ACME"]
        beta = [s for s in route["stops"] if s["customer_id"] == "BETA"][0]
        self.desk.record_stop(acme[0]["id"], "SERVICED", "a1")
        self.desk.record_stop(
            acme[1]["id"], "SKIPPED", "a2", exception_code="LOCKED_GATE"
        )
        self.desk.resolve_exception(
            acme[1]["id"],
            "MAKEUP_COMPLETED_BILLABLE",
            "a3",
            self.current_monday.isoformat(),
        )
        self.desk.record_stop(beta["id"], "SERVICED", "b1")
        beta_invoice = self.desk.draft_invoice(
            "BETA",
            self.current_monday.isoformat(),
            self.current_monday.isoformat(),
            "binv",
        )
        self.assertEqual(beta_invoice["total_minor"], 14900)
        self.assertEqual(
            {line["customer_id"] for line in beta_invoice["lines"]}, {"BETA"}
        )
        acme_invoice = self.desk.draft_invoice(
            "ACME",
            self.current_monday.isoformat(),
            self.current_monday.isoformat(),
            "ainv",
        )
        self.assertEqual(acme_invoice["total_minor"], 22800)
        makeup_line = [
            line
            for line in acme_invoice["lines"]
            if line["status"] == "RESOLVED_BILLABLE"
        ][0]
        self.assertEqual(
            makeup_line["makeup_service_date"], self.current_monday.isoformat()
        )

    def test_billable_makeup_requires_elapsed_completion_date(self):
        route = self._monday_route(self.prior_monday, "makeup-route")
        stop = [s for s in route["stops"] if s["customer_id"] == "ACME"][0]
        self.desk.record_stop(
            stop["id"], "SKIPPED", "makeup-skip", exception_code="BLOCKED_ACCESS"
        )
        with self.assertRaises(ValidationError):
            self.desk.resolve_exception(
                stop["id"], "MAKEUP_COMPLETED_BILLABLE", "missing-makeup-date"
            )
        with self.assertRaises(StateConflict):
            self.desk.resolve_exception(
                stop["id"],
                "MAKEUP_COMPLETED_BILLABLE",
                "future-makeup-date",
                self.next_monday.isoformat(),
            )
        result = self.desk.resolve_exception(
            stop["id"],
            "MAKEUP_COMPLETED_BILLABLE",
            "valid-makeup-date",
            self.current_monday.isoformat(),
        )
        self.assertEqual(result["status"], "RESOLVED_BILLABLE")
        self.assertEqual(
            result["makeup_service_date"], self.current_monday.isoformat()
        )

    def test_restart_preserves_state_event_history_and_timezone(self):
        route = self._monday_route()
        self.desk.record_stop(
            route["stops"][0]["id"], "SERVICED", "persist-outcome"
        )
        before = self.desk.event_log()
        self.desk.close()
        self.desk = WasteRouteDesk(self.db)
        snap = self.desk.route_snapshot(self.current_monday.isoformat())
        self.assertEqual(snap["stops"][0]["status"], "SERVICE_CONFIRMED")
        self.assertEqual(self.desk.business_date(), self.today)
        after = self.desk.event_log()
        self.assertEqual(before, after)

    def test_event_invoice_and_custody_rows_are_sqlite_immutable(self):
        route = self._monday_route()
        self._settle_customer(route, "ACME", "immutable")
        self.desk.draft_invoice(
            "ACME",
            self.current_monday.isoformat(),
            self.current_monday.isoformat(),
            "immutable-invoice",
        )
        with self.assertRaises(sqlite3.DatabaseError):
            self.desk.conn.execute("UPDATE events SET event_type='FORGED' WHERE id=1")
        with self.assertRaises(sqlite3.DatabaseError):
            self.desk.conn.execute("DELETE FROM events WHERE id=1")
        with self.assertRaises(sqlite3.DatabaseError):
            self.desk.conn.execute(
                "UPDATE invoice_drafts SET total_minor=0 WHERE customer_id='ACME'"
            )
        with self.assertRaises(sqlite3.DatabaseError):
            self.desk.conn.execute("DELETE FROM invoice_lines")
        with self.assertRaises(sqlite3.DatabaseError):
            self.desk.conn.execute(
                "UPDATE workspace_settings SET value='SYSTEM_LOCAL'"
            )

    def test_concurrent_terminal_race_has_one_winner(self):
        route = self._monday_route(self.current_monday, "route-race")
        stop_id = route["stops"][0]["id"]
        barrier = threading.Barrier(2)

        def worker(kind):
            with WasteRouteDesk(self.db) as desk:
                barrier.wait()
                try:
                    if kind == "service":
                        result = desk.record_stop(
                            stop_id, "SERVICED", "race-service"
                        )
                    else:
                        result = desk.record_stop(
                            stop_id,
                            "SKIPPED",
                            "race-skip",
                            exception_code="BLOCKED_ACCESS",
                        )
                    return ("ok", result["status"])
                except StateConflict as exc:
                    return ("conflict", str(exc))

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(worker, ["service", "skip"]))
        self.assertEqual(sorted(r[0] for r in results), ["conflict", "ok"])
        final = self.desk.route_snapshot(self.current_monday.isoformat())
        self.assertIn(
            final["stops"][0]["status"],
            {"SERVICE_CONFIRMED", "EXCEPTION_OPEN"},
        )

