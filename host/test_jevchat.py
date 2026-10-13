#!/usr/bin/env python3
"""host/test_jevchat.py — offline acceptance matrix for JEVCHAT.

Mocks jev.systemone; no network, no key required. Covers the order's
offline matrix: alphabet stability/reversibility, one-symbol-per-call,
EOS termination, fail-closed bad choices, distinct stop reasons, unicode
prompts, trace integrity, deterministic Hello! render, loopback demo.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jev  # noqa: E402
import jevchat  # noqa: E402


class FakeSystemOne:
    """Scripted stand-in for jev.systemone. Records states."""

    def __init__(self, ids, confidences=None, error=None):
        self.ids = list(ids)
        self.confidences = list(confidences or [])
        self.error = error
        self.states = []
        self.calls = 0

    def __call__(self, state, questions, model=jev.DEFAULT_MODEL, timeout=60):
        self.calls += 1
        self.states.append(state)
        if self.error is not None:
            raise self.error
        idx = min(self.calls - 1, len(self.ids) - 1)
        choice = self.ids[idx]
        conf = (self.confidences[idx] if idx < len(self.confidences) else 0.9)
        return {
            "model": model,
            "answers": {jevchat.QUESTION_KEY: {
                "type": "choice", "choice": choice,
                "probabilities": {choice: conf}, "confidence": conf}},
            "usage": {"input_tokens": 100 + self.calls, "output_tokens": 1},
        }


def ids_for(text, alphabet=None):
    alpha = alphabet or jevchat.Alphabet()
    return [alpha.encode(ch) for ch in text]


class AlphabetTests(unittest.TestCase):
    def test_stable_unique_reversible(self):
        alpha = jevchat.Alphabet()
        for sym in ("A", " ", "\n", "\t", "!", "\\", '"', "~", "0", "z"):
            sid = alpha.encode(sym)
            self.assertIsNotNone(sid, sym)
            decoded, is_eos = alpha.decode(sid)
            self.assertEqual(decoded, sym)
            self.assertFalse(is_eos)
        ids = [e[0] for e in alpha.entries]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertLess(len(alpha.entries), 255)
        decoded, is_eos = alpha.decode(jevchat.EOS_ID)
        self.assertTrue(is_eos)
        self.assertIsNone(decoded)

    def test_ids_are_safe_keys(self):
        alpha = jevchat.Alphabet()
        for sid, _, desc in alpha.entries:
            self.assertRegex(sid, jev.QUESTION_KEY_RE)
            self.assertTrue(desc)
        for version in ("char-v1", "chunk-v1"):
            a = jevchat.Alphabet(version)
            self.assertLess(len(a.entries), 255)

    def test_unknown_album_fails(self):
        with self.assertRaises(ValueError):
            jevchat.Alphabet("nope-v9")


class GenerateTests(unittest.TestCase):
    def test_hello_deterministic(self):
        fake = FakeSystemOne(ids_for("Hello!") + [jevchat.EOS_ID])
        emitted = []
        with tempfile.TemporaryDirectory() as td:
            trace = os.path.join(td, "t.jsonl")
            result = jevchat.generate(
                "say hi", trace_path=trace, systemone=fake,
                on_symbol=emitted.append)
            with open(trace, encoding="utf-8") as fh:
                rows = [json.loads(l) for l in fh]
        self.assertEqual(result["text"], "Hello!")
        self.assertEqual(result["stop_reason"], "EOS_EMITTED")
        self.assertEqual("".join(emitted), "Hello!")
        step_rows = [r for r in rows if r["type"] == "step"]
        self.assertEqual(len(step_rows), 7)  # 6 symbols + eos row
        self.assertEqual(rows[-1]["type"], "summary")
        self.assertEqual(rows[-1]["chars"], 6)

    def test_eos_first_appends_nothing(self):
        fake = FakeSystemOne([jevchat.EOS_ID])
        result = jevchat.generate("x", systemone=fake)
        self.assertEqual(result["text"], "")
        self.assertEqual(result["stop_reason"], "EOS_EMITTED")
        self.assertEqual(fake.calls, 1)

    def test_bad_choice_fails_closed(self):
        fake = FakeSystemOne(["zzz_no_such_id"])
        emitted = []
        result = jevchat.generate("x", systemone=fake, on_symbol=emitted.append)
        self.assertEqual(result["stop_reason"], "BAD_CHOICE")
        self.assertEqual(result["text"], "")
        self.assertEqual(emitted, [])

    def test_stop_reasons_distinct(self):
        for code in ("NO_KEY", "HTTP_500", "TRANSPORT", "BAD_REPLY"):
            fake = FakeSystemOne([], error=jev.JevError(code))
            result = jevchat.generate("x", systemone=fake)
            self.assertEqual(result["stop_reason"], code, code)

    def test_confidence_floor(self):
        fake = FakeSystemOne(ids_for("ab") + [jevchat.EOS_ID],
                             confidences=[0.9, 0.1, 0.9])
        result = jevchat.generate("x", systemone=fake, confidence_floor=0.5)
        self.assertEqual(result["stop_reason"], "CONFIDENCE_FLOOR")
        self.assertEqual(result["text"], "a")

    def test_max_chars(self):
        fake = FakeSystemOne(ids_for("x" * 50))
        result = jevchat.generate("x", systemone=fake, max_chars=5)
        self.assertEqual(result["stop_reason"], "MAX_CHARS")
        self.assertEqual(result["text"], "xxxxx")

    def test_state_too_large(self):
        fake = FakeSystemOne(ids_for("x"))
        big = "y" * (jev.MAX_STATE_BYTES)
        result = jevchat.generate(big, systemone=fake)
        self.assertEqual(result["stop_reason"], "STATE_TOO_LARGE")
        self.assertEqual(fake.calls, 0)

    def test_unicode_prompt_byte_exact(self):
        fake = FakeSystemOne([jevchat.EOS_ID])
        prompt = "héllo ✓ 中文 — émoji 🚀"
        jevchat.generate(prompt, systemone=fake)
        self.assertIn(prompt, fake.states[0])
        self.assertEqual(
            fake.states[0],
            jevchat.build_state(prompt, ""),
        )

    def test_state_hash_changes_with_prefix(self):
        fake = FakeSystemOne(ids_for("ab") + [jevchat.EOS_ID])
        with tempfile.TemporaryDirectory() as td:
            trace = os.path.join(td, "t.jsonl")
            jevchat.generate("p", trace_path=trace, systemone=fake)
            with open(trace, encoding="utf-8") as fh:
                rows = [json.loads(l) for l in fh]
        hashes = [r["state_sha256"] for r in rows if r["type"] == "step"]
        self.assertEqual(len(hashes), len(set(hashes)))

    def test_trace_has_no_key_material(self):
        fake = FakeSystemOne(ids_for("hi") + [jevchat.EOS_ID])
        with tempfile.TemporaryDirectory() as td:
            trace = os.path.join(td, "t.jsonl")
            jevchat.generate("p", trace_path=trace, systemone=fake)
            with open(trace, "rb") as fh:
                blob = fh.read()
        for leaked in (b"Bearer", b"Authorization", b"TYPESAFE_API_KEY",
                       b"xoxb-", b"tsk-"):
            self.assertNotIn(leaked, blob)

    def test_summary_prompt_hash_not_text(self):
        fake = FakeSystemOne([jevchat.EOS_ID])
        with tempfile.TemporaryDirectory() as td:
            trace = os.path.join(td, "t.jsonl")
            jevchat.generate("secret prompt", trace_path=trace,
                             systemone=fake)
            with open(trace, encoding="utf-8") as fh:
                blob = fh.read()
        self.assertNotIn("secret prompt", blob)
        self.assertIn("prompt_sha256", blob)


class DemoTests(unittest.TestCase):
    def test_demo_binds_loopback_only(self):
        import jevchat_demo
        with self.assertRaises(ValueError):
            jevchat_demo.serve(host="0.0.0.0", port=0, dry=True)
        with self.assertRaises(ValueError):
            jevchat_demo.serve(host="example.com", port=0, dry=True)

    def test_demo_page_escapes_text(self):
        import jevchat_demo
        self.assertIn("textContent", jevchat_demo.PAGE)
        self.assertNotIn("innerHTML", jevchat_demo.PAGE)


if __name__ == "__main__":
    unittest.main()
