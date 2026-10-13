"""Real SQLite, restart, process-death and concurrent-send delivery regressions."""
import copy
import json
import multiprocessing
import os
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest import mock

from host import slack_mirror_state as state

PARTS = ["first part", "second part", "last part"]
CHANNEL = "C0123456789"


def concurrent_worker(db_path, barrier, output, accepted):
    try:
        store = state.MirrorStore(db_path)
        barrier.wait(10)
        def sender(text, thread):
            with open(accepted, "a", encoding="utf-8") as stream:
                stream.write(text + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            time.sleep(0.15)
            return "1789458400.000001"
        output.put(("ok", store.send("concurrent", ["only"], sender, channel=CHANNEL)))
    except state.DeliveryUncertain:
        output.put(("uncertain", None))
    except BaseException as exc:
        output.put(("error", type(exc).__name__))


def dying_worker(db_path, accepted):
    store = state.MirrorStore(db_path)
    def sender(text, thread):
        with open(accepted, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os._exit(17)
    store.send("death", ["accepted before crash"], sender, channel=CHANNEL)


class MirrorStateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "receipts.sqlite3"
        self.store = state.MirrorStore(self.path)
        self.calls = []

    def sender(self, text, thread):
        self.calls.append((text, thread))
        return f"1789458400.{len(self.calls):06d}"

    def send(self, parts=None, source="post", channel=CHANNEL, thread=""):
        return self.store.send(source, PARTS if parts is None else parts, self.sender,
                               channel=channel, thread_ts=thread)

    def snapshot(self, parts=None, source="post"):
        return self.store.inspect(source, PARTS if parts is None else parts, channel=CHANNEL)

    def uncertain(self):
        def broken(text, thread):
            self.calls.append((text, thread))
            if len(self.calls) == 2:
                raise TimeoutError("do not persist token=SECRET")
            return f"1789458400.{len(self.calls):06d}"
        with self.assertRaises(state.DeliveryUncertain):
            self.store.send("post", PARTS, broken, channel=CHANNEL)
        return self.snapshot()["in_flight"]

    def test_exact_restart_reuses_all_native_receipts(self):
        first = self.send()
        self.store = state.MirrorStore(self.path)
        self.assertEqual(self.send(), first)
        self.assertEqual(len(self.calls), 3)
        self.assertEqual(self.snapshot()["state"], "COMPLETE")
        self.assertEqual(self.calls, [(PARTS[0], ""), (PARTS[1], first[0]), (PARTS[2], first[0])])

    def test_single_part_remains_root(self):
        self.send(["only"])
        self.assertEqual(self.calls, [("only", "")])

    def test_explicit_thread_preserved_for_every_part(self):
        self.send(thread="1789000000.000001")
        self.assertEqual({thread for _, thread in self.calls}, {"1789000000.000001"})

    def test_destinations_do_not_collide(self):
        self.send(["only"])
        self.send(["only"], channel="C9876543210")
        self.assertEqual(len(self.calls), 2)

    def test_initial_threads_do_not_collide(self):
        self.send(["only"], thread="1789000000.000001")
        self.send(["only"], thread="1789000000.000002")
        self.assertEqual(len(self.calls), 2)

    def test_explicit_new_event_is_a_new_delivery(self):
        self.send(["only"])
        self.send(["only"], source="post-v2")
        self.assertEqual(len(self.calls), 2)

    def test_changed_body_conflicts_without_send(self):
        self.send()
        with self.assertRaises(state.DeliveryConflict):
            self.send([PARTS[0], "different", PARTS[2]])
        self.assertEqual(len(self.calls), 3)

    def test_changed_chunk_boundaries_conflict(self):
        self.send(["ab", "cd"])
        with self.assertRaises(state.DeliveryConflict):
            self.send(["a", "bcd"])
        self.assertEqual(len(self.calls), 2)

    def test_uncertain_attempt_blocks_restart_and_keeps_first_receipt(self):
        self.uncertain()
        self.store = state.MirrorStore(self.path)
        with self.assertRaises(state.DeliveryUncertain):
            self.send()
        snapshot = self.snapshot()
        self.assertEqual(snapshot["receipts"], ["1789458400.000001"])
        self.assertEqual(snapshot["in_flight"]["part"], 1)
        self.assertNotIn("SECRET", json.dumps(snapshot))
        self.assertEqual(len(self.calls), 2)

    def test_native_accepted_reconciliation_resumes_only_unsent_tail(self):
        pending = self.uncertain()
        self.store.reconcile("post", PARTS, channel=CHANNEL, part=2,
            attempt=pending["attempt"], accepted_ts="1789458400.000002",
            evidence="native channel permalink for accepted second part")
        self.assertEqual(self.send(), ["1789458400.000001", "1789458400.000002", "1789458400.000003"])
        self.assertEqual(len(self.calls), 3)
        self.assertEqual(self.calls[-1], (PARTS[2], "1789458400.000001"))
        self.assertEqual(self.snapshot()["reconciliations"][0]["result"], "ACCEPTED")

    def test_not_sent_reconciliation_retries_only_pending_part(self):
        pending = self.uncertain()
        self.store.reconcile("post", PARTS, channel=CHANNEL, part=2,
            attempt=pending["attempt"], not_sent=True,
            evidence="operator inspected native delivery evidence; original worker stopped")
        self.send()
        self.assertEqual([text for text, _ in self.calls], [PARTS[0], PARTS[1], PARTS[1], PARTS[2]])
        self.assertEqual(self.snapshot()["reconciliations"][0]["result"], "NOT_SENT")

    def test_stale_reconciliation_cannot_resolve_new_attempt(self):
        pending = self.uncertain()
        kwargs = dict(channel=CHANNEL, part=2, attempt=pending["attempt"], not_sent=True, evidence="native evidence")
        self.store.reconcile("post", PARTS, **kwargs)
        def broken(*_):
            raise TimeoutError()
        with self.assertRaises(state.DeliveryUncertain):
            self.store.send("post", PARTS, broken, channel=CHANNEL)
        with self.assertRaises(state.DeliveryConflict):
            self.store.reconcile("post", PARTS, **kwargs)

    def test_wrong_part_and_wrong_attempt_rejected(self):
        pending = self.uncertain()
        for part, attempt in ((1, pending["attempt"]), (2, "0" * 32)):
            with self.subTest(part=part), self.assertRaises(state.DeliveryConflict):
                self.store.reconcile("post", PARTS, channel=CHANNEL, part=part,
                    attempt=attempt, accepted_ts="1789458400.000002", evidence="native evidence")

    def test_reconciliation_requires_evidence_and_exactly_one_result(self):
        pending = self.uncertain()
        base = dict(channel=CHANNEL, part=2, attempt=pending["attempt"], evidence="native evidence")
        for patch in ({}, {"not_sent": True, "accepted_ts": "1789458400.000002"},
                      {"accepted_ts": "1789458400.000002", "evidence": ""}):
            with self.subTest(patch=patch), self.assertRaises(state.DeliveryError):
                self.store.reconcile("post", PARTS, **{**base, **patch})

    def test_wrong_payload_reconciliation_rejected(self):
        pending = self.uncertain()
        with self.assertRaises(state.DeliveryConflict):
            self.store.reconcile("post", ["changed"], channel=CHANNEL, part=2,
                attempt=pending["attempt"], not_sent=True, evidence="native evidence")

    def test_duplicate_native_receipt_does_not_advance_progress(self):
        with self.assertRaises(state.DeliveryUncertain):
            self.store.send("post", PARTS, lambda *_: "1789458400.000001", channel=CHANNEL)
        self.assertEqual(len(self.snapshot()["receipts"]), 1)
        self.assertEqual(self.snapshot()["in_flight"]["part"], 1)

    def test_invalid_success_response_retains_uncertain_intent(self):
        with self.assertRaises(state.DeliveryUncertain):
            self.store.send("post", PARTS, lambda *_: "None", channel=CHANNEL)
        self.assertEqual(self.snapshot()["receipts"], [])
        self.assertIsNotNone(self.snapshot()["in_flight"])

    def test_definite_rejection_is_retryable_and_preserves_prior_progress(self):
        calls = []
        def reject(text, thread):
            calls.append(text)
            if len(calls) == 2:
                raise state.RejectedSend("not_in_channel")
            return "1789458400.000001"
        with self.assertRaises(state.RejectedSend):
            self.store.send("post", PARTS, reject, channel=CHANNEL)
        self.assertIsNone(self.snapshot()["in_flight"])
        self.calls.append((PARTS[0], ""))
        self.send()
        self.assertEqual([x[0] for x in self.calls], PARTS)

    def test_rate_limit_retry_after_survives_restart(self):
        with mock.patch.object(state.time, "time", return_value=1000):
            with self.assertRaises(state.RejectedSend):
                self.store.send("post", PARTS,
                    lambda *_: (_ for _ in ()).throw(state.RejectedSend("rate_limited", 30)), channel=CHANNEL)
        self.store = state.MirrorStore(self.path)
        with mock.patch.object(state.time, "time", return_value=1029):
            with self.assertRaises(state.RejectedSend) as caught:
                self.send()
            self.assertEqual(caught.exception.retry_after, 1)
            self.assertEqual(self.calls, [])
        with mock.patch.object(state.time, "time", return_value=1030):
            self.send()
        self.assertEqual(len(self.calls), 3)

    def test_actual_process_death_leaves_durable_intent(self):
        accepted = str(Path(self.temp.name) / "accepted.txt")
        ctx = multiprocessing.get_context("spawn")
        child = ctx.Process(target=dying_worker, args=(str(self.path), accepted))
        child.start()
        child.join(15)
        if child.is_alive():
            child.kill()
            child.join()
            self.fail("crash test child did not exit")
        self.assertEqual(child.exitcode, 17)
        self.assertEqual(Path(accepted).read_text(), "accepted before crash")
        with self.assertRaises(state.DeliveryUncertain):
            self.store.send("death", ["accepted before crash"], self.sender, channel=CHANNEL)
        self.assertEqual(self.calls, [])

    def test_two_processes_make_only_one_transport_call(self):
        ctx = multiprocessing.get_context("spawn")
        barrier, output = ctx.Barrier(2), ctx.Queue()
        accepted = str(Path(self.temp.name) / "calls.txt")
        workers = [ctx.Process(target=concurrent_worker, args=(str(self.path), barrier, output, accepted)) for _ in range(2)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(15)
            if worker.is_alive():
                worker.kill()
                worker.join()
                self.fail("concurrent child did not exit")
            self.assertEqual(worker.exitcode, 0)
        outcomes = [output.get(timeout=2)[0] for _ in workers]
        self.assertIn("ok", outcomes)
        self.assertNotIn("error", outcomes)
        self.assertEqual(Path(accepted).read_text().splitlines(), ["only"])
        self.assertEqual(self.store.send("concurrent", ["only"], self.sender, channel=CHANNEL), ["1789458400.000001"])
        self.assertEqual(self.calls, [])
        output.close()
        output.join_thread()

    def mutate_record(self, mutator):
        self.send()
        with sqlite3.connect(self.path) as db:
            key, raw = db.execute("SELECT event_key,record FROM deliveries").fetchone()
            record = json.loads(raw)
            changed = mutator(record)
            db.execute("UPDATE deliveries SET record=? WHERE event_key=?", (changed, key))
        before = self.path.read_bytes()
        with self.assertRaises(state.DeliveryError):
            self.send()
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(len(self.calls), 3)

    def test_duplicate_json_keys_rejected_without_replacing_state(self):
        self.mutate_record(lambda r: '{"version":1,' + json.dumps(r)[1:])

    def test_unknown_record_version_rejected(self):
        self.mutate_record(lambda r: json.dumps({**r, "version": 2}))

    def test_boolean_record_version_rejected(self):
        self.mutate_record(lambda r: json.dumps({**r, "version": True}))

    def test_nonfinite_retry_state_rejected(self):
        self.mutate_record(lambda r: json.dumps({**r, "retry_at_ms": float("nan")}))

    def test_fingerprint_tamper_rejected(self):
        self.mutate_record(lambda r: json.dumps({**r, "payload_sha256": "0" * 64}))

    def test_receipt_count_corruption_rejected(self):
        self.mutate_record(lambda r: json.dumps({**r, "receipts": r["receipts"] + ["1789458400.999999"]}))

    def test_unknown_database_version_preserved(self):
        with sqlite3.connect(self.path) as db:
            db.execute("PRAGMA user_version=99")
        before = self.path.read_bytes()
        with self.assertRaises(state.DeliveryError):
            state.MirrorStore(self.path)
        self.assertEqual(self.path.read_bytes(), before)

    def test_schema_changed_after_open_is_rejected_before_send(self):
        with sqlite3.connect(self.path) as db:
            db.execute("PRAGMA application_id=123")
        with self.assertRaises(state.DeliveryError):
            self.send()
        self.assertEqual(self.calls, [])

    def test_non_database_bytes_are_preserved(self):
        path = Path(self.temp.name) / "corrupt.sqlite3"
        path.write_bytes(b"not a database\x00private-data")
        with self.assertRaises(state.DeliveryError):
            state.MirrorStore(path)
        self.assertEqual(path.read_bytes(), b"not a database\x00private-data")

    def test_symlink_state_rejected_without_touching_target(self):
        target = Path(self.temp.name) / "other.txt"
        target.write_text("preserve")
        link = Path(self.temp.name) / "link.sqlite3"
        link.symlink_to(target)
        with self.assertRaises(state.DeliveryError):
            state.MirrorStore(link)
        self.assertEqual(target.read_text(), "preserve")

    def test_invalid_parts_never_invoke_sender(self):
        for parts in ([], [""], [None], ["\ud800"], ["x"] * (state.MAX_PARTS + 1), ("tuple",)):
            with self.subTest(kind=type(parts).__name__), self.assertRaises(state.DeliveryError):
                self.store.send("post", parts, self.sender, channel=CHANNEL)
        self.assertEqual(self.calls, [])

    def test_mutating_caller_parts_after_first_send_cannot_change_later_parts(self):
        parts = list(PARTS)
        def mutate(text, thread):
            ts = self.sender(text, thread)
            parts[1] = "caller changed this"
            return ts
        self.store.send("post", parts, mutate, channel=CHANNEL)
        self.assertEqual([text for text, _ in self.calls], PARTS)
        self.assertEqual(self.snapshot()["state"], "COMPLETE")

    def test_absent_status_does_not_create_delivery_row(self):
        self.assertEqual(self.snapshot()["state"], "ABSENT")
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM deliveries").fetchone()[0], 0)

    def test_credentials_and_bodies_are_not_retained(self):
        self.send(["sensitive-body-sentinel"])
        raw = self.path.read_bytes()
        self.assertNotIn(b"sensitive-body-sentinel", raw)
        self.assertEqual(self.snapshot(["sensitive-body-sentinel"])["state"], "COMPLETE")

    def test_default_path_respects_configuration(self):
        with mock.patch.dict(os.environ, {"COMMONS_SLACK_MIRROR_STATE": str(self.path)}):
            self.assertEqual(state.default_state_path(), self.path)
        with mock.patch.dict(os.environ, {"COMMONS_SLACK_MIRROR_STATE": "", "XDG_STATE_HOME": self.temp.name}):
            self.assertEqual(state.default_state_path(), Path(self.temp.name) / "commons" / "slack-mirror.sqlite3")


if __name__ == "__main__":
    unittest.main()
