from __future__ import annotations

import json
from contextlib import closing
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path

from workspace import Conflict, FieldServiceWorkspace, InvalidState, NotFound, WorkspaceError, _digest, verify_digest_envelope

TOKEN_A = "customer-token-A-0123456789abcdef0123456789abcdef"
TOKEN_B = "customer-token-B-0123456789abcdef0123456789abcdef"


def base_items():
    return [
        {"item_id": "labor", "description": "Diagnostic and repair labor", "quantity": 2, "unit_cents": 12_500},
        {"item_id": "part", "description": "Replacement component", "quantity": 1, "unit_cents": 8_750},
    ]


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "workspace.db"
        self.ws = FieldServiceWorkspace(self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def create(self, quote_id="q-1", token=TOKEN_A, request_key="create-1"):
        return self.ws.create_quote(
            quote_id=quote_id,
            currency="USD",
            customer_token=token,
            items=base_items(),
            created_at="2026-09-13T10:00:00Z",
            request_key=request_key,
        )

    def publish(self, quote_id="q-1", request_key="publish-1"):
        return self.ws.publish_quote(
            quote_id=quote_id,
            published_at="2026-09-13T10:01:00Z",
            request_key=request_key,
        )

    def approve(self, quote_id="q-1", token=TOKEN_A, request_key="approve-1"):
        quote_digest = self.ws.customer_quote(quote_id=quote_id, customer_token=token)["quote_digest"]
        return self.ws.customer_decide_quote(
            quote_id=quote_id,
            customer_token=token,
            expected_quote_digest=quote_digest,
            decision="APPROVE",
            decided_at="2026-09-13T10:02:00Z",
            request_key=request_key,
        )

    def approved_job(self, quote_id="q-1", token=TOKEN_A):
        self.create(quote_id, token, f"create-{quote_id}")
        self.publish(quote_id, f"publish-{quote_id}")
        return self.approve(quote_id, token, f"approve-{quote_id}")["job_id"]

    def schedule(self, job_id, resource="tech-1", start="2026-09-13T11:00:00Z", end="2026-09-13T12:00:00Z", request_key="schedule-1"):
        return self.ws.schedule_job(
            job_id=job_id,
            resource_id=resource,
            start_at=start,
            end_at=end,
            scheduled_at="2026-09-13T10:03:00Z",
            request_key=request_key,
        )

    def complete_all_scope(self, job_id, prefix="done"):
        export = self.ws.job_export(job_id=job_id)
        for index, item in enumerate(export["scope"]):
            self.ws.complete_scope_item(
                job_id=job_id,
                scope_key=item["scope_key"],
                completed_at=f"2026-09-13T12:{index:02d}:00Z",
                request_key=f"{prefix}-{index}",
            )

    def test_quote_total_exact_integer_cents(self):
        result = self.create()
        self.assertEqual(result["total_cents"], 33_750)
        self.assertIs(type(result["total_cents"]), int)

    def test_customer_view_happy_path(self):
        self.create(); self.publish()
        snapshot = self.ws.customer_quote(quote_id="q-1", customer_token=TOKEN_A)
        self.assertEqual(snapshot["state"], "OPEN")
        self.assertEqual(snapshot["total_cents"], 33_750)
        self.assertEqual(len(snapshot["items"]), 2)
        self.assertFalse(snapshot["payment_authorized"])

    def test_wrong_token_is_not_found_without_state(self):
        self.create(); self.publish()
        with self.assertRaises(NotFound):
            self.ws.customer_quote(quote_id="q-1", customer_token=TOKEN_B)
        with self.assertRaises(NotFound):
            self.ws.customer_quote(quote_id="does-not-exist", customer_token=TOKEN_B)

    def test_raw_customer_token_not_persisted(self):
        self.create(); self.publish()
        raw = TOKEN_A.encode("utf-8")
        self.assertNotIn(raw, self.db.read_bytes())
        with closing(sqlite3.connect(self.db)) as conn:
            token_digest = conn.execute("SELECT token_digest FROM quotes WHERE quote_id='q-1'").fetchone()[0]
        self.assertNotEqual(token_digest, TOKEN_A)
        self.assertEqual(len(token_digest), 64)

    def test_float_money_rejected(self):
        items = base_items(); items[0]["unit_cents"] = 12_500.0
        with self.assertRaises(WorkspaceError):
            self.ws.create_quote(quote_id="q", currency="USD", customer_token=TOKEN_A, items=items, created_at="2026-09-13T10:00:00Z", request_key="r")

    def test_bool_money_rejected(self):
        items = base_items(); items[0]["unit_cents"] = True
        with self.assertRaises(WorkspaceError):
            self.ws.create_quote(quote_id="q", currency="USD", customer_token=TOKEN_A, items=items, created_at="2026-09-13T10:00:00Z", request_key="r")

    def test_duplicate_line_item_rejected(self):
        items = base_items(); items[1]["item_id"] = "labor"
        with self.assertRaises(WorkspaceError):
            self.ws.create_quote(quote_id="q", currency="USD", customer_token=TOKEN_A, items=items, created_at="2026-09-13T10:00:00Z", request_key="r")

    def test_noncanonical_time_rejected(self):
        with self.assertRaises(WorkspaceError):
            self.ws.create_quote(quote_id="q", currency="USD", customer_token=TOKEN_A, items=base_items(), created_at="2026-09-13T10:00:00+00:00", request_key="r")

    def test_exact_request_replay_returns_same_result(self):
        first = self.create()
        second = self.create()
        self.assertEqual(first, second)
        with closing(sqlite3.connect(self.db)) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM quotes").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM audit_events WHERE event_kind='QUOTE_CREATED'").fetchone()[0], 1)

    def test_request_key_changed_payload_conflicts(self):
        self.create(request_key="same-key")
        changed = base_items(); changed[0]["quantity"] = 3
        with self.assertRaises(Conflict):
            self.ws.create_quote(quote_id="q-1", currency="USD", customer_token=TOKEN_A, items=changed, created_at="2026-09-13T10:00:00Z", request_key="same-key")

    def test_approval_creates_exactly_one_job(self):
        self.create(); self.publish()
        first = self.approve()
        second = self.approve(request_key="approve-new-key")
        self.assertEqual(first["job_id"], second["job_id"])
        with closing(sqlite3.connect(self.db)) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM scope_items").fetchone()[0], 2)

    def test_decline_never_creates_job_and_cannot_flip(self):
        self.create(); self.publish()
        out = self.ws.customer_decide_quote(quote_id="q-1", customer_token=TOKEN_A, expected_quote_digest=self.ws.customer_quote(quote_id="q-1", customer_token=TOKEN_A)["quote_digest"], decision="DECLINE", decided_at="2026-09-13T10:02:00Z", request_key="decline")
        self.assertIsNone(out["job_id"])
        with self.assertRaises(Conflict):
            self.approve(request_key="late-approve")
        with closing(sqlite3.connect(self.db)) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0], 0)

    def test_cross_quote_token_cannot_read_or_approve(self):
        self.create("q-a", TOKEN_A, "create-a"); self.publish("q-a", "pub-a")
        self.create("q-b", TOKEN_B, "create-b"); self.publish("q-b", "pub-b")
        with self.assertRaises(NotFound):
            self.ws.customer_quote(quote_id="q-b", customer_token=TOKEN_A)
        with self.assertRaises(NotFound):
            self.ws.customer_decide_quote(quote_id="q-b", customer_token=TOKEN_A, expected_quote_digest=self.ws.customer_quote(quote_id="q-b", customer_token=TOKEN_B)["quote_digest"], decision="APPROVE", decided_at="2026-09-13T10:02:00Z", request_key="wrong-token")


    def test_quote_fingerprint_mismatch_blocks_customer_approval(self):
        self.create(); self.publish()
        with self.assertRaises(Conflict):
            self.ws.customer_decide_quote(
                quote_id="q-1",
                customer_token=TOKEN_A,
                expected_quote_digest="0" * 64,
                decision="APPROVE",
                decided_at="2026-09-13T10:02:00Z",
                request_key="bad-fingerprint",
            )
        self.assertEqual(self.ws.customer_quote(quote_id="q-1", customer_token=TOKEN_A)["state"], "OPEN")

    def test_change_fingerprint_mismatch_blocks_customer_approval(self):
        job = self.approved_job(); self.schedule(job)
        proposed = self.ws.propose_change(
            job_id=job, change_id="co-fp",
            items=[{"item_id": "extra", "description": "Extra", "quantity": 1, "unit_cents": 5_000}],
            proposed_at="2026-09-13T10:10:00Z", request_key="pc-fp"
        )
        with self.assertRaises(Conflict):
            self.ws.customer_decide_change(
                job_id=job, change_id="co-fp", customer_token=TOKEN_A, expected_change_digest="0" * 64,
                decision="APPROVE", decided_at="2026-09-13T10:11:00Z", request_key="bad-co-fingerprint"
            )
        snapshot = self.ws.customer_quote(quote_id="q-1", customer_token=TOKEN_A)
        self.assertEqual(snapshot["changes"][0]["state"], "PENDING")
        self.assertEqual(snapshot["changes"][0]["change_digest"], proposed["change_digest"])

    def test_customer_change_view_contains_exact_line_items(self):
        job = self.approved_job(); self.schedule(job)
        self.ws.propose_change(
            job_id=job, change_id="co-visible",
            items=[{"item_id": "extra", "description": "Visible added scope", "quantity": 2, "unit_cents": 2_500}],
            proposed_at="2026-09-13T10:10:00Z", request_key="pc-visible"
        )
        change = self.ws.customer_quote(quote_id="q-1", customer_token=TOKEN_A)["changes"][0]
        self.assertEqual(change["items"][0]["description"], "Visible added scope")
        self.assertEqual(change["items"][0]["total_cents"], 5_000)

    def test_schedule_rejects_overlap_but_allows_adjacent_half_open(self):
        a = self.approved_job("q-a", TOKEN_A)
        b = self.approved_job("q-b", TOKEN_B)
        self.schedule(a, resource="tech-1", start="2026-09-13T11:00:00Z", end="2026-09-13T12:00:00Z", request_key="sa")
        with self.assertRaises(Conflict):
            self.schedule(b, resource="tech-1", start="2026-09-13T11:30:00Z", end="2026-09-13T12:30:00Z", request_key="sb")
        self.schedule(b, resource="tech-1", start="2026-09-13T12:00:00Z", end="2026-09-13T13:00:00Z", request_key="sb2")

    def test_schedule_change_on_same_job_conflicts(self):
        job = self.approved_job()
        self.schedule(job)
        with self.assertRaises(Conflict):
            self.schedule(job, resource="tech-2", request_key="schedule-different")

    def test_concurrent_overlapping_schedule_allows_one(self):
        a = self.approved_job("q-a", TOKEN_A)
        b = self.approved_job("q-b", TOKEN_B)
        barrier = threading.Barrier(2)
        results = []
        lock = threading.Lock()

        def runner(job_id, key):
            barrier.wait()
            try:
                self.schedule(job_id, resource="tech-race", request_key=key)
                value = "ok"
            except Conflict:
                value = "conflict"
            with lock:
                results.append(value)

        t1 = threading.Thread(target=runner, args=(a, "race-a"))
        t2 = threading.Thread(target=runner, args=(b, "race-b"))
        t1.start(); t2.start(); t1.join(); t2.join()
        self.assertEqual(sorted(results), ["conflict", "ok"])

    def test_schedule_timestamps_cannot_predate_job_approval(self):
        job = self.approved_job()
        with self.assertRaises(WorkspaceError):
            self.ws.schedule_job(
                job_id=job, resource_id="tech-early",
                start_at="2026-09-13T10:01:30Z", end_at="2026-09-13T10:30:00Z",
                scheduled_at="2026-09-13T10:01:00Z", request_key="early-schedule"
            )

    def test_change_cannot_predate_job_approval(self):
        job = self.approved_job()
        with self.assertRaises(WorkspaceError):
            self.ws.propose_change(
                job_id=job, change_id="co-early",
                items=[{"item_id": "x", "description": "Too early", "quantity": 1, "unit_cents": 100}],
                proposed_at="2026-09-13T10:01:30Z", request_key="early-change"
            )

    def test_scope_completion_cannot_predate_schedule_start(self):
        job = self.approved_job(); self.schedule(job)
        scope_key = self.ws.job_export(job_id=job)["scope"][0]["scope_key"]
        with self.assertRaises(WorkspaceError):
            self.ws.complete_scope_item(
                job_id=job, scope_key=scope_key, completed_at="2026-09-13T10:59:59Z", request_key="early-scope"
            )

    def test_job_completion_cannot_predate_latest_scope_completion(self):
        job = self.approved_job(); self.schedule(job)
        scope = self.ws.job_export(job_id=job)["scope"]
        for index, item in enumerate(scope):
            self.ws.complete_scope_item(
                job_id=job, scope_key=item["scope_key"],
                completed_at=f"2026-09-13T12:{20 + index:02d}:00Z", request_key=f"late-scope-{index}"
            )
        with self.assertRaises(WorkspaceError):
            self.ws.complete_job(job_id=job, completed_at="2026-09-13T12:19:00Z", request_key="too-early-job-complete")

    def test_scope_cannot_complete_before_schedule(self):
        job = self.approved_job()
        scope_key = self.ws.job_export(job_id=job)["scope"][0]["scope_key"]
        with self.assertRaises(InvalidState):
            self.ws.complete_scope_item(job_id=job, scope_key=scope_key, completed_at="2026-09-13T12:00:00Z", request_key="premature")

    def test_change_order_does_not_change_scope_until_approved(self):
        job = self.approved_job(); self.schedule(job)
        proposed = self.ws.propose_change(
            job_id=job,
            change_id="co-1",
            items=[{"item_id": "extra", "description": "Additional approved repair", "quantity": 1, "unit_cents": 5_000}],
            proposed_at="2026-09-13T10:10:00Z",
            request_key="propose-co",
        )
        before = self.ws.job_export(job_id=job)
        self.assertEqual(len(before["scope"]), 2)
        self.ws.customer_decide_change(job_id=job, change_id="co-1", customer_token=TOKEN_A, expected_change_digest=proposed["change_digest"], decision="APPROVE", decided_at="2026-09-13T10:11:00Z", request_key="approve-co")
        after = self.ws.job_export(job_id=job)
        self.assertEqual(len(after["scope"]), 3)
        self.assertIn("change:co-1:extra", {x["scope_key"] for x in after["scope"]})

    def test_declined_change_never_changes_scope(self):
        job = self.approved_job(); self.schedule(job)
        proposed = self.ws.propose_change(job_id=job, change_id="co-1", items=[{"item_id": "extra", "description": "Extra", "quantity": 1, "unit_cents": 5_000}], proposed_at="2026-09-13T10:10:00Z", request_key="pc")
        self.ws.customer_decide_change(job_id=job, change_id="co-1", customer_token=TOKEN_A, expected_change_digest=proposed["change_digest"], decision="DECLINE", decided_at="2026-09-13T10:11:00Z", request_key="dc")
        self.assertEqual(len(self.ws.job_export(job_id=job)["scope"]), 2)

    def test_wrong_token_cannot_decide_change(self):
        job = self.approved_job(); self.schedule(job)
        proposed = self.ws.propose_change(job_id=job, change_id="co-1", items=[{"item_id": "extra", "description": "Extra", "quantity": 1, "unit_cents": 5_000}], proposed_at="2026-09-13T10:10:00Z", request_key="pc")
        with self.assertRaises(NotFound):
            self.ws.customer_decide_change(job_id=job, change_id="co-1", customer_token=TOKEN_B, expected_change_digest=proposed["change_digest"], decision="APPROVE", decided_at="2026-09-13T10:11:00Z", request_key="wrong")

    def test_pending_change_blocks_job_completion(self):
        job = self.approved_job(); self.schedule(job); self.complete_all_scope(job)
        self.ws.propose_change(job_id=job, change_id="co-1", items=[{"item_id": "extra", "description": "Extra", "quantity": 1, "unit_cents": 5_000}], proposed_at="2026-09-13T12:05:00Z", request_key="pc")
        with self.assertRaises(InvalidState):
            self.ws.complete_job(job_id=job, completed_at="2026-09-13T13:00:00Z", request_key="complete")

    def test_incomplete_approved_scope_blocks_job_completion(self):
        job = self.approved_job(); self.schedule(job)
        with self.assertRaises(InvalidState):
            self.ws.complete_job(job_id=job, completed_at="2026-09-13T13:00:00Z", request_key="complete")

    def test_complete_job_and_invoice_exact_approved_value(self):
        job = self.approved_job(); self.schedule(job)
        proposed = self.ws.propose_change(job_id=job, change_id="co-1", items=[{"item_id": "extra", "description": "Extra", "quantity": 1, "unit_cents": 5_000}], proposed_at="2026-09-13T10:10:00Z", request_key="pc")
        self.ws.customer_decide_change(job_id=job, change_id="co-1", customer_token=TOKEN_A, expected_change_digest=proposed["change_digest"], decision="APPROVE", decided_at="2026-09-13T10:11:00Z", request_key="ac")
        self.complete_all_scope(job)
        completed = self.ws.complete_job(job_id=job, completed_at="2026-09-13T13:00:00Z", request_key="complete")
        self.assertEqual(completed["state"], "COMPLETED")
        invoice = self.ws.invoice_draft(job_id=job)
        self.assertEqual(invoice["total_cents"], 38_750)
        self.assertTrue(invoice["draft_only"])
        self.assertFalse(invoice["send_authorized"])
        self.assertFalse(invoice["payment_authorized"])
        self.assertFalse(invoice["recognized_revenue"])
        body = dict(invoice); digest = body.pop("draft_digest")
        self.assertEqual(_digest(body), digest)
        self.assertTrue(verify_digest_envelope(invoice, "draft_digest"))
        tampered = dict(invoice); tampered["total_cents"] += 1
        self.assertFalse(verify_digest_envelope(tampered, "draft_digest"))

    def test_invoice_before_completion_rejected(self):
        job = self.approved_job(); self.schedule(job)
        with self.assertRaises(InvalidState):
            self.ws.invoice_draft(job_id=job)

    def test_completion_replay_is_idempotent(self):
        job = self.approved_job(); self.schedule(job); self.complete_all_scope(job)
        first = self.ws.complete_job(job_id=job, completed_at="2026-09-13T13:00:00Z", request_key="complete")
        second = self.ws.complete_job(job_id=job, completed_at="2026-09-13T13:00:00Z", request_key="complete")
        third = self.ws.complete_job(job_id=job, completed_at="2026-09-13T13:01:00Z", request_key="complete-new")
        self.assertEqual(first, second)
        self.assertEqual(first["completed_at"], third["completed_at"])

    def test_restart_preserves_authoritative_state(self):
        job = self.approved_job(); self.schedule(job)
        reloaded = FieldServiceWorkspace(self.db)
        snapshot = reloaded.customer_quote(quote_id="q-1", customer_token=TOKEN_A)
        self.assertEqual(snapshot["job"]["job_id"], job)
        self.assertEqual(reloaded.operator_summary()["open_jobs"], 1)

    def test_export_is_deterministic_and_digest_bound(self):
        job = self.approved_job(); self.schedule(job)
        first = self.ws.job_export(job_id=job)
        second = self.ws.job_export(job_id=job)
        self.assertEqual(first, second)
        body = dict(first); digest = body.pop("export_digest")
        self.assertEqual(_digest(body), digest)
        self.assertTrue(verify_digest_envelope(first, "export_digest"))
        body["job"]["state"] = "COMPLETED"
        self.assertNotEqual(_digest(body), digest)
        tampered = dict(first); tampered["job"] = dict(first["job"]); tampered["job"]["state"] = "COMPLETED"
        self.assertFalse(verify_digest_envelope(tampered, "export_digest"))

    def test_operator_summary_does_not_expose_customer_tokens(self):
        self.create(); self.publish()
        summary = self.ws.operator_summary()
        self.assertEqual(summary["open_quotes"], 1)
        self.assertNotIn("token", json.dumps(summary).lower())


if __name__ == "__main__":
    unittest.main()
