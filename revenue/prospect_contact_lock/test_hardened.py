from __future__ import annotations

import base64
import hashlib
import json
import unittest
from urllib.parse import unquote, urlsplit

from revenue.prospect_contact_lock import hardened
from revenue.prospect_contact_lock import lock as core
from revenue.prospect_contact_lock.test_lock import DATE, FakeTransport


class HardenedTransport(FakeTransport):
    def __init__(self):
        super().__init__()
        self.authority_available = True
        self.authority_tampered = False
        self.authority_reads = 0

    def request(self, method, url, headers, body):
        parsed = urlsplit(url)
        path = unquote(parsed.path.split("/contents/", 1)[1]) if "/contents/" in parsed.path else ""
        if method == "GET" and path == hardened.AUTHORITY_MARKER_PATH:
            self.urls.append(url)
            self.auth_headers.append(headers.get("Authorization"))
            self.authority_reads += 1
            if not self.authority_available:
                return core.Response(404, self._headers(), b"{}")
            marker = dict(hardened.EXPECTED_AUTHORITY_MARKER)
            if self.authority_tampered:
                marker["branch"] = "attacker/other-authority"
            raw = json.dumps(marker, sort_keys=True, separators=(",", ":")).encode() + b"\n"
            envelope = {
                "sha": hashlib.sha1(raw).hexdigest(),
                "encoding": "base64",
                "content": base64.b64encode(raw).decode(),
            }
            return core.Response(200, self._headers(), json.dumps(envelope).encode())
        return super().request(method, url, headers, body)


class CanonicalHardeningTests(unittest.TestCase):
    def setUp(self):
        self.transport = HardenedTransport()
        self.lock = hardened.ProspectContactLock("ghp_TESTTOKEN123", self.transport)
        self.email = "Lead.Person+Pilot@Example.com"
        self.owner = dict(agent_id="ZXR-B7Q2", operation_id="OP-PAID-1")

    def acquire(self):
        return self.lock.acquire("email", self.email, **self.owner)

    def test_missing_authority_marker_status_fails_closed_not_absent(self):
        self.transport.authority_available = False
        with self.assertRaises(core.RemoteError):
            self.lock.status("email", self.email)
        self.assertEqual(self.transport.files, {})
        self.assertEqual(self.transport.counter, 1)

    def test_missing_authority_marker_acquire_never_puts_record(self):
        self.transport.authority_available = False
        with self.assertRaises(core.RemoteError):
            self.acquire()
        self.assertEqual(self.transport.files, {})
        self.assertEqual(self.transport.counter, 1)

    def test_tampered_authority_marker_fails_closed(self):
        self.transport.authority_tampered = True
        with self.assertRaises(core.ValidationError):
            self.acquire()
        self.assertEqual(self.transport.files, {})

    def test_authority_marker_precedes_record_read(self):
        self.acquire()
        self.assertGreaterEqual(self.transport.authority_reads, 1)
        marker_index = next(i for i, url in enumerate(self.transport.urls) if hardened.AUTHORITY_MARKER_PATH in url)
        record_index = next(i for i, url in enumerate(self.transport.urls) if hardened.AUTHORITY_MARKER_PATH not in url)
        self.assertLess(marker_index, record_index)

    def test_paid_path_token_boundaries_reject_negative_and_larger_tokens(self):
        self.acquire()
        for bad in (
            "unpaid volunteer work",
            "repaid favor",
            "uncontracted informal help",
            "not paid for this",
            "no fee",
            "$0",
        ):
            with self.subTest(bad=bad):
                with self.assertRaises(core.ValidationError):
                    self.lock.arm(
                        "email", self.email, **self.owner,
                        message_sha256=hashlib.sha256(b"hello").hexdigest(),
                        channel="email", compensation_path=bad,
                    )

    def test_positive_amount_and_exact_signal_are_accepted(self):
        self.acquire()
        armed = self.lock.arm(
            "email", self.email, **self.owner,
            message_sha256=hashlib.sha256(b"hello").hexdigest(),
            channel="email", compensation_path="$90 bounty on merged fix",
        )
        self.assertEqual(armed["state"], "ARMED")

    def test_dispatch_replay_still_fails_under_canonical_wrapper(self):
        self.acquire()
        self.lock.arm(
            "email", self.email, **self.owner,
            message_sha256=hashlib.sha256(b"hello").hexdigest(),
            channel="email", compensation_path="$2500 paid pilot",
        )
        first = self.lock.dispatch("email", self.email, **self.owner)
        self.assertEqual(first["state"], "OUTCOME_UNKNOWN")
        with self.assertRaises(core.ConflictError):
            self.lock.dispatch("email", self.email, **self.owner)


if __name__ == "__main__":
    unittest.main()
