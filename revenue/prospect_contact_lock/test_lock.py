from __future__ import annotations

import base64
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from revenue.prospect_contact_lock import lock as mod


DATE = "Mon, 14 Sep 2026 23:30:00 GMT"


class FakeTransport:
    def __init__(self):
        self.files = {}
        self.counter = 1
        self.race_next_put = False
        self.omit_date = False
        self.urls = []
        self.auth_headers = []

    def _headers(self):
        return {} if self.omit_date else {"Date": DATE}

    @staticmethod
    def _sha40(data: bytes) -> str:
        return hashlib.sha1(data).hexdigest()

    def request(self, method, url, headers, body):
        self.urls.append(url)
        self.auth_headers.append(headers.get("Authorization"))
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.netloc != "api.github.com":
            raise AssertionError("non-canonical URL reached transport")
        assert parsed.path.startswith("/repos/woahwhattheheck/commons/contents/")
        assert parse_qs(parsed.query).get("ref") == [mod.AUTHORITY_BRANCH]
        path = unquote(parsed.path.split("/contents/", 1)[1])
        if method == "GET":
            current = self.files.get(path)
            if current is None:
                return mod.Response(404, self._headers(), b"{}")
            blob_sha, raw = current
            envelope = {
                "sha": blob_sha,
                "encoding": "base64",
                "content": base64.b64encode(raw).decode(),
            }
            return mod.Response(200, self._headers(), json.dumps(envelope).encode())
        if method != "PUT":
            raise AssertionError(method)
        if self.race_next_put:
            self.race_next_put = False
            return mod.Response(409, self._headers(), b"{}")
        payload = json.loads(body.decode())
        raw = base64.b64decode(payload["content"])
        current = self.files.get(path)
        supplied = payload.get("sha")
        if current is None and supplied is not None:
            return mod.Response(409, self._headers(), b"{}")
        if current is not None and supplied is None:
            return mod.Response(422, self._headers(), b"{}")
        if current is not None and supplied != current[0]:
            return mod.Response(409, self._headers(), b"{}")
        blob_sha = self._sha40(raw)
        self.files[path] = (blob_sha, raw)
        commit_sha = hashlib.sha1(f"commit-{self.counter}".encode()).hexdigest()
        self.counter += 1
        envelope = {"content": {"sha": blob_sha}, "commit": {"sha": commit_sha}}
        return mod.Response(201 if current is None else 200, self._headers(), json.dumps(envelope).encode())

    def record_bytes(self):
        self.assert_one()
        return next(iter(self.files.values()))[1]

    def record(self):
        return json.loads(self.record_bytes().decode())

    def assert_one(self):
        if len(self.files) != 1:
            raise AssertionError(f"expected one record, got {len(self.files)}")


class ProspectContactLockTests(unittest.TestCase):
    def setUp(self):
        self.transport = FakeTransport()
        self.lock = mod.ProspectContactLock("ghp_TESTTOKEN123", self.transport)
        self.email = "Lead.Person+Pilot@Example.com"
        self.owner = dict(agent_id="ZXR-B7Q2", operation_id="OP-PAID-1")

    def acquire(self):
        return self.lock.acquire("email", self.email, **self.owner)

    def payload(self, body: bytes = b"hello", compensation: str = "$2500 paid pilot"):
        return dict(
            message_sha256=hashlib.sha256(body).hexdigest(),
            channel="email",
            compensation_path=compensation,
        )

    def arm(self, **overrides):
        kwargs = self.payload()
        kwargs.update(overrides)
        return self.lock.arm("email", self.email, **self.owner, **kwargs)

    def dispatch(self):
        return self.lock.dispatch("email", self.email, **self.owner)

    def consume(self, **overrides):
        self.acquire()
        armed = self.arm(**overrides)
        dispatched = self.dispatch()
        return armed, dispatched

    def test_email_normalization_collapses_case(self):
        a = mod.normalize_target("email", "User@EXAMPLE.com")
        b = mod.normalize_target("EMAIL", "user@example.com")
        self.assertEqual(a.fingerprint, b.fingerprint)

    def test_campaign_and_offer_not_in_fingerprint(self):
        target = mod.normalize_target("email", self.email)
        self.assertEqual(target.fingerprint, mod.normalize_target("email", self.email).fingerprint)
        self.assertNotIn("paid", target.fingerprint)

    def test_domain_idna_and_trailing_dot(self):
        a = mod.normalize_target("domain", "EXAMPLE.COM.")
        b = mod.normalize_target("domain", "example.com")
        self.assertEqual(a.fingerprint, b.fingerprint)

    def test_phone_normalization(self):
        a = mod.normalize_target("phone", "+1 (812) 555-0123")
        b = mod.normalize_target("phone", "+18125550123")
        self.assertEqual(a.fingerprint, b.fingerprint)

    def test_bad_target_rejected(self):
        for kind, value in [("email", "nope"), ("domain", "localhost"), ("phone", "8125550123"), ("url", "x")]:
            with self.subTest(kind=kind):
                with self.assertRaises(mod.ValidationError):
                    mod.normalize_target(kind, value)

    def test_acquire_creates_single_active_record(self):
        receipt = self.acquire()
        self.assertEqual(receipt["outcome"], "ACQUIRED")
        self.assertEqual(receipt["state"], "ACTIVE")
        self.assertFalse(receipt["external_send_authorized"])
        record = self.transport.record()
        self.assertEqual(record["state"], "ACTIVE")
        self.assertEqual(record["owner_agent_id"], self.owner["agent_id"])

    def test_raw_target_not_persisted(self):
        self.acquire()
        raw = self.transport.record_bytes().decode().casefold()
        self.assertNotIn(self.email.casefold(), raw)
        self.assertNotIn("lead.person+pilot", raw)

    def test_path_contains_only_digest_identity(self):
        self.acquire()
        path = next(iter(self.transport.files))
        self.assertIn(mod.AUTHORITY_ROOT, path)
        self.assertNotIn("example", path)
        self.assertRegex(path.rsplit("/", 1)[-1], r"^[0-9a-f]{64}\.json$")

    def test_second_owner_same_contact_fails_closed(self):
        self.acquire()
        with self.assertRaises(mod.ConflictError):
            self.lock.acquire("email", self.email, agent_id="Z-OTHER", operation_id="OP-2")
        self.assertEqual(self.transport.record()["owner_agent_id"], self.owner["agent_id"])

    def test_same_owner_acquire_is_idempotent_without_write(self):
        first = self.acquire()
        commits = self.transport.counter
        second = self.acquire()
        self.assertEqual(second["outcome"], "ALREADY_ACTIVE")
        self.assertEqual(self.transport.counter, commits)
        self.assertEqual(first["generation"], second["generation"])

    def test_no_timeout_or_stale_takeover_field_exists(self):
        self.acquire()
        record = self.transport.record()
        self.assertNotIn("lease_expires_at", record)
        self.assertNotIn("expires_at", record)
        with self.assertRaises(mod.ConflictError):
            self.lock.acquire("email", self.email, agent_id="Z-LATE", operation_id="OP-LATE")

    def test_cas_create_race_fails_closed(self):
        self.transport.race_next_put = True
        with self.assertRaises(mod.ConflictError):
            self.acquire()
        self.assertEqual(self.transport.files, {})

    def test_explicit_unsent_release_allows_reacquire(self):
        self.acquire()
        released = self.lock.release_unsent("email", self.email, **self.owner, reason="route invalid before send")
        self.assertEqual(released["state"], "RELEASED")
        again = self.lock.acquire("email", self.email, agent_id="Z-NEXT", operation_id="OP-NEXT")
        self.assertEqual(again["outcome"], "REACQUIRED_AFTER_EXPLICIT_RELEASE")
        self.assertEqual(again["state"], "ACTIVE")

    def test_only_exact_owner_can_release(self):
        self.acquire()
        with self.assertRaises(mod.ConflictError):
            self.lock.release_unsent("email", self.email, agent_id="Z-OTHER", operation_id="OP-2", reason="not mine")

    def test_release_requires_reason(self):
        self.acquire()
        with self.assertRaises(mod.ValidationError):
            self.lock.release_unsent("email", self.email, **self.owner, reason="")

    def test_finalize_contacted_is_terminal(self):
        self.consume()
        receipt = self.lock.finalize_contacted(
            "email", self.email, **self.owner,
            message_sha256=hashlib.sha256(b"hello").hexdigest(),
            channel="email", compensation_path="$2500 paid pilot",
            provider_receipt="gmail-message-id:abc123",
        )
        self.assertEqual(receipt["state"], "CONTACTED")
        with self.assertRaises(mod.ConflictError):
            self.lock.acquire("email", self.email, agent_id="Z-OTHER", operation_id="OP-2")
        with self.assertRaises(mod.ConflictError):
            self.lock.release_unsent("email", self.email, **self.owner, reason="too late")

    def test_finalize_owner_mismatch_fails(self):
        self.consume()
        with self.assertRaises(mod.ConflictError):
            self.lock.finalize_contacted(
                "email", self.email, agent_id="Z-OTHER", operation_id="OP-2",
                message_sha256=hashlib.sha256(b"hello").hexdigest(),
                channel="email", compensation_path="paid bounty $90",
                provider_receipt="receipt",
            )

    def test_finalize_requires_paid_path(self):
        self.consume()
        with self.assertRaises(mod.ValidationError):
            self.lock.finalize_contacted(
                "email", self.email, **self.owner,
                message_sha256=hashlib.sha256(b"hello").hexdigest(),
                channel="email", compensation_path="just saying hello",
                provider_receipt="receipt",
            )

    def test_contacted_persists_only_evidence_digests(self):
        comp = "$15,000 fixed paid subcontract"
        provider = "provider-secret-ish-id-123"
        message = hashlib.sha256(b"commercial offer body").hexdigest()
        self.acquire()
        self.lock.arm("email", self.email, **self.owner, message_sha256=message, channel="email", compensation_path=comp)
        self.dispatch()
        self.lock.finalize_contacted(
            "email", self.email, **self.owner,
            message_sha256=message, channel="email",
            compensation_path=comp, provider_receipt=provider,
        )
        text = self.transport.record_bytes().decode()
        record = self.transport.record()
        self.assertNotIn(comp, text)
        self.assertNotIn(provider, text)
        self.assertEqual(record["message_sha256"], message)
        self.assertEqual(record["provider_receipt_sha256"], hashlib.sha256(provider.encode()).hexdigest())
        self.assertEqual(record["compensation_path_sha256"], hashlib.sha256(comp.encode()).hexdigest())

    def test_finalize_is_idempotent_only_for_same_evidence(self):
        self.acquire()
        kwargs = dict(message_sha256=hashlib.sha256(b"x").hexdigest(), channel="email", compensation_path="$2500 paid pilot", provider_receipt="receipt-1")
        self.lock.arm("email", self.email, **self.owner, message_sha256=kwargs["message_sha256"], channel=kwargs["channel"], compensation_path=kwargs["compensation_path"])
        self.dispatch()
        self.lock.finalize_contacted("email", self.email, **self.owner, **kwargs)
        again = self.lock.finalize_contacted("email", self.email, **self.owner, **kwargs)
        self.assertEqual(again["outcome"], "ALREADY_CONTACTED")
        with self.assertRaises(mod.ConflictError):
            self.lock.finalize_contacted(
                "email", self.email, **self.owner,
                message_sha256=hashlib.sha256(b"y").hexdigest(), channel="email",
                compensation_path="$2500 paid pilot", provider_receipt="receipt-2",
            )

    def test_status_absent_and_active_never_authorize_send(self):
        absent = self.lock.status("email", self.email)
        self.assertEqual(absent["state"], "ABSENT")
        self.assertFalse(absent["external_send_authorized"])
        self.acquire()
        active = self.lock.status("email", self.email)
        self.assertEqual(active["state"], "ACTIVE")
        self.assertFalse(active["external_send_authorized"])

    def test_receipt_tamper_detected(self):
        receipt = self.acquire()
        self.assertTrue(mod.verify_receipt(receipt))
        bad = dict(receipt)
        bad["state"] = "CONTACTED"
        with self.assertRaises(mod.ValidationError):
            mod.verify_receipt(bad)

    def test_retained_record_tamper_detected(self):
        self.acquire()
        path, (blob, raw) = next(iter(self.transport.files.items()))
        record = json.loads(raw)
        record["external_send_authorized"] = True
        altered = json.dumps(record, sort_keys=True, separators=(",", ":")).encode()
        self.transport.files[path] = (hashlib.sha1(altered).hexdigest(), altered)
        with self.assertRaises(mod.ValidationError):
            self.lock.status("email", self.email)

    def test_missing_server_date_fails_closed(self):
        self.transport.omit_date = True
        with self.assertRaises(mod.RemoteError):
            self.acquire()
        self.assertEqual(self.transport.files, {})

    def test_token_bearing_urls_are_pinned(self):
        self.acquire()
        for url in self.transport.urls:
            parsed = urlsplit(url)
            self.assertEqual(parsed.scheme, "https")
            self.assertEqual(parsed.netloc, "api.github.com")
            self.assertTrue(parsed.path.startswith("/repos/woahwhattheheck/commons/"))
        self.assertTrue(all(h == "Bearer ghp_TESTTOKEN123" for h in self.transport.auth_headers))

    def test_arbitrary_api_origin_rejected(self):
        for url in (
            "http://api.github.com/repos/woahwhattheheck/commons/contents/x",
            "https://evil.example/repos/woahwhattheheck/commons/contents/x",
            "https://user:pw@api.github.com/repos/woahwhattheheck/commons/contents/x",
        ):
            with self.subTest(url=url):
                with self.assertRaises(mod.ValidationError):
                    mod._assert_canonical_url(url)

    def test_duplicate_json_key_rejected(self):
        with self.assertRaises(mod.ValidationError):
            mod._parse_json_strict(b'{"a":1,"a":2}')

    def test_message_file_hash_rejects_empty_and_hashes_exact_bytes(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "msg.txt"
            p.write_bytes(b"abc")
            self.assertEqual(mod.digest_message_file(p), hashlib.sha256(b"abc").hexdigest())
            p.write_bytes(b"")
            with self.assertRaises(mod.ValidationError):
                mod.digest_message_file(p)

    def test_release_reacquire_history_chain_advances(self):
        self.acquire()
        first = self.transport.record()["history_sha256"]
        self.lock.release_unsent("email", self.email, **self.owner, reason="never sent")
        second = self.transport.record()["history_sha256"]
        self.lock.acquire("email", self.email, agent_id="Z-NEXT", operation_id="OP-NEXT")
        third = self.transport.record()["history_sha256"]
        self.assertEqual(len({first, second, third}), 3)
        self.assertEqual(self.transport.record()["previous_history_sha256"], second)

    def test_update_cas_loss_does_not_reopen_or_overwrite(self):
        self.acquire()
        before = self.transport.record_bytes()
        self.transport.race_next_put = True
        with self.assertRaises(mod.ConflictError):
            self.lock.release_unsent("email", self.email, **self.owner, reason="unsent")
        self.assertEqual(self.transport.record_bytes(), before)

    def test_records_bind_canonical_authority_generation(self):
        self.acquire()
        record = self.transport.record()
        self.assertEqual(record["authority"], mod.AUTHORITY_DOCUMENT)
        self.assertEqual(record["authority_digest"], mod.AUTHORITY_DIGEST)

    def test_arm_binds_exact_payload_and_is_idempotent(self):
        self.acquire()
        first = self.arm()
        self.assertEqual(first["state"], "ARMED")
        record = self.transport.record()
        self.assertEqual(record["message_sha256"], hashlib.sha256(b"hello").hexdigest())
        self.assertEqual(record["channel"], "email")
        counter = self.transport.counter
        again = self.arm()
        self.assertEqual(again["outcome"], "ALREADY_ARMED")
        self.assertEqual(self.transport.counter, counter)

    def test_arm_payload_change_requires_release_not_rearm(self):
        self.acquire()
        self.arm()
        with self.assertRaises(mod.ConflictError):
            self.lock.arm(
                "email", self.email, **self.owner,
                message_sha256=hashlib.sha256(b"different").hexdigest(),
                channel="email", compensation_path="$2500 paid pilot",
            )

    def test_armed_may_release_unsent_then_reacquire(self):
        self.acquire()
        self.arm()
        released = self.lock.release_unsent("email", self.email, **self.owner, reason="armed but provider was never called")
        self.assertEqual(released["state"], "RELEASED")
        self.assertEqual(self.transport.record()["released_from_state"], "ARMED")
        again = self.lock.acquire("email", self.email, agent_id="Z-NEXT", operation_id="OP-NEXT")
        self.assertEqual(again["state"], "ACTIVE")

    def test_dispatch_consumes_slot_before_provider_effect(self):
        self.acquire()
        self.arm()
        receipt = self.dispatch()
        self.assertEqual(receipt["state"], "OUTCOME_UNKNOWN")
        self.assertEqual(receipt["outcome"], "OUTCOME_UNKNOWN_SLOT_CONSUMED")
        self.assertFalse(receipt["external_send_authorized"])
        record = self.transport.record()
        self.assertIsNotNone(record["dispatched_at"])

    def test_dispatch_same_owner_replay_is_blocked(self):
        self.consume()
        with self.assertRaises(mod.ConflictError):
            self.dispatch()

    def test_outcome_unknown_blocks_acquire_and_release(self):
        self.consume()
        with self.assertRaises(mod.ConflictError):
            self.lock.acquire("email", self.email, **self.owner)
        with self.assertRaises(mod.ConflictError):
            self.lock.acquire("email", self.email, agent_id="Z-OTHER", operation_id="OP-OTHER")
        with self.assertRaises(mod.ConflictError):
            self.lock.release_unsent("email", self.email, **self.owner, reason="cannot assert unsent after dispatch")

    def test_finalize_requires_dispatch_first(self):
        self.acquire()
        self.arm()
        kwargs = self.payload()
        with self.assertRaises(mod.ConflictError):
            self.lock.finalize_contacted("email", self.email, **self.owner, **kwargs, provider_receipt="provider-accepted")

    def test_finalize_requires_exact_armed_payload(self):
        self.consume()
        with self.assertRaises(mod.ConflictError):
            self.lock.finalize_contacted(
                "email", self.email, **self.owner,
                message_sha256=hashlib.sha256(b"different").hexdigest(), channel="email",
                compensation_path="$2500 paid pilot", provider_receipt="provider-accepted",
            )

    def test_outcome_unknown_retains_no_provider_receipt(self):
        self.consume()
        record = self.transport.record()
        self.assertEqual(record["state"], "OUTCOME_UNKNOWN")
        self.assertNotIn("provider_receipt_sha256", record)
        self.assertFalse(record["provider_send_completed"])


if __name__ == "__main__":
    unittest.main()
