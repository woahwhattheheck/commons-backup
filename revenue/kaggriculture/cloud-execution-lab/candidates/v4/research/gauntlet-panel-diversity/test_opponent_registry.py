from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import opponent_registry as reg


def write(path: Path, data: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data, encoding="utf-8")
    return path


def jwrite(path: Path, value) -> Path:
    return write(path, json.dumps(value, indent=2, sort_keys=True) + "\n")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.base = Path(self.td.name)
        self.kg = self.base / "revenue/kaggriculture"
        self.v4 = self.kg / "cloud-execution-lab/candidates/v4"
        self.research = self.v4 / "research"
        self._seed_fixture()

    def tearDown(self):
        self.td.cleanup()

    def _seed_fixture(self):
        # Static reference sources: two available, one intentionally missing by custody.
        apex = write(self.kg / "vendor/apex/main.py", "def agent(obs): return {}\n")
        arlene = write(self.kg / "vendor/arlene.py", "def agent(obs): return {\"farmer\": [\"PASS\"]}\n")
        ref = {
            "schema": reg.REF_REGISTRY_SCHEMA,
            "policies": {
                "apex_v7": {"root": "vendor/apex", "entry": "main.py", "license": "Apache-2.0",
                            "files": {"main.py": sha(apex)}},
                "arlene_v14": {"root": "vendor", "entry": "arlene.py", "license": "Apache-2.0",
                               "files": {"arlene.py": sha(arlene)}},
                "kaito_v43": {"root": "vendor", "entry": "kaito.py", "license": "Apache-2.0",
                              "files": {"kaito.py": "0" * 64},
                              "custody_at_receipt": "not_recovered_here; preparation fails"},
            },
        }
        jwrite(self.research / "reference-policy-bank/REFERENCE-POLICIES.json", ref)

        # REFORGE validation and generator authority.
        reforge_validation = {
            "materialization": {
                "entries": ["cok-v10", "lonespear-v18-greedy", "lonespear-v18-scipy"],
                "families": {"cok-v10": ["cok-v10"],
                             "lonespear-v18": ["lonespear-v18-greedy", "lonespear-v18-scipy"]},
                "reforge_manifest_sha256": "f" * 64,
            }
        }
        jwrite(self.research / "reference-policy-bank/REFORGE-RECOVERY-VALIDATION.json", reforge_validation)
        write(self.research / "reference-policy-bank/prepare_public_bank.py", "# generator authority\n")

        # ORCHARD synthetic family.
        challenger = write(self.research / "opponent-challengers/reactive_challengers.py",
                           "def agent(obs): return {}\ndef dairy(obs): return {}\ndef fiber(obs): return {}\n")
        orchard = {
            "schema": reg.ORCHARD_SCHEMA,
            "classification": "independent_synthetic_soft",
            "family": "independent_reactive_job_scheduler",
            "module": "reactive_challengers.py",
            "module_sha256": sha(challenger),
            "profiles": {"dairy": "dairy", "fiber": "fiber", "orchard": "agent"},
        }
        jwrite(self.research / "opponent-challengers/OPPONENTS.json", orchard)

        write(self.research / "market-pressure/market_pressure.py", "def agent(obs): return {\"market\": [[\"BUY_PRODUCT\", \"WHEAT\", 1]]}\n")
        write(self.research / "gauntlet-panel-diversity/panel_diversity.py", "# spectrum authority\n")
        self.pins = {
            "reference_manifest": reg.git_blob_file(self.research / "reference-policy-bank/REFERENCE-POLICIES.json"),
            "reforge_validation": reg.git_blob_file(self.research / "reference-policy-bank/REFORGE-RECOVERY-VALIDATION.json"),
            "reforge_generator": reg.git_blob_file(self.research / "reference-policy-bank/prepare_public_bank.py"),
            "orchard_manifest": reg.git_blob_file(self.research / "opponent-challengers/OPPONENTS.json"),
            "market_pressure": reg.git_blob_file(self.research / "market-pressure/market_pressure.py"),
            "spectrum_validator": reg.git_blob_file(self.research / "gauntlet-panel-diversity/panel_diversity.py"),
        }

    def build(self, **kwargs):
        return reg.build_registry(self.v4, pins=self.pins, validate_panel=self._validate_panel, **kwargs)

    def _validate_panel(self, panel):
        self.assertEqual(panel["schema"], reg.PANEL_SCHEMA)
        self.assertEqual(panel["expected_labels"], len(panel["opponents"]))
        allowed = {"id", "kind", "family", "source_id", "status", "note", "rank"}
        ids = set()
        source_claims = {}
        for row in panel["opponents"]:
            self.assertLessEqual(set(row), allowed)
            self.assertNotIn(row["id"], ids)
            ids.add(row["id"])
            if row["status"] == "resolved":
                self.assertNotEqual(row["kind"], "unknown")
                self.assertTrue(row["family"])
                self.assertTrue(row["source_id"])
                prior = source_claims.get(row["source_id"])
                claim = (row["family"], row["kind"])
                if prior is not None:
                    self.assertEqual(prior, claim)
                source_claims[row["source_id"]] = claim
            else:
                self.assertEqual(row["kind"], "unknown")
                self.assertIsNone(row["family"])
                self.assertIsNone(row["source_id"])
        return panel

    def test_builds_resolved_static_and_unresolved_reforge(self):
        registry, panel = self.build()
        by_id = {row["id"]: row for row in registry["entries"]}
        self.assertEqual(by_id["reference-apex-v7"]["status"], "resolved")
        self.assertEqual(by_id["reference-kaito-v43"]["status"], "unresolved")
        self.assertEqual(by_id["reforge-cok-v10"]["status"], "unresolved")
        self.assertGreater(registry["resolved_labels"], 0)
        self.assertEqual(len(panel["opponents"]), registry["resolved_labels"] + registry["unresolved_labels"])

    def test_orchard_profiles_share_one_family_and_source(self):
        registry, _ = self.build()
        rows = [r for r in registry["entries"] if r["source"] == "opponent-challengers"]
        self.assertEqual(len(rows), 3)
        self.assertEqual(len({r["family"] for r in rows}), 1)
        self.assertEqual(len({r["source_id"] for r in rows}), 1)
        self.assertEqual({r["metadata"]["profile"] for r in rows}, {"dairy", "fiber", "orchard"})

    def test_panel_contains_no_execution_metadata(self):
        registry, panel = self.build()
        rich = next(r for r in registry["entries"] if r["status"] == "resolved")
        self.assertIn("entry_sha256", rich)
        for row in panel["opponents"]:
            self.assertNotIn("entry", row)
            self.assertNotIn("entry_sha256", row)
            self.assertNotIn("metadata", row)

    def test_source_pin_drift_blocks_entire_registry(self):
        write(self.research / "market-pressure/market_pressure.py", "# drift\n")
        with self.assertRaisesRegex(reg.RegistryError, "Git blob drift"):
            self.build()

    def test_declared_present_source_digest_drift_blocks(self):
        ref_path = self.research / "reference-policy-bank/REFERENCE-POLICIES.json"
        raw = json.loads(ref_path.read_text())
        raw["policies"]["apex_v7"]["files"]["main.py"] = "1" * 64
        jwrite(ref_path, raw)
        self.pins["reference_manifest"] = reg.git_blob_file(ref_path)
        with self.assertRaisesRegex(reg.RegistryError, "source digest drift"):
            self.build()

    def test_spectrum_rejection_blocks(self):
        def reject(_panel):
            raise ValueError("bad panel")
        with self.assertRaisesRegex(reg.RegistryError, "SPECTRUM rejected"):
            reg.build_registry(self.v4, pins=self.pins, validate_panel=reject)

    def test_materialized_reforge_preserves_one_lonespear_family(self):
        bank = self.base / "materialized/bank"
        bank.mkdir(parents=True)
        files = {}
        entries = {}
        families = {"cok-v10": "cok-v10",
                    "lonespear-v18-greedy": "lonespear-v18",
                    "lonespear-v18-scipy": "lonespear-v18"}
        for identity, family in families.items():
            path = write(bank / f"{identity}.py", f"# {identity}\n")
            files[f"{identity}.py"] = sha(path)
            entries[identity] = {"family": family, "entry": f"bank/{identity}.py"}
        manifest = {"schema": reg.REFORGE_SCHEMA, "files": files, "entries": entries}
        manifest_path = jwrite(bank / "REFORGE-BANK.json", manifest)
        frozen = sha(manifest_path)
        val_path = self.research / "reference-policy-bank/REFORGE-RECOVERY-VALIDATION.json"
        val = json.loads(val_path.read_text())
        val["materialization"]["reforge_manifest_sha256"] = frozen
        jwrite(val_path, val)
        self.pins["reforge_validation"] = reg.git_blob_file(val_path)

        registry, _ = self.build(reforge_bank_root=bank, reforge_manifest_sha256=frozen)
        rows = {r["id"]: r for r in registry["entries"] if r["source"] == "reference-policy-bank/reforge"}
        self.assertTrue(all(r["status"] == "resolved" for r in rows.values()))
        self.assertEqual(rows["reforge-lonespear-v18-greedy"]["family"],
                         rows["reforge-lonespear-v18-scipy"]["family"])
        self.assertNotEqual(rows["reforge-lonespear-v18-greedy"]["source_id"],
                            rows["reforge-lonespear-v18-scipy"]["source_id"])

    def test_reforge_requires_exact_published_frozen_manifest(self):
        bank = self.base / "bank"
        bank.mkdir()
        with self.assertRaisesRegex(reg.RegistryError, "published validated"):
            self.build(reforge_bank_root=bank, reforge_manifest_sha256="0" * 64)


if __name__ == "__main__":
    unittest.main()
