import json
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

import rights_export
import rights_model
import rights_store


def manifest(valid_until="2026-12-31T23:59:59Z"):
    return {
        "schema": rights_model.SCHEMA,
        "assets": [{"asset_id":"cut-a","sha256":"a"*64,"parent_asset_id":None}],
        "grants": [{
            "grant_id":"grant-a",
            "asset_id":"cut-a",
            "authority_ref":"fictional-owner-row-1",
            "valid_from":"2026-09-01T00:00:00Z",
            "valid_until":valid_until,
            "channels":["web"],
            "territories":["US"],
        }],
    }


def placement(request_id, end):
    return {
        "request_id":request_id,
        "asset_id":"cut-a",
        "channel":"web",
        "territory":"US",
        "starts_at":"2026-10-04T23:59:59Z",
        "ends_at":end,
    }


class PrecisionTests(unittest.TestCase):
    def test_whole_second_compatibility(self):
        self.assertEqual(
            rights_model.norm_time("2026-09-18T12:00:00Z","t"),
            "2026-09-18T12:00:00Z",
        )

    def test_microsecond_precision_is_canonical_and_exact(self):
        self.assertEqual(
            rights_model.norm_time("2026-09-18T14:00:00.1+02:00","t"),
            "2026-09-18T12:00:00.100000Z",
        )
        self.assertEqual(
            rights_model.norm_time("2026-09-18T12:00:00.123456Z","t"),
            "2026-09-18T12:00:00.123456Z",
        )

    def test_unrepresentable_seventh_digit_rejected(self):
        with self.assertRaisesRegex(rights_model.RightsError,"at most 6"):
            rights_model.parse_time("2026-09-18T12:00:00.1234567Z","t")
        with self.assertRaisesRegex(rights_model.RightsError,"at most 6"):
            rights_model.parse_time("2026W38112.0000001+00:00","t")

    def test_fraction_silently_discarded_by_runtime_rejected(self):
        with self.assertRaisesRegex(rights_model.RightsError,"fractional UTC offsets"):
            rights_model.parse_time("2026-09-18T12:00:00+00:00.1","t")

    def test_zero_fraction_and_date_separator_remain_compatible(self):
        self.assertEqual(
            rights_model.norm_time("2026-09-18.12:00:00+00:00","t"),
            "2026-09-18T12:00:00Z",
        )
        self.assertEqual(
            rights_model.norm_time("2026-09-18T12:00:00.000000Z","t"),
            "2026-09-18T12:00:00Z",
        )


class QueueAndTransactionTests(unittest.TestCase):
    def setUp(self):
        self.td=tempfile.TemporaryDirectory()
        self.root=Path(self.td.name)
        self.db=self.root/"desk.sqlite3"
        rights_store.import_manifest(self.db,manifest(),"2026-09-15T00:00:00Z")

    def tearDown(self):
        self.td.cleanup()

    def test_parsed_instant_retraction_semantics_shared_by_export(self):
        rights_store.record_placement(
            self.db, placement("whole-before","2026-10-05T00:00:00Z"),
            "2026-09-15T00:00:00.100000Z",
        )
        rights_store.record_placement(
            self.db, placement("fraction-after","2026-10-05T00:00:00.500000Z"),
            "2026-09-15T00:00:00.200000Z",
        )
        rights_store.revoke_grant(
            self.db,"grant-a","2026-10-05T00:00:00.250000Z"
        )
        standalone=rights_store.queues(self.db,"2026-10-05T00:00:00.250000Z",30)
        self.assertEqual(
            [x["request_id"] for x in standalone["retraction_review"]],
            ["fraction-after"],
        )
        exported=rights_export.export_files(
            self.db,"2026-10-05T00:00:00.250000Z",30
        )
        self.assertEqual(json.loads(exported["queues.json"]),standalone)

    def test_microsecond_request_replay_identity(self):
        first=rights_store.record_placement(
            self.db,
            placement("repeat-a","2026-10-05T00:00:00.1Z"),
            "2026-09-15T00:00:00.123456Z",
        )
        replay=rights_store.record_placement(
            self.db,
            placement("repeat-a","2026-10-05T00:00:00.100000Z"),
            "2026-09-15T00:00:01Z",
        )
        self.assertEqual(first["status"],"RECORDED")
        self.assertEqual(replay["status"],"IDEMPOTENT_REPLAY")
        with self.assertRaisesRegex(rights_model.RightsError,"replay changed"):
            rights_store.record_placement(
                self.db,
                placement("repeat-a","2026-10-05T00:00:00.100001Z"),
                "2026-09-15T00:00:02Z",
            )

    def _writer_revoke(self, gate, done):
        gate.wait()
        rights_store.revoke_grant(
            self.db,"grant-a","2026-10-05T00:00:00.250000Z"
        )
        done.set()

    def test_snapshot_is_one_read_generation_under_wal_write(self):
        real_connect=rights_store.connect
        gate=threading.Barrier(2)
        done=threading.Event()
        writer=threading.Thread(target=self._writer_revoke,args=(gate,done))
        writer.start()
        first=True

        def instrumented(path):
            nonlocal first
            con=real_connect(path)
            if first:
                first=False
                def trace(sql):
                    if sql.startswith("SELECT * FROM grants"):
                        gate.wait()
                        self.assertTrue(done.wait(5))
                con.set_trace_callback(trace)
            return con

        with mock.patch.object(rights_store,"connect",side_effect=instrumented):
            snap=rights_store.snapshot(self.db)
        writer.join(5)
        self.assertFalse(writer.is_alive())
        self.assertIsNone(snap["grants"][0]["revoked_at"])
        self.assertEqual(
            rights_store.snapshot(self.db)["grants"][0]["revoked_at"],
            "2026-10-05T00:00:00.250000Z",
        )

    def test_queues_is_one_read_generation_under_wal_write(self):
        # A pre-revocation queue read must not splice the post-revocation
        # retraction rows after it already observed the grant as renewable.
        other=self.root/"queue.sqlite3"
        rights_store.import_manifest(
            other,manifest("2026-10-06T00:00:00Z"),"2026-09-15T00:00:00Z"
        )
        rights_store.record_placement(
            other,placement("p1","2026-10-05T00:00:00.500000Z"),
            "2026-09-15T00:00:00Z",
        )
        real_connect=rights_store.connect
        gate=threading.Barrier(2)
        done=threading.Event()

        def writer_fn():
            gate.wait()
            rights_store.revoke_grant(
                other,"grant-a","2026-10-05T00:00:00.250000Z"
            )
            done.set()

        writer=threading.Thread(target=writer_fn)
        writer.start()
        first=True
        def instrumented(path):
            nonlocal first
            con=real_connect(path)
            if first:
                first=False
                def trace(sql):
                    if sql.startswith("SELECT p.request_id"):
                        gate.wait()
                        self.assertTrue(done.wait(5))
                con.set_trace_callback(trace)
            return con

        with mock.patch.object(rights_store,"connect",side_effect=instrumented):
            q=rights_store.queues(other,"2026-10-05T00:00:00Z",30)
        writer.join(5)
        self.assertEqual([x["grant_id"] for x in q["renewal_review"]],["grant-a"])
        self.assertEqual(q["retraction_review"],[])
        after=rights_store.queues(other,"2026-10-05T00:00:00Z",30)
        self.assertEqual(after["renewal_review"],[])
        self.assertEqual([x["request_id"] for x in after["retraction_review"]],["p1"])


if __name__=="__main__":
    unittest.main()
