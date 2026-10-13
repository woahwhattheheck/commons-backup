"""Regression and certificate mutation checks; works with real python -O."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import verify_obstructions as proof

ROOT = Path(__file__).resolve().parent


class ObstructionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.certificate = proof.load_certificate(ROOT / "obstruction_certificate.json")

    def changed(self):
        return copy.deepcopy(self.certificate)

    def test_complete_support(self):
        result = proof.verify(self.changed())
        self.assertEqual(result["certificate_rows"], 26)
        self.assertEqual(result["unique_obstructions"], 24)
        self.assertEqual(result["mod8_coordinate_tuples"], 4096)
        self.assertFalse(result["a308734_proved"])
        self.assertFalse(result["prize_claimed"])

    def test_missing_family(self):
        data = self.changed()
        data["families"].pop()
        self.assertRaises(ValueError, proof.verify, data)

    def test_missing_row(self):
        data = self.changed()
        data["families"][0]["rows"].pop()
        self.assertRaises(ValueError, proof.verify, data)

    def test_extra_row(self):
        data = self.changed()
        data["families"][0]["rows"].append(data["families"][0]["rows"][0])
        self.assertRaises(ValueError, proof.verify, data)

    def test_reordered_rows(self):
        data = self.changed()
        data["families"][0]["rows"].reverse()
        self.assertRaises(ValueError, proof.verify, data)

    def test_every_row_field_mutation(self):
        for family_index, family in enumerate(self.certificate["families"]):
            for row_index in range(len(family["rows"])):
                for field in range(6):
                    with self.subTest(family=family_index, row=row_index, field=field):
                        data = self.changed()
                        data["families"][family_index]["rows"][row_index][field] += 1
                        self.assertRaises(ValueError, proof.verify, data)

    def test_boolean_not_integer(self):
        data = self.changed()
        data["families"][0]["rows"][0][1] = True
        self.assertRaises(ValueError, proof.verify, data)

    def test_wrong_identity(self):
        data = self.changed()
        data["families"][0]["p"] = 7
        self.assertRaises(ValueError, proof.verify, data)

    def test_wrong_original_coordinate(self):
        data = self.changed()
        data["families"][0]["original_witness"][0] += 1
        self.assertRaises(ValueError, proof.verify, data)

    def test_unknown_field(self):
        data = self.changed()
        data["proved"] = True
        self.assertRaises(ValueError, proof.verify, data)

    def test_composite_prime(self):
        data = self.changed()
        data["families"][0]["rows"][0][4] = 15
        self.assertRaises(ValueError, proof.verify, data)

    def test_two_square_controls(self):
        self.assertEqual(proof.two_square_witness(0), (0, 0))
        for n in (1, 2, 4, 5, 25, 65):
            x, y = proof.two_square_witness(n)
            self.assertEqual(x*x + y*y, n)
        for n in (3, 6, 7, 15, 24):
            self.assertIsNone(proof.two_square_witness(n))

    def test_first_lift_must_not_be_assumed(self):
        # 1 has no four-square specialized representation; 4 = 1+1+1+1.
        self.assertEqual(proof.powers(4, 0), [])
        self.assertEqual(proof.powers(4, 4), [1, 4])
        self.assertEqual(1 + 1 + 1 + 1, 4)
        self.assertEqual(proof.two_square_witness(4 - 1 - 1), (1, 1))

    def test_lift_original_witnesses(self):
        for family in self.certificate["families"]:
            x, y, a, b, c, d = family["original_witness"]
            for k in (0, 1, 2, 10, 100):
                self.assertEqual((x*2**k)**2+(y*2**k)**2+4**(a+k)*9**b+4**(c+k)*25**d,
                                 family["seed"]*4**k)

    def test_duplicate_json_key(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text('{"schema":1,"schema":2}', encoding="utf-8")
            self.assertRaises(ValueError, proof.load_certificate, path)

    def test_cli_normal_and_optimized(self):
        for flags in ([], ["-O"]):
            result = subprocess.run([sys.executable, *flags, str(ROOT / "verify_obstructions.py")],
                                    capture_output=True, text=True, cwd="/", check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr, "")
            self.assertEqual(json.loads(result.stdout)["result"], "VERIFIED_FINITE_SUPPORT")

    def test_invalid_cli_nonzero(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text("{}", encoding="utf-8")
            result = subprocess.run([sys.executable, "-O", str(ROOT / "verify_obstructions.py"), str(path)],
                                    capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout, "")
            self.assertIn("INVALID:", result.stderr)


if __name__ == "__main__":
    unittest.main()
