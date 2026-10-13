from __future__ import annotations

import copy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from evaluation import (SCORER, Trace, canonical, complete, diagnostics, digest, matched,
                        paired_bootstrap, report, ts_auc, validate, verify_report)
from stress import Case, SCENARIOS, corpus, f32, load_detector, make_case, run, summary


def trace(name="a", scores=(0.1, 0.9), tau=1, cluster=0, scenario="case"):
    return Trace(name, cluster, scenario, digest(name), tau, tuple(scores))


def manifest(items):
    return [{"case_id": t.case_id, "cluster": t.cluster, "scenario": t.scenario,
             "case_sha256": t.case_sha256, "break_index": t.break_index,
             "online_length": len(t.scores)} for t in items]


class MetricTests(unittest.TestCase):
    def test_perfect(self):
        self.assertEqual(ts_auc([trace("a", (0.1,), None), trace("b", (0.9,), 0)])["ts_auc"], 1)

    def test_reverse(self):
        self.assertEqual(ts_auc([trace("a", (0.9,), None), trace("b", (0.1,), 0)])["ts_auc"], 0)

    def test_ties(self):
        self.assertEqual(ts_auc([trace("a", (0.5,), None), trace("b", (0.5,), 0)])["ts_auc"], 0.5)

    def test_pair_weighting_not_macro_average(self):
        items = [trace("a", (0.1, 0.1), None), trace("b", (0.9, 0.1), 0),
                 trace("c", (0.1,), None), trace("d", (0.9,), 0), trace("e", (0.9,), 0)]
        value = ts_auc(items)
        self.assertEqual(value["comparable_pairs"], 7)
        self.assertEqual(value["ts_auc"], 6.5 / 7)

    def test_clock_only_does_not_score(self):
        items = [trace("a", (0.0, 0.1, 0.9, 1.0), None), trace("b", (0.0, 0.1, 0.9, 1.0), 2)]
        self.assertEqual(ts_auc(items)["ts_auc"], 0.5)
        self.assertEqual(ts_auc(items)["skipped_steps"], 2)

    def test_degenerate_is_explicit(self):
        for tau in (None, 0):
            value = ts_auc([trace(tau=tau)])
            self.assertEqual(value["ts_auc"], 0.5)
            self.assertTrue(value["no_comparable_pairs"])

    def test_break_is_inclusive(self):
        t = trace(scores=(0.0, 0.0, 1.0), tau=2)
        self.assertEqual([t.label(i) for i in range(3)], [0, 0, 1])

    def test_panel_order_invariance(self):
        items = [trace("b"), trace("a", tau=None)]
        self.assertEqual(ts_auc(items), ts_auc(reversed(items)))

    def test_empty_panel(self):
        with self.assertRaises(ValueError):
            ts_auc([])

    def test_duplicate_identity_rejected(self):
        with self.assertRaises(ValueError):
            ts_auc([trace(), trace()])

    def test_invalid_scores(self):
        for value in (True, False, float("nan"), float("inf"), -0.01, 1.01, 10**1000, "0.5"):
            with self.subTest(value=str(value)[:20]), self.assertRaises(ValueError):
                trace(scores=(value,), tau=0)

    def test_invalid_tau(self):
        for tau in (-1, 2, True, 0.0, "1"):
            with self.subTest(tau=tau), self.assertRaises(ValueError):
                trace(tau=tau)

    def test_invalid_cluster(self):
        for cluster in (-1, True, 1.0):
            with self.subTest(cluster=cluster), self.assertRaises(ValueError):
                trace(cluster=cluster)

    def test_record_roundtrip(self):
        t = trace()
        self.assertEqual(Trace.from_record(t.record()), t)

    def test_record_unknown_or_missing_field(self):
        for record in ({**trace().record(), "unknown": 0}, {"case_id": "a"}):
            with self.assertRaises(ValueError):
                Trace.from_record(record)

    def test_invalid_text_digest(self):
        for changes in ({"case_id": "a\nb"}, {"scenario": ""}, {"case_sha256": "f" * 63}):
            with self.assertRaises(ValueError):
                replace(trace(), **changes)

    def test_diagnostics_separates_early_alarms_and_conditional_delay(self):
        items = [trace("a", (0.9, 0.1, 0.1, 0.8), 2), trace("b", (0.1, 0.1, 0.1, 0.1), 2),
                 trace("c", (0.1, 0.6), None)]
        d = diagnostics(items)["case"]
        self.assertEqual((d["prebreak_false_alarms"], d["postbreak_hits"], d["postbreak_delay_median"]), (1, 1, 1))
        self.assertEqual(d["null_false_alarms"], 1)


class CompleteEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.items = [trace("a"), trace("b", tau=None, cluster=1)]
        self.manifest = manifest(self.items)
        self.kwargs = {"candidate_sha256": "a" * 64, "case_manifest": self.manifest}

    def test_report_replay(self):
        value = report(self.items, **self.kwargs)
        self.assertTrue(verify_report(value, self.items, **self.kwargs))
        self.assertEqual(value, report(reversed(self.items), **self.kwargs))

    def test_report_metadata_is_not_a_mutable_alias_of_the_source_pin(self):
        value = report(self.items, **self.kwargs)
        original = copy.deepcopy(SCORER)
        value["scorer_source"]["commit"] = "0" * 40
        self.assertEqual(SCORER, original)
        self.assertFalse(verify_report(value, self.items, **self.kwargs))

    def test_missing_or_extra_case(self):
        for items in (self.items[:1], self.items + [trace("c")]):
            with self.assertRaises(ValueError):
                report(items, **self.kwargs)

    def test_truncated_online_trace(self):
        items = [replace(self.items[0], scores=(0.9,), break_index=0), self.items[1]]
        with self.assertRaises(ValueError):
            report(items, **self.kwargs)

    def test_label_hash_scenario_and_cluster_transplants(self):
        for changes in ({"break_index": 0}, {"case_sha256": "b" * 64}, {"scenario": "other"}, {"cluster": 6}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                report([replace(self.items[0], **changes), self.items[1]], **self.kwargs)

    def test_resealed_false_metric_is_not_verified(self):
        value = report(self.items, **self.kwargs)
        value["metric"]["ts_auc"] = 0.123
        value["report_sha256"] = digest({k: v for k, v in value.items() if k != "report_sha256"})
        self.assertFalse(verify_report(value, self.items, **self.kwargs))

    def test_mutated_scores_invalidate_receipt(self):
        value = report(self.items, **self.kwargs)
        changed = [replace(self.items[0], scores=(0.8, 0.1)), self.items[1]]
        self.assertFalse(verify_report(value, changed, **self.kwargs))

    def test_expected_candidate_source_is_required(self):
        value = report(self.items, **self.kwargs)
        self.assertFalse(verify_report(value, self.items, **{**self.kwargs, "candidate_sha256": "b" * 64}))

    def test_boolean_manifest_alias_is_not_an_integer(self):
        m = copy.deepcopy(self.manifest)
        m[0]["cluster"] = False
        with self.assertRaises(ValueError):
            complete(self.items, m)

    def test_unknown_receipt_field_rejected(self):
        value = {**report(self.items, **self.kwargs), "send_authority": True}
        self.assertFalse(verify_report(value, self.items, **self.kwargs))

    def test_manifest_order_invariance(self):
        self.assertEqual(report(self.items, **self.kwargs), report(self.items, **{**self.kwargs, "case_manifest": self.manifest[::-1]}))


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.a = [trace("a", (0.1, 0.8, 0.8), 1, 0), trace("b", (0.2, 0.3), None, 0),
                  trace("c", (0.9, 0.2, 0.4), 0, 1), trace("d", (0.7, 0.5, 0.2), None, 1)]
        self.b = [replace(t, scores=tuple(1 - s for s in t.scores)) for t in self.a]

    def test_same_scores_have_zero_delta(self):
        r = paired_bootstrap(self.a, self.a, replicates=20)
        self.assertEqual(r["ci95"], [0, 0])
        self.assertEqual(r["candidate_minus_reference"], 0)

    def test_bootstrap_matches_literal_cluster_duplication(self):
        import numpy as np
        weights = np.random.default_rng(1729).multinomial(2, [0.5, 0.5], size=41)
        values = []
        for w in weights:
            panels = []
            for source in (self.a, self.b):
                repeated = []
                for t in source:
                    for j in range(int(w[t.cluster])):
                        repeated.append(replace(t, case_id=t.case_id + "/" + str(j)))
                panels.append(ts_auc(repeated)["ts_auc"])
            values.append(panels[1] - panels[0])
        actual = paired_bootstrap(self.a, self.b, replicates=41)
        np.testing.assert_allclose(actual["ci95"], np.quantile(values, [0.025, 0.975]), atol=1e-14)

    def test_paired_order_invariance(self):
        self.assertEqual(paired_bootstrap(self.a, self.b, replicates=20), paired_bootstrap(self.a[::-1], self.b[::-1], replicates=20))

    def test_mismatched_case_cannot_be_compared(self):
        with self.assertRaises(ValueError):
            matched(self.a, self.b[:-1])

    def test_wrong_label_cannot_be_compared(self):
        with self.assertRaises(ValueError):
            matched(self.a, [replace(self.b[0], break_index=0)] + self.b[1:])

    def test_bootstrap_requires_multiple_clusters(self):
        with self.assertRaises(ValueError):
            paired_bootstrap(self.a[:2], self.b[:2])

    def test_bad_bootstrap_arguments(self):
        for kwargs in ({"replicates": 0}, {"replicates": True}, {"seed": -1}):
            with self.assertRaises(ValueError):
                paired_bootstrap(self.a, self.b, **kwargs)


class HarnessTests(unittest.TestCase):
    def test_corpus_is_repeatable(self):
        self.assertEqual(make_case(20000, "null_iid"), make_case(20000, "null_iid"))
        self.assertNotEqual(make_case(20000, "null_iid").manifest(), make_case(20001, "null_iid").manifest())

    def test_all_scenarios_and_variable_lengths(self):
        cases = corpus(20000, 4)
        self.assertEqual(len(cases), 4 * len(SCENARIOS))
        self.assertEqual({len(c.online) for c in cases}, {10, 64, 256, 1000})
        self.assertEqual(len({c.case_id for c in cases}), len(cases))

    def test_null_truth_and_change_boundaries(self):
        for scenario in SCENARIOS:
            c = make_case(20000, scenario)
            if scenario.startswith("null_"):
                self.assertIsNone(c.break_index)
            else:
                self.assertTrue(0 <= c.break_index < len(c.online))

    def test_factory_receives_only_history_and_one_point_per_update(self):
        observed = []
        class Spy:
            def __init__(self, history):
                observed.append(history)
            def update(self, point):
                observed.append(point)
                return 0.25
        c = Case("spy", 0, "null", (1.0, 2.0), (3.0, 4.0), None)
        traces, timing = run(Spy, (c,))
        self.assertEqual(observed, [(1.0, 2.0), 3.0, 4.0])
        self.assertEqual(traces[0].scores, (0.25, 0.25))
        self.assertEqual(timing["updates"], 2)

    def test_inference_output_is_float32(self):
        class Fixed:
            def __init__(self, history):
                pass
            def update(self, point):
                return 0.123456789
        c = Case("f32", 0, "null", (1.0,), (0.0,), None)
        traces, _ = run(Fixed, (c,))
        self.assertEqual(traces[0].scores, (f32(0.123456789),))

    def test_invalid_inference_output_fails_whole_run(self):
        class Bad:
            def __init__(self, history):
                pass
            def update(self, point):
                return float("nan")
        with self.assertRaises(ValueError):
            run(Bad, (make_case(20000, "null_iid"),))

    def test_loader_checks_bytes_before_execution(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "candidate.py"
            p.write_text("raise RuntimeError('must not execute')\n")
            with self.assertRaises(ValueError):
                load_detector(p, "0" * 64, "Detector")

    def test_loader_executes_exact_source(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "candidate.py"
            p.write_text("class Detector:\n    def __init__(self, history): pass\n    def update(self, point): return 0.5\n")
            sha = hashlib.sha256(p.read_bytes()).hexdigest()
            factory, actual = load_detector(p, sha, "Detector")
            self.assertEqual(actual, sha)
            self.assertEqual(factory(()).update(1), 0.5)

    def test_summary_exposes_verifiable_core_report(self):
        class Fixed:
            def __init__(self, history): pass
            def update(self, point): return 0.5
        cases = (make_case(20000, "null_iid"), make_case(20000, "early_mean"))
        traces, _ = run(Fixed, cases)
        value = summary(traces, cases, "a" * 64)
        self.assertTrue(verify_report(value["report"], traces, candidate_sha256="a" * 64,
                                      case_manifest=[c.manifest() for c in cases]))

    def test_parity_rejects_empty_or_invalid_panel_counts(self):
        from parity import check
        for panels in (0, -1, True, 1.5):
            with self.assertRaises(ValueError):
                check(Path("not-read"), panels=panels)

    def test_corpus_argument_validation(self):
        for kwargs in ({"seeds": 0}, {"seeds": True}, {"seed_start": -1}):
            with self.assertRaises(ValueError):
                corpus(**kwargs)


if __name__ == "__main__":
    unittest.main()
