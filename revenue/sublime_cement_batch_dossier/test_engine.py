from __future__ import annotations

import copy
import hashlib
import json
import random
import tempfile
import unittest
from pathlib import Path

from revenue.sublime_cement_batch_dossier.engine import (
    AUTHORITY,
    EvidenceError,
    FAULT_CLASSES,
    PACKET_VERSION,
    assemble,
    loads_strict,
    main,
    verify_result,
)


def sha(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def section(source: str, status: str, **fields: str) -> dict[str, str]:
    return {
        "source_id": source,
        "source_sha256": sha(source + "-raw"),
        "source_status": status,
        **fields,
    }


def batch(i: int) -> dict:
    bid = f"B{i:03d}"
    return {
        "batch_id": bid,
        "feedstock": section(f"{bid}-feed", "AVAILABLE", lot_id=f"F{i:03d}", mineral_assay_sha256=sha(f"{bid}-assay")),
        "recipe": section(f"{bid}-recipe", "AVAILABLE", revision_id=f"R{i%7}", recipe_sha256=sha(f"{bid}-recipe")),
        "reagent": section(f"{bid}-reagent", "AVAILABLE", lot_id=f"G{i:03d}", coa_sha256=sha(f"{bid}-reagent-coa")),
        "equipment": section(f"{bid}-equip", "AVAILABLE", equipment_id=f"E{i%5}", calibration_id=f"C{i:03d}", calibration_record_sha256=sha(f"{bid}-cal")),
        "in_process": section(f"{bid}-chem", "AVAILABLE", chemistry_record_id=f"IP{i:03d}", chemistry_record_sha256=sha(f"{bid}-chem")),
        "physical_tests": section(
            f"{bid}-physical", "AVAILABLE",
            fineness_record_id=f"FN{i:03d}", strength_record_id=f"ST{i:03d}",
            fineness_record_sha256=sha(f"{bid}-fine"), strength_record_sha256=sha(f"{bid}-strength"),
        ),
        "astm_evidence": section(
            f"{bid}-astm", "AVAILABLE",
            evidence_id=f"A{i:03d}", standard="ASTM C1157", evidence_sha256=sha(f"{bid}-astm"),
        ),
        "delivery": section(
            f"{bid}-delivery", "AVAILABLE",
            coa_id=f"COA{i:03d}", delivery_lot_id=f"D{i:03d}",
            coa_sha256=sha(f"{bid}-coa"), mapping_evidence_sha256=sha(f"{bid}-mapping"),
        ),
    }


def golden_packet() -> dict:
    rows = [batch(i) for i in range(96)]
    sections = [
        "feedstock", "recipe", "reagent", "equipment",
        "in_process", "physical_tests", "astm_evidence", "delivery",
    ]
    for class_index, section_name in enumerate(sections):
        for offset in range(3):
            rows[class_index * 3 + offset][section_name]["source_status"] = "HOLD"
    return {"schema_version": PACKET_VERSION, "batches": rows}


class DossierTests(unittest.TestCase):
    def test_golden_96_contract(self) -> None:
        result = assemble(golden_packet())
        self.assertEqual(result["batch_count"], 96)
        self.assertEqual(result["dossier_count"], 72)
        self.assertEqual(result["exception_count"], 24)
        self.assertEqual(len(result["dossiers"]), 72)
        self.assertEqual(len(result["exceptions"]), 24)
        counts = {name: 0 for name in FAULT_CLASSES}
        for row in result["exceptions"]:
            counts[row["fault_class"]] += 1
            self.assertEqual(row["state"], "HOLD")
        self.assertEqual(counts, {name: 3 for name in FAULT_CLASSES})
        self.assertTrue(all(row["state"] == "DOSSIER_COMPLETE" for row in result["dossiers"]))
        self.assertEqual(result["authority"], AUTHORITY)
        self.assertTrue(all(value is False for value in result["authority"].values()))
        self.assertTrue(verify_result(golden_packet(), result))

    def test_order_independent_decisions_but_packet_digest_binds_order(self) -> None:
        packet = golden_packet()
        shuffled = copy.deepcopy(packet)
        random.Random(7).shuffle(shuffled["batches"])
        a = assemble(packet)
        b = assemble(shuffled)
        self.assertEqual(a["decisions_sha256"], b["decisions_sha256"])
        self.assertNotEqual(a["source_packet_sha256"], b["source_packet_sha256"])
        self.assertEqual(a["dossiers"], b["dossiers"])
        self.assertEqual(a["exceptions"], b["exceptions"])

    def test_multiple_source_holds_emit_multiple_explicit_exceptions(self) -> None:
        packet = {"schema_version": PACKET_VERSION, "batches": [batch(1)]}
        packet["batches"][0]["feedstock"]["source_status"] = "HOLD"
        packet["batches"][0]["delivery"]["source_status"] = "HOLD"
        result = assemble(packet)
        self.assertEqual(result["dossier_count"], 0)
        self.assertEqual(result["exception_count"], 2)
        self.assertEqual(
            {row["fault_class"] for row in result["exceptions"]},
            {"FEEDSTOCK_ASSAY", "COA_DELIVERY_MAPPING"},
        )

    def test_zero_inferred_pass_requires_explicit_available_status(self) -> None:
        packet = {"schema_version": PACKET_VERSION, "batches": [batch(1)]}
        del packet["batches"][0]["recipe"]["source_status"]
        with self.assertRaises(EvidenceError):
            assemble(packet)
        packet = {"schema_version": PACKET_VERSION, "batches": [batch(1)]}
        packet["batches"][0]["recipe"]["source_status"] = True
        with self.assertRaises(EvidenceError):
            assemble(packet)

    def test_astm_label_is_exact_but_no_conformance_authority_exists(self) -> None:
        packet = {"schema_version": PACKET_VERSION, "batches": [batch(1)]}
        packet["batches"][0]["astm_evidence"]["standard"] = "ASTM C150"
        with self.assertRaises(EvidenceError):
            assemble(packet)
        result = assemble({"schema_version": PACKET_VERSION, "batches": [batch(1)]})
        self.assertFalse(result["authority"]["astm_conformance_decision"])

    def test_strict_hash_unknown_field_and_duplicate_batch_id(self) -> None:
        packet = {"schema_version": PACKET_VERSION, "batches": [batch(1)]}
        packet["batches"][0]["feedstock"]["source_sha256"] = "ABC"
        with self.assertRaises(EvidenceError):
            assemble(packet)
        packet = {"schema_version": PACKET_VERSION, "batches": [batch(1)]}
        packet["batches"][0]["recipe"]["extra"] = "nope"
        with self.assertRaises(EvidenceError):
            assemble(packet)
        packet = {"schema_version": PACKET_VERSION, "batches": [batch(1), batch(1)]}
        with self.assertRaises(EvidenceError):
            assemble(packet)

    def test_duplicate_json_key_and_nonfinite_rejected(self) -> None:
        with self.assertRaises(EvidenceError):
            loads_strict('{"schema_version":"x","schema_version":"y","batches":[]}')
        with self.assertRaises(EvidenceError):
            loads_strict('{"x":NaN}')

    def test_result_tamper_fails_verification(self) -> None:
        packet = golden_packet()
        result = assemble(packet)
        tampered = copy.deepcopy(result)
        tampered["dossier_count"] = 73
        self.assertFalse(verify_result(packet, tampered))

    def test_lineage_has_all_eight_exact_sources(self) -> None:
        result = assemble({"schema_version": PACKET_VERSION, "batches": [batch(80)]})
        lineage = result["dossiers"][0]["raw_source_lineage"]
        self.assertEqual(len(lineage), 8)
        self.assertEqual(
            [row["section"] for row in lineage],
            ["feedstock", "recipe", "reagent", "equipment", "in_process", "physical_tests", "astm_evidence", "delivery"],
        )
        self.assertTrue(all(len(row["source_sha256"]) == 64 for row in lineage))

    def test_cli_round_trip_and_invalid_exit(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "packet.json"
            path.write_text(json.dumps({"schema_version": PACKET_VERSION, "batches": [batch(80)]}), encoding="utf-8")
            self.assertEqual(main([str(path)]), 0)
            path.write_text('{"bad":true}', encoding="utf-8")
            self.assertEqual(main([str(path)]), 2)


if __name__ == "__main__":
    unittest.main()
