#!/usr/bin/env python3

from __future__ import annotations

import json
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from returned_action_diff import (  # noqa: E402
    Operand,
    StateMismatchError,
    build_report,
    canonical_json_bytes,
    capture_pair,
    semantic_diff,
    unwrap_action,
    validate_state_hashes,
)


class ReturnedActionDiffTests(unittest.TestCase):
    def test_unwraps_nested_api_gateway_body(self) -> None:
        expected = {"orders": [{"market_id": "M1", "price": 7}]}
        raw = {
            "statusCode": 200,
            "headers": {"content-type": "application/json"},
            "body": json.dumps({"result": {"action": expected}}),
        }

        action, path = unwrap_action(raw)

        self.assertEqual(expected, action)
        self.assertEqual(("body", "result", "action"), path)

    def test_scalar_action_field_is_not_mistaken_for_wrapper(self) -> None:
        raw = {"action": "SELL", "market": "M1", "amount": 2}
        action, path = unwrap_action(raw)
        self.assertEqual(raw, action)
        self.assertEqual((), path)

    def test_keyed_list_alignment_ignores_reordering(self) -> None:
        left = {
            "orders": [
                {"market_id": "B", "price": 4, "amount": 2},
                {"market_id": "A", "price": 7, "amount": 1},
            ]
        }
        right = {
            "orders": [
                {"market_id": "A", "price": 8, "amount": 1},
                {"market_id": "B", "price": 4, "amount": 2},
            ]
        }

        differences = semantic_diff(left, right)

        self.assertEqual(1, len(differences))
        self.assertEqual('$.orders[market_id="A"].price', differences[0].path)
        self.assertEqual("number", differences[0].kind)
        self.assertEqual(1, differences[0].absolute_delta)

    def test_composite_identity_aligns_same_market_multiple_products(self) -> None:
        left = {
            "offers": [
                {"market": "M1", "product": "wheat", "delivery": 5, "price": 2},
                {"market": "M1", "product": "corn", "delivery": 5, "price": 3},
            ]
        }
        right = {
            "offers": [
                {"market": "M1", "product": "corn", "delivery": 5, "price": 4},
                {"market": "M1", "product": "wheat", "delivery": 5, "price": 2},
            ]
        }
        differences = semantic_diff(left, right)
        self.assertEqual(1, len(differences))
        self.assertIn('market="M1",product="corn",delivery=5', differences[0].path)

    def test_numeric_tolerances_and_delta(self) -> None:
        self.assertEqual([], semantic_diff({"score": 1.0}, {"score": 1.00001}, abs_tol=0.001))
        differences = semantic_diff({"score": 10.0}, {"score": 12.0}, rel_tol=0.01)
        self.assertEqual(1, len(differences))
        self.assertEqual(2.0, differences[0].absolute_delta)
        self.assertAlmostEqual(1.0 / 6.0, differences[0].relative_delta)

    def test_state_hash_mismatch_is_refused(self) -> None:
        left = Operand(name="v1", action={}, source="left", state_sha256="a" * 64)
        right = Operand(name="v2", action={}, source="right", state_sha256="b" * 64)
        with self.assertRaises(StateMismatchError):
            validate_state_hashes(left, right)
        result = validate_state_hashes(left, right, allow_state_mismatch=True)
        self.assertEqual("mismatch", result["proof"])

    def test_report_finds_first_divergent_field(self) -> None:
        state_hash = "c" * 64
        left = Operand(name="v1", action={"cash": 10, "orders": []}, source="left", state_sha256=state_hash)
        right = Operand(name="v2", action={"cash": -10, "orders": []}, source="right", state_sha256=state_hash)
        report = build_report(left, right)
        self.assertEqual("$.cash", report["summary"]["first_difference"]["path"])
        self.assertEqual(1, report["summary"]["difference_count"])


class EndpointCaptureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.received: list[tuple[str, bytes]] = []
        received = self.received

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers["Content-Length"])
                body = self.rfile.read(length)
                received.append((self.path, body))
                value = 1 if self.path == "/left" else 2
                payload = json.dumps({"body": json.dumps({"action": {"cash": value}})}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, format: str, *args: object) -> None:
                return

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def test_identical_canonical_request_bytes_and_repeat_stability(self) -> None:
        host, port = self.server.server_address
        state = {"z": [3, 2, 1], "a": {"cash": 9}}

        left, right = capture_pair(
            state=state,
            left_url=f"http://{host}:{port}/left",
            right_url=f"http://{host}:{port}/right",
            left_name="v1",
            right_name="v2",
            repeat=2,
        )

        expected = canonical_json_bytes(state)
        self.assertEqual(4, len(self.received))
        self.assertTrue(all(body == expected for _, body in self.received))
        self.assertEqual(left["request_sha256"], right["request_sha256"])
        self.assertEqual(left["state_sha256"], right["state_sha256"])
        self.assertTrue(left["deterministic"])
        self.assertTrue(right["deterministic"])
        self.assertEqual(1, left["unique_action_count"])
        self.assertEqual(1, right["unique_action_count"])
        self.assertNotEqual(left["action_sha256"], right["action_sha256"])


if __name__ == "__main__":
    unittest.main()
