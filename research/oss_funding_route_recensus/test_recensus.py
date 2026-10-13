#!/usr/bin/env python3
from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from research.oss_funding_route_recensus import recensus


def canon(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()


class RecensusTests(unittest.TestCase):
    def setUp(self):
        self.prior = {
            "schema": recensus.PRIOR_SCHEMA,
            "operation": recensus.PRIOR_OPERATION,
            "generated_at_utc": "2026-09-17T00:00:00Z",
            "as_of_date": "2026-09-16",
            "authority_profiles": {},
            "fence_profiles": {},
            "reward_state_definitions": {},
            "action_profiles": {},
            "gate_profiles": {},
            "proof_catalog": {},
            "sources": [{"id": "source-a", "url": "https://example.test/a", "authority": "FIRST_PARTY", "observed_at_utc": "2026-09-17T00:00:00Z", "currentness_fact": "route is open"}],
            "opportunities": [{"id": "opp-a", "name": "Opportunity A", "source": "source-a", "route": "GRANT", "reward": "ADVERTISED", "current": "OPEN", "priority": 1, "fit": ["systems"], "action": "A", "gate": "G", "econ": {"cash_kind": "CASH", "advertised_value": "$100"}, "proof": "P", "fence": "RECENSUS_V1", "authority": "RESEARCH_ONLY_V1"}],
            "summary": {},
        }
        self.prior_raw = canon(self.prior)
        source_digest = hashlib.sha256(canon({"id": "source-a", "url": "https://example.test/a", "authority": "FIRST_PARTY", "observed_at_utc": "2026-09-17T00:00:00Z", "currentness_fact": "route is open"})).hexdigest()
        self.obs = {
            "schema": recensus.OBS_SCHEMA,
            "operation": recensus.OPERATION,
            "generated_at_utc": "2026-09-17T01:00:00Z",
            "adapter": {"id": "adapter-a", "generation": "gen-1", "authority": recensus.ADAPTER_AUTHORITY},
            "prior_generation": {"operation": recensus.PRIOR_OPERATION, "generated_at_utc": self.prior["generated_at_utc"], "map_sha256": hashlib.sha256(self.prior_raw).hexdigest()},
            "observations": [{"opportunity_id": "opp-a", "source_id": "source-a", "source_url": "https://example.test/a", "source_sha256": source_digest, "observed_at_utc": "2026-09-17T01:00:00Z", "current": "OPEN", "currentness_fact": "route is open", "econ": {"cash_kind": "CASH", "advertised_value": "$100"}, "aliases": [], "conflicts": []}],
        }

    def compile(self, obs=None, prior=None):
        prior = self.prior if prior is None else prior
        obs = self.obs if obs is None else obs
        return recensus.compile_report(canon(prior), prior, canon(obs), obs)

    def outcome(self, obs=None):
        return self.compile(obs)["routes"][0]

    def test_same_open(self):
        row = self.outcome()
        self.assertEqual(row["outcome"], "SAME_OPEN")
        self.assertEqual(row["changed_fields"], [])

    def test_changed_fact_requires_review(self):
        obs = copy.deepcopy(self.obs); obs["observations"][0]["currentness_fact"] = "window extended"
        self.assertEqual(self.outcome(obs)["outcome"], "CHANGED_REVIEW")

    def test_economic_change_is_not_silent(self):
        obs = copy.deepcopy(self.obs); obs["observations"][0]["econ"]["advertised_value"] = "$200"
        row = self.outcome(obs)
        self.assertEqual(row["outcome"], "CHANGED_REVIEW")
        self.assertIn("ECONOMIC_REVIEW_REQUIRED", row["downstream_block_reasons"])

    def test_cash_kind_change_is_review(self):
        obs = copy.deepcopy(self.obs); obs["observations"][0]["econ"]["cash_kind"] = "NONCASH"
        self.assertIn("econ.cash_kind", self.outcome(obs)["changed_fields"])

    def test_closed(self):
        obs = copy.deepcopy(self.obs); obs["observations"][0]["current"] = "CLOSED"
        self.assertEqual(self.outcome(obs)["outcome"], "CLOSED")

    def test_stale(self):
        obs = copy.deepcopy(self.obs); obs["generated_at_utc"] = "2026-09-21T01:00:01Z"
        self.assertEqual(self.outcome(obs)["outcome"], "STALE")

    def test_conflict_precedes_other_classification(self):
        obs = copy.deepcopy(self.obs); obs["observations"][0]["conflicts"] = ["two trusted adapters disagree"]; obs["observations"][0]["current"] = "CLOSED"
        self.assertEqual(self.outcome(obs)["outcome"], "CONFLICT")

    def test_source_substitution_rejected(self):
        obs = copy.deepcopy(self.obs); obs["observations"][0]["source_id"] = "other"
        with self.assertRaisesRegex(recensus.RecensusError, "source substitution"): self.compile(obs)

    def test_source_url_substitution_rejected(self):
        obs = copy.deepcopy(self.obs); obs["observations"][0]["source_url"] = "https://evil.test/"
        with self.assertRaisesRegex(recensus.RecensusError, "source URL substitution"): self.compile(obs)

    def test_prior_digest_mismatch_rejected(self):
        obs = copy.deepcopy(self.obs); obs["prior_generation"]["map_sha256"] = "0" * 64
        with self.assertRaisesRegex(recensus.RecensusError, "prior map digest mismatch"): self.compile(obs)

    def test_prior_generation_mismatch_rejected(self):
        obs = copy.deepcopy(self.obs); obs["prior_generation"]["generated_at_utc"] = "2026-09-16T00:00:00Z"
        with self.assertRaisesRegex(recensus.RecensusError, "prior generation mismatch"): self.compile(obs)

    def test_future_observation_rejected(self):
        obs = copy.deepcopy(self.obs); obs["observations"][0]["observed_at_utc"] = "2026-09-17T02:00:00Z"
        with self.assertRaisesRegex(recensus.RecensusError, "future observation"): self.compile(obs)

    def test_untrusted_adapter_rejected(self):
        obs = copy.deepcopy(self.obs); obs["adapter"]["authority"] = "CALLER"
        with self.assertRaisesRegex(recensus.RecensusError, "TRUSTED_EVIDENCE_ADAPTER"): self.compile(obs)

    def test_missing_route_observation_rejected(self):
        obs = copy.deepcopy(self.obs); obs["observations"] = []
        with self.assertRaisesRegex(recensus.RecensusError, "coverage mismatch"): self.compile(obs)

    def test_unknown_route_rejected(self):
        obs = copy.deepcopy(self.obs); obs["observations"][0]["opportunity_id"] = "unknown"
        with self.assertRaisesRegex(recensus.RecensusError, "unknown opportunity"): self.compile(obs)

    def test_ambiguous_alias_rejected(self):
        prior = copy.deepcopy(self.prior); second = copy.deepcopy(prior["opportunities"][0]); second["id"] = "opp-b"; prior["opportunities"].append(second)
        prior_raw = canon(prior); obs = copy.deepcopy(self.obs); obs["prior_generation"]["map_sha256"] = hashlib.sha256(prior_raw).hexdigest(); obs["observations"][0]["aliases"] = ["same-alias"]
        second_obs = copy.deepcopy(obs["observations"][0]); second_obs["opportunity_id"] = "opp-b"; second_obs["aliases"] = ["same-alias"]; obs["observations"].append(second_obs)
        with self.assertRaisesRegex(recensus.RecensusError, "ambiguous alias"): recensus.compile_report(prior_raw, prior, canon(obs), obs)

    def test_alias_cannot_shadow_canonical_id(self):
        obs = copy.deepcopy(self.obs); obs["observations"][0]["aliases"] = ["opp-a"]
        with self.assertRaisesRegex(recensus.RecensusError, "canonical id"): self.compile(obs)

    def test_duplicate_json_key_rejected(self):
        with self.assertRaisesRegex(recensus.RecensusError, "duplicate JSON key"): recensus._strict_json_bytes(b'{"schema":"x","schema":"y"}', "x")

    def test_nonfinite_json_rejected(self):
        with self.assertRaisesRegex(recensus.RecensusError, "non-finite"): recensus._strict_json_bytes(b'{"x":NaN}', "x")

    def test_bool_does_not_bypass_object_shape(self):
        obs = copy.deepcopy(self.obs); obs["observations"][0]["econ"] = True
        with self.assertRaisesRegex(recensus.RecensusError, "must be object"): self.compile(obs)

    def test_report_tamper_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); prior_path = root / "prior.json"; obs_path = root / "obs.json"; report_path = root / "report.json"
            prior_path.write_bytes(self.prior_raw); obs_raw = canon(self.obs); obs_path.write_bytes(obs_raw)
            report = recensus.compile_report(self.prior_raw, self.prior, obs_raw, self.obs); report_path.write_bytes(recensus._canon(report)); recensus.verify_report(prior_path, obs_path, report_path)
            tampered = copy.deepcopy(report); tampered["routes"][0]["outcome"] = "CLOSED"; report_path.write_bytes(recensus._canon(tampered))
            with self.assertRaisesRegex(recensus.RecensusError, "exact recomputation"): recensus.verify_report(prior_path, obs_path, report_path)

    def test_exclusive_output_refuses_existing(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "out.json"; path.write_text("existing", encoding="utf-8")
            with self.assertRaisesRegex(recensus.RecensusError, "exclusive output create failed"): recensus._write_exclusive(path, b"new\n")
            self.assertEqual(path.read_text(encoding="utf-8"), "existing")

    def test_reference_adapter_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); prior_path = root / "prior.json"; obs_path = root / "obs.json"; report_path = root / "report.json"
            prior_path.write_bytes(self.prior_raw); recensus.make_reference_observations(prior_path, obs_path); obs_raw, obs_data = recensus._read(obs_path, "obs")
            report = recensus.compile_report(self.prior_raw, self.prior, obs_raw, obs_data); recensus._write_exclusive(report_path, recensus._canon(report)); verified = recensus.verify_report(prior_path, obs_path, report_path)
            self.assertEqual(verified["routes"][0]["outcome"], "SAME_OPEN")


if __name__ == "__main__":
    unittest.main()
