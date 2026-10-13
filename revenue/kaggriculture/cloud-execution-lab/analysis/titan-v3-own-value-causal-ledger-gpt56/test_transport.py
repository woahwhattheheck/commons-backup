# SPDX-License-Identifier: Apache-2.0
from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest

import causal_ledger as ledger
from causal_ledger.cli import _atomic_write_json
from support import arm_provenance, make_panel

class FormatAndRecorderTests(unittest.TestCase):
    def test_duplicate_json_keys_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "duplicate.json"
            path.write_text('{"schema": 1, "schema": 2}\n', encoding="utf-8")
            with self.assertRaisesRegex(ledger.EvidenceError, "duplicate JSON key"):
                ledger.load_json_strict(path)

    def test_nonfinite_json_constant_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nan.json"
            path.write_text('{"value": NaN}\n', encoding="utf-8")
            with self.assertRaisesRegex(ledger.EvidenceError, "non-finite JSON constant"):
                ledger.load_json_strict(path)

    def test_boolean_bank_value_is_rejected(self):
        panel = make_panel()
        game = panel["cells"][0]["candidate"]["primary"]
        game["steps"][1]["bank"][0] = True
        game["terminal_bank"][0] = True
        game["scores"][0] = True
        panel["cells"][0]["candidate"]["replay"] = deepcopy(game)
        with self.assertRaisesRegex(ledger.EvidenceError, "must be an integer"):
            ledger.analyze_panel(panel)

    def test_score_must_equal_final_bank_exactly(self):
        panel = make_panel()
        game = panel["cells"][0]["candidate"]["primary"]
        game["scores"][0] += 1
        panel["cells"][0]["candidate"]["replay"] = deepcopy(game)
        with self.assertRaisesRegex(ledger.EvidenceError, "scores must be byte-exact"):
            ledger.analyze_panel(panel)

    def test_cli_writes_admit_report_and_rejects_negative_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_path = root / "panel.json"
            output_path = root / "report.json"
            input_path.write_text(json.dumps(make_panel()), encoding="utf-8")
            with redirect_stdout(io.StringIO()):
                self.assertEqual(ledger.main(["--input", str(input_path), "--output", str(output_path)]), 0)
            report = ledger.load_json_strict(output_path)
            self.assertEqual(report["verdict"], "ADMIT")
            rejected = make_panel(action_changed=True, own_delta=0, rival_delta=0)
            input_path.write_text(json.dumps(rejected), encoding="utf-8")
            with redirect_stdout(io.StringIO()):
                self.assertEqual(ledger.main(["--input", str(input_path), "--output", str(output_path)]), 1)
            self.assertEqual(ledger.load_json_strict(output_path)["verdict"], "REJECT")

    def test_recorder_builds_a_valid_identity_bound_game(self):
        identity = {
            "opponent": "arlene",
            "seed": 7,
            "candidate_seat": 0,
            "arm": "control",
        }
        provenance = arm_provenance("control", "arlene")
        recorder = ledger.GameRecorder(identity, provenance, expected_actions=2)
        world0 = {"step": 0, "rng": 1}
        world1 = {"step": 1, "rng": 1}
        world2 = {"step": 2, "rng": 1, "money": [12, 10]}
        recorder.append(
            step=0,
            preworld=world0,
            observations=({"seat": 0}, {"seat": 1}),
            actions=({"market": []}, {"market": []}),
            postworld=world1,
            bank=(0, 0),
        )
        recorder.append(
            step=1,
            preworld=world1,
            observations=({"seat": 0}, {"seat": 1}),
            actions=({"market": []}, {"market": []}),
            postworld=world2,
            bank=(12, 10),
        )
        game = recorder.finalize(scores=(12, 10))
        view = ledger.validate_game(
            game,
            expected_actions=2,
            field="game",
            expected_identity=identity,
            expected_provenance=provenance,
        )
        self.assertEqual(view.scores, (12, 10))

    def test_recorder_rejects_discontinuous_worlds(self):
        recorder = ledger.GameRecorder(
            {
                "opponent": "arlene",
                "seed": 7,
                "candidate_seat": 0,
                "arm": "control",
            },
            arm_provenance("control", "arlene"),
            expected_actions=2,
        )
        recorder.append(
            step=0,
            preworld={"step": 0},
            observations=({}, {}),
            actions=({}, {}),
            postworld={"step": 1},
            bank=(0, 0),
        )
        with self.assertRaisesRegex(ledger.EvidenceError, "prior postworld"):
            recorder.append(
                step=1,
                preworld={"step": 999},
                observations=({}, {}),
                actions=({}, {}),
                postworld={"step": 2},
                bank=(1, 1),
            )

    def test_recorder_rejects_string_as_action_pair(self):
        recorder = ledger.GameRecorder(
            {
                "opponent": "arlene",
                "seed": 7,
                "candidate_seat": 0,
                "arm": "control",
            },
            arm_provenance("control", "arlene"),
            expected_actions=1,
        )
        with self.assertRaisesRegex(ledger.EvidenceError, "two-entry sequence"):
            recorder.append(
                step=0,
                preworld={},
                observations=({}, {}),
                actions="ab",
                postworld={},
                bank=(0, 0),
            )

    def test_output_cannot_alias_input_path_or_inode(self):
        panel = make_panel()
        report = ledger.analyze_panel(panel)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "input.json"
            source.write_text(json.dumps(panel), encoding="utf-8")
            with self.assertRaisesRegex(ledger.EvidenceError, "aliases an input path"):
                _atomic_write_json(source, report, forbidden=[source])
            hardlink = root / "hardlink.json"
            hardlink.hardlink_to(source)
            with self.assertRaisesRegex(ledger.EvidenceError, "aliases an input inode"):
                _atomic_write_json(hardlink, report, forbidden=[source])
