from __future__ import annotations

import contextlib
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path

from revenue.numih_ai_sad_admission_readiness import cli
from revenue.numih_ai_sad_admission_readiness.compiler import (
    ValidationError,
    canonical_json,
    compile_packet,
    loads_strict,
    render_markdown,
)


EXAMPLES = Path(__file__).parents[1] / "examples"
FORMAT_CONTROLS = {
    "bidi_override": "\u202e",
    "bidi_isolate": "\u2066",
    "pop_directional_isolate": "\u2069",
    "zero_width_space": "\u200b",
    "zero_width_joiner": "\u200d",
}


def _packet() -> dict:
    return loads_strict(
        (EXAMPLES / "fictional_partner_packet.json").read_text(encoding="utf-8")
    )


def _bundle() -> dict:
    return loads_strict(
        (EXAMPLES / "fictional_evidence_bundle.json").read_text(encoding="utf-8")
    )


class _StrictUtf8Stderr(io.TextIOBase):
    def __init__(self) -> None:
        super().__init__()
        self._data = bytearray()

    def writable(self) -> bool:
        return True

    def write(self, text: str) -> int:
        encoded = text.encode("utf-8", errors="strict")
        self._data.extend(encoded)
        return len(text)

    def getvalue(self) -> str:
        return bytes(self._data).decode("utf-8", errors="strict")


class DuplicateSurrogateRecoveryTests(unittest.TestCase):
    HOSTILE = '{"\\ud800":1,"\\ud800":2}'

    def test_duplicate_surrogate_key_uses_fixed_scalar_safe_error(self) -> None:
        with self.assertRaisesRegex(ValidationError, r"^duplicate JSON key$"):
            loads_strict(self.HOSTILE)

    def test_cli_duplicate_surrogate_key_is_bounded_and_traceback_free(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            packet_path = root / "packet.json"
            bundle_path = root / "bundle.json"
            packet_path.write_text(self.HOSTILE, encoding="ascii")
            bundle_path.write_text("{}", encoding="ascii")
            stderr = _StrictUtf8Stderr()
            with contextlib.redirect_stderr(stderr):
                rc = cli.main(
                    [
                        str(packet_path),
                        "--evidence-bundle",
                        str(bundle_path),
                    ]
                )
            rendered = stderr.getvalue()
            self.assertEqual(rc, 2)
            self.assertEqual(rendered, "numih error: duplicate JSON key\n")
            self.assertLessEqual(len(rendered.encode("utf-8")), 128)
            self.assertNotIn("Traceback", rendered)
            self.assertNotIn("UnicodeEncodeError", rendered)

    def test_format_controls_fail_strict_parse_and_canonicalization(self) -> None:
        for name, character in FORMAT_CONTROLS.items():
            with self.subTest(name=name, boundary="loads_strict"):
                hostile = json.dumps({"value": character})
                with self.assertRaisesRegex(ValidationError, "format control"):
                    loads_strict(hostile)
            with self.subTest(name=name, boundary="canonical_json"):
                with self.assertRaisesRegex(ValidationError, "format control"):
                    canonical_json({"value": character})

    def test_format_controls_cannot_reach_markdown(self) -> None:
        packet = _packet()
        bundle = _bundle()
        for name, character in FORMAT_CONTROLS.items():
            with self.subTest(name=name):
                hostile = copy.deepcopy(packet)
                hostile["applicant"]["display_name"] += character + "spoof"
                with self.assertRaisesRegex(ValidationError, "format control"):
                    render_markdown(
                        hostile,
                        compile_packet(hostile, bundle),
                        bundle,
                    )


if __name__ == "__main__":
    unittest.main()
