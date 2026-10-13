from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
DRAFT = "https://json-schema.org/draft/2020-12/schema"
SHA_RE = re.compile(r"^[0-9a-f]{64}$")

TRACE_FIELDS = {
    "schema",
    "variant",
    "policy_sha256",
    "identity",
    "capacity",
    "snapshots",
}
IDENTITY_FIELDS = {
    "engine_sha256",
    "evaluator_sha256",
    "opponent_sha256",
    "start_state_sha256",
    "counterfactual_protocol_sha256",
    "protected_commitments_sha256",
    "seed",
    "controlled_player",
    "horizon_tick",
    "worker_tick_budget",
    "product",
}
SNAPSHOT_FIELDS = {
    "tick",
    "fertilizer_actions",
    "produced_units",
    "harvested_units",
    "deposited_units",
    "sold_units",
    "cash",
    "discarded_units",
    "worker_ticks_used",
    "travel_steps",
    "watering_actions",
    "harvest_actions",
    "deposit_actions",
    "sale_actions",
    "protected_obligation_misses",
    "protected_stock_shortfall_units",
    "carry_units",
    "shed_units",
}
DELTA_FIELDS = SNAPSHOT_FIELDS - {"tick"}
MILESTONE_FIELDS = {
    "fertilizer_tick",
    "production_tick",
    "harvest_tick",
    "deposit_tick",
    "sale_tick",
}


def load(name: str) -> dict:
    return json.loads((HERE / name).read_text(encoding="utf-8"))


class SchemaContractTests(unittest.TestCase):
    def test_every_schema_is_draft_2020_12_and_closed_at_root(self) -> None:
        for name in (
            "trace.schema.json",
            "certificate.schema.json",
            "matrix.schema.json",
            "matrix-result.schema.json",
        ):
            with self.subTest(name=name):
                document = load(name)
                self.assertEqual(document["$schema"], DRAFT)
                self.assertFalse(document["additionalProperties"])
                self.assertTrue(
                    document["$id"].startswith(
                        "https://woahwhattheheck.github.io/commons/"
                    )
                )

    def test_trace_schema_exactly_names_runtime_top_level_fields(self) -> None:
        schema = load("trace.schema.json")
        self.assertEqual(set(schema["required"]), TRACE_FIELDS)
        self.assertEqual(set(schema["properties"]), TRACE_FIELDS)
        self.assertEqual(
            schema["properties"]["schema"]["const"],
            "titan.w10.realized-fertilizer-trace/v1",
        )
        self.assertEqual(
            schema["properties"]["variant"]["enum"], ["control", "fertilized"]
        )

    def test_trace_identity_and_snapshot_fields_are_exact(self) -> None:
        defs = load("trace.schema.json")["$defs"]
        self.assertEqual(set(defs["identity"]["required"]), IDENTITY_FIELDS)
        self.assertEqual(set(defs["identity"]["properties"]), IDENTITY_FIELDS)
        self.assertEqual(set(defs["snapshot"]["required"]), SNAPSHOT_FIELDS)
        self.assertEqual(set(defs["snapshot"]["properties"]), SNAPSHOT_FIELDS)
        self.assertNotIn("minimum", defs["snapshot"]["properties"]["cash"])
        for field in SNAPSHOT_FIELDS - {"cash"}:
            self.assertEqual(defs["snapshot"]["properties"][field]["minimum"], 0)

    def test_trace_array_limits_match_runtime_limits(self) -> None:
        snapshots = load("trace.schema.json")["properties"]["snapshots"]
        self.assertEqual(snapshots["minItems"], 2)
        self.assertEqual(snapshots["maxItems"], 100000)

    def test_certificate_structural_contract_matches_emitted_shapes(self) -> None:
        schema = load("certificate.schema.json")
        self.assertEqual(
            schema["properties"]["schema"]["const"],
            "titan.w10.realized-fertilizer-certificate/v1",
        )
        self.assertEqual(
            schema["properties"]["decision"]["enum"], ["CERTIFIED", "REJECTED"]
        )
        self.assertEqual(set(schema["$defs"]["deltas"]["required"]), DELTA_FIELDS)
        self.assertEqual(
            set(schema["$defs"]["milestones"]["required"]), MILESTONE_FIELDS
        )
        self.assertIn("policy_sha256", schema["allOf"][0]["then"]["required"])
        self.assertIn("terminal", schema["allOf"][0]["then"]["required"])

    def test_matrix_manifest_schema_matches_fail_closed_bounds(self) -> None:
        schema = load("matrix.schema.json")
        self.assertEqual(
            schema["properties"]["schema"]["const"],
            "titan.w10.realized-fertilizer-matrix/v1",
        )
        pairs = schema["properties"]["pairs"]
        self.assertEqual((pairs["minItems"], pairs["maxItems"]), (1, 1000))
        self.assertEqual(
            set(schema["$defs"]["pair"]["required"]),
            {"id", "control", "fertilized"},
        )
        path_pattern = re.compile(
            schema["$defs"]["pair"]["properties"]["control"]["pattern"]
        )
        self.assertIsNotNone(
            path_pattern.fullmatch("traces/seed-718.control.json")
        )
        self.assertIsNone(path_pattern.fullmatch("../escape.json"))
        self.assertIsNone(path_pattern.fullmatch("traces/../escape.json"))

    def test_matrix_result_schema_has_complete_accounting(self) -> None:
        schema = load("matrix-result.schema.json")
        self.assertEqual(
            schema["properties"]["schema"]["const"],
            "titan.w10.realized-fertilizer-matrix-result/v1",
        )
        self.assertEqual(schema["properties"]["decision"]["enum"], ["ADMIT", "REJECT"])
        self.assertEqual(
            set(schema["required"]),
            {
                "schema",
                "decision",
                "reasons",
                "manifest_sha256",
                "pair_count",
                "certified_count",
                "rejected_count",
                "pairs",
                "result_sha256",
            },
        )
        self.assertEqual(
            set(schema["$defs"]["pair_result"]["required"]),
            {
                "id",
                "decision",
                "reasons",
                "control",
                "fertilized",
                "identity_sha256",
                "certificate_sha256",
            },
        )

    def test_all_sha_patterns_reject_uppercase_and_wrong_length(self) -> None:
        for name in ("trace.schema.json", "certificate.schema.json"):
            text = (HERE / name).read_text(encoding="utf-8")
            self.assertIn("^[0-9a-f]{64}$", text)
        self.assertIsNotNone(SHA_RE.fullmatch("a" * 64))
        self.assertIsNone(SHA_RE.fullmatch("A" * 64))
        self.assertIsNone(SHA_RE.fullmatch("a" * 63))


if __name__ == "__main__":
    unittest.main()
