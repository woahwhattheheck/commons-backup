import unittest

from api.cua_s1 import handle_request
from host.cua_s1_cloud.runtime_onnx import collate, score


class HostedOnnxTests(unittest.TestCase):
    def test_collator_byte_contract(self):
        batch = collate("é", ["fill x", "skip"])
        self.assertEqual(batch["context_ids"][0, :2].tolist(), [196, 170])
        self.assertEqual(batch["option_mask"][0].tolist(), [True, True] + [False] * 30)
        self.assertEqual(batch["option_ids"].shape, (1, 32, 96))

    def test_scoring_and_http(self):
        payload = {"context": "ELEMENT Edit Phone", "options": ["fill 555-0142", "skip"]}
        result = score(payload)
        self.assertEqual(len(result["choices"]), 2)
        self.assertAlmostEqual(sum(x["probability"] for x in result["choices"]), 1.0, places=6)
        self.assertFalse(result["executed"])
        import json
        status, served = handle_request("POST", "/cua-s1", json.dumps(payload).encode())
        self.assertEqual(status, 200)
        self.assertEqual(served["selected_index"], result["selected_index"])
        self.assertEqual(handle_request("POST", "/cua-s1", b"{")[0], 400)


if __name__ == "__main__":
    unittest.main()
