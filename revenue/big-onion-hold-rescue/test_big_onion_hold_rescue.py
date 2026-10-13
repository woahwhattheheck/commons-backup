import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import big_onion_hold_rescue as rescue


class BigOnionHoldRescueTests(unittest.TestCase):
    def setUp(self):
        self.payload, self.manifest = rescue.load_fixture()

    def test_exact_six_event_acceptance_is_e1_e2_in_source_order(self):
        result = rescue.BigOnionHoldRescue().evaluate(
            self.payload["events"], as_of=self.payload["as_of"]
        )
        self.assertEqual([item["event_id"] for item in result.recommendations], ["E1", "E2"])
        self.assertEqual([item["source_index"] for item in result.recommendations], [0, 1])

    def test_exact_48_hour_boundary_is_eligible(self):
        result = rescue.BigOnionHoldRescue().evaluate(
            [self.payload["events"][1]], as_of=self.payload["as_of"]
        )
        self.assertEqual(result.recommendations[0]["event_id"], "E2")
        self.assertEqual(result.recommendations[0]["age_hours"], 48)

    def test_too_young_resolved_and_ineligible_states_do_not_emit(self):
        result = rescue.BigOnionHoldRescue().evaluate(
            self.payload["events"][2:5], as_of=self.payload["as_of"]
        )
        self.assertEqual(result.recommendations, ())
        self.assertEqual(
            [item["reason"] for item in result.diagnostics],
            ["TOO_YOUNG", "ALREADY_RESOLVED", "INELIGIBLE_STATE"],
        )

    def test_malformed_row_does_not_emit(self):
        result = rescue.BigOnionHoldRescue().evaluate(
            [self.payload["events"][5], {"event_id": "BAD"}],
            as_of=self.payload["as_of"],
        )
        self.assertEqual(result.recommendations, ())
        self.assertEqual([item["reason"] for item in result.diagnostics], ["MALFORMED_ROW", "MALFORMED_ROW"])

    def test_replay_is_identical_and_has_zero_side_effects(self):
        evaluator = rescue.BigOnionHoldRescue({"queue": ["unchanged"]})
        before = copy.deepcopy(evaluator.authoritative_state)
        first = evaluator.evaluate(self.payload["events"], as_of=self.payload["as_of"])
        second = evaluator.evaluate(self.payload["events"], as_of=self.payload["as_of"])
        self.assertEqual(first, second)
        self.assertEqual(first.digest(), second.digest())
        self.assertEqual(before, evaluator.authoritative_state)
        self.assertEqual((first.sends, first.actions, first.provider_writes, first.state_mutations, first.events_added), (0, 0, 0, 0, 0))

    def test_cutoff_is_pinned_to_48_hours(self):
        with self.assertRaises(rescue.IntegrityError):
            rescue.BigOnionHoldRescue().evaluate(
                self.payload["events"], as_of=self.payload["as_of"], cutoff_hours=47
            )

    def test_fixture_and_manifest_tampering_fail_closed(self):
        base = Path(rescue.__file__).resolve().parent
        fixture = base / "fixtures/six_events.json"
        manifest = base / "fixtures/manifest.json"
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            bad_fixture = td / "fixture.json"
            bad_fixture.write_text(fixture.read_text().replace('"E1"', '"X1"', 1), encoding="utf-8")
            with self.assertRaises(rescue.IntegrityError):
                rescue.load_fixture(bad_fixture, manifest)
            bad_manifest = json.loads(manifest.read_text())
            bad_manifest["cutoff_hours"] = 47
            bad_manifest_path = td / "manifest.json"
            bad_manifest_path.write_text(json.dumps(bad_manifest, sort_keys=True), encoding="utf-8")
            with self.assertRaises(rescue.IntegrityError):
                rescue.load_fixture(fixture, bad_manifest_path)

    def test_sensitive_shaped_fields_fail_closed(self):
        variants = []

        event = copy.deepcopy(self.payload["events"][0])
        event["email"] = "synthetic@example.invalid"
        variants.append(("canonical", event))

        event = copy.deepcopy(self.payload["events"][0])
        event["customerName"] = "Synthetic Person"
        variants.append(("camel_case", event))

        event = copy.deepcopy(self.payload["events"][0])
        event["payment-token"] = "synthetic-token"
        variants.append(("punctuation", event))

        event = copy.deepcopy(self.payload["events"][0])
        event["card number"] = "4111"
        variants.append(("space", event))

        event = copy.deepcopy(self.payload["events"][0])
        event["metadata"] = {"email": "synthetic@example.invalid"}
        variants.append(("nested_mapping", event))

        event = copy.deepcopy(self.payload["events"][0])
        event["metadata"] = [{"paymentMethod": "synthetic"}]
        variants.append(("nested_list", event))

        for label, event in variants:
            with self.subTest(label=label):
                with self.assertRaises(rescue.IntegrityError):
                    rescue.BigOnionHoldRescue().evaluate([event], as_of=self.payload["as_of"])

    def test_benign_nested_metadata_remains_eligible(self):
        event = copy.deepcopy(self.payload["events"][0])
        event["metadata"] = {"note": "synthetic-only", "labels": ["fixture"]}
        result = rescue.BigOnionHoldRescue().evaluate([event], as_of=self.payload["as_of"])
        self.assertEqual([item["event_id"] for item in result.recommendations], ["E1"])

    def test_run_acceptance_summary(self):
        summary = rescue.run_acceptance()
        self.assertEqual(summary["eligible_ids"], ["E1", "E2"])
        self.assertEqual(summary["recommendation_count"], 2)
        self.assertTrue(summary["replay_identical"])
        self.assertEqual((summary["sends"], summary["actions"], summary["provider_writes"], summary["state_mutations"], summary["events_added"]), (0, 0, 0, 0, 0))

    def test_cli_is_metadata_only_and_passes(self):
        result = subprocess.run(
            [sys.executable, "big_onion_hold_rescue.py"],
            cwd=Path(rescue.__file__).resolve().parent,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertTrue(data["ok"])
        self.assertEqual(data["eligible_ids"], ["E1", "E2"])
        self.assertEqual((data["sends"], data["actions"], data["provider_writes"]), (0, 0, 0))


if __name__ == "__main__":
    unittest.main()
