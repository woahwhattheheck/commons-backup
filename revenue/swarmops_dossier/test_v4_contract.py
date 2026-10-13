"""Regression: public SwarmOps currentness stays v4 CURRENT / HISTORICAL_REPLAY."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
import copy

import revenue.swarmops_dossier as pkg
from revenue.swarmops_dossier.acceptance import fixture
from revenue.swarmops_dossier.cli import main as cli_main
from revenue.swarmops_dossier.engine import (
    DossierError,
    LEGACY_OUTPUT_SCHEMA,
    OUTPUT_SCHEMA,
    _compile_at,
    compile_current_dossier,
    compile_dossier,
    compile_historical_dossier,
    verify_current_dossier,
    verify_historical_dossier,
)

AS_OF = "2026-09-13T14:00:00Z"


def _utc_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


class V4ContractTests(unittest.TestCase):
    def test_manifest_names_v4_modes_and_typed_authority(self):
        manifest = json.loads(Path("revenue/swarmops_dossier/manifest.json").read_text())
        self.assertEqual(manifest["output_schema"], OUTPUT_SCHEMA)
        self.assertEqual(manifest["evaluation_modes"], ["CURRENT", "HISTORICAL_REPLAY"])
        self.assertEqual(
            manifest["commercial_truth_authority"],
            "independent_typed_commercial_event_map",
        )

    def test_package_exports_named_current_and_historical_functions(self):
        expected = {
            "compile_current_dossier",
            "verify_current_dossier",
            "compile_historical_dossier",
            "verify_historical_dossier",
            "compile_dossier",
            "verify_dossier",
        }
        self.assertTrue(expected <= set(pkg.__all__))

    def test_public_alias_is_labeled_historical_replay(self):
        packet, policy = fixture()
        out = compile_dossier(packet, policy, AS_OF)
        self.assertEqual(out["schema"], "commons.swarmops-dossier-output/v4")
        self.assertEqual(out["evaluation_mode"], "HISTORICAL_REPLAY")
        self.assertEqual(out["status"], "HISTORICAL_READY")
        self.assertNotIn("core_v3_receipt_sha256", out)
        self.assertEqual(compile_historical_dossier(packet, policy, AS_OF), out)

    def test_archived_v3_still_verifies_only_as_historical(self):
        packet, policy = fixture()
        legacy = _compile_at(packet, policy, AS_OF)
        self.assertEqual(legacy["schema"], LEGACY_OUTPUT_SCHEMA)
        self.assertEqual(legacy["status"], "READY_FOR_OWNER_REVIEW")
        self.assertTrue(verify_historical_dossier(packet, policy, AS_OF, legacy))
        with self.assertRaises(DossierError):
            verify_current_dossier(packet, policy, legacy)

    def test_current_compile_and_verify_use_process_utc(self):
        original, policy = fixture()
        historical = compile_dossier(original, policy, AS_OF)
        packet = copy.deepcopy(original)
        stamp = _utc_text(datetime.now(timezone.utc))
        for row in packet["evidence"]:
            row["observed_at"] = stamp
        before = datetime.now(timezone.utc).replace(microsecond=0)
        out = compile_current_dossier(packet, policy)
        after = datetime.now(timezone.utc).replace(microsecond=0)
        self.assertEqual(out["schema"], OUTPUT_SCHEMA)
        self.assertEqual(out["evaluation_mode"], "CURRENT")
        self.assertEqual(out["status"], "READY_FOR_OWNER_REVIEW")
        self.assertGreaterEqual(_parse(out["as_of"]), before)
        self.assertLessEqual(_parse(out["as_of"]), after)
        self.assertTrue(verify_current_dossier(packet, policy, out))
        with self.assertRaises(DossierError):
            verify_current_dossier(packet, policy, historical)

    def test_public_cli_keeps_replay_and_rejects_current_as_of(self):
        packet, policy = fixture()
        with tempfile.TemporaryDirectory() as td:
            packet_path = Path(td, "packet.json")
            policy_path = Path(td, "policy.json")
            out = Path(td, "out.json")
            md = Path(td, "out.md")
            packet_path.write_text(json.dumps(packet))
            policy_path.write_text(json.dumps(policy))
            with self.assertRaises(SystemExit):
                cli_main([
                    "compile", str(packet_path), str(policy_path),
                    "--as-of", AS_OF, "--json-out", str(out), "--markdown-out", str(md),
                ])
            self.assertEqual(cli_main([
                "replay", str(packet_path), str(policy_path),
                "--as-of", AS_OF, "--json-out", str(out), "--markdown-out", str(md),
            ]), 0)
            replayed = json.loads(out.read_text())
            self.assertEqual(replayed["evaluation_mode"], "HISTORICAL_REPLAY")
            candidate = Path(td, "replay.json")
            candidate.write_text(out.read_text())
            self.assertEqual(cli_main([
                "verify-replay", str(packet_path), str(policy_path), str(candidate),
                "--as-of", AS_OF,
            ]), 0)
            current_json = Path(td, "current.json")
            current_md = Path(td, "current.md")
            self.assertEqual(cli_main([
                "compile", str(packet_path), str(policy_path),
                "--json-out", str(current_json), "--markdown-out", str(current_md),
            ]), 2)
            current = json.loads(current_json.read_text())
            self.assertEqual(current["evaluation_mode"], "CURRENT")
            self.assertEqual(current["status"], "HOLD")
            self.assertEqual(cli_main([
                "verify", str(packet_path), str(policy_path), str(current_json),
            ]), 0)


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value[:-1] + "+00:00")


if __name__ == "__main__":
    unittest.main()
