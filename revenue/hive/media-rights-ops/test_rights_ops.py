import http.client
import json
import os
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

import rights_export as e
import rights_http as h
import rights_ops as r

MASTER_SHA = "a" * 64
CUT_SHA = "b" * 64
ALT_SHA = "c" * 64


def manifest():
    return {
        "schema": r.SCHEMA,
        "assets": [
            {"asset_id": "master-a", "sha256": MASTER_SHA, "parent_asset_id": None},
            {"asset_id": "cut-a-15s", "sha256": CUT_SHA, "parent_asset_id": "master-a"},
            {"asset_id": "unlicensed-b", "sha256": ALT_SHA, "parent_asset_id": None},
        ],
        "grants": [
            {
                "grant_id": "grant-q4-social",
                "asset_id": "cut-a-15s",
                "authority_ref": "owner-normalized/licensor-sheet-row-17",
                "valid_from": "2026-09-01T00:00:00Z",
                "valid_until": "2026-12-31T23:59:59Z",
                "channels": ["instagram", "youtube"],
                "territories": ["CA", "US"],
            }
        ],
    }


def intent(**changes):
    base = {
        "asset_id": "cut-a-15s",
        "channel": "instagram",
        "territory": "US",
        "starts_at": "2026-10-01T12:00:00Z",
        "ends_at": "2026-10-15T12:00:00Z",
    }
    base.update(changes)
    return base


def placement(req="placement-001", **changes):
    base = intent(**changes)
    base["request_id"] = req
    return base


class DeskTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db = self.root / "desk.sqlite3"
        self.imported = r.import_manifest(self.db, manifest(), "2026-09-15T06:00:00Z")

    def tearDown(self):
        self.tmp.cleanup()

    def _http_post(self, path, payload):
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), h.ApiHandler)
        httpd.db_path = self.db
        httpd.ui_bytes = b"<!doctype html><title>test</title>"
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            conn = http.client.HTTPConnection("127.0.0.1", httpd.server_port, timeout=5)
            try:
                raw = json.dumps(payload, separators=(",", ":")).encode()
                conn.request("POST", path, body=raw, headers={"Content-Type": "application/json"})
                response = conn.getresponse()
                body = json.loads(response.read())
                return response.status, body
            finally:
                conn.close()
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=5)

    def test_import_receipt_and_snapshot(self):
        self.assertEqual(self.imported["status"], "IMPORTED")
        snap = r.snapshot(self.db)
        self.assertEqual(len(snap["assets"]), 3)
        self.assertEqual(len(snap["grants"]), 1)
        self.assertRegex(snap["snapshot_sha256"], r"^[0-9a-f]{64}$")

    def test_exact_asset_grant_ready(self):
        out = r.evaluate(self.db, intent())
        self.assertEqual(out["status"], "READY_ON_SUPPLIED_AUTHORITY")
        self.assertEqual(out["selected_grant_id"], "grant-q4-social")

    def test_parent_grant_does_not_authorize_derivative(self):
        parent_only = manifest()
        parent_only["grants"][0]["asset_id"] = "master-a"
        db = self.root / "parent-only.sqlite3"
        r.import_manifest(db, parent_only, "2026-09-15T06:00:01Z")
        out = r.evaluate(db, intent())
        self.assertEqual(out["status"], "HOLD")
        self.assertEqual(out["reasons"], ["MISSING_GRANT"])
        self.assertIsNone(out["selected_grant_id"])

    def test_http_mutations_are_disabled_and_do_not_write(self):
        before = r.snapshot(self.db)
        status, body = self._http_post("/api/place", {"intent": placement(), "recorded_at": "2026-09-15T06:01:00Z"})
        self.assertEqual(status, 405)
        self.assertIn("CLI", body["error"])
        status, body = self._http_post("/api/revoke", {"grant_id": "grant-q4-social", "revoked_at": "2026-10-05T00:00:00Z"})
        self.assertEqual(status, 405)
        self.assertIn("CLI", body["error"])
        after = r.snapshot(self.db)
        self.assertEqual(after["placements"], [])
        self.assertIsNone(after["grants"][0]["revoked_at"])
        self.assertEqual(before["snapshot_sha256"], after["snapshot_sha256"])

    def test_wrong_channel_holds(self):
        out = r.evaluate(self.db, intent(channel="tiktok"))
        self.assertEqual(out["status"], "HOLD")
        self.assertIn("CHANNEL_NOT_AUTHORIZED", out["reasons"])

    def test_wrong_territory_holds(self):
        out = r.evaluate(self.db, intent(territory="GB"))
        self.assertIn("TERRITORY_NOT_AUTHORIZED", out["reasons"])

    def test_future_window_holds(self):
        out = r.evaluate(self.db, intent(starts_at="2026-08-01T00:00:00Z", ends_at="2026-08-02T00:00:00Z"))
        self.assertIn("WINDOW_NOT_AUTHORIZED", out["reasons"])

    def test_expired_window_holds(self):
        out = r.evaluate(self.db, intent(starts_at="2026-12-31T12:00:00Z", ends_at="2027-01-01T12:00:00Z"))
        self.assertIn("WINDOW_NOT_AUTHORIZED", out["reasons"])

    def test_unlicensed_asset_holds(self):
        out = r.evaluate(self.db, intent(asset_id="unlicensed-b"))
        self.assertEqual(out["reasons"], ["MISSING_GRANT"])

    def test_unknown_asset_fails_closed(self):
        with self.assertRaisesRegex(r.RightsError, "unknown asset_id"):
            r.evaluate(self.db, intent(asset_id="unknown-x"))

    def test_record_and_idempotent_replay(self):
        first = r.record_placement(self.db, placement(), "2026-09-15T06:01:00Z")
        again = r.record_placement(self.db, placement(), "2026-09-15T06:09:00Z")
        self.assertEqual(first["status"], "RECORDED")
        self.assertEqual(again["status"], "IDEMPOTENT_REPLAY")
        self.assertEqual(again["recorded_at"], "2026-09-15T06:01:00Z")
        self.assertEqual(len(r.snapshot(self.db)["placements"]), 1)

    def test_changed_request_replay_rejected(self):
        r.record_placement(self.db, placement(), "2026-09-15T06:01:00Z")
        with self.assertRaisesRegex(r.RightsError, "replay changed"):
            r.record_placement(self.db, placement(channel="youtube"), "2026-09-15T06:02:00Z")

    def test_hold_is_not_recorded(self):
        out = r.record_placement(self.db, placement(channel="tiktok"), "2026-09-15T06:01:00Z")
        self.assertEqual(out["status"], "HOLD")
        self.assertEqual(r.snapshot(self.db)["placements"], [])

    def test_revocation_blocks_new_and_queues_existing(self):
        r.record_placement(self.db, placement(), "2026-09-15T06:01:00Z")
        rev = r.revoke_grant(self.db, "grant-q4-social", "2026-10-05T00:00:00Z")
        self.assertEqual(rev["status"], "REVOKED")
        out = r.evaluate(self.db, intent(starts_at="2026-10-06T00:00:00Z", ends_at="2026-10-07T00:00:00Z"))
        self.assertIn("REVOKED_GRANT", out["reasons"])
        q = r.queues(self.db, "2026-10-05T00:00:00Z", 30)
        self.assertEqual([x["request_id"] for x in q["retraction_review"]], ["placement-001"])

    def test_revocation_is_immutable_and_replayable(self):
        a = r.revoke_grant(self.db, "grant-q4-social", "2026-10-05T00:00:00Z")
        b = r.revoke_grant(self.db, "grant-q4-social", "2026-10-05T00:00:00Z")
        self.assertEqual(a["status"], "REVOKED")
        self.assertEqual(b["status"], "IDEMPOTENT_REPLAY")
        with self.assertRaisesRegex(r.RightsError, "immutable"):
            r.revoke_grant(self.db, "grant-q4-social", "2026-10-06T00:00:00Z")

    def test_renewal_and_expiry_queue(self):
        q1 = r.queues(self.db, "2026-12-10T00:00:00Z", 30)
        self.assertEqual(q1["renewal_review"][0]["state"], "EXPIRING")
        q2 = r.queues(self.db, "2027-01-05T00:00:00Z", 30)
        self.assertEqual(q2["renewal_review"][0]["state"], "EXPIRED")

    def test_concurrent_duplicate_placement_one_row(self):
        barrier = threading.Barrier(2)
        results = []
        errors = []
        def run():
            try:
                barrier.wait()
                results.append(r.record_placement(self.db, placement(), "2026-09-15T06:01:00Z"))
            except Exception as exc:  # pragma: no cover - captured for assertion
                errors.append(exc)
        ts = [threading.Thread(target=run) for _ in range(2)]
        for t in ts: t.start()
        for t in ts: t.join()
        self.assertFalse(errors)
        self.assertEqual(sorted(x["status"] for x in results), ["IDEMPOTENT_REPLAY", "RECORDED"])
        self.assertEqual(len(r.snapshot(self.db)["placements"]), 1)

    def test_restart_replay(self):
        r.record_placement(self.db, placement(), "2026-09-15T06:01:00Z")
        self.assertEqual(r.evaluate(self.db, intent())["status"], "READY_ON_SUPPLIED_AUTHORITY")
        self.assertEqual(len(r.snapshot(self.db)["audit"]), 2)

    def test_deterministic_export(self):
        r.record_placement(self.db, placement(), "2026-09-15T06:01:00Z")
        a = r.export_files(self.db, "2026-12-10T00:00:00Z", 30)
        b = r.export_files(self.db, "2026-12-10T00:00:00Z", 30)
        self.assertEqual(a, b)
        self.assertIn(b"Operational gate only", a["summary.md"])
        receipt = json.loads(a["receipt.json"])
        self.assertEqual(receipt["schema"], r.RECEIPT_SCHEMA)

    def test_export_requires_empty_preprovisioned_directory(self):
        out = self.root / "bundle"
        out.mkdir(mode=0o700)
        first = r.publish_export(self.db, out, "2026-12-10T00:00:00Z")
        self.assertEqual(first["status"], "EXPORTED")
        with self.assertRaisesRegex(r.RightsError, "must be empty"):
            r.publish_export(self.db, out, "2026-12-10T00:00:00Z")

    def test_export_rejects_symlink_output(self):
        real = self.root / "real-output"
        real.mkdir()
        out = self.root / "linked-output"
        os.symlink(real, out, target_is_directory=True)
        with self.assertRaisesRegex(r.RightsError, "real directory"):
            r.publish_export(self.db, out, "2026-12-10T00:00:00Z")
        self.assertEqual(list(real.iterdir()), [])

    def test_export_open_failure_leaves_empty_directory_and_clean_retry(self):
        out = self.root / "bundle-open-fail"
        out.mkdir()
        real_open = e.os.open
        fired = False
        def failing_open(path, flags, mode=0o777, *, dir_fd=None):
            nonlocal fired
            if dir_fd is None and Path(path) == out and not fired:
                fired = True
                raise OSError("injected directory open failure")
            if dir_fd is None:
                return real_open(path, flags, mode)
            return real_open(path, flags, mode, dir_fd=dir_fd)
        with mock.patch.object(e.os, "open", side_effect=failing_open):
            with self.assertRaisesRegex(OSError, "injected directory open failure"):
                r.publish_export(self.db, out, "2026-12-10T00:00:00Z")
        self.assertTrue(fired)
        self.assertEqual(list(out.iterdir()), [])
        self.assertEqual(r.publish_export(self.db, out, "2026-12-10T00:00:00Z")["status"], "EXPORTED")

    def test_export_fstat_failure_closes_descriptor_and_clean_retry(self):
        out = self.root / "bundle-fstat-fail"
        out.mkdir()
        real_fstat = e.os.fstat
        fired = False
        def failing_fstat(fd):
            nonlocal fired
            if not fired:
                fired = True
                raise OSError("injected directory fstat failure")
            return real_fstat(fd)
        with mock.patch.object(e.os, "fstat", side_effect=failing_fstat):
            with self.assertRaisesRegex(OSError, "injected directory fstat failure"):
                r.publish_export(self.db, out, "2026-12-10T00:00:00Z")
        self.assertTrue(fired)
        self.assertEqual(list(out.iterdir()), [])
        self.assertEqual(r.publish_export(self.db, out, "2026-12-10T00:00:00Z")["status"], "EXPORTED")

    def test_export_directory_swap_before_open_cannot_redirect(self):
        out = self.root / "bundle-preopen-race"
        retained = self.root / "bundle-preopen-retained"
        foreign = self.root / "bundle-preopen-foreign"
        out.mkdir()
        foreign.mkdir()
        (foreign / "sentinel.txt").write_text("foreign", encoding="utf-8")
        real_open = e.os.open
        fired = False
        def racing_open(path, flags, mode=0o777, *, dir_fd=None):
            nonlocal fired
            if dir_fd is None and Path(path) == out and not fired:
                fired = True
                os.rename(out, retained)
                os.rename(foreign, out)
            if dir_fd is None:
                return real_open(path, flags, mode)
            return real_open(path, flags, mode, dir_fd=dir_fd)
        with mock.patch.object(e.os, "open", side_effect=racing_open):
            with self.assertRaisesRegex(r.RightsError, "output directory identity changed"):
                r.publish_export(self.db, out, "2026-12-10T00:00:00Z")
        self.assertTrue(fired)
        self.assertEqual(list(retained.iterdir()), [])
        self.assertEqual(sorted(p.name for p in out.iterdir()), ["sentinel.txt"])

    def test_export_path_swap_cannot_redirect_success(self):
        out = self.root / "bundle-race"
        moved = self.root / "bundle-race-retained"
        foreign = self.root / "foreign-successor"
        out.mkdir()
        foreign.mkdir()
        (foreign / "sentinel.txt").write_text("foreign", encoding="utf-8")
        real_open = e.os.open
        fired = False
        def racing_open(path, flags, mode=0o777, *, dir_fd=None):
            nonlocal fired
            if dir_fd is not None and path == "placements.csv" and not fired:
                fired = True
                os.rename(out, moved)
                os.symlink(foreign, out, target_is_directory=True)
            if dir_fd is None:
                return real_open(path, flags, mode)
            return real_open(path, flags, mode, dir_fd=dir_fd)
        with mock.patch.object(e.os, "open", side_effect=racing_open):
            with self.assertRaisesRegex(r.RightsError, "real directory|output directory identity changed"):
                r.publish_export(self.db, out, "2026-12-10T00:00:00Z")
        self.assertTrue(fired)
        self.assertTrue(out.is_symlink())
        self.assertEqual(sorted(p.name for p in foreign.iterdir()), ["sentinel.txt"])
        tombstones = list(moved.iterdir())
        self.assertTrue(tombstones)
        self.assertTrue(all(p.is_file() and p.stat().st_size == 0 for p in tombstones))

    def test_export_failure_cleanup_preserves_foreign_successor(self):
        out = self.root / "bundle-fail-race"
        moved = self.root / "bundle-fail-race-retained"
        foreign = self.root / "foreign-successor-fail"
        out.mkdir()
        foreign.mkdir()
        (foreign / "sentinel.txt").write_text("foreign", encoding="utf-8")
        real_open = e.os.open
        fired = False
        def failing_open(path, flags, mode=0o777, *, dir_fd=None):
            nonlocal fired
            if dir_fd is not None and path == "queues.json" and not fired:
                fired = True
                os.rename(out, moved)
                os.symlink(foreign, out, target_is_directory=True)
                raise OSError("injected export write failure")
            if dir_fd is None:
                return real_open(path, flags, mode)
            return real_open(path, flags, mode, dir_fd=dir_fd)
        with mock.patch.object(e.os, "open", side_effect=failing_open):
            with self.assertRaisesRegex(OSError, "injected export write failure"):
                r.publish_export(self.db, out, "2026-12-10T00:00:00Z")
        self.assertTrue(fired)
        self.assertTrue(out.is_symlink())
        self.assertEqual(sorted(p.name for p in foreign.iterdir()), ["sentinel.txt"])
        tombstones = list(moved.iterdir())
        self.assertEqual([p.name for p in tombstones], ["placements.csv"])
        self.assertEqual(tombstones[0].stat().st_size, 0)

    def test_export_foreign_entry_fails_closed_and_survives_cleanup(self):
        out = self.root / "bundle-entry-race"
        out.mkdir()
        real_listdir = e.os.listdir
        calls = 0
        def racing_listdir(path):
            nonlocal calls
            calls += 1
            if calls == 2:
                (out / "foreign-sentinel.txt").write_text("foreign", encoding="utf-8")
            return real_listdir(path)
        with mock.patch.object(e.os, "listdir", side_effect=racing_listdir):
            with self.assertRaisesRegex(r.RightsError, "entries changed"):
                r.publish_export(self.db, out, "2026-12-10T00:00:00Z")
        self.assertEqual((out / "foreign-sentinel.txt").read_text(encoding="utf-8"), "foreign")
        owned = [p for p in out.iterdir() if p.name != "foreign-sentinel.txt"]
        self.assertTrue(owned)
        self.assertTrue(all(p.is_file() and p.stat().st_size == 0 for p in owned))

    def test_duplicate_json_key_rejected(self):
        with self.assertRaisesRegex(r.RightsError, "duplicate JSON key"):
            r.loads_strict(b'{"schema":"x","schema":"y"}')

    def test_float_and_nonfinite_json_rejected(self):
        with self.assertRaisesRegex(r.RightsError, "floating-point"):
            r.loads_strict(b'{"x":1.2}')
        with self.assertRaisesRegex(r.RightsError, "non-finite"):
            r.loads_strict(b'{"x":NaN}')

    def test_manifest_cycle_rejected(self):
        bad = manifest()
        bad["assets"] = [
            {"asset_id": "a1", "sha256": "a"*64, "parent_asset_id": "a2"},
            {"asset_id": "a2", "sha256": "b"*64, "parent_asset_id": "a1"},
        ]
        bad["grants"][0]["asset_id"] = "a1"
        with self.assertRaisesRegex(r.RightsError, "cycle"):
            r.normalize_manifest(bad)

    def test_lineage_missing_parent_rejected(self):
        bad = manifest()
        bad["assets"][1]["parent_asset_id"] = "missing-parent"
        with self.assertRaisesRegex(r.RightsError, "unknown parent"):
            r.normalize_manifest(bad)

    def test_manifest_duplicate_channel_rejected(self):
        bad = manifest(); bad["grants"][0]["channels"] = ["instagram", "instagram"]
        with self.assertRaisesRegex(r.RightsError, "duplicates"):
            r.normalize_manifest(bad)

    def test_naive_time_rejected(self):
        with self.assertRaisesRegex(r.RightsError, "include an offset"):
            r.evaluate(self.db, intent(starts_at="2026-10-01T12:00:00"))

    def test_bool_horizon_rejected(self):
        with self.assertRaisesRegex(r.RightsError, "integer"):
            r.queues(self.db, "2026-10-01T00:00:00Z", True)

    def test_import_twice_rejected(self):
        with self.assertRaisesRegex(r.RightsError, "already initialized"):
            r.import_manifest(self.db, manifest(), "2026-09-15T06:02:00Z")

    def test_snapshot_hash_stable_across_reopen(self):
        before = r.snapshot(self.db)["snapshot_sha256"]
        after = r.snapshot(self.db)["snapshot_sha256"]
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
