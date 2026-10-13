"""Independent arithmetic/permutation oracles plus CLI and boundary coverage."""
from __future__ import annotations
import copy
from datetime import datetime, timedelta, timezone
import itertools
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest

from . import planner as p
from .cli import read_document

START = datetime(2026, 9, 15, 8, tzinfo=timezone.utc)
ROOT = Path(__file__).resolve().parents[2]


def stamp(minutes: int) -> str:
    return (START + timedelta(minutes=minutes)).isoformat().replace("+00:00", "Z")


def job(op: str, family: str = "f", *, reward: int = 1_000, minutes: int = 10,
        cash: int = 0, probability: int = 10_000, deadline: int | None = None) -> dict:
    return {"operation_id": op, "family_id": family, "availability": "AVAILABLE",
        "work_units": 1, "minutes": minutes, "cash_cost_minor": cash,
        "reward_minor": reward, "collection_probability_bp": probability,
        "valuation_basis": "OWNER_SCENARIO", "evidence_ref": "synthetic:" + op,
        "deadline_at": None if deadline is None else stamp(deadline)}


def scenario(jobs: list[dict] | None = None, *, families: list[dict] | None = None,
             horizon: int = 120, cash: int = 10_000, rate: int = 10,
             minimum: int = 1, nodes: int = 100_000) -> dict:
    return {"schema": p.SCHEMA, "scenario_id": "synthetic-test", "currency": "USD",
        "start_at": stamp(0), "horizon_minutes": horizon, "cash_budget_minor": cash,
        "effort_cost_minor_per_minute": rate, "minimum_net_minor": minimum,
        "node_budget": nodes, "families": families if families is not None else
            [{"id": "f", "setup_minutes": 0, "setup_cash_minor": 0}],
        "jobs": jobs if jobs is not None else [job("a"), job("b")]}


def independent_score(s: dict, ordered: tuple[dict, ...]) -> tuple | None:
    """No production helpers: simulate a supplied job order with integer money."""
    fam = {f["id"]: f for f in s["families"]}
    started, elapsed, cash, value = set(), 0, 0, 0
    origin = datetime.fromisoformat(s["start_at"].replace("Z", "+00:00"))
    for row in ordered:
        if row["availability"] != "AVAILABLE" or row["reward_minor"] is None:
            return None
        if row["family_id"] not in started:
            f = fam[row["family_id"]]
            elapsed += f["setup_minutes"]
            cash += f["setup_cash_minor"]
            started.add(row["family_id"])
        elapsed += row["minutes"]
        cash += row["cash_cost_minor"]
        value += (row["reward_minor"] * row["collection_probability_bp"]) // 10_000
        if elapsed > s["horizon_minutes"] or cash > s["cash_budget_minor"]:
            return None
        if row["deadline_at"] is not None:
            deadline = datetime.fromisoformat(row["deadline_at"].replace("Z", "+00:00"))
            if origin + timedelta(minutes=elapsed) > deadline:
                return None
    return (-(value - cash - elapsed * s["effort_cost_minor_per_minute"]),
            elapsed, cash, tuple(sorted(row["operation_id"] for row in ordered)))


def oracle(s: dict, *, permutations: bool = False) -> tuple:
    """Exhaust all subsets; optionally every order, independent of the EDD claim."""
    best = (0, 0, 0, ())
    for mask in range(1 << len(s["jobs"])):
        selected = tuple(row for i, row in enumerate(s["jobs"]) if mask & (1 << i))
        if permutations:
            orders = itertools.permutations(selected)
        else:
            end = stamp(s["horizon_minutes"])
            orders = [tuple(sorted(selected, key=lambda row: (
                min(row["deadline_at"] or end, end), row["operation_id"])))]
        for ordered in orders:
            result = independent_score(s, ordered)
            if result is not None and result < best:
                best = result
    return best


def generated(seed: int, n: int = 8) -> dict:
    rng = random.Random(seed)
    families = [{"id": f"f{i}", "setup_minutes": rng.randrange(0, 14),
        "setup_cash_minor": rng.randrange(0, 400)} for i in range(3)]
    jobs = [job(f"op-{i:03}", family=rng.choice(families)["id"],
        reward=rng.randrange(0, 4_000), minutes=rng.randrange(1, 26),
        cash=rng.randrange(0, 300), probability=rng.randrange(0, 10_001),
        deadline=rng.choice([None, 20, 45, 60, 90, 120])) for i in range(n)]
    return scenario(jobs, families=families, horizon=rng.randrange(35, 150),
        cash=rng.randrange(0, 1_700), rate=rng.randrange(0, 30), minimum=500)


class ModelTests(unittest.TestCase):
    def test_shared_setup_once_and_profitable_only_as_a_batch(self):
        s = scenario([job("a", reward=20, minutes=1), job("b", reward=20, minutes=1)],
            families=[{"id": "f", "setup_minutes": 3, "setup_cash_minor": 30}], rate=0)
        result = p.plan(s)
        self.assertEqual(result["batch"]["net_minor"], 10)
        self.assertEqual(result["batch"]["minutes"], 5)
        self.assertEqual(result["batch"]["cash_cost_minor"], 30)
        self.assertEqual([r["setup_minutes"] for r in result["batch"]["schedule"]], [3, 0])
        for row in s["jobs"]:
            self.assertEqual(p.plan({**s, "jobs": [row]})["batch"]["job_count"], 0)

    def test_all_units_are_one_indivisible_total_reward_not_a_multiplier(self):
        row = job("many-records", reward=1_000)
        row["work_units"] = 400
        result = p.plan(scenario([row]))
        self.assertEqual(result["batch"]["scenario_value_minor"], 1_000)
        self.assertEqual(result["batch"]["work_units"], 400)
        self.assertEqual(result["batch"]["job_count"], 1)

    def test_collection_rounding_is_conservative_per_job(self):
        s = scenario([job("a", reward=1, probability=5_000, minutes=1),
                      job("b", reward=1, probability=5_000, minutes=1)], rate=0)
        self.assertEqual(p.plan(s)["batch"]["scenario_value_minor"], 0)

    def test_large_nominal_reward_does_not_override_low_collection_assumption(self):
        s = scenario([job("nominal", reward=100_000, probability=100, minutes=100),
                      job("modest", reward=5_000, probability=10_000, minutes=100)], horizon=100)
        self.assertEqual(p.plan(s)["batch"]["operation_ids"], ["modest"])

    def test_zero_cash_jobs_remain_in_fractional_upper_bound(self):
        s = scenario([job("a", cash=0), job("b", cash=0)], cash=0, nodes=1)
        result = p.plan(s)
        self.assertLessEqual(result["search"]["lower_bound_minor"], -oracle(s)[0])
        self.assertGreaterEqual(result["search"]["upper_bound_minor"], -oracle(s)[0])

    def test_deadline_equality_is_feasible(self):
        s = scenario([job("a", minutes=10, deadline=10)])
        self.assertEqual(p.plan(s)["batch"]["job_count"], 1)
        s["jobs"][0]["deadline_at"] = "2026-09-15T08:09:59Z"
        self.assertEqual(p.plan(s)["batch"]["job_count"], 0)

    def test_setup_must_finish_before_work_deadline(self):
        s = scenario([job("a", minutes=10, deadline=10)],
            families=[{"id": "f", "setup_minutes": 1, "setup_cash_minor": 0}])
        self.assertIn("DEADLINE_OR_HORIZON_INFEASIBLE", p.plan(s)["unselected"][0]["reasons"])

    def test_deadline_without_time_is_not_guessed(self):
        s = scenario()
        s["jobs"][0]["deadline_at"] = "2026-09-15"
        with self.assertRaises(p.InputError):
            p.plan(s)

    def test_schedule_respects_earlier_deadline_across_families(self):
        s = scenario([job("late", "f1", minutes=20, deadline=60),
                      job("early", "f2", minutes=10, deadline=15)],
            families=[{"id": "f1", "setup_minutes": 5, "setup_cash_minor": 0},
                      {"id": "f2", "setup_minutes": 5, "setup_cash_minor": 0}])
        self.assertEqual([r["operation_id"] for r in p.plan(s)["batch"]["schedule"]], ["early", "late"])

    def test_owned_unavailable_and_unvalued_remain_visible(self):
        a, b, c = job("owned"), job("unavailable"), job("unvalued")
        a["availability"], b["availability"] = "OWNED_ELSEWHERE", "UNAVAILABLE"
        c.update(reward_minor=None, collection_probability_bp=None, valuation_basis="UNVALUED")
        result = p.plan(scenario([a, b, c]))
        self.assertEqual(result["batch"]["job_count"], 0)
        self.assertEqual(len(result["unselected"]), 3)
        self.assertEqual(result["search"]["candidate_count"], 0)

    def test_minimum_net_is_not_nominal_revenue(self):
        s = scenario([job("a", reward=1_000, minutes=90)], minimum=500)
        result = p.plan(s)
        self.assertEqual(result["batch"]["net_minor"], 100)
        self.assertEqual(result["decision"], "NO_QUALIFYING_BATCH")

    def test_cash_and_effort_budgets_are_separate(self):
        s = scenario([job("a", reward=20_000, minutes=50, cash=300)], cash=300, rate=100)
        b = p.plan(s)["batch"]
        self.assertEqual((b["cash_cost_minor"], b["effort_cost_minor"], b["net_minor"]), (300, 5_000, 14_700))
        s["cash_budget_minor"] = 299
        self.assertEqual(p.plan(s)["batch"]["job_count"], 0)

    def test_net_ties_prefer_less_time_then_cash_then_ids(self):
        s = scenario([job("b", reward=100, minutes=20), job("a", reward=100, minutes=10)],
                     horizon=20, rate=0)
        self.assertEqual(p.plan(s)["batch"]["operation_ids"], ["a"])
        s = scenario([job("b", reward=110, minutes=10, cash=10),
                      job("a", reward=100, minutes=10, cash=0)], horizon=10, rate=0)
        self.assertEqual(p.plan(s)["batch"]["operation_ids"], ["a"])
        s = scenario([job("b", reward=100, minutes=10), job("a", reward=100, minutes=10)], horizon=10, rate=0)
        self.assertEqual(p.plan(s)["batch"]["operation_ids"], ["a"])

    def test_empty_portfolio(self):
        result = p.plan(scenario([], families=[]))
        self.assertEqual(result["decision"], "NO_QUALIFYING_BATCH")
        self.assertTrue(result["search"]["complete"])
        self.assertEqual(result["search"]["upper_bound_minor"], 0)

    def test_input_is_not_mutated(self):
        s = generated(7)
        before = copy.deepcopy(s)
        p.plan(s)
        self.assertEqual(s, before)

    def test_input_order_is_byte_stable(self):
        s = generated(14)
        first = p.canonical_json(p.plan(s))
        s["jobs"].reverse()
        s["families"].reverse()
        self.assertEqual(p.canonical_json(p.plan(s)), first)

    def test_exact_search_matches_300_exhaustive_subset_oracles(self):
        for seed in range(300):
            with self.subTest(seed=seed):
                s = generated(seed)
                r = p.plan(s)
                expected = oracle(s)
                b = r["batch"]
                self.assertTrue(r["search"]["complete"])
                self.assertEqual((-b["net_minor"], b["minutes"], b["cash_cost_minor"],
                    tuple(b["operation_ids"])), expected)
                self.assertEqual(r["search"]["upper_bound_minor"], b["net_minor"])

    def test_edd_matches_all_permutations_for_60_small_cases(self):
        for seed in range(60):
            with self.subTest(seed=seed):
                s = generated(seed + 600, 5)
                self.assertEqual(oracle(s), oracle(s, permutations=True))

    def test_bounded_intervals_enclose_160_independent_optima(self):
        for seed in range(160):
            s = generated(seed + 1_000)
            optimum = -oracle(s)[0]
            for nodes in (1, 2, 7, 31):
                with self.subTest(seed=seed, nodes=nodes):
                    s["node_budget"] = nodes
                    r = p.plan(s)
                    search = r["search"]
                    self.assertLessEqual(search["nodes_expanded"], nodes)
                    self.assertLessEqual(search["lower_bound_minor"], optimum)
                    self.assertGreaterEqual(search["upper_bound_minor"], optimum)
                    self.assertEqual(search["absolute_gap_minor"], search["upper_bound_minor"] - search["lower_bound_minor"])
                    if r["decision"] == "NO_QUALIFYING_BATCH":
                        self.assertLess(optimum, s["minimum_net_minor"])
                    if r["decision"] == "QUALIFYING_SCENARIO_BATCH":
                        self.assertGreaterEqual(r["batch"]["net_minor"], s["minimum_net_minor"])

    def test_truncation_is_not_silently_called_optimal(self):
        s = generated(19, 18)
        s["node_budget"] = 1
        result = p.plan(s)
        self.assertEqual(result["search"]["status"], "BOUNDED")
        self.assertFalse(result["search"]["complete"])

    def test_bounded_search_reports_incomplete_when_threshold_between_bounds(self):
        found = False
        for seed in range(100):
            s = generated(2_000 + seed, 10)
            s["node_budget"] = 1
            r = p.plan(s)
            if r["search"]["upper_bound_minor"] > r["search"]["lower_bound_minor"]:
                s["minimum_net_minor"] = r["search"]["lower_bound_minor"] + 1
                self.assertEqual(p.plan(s)["decision"], "SEARCH_INCOMPLETE")
                found = True
                break
        self.assertTrue(found)

    def test_256_jobs_are_supported_with_a_bounded_search(self):
        s = generated(31, 256)
        s.update(node_budget=50, horizon_minutes=300, cash_budget_minor=30_000)
        r = p.plan(s)
        self.assertLessEqual(r["search"]["nodes_expanded"], 50)
        self.assertEqual(len(r["unselected"]) + r["batch"]["job_count"], 256)
        self.assertGreaterEqual(r["search"]["upper_bound_minor"], r["batch"]["net_minor"])

    def test_replay_rejects_tampering_and_parameter_change(self):
        s = scenario()
        result = p.plan(s)
        self.assertTrue(p.verify(s, result)["matches"])
        result["batch"]["net_minor"] += 1
        with self.assertRaises(p.InputError):
            p.verify(s, result)
        result = p.plan(s)
        s["cash_budget_minor"] += 1
        with self.assertRaises(p.InputError):
            p.verify(s, result)

    def test_authority_bits_never_turn_true(self):
        result = p.plan(scenario())
        self.assertEqual(result["analysis_mode"], "WHAT_IF_NOT_AUTHORITY")
        self.assertTrue(all(value is False for value in result["authority"].values()))

    def test_currency_label_never_performs_exchange(self):
        s = scenario()
        usd = p.plan(s)
        s["currency"] = "RTC"
        rtc = p.plan(s)
        self.assertEqual(usd["batch"], rtc["batch"])
        self.assertNotEqual(usd["input_sha256"], rtc["input_sha256"])
        self.assertIn("no currency conversion", p.render_text(rtc))


class ValidationTests(unittest.TestCase):
    def test_bool_float_negative_and_oversize_integer_rejected(self):
        for bad in (True, False, 1.0, -1, 10**40):
            s = scenario()
            s["cash_budget_minor"] = bad
            with self.subTest(value=repr(bad)), self.assertRaises(p.InputError):
                p.plan(s)

    def test_unknown_missing_and_mixed_key_objects_rejected(self):
        for mutate in (lambda s: s.update(extra=1), lambda s: s.pop("currency"),
                       lambda s: s.update({1: "bad", "extra": "bad"})):
            s = scenario()
            mutate(s)
            with self.assertRaises(p.InputError):
                p.plan(s)

    def test_duplicate_operation_and_family_rejected(self):
        s = scenario()
        s["jobs"].append(copy.deepcopy(s["jobs"][0]))
        with self.assertRaises(p.InputError):
            p.plan(s)
        s = scenario()
        s["families"].append(copy.deepcopy(s["families"][0]))
        with self.assertRaises(p.InputError):
            p.plan(s)

    def test_unknown_family_and_unknown_status_rejected(self):
        for key, value in (("family_id", "absent"), ("availability", "READY"),
                           ("valuation_basis", "GUARANTEED_REVENUE")):
            s = scenario()
            s["jobs"][0][key] = value
            with self.assertRaises(p.InputError):
                p.plan(s)

    def test_unvalued_does_not_accept_a_hidden_value(self):
        s = scenario()
        s["jobs"][0]["valuation_basis"] = "UNVALUED"
        with self.assertRaises(p.InputError):
            p.plan(s)

    def test_probability_is_explicit_and_bounded(self):
        for bad in (None, True, 10_001, -1, 0.5):
            s = scenario()
            s["jobs"][0]["collection_probability_bp"] = bad
            with self.assertRaises(p.InputError):
                p.plan(s)

    def test_bad_utc_and_overflow_horizon_rejected(self):
        for bad in ("2026-09-15T08:00:00+00:00", "2026-02-30T08:00:00Z", "noon", "\ud800"):
            s = scenario()
            s["start_at"] = bad
            with self.assertRaises(p.InputError):
                p.plan(s)
        s = scenario()
        s["start_at"] = "9999-12-31T23:59:00Z"
        with self.assertRaises(p.InputError):
            p.plan(s)

    def test_surrogate_control_and_contact_shaped_ids_rejected(self):
        for bad in ("bad\ud800", "bad\n", "person@example.org", "../../escape", "x" * 97):
            s = scenario()
            s["jobs"][0]["operation_id"] = bad
            with self.assertRaises(p.InputError):
                p.plan(s)

    def test_array_and_search_bounds(self):
        for key, bad in (("jobs", [job(f"a{i}") for i in range(257)]),
                         ("node_budget", 0), ("node_budget", p.MAX_NODES + 1),
                         ("horizon_minutes", 0), ("minimum_net_minor", 0)):
            s = scenario()
            s[key] = bad
            with self.assertRaises(p.InputError):
                p.plan(s)

    def test_json_depth_preflight_respects_strings_and_escapes(self):
        value = {"x": "[" * 100 + '\"' + "\\" + "}" * 100}
        self.assertEqual(p.parse_json(json.dumps(value)), value)
        self.assertIsInstance(p.parse_json("[" * 32 + "]" * 32), list)
        with self.assertRaises(p.InputError):
            p.parse_json("[" * 33 + "]" * 33)

    def test_integer_digit_limit_is_independent_of_runtime(self):
        self.assertEqual(p.parse_json("9" * 32), int("9" * 32))
        for bad in ("9" * 33, "9" * 5000, "-" + "9" * 33):
            with self.assertRaises(p.InputError):
                p.parse_json(bad)

    def test_checked_in_example_has_documented_batch(self):
        raw = read_document(str(Path(__file__).with_name("example.synthetic.json")))
        result = p.plan(raw)
        self.assertEqual(result["batch"]["net_minor"], 36100)
        self.assertEqual(result["batch"]["work_units"], 400)
        self.assertEqual(result["batch"]["minutes"], 165)
        self.assertEqual(result["batch"]["job_count"], 4)
        self.assertTrue(result["search"]["complete"])
        self.assertTrue(p.verify(raw, result)["matches"])

    def test_enum_types_rejected_before_comparison(self):
        for key in ("availability", "valuation_basis"):
            for bad in (True, [], {}, 0):
                s = scenario()
                s["jobs"][0][key] = bad
                with self.assertRaises(p.InputError):
                    p.plan(s)

    def test_duplicate_json_nonfinite_and_recursion_are_controlled(self):
        for bad in ('{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}', "[" * 5_000 + "]" * 5_000,
                    '"\ud800"', "{" ):
            with self.subTest(value=bad[:30]), self.assertRaises(p.InputError):
                p.parse_json(bad)

    def test_oversize_json_and_non_text(self):
        for value in (" " * (p.MAX_DOCUMENT_BYTES + 1), None, b"{}"):
            with self.assertRaises(p.InputError):
                p.parse_json(value)


class CliTests(unittest.TestCase):
    def command(self, *args: str, data: bytes | None = None) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, "-m", "tools.costed_work_batch", *args],
                              cwd=ROOT, input=data, capture_output=True, timeout=15)

    def test_cli_plan_text_and_replay(self):
        raw = p.canonical_json(scenario()).encode()
        result = self.command("plan", "-", data=raw)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        text = self.command("plan", "-", "--format", "text", data=raw)
        self.assertEqual(text.returncode, 0, text.stderr)
        self.assertIn(b"WHAT-IF ONLY", text.stdout)
        with tempfile.TemporaryDirectory() as tmp:
            source, output = Path(tmp) / "scenario.json", Path(tmp) / "report.json"
            source.write_bytes(raw)
            output.write_bytes(result.stdout)
            verified = self.command("verify", str(source), str(output))
            self.assertEqual(verified.returncode, 0, verified.stderr)
            self.assertTrue(json.loads(verified.stdout)["matches"])
            report["authority"]["task_claimed"] = True
            output.write_text(json.dumps(report))
            rejected = self.command("verify", str(source), str(output))
            self.assertEqual(rejected.returncode, 2)
            self.assertEqual(rejected.stdout, b"")

    def test_cli_missing_file_and_bad_json_are_controlled(self):
        r = self.command("plan", "/does-not-exist-q7b4.json")
        self.assertEqual(r.returncode, 2)
        self.assertNotIn(b"Traceback", r.stderr)
        r = self.command("plan", "-", data=b"{bad}")
        self.assertEqual(r.returncode, 2)
        self.assertEqual(r.stdout, b"")

    def test_cli_both_stdin_rejected(self):
        r = self.command("verify", "-", "-", data=b"{}")
        self.assertEqual(r.returncode, 2)

    def test_reader_refuses_directory_fifo_and_supported_final_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            with self.assertRaises(p.InputError):
                read_document(str(path))
            if hasattr(os, "mkfifo"):
                fifo = path / "fifo"
                os.mkfifo(fifo)
                with self.assertRaises(p.InputError):
                    read_document(str(fifo))
            if hasattr(os, "O_NOFOLLOW"):
                target = path / "scenario.json"
                target.write_text(p.canonical_json(scenario()))
                link = path / "link"
                link.symlink_to(target)
                with self.assertRaises(OSError):
                    read_document(str(link))

    def test_reader_rejects_invalid_utf8_and_oversize(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            for raw in (b"\xff", b" " * (p.MAX_DOCUMENT_BYTES + 1)):
                path.write_bytes(raw)
                with self.assertRaises(p.InputError):
                    read_document(str(path))

    def test_normal_and_optimized_cli_bytes_match(self):
        raw = p.canonical_json(generated(61)).encode()
        ordinary = self.command("plan", "-", data=raw)
        optimized = subprocess.run([sys.executable, "-O", "-m", "tools.costed_work_batch", "plan", "-"],
            cwd=ROOT, input=raw, capture_output=True, timeout=15)
        self.assertEqual(ordinary.returncode, 0)
        self.assertEqual(optimized.returncode, 0, optimized.stderr)
        self.assertEqual(ordinary.stdout, optimized.stdout)


if __name__ == "__main__":
    unittest.main()
