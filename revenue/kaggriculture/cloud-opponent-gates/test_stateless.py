"""Source-bound stateless and saved-evidence tests; no new scored games."""
from __future__ import annotations
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import diagnose
import read_evidence

SOURCE = Path(os.environ.get("TITAN_COK_SOURCE", "sources/cok-v10/main.py"))


class StatelessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.namespace = diagnose.load_source(SOURCE)
        cls.data = read_evidence.read()

    def frame(self, seat=0):
        case = self.data["cases"][seat]
        return copy.deepcopy(next(row["observation"] for row in case["frames"] if row["step"] == 72))

    def matching_public_fixture(self, seat=0):
        obs = self.frame(seat)
        obs["town"]["unlocked_shops"] = ["BAKERY"]
        obs["farms"][seat]["money"] = 100
        rival = obs["farms"][1-seat]
        rival["money"] = 200
        rival["tiles"] = [[{"animal": "COW"}] + [{"animal": "SHEEP"} for _ in range(4)] +
                          [{"crop": "WHEAT"} for _ in range(5)] + [{"crop": "MELON"} for _ in range(4)]]
        return obs

    def test_real_gate_frames_both_positions(self):
        for seat in (0, 1):
            facts = diagnose.gate_facts(self.namespace, self.frame(seat))
            self.assertFalse(facts["predicate"])
            self.assertEqual(facts["shops"], ["PET_CAFE"])
            self.assertEqual(facts["rival_counts"], {"COW": 3, "SHEEP": 2, "WHEAT": 7, "MELON": 12})

    def test_source_positive_condition_both_positions(self):
        for seat in (0, 1):
            facts = diagnose.gate_facts(self.namespace, self.matching_public_fixture(seat))
            self.assertTrue(facts["predicate"])
            self.assertTrue(all(facts["conditions"].values()))

    def test_cash_boundaries_and_upstream_numeric_coercion(self):
        obs = self.matching_public_fixture()
        for invalid in (200, 201, None, True, float("nan"), float("inf"), "not-money"):
            obs["farms"][0]["money"] = invalid
            self.assertFalse(diagnose.gate_facts(self.namespace, obs)["predicate"])
        obs["farms"][0]["money"] = "100"
        self.assertTrue(diagnose.gate_facts(self.namespace, obs)["predicate"])

    def test_source_tolerance_and_malformed_tiles(self):
        obs = self.matching_public_fixture()
        obs["farms"][1]["tiles"][0].append({"crop": "MELON"})
        self.assertTrue(diagnose.gate_facts(self.namespace, obs)["predicate"])
        obs["farms"][1]["tiles"][0].append({"crop": "MELON"})
        self.assertFalse(diagnose.gate_facts(self.namespace, obs)["predicate"])
        obs["farms"][1]["tiles"] = [None]
        self.assertFalse(diagnose.gate_facts(self.namespace, obs)["complete_public_inputs"])

    def test_source_tables_and_state_are_unmodified(self):
        before = copy.deepcopy(self.namespace["_ROUTE_STATE"])
        facts = diagnose.gate_facts(self.namespace, self.matching_public_fixture())
        rows = diagnose.route_prefixes(self.namespace)
        self.assertTrue(facts["predicate"])
        self.assertEqual(self.namespace["_ROUTE_STATE"], before)
        self.assertEqual(len(rows), 21)
        self.assertEqual(rows[0]["first_action_difference"], 168)
        self.assertEqual({row["first_action_difference"] for row in rows[1:]}, {72, 73})

    def test_all_complete_action_streams_decode(self):
        for case in self.data["cases"]:
            for seat in (0, 1):
                rows = read_evidence.actions(self.data, case, seat)
                self.assertEqual([row["step"] for row in rows], list(range(719)))
                self.assertEqual(set(rows[0]["action"]), {"farmer", "hands", "market"})
        with self.assertRaises(ValueError):
            read_evidence.actions(self.data, self.data["cases"][0], 2)

    def test_changed_evidence_and_source_are_detected(self):
        with tempfile.TemporaryDirectory() as temp:
            bundle = Path(temp)/"evidence.b64"
            original = (read_evidence.HERE/"evidence.json.gz.b64").read_text()
            bundle.write_text(("A" if original[0] != "A" else "B") + original[1:])
            with self.assertRaises(ValueError):
                read_evidence.read(bundle=bundle)
            source = Path(temp)/"changed.py"
            source.write_bytes(SOURCE.read_bytes()+b"\n")
            with self.assertRaises(ValueError):
                diagnose.load_source(source)

    def assert_cli_preserves_input_aliases(self, kind):
        for alias in ("direct", "symlink", "hardlink"):
            with self.subTest(input_kind=kind, alias=alias), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                source, observations = root / "source.py", root / "observations.jsonl"
                source.write_bytes(SOURCE.read_bytes())
                observations.write_text(json.dumps({"observation": self.frame()}) + "\n", encoding="utf-8")
                incoming = source if kind == "source" else observations
                before = incoming.read_bytes()
                output = incoming if alias == "direct" else root / "output.json"
                if alias == "symlink":
                    output.symlink_to(incoming)
                elif alias == "hardlink":
                    output.hardlink_to(incoming)
                result = subprocess.run([sys.executable, str(Path(diagnose.__file__)),
                    "--source", str(source), "--observations", str(observations),
                    "--output", str(output)], capture_output=True, text=True)
                self.assertEqual(incoming.read_bytes(), before, "CLI changed its input")
                self.assertEqual(result.returncode, 2)
                self.assertIn("must not alias", result.stderr)

    def test_cli_preserves_source_aliases(self):
        self.assert_cli_preserves_input_aliases("source")

    def test_cli_preserves_observation_aliases(self):
        self.assert_cli_preserves_input_aliases("observations")

    def test_stateless_cli_does_not_claim_activation(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/"report.json"
            subprocess.run([sys.executable, str(Path(diagnose.__file__)), "--source", str(SOURCE.resolve()),
                            "--output", str(path)], check=True, capture_output=True, text=True)
            report = json.loads(path.read_text())
            self.assertIs(report["activation_measured"], False)
            self.assertEqual(len(report["route_prefixes"]), 21)


if __name__ == "__main__":
    unittest.main(verbosity=2)
