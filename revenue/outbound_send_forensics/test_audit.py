import copy
import contextlib
import hashlib
import hmac
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import revenue.outbound_send_forensics.audit as audit
from revenue.outbound_connector_lease.key import compile_document

SCHEMA = "outbound-connector-lease/v1"
INPUT_SCHEMA = audit.INPUT_SCHEMA
LABEL_SCHEMA = audit.LABEL_INPUT_SCHEMA
LEGACY_SCHEMA = audit.LEGACY_INPUT_SCHEMA
TEST_KEY = bytes.fromhex("11" * 32)

def seam():
    return {
        "schema": SCHEMA,
        "buyer_scope": "Example.COM.",
        "opportunity": {"kind": "external", "authority": "Issuer.EXAMPLE.", "id": "RFP-04254"},
    }

def _mac(payload, key=TEST_KEY):
    return hmac.new(key, audit._canonical_bytes(payload), hashlib.sha256).hexdigest()

def send(
    event="msg-1",
    when="2026-09-14T01:20:00Z",
    status="sent",
    receipt="a" * 64,
    provider="gmail",
    key=TEST_KEY,
    seam_value=None,
):
    base = {
        "provider": provider,
        "event_id": event,
        "sent_at": when,
        "status": status,
        "receipt_sha256": receipt,
    }
    _, canonical = audit._timestamp(base["sent_at"], "x")
    normalized = {
        "provider": base["provider"].strip().casefold(),
        "event_id": base["event_id"].strip().casefold(),
        "sent_at": canonical,
        "status": base["status"].strip().casefold(),
        "receipt_sha256": base["receipt_sha256"],
    }
    return {
        **base,
        "attestation_hmac_sha256": _mac(
            audit._send_attestation_payload(
                normalized, compile_document(seam_value or seam())["seam_sha256"]
            ),
            key,
        ),
    }

def lease(
    s=None,
    when="2026-09-14T01:19:00Z",
    result="created",
    branch=None,
    receipt="b" * 64,
    base="c" * 40,
    repository=audit.CANONICAL_LEASE_REPOSITORY,
    key=TEST_KEY,
):
    s = s or seam()
    raw = {
        "repository_full_name": repository,
        "branch": branch or compile_document(s)["branch"],
        "created_at": when,
        "result": result,
        "base_sha": base,
        "receipt_sha256": receipt,
    }
    _, canonical = audit._timestamp(raw["created_at"], "x")
    normalized = {
        **raw,
        "repository_full_name": raw["repository_full_name"].strip().casefold(),
        "created_at": canonical,
    }
    return {
        **raw,
        "attestation_hmac_sha256": _mac(audit._lease_attestation_payload(normalized), key),
    }

def record(rid="r1", event="msg-1", s=None, send_kwargs=None, lease_value="default"):
    s = copy.deepcopy(s or seam())
    return {
        "record_id": rid,
        "seam": s,
        "send": send(event=event, seam_value=s, **(send_kwargs or {})),
        "lease_create": lease(s) if lease_value == "default" else lease_value,
    }

def doc(*rows, schema=INPUT_SCHEMA):
    return {"schema": schema, "records": list(rows)}

def label_send(event="msg-1", when="2026-09-14T01:20:00Z", authority="provider-receipt", status="sent", receipt="a"*64, provider="gmail"):
    return {
        "provider": provider,
        "event_id": event,
        "sent_at": when,
        "authority": authority,
        "status": status,
        "receipt_sha256": receipt,
    }

def label_lease(s=None, when="2026-09-14T01:19:00Z", authority="github-create-result", result="created", branch=None, receipt="b"*64, base="c"*40, repository=audit.CANONICAL_LEASE_REPOSITORY):
    s = s or seam()
    return {
        "repository_full_name": repository,
        "branch": branch or compile_document(s)["branch"],
        "created_at": when,
        "authority": authority,
        "result": result,
        "base_sha": base,
        "receipt_sha256": receipt,
    }

def label_record(rid="r1", event="msg-1"):
    s=seam()
    return {"record_id":rid,"seam":s,"send":label_send(event=event),"lease_create":label_lease(s)}

class AuditTests(unittest.TestCase):
    def current(self, document):
        return audit._audit_document(document, authority_key=TEST_KEY)

    def one(self, r):
        return self.current(doc(r))["receipts"][0]

    def test_protected_requires_host_attested_send_and_lease(self):
        o = self.one(record())
        self.assertEqual(o["classification"], audit.CLASS_PROTECTED)
        self.assertTrue(o["send_authority_authenticated"])
        self.assertTrue(o["lease_authority_authenticated"])
        self.assertTrue(o["dnr"])

    def test_noncanonical_repository_is_untrusted_even_when_attested(self):
        o = self.one(record(lease_value=lease(repository="woahwhattheheck/commons-fork")))
        self.assertEqual(o["classification"], audit.CLASS_UNTRUSTED)
        self.assertIn("canonical repository", o["reasons"][0])

    def test_repository_normalization_and_validation(self):
        self.assertEqual(
            self.one(record(lease_value=lease(repository=" WoahWhatTheHeck/Commons ")))["classification"],
            audit.CLASS_PROTECTED,
        )
        for v in (True, "commons", "owner/repo/extra", "https://github.com/woahwhattheheck/commons"):
            bad = lease()
            bad["repository_full_name"] = v
            with self.subTest(v=v), self.assertRaisesRegex(audit.ForensicsError, "repository"):
                self.one(record(lease_value=bad))

    def test_forged_send_attestation_cannot_mint_authority(self):
        r = record()
        r["send"]["attestation_hmac_sha256"] = "0" * 64
        o = self.one(r)
        self.assertEqual(o["classification"], audit.CLASS_UNTRUSTED)
        self.assertFalse(o["send_authority_authenticated"])

    def test_forged_lease_attestation_cannot_mint_authority(self):
        r = record()
        r["lease_create"]["attestation_hmac_sha256"] = "0" * 64
        o = self.one(r)
        self.assertEqual(o["classification"], audit.CLASS_UNTRUSTED)
        self.assertFalse(o["lease_authority_authenticated"])

    def test_attestation_binds_exact_send_generation(self):
        r = record()
        r["send"]["receipt_sha256"] = "9" * 64
        o = self.one(r)
        self.assertEqual(o["classification"], audit.CLASS_UNTRUSTED)
        r = record()
        r["send"]["sent_at"] = "2026-09-14T01:20:01Z"
        self.assertEqual(self.one(r)["classification"], audit.CLASS_UNTRUSTED)

    def test_send_attestation_cannot_be_transplanted_to_another_seam(self):
        r = record()
        altered = seam()
        altered["buyer_scope"] = "other.example"
        r["seam"] = altered
        o = self.one(r)
        self.assertEqual(o["classification"], audit.CLASS_UNTRUSTED)
        self.assertFalse(o["send_authority_authenticated"])

    def test_attestation_binds_exact_lease_generation(self):
        r = record()
        r["lease_create"]["base_sha"] = "9" * 40
        self.assertEqual(self.one(r)["classification"], audit.CLASS_UNTRUSTED)
        r = record()
        r["lease_create"]["repository_full_name"] = "woahwhattheheck/commons-fork"
        self.assertEqual(self.one(r)["classification"], audit.CLASS_UNTRUSTED)

    def test_attestation_field_mutation_matrix_fails_closed(self):
        send_mutations = [
            ("provider", "slack"),
            ("event_id", "msg-2"),
            ("sent_at", "2026-09-14T01:20:01Z"),
            ("status", "ambiguous"),
            ("receipt_sha256", "9" * 64),
        ]
        for field, value in send_mutations:
            r = record()
            r["send"][field] = value
            with self.subTest(kind="send", field=field):
                o = self.one(r)
                self.assertEqual(o["classification"], audit.CLASS_UNTRUSTED)
                self.assertFalse(o["send_authority_authenticated"])

        lease_mutations = [
            ("repository_full_name", "woahwhattheheck/commons-fork"),
            ("branch", "outbound-connector-lease/v1/" + "0" * 64),
            ("created_at", "2026-09-14T01:18:59Z"),
            ("result", "exists"),
            ("base_sha", "9" * 40),
            ("receipt_sha256", "8" * 64),
        ]
        for field, value in lease_mutations:
            r = record()
            r["lease_create"][field] = value
            with self.subTest(kind="lease", field=field):
                o = self.one(r)
                self.assertEqual(o["classification"], audit.CLASS_UNTRUSTED)
                self.assertFalse(o["lease_authority_authenticated"])

    def test_v2_caller_labels_are_claim_only(self):
        r = label_record()
        o = audit.audit_document(doc(r, schema=LABEL_SCHEMA))["receipts"][0]
        self.assertEqual(o["classification"], audit.CLASS_UNTRUSTED)
        self.assertFalse(o["send_authority_authenticated"])
        self.assertFalse(o["lease_authority_authenticated"])

    def test_v2_fake_trusted_labels_cannot_create_incident(self):
        a = label_record("a", "e1")
        b = label_record("b", "e2")
        o = audit.audit_document(doc(a,b,schema=LABEL_SCHEMA))
        self.assertEqual(o["summary"]["duplicate_seams"], 0)
        self.assertEqual(o["summary"]["duplicate_send_records"], 0)
        self.assertTrue(all(x["classification"] == audit.CLASS_UNTRUSTED for x in o["receipts"]))

    def test_v3_without_host_key_is_auditable_but_non_authoritative(self):
        o = audit.audit_document(doc(record()))["receipts"][0]
        self.assertEqual(o["classification"], audit.CLASS_UNTRUSTED)
        self.assertFalse(o["send_authority_authenticated"])
        self.assertFalse(o["lease_authority_authenticated"])

    def test_attested_duplicate_incident_excludes_untrusted_rows(self):
        a = record(rid="a", event="e1")
        b = record(rid="b", event="e2")
        forged = record(rid="forged", event="e3")
        forged["send"]["attestation_hmac_sha256"]="0"*64
        o = self.current(doc(a,b,forged))
        rows={x["record_id"]:x for x in o["receipts"]}
        self.assertEqual(o["summary"]["duplicate_seams"],1)
        self.assertEqual(o["summary"]["duplicate_send_records"],2)
        self.assertEqual(rows["a"]["same_seam_send_count"],2)
        self.assertEqual(rows["b"]["same_seam_send_count"],2)
        self.assertEqual(rows["forged"]["same_seam_send_count"],1)
        self.assertEqual(rows["forged"]["batch_flags"],[])

    def test_two_forged_rows_cannot_fabricate_incident(self):
        a=record(rid="a",event="e1"); b=record(rid="b",event="e2")
        a["send"]["attestation_hmac_sha256"]="0"*64
        b["send"]["attestation_hmac_sha256"]="0"*64
        o=self.current(doc(a,b))
        self.assertEqual(o["summary"]["duplicate_seams"],0)

    def test_chronology_equal_and_later_are_post_send(self):
        for t in ("2026-09-14T01:20:00Z","2026-09-14T01:21:00Z"):
            with self.subTest(t=t):
                self.assertEqual(
                    self.one(record(lease_value=lease(when=t)))["classification"],
                    audit.CLASS_POST_SEND,
                )

    def test_missing_mismatch_and_noncreate(self):
        self.assertEqual(self.one(record(lease_value=None))["classification"], audit.CLASS_MISSING)
        self.assertEqual(
            self.one(record(lease_value=lease(branch="outbound-connector-lease/v1/"+"0"*64)))["classification"],
            audit.CLASS_MISMATCH,
        )
        for result in ("exists","ambiguous","failed"):
            with self.subTest(result=result):
                self.assertEqual(self.one(record(lease_value=lease(result=result)))["classification"], audit.CLASS_UNTRUSTED)

    def test_timestamps_are_strict_and_normalized(self):
        o=self.one(record(send_kwargs={"when":"2026-09-13T21:20:00-04:00"}, lease_value=lease(when="2026-09-14T01:19:59+00:00")))
        self.assertEqual(o["classification"],audit.CLASS_PROTECTED)
        self.assertEqual(o["send_at_utc"],"2026-09-14T01:20:00.000000Z")
        for t in ("2026-09-14T01:20:00","2026-09-14 01:20:00+00:00"):
            with self.subTest(t=t), self.assertRaisesRegex(audit.ForensicsError,"strict RFC3339"):
                self.one(record(send_kwargs={"when":t}))

    def test_malformed_branch_hash_and_types_rejected(self):
        b=lease(); b["branch"]="outbound-connector-lease/v1/not-a-hash"
        with self.assertRaisesRegex(audit.ForensicsError,"64-lowercase-hex"): self.one(record(lease_value=b))
        with self.assertRaisesRegex(audit.ForensicsError,"64 lowercase hex"): self.one(record(send_kwargs={"receipt":"A"*64}))
        b=lease(); b["base_sha"]="c"*39
        with self.assertRaisesRegex(audit.ForensicsError,"40 lowercase hex"): self.one(record(lease_value=b))
        r=record(); r["send"]["event_id"]=True
        with self.assertRaisesRegex(audit.ForensicsError,"must be a string"): self.one(r)

    def test_top_level_schema_types_fail_closed_without_typeerror(self):
        for value in ([], {}, True, 1, None):
            with self.subTest(value=value):
                with self.assertRaisesRegex(audit.ForensicsError,"input.schema must be a string"):
                    audit.audit_document({"schema":value,"records":[label_record()]})

    def test_cli_malformed_schema_type_returns_hold_2_no_traceback(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"bad.json"
            p.write_text(json.dumps({"schema":[],"records":[label_record()]}))
            err=io.StringIO()
            with contextlib.redirect_stderr(err):
                rc=audit.main([str(p)])
            self.assertEqual(rc,2)
            self.assertIn("HOLD:",err.getvalue())
            self.assertNotIn("Traceback",err.getvalue())

    def test_strict_json_and_empty_batch(self):
        with self.assertRaisesRegex(audit.ForensicsError,"duplicate JSON key"):
            audit.audit_json('{"schema":"outbound-send-forensics/v2","schema":"outbound-send-forensics/v2","records":[]}')
        with self.assertRaisesRegex(audit.ForensicsError,"non-finite"):
            audit.audit_json('{"schema":"outbound-send-forensics/v2","records":NaN}')
        with self.assertRaisesRegex(audit.ForensicsError,"non-empty array"):
            audit.audit_document(doc(schema=LABEL_SCHEMA))

    def test_duplicate_ids_and_provider_events_rejected(self):
        with self.assertRaisesRegex(audit.ForensicsError,"duplicate record_id"):
            self.current(doc(record(rid="Case-A",event="a"),record(rid="case-a",event="b")))
        with self.assertRaisesRegex(audit.ForensicsError,"duplicate provider event"):
            self.current(doc(record(rid="a",event="same"),record(rid="b",event="same")))
        with self.assertRaisesRegex(audit.ForensicsError,"contradictory duplicate provider event"):
            self.current(doc(record(rid="a",event="same"),record(rid="b",event="same",send_kwargs={"when":"2026-09-14T01:21:00Z"})))

    def test_order_independent_and_deterministic(self):
        a=record(rid="a",event="e1"); b=record(rid="b",event="e2")
        x=self.current(doc(a,b)); y=self.current(doc(b,a))
        self.assertEqual(x["batch_sha256"],y["batch_sha256"])
        self.assertEqual(x["receipts"],y["receipts"])
        self.assertEqual(x,self.current(doc(a,b)))

    def test_seam_normalization_uses_landed_compiler(self):
        s1=seam(); s2=copy.deepcopy(s1)
        s2["buyer_scope"]="example.com"; s2["opportunity"]["authority"]="issuer.example"; s2["opportunity"]["id"]="rfp-04254"
        self.assertEqual(compile_document(s1)["branch"],compile_document(s2)["branch"])
        self.assertEqual(self.one(record(s=s1,lease_value=lease(s2)))["classification"],audit.CLASS_PROTECTED)

    def test_legacy_v1_remains_readable_but_non_authoritative(self):
        r=label_record(); r["lease_create"].pop("repository_full_name")
        o=audit.audit_document(doc(r,schema=LEGACY_SCHEMA))["receipts"][0]
        self.assertEqual(o["classification"],audit.CLASS_UNTRUSTED)
        self.assertEqual(o["source_input_schema"],LEGACY_SCHEMA)

    def test_host_key_loader_requires_fixed_schema_secret_and_private_mode(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"authority-key.json"
            p.write_text(json.dumps({"schema":audit.AUTHORITY_KEY_SCHEMA,"key_hex":TEST_KEY.hex()}))
            if os.name=="posix": os.chmod(p,0o600)
            with mock.patch.object(audit,"HOST_AUTHORITY_KEY_PATH",p):
                self.assertEqual(audit._read_host_authority_key(),TEST_KEY)
                result=audit.audit_current_document(doc(record()))
                self.assertEqual(result["receipts"][0]["classification"],audit.CLASS_PROTECTED)
            if os.name=="posix":
                os.chmod(p,0o644)
                with mock.patch.object(audit,"HOST_AUTHORITY_KEY_PATH",p):
                    with self.assertRaisesRegex(audit.ForensicsError,"group/other"):
                        audit._read_host_authority_key()

    def test_host_key_ancestor_symlink_refused_on_posix(self):
        if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
            self.skipTest("descriptor path walk unavailable")
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            real = td / "real"
            real.mkdir()
            key = real / "authority-key.json"
            key.write_text(json.dumps({"schema":audit.AUTHORITY_KEY_SCHEMA,"key_hex":TEST_KEY.hex()}))
            os.chmod(key, 0o600)
            alias = td / "alias"
            alias.symlink_to(real, target_is_directory=True)
            with mock.patch.object(audit, "HOST_AUTHORITY_KEY_PATH", alias / "authority-key.json"):
                with self.assertRaisesRegex(audit.ForensicsError, "ancestor"):
                    audit._read_host_authority_key()

    def test_host_key_symlink_refused_where_supported(self):
        if not hasattr(os,"O_NOFOLLOW"):
            self.skipTest("O_NOFOLLOW unavailable")
        with tempfile.TemporaryDirectory() as td:
            td=Path(td)
            target=td/"real.json"; target.write_text(json.dumps({"schema":audit.AUTHORITY_KEY_SCHEMA,"key_hex":TEST_KEY.hex()}))
            if os.name=="posix": os.chmod(target,0o600)
            link=td/"link.json"; link.symlink_to(target)
            with mock.patch.object(audit,"HOST_AUTHORITY_KEY_PATH",link):
                with self.assertRaisesRegex(audit.ForensicsError,"unavailable"):
                    audit._read_host_authority_key()

if __name__=="__main__":
    unittest.main()
