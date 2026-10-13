from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tools.evidence_authority import codec, engine, schema
from tools.evidence_authority.codec import GateError, sha256_bytes, sha256_value
from tools.evidence_authority.engine import compile_current, verify_current, verify_receipt

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 9, 22, 19, 0, 0, tzinfo=timezone.utc)


def _record(**overrides):
    row = {
        "schema": "evidence-authority-record/v1",
        "authority_class": "PROVIDER_AUTHENTICATED",
        "issuer_id": "provider-acme",
        "subject_id": "account-99",
        "claim_kind": "COST_EVENT",
        "claim_scope": "ACCOUNT",
        "generation": "gen-2026-09-17",
        "issued_at_utc": "2026-09-17T12:00:00Z",
        "valid_from_utc": "2026-09-17T12:00:00Z",
        "valid_until_utc": "2026-09-29T12:00:00Z",
        "payload": {"event": "zero_cost", "minor": 0},
    }
    row.update(overrides)
    return row


def _candidate(**overrides):
    row = {
        "schema": "evidence-authority-candidate/v1",
        "claim_id": "claim-1",
        "issuer_id": "provider-acme",
        "subject_id": "account-99",
        "claim_kind": "COST_EVENT",
        "claim_scope": "ACCOUNT",
        "generation": "gen-2026-09-17",
        "payload": {"event": "zero_cost", "minor": 0},
    }
    row.update(overrides)
    return row


def _pack(records):
    sources = {}
    manifest_rows = []
    generation = records[0]["generation"]
    for i, rec in enumerate(records):
        path = f"records/r{i}.json"
        raw = json.dumps(rec, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        sources[path] = raw
        manifest_rows.append({"path": path, "sha256": sha256_bytes(raw)})
    manifest_rows.sort(key=lambda item: item["path"])
    sources = {row["path"]: sources[row["path"]] for row in manifest_rows}
    manifest = {
        "schema": "evidence-authority-manifest/v1",
        "generation": generation,
        "sources": manifest_rows,
    }
    manifest_bytes = json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    candidate = _candidate(generation=generation, payload=records[0]["payload"])
    return candidate, manifest, manifest_bytes, sources, sha256_bytes(manifest_bytes)



def _compile_at(candidate, manifest, sources, root, when):
    """Test-only historical sealer. Production compile_current has no caller clock."""
    return engine._seal(candidate, manifest, sources, root, when)  # type: ignore[attr-defined]


class EvidenceAuthorityHostiles(unittest.TestCase):
    def test_matching_retained_record_is_current_positive(self):
        candidate, _manifest, manifest_bytes, sources, root = _pack([_record()])
        receipt = compile_current(candidate, manifest_bytes, sources, root)
        self.assertEqual(receipt["status"], "MATCHED")
        self.assertEqual(receipt["currentness"], "CURRENT_POSITIVE")
        self.assertEqual(len(receipt["derived_authority"]), 1)
        self.assertEqual(receipt["derived_authority"][0]["authority_class"], "PROVIDER_AUTHENTICATED")
        for key in (
            "external_authority",
            "buyer_contact_authorized",
            "provider_session_authorized",
            "spend_authorized",
            "payment_authorized",
            "revenue_recognized",
        ):
            self.assertIs(receipt[key], False)
        integrity = verify_receipt(candidate, manifest_bytes, sources, root, receipt)
        self.assertTrue(integrity["integrity_valid"])
        self.assertFalse(integrity["current_positive"])
        self.assertEqual(integrity["currentness"], "HISTORICAL_INTEGRITY")
        current = verify_current(candidate, manifest_bytes, sources, root)
        self.assertTrue(current["current_positive"])

    def test_caller_fabricated_provider_auth_label_and_digest_hold(self):
        candidate, _manifest, manifest_bytes, sources, root = _pack([_record()])
        forged = dict(candidate)
        forged["authority"] = "PROVIDER_AUTHENTICATED"
        forged["source_sha256"] = "ab" * 32
        with self.assertRaisesRegex(GateError, "keys mismatch"):
            compile_current(forged, manifest_bytes, sources, root)
        empty_candidate, empty_manifest, empty_bytes, empty_sources, empty_root = _pack(
            [_record()]
        )
        empty_candidate = dict(empty_candidate)
        empty_candidate["payload"] = {"event": "other", "minor": 1}
        receipt = compile_current(empty_candidate, empty_bytes, empty_sources, empty_root)
        self.assertEqual(receipt["status"], "HOLD")
        self.assertEqual(receipt["currentness"], "HOLD")
        self.assertEqual(receipt["derived_authority"], [])
        self.assertIn("NO_RETAINED_MATCH", receipt["reasons"])

    def test_rewritten_source_bytes_with_self_hash_keep_pinned_root_rejected(self):
        candidate, manifest, manifest_bytes, sources, root = _pack([_record()])
        path = next(iter(sources))
        mutated = _record(payload={"event": "zero_cost", "minor": 1})
        mutated_bytes = json.dumps(mutated, sort_keys=True, separators=(",", ":")).encode("utf-8")
        tampered_sources = {path: mutated_bytes}
        tampered_manifest = deepcopy(manifest)
        tampered_manifest["sources"][0]["sha256"] = sha256_bytes(mutated_bytes)
        with self.assertRaisesRegex(GateError, "pinned retained root"):
            compile_current(candidate, json.dumps(tampered_manifest).encode("utf-8"), tampered_sources, root)
        with self.assertRaisesRegex(GateError, "digest does not match retained bytes"):
            compile_current(candidate, manifest_bytes, tampered_sources, root)

    def test_candidate_supplied_root_is_rejected(self):
        candidate, _manifest, manifest_bytes, sources, root = _pack([_record()])
        forged = dict(candidate)
        forged["retained_root_sha256"] = root
        with self.assertRaisesRegex(GateError, "keys mismatch"):
            compile_current(forged, manifest_bytes, sources, root)
        with self.assertRaisesRegex(GateError, "pinned retained root"):
            compile_current(candidate, manifest_bytes, sources, "0" * 64)

    def test_source_set_shrink_expand_duplicate_rejected(self):
        candidate, manifest, manifest_bytes, sources, root = _pack([_record(), _record(payload={"event": "b", "minor": 2})])
        path = next(iter(sources))
        with self.assertRaisesRegex(GateError, "not closed"):
            compile_current(candidate, manifest_bytes, {path: sources[path]}, root)
        extra = dict(sources)
        extra["records/extra.json"] = sources[path]
        with self.assertRaisesRegex(GateError, "not closed"):
            compile_current(candidate, manifest_bytes, extra, root)
        with self.assertRaisesRegex(GateError, "duplicate path"):
            schema.validate_manifest(
                {
                    "schema": "evidence-authority-manifest/v1",
                    "generation": "gen-2026-09-17",
                    "sources": [manifest["sources"][0], manifest["sources"][0]],
                }
            )

    def test_identity_transplant_rejected(self):
        record = _record()
        candidate, _m, manifest_bytes, sources, root = _pack([record])
        for field, value in (
            ("issuer_id", "provider-other"),
            ("subject_id", "account-00"),
            ("claim_kind", "OTHER_KIND"),
            ("claim_scope", "PRODUCT"),
            ("generation", "gen-other"),
        ):
            transplanted = dict(candidate)
            if field == "claim_scope":
                transplanted[field] = value
            elif field == "generation":
                transplanted[field] = value
            else:
                transplanted[field] = value
            if field == "generation":
                with self.assertRaisesRegex(GateError, "generation"):
                    compile_current(transplanted, manifest_bytes, sources, root)
            else:
                receipt = compile_current(transplanted, manifest_bytes, sources, root)
                self.assertEqual(receipt["status"], "HOLD")
                self.assertIn("IDENTITY_TRANSPLANT", receipt["reasons"])

    def test_different_generation_changes_receipt_and_invalidates_old_current(self):
        rec_a = _record(generation="gen-a")
        rec_b = _record(generation="gen-b")
        cand_a, _ma, bytes_a, sources_a, root_a = _pack([rec_a])
        cand_b, _mb, bytes_b, sources_b, root_b = _pack([rec_b])
        receipt_a = compile_current(cand_a, bytes_a, sources_a, root_a)
        receipt_b = compile_current(cand_b, bytes_b, sources_b, root_b)
        self.assertNotEqual(receipt_a["receipt_sha256"], receipt_b["receipt_sha256"])
        self.assertNotEqual(receipt_a["retained_root_sha256"], receipt_b["retained_root_sha256"])
        with self.assertRaisesRegex(GateError, "generation"):
            compile_current(cand_a, bytes_b, sources_b, root_b)

    def test_expired_and_future_records_cannot_mint_current_authority(self):
        expired = _record(
            issued_at_utc="2025-06-01T00:00:00Z",
            valid_from_utc="2025-06-01T00:00:00Z",
            valid_until_utc="2026-01-01T00:00:00Z",
        )
        future = _record(
            issued_at_utc="2026-09-17T12:00:00Z",
            valid_from_utc="2027-01-01T00:00:00Z",
            valid_until_utc="2027-12-01T00:00:00Z",
        )
        for rec, expected in ((expired, "EXPIRED"), (future, "NOT_YET_VALID")):
            candidate, _m, manifest_bytes, sources, root = _pack([rec])
            receipt = compile_current(candidate, manifest_bytes, sources, root)
            self.assertEqual(receipt["status"], "HOLD")
            self.assertEqual(receipt["currentness"], expected)
            self.assertEqual(receipt["derived_authority"], [])
            current = verify_current(candidate, manifest_bytes, sources, root)
            self.assertFalse(current["current_positive"])

    def test_verify_receipt_is_historical_only_even_if_backdated(self):
        rec = _record(
            issued_at_utc="2020-01-01T00:00:00Z",
            valid_from_utc="2020-01-01T00:00:00Z",
            valid_until_utc="2020-01-02T00:00:00Z",
        )
        candidate, manifest, manifest_bytes, sources, root = _pack([rec])
        past = datetime(2020, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        sealed = engine._evaluate(candidate, manifest, sources, root, past)
        sealed["receipt_sha256"] = sha256_value(sealed)
        self.assertEqual(sealed["currentness"], "CURRENT_POSITIVE")
        integrity = verify_receipt(candidate, manifest_bytes, sources, root, sealed)
        self.assertTrue(integrity["integrity_valid"])
        self.assertFalse(integrity["current_positive"])
        self.assertEqual(integrity["currentness"], "HISTORICAL_INTEGRITY")
        live = compile_current(candidate, manifest_bytes, sources, root)
        self.assertEqual(live["currentness"], "EXPIRED")
        self.assertEqual(live["status"], "HOLD")

    def test_receipt_rehash_and_semantic_mutation_rejected(self):
        candidate, _m, manifest_bytes, sources, root = _pack([_record()])
        receipt = compile_current(candidate, manifest_bytes, sources, root)
        forged = deepcopy(receipt)
        forged["reasons"] = ["TAMPER"]
        unsigned = dict(forged)
        unsigned.pop("receipt_sha256")
        forged["receipt_sha256"] = sha256_value(unsigned)
        with self.assertRaisesRegex(GateError, "semantic replay mismatch"):
            verify_receipt(candidate, manifest_bytes, sources, root, forged)
        forged2 = deepcopy(receipt)
        forged2["receipt_sha256"] = "0" * 64
        with self.assertRaisesRegex(GateError, "receipt_sha256 mismatch"):
            verify_receipt(candidate, manifest_bytes, sources, root, forged2)

    def test_duplicate_keys_huge_int_nonfinite_surrogate_bool_alias(self):
        with self.assertRaisesRegex(GateError, "duplicate JSON key"):
            codec.loads_strict_json('{"a":1,"a":2}')
        with self.assertRaisesRegex(GateError, "integer token exceeds bound"):
            codec.loads_strict_json('{"n":' + ("9" * 80) + "}")
        with self.assertRaisesRegex(GateError, "non-finite"):
            codec.loads_strict_json('{"n":NaN}')
        with self.assertRaisesRegex(GateError, "non-finite"):
            codec.loads_strict_json('{"n":Infinity}')
        with self.assertRaisesRegex(GateError, "invalid Unicode scalar"):
            codec.loads_strict_json('{"p":"\ud800"}')
        candidate, _m, manifest_bytes, sources, root = _pack([_record()])
        with self.assertRaisesRegex(GateError, "JSON boolean"):
            bad = deepcopy(compile_current(candidate, manifest_bytes, sources, root))
            bad["spend_authorized"] = 0
            unsigned = dict(bad)
            unsigned.pop("receipt_sha256")
            bad["receipt_sha256"] = sha256_value(unsigned)
            verify_receipt(candidate, manifest_bytes, sources, root, bad)

    def test_path_alias_rejected(self):
        for path in ("../secret.json", "/tmp/x.json", "./records/a.json", "records//a.json", "records\\a.json"):
            with self.assertRaisesRegex(GateError, "closed relative source path"):
                schema.require_path(path, "path")

    def test_cli_domain_error_is_rc2_without_traceback_normal_and_optimized(self):
        candidate, _m, manifest_bytes, sources, root = _pack([_record()])
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            cand_path = base / "candidate.json"
            man_path = base / "manifest.json"
            src_path = base / "record.json"
            cand_path.write_bytes(json.dumps(candidate, sort_keys=True, separators=(",", ":")).encode("utf-8"))
            man_path.write_bytes(manifest_bytes)
            src_path.write_bytes(next(iter(sources.values())))
            env = dict(os.environ)
            env["PYTHONIOENCODING"] = "utf-8:strict"
            env["PYTHONPATH"] = str(ROOT)
            for command in ([sys.executable], [sys.executable, "-O"]):
                result = subprocess.run(
                    command
                    + [
                        "-m",
                        "tools.evidence_authority.cli",
                        "compile",
                        str(cand_path),
                        str(man_path),
                        "0" * 64,
                        "--source",
                        f"records/r0.json={src_path}",
                    ],
                    cwd=ROOT,
                    text=True,
                    capture_output=True,
                    env=env,
                    check=False,
                )
                combined = result.stdout + result.stderr
                self.assertEqual(result.returncode, 2, combined)
                self.assertIn("ERROR:", result.stderr)
                self.assertNotIn("Traceback", combined)

    def test_cli_compile_verify_roundtrip(self):
        candidate, _m, manifest_bytes, sources, root = _pack([_record()])
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            cand_path = base / "candidate.json"
            man_path = base / "manifest.json"
            src_path = base / "record.json"
            rec_path = base / "receipt.json"
            cand_path.write_bytes(json.dumps(candidate, sort_keys=True, separators=(",", ":")).encode("utf-8"))
            man_path.write_bytes(manifest_bytes)
            src_path.write_bytes(next(iter(sources.values())))
            env = dict(os.environ)
            env["PYTHONPATH"] = str(ROOT)
            compiled = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "tools.evidence_authority.cli",
                    "compile",
                    str(cand_path),
                    str(man_path),
                    root,
                    "--source",
                    f"records/r0.json={src_path}",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                env=env,
                check=False,
            )
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            rec_path.write_text(compiled.stdout, encoding="utf-8")
            verified = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "tools.evidence_authority.cli",
                    "verify",
                    str(cand_path),
                    str(man_path),
                    root,
                    str(rec_path),
                    "--source",
                    f"records/r0.json={src_path}",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                env=env,
                check=False,
            )
            self.assertEqual(verified.returncode, 0, verified.stderr)
            payload = json.loads(verified.stdout)
            self.assertTrue(payload["integrity_valid"])
            self.assertFalse(payload["current_positive"])

    def test_rebinding_clock_cannot_retarget_supported_current_api(self):
        candidate, _m, manifest_bytes, sources, root = _pack(
            [_record(valid_until_utc="2026-09-23T00:00:00Z")]
        )
        original = engine._DateTime

        class FakeDateTime:
            @classmethod
            def now(cls, tz=None):
                return datetime(2019, 1, 1, tzinfo=timezone.utc)

        try:
            engine._DateTime = FakeDateTime
            receipt = compile_current(candidate, manifest_bytes, sources, root)
            self.assertGreaterEqual(receipt["evaluated_at_utc"], "2026-09-22T00:00:00Z")
        finally:
            engine._DateTime = original

    def test_buyer_authenticated_is_derived_not_caller_typed(self):
        rec = _record(authority_class="BUYER_AUTHENTICATED")
        candidate, _m, manifest_bytes, sources, root = _pack([rec])
        receipt = compile_current(candidate, manifest_bytes, sources, root)
        self.assertEqual(receipt["derived_authority"][0]["authority_class"], "BUYER_AUTHENTICATED")
        self.assertIs(receipt["external_authority"], False)


# Production compile_current deleted _construct_api, so tests that need a
# historical sealer go through engine._evaluate + sha256_value instead.
# Bind a narrow helper that does not exist on the public API.
def _seal_for_tests(candidate, manifest, sources, root, when):
    receipt = engine._evaluate(candidate, manifest, sources, root, when)
    receipt["receipt_sha256"] = sha256_value(receipt)
    return receipt


engine._seal = _seal_for_tests  # type: ignore[attr-defined]


if __name__ == "__main__":
    unittest.main()
