import unittest

from controller import verify_receipt
from data_contract import abstention_receipt, assign_group_folds, series_manifest_from_csv


class DataContractTests(unittest.TestCase):
    def test_manifest_ingestion_groups_and_sorts(self):
        data = (
            b"StudyInstanceUID,SeriesInstanceUID,Fluid_Sensitive,Fat_Suppression,Anatomical_Plane\n"
            b"A,z,1,0,Sagittal\n"
            b"A,a,0,1,Axial\n"
            b"B,b,1,1,Coronal\n"
        )
        out = series_manifest_from_csv(data, {"z": 30, "a": 40, "b": 50})
        self.assertEqual(tuple(out), ("A", "B"))
        self.assertEqual(tuple(x.series_id for x in out["A"]), ("a", "z"))

    def test_manifest_rejects_stale_slice_count(self):
        data = b"StudyInstanceUID,SeriesInstanceUID,Fluid_Sensitive,Fat_Suppression,Anatomical_Plane\nA,a,1,0,Sagittal\n"
        with self.assertRaises(ValueError):
            series_manifest_from_csv(data, {"a": 40, "ghost": 3})

    def test_group_folds_keep_same_group_together(self):
        rows = (("S1", "P1"), ("S2", "P1"), ("S3", "P2"))
        folds = assign_group_folds(rows, 5, salt="rsna-v1")
        self.assertEqual(folds["S1"], folds["S2"])
        self.assertEqual(folds, assign_group_folds(rows, 5, salt="rsna-v1"))

    def test_group_folds_reject_duplicate_study(self):
        with self.assertRaises(ValueError):
            assign_group_folds((("S1", "P1"), ("S1", "P2")), 5, salt="rsna-v1")

    def test_abstention_receipt_is_verifiable(self):
        value = abstention_receipt("S1", "RESOURCE_BUDGET", selected_series=("a", "b"))
        verify_receipt(value)
        self.assertEqual(value["payload"]["reason_code"], "RESOURCE_BUDGET")
        with self.assertRaises(ValueError):
            abstention_receipt("S1", "OTHER")


if __name__ == "__main__":
    unittest.main()
