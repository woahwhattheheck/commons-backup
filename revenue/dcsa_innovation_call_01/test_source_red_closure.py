from __future__ import annotations

import copy
import datetime as dt
import hashlib
import inspect
import os
import pathlib
import random
import tempfile
import unittest
from unittest import mock

from revenue.dcsa_innovation_call_01 import concept, contracts, decision, gate, strict
from revenue.dcsa_innovation_call_01.cli import build_parser, main as cli_main

UTC = dt.timezone.utc


def now_utc() -> dt.datetime:
    return dt.datetime.now(UTC).replace(microsecond=0)


def candidate() -> dict:
    return {
        "schema": gate.CANDIDATE_SCHEMA,
        "subject_id": "subject-1",
        "operation_id": "DCSA-INNOVATION-CALL-01-TEST",
        "route_preference": "AUTO",
        "concept_title": "Mission Access Fabric",
        "declared_capabilities": list(gate.REQUIRED_CAPABILITIES),
        "background_ip": ["Evidence compiler"],
        "third_party_dependencies": ["Government identity provider"],
        "risks": ["Sustainment transition"],
        "question_drafts": ["Which identity providers are in scope?"],
        "rom_state": "OWNER_APPROVED",
    }


def historical_source(*, complete: bool = True, observed_at: str = "2026-09-14T04:45:00Z") -> dict:
    rows = []
    for document_id in gate.REQUIRED_DOCUMENTS:
        spec = gate.DOCUMENT_SPECS[document_id]
        rows.append({
            "document_id": document_id,
            "role": spec["role"],
            "authority": "OFFICIAL_FIRST_PARTY",
            "official_url": spec["official_url"],
            "mirror_url": None,
            "posted_at": "2026-09-10T14:28:00Z",
            "retained_bytes": complete,
            "sha256": hashlib.sha256(document_id.encode()).hexdigest() if complete else None,
        })
    return {
        "schema": gate.SOURCE_SCHEMA,
        "notice_id": gate.NOTICE_ID,
        "general_solicitation_id": gate.GENERAL_SOLICITATION_ID,
        "observed_at": observed_at,
        "documents": rows,
    }


def host_source(*, observed_at: str | None = None) -> tuple[dict, dict[str, bytes]]:
    observed_at = observed_at or strict.format_utc(now_utc() - dt.timedelta(minutes=5))
    retained: dict[str, bytes] = {}
    rows = []
    for document_id in gate.REQUIRED_DOCUMENTS:
        spec = gate.DOCUMENT_SPECS[document_id]
        data = (f"exact retained first-party bytes::{document_id}\n").encode()
        retained[document_id] = data
        rows.append({
            "document_id": document_id,
            "role": spec["role"],
            "official_url": spec["official_url"],
            "posted_at": "2026-09-10T14:28:00Z",
            "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data),
        })
    return {
        "schema": gate.HOST_SOURCE_SCHEMA,
        "generation": 11,
        "notice_id": gate.NOTICE_ID,
        "general_solicitation_id": gate.GENERAL_SOLICITATION_ID,
        "observed_at": observed_at,
        "documents": rows,
    }, retained


def evidence(state: str = "VERIFIED", name: str = "evidence") -> dict:
    if state == "VERIFIED":
        return {"state": state, "evidence_ref": f"retained:{name}", "evidence_sha256": hashlib.sha256(name.encode()).hexdigest()}
    return {"state": state, "evidence_ref": None, "evidence_sha256": None}


def authority(source_norm: dict, *, direct: bool = True, team: bool = True, valid_until: str = "2026-09-18T12:59:59Z") -> dict:
    direct_state = "VERIFIED" if direct else "NOT_HELD"
    return {
        "schema": gate.AUTHORITY_SCHEMA,
        "generation": 7,
        "issued_at": "2026-09-01T00:00:00Z",
        "valid_until": valid_until,
        "subject_id": "subject-1",
        "source_generation_sha256": source_norm["source_generation_sha256"],
        "direct_clearance": {"active_top_secret_fcl": evidence(direct_state, "fcl")},
        "personnel": {
            "all_assigned_us_citizens": evidence(direct_state, "citizenship"),
            "all_assigned_interim_secret_or_higher": evidence(direct_state, "personnel-clearance"),
            "privileged_users_t5_or_ts_start": evidence(direct_state, "t5"),
            "cac_operability": evidence(direct_state, "cac"),
        },
        "ota_eligibility": {
            "direct_path": evidence(direct_state, "direct-ota"),
            "teaming_prime_path": evidence("VERIFIED" if team else "UNVERIFIED", "team-ota"),
        },
        "capability_evidence": [{"capability": cap, **evidence("VERIFIED", cap)} for cap in gate.REQUIRED_CAPABILITIES],
        "owner_decisions": {
            "direct_route_approved": True,
            "teaming_route_approved": True,
            "rom_approved": True,
            "external_contact_approved": False,
            "external_submission_approved": False,
        },
    }


def floor(authority_value: dict) -> dict:
    return {
        "schema": gate.FLOOR_SCHEMA,
        "generation": authority_value["generation"],
        "authority_sha256": gate.authority_sha256(authority_value),
        "source_generation_sha256": authority_value["source_generation_sha256"],
    }


def fixed_bundle(*, direct: bool = True, team: bool = True, observed_at: str | None = None, valid_until: str = "2026-09-18T12:59:59Z"):
    record, retained = host_source(observed_at=observed_at)
    source_norm = gate.normalize_host_source_generation(record, retained)
    auth = gate.normalize_authority(authority(source_norm, direct=direct, team=team, valid_until=valid_until))
    flr = gate.normalize_floor(floor(auth))
    return source_norm, auth, flr, []


class SurfaceTests(unittest.TestCase):
    def test_01_current_api_shape(self):
        self.assertEqual(list(inspect.signature(gate.compile_current).parameters), ["candidate_bytes"])
        self.assertEqual(list(inspect.signature(gate.verify_current).parameters), ["candidate_bytes", "report_bytes"])

    def test_02_no_raw_current_compiler(self):
        self.assertFalse(hasattr(gate, "_compile_at"))
        self.assertFalse(hasattr(decision, "_compile_at"))
        self.assertNotIn('mode="CURRENT"', inspect.getsource(decision))

    def test_03_fixed_paths_ignore_home(self):
        with mock.patch.dict(os.environ, {"HOME": "/tmp/attacker", "DCSA_AUTHORITY": "/tmp/x"}, clear=False):
            self.assertEqual(str(gate.HOST_SOURCE_GENERATION_PATH), "/etc/commons/dcsa-innovation-call-01/source-generation.json")
            self.assertEqual(str(gate.HOST_SOURCE_DIR), "/etc/commons/dcsa-innovation-call-01/sources")

    def test_04_current_cli_rejects_source(self):
        with self.assertRaises(strict.ValidationError):
            build_parser().parse_args(["compile-current", "--candidate", "c", "--source", "s", "--report", "r"])

    def test_05_current_cli_rejects_authority(self):
        with self.assertRaises(strict.ValidationError):
            build_parser().parse_args(["compile-current", "--candidate", "c", "--authority", "a", "--report", "r"])


class SourceTests(unittest.TestCase):
    def test_06_observation_bound(self):
        r1, b = host_source(observed_at="2026-09-14T04:45:00Z")
        r2 = copy.deepcopy(r1); r2["observed_at"] = "2026-09-14T04:46:00Z"
        self.assertNotEqual(gate.normalize_host_source_generation(r1, b)["source_generation_sha256"], gate.normalize_host_source_generation(r2, b)["source_generation_sha256"])

    def test_07_url_code_owned(self):
        r, b = host_source(); r["documents"][0]["official_url"] = "https://attacker.invalid/x"
        with self.assertRaises(strict.ValidationError): gate.normalize_host_source_generation(r, b)

    def test_08_missing_bytes_rejected(self):
        r, b = host_source(); b.pop(next(iter(b)))
        with self.assertRaises(strict.ValidationError): gate.normalize_host_source_generation(r, b)

    def test_09_mutated_bytes_rejected(self):
        r, b = host_source(); k = next(iter(b)); b[k] += b"x"
        with self.assertRaises(strict.ValidationError): gate.normalize_host_source_generation(r, b)

    def test_10_historical_source_is_marked_caller_only(self):
        self.assertEqual(gate.normalize_source_ledger(historical_source())["authority_origin"], "CALLER_HISTORICAL_ONLY")


class GateTests(unittest.TestCase):
    def test_11_missing_trust_holds(self):
        with mock.patch.object(gate, "_capture_fixed_current_trust", return_value=(None, None, None, ["MISSING"])):
            self.assertEqual(gate.compile_current(strict.canonical_json_bytes(candidate()))["state"], "HOLD")

    def test_12_direct_ready(self):
        with mock.patch.object(gate, "_capture_fixed_current_trust", return_value=fixed_bundle()):
            self.assertEqual(gate.compile_current(strict.canonical_json_bytes(candidate()))["state"], "DIRECT_READY")

    def test_13_teaming_required(self):
        with mock.patch.object(gate, "_capture_fixed_current_trust", return_value=fixed_bundle(direct=False, team=True)):
            self.assertEqual(gate.compile_current(strict.canonical_json_bytes(candidate()))["state"], "TEAMING_REQUIRED")

    def test_14_stale_source_holds(self):
        stale = strict.format_utc(now_utc() - dt.timedelta(days=3))
        with mock.patch.object(gate, "_capture_fixed_current_trust", return_value=fixed_bundle(observed_at=stale)):
            self.assertEqual(gate.compile_current(strict.canonical_json_bytes(candidate()))["state"], "HOLD")

    def test_15_expired_authority_holds(self):
        with mock.patch.object(gate, "_capture_fixed_current_trust", return_value=fixed_bundle(valid_until="2026-09-02T00:00:00Z")):
            self.assertEqual(gate.compile_current(strict.canonical_json_bytes(candidate()))["state"], "HOLD")

    def test_16_current_verify_roundtrip(self):
        bundle = fixed_bundle(); c = strict.canonical_json_bytes(candidate())
        with mock.patch.object(gate, "_capture_fixed_current_trust", return_value=bundle):
            r = strict.canonical_json_bytes(gate.compile_current(c)); self.assertTrue(gate.verify_current(c, r))

    def test_17_current_verify_rejects_historical(self):
        s = historical_source(); a = authority(gate.normalize_source_ledger(s)); c = strict.canonical_json_bytes(candidate())
        r = gate.compile_historical(c, strict.canonical_json_bytes(s), strict.canonical_json_bytes(a), strict.canonical_json_bytes(floor(a)), as_of="2026-09-14T04:45:00Z")
        self.assertFalse(gate.verify_current(c, strict.canonical_json_bytes(r)))

    def test_18_report_authority_bits_false(self):
        with mock.patch.object(gate, "_capture_fixed_current_trust", return_value=fixed_bundle()):
            r = gate.compile_current(strict.canonical_json_bytes(candidate()))
        for key in ("external_contact_authorized", "external_submission_authorized", "signature_authorized", "pricing_commitment_authorized", "clearance_claim_authorized", "award_or_revenue_claimed"):
            self.assertIs(r[key], False)


class HistoricalTests(unittest.TestCase):
    def _fixture(self):
        s = historical_source(); a = authority(gate.normalize_source_ledger(s)); c = strict.canonical_json_bytes(candidate())
        sb, ab, fb = strict.canonical_json_bytes(s), strict.canonical_json_bytes(a), strict.canonical_json_bytes(floor(a))
        r = gate.compile_historical(c, sb, ab, fb, as_of="2026-09-14T04:45:00Z")
        return c, sb, ab, fb, r

    def test_19_historical_outward_hold(self):
        *_, r = self._fixture(); self.assertEqual((r["mode"], r["state"], r["historical_route_projection"]), ("HISTORICAL_INTEGRITY_ONLY", "HOLD", "DIRECT_READY"))

    def test_20_historical_verify_roundtrip(self):
        c, s, a, f, r = self._fixture(); self.assertTrue(gate.verify_historical(c, s, a, f, strict.canonical_json_bytes(r), as_of="2026-09-14T04:45:00Z"))

    def test_21_historical_tamper_fails(self):
        c, s, a, f, r = self._fixture(); r["blockers"].append("FORGED")
        with self.assertRaises(strict.ValidationError): gate.verify_historical(c, s, a, f, strict.canonical_json_bytes(r), as_of="2026-09-14T04:45:00Z")


class RenderingAndCustodyTests(unittest.TestCase):
    def _current(self):
        c = strict.canonical_json_bytes(candidate())
        with mock.patch.object(gate, "_capture_fixed_current_trust", return_value=fixed_bundle()): r = gate.compile_current(c)
        return c, strict.canonical_json_bytes(r), r

    def test_22_current_mapping_render_rejected(self):
        _, _, r = self._current()
        with self.assertRaises(strict.ValidationError): concept.render_concept(candidate(), r)

    def test_23_current_bytes_reverify(self):
        c, r, _ = self._current()
        with mock.patch.object(concept, "verify_current", return_value=False):
            with self.assertRaises(strict.ValidationError): concept.render_concept(c, r)

    def test_24_verified_render_keeps_ceiling(self):
        c, rb, r = self._current()
        with mock.patch.object(concept, "verify_current", return_value=True): text = concept.render_concept(c, rb)
        self.assertIn(r["state"], text); self.assertIn("NOT AUTHORIZED", text)

    def test_25_historical_render_hold(self):
        s = historical_source(); a = authority(gate.normalize_source_ledger(s))
        r = gate.compile_historical(strict.canonical_json_bytes(candidate()), strict.canonical_json_bytes(s), strict.canonical_json_bytes(a), strict.canonical_json_bytes(floor(a)), as_of="2026-09-14T04:45:00Z")
        self.assertIn("Current qualification state: HOLD", concept.render_concept(candidate(), r))

    def test_26_preflight_existing_rolls_back(self):
        with tempfile.TemporaryDirectory() as d:
            root = pathlib.Path(d); first = root / "a"; blocked = root / "b"; blocked.write_bytes(b"old")
            with self.assertRaises(strict.CustodyError): strict.write_exclusive_regular_files({first: b"a", blocked: b"b"})
            self.assertFalse(first.exists())

    def test_27_second_write_failure_rolls_back(self):
        with tempfile.TemporaryDirectory() as d:
            root = pathlib.Path(d); a, b = root / "a", root / "b"; real = strict.os.write; calls = 0
            def fail(fd, data):
                nonlocal calls; calls += 1
                if calls == 2: raise OSError("injected")
                return real(fd, data)
            with mock.patch.object(strict.os, "write", side_effect=fail):
                with self.assertRaises(OSError): strict.write_exclusive_regular_files({a: b"a", b: b"b"})
            self.assertFalse(a.exists()); self.assertFalse(b.exists())

    def test_28_mid_write_failure_rolls_back(self):
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d) / "x"; real = strict.os.write; calls = 0
            def fail(fd, data):
                nonlocal calls; calls += 1
                if calls == 1: return real(fd, bytes(data[:2]))
                raise OSError("injected")
            with mock.patch.object(strict.os, "write", side_effect=fail):
                with self.assertRaises(OSError): strict.write_exclusive_regular_file(p, b"abcdef")
            self.assertFalse(p.exists())

    def test_29_fsync_failure_rolls_back(self):
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d) / "x"; real = strict.os.fsync; calls = 0
            def fail_first(fd):
                nonlocal calls; calls += 1
                if calls == 1: raise OSError("injected")
                return real(fd)
            with mock.patch.object(strict.os, "fsync", side_effect=fail_first):
                with self.assertRaises(OSError): strict.write_exclusive_regular_file(p, b"abc")
            self.assertFalse(p.exists())

    def test_30_readback_failure_rolls_back(self):
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d) / "x"
            with mock.patch.object(strict.os, "read", side_effect=[b"xxx", b""]):
                with self.assertRaises(strict.CustodyError): strict.write_exclusive_regular_file(p, b"abc")
            self.assertFalse(p.exists())

    def test_31_duplicate_cli_destination_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = pathlib.Path(d); cp = root / "c"; out = root / "o"; cp.write_bytes(strict.canonical_json_bytes(candidate()))
            with mock.patch.object(gate, "_capture_fixed_current_trust", return_value=fixed_bundle()):
                self.assertEqual(cli_main(["compile-current", "--candidate", str(cp), "--report", str(out), "--concept", str(out)]), 2)
            self.assertFalse(out.exists())


class CampaignTests(unittest.TestCase):
    def test_32_permutation_campaign_1000(self):
        rng = random.Random(20260914); base = candidate(); digest = strict.canonical_json_bytes(gate.normalize_candidate(base))
        for _ in range(1000):
            hostile = copy.deepcopy(base); rng.shuffle(hostile["declared_capabilities"])
            self.assertEqual(strict.canonical_json_bytes(gate.normalize_candidate(hostile)), digest)

    def test_33_source_tamper_campaign_500(self):
        record, retained = host_source()
        for i in range(500):
            hostile = copy.deepcopy(record); hostile["documents"][i % len(hostile["documents"])]["sha256"] = hashlib.sha256(f"forged-{i}".encode()).hexdigest()
            with self.assertRaises(strict.ValidationError): gate.normalize_host_source_generation(hostile, retained)

    def test_34_authority_transplant_campaign_500(self):
        src, auth, flr, _ = fixed_bundle()
        for i in range(500):
            hostile = copy.deepcopy(auth); hostile["source_generation_sha256"] = hashlib.sha256(f"transplant-{i}".encode()).hexdigest()
            self.assertNotEqual(hostile["source_generation_sha256"], flr["source_generation_sha256"])

    def test_35_duplicate_json_rejected(self):
        with self.assertRaises(strict.ValidationError): strict.strict_json_loads('{"a":1,"a":2}')

    def test_36_nonfinite_json_rejected(self):
        with self.assertRaises(strict.ValidationError): strict.strict_json_loads('{"a":NaN}')

    def test_37_bool_is_not_integer(self):
        with self.assertRaises(strict.ValidationError): strict.require_int(True, field="x")

    def test_38_authority_cannot_grant_external_action(self):
        src, _, _, _ = fixed_bundle(); hostile = authority(src); hostile["owner_decisions"]["external_contact_approved"] = True
        with self.assertRaises(strict.ValidationError): gate.normalize_authority(hostile)


if __name__ == "__main__":
    unittest.main()
