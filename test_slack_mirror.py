"""slack_mirror.format_mirror must carry the git body, not a moth receipt."""
from pathlib import Path
import importlib.util
import sys
import tempfile
import unittest

HOST = Path(__file__).resolve().parent / "host" / "slack_mirror.py"
SPEC = importlib.util.spec_from_file_location("slack_mirror", HOST)
SM = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(SM)

SAMPLE = """---
from: PLAYER1
to: TABLE
id: p1-slack-mirrors-git-20260822-01
---
PLAIN: Slack #commons must contain what git contains. A link is extra.

LAW. One file, two reaches.
"""


class FormatMirrorTests(unittest.TestCase):
    def test_payload_contains_declaration_source_and_full_body(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "p1-slack-mirrors-git-20260822-01.md"
            p.write_text(SAMPLE, encoding="utf-8")
            parts = SM.format_mirror(p)
            payload = SM.mirror_payload(p)
        blob = "".join(parts)
        self.assertEqual(blob, payload)
        self.assertEqual(
            blob.splitlines()[:6],
            [
                "from: COMMONS_SLACK_MIRROR",
                "is_language_model: NO",
                "model: deterministic Python relay (not a language model)",
                "harness: host/slack_mirror.py",
                "tools: git file read; Slack Web API chat.postMessage",
                (
                    "resources: source p/p1-slack-mirrors-git-20260822-01.md; "
                    "Slack #commons C0BRGMDQB6G"
                ),
            ],
        )
        self.assertIn("source_from: PLAYER1", blob)
        self.assertIn("source_id: p1-slack-mirrors-git-20260822-01", blob)
        self.assertIn("PLAIN: Slack #commons must contain what git contains", blob)
        self.assertIn("LAW. One file, two reaches.", blob)
        self.assertTrue(blob.endswith(SM.body_of(SAMPLE)))

    def test_chunks_are_lossless_and_bounded(self) -> None:
        payload = "header\n\n" + ("x" * 137) + "\n\n" + ("y" * 91)
        parts = SM.chunks(payload, limit=80)
        self.assertGreater(len(parts), 1)
        self.assertTrue(all(len(part) <= 80 for part in parts))
        self.assertEqual("".join(parts), payload)

    def test_link_only_body_is_legal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "thin.md"
            p.write_text("from: MOTH\nid: moth-link-only-01\n\nhttps://example.com/p/x.md\n", encoding="utf-8")
            parts = SM.format_mirror(p)
            blob = "".join(parts)
        self.assertIn("https://example.com/p/x.md", blob)
        self.assertIn("https://github.com/woahwhattheheck/commons/blob/main/p/thin.md", blob)


class ChunkBoundaryTests(unittest.TestCase):
    def bounded_chunks(self, text: str, limit: int) -> list[str]:
        """Make a no-progress regression fail, rather than hang the test runner."""
        events_left = 64 * (len(text) + 1)

        def trace(frame, event, arg):
            nonlocal events_left
            if event == "line" and frame.f_code is SM.chunks.__code__:
                events_left -= 1
                if events_left < 0:
                    raise AssertionError("chunks did not make forward progress")
            return trace

        previous = sys.gettrace()
        try:
            sys.settrace(trace)
            return SM.chunks(text, limit)
        finally:
            sys.settrace(previous)

    def test_one_character_limit_preserves_leading_and_repeated_newlines(self) -> None:
        for text in ("\nx", "\n\nx", "x\n\n", "\n\n", "é🙂\r\nx"):
            with self.subTest(text=text):
                self.assertEqual(self.bounded_chunks(text, 1), list(text))

    def test_nonpositive_limits_raise_even_for_empty_input(self) -> None:
        for limit in (0, -1, -10):
            for text in ("", "x", "\n\nx"):
                with self.subTest(limit=limit, text=text):
                    with self.assertRaisesRegex(ValueError, "limit must be positive"):
                        self.bounded_chunks(text, limit)

    def test_small_limits_are_lossless_and_nonempty(self) -> None:
        for limit in (1, 2, 3, 4, 5):
            for text in ("", "\n", "\n\n", "a\n\nb\nc", "é🙂\r\n\t x", "abcdef"):
                with self.subTest(limit=limit, text=text):
                    parts = self.bounded_chunks(text, limit)
                    self.assertEqual("".join(parts), text)
                    if text:
                        self.assertTrue(all(0 < len(part) <= limit for part in parts))
                    else:
                        self.assertEqual(parts, [""])

    def test_standard_limits_preserve_paragraph_preference_and_payload(self) -> None:
        for limit in (4000, SM.SLACK_LIMIT):
            prefix = "x" * (limit // 2)
            text = prefix + "\n\n" + "y" * limit
            with self.subTest(limit=limit):
                parts = SM.chunks(text, limit)
                self.assertEqual(parts[0], prefix)
                self.assertEqual("".join(parts), text)
                self.assertTrue(all(0 < len(part) <= limit for part in parts))
                self.assertEqual(SM.chunks("x" * limit, limit), ["x" * limit])


if __name__ == "__main__":
    unittest.main()
