from __future__ import annotations

import base64
import hashlib
import inspect
import json
import unittest
from urllib.parse import parse_qs, unquote, urlsplit

from revenue.prospect_contact_lock import ProspectContactLock as package_lock
from revenue.prospect_contact_lock import hardened
from revenue.prospect_contact_lock import lock as core

DATE = "Tue, 15 Sep 2026 00:40:00 GMT"


class TransactionalTransport:
    supports_authority_transactions = True

    def __init__(self, *, protected: bool = True):
        self.protected = protected
        self.urls: list[str] = []
        self.bodies: list[tuple[str, str, object | None]] = []
        self.race_before_patch = False
        self.counter = 1
        self.marker_raw = (
            json.dumps(
                hardened.EXPECTED_AUTHORITY_MARKER,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
            + b"\n"
        )
        self.head = "1" * 40
        self.commit_tree = {self.head: "2" * 40}
        self.commit_parent: dict[str, str | None] = {self.head: None}
        self.tree_snapshot = {
            "2" * 40: {hardened.AUTHORITY_MARKER_PATH: self.marker_raw}
        }
        self.blobs: dict[str, bytes] = {}

    @staticmethod
    def _sha(prefix: str, payload: bytes) -> str:
        return hashlib.sha1(prefix.encode() + b"\0" + payload).hexdigest()

    @staticmethod
    def _response(status: int, obj: object) -> core.Response:
        return core.Response(status, {"Date": DATE}, json.dumps(obj).encode())

    def _snapshot_for_commit(self, sha: str) -> dict[str, bytes]:
        return self.tree_snapshot[self.commit_tree[sha]]

    def request(self, method, url, headers, body):
        self.urls.append(url)
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.netloc != "api.github.com":
            raise AssertionError("non-canonical URL")
        if not parsed.path.startswith("/repos/woahwhattheheck/commons/"):
            raise AssertionError("escaped repo")
        payload = json.loads(body.decode()) if body else None
        self.bodies.append((method, parsed.path, payload))

        suffix = parsed.path.split("/repos/woahwhattheheck/commons/", 1)[1]
        if method == "GET" and suffix.startswith("branches/"):
            return self._response(
                200,
                {"protected": self.protected, "commit": {"sha": self.head}},
            )
        if suffix.startswith("git/refs/heads/"):
            if method == "GET":
                return self._response(
                    200,
                    {
                        "ref": f"refs/heads/{core.AUTHORITY_BRANCH}",
                        "object": {"type": "commit", "sha": self.head},
                    },
                )
            if method == "PATCH":
                assert payload is not None
                assert payload.get("force") is False
                new_sha = payload["sha"]
                if self.race_before_patch:
                    self.race_before_patch = False
                    race_sha = self._sha("race", str(self.counter).encode())
                    self.counter += 1
                    self.commit_tree[race_sha] = self.commit_tree[self.head]
                    self.commit_parent[race_sha] = self.head
                    self.head = race_sha
                    return self._response(
                        422, {"message": "Update is not a fast forward"}
                    )
                if self.commit_parent.get(new_sha) != self.head:
                    return self._response(
                        422, {"message": "Update is not a fast forward"}
                    )
                self.head = new_sha
                return self._response(
                    200, {"object": {"type": "commit", "sha": self.head}}
                )
        if method == "GET" and suffix.startswith("git/commits/"):
            sha = suffix.rsplit("/", 1)[1]
            if sha not in self.commit_tree:
                return self._response(404, {"message": "not found"})
            return self._response(
                200,
                {"sha": sha, "tree": {"sha": self.commit_tree[sha]}},
            )
        if method == "GET" and suffix.startswith("contents/"):
            path = unquote(suffix.split("contents/", 1)[1])
            ref = parse_qs(parsed.query).get("ref", [""])[0]
            if ref not in self.commit_tree:
                return self._response(404, {"message": "unknown ref"})
            raw = self._snapshot_for_commit(ref).get(path)
            if raw is None:
                return self._response(404, {"message": "not found"})
            return self._response(
                200,
                {
                    "sha": hashlib.sha1(raw).hexdigest(),
                    "encoding": "base64",
                    "content": base64.b64encode(raw).decode(),
                },
            )
        if method == "POST" and suffix == "git/blobs":
            assert payload is not None and payload.get("encoding") == "utf-8"
            raw = payload["content"].encode()
            sha = hashlib.sha1(raw).hexdigest()
            self.blobs[sha] = raw
            return self._response(201, {"sha": sha})
        if method == "POST" and suffix == "git/trees":
            assert payload is not None
            base_tree = payload["base_tree"]
            snapshot = dict(self.tree_snapshot[base_tree])
            for entry in payload["tree"]:
                snapshot[entry["path"]] = self.blobs[entry["sha"]]
            raw = json.dumps(
                sorted((k, hashlib.sha1(v).hexdigest()) for k, v in snapshot.items())
            ).encode()
            new_tree = self._sha("tree", raw)
            self.tree_snapshot[new_tree] = snapshot
            return self._response(201, {"sha": new_tree})
        if method == "POST" and suffix == "git/commits":
            assert payload is not None
            parent = payload["parents"][0]
            raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
            sha = self._sha("commit", raw + str(self.counter).encode())
            self.counter += 1
            self.commit_tree[sha] = payload["tree"]
            self.commit_parent[sha] = parent
            return self._response(201, {"sha": sha})
        raise AssertionError((method, url, payload))


class TransactionalAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.transport = TransactionalTransport()
        self.lock = hardened._TestProspectContactLock("unit-test-token", self.transport)
        self.email = "Lead.Person+Pilot@Example.com"
        self.owner = dict(agent_id="ZRS-P8V3", operation_id="OP-PAID-POSTMERGE")

    def test_every_supported_production_import_is_same_transport_free_class(self):
        self.assertIs(core.ProspectContactLock, hardened.ProspectContactLock)
        self.assertIs(core.ProspectContactLock, package_lock)
        params = list(inspect.signature(package_lock).parameters)
        self.assertEqual(params, ["token"])
        with self.assertRaises(TypeError):
            package_lock("unit-test-token", self.transport)
        with self.assertRaises(TypeError):
            hardened.ProspectContactLock("unit-test-token", transport=self.transport)
        with self.assertRaises(TypeError):
            core.ProspectContactLock("unit-test-token", self.transport)

    def test_private_test_transport_artifacts_cannot_verify_as_production(self):
        receipt = self.lock.acquire("email", self.email, **self.owner)
        self.assertIs(receipt["test_only_transport"], True)
        with self.assertRaises(core.ValidationError):
            core.verify_receipt(receipt)
        status = self.lock.status("email", self.email)
        self.assertIs(status["test_only_transport"], True)

    def test_unprotected_authority_fails_closed_before_contact_read(self):
        transport = TransactionalTransport(protected=False)
        lock = hardened._TestProspectContactLock("unit-test-token", transport)
        with self.assertRaises(core.RemoteError):
            lock.status("email", self.email)
        self.assertFalse(any("/contents/" in url for url in transport.urls))

    def test_acquire_reads_marker_and_record_at_one_immutable_head(self):
        old_head = self.transport.head
        receipt = self.lock.acquire("email", self.email, **self.owner)
        self.assertEqual(receipt["state"], "ACTIVE")
        self.assertIs(receipt["test_only_transport"], True)
        content_refs = [
            parse_qs(urlsplit(url).query).get("ref", [None])[0]
            for url in self.transport.urls
            if "/contents/" in url
        ]
        self.assertGreaterEqual(len(content_refs), 3)
        self.assertEqual(content_refs[0], old_head)
        self.assertEqual(content_refs[1], old_head)
        self.assertNotEqual(self.transport.head, old_head)
        self.assertEqual(content_refs[-1], self.transport.head)

    def test_mutation_uses_non_force_whole_ref_cas(self):
        self.lock.acquire("email", self.email, **self.owner)
        patch_payloads = [
            body
            for method, path, body in self.transport.bodies
            if method == "PATCH" and "/git/refs/heads/" in path
        ]
        self.assertEqual(len(patch_payloads), 1)
        self.assertIs(patch_payloads[0]["force"], False)
        self.assertEqual(patch_payloads[0]["sha"], self.transport.head)

    def test_head_race_loses_without_publishing_candidate_record(self):
        old_head = self.transport.head
        self.transport.race_before_patch = True
        with self.assertRaises(core.ConflictError):
            self.lock.acquire("email", self.email, **self.owner)
        self.assertNotEqual(self.transport.head, old_head)
        target = core.normalize_target("email", self.email)
        self.assertNotIn(
            core._record_path(target),
            self.transport._snapshot_for_commit(self.transport.head),
        )

    def test_composite_zero_amount_signals_are_rejected(self):
        for bad in ("$0 invoice", "0 USD fee", "bounty $0", "paid 0 EUR"):
            with self.subTest(bad=bad):
                with self.assertRaises(core.ValidationError):
                    hardened._strict_compensation_category(bad)

    def test_distinct_positive_amount_can_override_zero_reference(self):
        category = hardened._strict_compensation_category(
            "old invoice $0; new paid bounty $90"
        )
        self.assertTrue(category)


if __name__ == "__main__":
    unittest.main()
