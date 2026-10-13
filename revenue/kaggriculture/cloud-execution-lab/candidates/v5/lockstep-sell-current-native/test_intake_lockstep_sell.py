from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "intake_lockstep_sell", HERE / "intake_lockstep_sell.py"
)
mod = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(mod)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_blob(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


class IntakeTests(unittest.TestCase):
    def fixture(self):
        agent = b"exact-evaluated-agent\n"
        composer = b"current-self-pinning-composer\n"
        agent_sha = sha256(agent)
        card = json.dumps(
            {
                "agent_sha256": agent_sha,
                "baseline": "v5",
                "changed_members": ["x.py"],
            },
            sort_keys=True,
        ).encode()
        return card, agent, composer, agent_sha

    def test_authenticated_receipt_is_deterministic_and_default_off(self):
        card, agent, composer, agent_sha = self.fixture()
        first = mod.build_receipt(
            card, agent, composer, expected_agent_sha256=agent_sha
        )
        second = mod.build_receipt(
            card, agent, composer, expected_agent_sha256=agent_sha
        )
        self.assertEqual(first, second)
        self.assertEqual(first["status"], "AUTHENTICATED_EVIDENCE_ONLY")
        self.assertEqual(first["promotion"], "DEFAULT_OFF_NO_ROOT_MUTATION")
        self.assertEqual(first["agent_sha256"], agent_sha)
        self.assertEqual(first["composition_card_sha256"], sha256(card))
        self.assertEqual(first["returnbridge_composer"]["git_blob"], git_blob(composer))

    def test_duplicate_agent_witness_is_rejected_even_when_last_value_matches(self):
        _, agent, composer, agent_sha = self.fixture()
        raw = (
            '{"agent_sha256":"%s","agent_sha256":"%s"}'
            % ("0" * 64, agent_sha)
        ).encode()
        with self.assertRaisesRegex(mod.IntakeError, "duplicate JSON object key"):
            mod.build_receipt(raw, agent, composer, expected_agent_sha256=agent_sha)

    def test_nonfinite_card_value_is_rejected(self):
        _, agent, composer, agent_sha = self.fixture()
        raw = ('{"agent_sha256":"%s","mean_delta":NaN}' % agent_sha).encode()
        with self.assertRaisesRegex(mod.IntakeError, "non-finite JSON constant"):
            mod.build_receipt(raw, agent, composer, expected_agent_sha256=agent_sha)

    def test_wrong_card_witness_is_rejected(self):
        card, agent, composer, agent_sha = self.fixture()
        parsed = json.loads(card)
        parsed["agent_sha256"] = "0" * 64
        with self.assertRaisesRegex(mod.IntakeError, "card agent witness"):
            mod.build_receipt(
                json.dumps(parsed).encode(),
                agent,
                composer,
                expected_agent_sha256=agent_sha,
            )

    def test_wrong_agent_bytes_are_rejected(self):
        card, agent, composer, agent_sha = self.fixture()
        with self.assertRaisesRegex(mod.IntakeError, "agent bytes"):
            mod.build_receipt(
                card,
                agent + b"tamper",
                composer,
                expected_agent_sha256=agent_sha,
            )

    def test_composer_identity_is_recorded_without_freezing_rebinds(self):
        card, agent, composer, agent_sha = self.fixture()
        first = mod.build_receipt(card, agent, composer, expected_agent_sha256=agent_sha)
        rebound = composer + b"scheduler-pin-rebound\n"
        second = mod.build_receipt(card, agent, rebound, expected_agent_sha256=agent_sha)
        self.assertNotEqual(
            first["returnbridge_composer"]["git_blob"],
            second["returnbridge_composer"]["git_blob"],
        )
        self.assertEqual(first["agent_sha256"], second["agent_sha256"])

    def test_paths_reject_empty_artifact_before_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            card = root / "card.json"
            agent = root / "agent.py"
            composer = root / "compose.py"
            card.write_text(
                '{"agent_sha256":"%s"}' % mod.EXPECTED_AGENT_SHA256
            )
            agent.write_bytes(b"")
            composer.write_text("x")
            with self.assertRaisesRegex(mod.IntakeError, "agent artifact is empty"):
                mod.validate_paths(card, agent, composer)

    def test_paths_reject_empty_composer_before_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            card = root / "card.json"
            agent = root / "agent.py"
            composer = root / "compose.py"
            card.write_text(
                '{"agent_sha256":"%s"}' % mod.EXPECTED_AGENT_SHA256
            )
            agent.write_bytes(b"not-the-production-agent")
            composer.write_bytes(b"")
            with self.assertRaisesRegex(mod.IntakeError, "ReturnBridge composer is empty"):
                mod.validate_paths(card, agent, composer)

    def test_production_agent_witness_constant_is_exact(self):
        self.assertEqual(
            mod.EXPECTED_AGENT_SHA256,
            "6355999beb5c3f3948bbce9dcbd69380b773b5ebf084226c39f41a07db4bd20e",
        )


if __name__ == "__main__":
    unittest.main()
