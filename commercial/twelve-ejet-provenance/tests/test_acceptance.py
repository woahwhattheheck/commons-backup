import importlib.util
import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


compiler = load_module("compiler", "compiler.py")
synthetic = load_module("synthetic_acceptance", "synthetic_acceptance.py")


class AcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.batches, cls.plan = synthetic.build_corpus()
        cls.result = compiler.compile_run(cls.batches)

    def test_frozen_corpus_has_exact_shape(self):
        self.assertEqual(100, len(self.batches))
        flattened = [record_id for ids in self.plan.values() for record_id in ids]
        self.assertEqual(24, len(flattened))
        self.assertEqual(24, len(set(flattened)))
        self.assertEqual(set(synthetic.FAULT_CLASSES), set(self.plan))
        self.assertTrue(all(len(ids) == 3 for ids in self.plan.values()))

    def test_exact_76_dossiers_24_batch_reason_exceptions(self):
        summary = self.result["summary"]
        self.assertEqual(76, summary["complete_dossiers"])
        self.assertEqual(24, summary["exceptions"])
        self.assertEqual(24, summary["unique_exception_batches"])
        self.assertFalse(summary["automated_release_performed"])

    def test_exactly_three_exceptions_in_each_of_eight_classes(self):
        counts = Counter(item["input_class"] for item in self.result["exceptions"])
        self.assertEqual({name: 3 for name in synthetic.FAULT_CLASSES}, dict(counts))
        self.assertEqual(8, len(counts))

    def test_every_faulty_record_emits_exactly_one_reason(self):
        counts = Counter(item["batch_ref"] for item in self.result["exceptions"])
        self.assertTrue(all(count == 1 for count in counts.values()))
        self.assertEqual(24, len(counts))

    def test_lineage_values_are_copied_not_invented(self):
        by_id = {batch["batch_id"]: batch for batch in self.batches if batch["batch_id"]}
        for dossier in self.result["dossiers"]:
            source = by_id[dossier["batch_id"]]
            for path, item in dossier["lineage"].items():
                self.assertEqual(path, item["source"])
                self.assertEqual(compiler.resolve_path(source, path), item["value"])

    def test_no_automated_release_or_disposition(self):
        for dossier in self.result["dossiers"]:
            self.assertFalse(dossier["automated_release"])
            self.assertIsNone(dossier["release_decision"])
            self.assertIn("named-human", dossier["boundary"])
        for item in self.result["exceptions"]:
            self.assertFalse(item["automated_release"])
            self.assertIsNone(item["release_decision"])

    def test_output_is_deterministic_and_bundle_is_complete(self):
        repeat = compiler.compile_run(self.batches)
        self.assertEqual(json.dumps(self.result, sort_keys=True), json.dumps(repeat, sort_keys=True))
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            compiler.write_bundle(self.result, out)
            self.assertEqual(76, len(list((out / "dossiers").glob("*.json"))))
            self.assertEqual(24, len((out / "exceptions.jsonl").read_text().splitlines()))
            summary = json.loads((out / "summary.json").read_text())
            self.assertEqual(76, summary["complete_dossiers"])
            self.assertEqual(24, summary["exceptions"])


if __name__ == "__main__":
    unittest.main()
