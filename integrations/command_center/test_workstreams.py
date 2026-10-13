"""Work snapshot semantics; run in cloud CI, never as a workstation build."""
import copy
import tempfile
import unittest
from pathlib import Path

from integrations.command_center.schema import CoreError
from integrations.command_center.workstreams import WorkstreamStore


OLD = "2020-01-01T00:00:00Z"
FIRST = "2026-09-07T20:00:00Z"
SECOND = "2026-09-07T20:01:00Z"


class WorkstreamTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.store = WorkstreamStore(self.path)

    def snapshot(self, operation="sync-1", source="github-work", items=None,
                 complete=True, observed=FIRST, status="ok", error=None):
        return {
            "operation_id": operation,
            "source": {
                "id": source, "provider": "github", "label": "Actual repository work",
                "sync_mode": "direct", "observed_at": observed, "activity_as_of": FIRST,
                "scope": {"repo": "owner/repo"}, "status": status, "error": error,
                "coverage": {"complete": complete, "pagination_remaining": 0 if complete else 1,
                             "notes": []}, "stale_after_seconds": 300,
                "refs": {"ledger": "feature-tracker.json"},
            },
            "items": items if items is not None else [
                {"id": "owner/repo:pull/7", "kind": "build", "title": "Real build",
                 "status": "running", "updated_at": OLD, "activity_observed_at": FIRST,
                 "owner": None, "project": "repo", "amount": 0,
                 "summary": "Checks running", "next_action": None,
                 "refs": {"commit": "a" * 40},
                 "actions": [{"kind": "open", "label": "View run", "url": "https://example.test/run/7"}]}
            ],
        }

    def test_unchanged_snapshot_does_not_invent_work_activity(self):
        self.assertEqual(1, self.store.ingest(self.snapshot())["changed"])
        result = self.store.ingest(self.snapshot("sync-2", observed=SECOND))
        self.assertEqual(0, result["changed"])
        item = self.store.state()["items"][0]
        self.assertEqual(OLD, item["updated_at"])
        self.assertEqual(FIRST, item["activity_observed_at"])
        self.assertEqual(0, item["amount"])
        self.assertIsNone(item["next_action"])

    def test_durable_snapshot_and_owner_job_survive_restart(self):
        self.store.ingest(self.snapshot())
        update = {"operation_id": "owner-1", "source_id": "github-work",
                  "item_id": "owner/repo:pull/7", "priority": 0, "next_action": None,
                  "job": {"instruction": "Inspect existing run",
                          "action": {"tool": "read_run", "route": "shared_gateway"}}}
        first = self.store.update_work(update)
        reopened = WorkstreamStore(self.path)
        item = reopened.state()["items"][0]
        self.assertEqual(0, item["owner_work"]["priority"])
        self.assertIsNone(item["owner_work"]["next_action"])
        self.assertEqual("not_dispatched", item["owner_work"]["job"]["dispatch_status"])
        replay = reopened.update_work(update)
        self.assertTrue(replay["replayed"])
        self.assertEqual(first["work"]["job"]["id"], replay["work"]["job"]["id"])

    def test_partial_snapshot_keeps_unseen_and_complete_snapshot_removes(self):
        self.store.ingest(self.snapshot(items=[{"id": "1"}, {"id": "2"}]))
        partial = self.snapshot("sync-2", items=[{"id": "2", "status": "updated"}],
                                complete=False, observed=SECOND)
        result = self.store.ingest(partial)
        self.assertEqual(1, result["retained"])
        self.assertEqual({"1", "2"}, {item["id"] for item in self.store.state()["items"]})
        self.assertFalse(self.store.state()["sources"][0]["coverage"]["complete"])
        complete = self.snapshot("sync-3", items=[{"id": "2"}], observed=SECOND)
        self.assertEqual(1, self.store.ingest(complete)["removed"])
        self.assertEqual(["2"], [item["id"] for item in self.store.state()["items"]])

    def test_error_preserves_last_good_and_marks_attempt_coverage(self):
        self.store.ingest(self.snapshot())
        failure = self.snapshot("sync-error", items=[], complete=False, observed=SECOND,
                                status="error", error={"message": "Provider unavailable"})
        failure["source"]["activity_as_of"] = None
        result = self.store.ingest(failure)
        self.assertEqual("source_error", result["status"])
        state = WorkstreamStore(self.path).state()
        self.assertEqual(1, len(state["items"]))
        source = state["sources"][0]
        self.assertTrue(source["retained_last_good"])
        self.assertEqual(FIRST, source["last_good_observed_at"])
        self.assertEqual(FIRST, source["activity_as_of"])
        self.assertEqual(SECOND, source["observed_at"])
        self.assertFalse(source["coverage"]["complete"])
        self.assertTrue(source["last_good_coverage"]["complete"])
        self.assertEqual("Provider unavailable", source["error"]["message"])

    def test_item_id_collisions_are_scoped_to_source_and_exact_ids_preserved(self):
        exact = "repo:issue / 0 café"
        self.store.ingest(self.snapshot(items=[{"id": exact, "status": "one"}]))
        self.store.ingest(self.snapshot("sync-other", source="second-source",
                                       items=[{"id": exact, "status": "two"}]))
        self.store.update_work({"operation_id": "owner-one", "source_id": "github-work",
                                "item_id": exact, "priority": "next"})
        rows = self.store.state()["items"]
        self.assertEqual([exact, exact], [item["id"] for item in rows])
        self.assertEqual(["one", "two"], [item["status"] for item in rows])
        self.assertEqual("next", rows[0]["owner_work"]["priority"])
        self.assertIsNone(rows[1]["owner_work"])

    def test_operation_id_replay_and_changed_payload_conflict_are_durable(self):
        first = self.snapshot()
        self.store.ingest(first)
        reopened = WorkstreamStore(self.path)
        self.assertTrue(reopened.ingest(first)["replayed"])
        altered = copy.deepcopy(first)
        altered["items"][0]["status"] = "done"
        with self.assertRaises(CoreError) as caught:
            reopened.ingest(altered)
        self.assertEqual(409, caught.exception.status)
        self.assertEqual("running", reopened.state()["items"][0]["status"])
        with self.assertRaises(CoreError) as caught:
            reopened.update_work({"operation_id": "sync-1", "source_id": "github-work",
                                  "item_id": "owner/repo:pull/7", "priority": 1})
        self.assertEqual(409, caught.exception.status)

    def test_actual_activity_change_is_preserved_without_touching_vm_files(self):
        self.store.ingest(self.snapshot())
        changed = self.snapshot("sync-2", observed=SECOND)
        changed["items"][0]["updated_at"] = SECOND
        changed["items"][0]["activity_observed_at"] = SECOND
        self.assertEqual(1, self.store.ingest(changed)["changed"])
        self.assertEqual(SECOND, self.store.state()["items"][0]["updated_at"])
        self.assertEqual({"workstreams.sqlite3"}, {p.name for p in self.path.iterdir()})

    def test_stale_uses_source_observation_not_recent_work_timestamp(self):
        sample = self.snapshot(observed=OLD)
        sample["items"][0]["updated_at"] = "2099-01-01T00:00:00Z"
        self.store.ingest(sample)
        self.assertTrue(self.store.state()["sources"][0]["stale"])

    def test_control_rows_do_not_inflate_business_counts(self):
        self.store.ingest(self.snapshot(items=[
            {"id": "controls", "row_type": "control", "control": True},
            {"id": "lead", "kind": "marketing", "stage": "PurchaseIntent",
             "summary": "CRM stage only; outreach and intent still need verification",
             "needs_attention": True},
            {"id": "coverage", "countable": False}]))
        counts = self.store.state()["counts"]
        self.assertEqual(1, counts["work_items"])
        self.assertEqual(2, counts["control_rows"])

    def test_complete_empty_snapshot_removes_items_but_retains_source(self):
        self.store.ingest(self.snapshot())
        self.store.ingest(self.snapshot("empty", items=[], observed=SECOND))
        state = self.store.state()
        self.assertEqual([], state["items"])
        self.assertEqual(1, len(state["sources"]))

    def test_duplicate_ids_and_ambiguous_coverage_rejected_without_state_change(self):
        for sample in (
            self.snapshot(items=[{"id": "1"}, {"id": "1"}]),
            self.snapshot(),
        ):
            if len(sample["items"]) == 1:
                sample["source"]["coverage"]["pagination_remaining"] = 1
            with self.assertRaises(CoreError) as caught:
                self.store.ingest(sample)
            self.assertEqual(400, caught.exception.status)
        self.assertEqual([], self.store.state()["sources"])

    def test_raw_bodies_and_secret_fields_never_persist(self):
        for dangerous in ({"body": "raw email"}, {"access_token": "not-a-real-secret"}):
            sample = self.snapshot()
            sample["items"][0]["metadata"] = dangerous
            with self.assertRaises(CoreError) as caught:
                self.store.ingest(sample)
            self.assertEqual(400, caught.exception.status)
        self.assertEqual([], self.store.state()["items"])

    def test_older_snapshot_and_provider_or_scope_reassignment_conflict(self):
        self.store.ingest(self.snapshot(observed=SECOND))
        cases = [self.snapshot("older", observed=FIRST),
                 self.snapshot("provider", observed=SECOND),
                 self.snapshot("scope", observed=SECOND)]
        cases[1]["source"]["provider"] = "slack"
        cases[2]["source"]["scope"] = {"repo": "different"}
        for sample in cases:
            with self.assertRaises(CoreError) as caught:
                self.store.ingest(sample)
            self.assertEqual(409, caught.exception.status)
        self.assertEqual("github", self.store.state()["sources"][0]["provider"])

    def test_owner_job_cannot_claim_dispatch(self):
        self.store.ingest(self.snapshot())
        with self.assertRaises(CoreError) as caught:
            self.store.update_work({"operation_id": "false-dispatch", "source_id": "github-work",
                                    "item_id": "owner/repo:pull/7", "job": {"status": "running"}})
        self.assertEqual(400, caught.exception.status)
        self.assertIsNone(self.store.state()["items"][0]["owner_work"])

    def test_failed_first_sync_reports_source_without_fake_items(self):
        failure = self.snapshot(items=[], complete=False, status="error",
                                error="Provider unavailable")
        self.store.ingest(failure)
        state = self.store.state()
        self.assertEqual([], state["items"])
        self.assertIsNone(state["sources"][0]["last_success_at"])
        self.assertFalse(state["sources"][0]["retained_last_good"])

    def test_bulk_reconciliation_keeps_history_without_decoding_absent_owner_packets(self):
        from unittest.mock import patch
        from integrations.command_center import workstreams

        rows = [{"id": str(i), "summary": "Retained observation"} for i in range(1025)]
        with patch.object(workstreams, "_now", return_value=FIRST) as clock:
            self.assertEqual(1025, self.store.ingest(self.snapshot(items=rows))["changed"])
            self.store.ingest(self.snapshot("other", source="other", items=[{"id": "0"}]))
            self.store.update_work({"operation_id": "direction", "source_id": "github-work",
                                    "item_id": "0", "priority": 0, "next_action": "Keep this direction"})
            with self.store._db() as db:
                owner_packet = db.execute("SELECT payload FROM owner_work").fetchone()[0]
            clock.return_value = SECOND
            partial = self.snapshot("partial", complete=False, observed=SECOND,
                                    items=[{**rows[0], "status": "done"}, rows[1], {"id": "new"}])
            result = self.store.ingest(partial)
            self.assertEqual((2, 0, 1023), (result["changed"], result["removed"], result["retained"]))
            state = self.store.state()
            current = next(item for item in state["items"]
                           if item["source_id"] == "github-work" and item["id"] == "0")
            self.assertEqual((FIRST, SECOND), (current["first_seen_at"], current["last_seen_at"]))
            self.assertEqual(0, current["owner_work"]["priority"])
            failure = self.snapshot("failed", observed=SECOND, status="error", error="Unavailable",
                                    items=[{"id": "must-not-appear"}])
            failed = self.store.ingest(failure)
            self.assertEqual((0, 0, 1026), (failed["changed"], failed["removed"], failed["retained"]))
            failed_state = self.store.state()
            self.assertEqual(state["items"], failed_state["items"])
            self.assertTrue(failed_state["sources"][0]["retained_last_good"])
            self.assertEqual(SECOND, failed_state["sources"][0]["last_good_observed_at"])
            self.assertFalse(failed_state["sources"][0]["last_good_coverage"]["complete"])
            self.assertEqual({**result, "replayed": True}, self.store.ingest(partial))
            altered = copy.deepcopy(partial)
            altered["items"][0]["status"] = "different"
            with self.assertRaises(CoreError) as caught:
                self.store.ingest(altered)
            self.assertEqual(409, caught.exception.status)
            complete = self.snapshot("complete", observed=SECOND, items=[{"id": "new"}])
            result = self.store.ingest(complete)
            self.assertEqual((0, 1025, 0), (result["changed"], result["removed"], result["retained"]))
            with patch.object(workstreams.json, "loads", wraps=workstreams.json.loads) as loads:
                state = WorkstreamStore(self.path).state()
            self.assertEqual([("github-work", "new"), ("other", "0")],
                             [(item["source_id"], item["id"]) for item in state["items"]])
            self.assertTrue(all(item["owner_work"] is None for item in state["items"]))
            self.assertNotIn(owner_packet, [call.args[0] for call in loads.call_args_list])
            with self.store._db() as db:
                self.assertEqual(owner_packet, db.execute("SELECT payload FROM owner_work").fetchone()[0])
                self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='incoming_work_items'").fetchone())
                self.assertIsNone(db.execute("SELECT name FROM sqlite_temp_master WHERE name='incoming_work_items'").fetchone())
            self.assertEqual(1, self.store.ingest(self.snapshot("empty", items=[], observed=SECOND))["removed"])
            self.assertEqual(0, self.store.ingest(self.snapshot("partial-empty", items=[], complete=False,
                                                              observed=SECOND))["retained"])
            self.store.ingest(self.snapshot("returns", items=[rows[0]], observed=SECOND))
            restored = self.store.state()["items"][0]
            self.assertEqual("github-work", restored["source_id"])
            self.assertEqual(0, restored["owner_work"]["priority"])
            self.assertEqual("Keep this direction", restored["owner_work"]["next_action"])


if __name__ == "__main__":
    unittest.main()
