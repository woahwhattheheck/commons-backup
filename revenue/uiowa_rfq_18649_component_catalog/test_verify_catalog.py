import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import verify_catalog


def blob_sha(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\\0".encode("ascii") + data).hexdigest()


class CatalogVerifierTests(unittest.TestCase):
    def mini(self, root: Path):
        src = root / "tool.py"
        src.write_text('print("READY")\n', encoding="utf-8")
        sample = root / "sample.csv"
        sample.write_text("id,value\nA,1\n", encoding="utf-8")
        return {
            "schema": "uiowa.component-entry-catalog.v1",
            "snapshot": {"revision": "a" * 40},
            "entries": [{
                "id": "tool",
                "title": "Tool",
                "status": "working",
                "kind": "cli",
                "source": {"path": "tool.py", "blob_sha": blob_sha(src.read_bytes())},
                "readme": None,
                "command_cwd": ".",
                "command": "python tool.py",
                "supported_input": "fixture",
                "produced_output": "result",
                "prerequisites": ["Python 3"],
                "contract_markers": ["READY"],
                "sample_result": {
                    "basis": "provider_readback",
                    "summary": "one row",
                    "evidence_path": "sample.csv",
                    "evidence_blob_sha": blob_sha(sample.read_bytes()),
                    "expected_data_rows": 1
                }
            }]
        }

    def test_clean_mini_catalog_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = verify_catalog.verify(self.mini(root), root)
            self.assertEqual(report["status"], "PASS")
            self.assertEqual(report["entry_count"], 1)

    def test_blob_drift_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            catalog = self.mini(root)
            (root / "tool.py").write_text('print("CHANGED")\n', encoding="utf-8")
            report = verify_catalog.verify(catalog, root)
            self.assertEqual(report["status"], "FAIL")
            self.assertTrue(any("blob drift" in e for e in report["errors"]))

    def test_missing_contract_marker_is_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            catalog = self.mini(root)
            catalog["entries"][0]["contract_markers"] = ["NOT_THERE"]
            report = verify_catalog.verify(catalog, root)
            self.assertTrue(any("contract marker" in e for e in report["errors"]))

    def test_incomplete_entry_must_stay_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            readme = root / "README.md"
            readme.write_text("pending\n", encoding="utf-8")
            catalog = {
                "schema": "uiowa.component-entry-catalog.v1",
                "snapshot": {"revision": "b" * 40},
                "entries": [{
                    "id": "pending",
                    "title": "Pending",
                    "status": "incomplete",
                    "kind": "advertised_cli_missing",
                    "source": {"path": "README.md", "blob_sha": blob_sha(readme.read_bytes())},
                    "readme": None,
                    "command_cwd": ".",
                    "command": "python missing.py",
                    "expected_entrypoint": "missing.py",
                    "missing_reason": "not published",
                    "supported_input": "unknown",
                    "produced_output": "not runnable",
                    "prerequisites": ["implementation"],
                    "contract_markers": [],
                    "sample_result": {
                        "basis": "snapshot_gap",
                        "summary": "missing",
                        "evidence_path": "README.md",
                        "evidence_blob_sha": blob_sha(readme.read_bytes())
                    }
                }]
            }
            self.assertEqual(verify_catalog.verify(catalog, root)["status"], "PASS")
            (root / "missing.py").write_text("# landed\n", encoding="utf-8")
            report = verify_catalog.verify(catalog, root)
            self.assertEqual(report["status"], "FAIL")
            self.assertTrue(any("now exists" in e for e in report["errors"]))


if __name__ == "__main__":
    unittest.main()
