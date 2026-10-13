from __future__ import annotations
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("trace_replay", HERE / "trace_replay.py")
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def transition(step, candidate_money, rival_money, candidate_action=None, rival_action=None):
    observation = {
        "step": step,
        "day": step // 24,
        "hour": step % 24,
        "farms": [{"money": candidate_money}, {"money": rival_money}],
    }
    return {
        "game_step": step,
        "after": [observation, observation],
        "applied_actions": [
            candidate_action or {"farmer": ["PASS"], "hands": [], "market": []},
            rival_action or {"farmer": ["PASS"], "hands": [], "market": []},
        ],
    }


class InterventionTests(unittest.TestCase):
    def test_drop_one_market_order_preserves_everything_else(self):
        action = {"farmer": ["NORTH"], "hands": [["PICKUP", "WHEAT"]],
                  "market": [["HIRE"], ["BUY_SEED", "WHEAT", 3], ["SELL", "MILK", 1]]}
        result = module.apply_intervention(action, {"mode": "drop_market_order", "order_index": 1})
        self.assertEqual(result["market"], [["HIRE"], ["SELL", "MILK", 1]])
        self.assertEqual(result["farmer"], ["NORTH"])
        self.assertEqual(len(action["market"]), 3)

    def test_full_pass_preserves_hand_cardinality(self):
        action = {"farmer": ["NORTH"], "hands": [["WEST"], ["CARE"]], "market": [["HIRE"]]}
        result = module.apply_intervention(action, {"mode": "full_pass"})
        self.assertEqual(result, {"farmer": ["PASS"], "hands": [["PASS"], ["PASS"]], "market": []})

    def test_invalid_drop_is_rejected(self):
        with self.assertRaises(ValueError):
            module.apply_intervention({"market": []}, {"mode": "drop_market_order", "order_index": 2})


class AnalysisTests(unittest.TestCase):
    def test_permanent_deficit_and_largest_widening(self):
        rows = [
            transition(0, 100, 100),
            transition(1, 90, 100, {"farmer": ["PASS"], "hands": [], "market": [["HIRE"]]}),
            transition(2, 130, 100),
            transition(3, 80, 100, {"farmer": ["PASS"], "hands": [], "market": [["BUY_SEED", "WHEAT", 4]]}),
            transition(4, 75, 110),
        ]
        analysis = module.analyze_transitions(rows, 0)
        self.assertEqual(analysis["permanent_deficit_onset"]["game_step"], 3)
        self.assertEqual(analysis["largest_one_step_deficit_expansions"][0]["game_step"], 3)
        self.assertEqual(analysis["terminal_money_margin"], -35)

    def test_intervention_selection_is_bounded_and_order_specific(self):
        rows = [
            transition(0, 100, 100),
            transition(1, 10, 100, {"farmer": ["PASS"], "hands": [],
                                    "market": [["HIRE"], ["BUY_SEED", "WHEAT", 5]]}),
        ]
        selected = module.intervention_candidates(module.analyze_transitions(rows, 0), 2)
        self.assertEqual([item["mode"] for item in selected], ["drop_market_order", "drop_market_order"])
        self.assertEqual([item["order_index"] for item in selected], [0, 1])

    def test_intervention_selection_deduplicates_identical_resulting_actions(self):
        rows = [
            transition(0, 100, 100),
            transition(1, 10, 100, {"farmer": ["PASS"], "hands": [],
                                    "market": [["HIRE"], ["HIRE"], ["HIRE"],
                                               ["BUY_LAND"], ["BUY_ANIMAL", "SHEEP", 1]]}),
        ]
        selected = module.intervention_candidates(module.analyze_transitions(rows, 0), 4)
        self.assertEqual([item["mode"] for item in selected],
                         ["drop_market_order", "drop_market_order",
                          "drop_market_order", "market_pass"])
        self.assertEqual([item.get("order_index") for item in selected], [0, 3, 4, None])
        resulting = [
            module.apply_intervention(rows[1]["applied_actions"][0], item)
            for item in selected
        ]
        self.assertEqual(len({json.dumps(item, sort_keys=True) for item in resulting}), 4)

    def test_intervention_candidates_zero_limit_returns_empty(self):
        rows = [
            transition(0, 100, 100),
            transition(1, 10, 100, {"farmer": ["PASS"], "hands": [],
                                    "market": [["HIRE"], ["BUY_SEED", "WHEAT", 5]]}),
        ]
        selected = module.intervention_candidates(module.analyze_transitions(rows, 0), 0)
        self.assertEqual(selected, [])
        selected_neg = module.intervention_candidates(module.analyze_transitions(rows, 0), -1)
        self.assertEqual(selected_neg, [])


class ArchiveTests(unittest.TestCase):
    SOURCE = b'{"schema":"source"}\n'

    def _pin(self, archive, files, source=SOURCE):
        return {"release": {"sha256": module.sha256_file(archive), "bytes": archive.stat().st_size,
                            "runtime_files": files, "entrypoint": "main.py::agent",
                            "config": "TITAN-CONFIG.json",
                            "source_manifest_sha256": hashlib.sha256(source).hexdigest()}}

    def _archive(self, path, source=SOURCE):
        with tarfile.open(path, "w:gz") as tar:
            for name, data in (("main.py", b"def agent(o,c=None): return {}\n"),
                               ("TITAN-CONFIG.json", b"{}\n"),
                               ("SOURCE.json", source)):
                info = tarfile.TarInfo(name)
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))

    def test_verified_archive_extracts_and_separates_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            archive = root / "candidate.tar.gz"
            self._archive(archive)
            pin = root / "PIN.json"
            pin.write_text(json.dumps(self._pin(archive, 2)))
            receipt = module.verify_and_extract(archive, pin, root / "out")
            self.assertEqual(receipt["extraction"]["regular_files"], 3)
            self.assertEqual(receipt["extraction"]["runtime_files"], 2)
            self.assertEqual(receipt["extraction"]["source_manifest"]["sha256"],
                             hashlib.sha256(self.SOURCE).hexdigest())

    def test_missing_embedded_source_manifest_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            archive = root / "candidate.tar.gz"
            with tarfile.open(archive, "w:gz") as tar:
                for name, data in (("main.py", b"x"), ("TITAN-CONFIG.json", b"{}")):
                    info = tarfile.TarInfo(name)
                    info.size = len(data)
                    tar.addfile(info, io.BytesIO(data))
            pin = root / "PIN.json"
            pin.write_text(json.dumps(self._pin(archive, 2)))
            with self.assertRaisesRegex(ValueError, "exactly one root SOURCE.json"):
                module.verify_and_extract(archive, pin, root / "out")

    def test_embedded_source_manifest_hash_is_verified(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            archive = root / "candidate.tar.gz"
            self._archive(archive, b'{"different":true}\n')
            pin = root / "PIN.json"
            pin.write_text(json.dumps(self._pin(archive, 2, self.SOURCE)))
            with self.assertRaisesRegex(ValueError, "embedded source manifest mismatch"):
                module.verify_and_extract(archive, pin, root / "out")

    def test_parent_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            archive = root / "candidate.tar.gz"
            with tarfile.open(archive, "w:gz") as tar:
                info = tarfile.TarInfo("../escape")
                info.size = 1
                tar.addfile(info, io.BytesIO(b"x"))
            pin = root / "PIN.json"
            pin.write_text(json.dumps(self._pin(archive, 1)))
            with self.assertRaises(ValueError):
                module.verify_and_extract(archive, pin, root / "out")


class LivePinTests(unittest.TestCase):
    REPO = HERE.parents[2]
    PIN_PATH = HERE / "PIN.json"
    CANON_ARCHIVE = (
        REPO / "revenue/kaggriculture/cloud-execution-lab/runtime/integrated-selected/CURRENT-ARCHIVE.json"
    )

    def test_pin_matches_living_current_source_and_archive(self):
        pin = json.loads(self.PIN_PATH.read_text(encoding="utf-8"))
        release = pin["release"]
        source = self.REPO / release["source_manifest"]
        archive = self.REPO / release["path"]
        source_digest = hashlib.sha256(source.read_bytes()).hexdigest()
        archive_digest = module.sha256_file(archive)
        self.assertEqual(source_digest, release["source_manifest_sha256"])
        self.assertEqual(archive_digest, release["sha256"])
        self.assertEqual(archive.stat().st_size, release["bytes"])
        canon = json.loads(self.CANON_ARCHIVE.read_text(encoding="utf-8"))
        self.assertEqual(canon["sha256"], release["sha256"])
        self.assertEqual(canon["bytes"], release["bytes"])
        self.assertEqual(canon["runtime_files"], release["runtime_files"])
        self.assertEqual(canon["source_manifest_sha256"], release["source_manifest_sha256"])

    def test_stale_source_manifest_hash_is_rejected_before_extract(self):
        pin = json.loads(self.PIN_PATH.read_text(encoding="utf-8"))
        release = pin["release"]
        source = self.REPO / release["source_manifest"]
        actual = hashlib.sha256(source.read_bytes()).hexdigest()
        stale = "9abd5b96091816428780172c6b0b8f69cfebddcd61de65a3a438f26435da674f"
        self.assertNotEqual(actual, stale)
        self.assertEqual(actual, release["source_manifest_sha256"])

    def test_living_release_extracts_under_the_reminted_pin(self):
        pin = json.loads(self.PIN_PATH.read_text(encoding="utf-8"))
        release = pin["release"]
        with tempfile.TemporaryDirectory() as td:
            receipt = module.verify_and_extract(
                self.REPO / release["path"],
                self.PIN_PATH,
                Path(td) / "out",
            )
            self.assertEqual(receipt["extraction"]["runtime_files"], release["runtime_files"])
            self.assertEqual(
                receipt["extraction"]["source_manifest"]["sha256"],
                release["source_manifest_sha256"],
            )


if __name__ == "__main__":
    unittest.main()
