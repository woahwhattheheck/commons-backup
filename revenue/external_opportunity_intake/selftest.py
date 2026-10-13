from __future__ import annotations

import copy
import json
import tempfile
import unittest
from unittest.mock import patch
import hashlib
import io
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path

from revenue.external_opportunity_intake.core import (
    AUTHORITY,
    IntakeError,
    READY,
    compile_document,
    parse_strict_json,
    verify_record,
    write_bundle,
)

NOW = datetime(2026, 9, 19, 20, 0, 0, tzinfo=timezone.utc)
Z = "0" * 64
A = "a" * 64
B = "b" * 64


def base():
    return {
        "opportunity_id": "grantfox-flux-182",
        "opportunity_class": "BOUNTY",
        "active_source_generation": "g1",
        "title": "Fix stream loading/error states",
        "counterparty": "Flux-DeFi",
        "scope": "Separate loading, error and empty states with tests.",
        "opportunity_url": "https://example.test/issues/182",
        "sources": [{
            "opportunity_id": "grantfox-flux-182",
            "provider_class": "GRANTFOX",
            "source_ref": "gf:Flux-DeFi/LiquidFlow#182",
            "source_sha256": Z,
            "generation": "g1",
            "observed_at": "2026-09-19T19:00:00Z",
            "published_at": "2026-09-19T18:00:00Z",
            "supersedes_generation": None,
            "deadline_at": None,
            "deadline_externally_stated": False,
        }],
        "compensation": [{
            "opportunity_id": "grantfox-flux-182",
            "source_generation": "g1",
            "kind": "NON_FIXED",
            "currency": None,
            "amount_minor": None,
            "terms": "possible/discretionary reward; amount unconfirmed",
            "source_ref": "gf:Flux-DeFi/LiquidFlow#182",
            "source_sha256": A,
        }],
        "acceptance_route": {
            "opportunity_id": "grantfox-flux-182",
            "source_generation": "g1",
            "route": "https://contribute.example.test/apply/182",
            "source_ref": "gf:route:182",
            "source_sha256": B,
            "observed_at": "2026-09-19T19:01:00Z",
        },
        "policy": {
            "max_source_age_seconds": 7200,
            "permitted_classes": ["BOUNTY", "COMPETITION"],
            "candidate_holder_id": "ZZ-Quasar-41",
        },
        "custody": [],
        "actions": [],
        "blockers": [],
    }


def compile_at(doc, at=NOW):
    return compile_document(doc, clock=lambda: at)


class IntakeTests(unittest.TestCase):
    def test_ready(self):
        record = compile_at(base())
        self.assertEqual(record["state"], READY)
        self.assertEqual(record["authority"], AUTHORITY)
        verify_record(record)

    def test_strict_duplicate_key(self):
        with self.assertRaises(IntakeError):
            parse_strict_json('{"x":1,"x":2}')

    def test_strict_float_nonfinite_bool_int_and_unsafe_int(self):
        for raw in ('{"x":1.5}', '{"x":NaN}', '{"x":9007199254740992}'):
            with self.subTest(raw=raw), self.assertRaises(IntakeError):
                parse_strict_json(raw)
        doc = base(); doc["policy"]["max_source_age_seconds"] = True
        with self.assertRaises(IntakeError):
            compile_at(doc)

    def test_lone_surrogate_and_control_id(self):
        doc = base(); doc["opportunity_id"] = "bad\ud800"
        with self.assertRaises(IntakeError):
            compile_at(doc)
        doc = base(); doc["opportunity_id"] = "bad space"
        with self.assertRaises(IntakeError):
            compile_at(doc)

    def test_future_evidence(self):
        doc = base(); doc["sources"][0]["observed_at"] = "2026-09-19T20:00:01Z"; doc["acceptance_route"]["observed_at"] = "2026-09-19T20:00:02Z"
        self.assertEqual(compile_at(doc)["state"], "HOLD_FUTURE_EVIDENCE")

    def test_publication_after_observation_rejected(self):
        doc = base(); doc["sources"][0]["published_at"] = "2026-09-19T19:00:01Z"
        with self.assertRaises(IntakeError):
            compile_at(doc)

    def test_exact_deadline_boundary_then_expired(self):
        doc = base(); doc["sources"][0]["deadline_at"] = "2026-09-19T20:00:00Z"; doc["sources"][0]["deadline_externally_stated"] = True
        self.assertEqual(compile_at(doc)["state"], READY)
        self.assertEqual(compile_at(doc, NOW.replace(second=1))["state"], "HOLD_EXPIRED")

    def test_stale_without_deadline(self):
        doc = base(); doc["policy"]["max_source_age_seconds"] = 3599
        self.assertEqual(compile_at(doc)["state"], "HOLD_STALE_SOURCE")

    def test_generation_conflict_requires_supersession(self):
        doc = base()
        doc["sources"].append({**copy.deepcopy(doc["sources"][0]), "generation":"g2", "observed_at":"2026-09-19T19:30:00Z", "source_sha256":A})
        doc["active_source_generation"] = "g2"
        self.assertEqual(compile_at(doc)["state"], "HOLD_EVIDENCE_CONFLICT")
        doc["sources"][1]["supersedes_generation"] = "g1"
        doc["compensation"][0]["source_generation"] = "g2"
        doc["acceptance_route"]["source_generation"] = "g2"
        doc["acceptance_route"]["observed_at"] = "2026-09-19T19:31:00Z"
        self.assertEqual(compile_at(doc)["state"], READY)

    def test_cross_opportunity_transplant_rejected(self):
        for area in ("sources", "compensation"):
            doc = base(); doc[area][0]["opportunity_id"] = "other"
            with self.subTest(area=area), self.assertRaises(IntakeError):
                compile_at(doc)
        doc = base(); doc["acceptance_route"]["opportunity_id"] = "other"
        with self.assertRaises(IntakeError):
            compile_at(doc)

    def test_duplicate_custody_active_vs_released(self):
        claim = {"opportunity_id":"grantfox-flux-182","claim_id":"c1","holder_id":"other-worker","source_generation":"g1","claimed_at":"2026-09-19T19:10:00Z","released_at":None}
        doc = base(); doc["custody"] = [claim]
        self.assertEqual(compile_at(doc)["state"], "HOLD_DUPLICATE_CUSTODY")
        doc["custody"][0]["released_at"] = "2026-09-19T19:20:00Z"
        self.assertEqual(compile_at(doc)["state"], READY)

    def test_actioned_and_closed_dominate(self):
        for kind in ("MUSE_ELECTED", "APPLICATION_SENT", "OFFER_SENT", "DECLINED", "EXTERNAL_CLOSED", "EXTERNAL_WITHDRAWN", "EXTERNAL_CANCELLED"):
            doc = base(); doc["actions"] = [{"opportunity_id":"grantfox-flux-182","action_id":"a1","kind":kind,"source_generation":"g1","provider_ref":"provider:1","occurred_at":"2026-09-19T19:10:00Z"}]
            with self.subTest(kind=kind):
                self.assertEqual(compile_at(doc)["state"], "HOLD_ALREADY_ACTIONED")

    def test_action_before_observation_rejected(self):
        doc = base(); doc["actions"] = [{"opportunity_id":"grantfox-flux-182","action_id":"a1","kind":"APPLICATION_SENT","source_generation":"g1","provider_ref":"provider:1","occurred_at":"2026-09-19T18:59:59Z"}]
        with self.assertRaises(IntakeError): compile_at(doc)

    def test_semantic_duplicate_action_rejected(self):
        action={"opportunity_id":"grantfox-flux-182","action_id":"a1","kind":"APPLICATION_SENT","source_generation":"g1","provider_ref":"provider:1","occurred_at":"2026-09-19T19:10:00Z"}
        doc=base(); doc["actions"]=[action,{**action,"action_id":"a2"}]
        with self.assertRaises(IntakeError): compile_at(doc)

    def test_dnr_dominance(self):
        doc=base(); doc["blockers"]=[{"opportunity_id":"grantfox-flux-182","blocker_id":"b1","kind":"DNR","source_ref":"owner:dnr","source_sha256":Z,"observed_at":"2026-09-19T19:05:00Z"}]
        self.assertEqual(compile_at(doc)["state"], "HOLD_DNR_OR_RELATIONSHIP")

    def test_no_acceptance_route(self):
        doc=base(); doc["acceptance_route"]=None
        self.assertEqual(compile_at(doc)["state"], "HOLD_NO_ACCEPTANCE_ROUTE")

    def test_compensation_unknown_and_conflict(self):
        doc=base(); doc["compensation"]=[{"opportunity_id":"grantfox-flux-182","source_generation":"g1","kind":"UNKNOWN","currency":None,"amount_minor":None,"terms":None,"source_ref":"x","source_sha256":Z}]
        self.assertEqual(compile_at(doc)["state"], "HOLD_COMPENSATION_UNKNOWN")
        doc=base(); doc["compensation"].append({"opportunity_id":"grantfox-flux-182","source_generation":"g1","kind":"FIXED","currency":"USD","amount_minor":100,"terms":None,"source_ref":"x","source_sha256":Z})
        self.assertEqual(compile_at(doc)["state"], "HOLD_EVIDENCE_CONFLICT")

    def test_deadline_before_publication_requires_external_statement(self):
        doc=base(); doc["sources"][0]["deadline_at"]="2026-09-19T17:00:00Z"
        with self.assertRaises(IntakeError): compile_at(doc)
        doc["sources"][0]["deadline_externally_stated"]=True
        self.assertEqual(compile_at(doc)["state"], "HOLD_EXPIRED")

    def test_historical_replay_never_ready(self):
        record=compile_document(base(), historical_at=NOW)
        self.assertEqual(record["evaluation_mode"], "HISTORICAL_REPLAY")
        self.assertEqual(record["state"], "HOLD_INCOMPLETE_EVIDENCE")
        verify_record(record)

    def test_receipt_tamper_and_historical_reseal_rejected(self):
        record=compile_at(base()); record["state"]="HOLD_STALE_SOURCE"
        with self.assertRaises(IntakeError): verify_record(record)
        record=compile_at(base()); record["evaluation_mode"]="HISTORICAL_REPLAY"
        body={k:v for k,v in record.items() if k!="receipt_sha256"}
        import hashlib
        record["receipt_sha256"]=hashlib.sha256(json.dumps(body,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
        with self.assertRaises(IntakeError): verify_record(record)

    def test_deterministic_ordering(self):
        a=base(); b=base()
        a["policy"]["permitted_classes"]=["COMPETITION","BOUNTY"]
        b["policy"]["permitted_classes"]=["BOUNTY","COMPETITION"]
        self.assertEqual(compile_at(a), compile_at(b))

    def test_output_create_exclusive_and_verify(self):
        with tempfile.TemporaryDirectory() as td:
            out=Path(td)/"bundle"
            record=write_bundle(base(), out, clock=lambda: NOW)
            verify_record(parse_strict_json((out/"record.json").read_bytes()))
            self.assertTrue((out/"routing.md").exists())
            self.assertTrue((out/"manifest.json").exists())
            with self.assertRaises(IntakeError): write_bundle(base(), out, clock=lambda: NOW)


    def test_fractional_deadline_precision_and_roundtrip(self):
        doc = base()
        doc["sources"][0]["deadline_at"] = "2026-09-19T20:00:00.500000Z"
        doc["sources"][0]["deadline_externally_stated"] = True
        self.assertEqual(compile_at(doc, datetime(2026, 9, 19, 20, 0, 0, 500000, tzinfo=timezone.utc))["state"], READY)
        self.assertEqual(compile_at(doc, datetime(2026, 9, 19, 20, 0, 0, 500001, tzinfo=timezone.utc))["state"], "HOLD_EXPIRED")
        rec = compile_at(doc, datetime(2026, 9, 19, 20, 0, 0, 500000, tzinfo=timezone.utc))
        self.assertEqual(rec["opportunity"]["sources"][0]["deadline_at"], "2026-09-19T20:00:00.500000Z")
        self.assertEqual(rec["evaluated_at"], "2026-09-19T20:00:00.500000Z")
        verify_record(rec)

    def test_first_microsecond_after_integer_deadline_is_expired(self):
        doc = base()
        doc["sources"][0]["deadline_at"] = "2026-09-19T20:00:00Z"
        doc["sources"][0]["deadline_externally_stated"] = True
        at = datetime(2026, 9, 19, 20, 0, 0, 1, tzinfo=timezone.utc)
        self.assertEqual(compile_at(doc, at)["state"], "HOLD_EXPIRED")

    def test_exact_freshness_microsecond_boundary(self):
        doc = base()
        doc["policy"]["max_source_age_seconds"] = 3600
        self.assertEqual(compile_at(doc, NOW)["state"], READY)
        self.assertEqual(compile_at(doc, NOW.replace(microsecond=1))["state"], "HOLD_STALE_SOURCE")

    def test_single_source_dangling_supersedes_holds(self):
        doc = base(); doc["sources"][0]["supersedes_generation"] = "missing"
        self.assertEqual(compile_at(doc)["state"], "HOLD_EVIDENCE_CONFLICT")

    def test_active_generation_must_be_unique_terminal(self):
        doc = base()
        g1 = copy.deepcopy(doc["sources"][0])
        g2 = {**copy.deepcopy(g1), "generation":"g2", "observed_at":"2026-09-19T19:20:00Z", "source_sha256":A, "supersedes_generation":"g1"}
        g3 = {**copy.deepcopy(g1), "generation":"g3", "observed_at":"2026-09-19T19:30:00Z", "source_sha256":B, "supersedes_generation":"g2"}
        doc["sources"] = [g1, g2, g3]
        doc["active_source_generation"] = "g2"
        doc["compensation"][0]["source_generation"] = "g2"
        doc["acceptance_route"]["source_generation"] = "g2"
        doc["acceptance_route"]["observed_at"] = "2026-09-19T19:31:00Z"
        self.assertEqual(compile_at(doc)["state"], "HOLD_EVIDENCE_CONFLICT")

    def test_provider_class_cannot_change_across_generations(self):
        doc = base()
        g2 = {**copy.deepcopy(doc["sources"][0]), "generation":"g2", "observed_at":"2026-09-19T19:30:00Z", "source_sha256":A, "supersedes_generation":"g1", "provider_class":"RIVAL_PROVIDER"}
        doc["sources"].append(g2)
        doc["active_source_generation"] = "g2"
        doc["compensation"][0]["source_generation"] = "g2"
        doc["acceptance_route"]["source_generation"] = "g2"
        doc["acceptance_route"]["observed_at"] = "2026-09-19T19:31:00Z"
        self.assertEqual(compile_at(doc)["state"], "HOLD_EVIDENCE_CONFLICT")

    def test_compensation_and_acceptance_bind_active_generation(self):
        doc = base()
        g2 = {**copy.deepcopy(doc["sources"][0]), "generation":"g2", "observed_at":"2026-09-19T19:30:00Z", "source_sha256":A, "supersedes_generation":"g1"}
        doc["sources"].append(g2); doc["active_source_generation"] = "g2"
        self.assertEqual(compile_at(doc)["state"], "HOLD_INCOMPLETE_EVIDENCE")
        doc["acceptance_route"]["source_generation"] = "g2"
        doc["acceptance_route"]["observed_at"] = "2026-09-19T19:31:00Z"
        self.assertEqual(compile_at(doc)["state"], "HOLD_INCOMPLETE_EVIDENCE")
        doc["compensation"][0]["source_generation"] = "g2"
        self.assertEqual(compile_at(doc)["state"], READY)

    def test_semantic_reseal_cannot_hide_dnr(self):
        rec = compile_at(base())
        rec["opportunity"]["blockers"].append({
            "opportunity_id":"grantfox-flux-182", "blocker_id":"b9", "kind":"DNR",
            "source_ref":"owner:dnr", "source_sha256":Z, "observed_at":"2026-09-19T19:05:00.000000Z"
        })
        body = {k:v for k,v in rec.items() if k != "receipt_sha256"}
        rec["receipt_sha256"] = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",",":"), ensure_ascii=False).encode()).hexdigest()
        with self.assertRaises(IntakeError):
            verify_record(rec)

    def test_deep_nesting_fails_as_intake_error(self):
        raw = "[" * 1200 + "0" + "]" * 1200
        with self.assertRaises(IntakeError):
            parse_strict_json(raw)

    def test_failed_validation_does_not_reserve_destination(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "bundle"
            bad = base(); bad["sources"][0]["published_at"] = "2026-09-19T19:00:01Z"
            with self.assertRaises(IntakeError):
                write_bundle(bad, out, clock=lambda: NOW)
            self.assertFalse(out.exists())
            write_bundle(base(), out, clock=lambda: NOW)
            self.assertTrue((out / "record.json").exists())

    def test_intermediate_write_failure_leaves_no_destination(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "bundle"
            original = Path.write_bytes
            def failing_write(path, data):
                if path.name == "routing.md":
                    raise OSError("simulated write failure")
                return original(path, data)
            with patch.object(Path, "write_bytes", failing_write):
                with self.assertRaises(OSError):
                    write_bundle(base(), out, clock=lambda: NOW)
            self.assertFalse(out.exists())
            self.assertEqual(list(Path(td).glob(".bundle.stage-*")), [])
            write_bundle(base(), out, clock=lambda: NOW)
            self.assertTrue(out.exists())

    def test_competing_creator_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "bundle"
            original_mkdir = Path.mkdir
            raced = False

            def racing_mkdir(path, *args, **kwargs):
                nonlocal raced
                if path == out and not raced:
                    raced = True
                    original_mkdir(path, *args, **kwargs)
                    raise FileExistsError("simulated competing creator")
                return original_mkdir(path, *args, **kwargs)

            with patch.object(Path, "mkdir", racing_mkdir):
                with self.assertRaises(IntakeError):
                    write_bundle(base(), out, clock=lambda: NOW)

            self.assertTrue(out.is_dir())
            self.assertEqual(list(out.iterdir()), [])
            self.assertEqual(list(Path(td).glob(".bundle.stage-*")), [])

    def test_cli_compile_verify_and_hostile_tamper(self):
        from revenue.external_opportunity_intake import cli as cli_module
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            inp = td / "input.json"; out = td / "bundle"
            inp.write_text(json.dumps(base()))
            with redirect_stdout(io.StringIO()):
                self.assertEqual(cli_module.main(["compile-historical", str(inp), str(out), "--at", "2026-09-19T20:00:00Z"]), 0)
                self.assertEqual(cli_module.main(["verify", str(out / "record.json")]), 0)
            record = json.loads((out / "record.json").read_text())
            record["opportunity"]["blockers"].append({
                "opportunity_id":"grantfox-flux-182", "blocker_id":"b9", "kind":"DNR",
                "source_ref":"owner:dnr", "source_sha256":Z, "observed_at":"2026-09-19T19:05:00.000000Z"
            })
            body = {k:v for k,v in record.items() if k != "receipt_sha256"}
            record["receipt_sha256"] = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",",":"), ensure_ascii=False).encode()).hexdigest()
            bad = td / "bad.json"; bad.write_text(json.dumps(record))
            with self.assertRaises(SystemExit) as cm, redirect_stdout(io.StringIO()):
                cli_module.main(["verify", str(bad)])
            self.assertEqual(cm.exception.code, 2)


    def test_invalid_utf8_is_intake_error(self):
        with self.assertRaises(IntakeError):
            parse_strict_json(b"{\xff}")

    def test_acceptance_route_cannot_predate_bound_generation(self):
        doc = base()
        doc["acceptance_route"]["observed_at"] = "2026-09-19T18:59:59Z"
        with self.assertRaises(IntakeError):
            compile_at(doc)

    def test_incomplete_generation_bundle_still_renders_hold(self):
        doc = base()
        g2 = {**copy.deepcopy(doc["sources"][0]), "generation":"g2", "observed_at":"2026-09-19T19:30:00Z", "source_sha256":A, "supersedes_generation":"g1"}
        doc["sources"].append(g2)
        doc["active_source_generation"] = "g2"
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "bundle"
            record = write_bundle(doc, out, clock=lambda: NOW)
            self.assertEqual(record["state"], "HOLD_INCOMPLETE_EVIDENCE")
            self.assertIn("NO ACTIVE-GENERATION COMPENSATION EVIDENCE", (out / "routing.md").read_text())
            verify_record(parse_strict_json((out / "record.json").read_bytes()))


if __name__ == "__main__":
    unittest.main()
