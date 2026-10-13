import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from integrations.shared_equipment import github_publication
from integrations.shared_equipment.provider_io import EquipmentError


class PublisherCapabilityDriftTests(unittest.TestCase):
    def setUp(self):
        with github_publication._CAPABILITY_DRIFT_LOCK:
            github_publication._CAPABILITY_DRIFT.clear()

    def tearDown(self):
        with github_publication._CAPABILITY_DRIFT_LOCK:
            github_publication._CAPABILITY_DRIFT.clear()

    @staticmethod
    def _invalid_runner(seen, version="publisher-v1"):
        def runner(command, **kwargs):
            seen.append((command, kwargs))
            operation_id = json.loads(kwargs["input"])["operation_id"]
            return subprocess.CompletedProcess(
                command,
                1,
                json.dumps({
                    "allow": False,
                    "incident": False,
                    "operation_id": operation_id,
                    "error": "INVALID_OPERATION",
                    "version": version,
                }),
                "",
            )
        return runner

    def test_definite_invalid_operation_is_structured_and_quarantined(self):
        with tempfile.TemporaryDirectory() as directory:
            client = Path(directory) / "publish.py"
            client.write_text("# fixture", encoding="utf-8")
            seen = []
            actor_tokens = []
            actor_reads = []
            with patch.object(
                github_publication,
                "_named_actor_token",
                side_effect=lambda actor: actor_tokens.append(actor) or "token",
            ), patch.object(
                github_publication,
                "_actor_readback",
                side_effect=lambda token: actor_reads.append(token)
                or {"login": "owner", "id": 1},
            ):
                first = github_publication.publish(
                    "pull.create",
                    {
                        "title": "Fix transport",
                        "body": "Details",
                        "head": "owner:fix",
                        "base": "main",
                    },
                    "fleet-op-0001",
                    actor="owner",
                    client=client,
                    runner=self._invalid_runner(seen),
                )
                second = github_publication.publish(
                    "pull.create",
                    {
                        "title": "Another fix",
                        "body": "Details",
                        "head": "owner:next",
                        "base": "main",
                    },
                    "fleet-op-0002",
                    actor="owner",
                    client=client,
                    runner=lambda *args, **kwargs: self.fail(
                        "quarantined call reached publisher"
                    ),
                )

        self.assertFalse(first["ok"])
        self.assertFalse(first["uncertain"])
        self.assertEqual(first["code"], "publisher_capability_drift")
        self.assertFalse(first["capability_drift"]["cached"])
        self.assertEqual(
            first["capability_drift"]["publisher_version"], "publisher-v1"
        )
        self.assertEqual(
            first["retry_after_seconds"],
            int(github_publication._CAPABILITY_DRIFT_TTL_SECONDS),
        )
        self.assertEqual(second["code"], "publisher_capability_drift")
        self.assertTrue(second["capability_drift"]["cached"])
        self.assertEqual(second["publication"]["operation_id"], "fleet-op-0002")
        self.assertGreater(second["retry_after_seconds"], 0)
        self.assertEqual(len(seen), 1)
        self.assertEqual(actor_tokens, ["owner"])
        self.assertEqual(actor_reads, ["token"])

    def test_quarantine_is_scoped_to_client_and_operation(self):
        with tempfile.TemporaryDirectory() as directory:
            client_a = Path(directory) / "a.py"
            client_b = Path(directory) / "b.py"
            client_a.write_text("# a", encoding="utf-8")
            client_b.write_text("# b", encoding="utf-8")
            seen = []
            github_publication.publish(
                "pull.create",
                {
                    "title": "Fix transport",
                    "body": "Details",
                    "head": "owner:fix",
                    "base": "main",
                },
                "fleet-op-1001",
                client=client_a,
                runner=self._invalid_runner(seen),
            )

            def allowed(command, **kwargs):
                operation_id = json.loads(kwargs["input"])["operation_id"]
                return subprocess.CompletedProcess(
                    command,
                    0,
                    json.dumps({
                        "allow": True,
                        "operation_id": operation_id,
                        "receipt": {"id": 9},
                    }),
                    "",
                )

            other_operation = github_publication.publish(
                "issue.update",
                {"title": "Fix issue", "body": "Details"},
                "fleet-op-1002",
                client=client_a,
                runner=allowed,
            )
            other_client = github_publication.publish(
                "pull.create",
                {
                    "title": "Fix transport",
                    "body": "Details",
                    "head": "owner:fix",
                    "base": "main",
                },
                "fleet-op-1003",
                client=client_b,
                runner=allowed,
            )

        self.assertTrue(other_operation["ok"])
        self.assertTrue(other_client["ok"])

    def test_quarantine_expires_and_preflight_still_runs_first(self):
        with tempfile.TemporaryDirectory() as directory:
            client = Path(directory) / "publish.py"
            client.write_text("# fixture", encoding="utf-8")
            clock = [100.0]
            seen = []
            with patch.object(
                github_publication, "monotonic", side_effect=lambda: clock[0]
            ):
                github_publication.publish(
                    "pull.create",
                    {
                        "title": "Fix transport",
                        "body": "Details",
                        "head": "owner:fix",
                        "base": "main",
                    },
                    "fleet-op-2001",
                    client=client,
                    runner=self._invalid_runner(seen),
                )
                with self.assertRaises(EquipmentError):
                    github_publication.publish(
                        "pull.create",
                        {
                            "title": "Astra transport",
                            "body": "Details",
                            "head": "owner:fix",
                            "base": "main",
                        },
                        "fleet-op-2002",
                        client=client,
                        runner=lambda *args, **kwargs: self.fail(
                            "preflight should block"
                        ),
                    )

                clock[0] += github_publication._CAPABILITY_DRIFT_TTL_SECONDS + 1
                recovered = github_publication.publish(
                    "pull.create",
                    {
                        "title": "Fix transport",
                        "body": "Details",
                        "head": "owner:fix",
                        "base": "main",
                    },
                    "fleet-op-2003",
                    client=client,
                    runner=lambda command, **kwargs: subprocess.CompletedProcess(
                        command,
                        0,
                        json.dumps({
                            "allow": True,
                            "operation_id": "fleet-op-2003",
                            "receipt": {"id": 10},
                        }),
                        "",
                    ),
                )

        self.assertTrue(recovered["ok"])


if __name__ == "__main__":
    unittest.main()
