from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import reply_intake


ROUTES = (
    ("OPT_OUT", "DNC/CLOSE"),
    ("AUTO_RESPONSE", "WAIT_FOR_HUMAN_REPLY"),
    ("NEGATIVE", "CLOSE"),
    ("QUESTION", "DRAFT_REPLY"),
    ("POSITIVE_SCOPE", "NEEDS_ACCEPTANCE"),
    ("NEEDS_HUMAN", "ESCALATE_ONLY_IF_BUYER_REQUESTS_BRYCE"),
)
PRIVATE_FIELDS = (
    "body",
    "raw",
    "raw_body",
    "headers",
    "email",
    "from",
    "to",
    "subject",
    "credentials",
    "password",
    "token",
    "secret",
    "content",
    "message",
    "payload",
    "private",
)
FORBIDDEN_CLAIMS = (
    "replied",
    "accepted",
    "invoiced",
    "authorized",
    "settled",
    "delivered",
    "paid",
)


def _sha(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _envelope(
    classification: str,
    *,
    event_ref: str | None = None,
    payload_sha256: str | None = None,
    prospect_key: str | None = None,
) -> dict[str, str]:
    token = classification.lower().replace("_", "-")
    return {
        "event_ref": event_ref or f"opaque:fixture-{token}-event-01",
        "received_at": "2026-08-26T17:32:00Z",
        "prospect_key": prospect_key or f"prospect.{token}.01",
        "payload_sha256": payload_sha256 or _sha(f"opaque-payload-{token}"),
        "classification": classification,
    }


class ReplyIntakeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.store = Path(self.temp.name) / "store"
        self.schema = reply_intake.load_schema()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _assert_stored_is_canonical_lf(
        self,
        envelope: dict[str, str],
        returned: bytes,
    ) -> None:
        path = reply_intake.store_path_for(self.store, envelope["event_ref"])
        stored = path.read_bytes()
        canonical = reply_intake.canonical_bytes(json.loads(stored.decode("utf-8")))
        self.assertEqual(returned, stored)
        self.assertEqual(stored, canonical)
        self.assertNotIn(b"\r", stored)
        self.assertIn(b"\n", stored)

    def _record(self, envelope: dict[str, str]) -> bytes:
        return reply_intake.record_envelope(envelope, self.store)

    def test_six_route_fixtures_pass(self) -> None:
        for classification, next_action in ROUTES:
            with self.subTest(classification=classification):
                envelope = _envelope(classification)
                blob = self._record(envelope)
                self._assert_stored_is_canonical_lf(envelope, blob)
                receipt = json.loads(blob.decode("utf-8"))
                reply_intake.validate_receipt(receipt, self.schema)
                self.assertEqual(receipt["classification"], classification)
                self.assertEqual(receipt["next_action"], next_action)
                self.assertEqual(receipt["status"], "RECORDED")
                self.assertEqual(receipt["event_ref"], envelope["event_ref"])
                self.assertEqual(receipt["payload_sha256"], envelope["payload_sha256"])
                self.assertEqual(
                    receipt["receipt_id"],
                    reply_intake.receipt_id_for(envelope["event_ref"]),
                )
                text = blob.decode("utf-8").lower()
                for claim in FORBIDDEN_CLAIMS:
                    self.assertNotRegex(text, rf"\b{claim}\b")

    def test_identical_replay_is_byte_identical(self) -> None:
        envelope = _envelope("QUESTION")
        first = self._record(envelope)
        second = self._record(dict(envelope))
        self.assertEqual(first, second)
        self._assert_stored_is_canonical_lf(envelope, first)
        self._assert_stored_is_canonical_lf(envelope, second)
        third_store = Path(self.temp.name) / "replay-cli"
        envelope_path = Path(self.temp.name) / "question.json"
        envelope_path.write_bytes(reply_intake.canonical_bytes(envelope))
        command = [
            sys.executable,
            str(Path(__file__).with_name("reply_intake.py")),
            "--envelope",
            str(envelope_path),
            "--store",
            str(third_store),
        ]
        first_cli = subprocess.run(command, check=False, capture_output=True)
        second_cli = subprocess.run(command, check=False, capture_output=True)
        self.assertEqual(first_cli.returncode, 0, first_cli.stderr)
        self.assertEqual(second_cli.returncode, 0, second_cli.stderr)
        self.assertEqual(first_cli.stdout, second_cli.stdout)
        self.assertEqual(
            first_cli.stdout,
            reply_intake.store_path_for(third_store, envelope["event_ref"]).read_bytes(),
        )

    def test_same_event_ref_different_hash_fails_nonzero(self) -> None:
        envelope = _envelope("NEGATIVE")
        self._record(envelope)
        colliding = dict(envelope)
        colliding["payload_sha256"] = _sha("different-opaque-payload")
        self.assertNotEqual(envelope["payload_sha256"], colliding["payload_sha256"])
        with self.assertRaises(reply_intake.CollisionError):
            self._record(colliding)
        envelope_path = Path(self.temp.name) / "negative.json"
        collide_path = Path(self.temp.name) / "negative-collide.json"
        envelope_path.write_bytes(reply_intake.canonical_bytes(envelope))
        collide_path.write_bytes(reply_intake.canonical_bytes(colliding))
        script = str(Path(__file__).with_name("reply_intake.py"))
        store = Path(self.temp.name) / "cli-store"
        first = subprocess.run(
            [sys.executable, script, "--envelope", str(envelope_path), "--store", str(store)],
            check=False,
            capture_output=True,
        )
        second = subprocess.run(
            [sys.executable, script, "--envelope", str(collide_path), "--store", str(store)],
            check=False,
            capture_output=True,
        )
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertNotEqual(second.returncode, 0)
        self.assertEqual(second.returncode, reply_intake.EXIT_COLLISION)

    def test_raw_private_fields_fail_schema(self) -> None:
        envelope = _envelope("OPT_OUT")
        reply_intake.validate_envelope(envelope, self.schema)
        self.assertFalse(self.schema["$defs"]["envelope"]["additionalProperties"])
        self.assertEqual(
            self.schema["$defs"]["envelope"]["propertyNames"]["enum"],
            list(reply_intake.ENVELOPE_FIELDS),
        )
        for field in PRIVATE_FIELDS:
            with self.subTest(field=field):
                dirty = dict(envelope)
                dirty[field] = "redacted-private-value"
                with self.assertRaises(reply_intake.SchemaError):
                    reply_intake.validate_envelope(dirty, self.schema)
                with self.assertRaises(reply_intake.SchemaError):
                    self._record(dirty)
        envelope_path = Path(self.temp.name) / "private.json"
        dirty = dict(envelope)
        dirty["body"] = "do-not-store"
        envelope_path.write_bytes(reply_intake.canonical_bytes(dirty))
        result = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).with_name("reply_intake.py")),
                "--envelope",
                str(envelope_path),
                "--store",
                str(self.store),
            ],
            check=False,
            capture_output=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.returncode, reply_intake.EXIT_SCHEMA)

    def test_positive_scope_stops_only_at_needs_acceptance(self) -> None:
        envelope = _envelope("POSITIVE_SCOPE")
        blob = self._record(envelope)
        receipt = json.loads(blob.decode("utf-8"))
        self.assertEqual(receipt["next_action"], "NEEDS_ACCEPTANCE")
        other_actions = {
            next_action
            for classification, next_action in ROUTES
            if classification != "POSITIVE_SCOPE"
        }
        self.assertNotIn(receipt["next_action"], other_actions)
        mutated = dict(receipt)
        for next_action in other_actions:
            mutated["next_action"] = next_action
            with self.assertRaises(reply_intake.SchemaError):
                reply_intake.validate_receipt(mutated, self.schema)
        text = blob.decode("utf-8").lower()
        for claim in FORBIDDEN_CLAIMS:
            self.assertNotRegex(text, rf"\b{claim}\b")

    def _no_temp_leftovers(self) -> None:
        leftovers = [
            path
            for path in self.store.iterdir()
            if path.name.endswith(".tmp")
        ]
        self.assertEqual(leftovers, [])

    def _concurrent_record(
        self,
        first: dict[str, str],
        second: dict[str, str],
    ) -> tuple[tuple[str, bytes | None], tuple[str, bytes | None]]:
        barrier = threading.Barrier(2, timeout=10)
        original = reply_intake._before_exclusive_claim
        outcomes: list[tuple[str, bytes | None]] = [("pending", None), ("pending", None)]

        def worker(index: int, envelope: dict[str, str]) -> None:
            try:
                blob = reply_intake.record_envelope(envelope, self.store)
            except reply_intake.CollisionError:
                outcomes[index] = ("CollisionError", None)
            except Exception as error:
                outcomes[index] = (type(error).__name__, None)
            else:
                outcomes[index] = ("OK", blob)

        def wait_then_claim() -> None:
            barrier.wait()

        reply_intake._before_exclusive_claim = wait_then_claim
        try:
            threads = [
                threading.Thread(target=worker, args=(0, first)),
                threading.Thread(target=worker, args=(1, second)),
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=10)
                self.assertFalse(thread.is_alive())
        finally:
            reply_intake._before_exclusive_claim = original
        return outcomes[0], outcomes[1]

    def test_concurrent_different_hash_one_ok_one_collision(self) -> None:
        first = _envelope(
            "NEGATIVE",
            event_ref="opaque:race-different-hash-event-01",
        )
        second = dict(first)
        second["payload_sha256"] = _sha("race-other-opaque-payload")
        self.assertNotEqual(first["payload_sha256"], second["payload_sha256"])
        left, right = self._concurrent_record(first, second)
        labels = sorted([left[0], right[0]])
        self.assertEqual(labels, ["CollisionError", "OK"])
        winner = left[1] if left[0] == "OK" else right[1]
        self.assertIsNotNone(winner)
        if winner is None:
            self.fail("winner blob missing")
        self._assert_stored_is_canonical_lf(first, winner)
        receipt = json.loads(winner.decode("utf-8"))
        self.assertIn(
            receipt["payload_sha256"],
            {first["payload_sha256"], second["payload_sha256"]},
        )
        self._no_temp_leftovers()

    def test_concurrent_identical_replay_returns_identical_bytes(self) -> None:
        envelope = _envelope(
            "QUESTION",
            event_ref="opaque:race-identical-replay-event-01",
        )
        left, right = self._concurrent_record(envelope, dict(envelope))
        self.assertEqual(left[0], "OK")
        self.assertEqual(right[0], "OK")
        self.assertIsNotNone(left[1])
        self.assertIsNotNone(right[1])
        self.assertEqual(left[1], right[1])
        if left[1] is None:
            self.fail("identical replay blob missing")
        self._assert_stored_is_canonical_lf(envelope, left[1])
        self._no_temp_leftovers()

    def test_store_bytes_stay_lf_under_windows_text_mode(self) -> None:
        native_binary = getattr(os, "O_BINARY", 0)
        simulated_binary = native_binary or 0x8000
        original_open = os.open
        original_write = os.write
        had_binary = hasattr(os, "O_BINARY")
        original_binary = getattr(os, "O_BINARY", None)
        fd_flags: dict[int, int] = {}

        def fake_open(path, flags, *args, **kwargs):
            native_flags = flags if native_binary else flags & ~simulated_binary
            fd = original_open(path, native_flags, *args, **kwargs)
            fd_flags[fd] = flags
            return fd

        def fake_write(fd, data):
            payload = bytes(data)
            if not (fd_flags.get(fd, 0) & simulated_binary):
                payload = payload.replace(b"\n", b"\r\n")
            return original_write(fd, payload)

        os.O_BINARY = simulated_binary
        os.open = fake_open
        os.write = fake_write
        try:
            envelope = _envelope(
                "QUESTION",
                event_ref="opaque:windows-text-mode-event-01",
            )
            returned = self._record(envelope)
            self._assert_stored_is_canonical_lf(envelope, returned)
            replay = self._record(dict(envelope))
            self.assertEqual(returned, replay)
            self.assertEqual(returned, reply_intake.canonical_bytes(json.loads(returned.decode("utf-8"))))
        finally:
            os.open = original_open
            os.write = original_write
            if had_binary:
                os.O_BINARY = original_binary
            else:
                delattr(os, "O_BINARY")


if __name__ == "__main__":
    unittest.main()
