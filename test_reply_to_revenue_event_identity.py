from __future__ import annotations

import copy
import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "reply_to_revenue_event_identity",
    ROOT / "host" / "reply_to_revenue.py",
)
assert SPEC and SPEC.loader
r2r = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(r2r)


class ReplyToRevenueEventIdentityTests(unittest.TestCase):
    def _write(self, directory: str, observations: dict) -> Path:
        path = Path(directory) / "observations.json"
        path.write_text(r2r.canonical_text(observations), encoding="utf-8")
        return path

    def test_identical_full_envelope_retry_is_ingested_once(self) -> None:
        observations = r2r.read_object(r2r.OBSERVATIONS_PATH)
        observations["events"].append(copy.deepcopy(observations["events"][0]))
        observations["monitor"]["attributed_inbound"] = len(observations["events"]) - 1
        with tempfile.TemporaryDirectory() as directory:
            loaded = r2r.load_observations(self._write(directory, observations))
        self.assertEqual(len(loaded["events"]), 4)

    def test_same_ref_and_payload_with_changed_envelope_collides(self) -> None:
        original = r2r.read_object(r2r.OBSERVATIONS_PATH)
        mutations = {
            "received_at": "2026-08-26T14:08:11Z",
            "prospect_key": "different-buyer",
            "markers": ["operator note only"],
            "provider": "different-provider",
            "matched_receipt_id": "different-receipt",
            "requested_classification": "NEGATIVE",
        }
        for field, value in mutations.items():
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                observations = copy.deepcopy(original)
                duplicate = copy.deepcopy(observations["events"][0])
                duplicate[field] = value
                observations["events"].append(duplicate)
                observations["monitor"]["attributed_inbound"] = len(original["events"])
                with self.assertRaisesRegex(
                    r2r.CollisionError,
                    "different observation envelope",
                ):
                    r2r.load_observations(self._write(directory, observations))


if __name__ == "__main__":
    unittest.main()
