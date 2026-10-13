"""Real-file schedule races, including independent processes and HTTP requests.

Fixtures are synthetic. No customer, provider, payment, or external-calendar calls.
The delayed reader deliberately exposes the old read/check/rewrite race. A fixed
writer holds its per-schedule lock through publication, so the second reader
cannot enter until the first acceptance has completed.
"""

from __future__ import annotations

import csv
import json
import multiprocessing
import os
import queue
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import trade_quote as app


def _attempt(quote, start, schedule):
    try:
        receipt = app.accept_quote(Path(quote), "fixture-token", "2026-09-15", start, Path(schedule))
        return ("accepted", receipt["schedule"]["quote_id"])
    except Exception as exc:
        return (type(exc).__name__, str(exc))


def _process_worker(role, quote, start, schedule, first_read, second_read, results):
    original = app._read_schedule

    def delayed(path):
        rows = original(path)
        if role == "first":
            first_read.set()
            second_read.wait(2)
        else:
            second_read.set()
        return rows

    app._read_schedule = delayed
    if role == "second" and not first_read.wait(10):
        results.put(("harness-error", "first process never reached schedule read"))
        return
    results.put(_attempt(quote, start, schedule))


class ScheduleConcurrencyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.schedule = self.root / "jobs" / "schedule.csv"
        self.first = self.quote("Q-FIRST")
        self.second = self.quote("Q-SECOND")

    def quote(self, quote_id):
        path = self.root / (quote_id + ".json")
        path.write_text(json.dumps({
            "schema": app.SCHEMA, "status": "DRAFT_NOT_SENT",
            "quote_id": quote_id, "request_id": "fixture-" + quote_id,
            "customer": "Synthetic schedule fixture", "service": "interior_painting",
            "valid_until": "2026-09-22", "acceptance_token": "fixture-token",
            "schedule_duration_hours": "1", "total": "100.00", "currency": "USD",
        }), encoding="utf-8")
        return path

    def rows(self, path=None):
        with (path or self.schedule).open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            self.assertEqual(reader.fieldnames, app.SCHEDULE_FIELDS)
            return list(reader)

    def delayed_reader(self):
        first_read, second_read = threading.Event(), threading.Event()
        original = app._read_schedule
        guard = threading.Lock()
        calls = 0

        def delayed(path):
            nonlocal calls
            rows = original(path)
            with guard:
                calls += 1
                first = calls == 1
            if first:
                first_read.set()
                second_read.wait(2)
            else:
                second_read.set()
            return rows

        return delayed, first_read

    def thread_pair(self, second_start, second_schedule=None):
        results = queue.Queue()
        delayed, first_read = self.delayed_reader()
        first = threading.Thread(target=lambda: results.put(_attempt(self.first, "09:00", self.schedule)))
        second = threading.Thread(target=lambda: results.put(_attempt(self.second, second_start, second_schedule or self.schedule)))
        with mock.patch.object(app, "_read_schedule", side_effect=delayed):
            first.start()
            self.assertTrue(first_read.wait(10), "first thread never reached read")
            second.start()
            for worker in (first, second):
                worker.join(10)
                self.assertFalse(worker.is_alive(), "acceptance thread did not complete")
        return [results.get(timeout=1), results.get(timeout=1)]

    def assert_outcomes(self, outcomes, overlap):
        accepted = [item for item in outcomes if item[0] == "accepted"]
        held = [item for item in outcomes if item[0] == "QuoteError"]
        self.assertEqual(len(accepted), 1 if overlap else 2, outcomes)
        self.assertEqual(len(held), 1 if overlap else 0, outcomes)
        if overlap:
            self.assertIn("collision", held[0][1])
        rows = self.rows()
        self.assertEqual({row["quote_id"] for row in rows}, {item[1] for item in accepted})
        self.assertEqual(len(rows), len(accepted))
        for row in rows:
            receipt_path = self.schedule.with_name(row["quote_id"] + "-acceptance.json")
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            self.assertEqual(receipt["schedule"], row)
            self.assertEqual(receipt["messages_sent"], 0)
            self.assertEqual(receipt["external_calendar_writes"], 0)
            self.assertEqual(receipt["payments_collected"], 0)

    def test_concurrent_threads_keep_both_nonoverlapping_jobs(self):
        self.assert_outcomes(self.thread_pair("11:00"), overlap=False)

    def test_concurrent_threads_accept_only_one_overlapping_job(self):
        self.assert_outcomes(self.thread_pair("09:30"), overlap=True)

    def process_pair(self, second_start):
        ctx = multiprocessing.get_context("spawn")
        first_read, second_read, results = ctx.Event(), ctx.Event(), ctx.Queue()
        workers = [
            ctx.Process(target=_process_worker, args=(role, str(quote), start, str(self.schedule), first_read, second_read, results))
            for role, quote, start in (("first", self.first, "09:00"), ("second", self.second, second_start))
        ]
        try:
            for worker in workers:
                worker.start()
            for worker in workers:
                worker.join(15)
                self.assertFalse(worker.is_alive(), "acceptance process did not complete")
                self.assertEqual(worker.exitcode, 0)
            return [results.get(timeout=2), results.get(timeout=2)]
        finally:
            for worker in workers:
                if worker.is_alive():
                    worker.terminate()
                    worker.join(5)
            results.close()
            results.join_thread()

    def test_independent_processes_keep_both_nonoverlapping_jobs(self):
        self.assert_outcomes(self.process_pair("11:00"), overlap=False)

    def test_independent_processes_accept_only_one_overlapping_job(self):
        self.assert_outcomes(self.process_pair("09:30"), overlap=True)

    def test_failed_csv_write_preserves_previous_schedule_and_releases_lock(self):
        self.assertEqual(_attempt(self.first, "09:00", self.schedule)[0], "accepted")
        before = self.schedule.read_bytes()
        sentinel = self.schedule.with_name(self.schedule.name + ".tmp")
        sentinel.write_bytes(b"pre-existing unrelated file")
        with mock.patch.object(csv.DictWriter, "writerows", side_effect=OSError("injected write failure")):
            outcome = _attempt(self.second, "11:00", self.schedule)
        self.assertIn(outcome[0], ("QuoteError", "OSError"), outcome)
        self.assertEqual(self.schedule.read_bytes(), before)
        self.assertEqual(sentinel.read_bytes(), b"pre-existing unrelated file")
        self.assertEqual(list(self.schedule.parent.glob(".schedule.csv.*.tmp")), [])
        self.assertFalse(self.schedule.with_name("Q-SECOND-acceptance.json").exists())
        self.assertEqual(_attempt(self.second, "11:00", self.schedule)[0], "accepted")
        self.assertEqual(len(self.rows()), 2)

    def test_invalid_token_does_not_create_schedule_directory(self):
        with self.assertRaisesRegex(app.QuoteError, "token"):
            app.accept_quote(self.first, "wrong-token", "2026-09-15", "09:00", self.schedule)
        self.assertFalse(self.schedule.parent.exists())

    def test_existing_schedule_mode_survives_update(self):
        self.assertEqual(_attempt(self.first, "09:00", self.schedule)[0], "accepted")
        if os.name == "posix":
            self.schedule.chmod(0o640)
        before_mode = self.schedule.stat().st_mode & 0o777
        self.assertEqual(_attempt(self.second, "11:00", self.schedule)[0], "accepted")
        self.assertEqual(self.schedule.stat().st_mode & 0o777, before_mode)

    def test_equivalent_paths_share_the_same_lock(self):
        alias = self.schedule.parent / "unused" / ".." / self.schedule.name
        (self.schedule.parent / "unused").mkdir(parents=True)
        self.assert_outcomes(self.thread_pair("11:00", alias), overlap=False)

    def test_existing_schema_error_does_not_modify_schedule(self):
        self.schedule.parent.mkdir(parents=True)
        self.schedule.write_bytes(b"wrong,schema\nkeep,these\n")
        before = self.schedule.read_bytes()
        result = _attempt(self.first, "09:00", self.schedule)
        self.assertEqual(result[0], "QuoteError", result)
        self.assertIn("schema", result[1])
        self.assertEqual(self.schedule.read_bytes(), before)

    def test_neighboring_slots_still_both_schedule(self):
        self.assertEqual(_attempt(self.first, "09:00", self.schedule)[0], "accepted")
        self.assertEqual(_attempt(self.second, "10:00", self.schedule)[0], "accepted")
        self.assertEqual(len(self.rows()), 2)

    def test_independent_schedules_do_not_share_a_global_lock(self):
        first_read, release = threading.Event(), threading.Event()
        original = app._read_schedule
        outcomes = queue.Queue()
        other = self.root / "other" / "schedule.csv"

        def delayed(path):
            rows = original(path)
            if path == self.schedule:
                first_read.set()
                if not release.wait(10):
                    raise RuntimeError("unrelated schedule could not finish")
            return rows

        first = threading.Thread(target=lambda: outcomes.put(_attempt(self.first, "09:00", self.schedule)))
        with mock.patch.object(app, "_read_schedule", side_effect=delayed):
            first.start()
            try:
                self.assertTrue(first_read.wait(10))
                second = threading.Thread(target=lambda: outcomes.put(_attempt(self.second, "09:00", other)))
                second.start()
                second.join(5)
                self.assertFalse(second.is_alive(), "unrelated schedule was blocked")
            finally:
                release.set()
                first.join(10)
                if 'second' in locals():
                    second.join(10)
        self.assertEqual([outcomes.get(timeout=1)[0] for _ in range(2)], ["accepted", "accepted"])
        self.assertEqual(len(self.rows()), 1)
        self.assertEqual(len(self.rows(other)), 1)

    def test_concurrent_http_requests_reject_overlap(self):
        delayed, first_read = self.delayed_reader()
        results = queue.Queue()
        server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.make_handler(app.ServeConfig(self.root, self.schedule)))
        serving = threading.Thread(target=server.serve_forever, daemon=True)
        serving.start()
        url = "http://127.0.0.1:%d/accept" % server.server_address[1]

        def post(quote_id, start):
            data = urlencode({"quote": quote_id, "token": "fixture-token", "date": "2026-09-15", "start": start}).encode()
            try:
                with urlopen(Request(url, data=data), timeout=10) as response:
                    results.put((response.status, response.read().decode()))
            except HTTPError as exc:
                results.put((exc.code, exc.read().decode()))
            except Exception as exc:
                results.put((type(exc).__name__, str(exc)))

        workers = [threading.Thread(target=post, args=(qid, start)) for qid, start in (("Q-FIRST", "09:00"), ("Q-SECOND", "09:30"))]
        try:
            with mock.patch.object(app, "_read_schedule", side_effect=delayed):
                workers[0].start()
                self.assertTrue(first_read.wait(10))
                workers[1].start()
                for worker in workers:
                    worker.join(15)
                    self.assertFalse(worker.is_alive())
            responses = [results.get(timeout=1), results.get(timeout=1)]
            self.assertCountEqual([item[0] for item in responses], [200, 400], responses)
            self.assertIn("collision", next(body for status, body in responses if status == 400))
            self.assertEqual(len(self.rows()), 1)
        finally:
            server.shutdown()
            server.server_close()
            serving.join(5)


if __name__ == "__main__":
    unittest.main()
