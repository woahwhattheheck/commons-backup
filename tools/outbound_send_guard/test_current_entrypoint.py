from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tools.outbound_send_guard import cli, current


def stamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def fresh_sources() -> tuple[dict, dict]:
    now = datetime.now(timezone.utc)
    intent = {
        "schema_version": "outbound-send-intent/v1",
        "intent_id": "direct-current-1",
        "recipient": "buyer@example.com",
        "offer_id": "fixed-proof-001",
        "requested_at": stamp(now - timedelta(seconds=5)),
        "route_kind": "email",
    }
    evidence = {
        "schema_version": "outbound-send-evidence/v1",
        "generated_at": stamp(now - timedelta(seconds=10)),
        "mailbox": {"complete": True, "query_id": "mail-current", "messages": []},
        "slack": {"complete": True, "query_id": "slack-current", "events": []},
        "policy": {
            "cross_offer_cooldown_days": 30,
            "max_evidence_age_seconds": 900,
            "max_future_skew_seconds": 300,
        },
    }
    return intent, evidence


class DirectCurrentCliTests(unittest.TestCase):
    def test_imported_cli_main_is_not_authority_boundary(self):
        self.assertEqual(cli.main(["compile"]), 2)

    def test_nonisolated_direct_cli_rejects_before_inputs(self):
        root = Path(__file__).resolve().parents[2]
        script = root / "tools" / "outbound_send_guard" / "cli.py"
        proc = subprocess.run(
            [sys.executable, str(script), "compile"],
            cwd=root,
            text=True,
            capture_output=True,
            timeout=30,
        )
        self.assertEqual(proc.returncode, 2)
        self.assertIn("python -I -S", proc.stderr)

    def test_direct_isolated_cli_compile_verify_round_trip_normal_and_optimized(self):
        root = Path(__file__).resolve().parents[2]
        script = root / "tools" / "outbound_send_guard" / "cli.py"
        for optimized in (False, True):
            with self.subTest(optimized=optimized), tempfile.TemporaryDirectory() as td:
                directory = Path(td)
                intent, evidence = fresh_sources()
                ip = directory / "intent.json"
                ep = directory / "evidence.json"
                rp = directory / "receipt.json"
                vp = directory / "verification.json"
                ip.write_text(json.dumps(intent, sort_keys=True), encoding="utf-8")
                ep.write_text(json.dumps(evidence, sort_keys=True), encoding="utf-8")
                prefix = [sys.executable]
                if optimized:
                    prefix.append("-O")
                prefix.extend(["-I", "-S", str(script)])

                compiled = subprocess.run(
                    [*prefix, "compile", "--intent", str(ip), "--evidence", str(ep), "--out", str(rp)],
                    cwd=root,
                    text=True,
                    capture_output=True,
                    timeout=30,
                )
                self.assertEqual(compiled.returncode, 0, compiled.stderr or compiled.stdout)
                receipt = json.loads(rp.read_text(encoding="utf-8"))
                self.assertEqual(receipt["payload"]["mode"], current.MODE_CURRENT)
                self.assertEqual(receipt["payload"]["decision"], "ALLOW_NEW")
                self.assertTrue(receipt["payload"]["current_preflight_clear"])
                self.assertFalse(receipt["payload"]["side_effects_authorized"])

                verified = subprocess.run(
                    [*prefix, "verify", "--intent", str(ip), "--evidence", str(ep), "--receipt", str(rp), "--out", str(vp)],
                    cwd=root,
                    text=True,
                    capture_output=True,
                    timeout=30,
                )
                self.assertEqual(verified.returncode, 0, verified.stderr or verified.stdout)
                verification = json.loads(vp.read_text(encoding="utf-8"))
                self.assertTrue(verification["payload"]["current_preflight_valid"])
                self.assertFalse(verification["payload"]["side_effects_authorized"])

    def test_direct_cli_stale_matched_pair_holds(self):
        root = Path(__file__).resolve().parents[2]
        script = root / "tools" / "outbound_send_guard" / "cli.py"
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            ip = directory / "intent.json"
            ep = directory / "evidence.json"
            rp = directory / "receipt.json"
            intent, evidence = fresh_sources()
            intent["requested_at"] = "2025-01-01T00:00:10Z"
            evidence["generated_at"] = "2025-01-01T00:00:00Z"
            evidence["policy"]["max_evidence_age_seconds"] = 604800
            ip.write_text(json.dumps(intent, sort_keys=True), encoding="utf-8")
            ep.write_text(json.dumps(evidence, sort_keys=True), encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, "-I", "-S", str(script), "compile", "--intent", str(ip), "--evidence", str(ep), "--out", str(rp)],
                cwd=root,
                text=True,
                capture_output=True,
                timeout=30,
            )
            self.assertEqual(proc.returncode, 4, proc.stderr or proc.stdout)
            payload = json.loads(rp.read_text(encoding="utf-8"))["payload"]
            self.assertEqual(payload["historical_decision"], "ALLOW_NEW")
            self.assertEqual(payload["decision"], "HOLD")
            self.assertFalse(payload["current_preflight_clear"])


if __name__ == "__main__":
    unittest.main()
