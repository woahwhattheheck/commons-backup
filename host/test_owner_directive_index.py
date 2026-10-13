import copy
import json
import tempfile
import unittest
from pathlib import Path

from host import owner_directive_index as odi


BASE = {
    "directives": [
        {
            "op_id": "op-002",
            "owner": "Bryce",
            "owner_mark": True,
            "directive": "Ship reviewed carrier only.",
        },
        {
            "op_id": "op-001",
            "owner": "Bryce",
            "owner_mark": True,
            "directive": "Stop stale runner work.",
        },
    ],
    "broadcasts": [
        {"op_id": "op-001", "surface": "slack:#coord", "permalink": "https://s/1"},
        {"op_id": "op-001", "surface": "slack:#titan"},
        {"op_id": "op-002", "surface": "github:#42", "permalink": "https://g/42"},
    ],
    "heartbeats": [
        {"seat": "ASTRA", "acks": ["op-001", "op-002"]},
        {"seat": "MUSE", "acks": ["op-001"]},
    ],
}


class OwnerDirectiveIndexTests(unittest.TestCase):
    def test_happy_path_is_sorted_and_literal(self):
        out = odi.build_index(copy.deepcopy(BASE))
        self.assertEqual(out["schema"], "commons.owner-directive-index.v1")
        self.assertEqual(out["seats"], ["ASTRA", "MUSE"])
        self.assertEqual([row["op_id"] for row in out["rows"]], ["op-001", "op-002"])
        first = out["rows"][0]
        self.assertIs(first["owner_mark"], True)
        self.assertEqual(
            [x["surface"] for x in first["broadcasts"]],
            ["slack:#coord", "slack:#titan"],
        )
        self.assertEqual(first["acks"], {"ASTRA": True, "MUSE": True})
        self.assertEqual(out["rows"][1]["acks"], {"ASTRA": True, "MUSE": False})

    def test_input_order_does_not_change_output(self):
        left = odi.build_index(copy.deepcopy(BASE))
        right_input = copy.deepcopy(BASE)
        right_input["directives"].reverse()
        right_input["broadcasts"].reverse()
        right_input["heartbeats"].reverse()
        right = odi.build_index(right_input)
        self.assertEqual(left, right)

    def test_owner_mark_must_be_literal_true(self):
        for poison in (False, 1, "true", None):
            payload = copy.deepcopy(BASE)
            payload["directives"][0]["owner_mark"] = poison
            with self.subTest(poison=poison), self.assertRaises(odi.DirectiveIndexError):
                odi.build_index(payload)

    def test_duplicate_directive_rejected_before_indexing(self):
        payload = copy.deepcopy(BASE)
        payload["directives"].append(copy.deepcopy(payload["directives"][0]))
        with self.assertRaisesRegex(odi.DirectiveIndexError, "duplicate directive"):
            odi.build_index(payload)

    def test_duplicate_broadcast_fact_rejected(self):
        payload = copy.deepcopy(BASE)
        payload["broadcasts"].append(
            {"op_id": "op-001", "surface": "slack:#coord", "permalink": "https://other"}
        )
        with self.assertRaisesRegex(odi.DirectiveIndexError, "duplicate broadcast"):
            odi.build_index(payload)

    def test_unknown_broadcast_op_rejected(self):
        payload = copy.deepcopy(BASE)
        payload["broadcasts"].append({"op_id": "missing", "surface": "slack:#coord"})
        with self.assertRaisesRegex(odi.DirectiveIndexError, "unknown op_id"):
            odi.build_index(payload)

    def test_unknown_heartbeat_ack_rejected(self):
        payload = copy.deepcopy(BASE)
        payload["heartbeats"][0]["acks"].append("missing")
        with self.assertRaisesRegex(odi.DirectiveIndexError, "ACK references unknown"):
            odi.build_index(payload)

    def test_duplicate_heartbeat_and_duplicate_ack_rejected(self):
        payload = copy.deepcopy(BASE)
        payload["heartbeats"].append({"seat": "ASTRA", "acks": []})
        with self.assertRaisesRegex(odi.DirectiveIndexError, "duplicate heartbeat seat"):
            odi.build_index(payload)
        payload = copy.deepcopy(BASE)
        payload["heartbeats"][0]["acks"].append("op-001")
        with self.assertRaisesRegex(odi.DirectiveIndexError, "duplicate heartbeat ACK"):
            odi.build_index(payload)

    def test_exact_string_contract_rejects_coercions_and_whitespace(self):
        for poison in (1, True, " op-002", "op-002 ", ""):
            payload = copy.deepcopy(BASE)
            payload["directives"][0]["op_id"] = poison
            with self.subTest(poison=poison), self.assertRaises(odi.DirectiveIndexError):
                odi.build_index(payload)

    def test_cli_writes_stable_compact_json(self):
        with tempfile.TemporaryDirectory() as td:
            inp = Path(td) / "in.json"
            out = Path(td) / "out.json"
            inp.write_text(json.dumps(BASE), encoding="utf-8")
            self.assertEqual(odi.main([str(inp), "--output", str(out)]), 0)
            parsed = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(parsed, odi.build_index(BASE))
            self.assertTrue(out.read_text(encoding="utf-8").endswith("\n"))


if __name__ == "__main__":
    unittest.main()
