from __future__ import annotations

import contextlib
import io
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
    verify_result,
)

EXAMPLES = Path(__file__).parents[1] / "examples"


def _packet() -> dict:
    return loads_strict(
        (EXAMPLES / "fictional_partner_packet.json").read_text(encoding="utf-8")
    )


def _bundle() -> dict:
    return loads_strict(
        (EXAMPLES / "fictional_evidence_bundle.json").read_text(encoding="utf-8")
    )


class PublicBoundaryRecoveryTests(unittest.TestCase):
    def test_missing_bundle_cannot_mint_ready_or_verify_true(self):
        packet = _packet()
        result = compile_packet(packet, None)
        self.assertEqual(result["packet_state"], "INCOMPLETE_EVIDENCE")
        self.assertFalse(verify_result(packet, result, None))
        bundle = _bundle()
        ready = compile_packet(packet, bundle)
        self.assertEqual(ready["packet_state"], "PACKET_REVIEW_READY")
        self.assertTrue(verify_result(packet, ready, bundle))
        self.assertFalse(verify_result(packet, ready, None))

    def test_arbitrary_result_cannot_use_legacy_renderer(self):
        fabricated = {
            "packet_state": "PACKET_REVIEW_READY",
            "external_submission_state": "SUBMITTED",
            "dce": {"currentness": "CURRENT"},
            "rubric": {"retained_evidence_coverage_points": 100},
            "evidence_bundle": {"root_sha256": "f" * 64},
            "categories": [],
            "evidence_authority_queue": [],
            "translation_queue": [],
            "owner_actions": [],
            "disclaimer": "fabricated",
        }
        with self.assertRaisesRegex(ValidationError, "unbound result"):
            render_markdown(fabricated)

    def test_tampered_result_cannot_render_in_either_api(self):
        packet, bundle = _packet(), _bundle()
        result = compile_packet(packet, bundle)
        result["external_submission_state"] = "SUBMITTED"
        with self.assertRaisesRegex(ValidationError, "tampered result"):
            render_markdown(result)
        with self.assertRaisesRegex(ValidationError, "verification failed"):
            render_markdown(packet, result, bundle)

    def test_missing_receipt_cannot_render(self):
        packet, bundle = _packet(), _bundle()
        result = compile_packet(packet, bundle)
        result.pop("receipt")
        with self.assertRaisesRegex(ValidationError, "verification failed"):
            render_markdown(packet, result, bundle)

    def test_dynamic_markdown_metacharacters_are_neutralized(self):
        packet, bundle = _packet(), _bundle()
        packet["evidence"][-1]["id"] = (
            "evil`](https://example.invalid) **READY** | # injected"
        )
        result = compile_packet(packet, bundle)
        rendered = render_markdown(packet, result, bundle)
        self.assertNotIn("](https://example.invalid)", rendered)
        self.assertNotIn("**READY**", rendered)
        self.assertNotIn("| # injected", rendered)
        self.assertIn("&#96;", rendered)
        self.assertIn("&#124;", rendered)

    def test_lone_surrogate_is_rejected_before_hashing(self):
        with self.assertRaisesRegex(ValidationError, "non-scalar Unicode surrogate"):
            loads_strict('"\\ud800"')
        with self.assertRaisesRegex(ValidationError, "non-scalar Unicode surrogate"):
            canonical_json({"x": "\ud800"})

    def test_control_character_is_rejected(self):
        with self.assertRaisesRegex(ValidationError, "disallowed control"):
            loads_strict('"\\u0000"')

    def test_deep_json_is_controlled_failure(self):
        hostile = "[" * 2500 + "0" + "]" * 2500
        with self.assertRaisesRegex(
            ValidationError, "strict JSON parse failed|nesting limit"
        ):
            loads_strict(hostile)

    def test_oversized_integer_is_controlled_failure(self):
        hostile = '{"x":' + ("9" * 6000) + "}"
        with self.assertRaisesRegex(
            ValidationError, "strict JSON parse failed|integer exceeds"
        ):
            loads_strict(hostile)

    def test_malformed_json_is_controlled_failure(self):
        with self.assertRaisesRegex(ValidationError, "strict JSON parse failed"):
            loads_strict('{"x":')

    def test_cli_malformed_json_is_traceback_free(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            packet_path = root / "packet.json"
            packet_path.write_text('{"x":', encoding="utf-8")
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                rc = cli.main(
                    [
                        str(packet_path),
                        "--evidence-bundle",
                        str(EXAMPLES / "fictional_evidence_bundle.json"),
                    ]
                )
            self.assertEqual(rc, 2)
            self.assertIn("numih error:", stderr.getvalue())
            self.assertNotIn("Traceback", stderr.getvalue())

    def test_cli_output_collision_is_controlled_and_preserves_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "result.json"
            output.write_text("foreign-successor", encoding="utf-8")
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                rc = cli.main(
                    [
                        str(EXAMPLES / "fictional_partner_packet.json"),
                        "--evidence-bundle",
                        str(EXAMPLES / "fictional_evidence_bundle.json"),
                        "--json-out",
                        str(output),
                    ]
                )
            self.assertEqual(rc, 2)
            self.assertIn("numih error:", stderr.getvalue())
            self.assertNotIn("Traceback", stderr.getvalue())
            self.assertEqual(
                output.read_text(encoding="utf-8"),
                "foreign-successor",
            )

    def test_current_readiness_guard_is_clean_on_product_python(self):
        from tools.current_readiness_guard.guard import scan_paths

        findings = scan_paths(
            [
                "revenue/numih_ai_sad_admission_readiness/_compiler_core.py",
                "revenue/numih_ai_sad_admission_readiness/compiler.py",
                "revenue/numih_ai_sad_admission_readiness/cli.py",
                "revenue/numih_ai_sad_admission_readiness/__init__.py",
            ]
        )
        self.assertEqual(findings, [])


if __name__ == "__main__":
    unittest.main()
