from __future__ import annotations

import copy
import unittest
from unittest.mock import patch

from revenue.commercial_experiment_lab.common import INPUT_SCHEMA, UPSTREAM_READY, LabError, strict_loads
from revenue.commercial_experiment_lab.compiler import compile_experiment, verify_artifacts, verify_compilation

AS_OF = "2026-09-13T12:00:00Z"
COMMIT = "a" * 40
SHA = "b" * 64


def source(path: str) -> dict[str, str]:
    return {"repository": "woahwhattheheck/commons", "commit": COMMIT, "path": path, "sha256": SHA}


def fake_opp(opp_id: str, offer: str, stages: dict[str, str], *, state: str = UPSTREAM_READY,
             gross: dict[str, int] | None = None, reversals: dict[str, int] | None = None) -> dict:
    strongest = max(stages, key=lambda s: ("TRAFFIC", "REPLY", "ACCEPTANCE", "DELIVERY", "TRANSFER", "CASH").index(s))
    gross, reversals = gross or {}, reversals or {}
    return {
        "id": opp_id, "family": "SERVICE",
        "offer": {"id": offer, "version": "v1", "source": source(f"offers/{offer}.json")},
        "state": state, "hold_reasons": [] if state == UPSTREAM_READY else ["EVIDENCE_STALE"],
        "strongest_evidenced_stage": strongest, "stage_times": stages,
        "latest_evidence_age_bucket": "0_1D", "next_evidence_needed": "NONE",
        "gross_cash_by_currency": gross, "cash_reversals_by_currency": reversals,
        "net_cash_by_currency": {c: n - reversals.get(c, 0) for c, n in gross.items()}, "noncash_awards": {},
        "events": [{"id": f"evt-{opp_id}", "stage": strongest, "observed_at": min(stages.values()),
                    "evidence": source(f"events/{opp_id}.json"), "proves": []}],
    }


def fixture() -> tuple[dict, dict]:
    value = {
        "schema": INPUT_SCHEMA,
        "plan": {
            "id": "exp-1", "revision": "r1", "family": "SERVICE", "declared_at": "2026-09-13T09:00:00Z",
            "source": source("experiments/plan.json"), "opportunity_ids": ["a1", "a2", "b1", "b2"],
            "arms": [
                {"id": "arm-a", "segment": "ops-smb", "offer_id": "diag", "offer_version": "v1", "proof_package": "map", "route_class": "EMAIL"},
                {"id": "arm-b", "segment": "ops-midmarket", "offer_id": "proof", "offer_version": "v1", "proof_package": "binary", "route_class": "FORM"},
            ],
            "minimum_sample_per_arm": 2,
            "thresholds": {"expand_reply_bps": 7500, "expand_acceptance_bps": 5000, "pause_reply_bps": 2500},
        },
        "assignments": [
            {"id": f"assign-{oid}", "opportunity_id": oid, "arm_id": arm, "assigned_at": f"2026-09-13T09:{minute}:00Z", "evidence": source(f"experiments/{oid}.json")}
            for oid, arm, minute in [("a1", "arm-a", "10"), ("a2", "arm-a", "11"), ("b1", "arm-b", "12"), ("b2", "arm-b", "13")]
        ],
        "funnel": {"fixture": "synthetic"},
    }
    opps = [
        fake_opp("a1", "diag", {"TRAFFIC": "2026-09-13T10:10:00Z", "REPLY": "2026-09-13T10:20:00Z", "ACCEPTANCE": "2026-09-13T10:30:00Z", "DELIVERY": "2026-09-13T10:40:00Z", "TRANSFER": "2026-09-13T10:50:00Z", "CASH": "2026-09-13T11:00:00Z"}, gross={"USD": 100}, reversals={"USD": 25}),
        fake_opp("a2", "diag", {"TRAFFIC": "2026-09-13T10:11:00Z", "REPLY": "2026-09-13T10:26:00Z"}),
        fake_opp("b1", "proof", {"TRAFFIC": "2026-09-13T10:12:00Z"}),
        fake_opp("b2", "proof", {"TRAFFIC": "2026-09-13T10:13:00Z"}),
    ]
    upstream = {"packet": {"state": UPSTREAM_READY, "opportunities": opps},
                "receipt": {"input_sha256": "c" * 64, "packet_sha256": "d" * 64}}
    return value, upstream


class ExperimentTests(unittest.TestCase):
    def compile(self, value: dict, upstream: dict) -> dict:
        with patch("revenue.commercial_experiment_lab.compiler._compile_upstream", return_value=upstream):
            return compile_experiment(value, as_of=AS_OF)

    def test_metrics_money_timing_descriptive_status_and_authority(self) -> None:
        value, upstream = fixture(); result = self.compile(value, upstream)
        arms = {x["arm"]["id"]: x for x in result["packet"]["arms"]}; a, b = arms["arm-a"], arms["arm-b"]
        self.assertEqual((a["stage_reach_bps"]["REPLY"], a["stage_reach_bps"]["ACCEPTANCE"], a["stage_reach_bps"]["CASH"]), (10000, 5000, 5000))
        self.assertEqual(a["median_seconds_from_traffic"]["REPLY"], 600)
        self.assertEqual((a["gross_cash_by_currency"], a["cash_reversals_by_currency"], a["net_cash_by_currency"]), ({"USD": 100}, {"USD": 25}, {"USD": 75}))
        self.assertEqual((a["strategy_status"]["state"], b["strategy_status"]["state"]), ("DESCRIPTIVE_ONLY", "DESCRIPTIVE_ONLY"))
        self.assertEqual(result["packet"]["chronology"]["state"], "SELF_ASSERTED_UNVERIFIED")
        self.assertFalse(result["packet"]["chronology"]["strategy_recommendations_authorized"])
        self.assertEqual(result["packet"]["comparisons"][0]["interpretation"], "OBSERVATIONAL_NOT_CAUSAL")
        self.assertTrue(all(v is False for v in result["packet"]["authority"].values()))

    def test_assignment_and_binding_guards(self) -> None:
        cases = []
        v, u = fixture(); v["assignments"][0]["assigned_at"] = "2026-09-13T10:10:00Z"; cases.append((v, u, "post-outcome"))
        v, u = fixture(); v["assignments"][1]["opportunity_id"] = "a1"; cases.append((v, u, "assigned more than once"))
        v, u = fixture(); v["assignments"].pop(); cases.append((v, u, "missing assignments"))
        v, u = fixture(); v["plan"]["arms"][0]["offer_version"] = "v2"; cases.append((v, u, "offer identity"))
        v, u = fixture(); v["plan"]["family"] = "PRODUCT"; cases.append((v, u, "family"))
        for value, upstream, text in cases:
            with self.subTest(text=text), self.assertRaisesRegex(LabError, text): self.compile(value, upstream)

    def test_upstream_hold_excluded_and_reported_descriptively(self) -> None:
        value, upstream = fixture(); opp = upstream["packet"]["opportunities"][0]; opp["state"] = "HOLD"; opp["hold_reasons"] = ["EVIDENCE_STALE"]; upstream["packet"]["state"] = "HOLD"
        result = self.compile(value, upstream); arm = {x["arm"]["id"]: x for x in result["packet"]["arms"]}["arm-a"]
        self.assertEqual((arm["eligible_count"], arm["held_count"], arm["strategy_status"]["state"]), (1, 1, "DESCRIPTIVE_ONLY"))
        self.assertIn("UPSTREAM_HOLD_PRESENT", arm["strategy_status"]["reasons"])
        self.assertEqual(result["packet"]["excluded_opportunities"][0]["reason"], "UPSTREAM_FUNNEL_HOLD")

    def test_no_fx_and_order_invariance(self) -> None:
        value, upstream = fixture(); upstream["packet"]["opportunities"][1]["gross_cash_by_currency"] = {"EUR": 200}; upstream["packet"]["opportunities"][1]["net_cash_by_currency"] = {"EUR": 200}
        one = self.compile(copy.deepcopy(value), copy.deepcopy(upstream)); self.assertEqual({x["arm"]["id"]: x for x in one["packet"]["arms"]}["arm-a"]["net_cash_by_currency"], {"EUR": 200, "USD": 75})
        value["plan"]["opportunity_ids"].reverse(); value["plan"]["arms"].reverse(); value["assignments"].reverse(); upstream["packet"]["opportunities"].reverse()
        two = self.compile(value, upstream); self.assertEqual((one["packet"], one["receipt"]), (two["packet"], two["receipt"]))

    def test_identity_and_upstream_digest_bind_receipt(self) -> None:
        value, upstream = fixture(); one = self.compile(copy.deepcopy(value), copy.deepcopy(upstream))
        value["assignments"][0]["id"] = "assign-a1-rebound"; two = self.compile(value, upstream); self.assertNotEqual(one["receipt"]["receipt_sha256"], two["receipt"]["receipt_sha256"])
        value, upstream = fixture(); three = self.compile(copy.deepcopy(value), copy.deepcopy(upstream)); upstream["receipt"]["input_sha256"] = "e" * 64; upstream["receipt"]["packet_sha256"] = "f" * 64
        four = self.compile(value, upstream); self.assertNotEqual(three["packet"]["input_sha256"], four["packet"]["input_sha256"])

    def test_post_hoc_backdating_and_threshold_rewrite_cannot_mint_strategy_advice(self) -> None:
        # Red-team attack: start after outcomes are known, backdate the caller-owned
        # declaration/assignment record, rewrite the declared thresholds to favor the
        # observed winner, and reseal syntactically valid source metadata. V1 accepts
        # the internally consistent historical record but must downgrade it to
        # self-asserted descriptive evidence with no expand/pause/keep-testing state.
        value, upstream = fixture()
        value["plan"]["declared_at"] = "2026-09-13T09:50:00Z"
        for i, assignment in enumerate(value["assignments"]):
            assignment["assigned_at"] = f"2026-09-13T10:0{i}:00Z"
            assignment["evidence"] = source(f"resealed/posthoc-{i}.json")
        value["plan"]["source"] = source("resealed/posthoc-plan.json")
        value["plan"]["thresholds"] = {"expand_reply_bps": 1, "expand_acceptance_bps": 1, "pause_reply_bps": 0}
        result = self.compile(value, upstream)
        self.assertEqual(result["packet"]["chronology"], {
            "state": "SELF_ASSERTED_UNVERIFIED",
            "plan_predeclaration_authenticated": False,
            "assignment_chronology_authenticated": False,
            "declared_thresholds_authenticated": False,
            "strategy_recommendations_authorized": False,
        })
        self.assertTrue(all(arm["strategy_status"]["state"] == "DESCRIPTIVE_ONLY" for arm in result["packet"]["arms"]))
        rendered = repr(result["packet"])
        for forbidden in ("EXPAND_CANDIDATE", "PAUSE_REVIEW", "KEEP_TESTING"):
            self.assertNotIn(forbidden, rendered)
        self.assertEqual(result["receipt"]["chronology_state"], "SELF_ASSERTED_UNVERIFIED")
        self.assertFalse(result["receipt"]["strategy_recommendations_authorized"])

    def test_self_asserted_minimum_sample_is_only_a_note(self) -> None:
        value, upstream = fixture(); value["plan"]["minimum_sample_per_arm"] = 3
        result = self.compile(value, upstream)
        for arm in result["packet"]["arms"]:
            self.assertEqual(arm["strategy_status"]["state"], "DESCRIPTIVE_ONLY")
            self.assertIn("SELF_ASSERTED_MINIMUM_SAMPLE_NOT_MET", arm["strategy_status"]["reasons"])

    def test_shape_time_number_pii_and_source_guards(self) -> None:
        cases = []
        v, u = fixture(); v["assignments"][0]["assigned_at"] = "2026-09-13T12:00:01Z"; cases.append((v, u))
        v, u = fixture(); v["assignments"][0]["assigned_at"] = "2026-09-13T08:59:59Z"; cases.append((v, u))
        v, u = fixture(); v["plan"]["minimum_sample_per_arm"] = True; cases.append((v, u))
        v, u = fixture(); v["plan"]["minimum_sample_per_arm"] = 9_000_000_000_000_001; cases.append((v, u))
        v, u = fixture(); v["plan"]["arms"][0]["segment"] = "person@example.com"; cases.append((v, u))
        v, u = fixture(); v["plan"]["source"]["sha256"] = "abc"; cases.append((v, u))
        for value, upstream in cases:
            with self.subTest(case=len(value.get("assignments", []))), self.assertRaises(LabError): self.compile(value, upstream)
        with self.assertRaisesRegex(LabError, "duplicate JSON key"): strict_loads('{"schema":"a","schema":"b"}')

    def test_verifiers_detect_packet_receipt_and_report_tamper(self) -> None:
        value, upstream = fixture(); compiled = self.compile(value, upstream)
        with patch("revenue.commercial_experiment_lab.compiler._compile_upstream", return_value=upstream):
            self.assertTrue(verify_compilation(value, as_of=AS_OF, packet=compiled["packet"], receipt=compiled["receipt"]))
            bad_packet = copy.deepcopy(compiled["packet"]); bad_packet["arms"][0]["assigned_count"] += 1
            self.assertFalse(verify_compilation(value, as_of=AS_OF, packet=bad_packet, receipt=compiled["receipt"]))
            bad_receipt = copy.deepcopy(compiled["receipt"]); bad_receipt["receipt_sha256"] = "0" * 64
            self.assertFalse(verify_compilation(value, as_of=AS_OF, packet=compiled["packet"], receipt=bad_receipt))
            self.assertTrue(verify_artifacts(value, as_of=AS_OF, packet=compiled["packet"], receipt=compiled["receipt"], report_json=compiled["json"], report_csv=compiled["csv"], report_markdown=compiled["markdown"]))
            self.assertFalse(verify_artifacts(value, as_of=AS_OF, packet=compiled["packet"], receipt=compiled["receipt"], report_json=compiled["json"] + b"x", report_csv=compiled["csv"], report_markdown=compiled["markdown"]))

    def test_real_upstream_contract(self) -> None:
        try:
            from revenue.commercial_funnel import compile_funnel as _real  # noqa: F401
        except ImportError:
            self.skipTest("commercial_funnel package only exists in repository checkout")
        def ev(i: str, when: str) -> dict: return {"id": i, "stage": "TRAFFIC", "observed_at": when, "evidence": source(f"events/{i}.json")}
        value = {
            "schema": INPUT_SCHEMA,
            "plan": {"id": "real", "revision": "r1", "family": "SERVICE", "declared_at": "2026-09-13T09:00:00Z", "source": source("experiments/real.json"), "opportunity_ids": ["r1", "r2"],
                     "arms": [{"id": "ra", "segment": "smb", "offer_id": "diag", "offer_version": "v1", "proof_package": "map", "route_class": "EMAIL"}, {"id": "rb", "segment": "midmarket", "offer_id": "diag", "offer_version": "v1", "proof_package": "proof", "route_class": "FORM"}],
                     "minimum_sample_per_arm": 1, "thresholds": {"expand_reply_bps": 5000, "expand_acceptance_bps": 5000, "pause_reply_bps": 1000}},
            "assignments": [{"id": "as1", "opportunity_id": "r1", "arm_id": "ra", "assigned_at": "2026-09-13T09:10:00Z", "evidence": source("experiments/as1.json")}, {"id": "as2", "opportunity_id": "r2", "arm_id": "rb", "assigned_at": "2026-09-13T09:10:00Z", "evidence": source("experiments/as2.json")}],
            "funnel": {"schema": "commons-commercial-funnel-input/v1", "opportunities": [
                {"id": "r1", "family": "SERVICE", "offer": {"id": "diag", "version": "v1", "source": source("offers/diag.json")}, "events": [ev("e1", "2026-09-13T10:00:00Z")]},
                {"id": "r2", "family": "SERVICE", "offer": {"id": "diag", "version": "v1", "source": source("offers/diag.json")}, "events": [ev("e2", "2026-09-13T10:01:00Z")]},
            ]},
        }
        self.assertEqual(compile_experiment(value, as_of=AS_OF)["packet"]["upstream_funnel"]["state"], UPSTREAM_READY)


if __name__ == "__main__":
    unittest.main()
