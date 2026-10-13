import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO_ROOT = Path(__file__).resolve().parents[2]
for path in (str(ROOT), str(REPO_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

import open_door_guard as guard
import validate_pack as vp


class WorksharePackTests(unittest.TestCase):
    def setUp(self):
        self.pack = vp._load(ROOT / "pack.json")
        self.il = vp._load(ROOT / "overlays" / "IL_DOIT_CDB_27_448DOIT_ADMIN_B_52519.json")
        self.nc = vp._load(ROOT / "overlays" / "NC_DHHS_DHB_30_2025_037_DHB.json")

    def test_tree_validates(self):
        result = vp.validate_tree(ROOT)
        self.assertEqual(result["schema"], vp.PACK_SCHEMA)
        self.assertEqual(len(result["modules"]), 4)
        self.assertEqual(len(result["overlays"]), 2)

    def test_offer_truth_and_scale(self):
        vp.validate_pack(self.pack)
        offers = {o["id"]: o for o in self.pack["offers"]}
        self.assertEqual(offers["PILOT_2_TO_4_WEEK"]["price_usd"], 25000)
        self.assertEqual(offers["IMPLEMENTATION_WORKSHARE"]["price_usd"], 125000)
        self.assertTrue(all(o["status"] == "PROPOSED_NOT_ACCEPTED" for o in offers.values()))

    def test_commercial_claim_tamper_fails(self):
        for key in ("buyer_acceptance_asserted","award_asserted","payment_asserted","recognized_revenue_asserted"):
            candidate = copy.deepcopy(self.pack)
            candidate[key] = True
            with self.assertRaises(vp.ContractError):
                vp.validate_pack(candidate)

    def test_bool_int_alias_fails(self):
        candidate = copy.deepcopy(self.pack)
        candidate["payment_asserted"] = 0
        with self.assertRaises(vp.ContractError):
            vp.validate_pack(candidate)

    def test_offer_status_drift_fails(self):
        candidate = copy.deepcopy(self.pack)
        candidate["offers"][0]["status"] = "ACCEPTED"
        with self.assertRaises(vp.ContractError):
            vp.validate_pack(candidate)

    def test_overlay_prime_or_outbound_drift_fails(self):
        for source in (self.il, self.nc):
            candidate = copy.deepcopy(source)
            candidate["qualification_truth"] = "PRIME_READY"
            with self.assertRaises(vp.ContractError):
                vp.validate_overlay(candidate, self.pack)
            candidate = copy.deepcopy(source)
            candidate["outbound_authorized_by_overlay"] = True
            with self.assertRaises(vp.ContractError):
                vp.validate_overlay(candidate, self.pack)

    def test_unknown_module_fails(self):
        candidate = copy.deepcopy(self.il)
        candidate["workshare_modules"].append("MAGIC_PRIME_AUTHORITY")
        with self.assertRaises(vp.ContractError):
            vp.validate_overlay(candidate, self.pack)

    def test_collision_key_is_canonical_and_route_specific(self):
        a = vp.collision_key("NC-DHHS-DHB-30-2025-037-DHB", "Example Prime", "Teaming@Example.com")
        b = vp.collision_key(" nc-dhhs-dhb-30-2025-037-dhb ", "example prime", "teaming@example.com")
        c = vp.collision_key("NC-DHHS-DHB-30-2025-037-DHB", "Example Prime", "other@example.com")
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)
        self.assertEqual(len(a), 64)

    def test_duplicate_json_key_fails(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "bad.json"
            path.write_text('{"a":1,"a":2}', encoding="utf-8")
            with self.assertRaises(vp.ContractError):
                vp._load(path)

    def test_existing_merged_qualification_refs_are_exact(self):
        refs = vp._load(ROOT / "overlays" / "EXISTING_MERGED_QUALIFICATIONS.json")
        by_id = {row["opportunity_id"]: row for row in refs["refs"]}
        self.assertEqual(by_id["OR-ODA-S-DASOBO-00017788"]["pr"], 13907)
        self.assertEqual(by_id["NYSED-RFP-144-OCUE"]["pr"], 13547)

    def test_package_source_does_not_add_open_door_admission_locks(self):
        chunks = []
        for path in sorted(ROOT.rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            rel = path.relative_to(REPO_ROOT).as_posix()
            if not guard.active_path(rel):
                continue
            lines = path.read_text(encoding="utf-8").splitlines()
            header = [
                f"diff --git a/{rel} b/{rel}",
                "--- /dev/null",
                f"+++ b/{rel}",
                f"@@ -0,0 +1,{len(lines)} @@",
            ]
            chunks.append(
                "\n".join(header + [f"+{line}" for line in lines]) + "\n"
            )
        found = guard.scan_diff("\n".join(chunks))
        self.assertEqual(found, [], found)

if __name__ == "__main__":
    unittest.main()
