#!/usr/bin/env python3
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from workbench import (  # noqa: E402
    LedgerError,
    evaluate_ledger,
    load_strict_json,
    main,
    publish,
)


SCHEMA = "crowdstrike-aoc-manual-ledger-v1"


def attempt(**kwargs):
    base = {
        "attempt_id": "a1",
        "puzzle_id": "basilisk-1",
        "prompt_text": "please solve this puzzle",
        "observed_token_count": 40,
        "outcome": "success",
        "entry_mode": "manual",
        "declared_actions": ["human_paste"],
    }
    base.update(kwargs)
    return base


def ledger(*attempts):
    return {"schema": SCHEMA, "attempts": list(attempts)}


class _PostCreateFailure:
    """Proxy a real exclusive file while injecting failure after creation."""

    def __init__(self, wrapped, *, fail_write=False, fail_close=False):
        self._wrapped = wrapped
        self._fail_write = fail_write
        self._fail_close = fail_close

    def __enter__(self):
        self._wrapped.__enter__()
        return self

    def __exit__(self, exc_type, exc, tb):
        result = self._wrapped.__exit__(exc_type, exc, tb)
        if exc_type is None and self._fail_close:
            raise OSError("synthetic close failure")
        return result

    def write(self, text):
        if self._fail_write:
            self._wrapped.write(text[: max(1, len(text) // 8)])
            self._wrapped.flush()
            raise OSError("synthetic write failure")
        return self._wrapped.write(text)


class WorkbenchTests(unittest.TestCase):
    def test_duplicate_json_keys_rejected(self):
        raw = '{"schema":"x","schema":"y"}'
        with self.assertRaises(LedgerError):
            load_strict_json(raw)

    def test_nonfinite_json_constants_rejected(self):
        for raw in ('{"x":NaN}', '{"x":Infinity}', '{"x":-Infinity}'):
            with self.subTest(raw=raw), self.assertRaises(LedgerError):
                load_strict_json(raw)

    def test_invalid_json_is_ledger_error(self):
        with self.assertRaises(LedgerError):
            load_strict_json('{"x":')

    def test_malformed_token_count_rejected(self):
        for bad in (True, 3.5, "12", -1):
            with self.assertRaises(LedgerError):
                evaluate_ledger(ledger(attempt(observed_token_count=bad)))

    def test_identity_and_text_types_are_not_coerced(self):
        cases = (
            {"attempt_id": 7},
            {"puzzle_id": ["basilisk"]},
            {"prompt_text": {"prompt": "x"}},
            {"notes": 123},
            {"outcome": ["success"]},
            {"entry_mode": True},
        )
        for kwargs in cases:
            with self.subTest(kwargs=kwargs), self.assertRaises(LedgerError):
                evaluate_ledger(ledger(attempt(**kwargs)))

    def test_declared_action_types_are_not_coerced_or_leaked(self):
        for actions in ([{}], [7], [None], "human_paste"):
            with self.subTest(actions=actions), self.assertRaises(LedgerError):
                evaluate_ledger(ledger(attempt(declared_actions=actions)))

    def test_unknown_attempt_and_ledger_fields_are_rejected(self):
        row = attempt(extra="not-bound")
        with self.assertRaises(LedgerError):
            evaluate_ledger(ledger(row))
        top = ledger(attempt())
        top["extra"] = "not-bound"
        with self.assertRaises(LedgerError):
            evaluate_ledger(top)

    def test_prohibited_automation_flag_rejected(self):
        with self.assertRaises(LedgerError):
            evaluate_ledger(
                ledger(attempt(declared_actions=["bot_live_interaction"]))
            )

    def test_prohibited_text_rejected(self):
        with self.assertRaises(LedgerError):
            evaluate_ledger(
                ledger(attempt(notes="used network interception on scoring"))
            )

    def test_frontier_uses_operator_token_counts_only(self):
        result = evaluate_ledger(
            ledger(
                attempt(attempt_id="a", observed_token_count=90, outcome="success"),
                attempt(attempt_id="b", observed_token_count=30, outcome="success"),
                attempt(attempt_id="c", observed_token_count=10, outcome="failure"),
            )
        )
        front = result["frontiers"][0]
        self.assertEqual(front["best_observed_token_count"], 30)
        self.assertEqual(front["best_attempt_ids"], ["b"])
        self.assertEqual(front["successful_count"], 2)
        by_id = {a["attempt_id"]: a for a in result["attempts"]}
        self.assertEqual(by_id["a"]["delta_from_best"], 60)
        self.assertIsNone(by_id["c"]["delta_from_best"])

    def test_duplicate_prompt_detection(self):
        result = evaluate_ledger(
            ledger(
                attempt(attempt_id="x", prompt_text="hello   world"),
                attempt(attempt_id="y", prompt_text="hello world"),
            )
        )
        groups = result["frontiers"][0]["duplicate_prompt_groups"]
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["attempt_ids"], ["x", "y"])

    def test_order_invariance_of_receipt(self):
        a = attempt(attempt_id="p1", puzzle_id="p", observed_token_count=11)
        b = attempt(attempt_id="p2", puzzle_id="p", observed_token_count=22)
        r1 = evaluate_ledger(ledger(a, b))
        r2 = evaluate_ledger(ledger(b, a))
        self.assertEqual(r1["receipt"]["receipt_sha256"], r2["receipt"]["receipt_sha256"])
        self.assertEqual(r1["receipt"]["normalized_ledger_sha256"], r2["receipt"]["normalized_ledger_sha256"])
        self.assertEqual(r1["frontiers"], r2["frontiers"])
        self.assertEqual(r1["attempts"], r2["attempts"])

    def test_receipt_binds_non_frontier_evidence(self):
        one = evaluate_ledger(
            ledger(
                attempt(attempt_id="best", observed_token_count=10),
                attempt(
                    attempt_id="failed",
                    outcome="failure",
                    observed_token_count=5,
                    prompt_text="failed evidence one",
                    notes="manual note one",
                ),
            )
        )
        two = evaluate_ledger(
            ledger(
                attempt(attempt_id="best", observed_token_count=10),
                attempt(
                    attempt_id="failed",
                    outcome="failure",
                    observed_token_count=5,
                    prompt_text="failed evidence two",
                    notes="manual note two",
                ),
            )
        )
        self.assertEqual(one["frontiers"], two["frontiers"])
        self.assertNotEqual(
            one["receipt"]["normalized_ledger_sha256"],
            two["receipt"]["normalized_ledger_sha256"],
        )
        self.assertNotEqual(
            one["receipt"]["receipt_sha256"],
            two["receipt"]["receipt_sha256"],
        )

    def test_receipt_recompute_detects_tamper(self):
        result = evaluate_ledger(ledger(attempt()))
        digest = result["receipt"]["receipt_sha256"]
        from workbench import build_receipt

        tampered = [dict(result["frontiers"][0], best_observed_token_count=1)]
        rebuilt = build_receipt({"attempts": result["attempts"]}, tampered)
        self.assertNotEqual(digest, rebuilt["receipt_sha256"])
        self.assertEqual(result["receipt"]["compliance_kind"], "SELF_ATTESTED_ONLY")
        self.assertFalse(result["receipt"]["eligibility_certificate"])

    def test_distinct_puzzles_have_distinct_frontiers(self):
        result = evaluate_ledger(
            ledger(
                attempt(attempt_id="1", puzzle_id="A", observed_token_count=5),
                attempt(attempt_id="2", puzzle_id="B", observed_token_count=9),
            )
        )
        self.assertEqual([f["puzzle_id"] for f in result["frontiers"]], ["A", "B"])
        self.assertEqual(result["frontiers"][0]["best_observed_token_count"], 5)
        self.assertEqual(result["frontiers"][1]["best_observed_token_count"], 9)

    def test_create_exclusive_publish(self):
        result = evaluate_ledger(ledger(attempt()))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            js = root / "out.json"
            md = root / "out.md"
            publish(result, js, md)
            self.assertTrue(js.exists())
            self.assertIn("SELF_ATTESTED_ONLY", md.read_text(encoding="utf-8"))
            self.assertIn("normalized_ledger_sha256", md.read_text(encoding="utf-8"))
            with self.assertRaises(LedgerError):
                publish(result, js, md)

    def test_publish_rejects_same_target_without_writing(self):
        result = evaluate_ledger(ledger(attempt()))
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "same"
            with self.assertRaises(LedgerError):
                publish(result, target, target)
            self.assertFalse(target.exists())

    def test_publish_rolls_back_first_file_when_second_open_fails(self):
        result = evaluate_ledger(ledger(attempt()))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            js = root / "out.json"
            md = root / "out.md"
            real_open = Path.open

            def failing_open(path_self, *args, **kwargs):
                if path_self == md:
                    raise OSError("synthetic second-open failure")
                return real_open(path_self, *args, **kwargs)

            with mock.patch.object(Path, "open", new=failing_open):
                with self.assertRaises(LedgerError):
                    publish(result, js, md)
            self.assertFalse(js.exists())
            self.assertFalse(md.exists())

    def test_publish_rolls_back_partial_first_output_after_write_failure(self):
        result = evaluate_ledger(ledger(attempt()))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            js = root / "out.json"
            md = root / "out.md"
            real_open = Path.open

            def failing_open(path_self, *args, **kwargs):
                opened = real_open(path_self, *args, **kwargs)
                if path_self == js:
                    return _PostCreateFailure(opened, fail_write=True)
                return opened

            with mock.patch.object(Path, "open", new=failing_open):
                with self.assertRaises(LedgerError):
                    publish(result, js, md)
            self.assertFalse(js.exists())
            self.assertFalse(md.exists())

    def test_publish_rolls_back_both_outputs_after_second_close_failure(self):
        result = evaluate_ledger(ledger(attempt()))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            js = root / "out.json"
            md = root / "out.md"
            real_open = Path.open

            def failing_open(path_self, *args, **kwargs):
                opened = real_open(path_self, *args, **kwargs)
                if path_self == md:
                    return _PostCreateFailure(opened, fail_close=True)
                return opened

            with mock.patch.object(Path, "open", new=failing_open):
                with self.assertRaises(LedgerError):
                    publish(result, js, md)
            self.assertFalse(js.exists())
            self.assertFalse(md.exists())

    def test_cli_fixture(self):
        fixture = ROOT / "fixtures" / "sample_ledger.json"
        code = main([str(fixture)])
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
