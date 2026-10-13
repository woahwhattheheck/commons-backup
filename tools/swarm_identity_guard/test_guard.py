import copy
import unittest

from tools.swarm_identity_guard.guard import CENSUS_SCHEMA, DECISION_SCHEMA, IdentityGuardError, evaluate, loads_strict, sha256_json

NOW = "2026-09-13T09:10:00Z"


def row(seat="Cobb-Z-Sable-913", lineage="Cobb-Z-Sable", aliases=None):
    return {
        "seat_id": seat,
        "lineage": lineage,
        "aliases": aliases or ["COBBZSABLE-913"],
        "first_seen": "2026-09-13T06:00:00Z",
        "last_seen": "2026-09-13T09:00:00Z",
    }


def census(rows=None):
    return {
        "schema": CENSUS_SCHEMA,
        "complete": True,
        "next_cursor": None,
        "query_id": "identity-census-20260913-01",
        "captured_at": "2026-09-13T09:09:30Z",
        "as_of": "2026-09-13T09:09:00Z",
        "rows": rows if rows is not None else [row()],
    }


def proposal(seat="Z-Meridian-913506-L91", lineage="Z-Meridian", aliases=None):
    return {"seat_id": seat, "lineage": lineage, "aliases": aliases or ["ZMER-913506-L91"]}


class IdentityGuardTests(unittest.TestCase):
    def test_unique_candidate_authorized(self):
        result = evaluate(census(), [proposal()], evaluated_at=NOW)
        self.assertEqual(result["schema"], DECISION_SCHEMA)
        self.assertEqual(result["decision"], "CLAIM_AUTHORIZED")
        self.assertTrue(result["claim_authorized"])
        self.assertFalse(result["source_write_authorized"])
        self.assertEqual(result["selected"]["seat_id"], "Z-Meridian-913506-L91")
        self.assertEqual(result["rejected"], [])

    def test_exact_id_collision_holds(self):
        p = proposal(seat="Cobb-Z-Sable-913", lineage="Z-Meridian")
        result = evaluate(census(), [p], evaluated_at=NOW)
        self.assertEqual(result["decision"], "HOLD")
        self.assertIn("IDENTITY_TOKEN_COLLISION", {r["code"] for r in result["rejected"][0]["reasons"]})

    def test_alias_collision_holds(self):
        p = proposal(aliases=["COBBZSABLE-913"])
        result = evaluate(census(), [p], evaluated_at=NOW)
        self.assertEqual(result["decision"], "HOLD")

    def test_casefold_collision_holds(self):
        p = proposal(seat="cobb-z-sable-913", lineage="Z-Meridian")
        self.assertEqual(evaluate(census(), [p], evaluated_at=NOW)["decision"], "HOLD")

    def test_lineage_collision_holds_even_new_full_id(self):
        p = proposal(seat="Cobb-Z-Sable-999", lineage="Cobb-Z-Sable", aliases=["CZS-999"])
        result = evaluate(census(), [p], evaluated_at=NOW)
        self.assertIn("LINEAGE_COLLISION", {r["code"] for r in result["rejected"][0]["reasons"]})

    def test_candidate_alias_cannot_reuse_existing_lineage(self):
        p = proposal(aliases=["Cobb-Z-Sable"])
        result = evaluate(census(), [p], evaluated_at=NOW)
        self.assertIn("IDENTITY_REUSES_EXISTING_LINEAGE", {r["code"] for r in result["rejected"][0]["reasons"]})

    def test_candidate_lineage_cannot_reuse_existing_alias(self):
        p = proposal(lineage="COBBZSABLE-913", aliases=["ZMER-913506-L91"])
        result = evaluate(census(), [p], evaluated_at=NOW)
        self.assertIn("LINEAGE_REUSES_EXISTING_IDENTITY", {r["code"] for r in result["rejected"][0]["reasons"]})

    def test_first_safe_candidate_selected_deterministically(self):
        bad = proposal(seat="Cobb-Z-Sable-913", lineage="Different-Lineage", aliases=["BAD-913"])
        good = proposal()
        result = evaluate(census(), [bad, good], evaluated_at=NOW)
        self.assertEqual(result["selected"]["index"], 1)
        self.assertEqual(result["selected"]["seat_id"], good["seat_id"])

    def test_all_candidates_collide_holds(self):
        c = census([row(), row("Z-Other-1", "Z-Other", ["OTHER-1"])])
        result = evaluate(c, [proposal(lineage="Cobb-Z-Sable"), proposal("Z-Other-2", "Z-Other", ["OTHER-2"])], evaluated_at=NOW)
        self.assertEqual(result["decision"], "HOLD")
        self.assertFalse(result["claim_authorized"])

    def test_incomplete_census_rejected(self):
        c = census(); c["complete"] = False
        with self.assertRaisesRegex(IdentityGuardError, "complete"):
            evaluate(c, [proposal()], evaluated_at=NOW)

    def test_paginated_census_rejected(self):
        c = census(); c["next_cursor"] = "more"
        with self.assertRaisesRegex(IdentityGuardError, "pagination"):
            evaluate(c, [proposal()], evaluated_at=NOW)

    def test_stale_census_rejected(self):
        c = census(); c["as_of"] = "2026-09-13T08:00:00Z"; c["captured_at"] = "2026-09-13T08:01:00Z"
        with self.assertRaisesRegex(IdentityGuardError, "stale"):
            evaluate(c, [proposal()], evaluated_at=NOW, max_age_seconds=900)

    def test_future_census_rejected(self):
        c = census(); c["captured_at"] = "2026-09-13T09:11:00Z"; c["as_of"] = "2026-09-13T09:10:45Z"; c["rows"] = []
        with self.assertRaisesRegex(IdentityGuardError, "future"):
            evaluate(c, [proposal()], evaluated_at=NOW, max_future_skew_seconds=30)

    def test_conflicting_duplicate_rows_fail_closed(self):
        a = row(); b = copy.deepcopy(a); b["last_seen"] = "2026-09-13T08:59:00Z"
        with self.assertRaisesRegex(IdentityGuardError, "conflicting census rows"):
            evaluate(census([a, b]), [proposal()], evaluated_at=NOW)

    def test_exact_duplicate_rows_collapse_and_count(self):
        a = row()
        result = evaluate(census([a, copy.deepcopy(a)]), [proposal()], evaluated_at=NOW)
        self.assertEqual(result["census"]["row_count"], 1)
        self.assertEqual(result["census"]["exact_duplicate_rows"], 1)

    def test_non_ascii_confusable_rejected(self):
        p = proposal(seat="Z-Meridian-913506-Ł91")
        with self.assertRaisesRegex(IdentityGuardError, "unsafe identity token"):
            evaluate(census(), [p], evaluated_at=NOW)

    def test_nfkc_variant_rejected(self):
        p = proposal(seat="Z-Meridian-913506-Ｌ91")
        with self.assertRaisesRegex(IdentityGuardError, "NFKC"):
            evaluate(census(), [p], evaluated_at=NOW)

    def test_lineage_cannot_be_an_alias(self):
        p = proposal(aliases=["Z-Meridian"])
        result = evaluate(census(), [p], evaluated_at=NOW)
        self.assertEqual(result["decision"], "HOLD")
        self.assertIn("LINEAGE_REUSED_AS_IDENTITY_TOKEN", {r["code"] for r in result["rejected"][0]["reasons"]})

    def test_row_after_as_of_rejected(self):
        r = row(); r["last_seen"] = "2026-09-13T09:09:30Z"
        with self.assertRaisesRegex(IdentityGuardError, "after census as_of"):
            evaluate(census([r]), [proposal()], evaluated_at=NOW)

    def test_duplicate_proposal_id_rejected(self):
        with self.assertRaisesRegex(IdentityGuardError, "duplicate proposal"):
            evaluate(census(), [proposal(), proposal()], evaluated_at=NOW)

    def test_unknown_keys_fail_closed(self):
        c = census(); c["mystery"] = True
        with self.assertRaisesRegex(IdentityGuardError, "unexpected keys"):
            evaluate(c, [proposal()], evaluated_at=NOW)

    def test_bool_policy_not_int(self):
        with self.assertRaisesRegex(IdentityGuardError, "positive int"):
            evaluate(census(), [proposal()], evaluated_at=NOW, max_age_seconds=True)

    def test_duplicate_json_keys_rejected(self):
        with self.assertRaisesRegex(IdentityGuardError, "duplicate JSON key"):
            loads_strict('{"a":1,"a":2}')

    def test_nonfinite_json_rejected(self):
        with self.assertRaisesRegex(IdentityGuardError, "non-finite"):
            loads_strict('{"x":NaN}')

    def test_receipt_stable_for_same_input(self):
        c, p = census(), [proposal()]
        a = evaluate(copy.deepcopy(c), copy.deepcopy(p), evaluated_at=NOW)
        b = evaluate(copy.deepcopy(c), copy.deepcopy(p), evaluated_at=NOW)
        self.assertEqual(a, b)
        material = dict(a); digest = material.pop("receipt_sha256")
        self.assertEqual(digest, sha256_json(material))

    def test_receipt_changes_if_candidate_priority_changes(self):
        p1 = proposal("Z-Meridian-913506-L91", "Z-Meridian", ["ZMER-913506-L91"])
        p2 = proposal("Z-Orchid-913506-K22", "Z-Orchid", ["ZORC-913506-K22"])
        a = evaluate(census(), [p1, p2], evaluated_at=NOW)
        b = evaluate(census(), [p2, p1], evaluated_at=NOW)
        self.assertNotEqual(a["receipt_sha256"], b["receipt_sha256"])
        self.assertNotEqual(a["selected"]["seat_id"], b["selected"]["seat_id"])


if __name__ == "__main__":
    unittest.main()
