#!/usr/bin/env python3
"""Deterministic tests for host/chargeback_defense_receiver.py.

Synthetic fixtures only: every identifier carries a synthetic marker, the
signing secret is an explicitly synthetic test value, and no test performs
any external or provider call. The loopback test uses real HTTP over
127.0.0.1 with an ephemeral port.
"""
from __future__ import annotations

import hashlib
import hmac
import io
import json
import logging
import os
import shutil
import sqlite3
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import chargeback_defense as core
import chargeback_defense_receiver as receiver

TEST_SECRET = "synthetic-test-endpoint-secret-20261001-01"
RAW_SENTINEL = "SENTINEL-RAW-BODY-7f3a91c4"
CUSTOMER_SENTINEL = "sentinel-customer-7f3a91c4@example.test"
TOLERANCE = 300


def make_event(event_id="evt_synthetic_test_0001", extra=None, etype="charge.succeeded"):
    now = int(time.time())
    event = {
        "id": event_id,
        "object": "event",
        "type": etype,
        "livemode": False,
        "created": now,
        "data": {"object": {
            "id": "ch_synthetic_test_0001",
            "object": "charge",
            "created": now,
            "amount": 2500,
            "currency": "usd",
            "paid": True,
            "captured": True,
            "payment_intent": "pi_synthetic_test_0001",
        }},
    }
    if extra:
        event.update(extra)
    return json.dumps(event, separators=(",", ":"), sort_keys=True).encode("utf-8")


def sign(body, secret=TEST_SECRET, stamp=None):
    stamp = int(time.time()) if stamp is None else stamp
    digest = hmac.new(secret.encode(), str(stamp).encode() + b"." + body,
                      hashlib.sha256).hexdigest()
    return "t=%d,v1=%s" % (stamp, digest)


def headers_for(body, secret=TEST_SECRET, stamp=None):
    return {"content-type": "application/json", "stripe-signature": sign(body, secret, stamp)}


class ReceiverTestBase(unittest.TestCase):
    def setUp(self):
        self.workdir = tempfile.mkdtemp(prefix="receiver-test-")
        os.chmod(self.workdir, 0o700)
        self.db_path = os.path.join(self.workdir, "ledger.sqlite")
        receiver.initialize_ledger(self.db_path)
        self.config = receiver.ReceiverConfig(db_path=self.db_path, secret=TEST_SECRET,
                                              tolerance=TOLERANCE)
        self._verify_calls = []
        self._real_verify = core.verify

        def spy(raw, header, secret, tolerance):
            self._verify_calls.append((raw, header, secret, tolerance))
            return self._real_verify(raw, header, secret, tolerance)

        core.verify = spy
        receiver._core.verify = spy

    def tearDown(self):
        core.verify = self._real_verify
        receiver._core.verify = self._real_verify
        shutil.rmtree(self.workdir, ignore_errors=True)

    def deliver(self, body, headers=None, method="POST", path="/ingest"):
        return receiver.handle_delivery(method, path, headers or {}, body, self.config)

    def row_count(self):
        db = core.connect(self.db_path)
        try:
            return db.execute("SELECT count(*) FROM events").fetchone()[0]
        finally:
            db.close()


class ExactBytesTests(ReceiverTestBase):
    def test_exact_body_bytes_and_header_reach_core_unchanged(self):
        body = make_event()
        sent_headers = headers_for(body)
        status, payload = self.deliver(body, sent_headers)
        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "recorded")
        self.assertEqual(len(self._verify_calls), 1)
        seen_body, seen_header, seen_secret, seen_tolerance = self._verify_calls[0]
        self.assertIs(seen_body, body)
        self.assertEqual(seen_header, sent_headers["stripe-signature"])
        self.assertEqual(seen_secret, TEST_SECRET)
        self.assertEqual(seen_tolerance, TOLERANCE)
        self.assertEqual(seen_body, body)  # byte-identical, no re-encoding


class RejectionTests(ReceiverTestBase):
    def test_missing_signature_rejected(self):
        status, payload = self.deliver(make_event(), {"content-type": "application/json"})
        self.assertEqual(status, 401)
        self.assertEqual(payload["error"], "signature_required")

    def test_malformed_signature_rejected(self):
        for bad in ("not-a-signature", "t=abc,v1=zz", "t=1,t=2,v1=" + "a" * 64,
                    "v1=" + "a" * 64, "t=%d" % int(time.time())):
            status, payload = self.deliver(make_event(),
                                           {"content-type": "application/json",
                                            "stripe-signature": bad})
            self.assertEqual(status, 400, bad)
            self.assertEqual(payload["error"], "signature_malformed", bad)

    def test_stale_timestamp_rejected(self):
        body = make_event()
        header = sign(body, stamp=int(time.time()) - TOLERANCE - 60)
        status, payload = self.deliver(body, {"content-type": "application/json",
                                              "stripe-signature": header})
        self.assertEqual(status, 401)
        self.assertEqual(payload["error"], "signature_stale")

    def test_invalid_signature_rejected(self):
        body = make_event()
        header = sign(body, secret="synthetic-wrong-secret")
        status, payload = self.deliver(body, {"content-type": "application/json",
                                              "stripe-signature": header})
        self.assertEqual(status, 401)
        self.assertEqual(payload["error"], "signature_invalid")

    def test_oversized_body_rejected(self):
        body = b"x" * (self.config.max_body_bytes + 1)
        status, payload = self.deliver(body, headers_for(b"x"))
        self.assertEqual(status, 413)
        self.assertEqual(payload["error"], "body_too_large")

    def test_empty_body_rejected(self):
        status, payload = self.deliver(b"", headers_for(b""))
        self.assertEqual(status, 400)
        self.assertEqual(payload["error"], "body_empty")

    def test_wrong_method_rejected(self):
        body = make_event()
        status, payload = self.deliver(body, headers_for(body), method="GET")
        self.assertEqual(status, 405)
        self.assertEqual(payload["error"], "method_not_allowed")

    def test_unknown_path_rejected(self):
        body = make_event()
        status, payload = self.deliver(body, headers_for(body), path="/nope")
        self.assertEqual(status, 404)
        self.assertEqual(payload["error"], "not_found")

    def test_wrong_content_type_rejected(self):
        body = make_event()
        status, payload = self.deliver(body, {"content-type": "text/plain",
                                              "stripe-signature": sign(body)})
        self.assertEqual(status, 415)
        self.assertEqual(payload["error"], "content_type_unsupported")

    def test_signed_non_event_rejected(self):
        body = b'{"unexpected": "shape"}'
        status, payload = self.deliver(body, headers_for(body))
        self.assertEqual(status, 400)
        self.assertEqual(payload["error"], "event_invalid")

    def test_signed_non_json_rejected(self):
        body = b"not json at all"
        status, payload = self.deliver(body, headers_for(body))
        self.assertEqual(status, 400)
        self.assertEqual(payload["error"], "event_invalid")


class DurabilityTests(ReceiverTestBase):
    def test_first_valid_event_durably_recorded(self):
        body = make_event()
        status, payload = self.deliver(body, headers_for(body))
        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "recorded")
        self.assertEqual(payload["event_id"], "evt_synthetic_test_0001")
        self.assertEqual(payload["record_kind"], "charge")
        self.assertEqual(payload["record_count_added"], 1)
        self.assertEqual(self.row_count(), 1)
        db = core.connect(self.db_path)
        try:
            row = db.execute("SELECT * FROM events WHERE event_id=?",
                             ("evt_synthetic_test_0001",)).fetchone()
        finally:
            db.close()
        self.assertIsNotNone(row)
        self.assertEqual(row["payload_sha256"], hashlib.sha256(body).hexdigest())
        record = json.loads(row["record_json"])
        self.assertNotIn("customer", json.dumps(record).lower())

    def test_exact_replay_is_idempotent(self):
        body = make_event()
        sent = headers_for(body)
        first_status, first = self.deliver(body, sent)
        second_status, second = self.deliver(body, sent)
        self.assertEqual((first_status, first["status"]), (200, "recorded"))
        self.assertEqual((second_status, second["status"]), (200, "duplicate"))
        self.assertEqual(second["record_count_added"], 0)
        self.assertEqual(self.row_count(), 1)

    def test_conflicting_bytes_rejected_and_original_preserved(self):
        first = make_event()
        second = make_event()
        # Same event id, different payload bytes.
        obj = json.loads(second.decode())
        obj["data"]["object"]["amount"] = 9999
        second = json.dumps(obj, separators=(",", ":"), sort_keys=True).encode()
        self.assertEqual(self.deliver(first, headers_for(first))[0], 200)
        status, payload = self.deliver(second, headers_for(second))
        self.assertEqual(status, 409)
        self.assertEqual(payload["error"], "event_conflict")
        self.assertEqual(self.row_count(), 1)
        db = core.connect(self.db_path)
        try:
            digest = db.execute("SELECT payload_sha256 FROM events WHERE event_id=?",
                                ("evt_synthetic_test_0001",)).fetchone()[0]
        finally:
            db.close()
        self.assertEqual(digest, hashlib.sha256(first).hexdigest())

    def test_storage_failure_is_non_2xx(self):
        os.chmod(self.db_path, 0o444)  # connect() then fails its privacy checks.
        try:
            body = make_event()
            status, payload = self.deliver(body, headers_for(body))
        finally:
            os.chmod(self.db_path, 0o600)
        self.assertEqual(status, 500)
        self.assertEqual(payload["error"], "storage_failure")

    def test_unsupported_event_recorded_without_object_data(self):
        body = make_event(event_id="evt_synthetic_test_0002",
                          etype="synthetic.unmapped_type")
        status, payload = self.deliver(body, headers_for(body))
        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "recorded")
        self.assertEqual(payload["record_kind"], "unsupported")
        self.assertIn("UNSUPPORTED_EVENT_RECORDED_WITHOUT_OBJECT_DATA",
                      payload["operator_flags"])


class PrivacyTests(ReceiverTestBase):
    def test_logs_responses_and_receipts_exclude_sensitive_material(self):
        records = []

        class Capture(logging.Handler):
            def emit(self, record):
                records.append(record.getMessage())

        handler = Capture()
        receiver.LOG.addHandler(handler)
        try:
            event = json.loads(make_event().decode())
            event["description"] = RAW_SENTINEL
            event["customer_email"] = CUSTOMER_SENTINEL
            body = json.dumps(event, separators=(",", ":"), sort_keys=True).encode()
            status, payload = self.deliver(body, headers_for(body))
            self.assertEqual(status, 200)
            # Exercise a rejection path too.
            bad_status, bad_payload = self.deliver(body, {"content-type": "application/json"})
            self.assertEqual(bad_status, 401)
        finally:
            receiver.LOG.removeHandler(handler)
        haystack = "\n".join(records) + "\n" + json.dumps(payload) + "\n" + json.dumps(bad_payload)
        for sentinel in (RAW_SENTINEL, CUSTOMER_SENTINEL, TEST_SECRET, self.db_path, self.workdir):
            self.assertNotIn(sentinel, haystack, "leaked: " + sentinel[:24])
        # The persisted record keeps only minimized fields, never raw extras.
        db = core.connect(self.db_path)
        try:
            stored = db.execute("SELECT record_json FROM events").fetchone()[0]
        finally:
            db.close()
        self.assertNotIn(RAW_SENTINEL, stored)
        self.assertNotIn(CUSTOMER_SENTINEL, stored)

    def test_receipt_carries_no_account_identifier_or_path(self):
        body = make_event()
        status, payload = self.deliver(body, headers_for(body))
        self.assertEqual(status, 200)
        self.assertNotIn("account_id", payload)
        for value in payload.values():
            if isinstance(value, str):
                self.assertNotIn(self.workdir, value)


class ConfigTests(unittest.TestCase):
    def test_config_rejects_bad_secret_and_tolerance(self):
        workdir = tempfile.mkdtemp(prefix="receiver-config-test-")
        os.chmod(workdir, 0o700)
        try:
            db_path = os.path.join(workdir, "ledger.sqlite")
            receiver.initialize_ledger(db_path)
            with self.assertRaises(receiver.ReceiverError):
                receiver.ReceiverConfig(db_path=db_path, secret="")
            with self.assertRaises(receiver.ReceiverError):
                receiver.ReceiverConfig(db_path=db_path, secret=TEST_SECRET, tolerance=0)
            with self.assertRaises(receiver.ReceiverError):
                receiver.ReceiverConfig(db_path=db_path, secret=TEST_SECRET, tolerance=99999)
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

    def test_config_rejects_in_repository_db_path(self):
        with self.assertRaises(core.DefenseError):
            receiver.ReceiverConfig(db_path="relative/ledger.sqlite", secret=TEST_SECRET)


class WsgiTests(ReceiverTestBase):
    def _environ(self, body, headers, method="POST", path="/ingest", length=None):
        environ = {"REQUEST_METHOD": method, "PATH_INFO": path,
                   "wsgi.input": io.BytesIO(body)}
        for name, value in headers.items():
            key = "HTTP_" + name.upper().replace("-", "_")
            environ[key] = value
        if "content-type" in headers:
            environ["CONTENT_TYPE"] = headers["content-type"]
        if length is None:
            # PEP 3333 exposes Content-Length under this exact uppercase key.
            # Keep the fixture standards-compliant so case regressions cannot
            # be hidden by the test harness.
            environ["CONTENT_LENGTH"] = str(len(body))
        elif length != "missing":
            environ["CONTENT_LENGTH"] = length
        return environ

    def _call(self, environ):
        app = receiver.create_app(self.config)
        captured = {}

        def start_response(status, response_headers):
            captured["status"] = status
            captured["headers"] = dict(response_headers)

        body = b"".join(app(environ, start_response))
        return captured, json.loads(body.decode())

    def test_wsgi_round_trip(self):
        body = make_event()
        environ = self._environ(body, headers_for(body))
        captured, payload = self._call(environ)
        self.assertTrue(captured["status"].startswith("200"))
        self.assertEqual(payload["status"], "recorded")
        self.assertEqual(self.row_count(), 1)

    def test_wsgi_get_without_content_length_maps_to_405(self):
        environ = self._environ(b"", {"content-type": "application/json"},
                                method="GET", length="missing")
        captured, payload = self._call(environ)
        self.assertTrue(captured["status"].startswith("405"))
        self.assertEqual(payload["error"], "method_not_allowed")

    def test_wsgi_missing_content_length(self):
        environ = self._environ(b"{}", {"content-type": "application/json"}, length="missing")
        captured, payload = self._call(environ)
        self.assertTrue(captured["status"].startswith("411"))
        self.assertEqual(payload["error"], "length_required")

    def test_wsgi_bad_content_length(self):
        environ = self._environ(b"{}", {"content-type": "application/json"}, length="abc")
        captured, payload = self._call(environ)
        self.assertTrue(captured["status"].startswith("400"))
        self.assertEqual(payload["error"], "content_length_invalid")

    def test_wsgi_declared_oversize(self):
        environ = self._environ(b"{}", {"content-type": "application/json"},
                               length=str(self.config.max_body_bytes + 1))
        captured, payload = self._call(environ)
        self.assertTrue(captured["status"].startswith("413"))

    def test_wsgi_truncated_body(self):
        body = make_event()
        environ = self._environ(body[:10], headers_for(body), length=str(len(body)))
        captured, payload = self._call(environ)
        self.assertTrue(captured["status"].startswith("400"))
        self.assertEqual(payload["error"], "payload_truncated")


class LoopbackProofTest(unittest.TestCase):
    def test_loopback_proof_passes(self):
        proof = receiver.run_loopback_proof()
        self.assertTrue(proof["passed"], json.dumps(proof["checks"], indent=2))
        self.assertEqual(proof["external_calls"], 0)
        self.assertTrue(proof["synthetic_only"])
        self.assertGreaterEqual(len(proof["checks"]), 8)


if __name__ == "__main__":
    unittest.main(verbosity=2)
