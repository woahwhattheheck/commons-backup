import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

from revenue.verified_paid_proof.core import CompiledProof
from revenue.verified_paid_proof.verified_paid_proof import (
    ProofError,
    compile_proof,
    public_json,
    public_payload,
    strict_json_loads,
    write_outputs,
)
import revenue.verified_paid_proof.verified_paid_proof as public_api


def permission(granted=False, *refs):
    return {"granted": granted, "evidence_refs": list(refs)}


def base_record():
    return {
        "schema_version": 1,
        "engagement_id": "eng.synthetic.001",
        "customer": {
            "display_name": "Synthetic Buyer",
            "logo_ref": "evidence:logo:1",
        },
        "payment": {
            "status": "SETTLED",
            "amount_minor": 9000,
            "currency": "USD",
            "currency_decimals": 2,
            "settled_at": "2026-09-14T18:00:00-04:00",
            "evidence_refs": ["stripe:pi_synthetic_1"],
        },
        "delivery": {
            "status": "ACCEPTED",
            "accepted_at": "2026-09-14T18:30:00-04:00",
            "evidence_refs": ["email:synthetic-acceptance-1"],
        },
        "quote": {
            "text": "The bounded artifact met the requested acceptance checks.",
            "evidence_ref": "email:synthetic-quote-1",
        },
        "outcomes": [
            {
                "claim": "Buyer confirmed the requested acceptance checks passed.",
                "evidence_refs": ["email:synthetic-acceptance-1"],
                "publication_permission": permission(False),
            }
        ],
        "permissions": {
            "public_proof": permission(False),
            "payment_fact": permission(False),
            "customer_identity": permission(False),
            "logo": permission(False),
            "exact_amount": permission(False),
            "delivery_acceptance": permission(False),
            "quote": permission(False),
        },
        "revocation": {"revoked": False, "evidence_refs": []},
    }


def grant_all(record):
    for scope in (
        "public_proof",
        "payment_fact",
        "customer_identity",
        "logo",
        "exact_amount",
        "delivery_acceptance",
        "quote",
    ):
        record["permissions"][scope] = permission(
            True, f"email:permission:{scope}"
        )
    record["outcomes"][0]["publication_permission"] = permission(
        True, "email:permission:outcome"
    )
    return record


class PaidProofTests(unittest.TestCase):
    def assert_public_projection_closed(self, proof):
        self.assertEqual(proof["status"], "HOLD")
        projection = proof["public_projection"]
        self.assertEqual(
            projection,
            {
                "status": "HOLD",
                "proof_id": None,
                "customer": None,
                "paid_engagement": None,
                "exact_amount": None,
                "delivery_accepted": None,
                "quote": None,
                "logo_ref": None,
                "outcomes": [],
            },
        )

    def test_self_attested_settlement_is_not_verified(self):
        proof = compile_proof(base_record()).proof
        self.assert_public_projection_closed(proof)
        self.assertIn("evidence_provenance_unverified", proof["blockers"])
        private = proof["private_evidence"]
        self.assertFalse(private["evidence_provenance"]["verified"])
        self.assertFalse(private["payment_verified"])
        self.assertTrue(private["payment_asserted"])
        self.assertEqual(
            private["unverified_candidate"]["status"],
            "PRIVATE_VERIFIED",
        )

    def test_provider_looking_refs_cannot_mint_public_named(self):
        record = grant_all(base_record())
        record["payment"]["evidence_refs"] = [
            "stripe:pi_real_looking_but_caller_authored"
        ]
        proof = compile_proof(record).proof
        self.assert_public_projection_closed(proof)
        candidate = proof["private_evidence"]["unverified_candidate"]
        self.assertEqual(candidate["status"], "PUBLIC_NAMED")
        self.assertEqual(
            candidate["public_projection"]["customer"],
            "Synthetic Buyer",
        )
        self.assertFalse(proof["private_evidence"]["payment_verified"])

    def test_public_anonymous_candidate_remains_private(self):
        record = base_record()
        record["permissions"]["public_proof"] = permission(
            True, "email:permission:public"
        )
        record["permissions"]["payment_fact"] = permission(
            True, "email:permission:payment"
        )
        proof = compile_proof(record).proof
        self.assert_public_projection_closed(proof)
        candidate = proof["private_evidence"]["unverified_candidate"]
        self.assertEqual(candidate["status"], "PUBLIC_ANONYMOUS")
        self.assertTrue(
            candidate["public_projection"]["customer"].startswith(
                "anonymous-customer-"
            )
        )
        self.assertNotIn(
            "Synthetic Buyer",
            json.dumps(proof["public_projection"]),
        )

    def test_public_artifacts_are_content_free_even_for_granted_hostile_input(self):
        record = grant_all(base_record())
        record["customer"]["display_name"] = (
            "PRIVATE BUYER\n# FORGED PUBLIC HEADING [click](https://evil.invalid)"
        )
        record["quote"]["text"] = "FORGED QUOTE @buyer https://evil.invalid"
        record["outcomes"][0]["claim"] = (
            "PRIVATE OUTCOME\n# FORGED OUTCOME HEADING"
        )
        compiled = compile_proof(record)
        public_blob = compiled.markdown + public_json(compiled)
        for secret in (
            "PRIVATE BUYER",
            "FORGED PUBLIC HEADING",
            "evil.invalid",
            "FORGED QUOTE",
            "@buyer",
            "PRIVATE OUTCOME",
            "FORGED OUTCOME HEADING",
            "Synthetic Buyer",
            "USD 90.00",
        ):
            self.assertNotIn(secret, public_blob)
        internal_blob = compiled.proof_json()
        self.assertIn("PRIVATE BUYER", internal_blob)
        self.assertIn("PRIVATE OUTCOME", internal_blob)

    def test_nonpublic_outcome_claim_is_not_echoed_in_top_level_metadata(self):
        record = base_record()
        private_claim = "PRIVATE BUYER OUTCOME MUST NOT SHIP"
        record["outcomes"][0]["claim"] = private_claim
        compiled = compile_proof(record)
        self.assertNotIn(private_claim, compiled.proof["withheld"])
        self.assertNotIn(private_claim, compiled.markdown)
        self.assertIn(
            "outcome_claim",
            compiled.proof["private_evidence"]["unverified_candidate"]["withheld"],
        )

    def test_public_renderer_is_not_exposed(self):
        self.assertFalse(hasattr(public_api, "render_markdown"))

    def test_mutated_compiled_proof_cannot_mint_release(self):
        compiled = compile_proof(base_record())
        compiled.proof["status"] = "PUBLIC_NAMED"
        compiled.proof["public_projection"] = {
            "status": "PUBLIC_NAMED",
            "proof_id": "proof-forged",
            "customer": "Forged",
            "paid_engagement": True,
            "exact_amount": "USD 9000000.00",
            "delivery_accepted": True,
            "quote": "FORGED",
            "logo_ref": None,
            "outcomes": [{"claim": "FORGED"}],
        }
        with self.assertRaises(ProofError):
            public_payload(compiled)
        with self.assertRaises(ProofError):
            public_json(compiled)

    def test_manual_compiledproof_cannot_mint_release(self):
        forged = CompiledProof(
            proof={
                "schema_version": 3,
                "policy_version": "verified-paid-proof/v3",
                "status": "PUBLIC_NAMED",
                "blockers": [],
                "public_projection": {"status": "PUBLIC_NAMED"},
                "private_evidence": {},
                "public_release": {},
                "receipt_sha256": "0" * 64,
            },
            markdown="Paid engagement verified",
            receipt_sha256="0" * 64,
        )
        with self.assertRaises(ProofError):
            public_payload(forged)

    def test_public_payload_returns_copy(self):
        compiled = compile_proof(base_record())
        first = public_payload(compiled)
        first["release_state"] = "FORGED"
        second = public_payload(compiled)
        self.assertEqual(second["release_state"], "NO_PUBLIC_CLAIM")

    def test_public_receipt_is_deterministic_and_public_only(self):
        a = compile_proof(base_record())
        b = compile_proof(grant_all(base_record()))
        self.assertEqual(
            public_payload(a)["public_receipt_sha256"],
            public_payload(b)["public_receipt_sha256"],
        )
        self.assertNotEqual(a.receipt_sha256, b.receipt_sha256)

    def test_v3_receipt_and_schema_mark_new_semantics(self):
        compiled = compile_proof(base_record())
        self.assertEqual(
            compiled.proof["policy_version"],
            "verified-paid-proof/v3",
        )
        self.assertEqual(compiled.proof["schema_version"], 3)
        self.assertEqual(compiled.proof["status"], "HOLD")
        self.assertEqual(
            compiled.proof["public_release"]["release_state"],
            "NO_PUBLIC_CLAIM",
        )
        self.assertEqual(len(compiled.receipt_sha256), 64)

    def test_payment_only_never_implies_satisfaction(self):
        record = base_record()
        record["delivery"] = {
            "status": "NOT_DELIVERED",
            "accepted_at": None,
            "evidence_refs": [],
        }
        record["quote"] = {"text": None, "evidence_ref": None}
        record["outcomes"] = []
        compiled = compile_proof(record)
        public_blob = (compiled.markdown + public_json(compiled)).lower()
        self.assertNotIn("satisfied", public_blob)
        self.assertNotIn("recommend", public_blob)
        self.assert_public_projection_closed(compiled.proof)

    def test_accepted_delivery_no_public_permission_is_only_candidate(self):
        proof = compile_proof(base_record()).proof
        self.assert_public_projection_closed(proof)
        self.assertFalse(proof["private_evidence"]["delivery_accepted"])
        self.assertTrue(
            proof["private_evidence"]["delivery_accepted_asserted"]
        )

    def test_quote_requires_source_pair(self):
        record = base_record()
        record["quote"]["evidence_ref"] = None
        with self.assertRaises(ProofError):
            compile_proof(record)

    def test_granted_quote_permission_requires_quote(self):
        record = base_record()
        record["quote"] = {"text": None, "evidence_ref": None}
        record["permissions"]["quote"] = permission(
            True, "email:permission:quote"
        )
        with self.assertRaises(ProofError):
            compile_proof(record)

    def test_outcome_requires_evidence(self):
        record = base_record()
        record["outcomes"][0]["evidence_refs"] = []
        with self.assertRaises(ProofError):
            compile_proof(record)

    def test_revocation_forces_candidate_hold(self):
        record = base_record()
        record["permissions"]["public_proof"] = permission(
            True, "email:permission:public"
        )
        record["permissions"]["payment_fact"] = permission(
            True, "email:permission:payment"
        )
        record["revocation"] = {
            "revoked": True,
            "evidence_refs": ["email:revocation:1"],
        }
        proof = compile_proof(record).proof
        self.assert_public_projection_closed(proof)
        self.assertIn("publication_permission_revoked", proof["blockers"])
        self.assertEqual(
            proof["private_evidence"]["unverified_candidate"]["status"],
            "HOLD",
        )

    def test_false_revocation_label_does_not_create_authority(self):
        proof = compile_proof(grant_all(base_record())).proof
        self.assert_public_projection_closed(proof)
        self.assertIn("evidence_provenance_unverified", proof["blockers"])

    def test_bool_is_not_integer_amount(self):
        record = base_record()
        record["payment"]["amount_minor"] = True
        with self.assertRaises(ProofError):
            compile_proof(record)

    def test_duplicate_json_keys_rejected(self):
        with self.assertRaises(ProofError):
            strict_json_loads(
                '{"schema_version":1,"schema_version":1}'
            )

    def test_float_money_rejected(self):
        text = json.dumps(base_record()).replace(
            '"amount_minor": 9000',
            '"amount_minor": 90.0',
        )
        with self.assertRaises(ProofError):
            strict_json_loads(text)

    def test_negative_money_rejected(self):
        record = base_record()
        record["payment"]["amount_minor"] = -1
        with self.assertRaises(ProofError):
            compile_proof(record)

    def test_non_settled_cannot_smuggle_amount(self):
        record = base_record()
        record["payment"]["status"] = "PENDING"
        with self.assertRaises(ProofError):
            compile_proof(record)

    def test_permission_true_requires_evidence(self):
        record = base_record()
        record["permissions"]["public_proof"] = permission(True)
        with self.assertRaises(ProofError):
            compile_proof(record)

    def test_irrelevant_input_order_is_deterministic(self):
        a = base_record()
        a["payment"]["evidence_refs"] = ["stripe:z", "stripe:a"]
        a["outcomes"].append(
            {
                "claim": "A second synthetic asserted fact.",
                "evidence_refs": ["evidence:z", "evidence:a"],
                "publication_permission": permission(False),
            }
        )
        b = copy.deepcopy(a)
        b["payment"]["evidence_refs"].reverse()
        b["outcomes"].reverse()
        for outcome in b["outcomes"]:
            outcome["evidence_refs"].reverse()
        self.assertEqual(
            compile_proof(a).receipt_sha256,
            compile_proof(b).receipt_sha256,
        )
        self.assertEqual(
            compile_proof(a).proof_json(),
            compile_proof(b).proof_json(),
        )

    def test_receipt_changes_on_material_permission_change(self):
        a = base_record()
        b = copy.deepcopy(a)
        b["permissions"]["public_proof"] = permission(
            True, "email:permission:public"
        )
        b["permissions"]["payment_fact"] = permission(
            True, "email:permission:payment"
        )
        self.assertNotEqual(
            compile_proof(a).receipt_sha256,
            compile_proof(b).receipt_sha256,
        )

    def test_write_outputs_splits_public_and_internal_custody(self):
        compiled = compile_proof(grant_all(base_record()))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            internal = root / "internal"
            public = root / "public"
            write_outputs(compiled, internal, public)
            self.assertEqual(
                sorted(p.name for p in internal.iterdir()),
                ["proof.json", "receipt.sha256"],
            )
            self.assertEqual(
                sorted(p.name for p in public.iterdir()),
                ["proof.md", "public.json", "receipt.sha256"],
            )
            public_blob = "".join(
                p.read_text(encoding="utf-8")
                for p in public.iterdir()
            )
            self.assertNotIn("Synthetic Buyer", public_blob)
            self.assertNotIn("stripe:pi_synthetic_1", public_blob)
            internal_blob = (internal / "proof.json").read_text(encoding="utf-8")
            self.assertIn("Synthetic Buyer", internal_blob)
            self.assertIn("stripe:pi_synthetic_1", internal_blob)

    def test_write_outputs_rejects_colocation_nesting_and_overwrite(self):
        compiled = compile_proof(base_record())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(ProofError):
                write_outputs(compiled, root / "same", root / "same")
            with self.assertRaises(ProofError):
                write_outputs(compiled, root / "parent", root / "parent" / "public")
            (root / "existing").mkdir()
            with self.assertRaises(ProofError):
                write_outputs(compiled, root / "existing", root / "public")

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink unsupported")
    def test_write_outputs_rejects_symlink_ancestry(self):
        compiled = compile_proof(base_record())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "target"
            target.mkdir()
            link = root / "link"
            try:
                os.symlink(target, link, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("symlink creation unavailable")
            with self.assertRaises(ProofError):
                write_outputs(compiled, link / "internal", root / "public")

    def test_optimized_python_semantics_match(self):
        record = grant_all(base_record())
        with tempfile.TemporaryDirectory() as tmp:
            input_path = Path(tmp) / "input.json"
            input_path.write_text(
                json.dumps(record),
                encoding="utf-8",
            )
            common = [
                "-m",
                "revenue.verified_paid_proof.verified_paid_proof",
                str(input_path),
                "--json",
            ]
            normal = subprocess.run(
                [sys.executable, *common],
                check=True,
                capture_output=True,
                text=True,
                cwd=ROOT,
            )
            optimized = subprocess.run(
                [sys.executable, "-O", *common],
                check=True,
                capture_output=True,
                text=True,
                cwd=ROOT,
            )
            self.assertEqual(normal.stdout, optimized.stdout)
            output = json.loads(normal.stdout)
            self.assertEqual(output["status"], "HOLD")
            self.assertIn(
                "evidence_provenance_unverified",
                output["blockers"],
            )

    def test_public_json_cli_is_content_free(self):
        record = grant_all(base_record())
        with tempfile.TemporaryDirectory() as tmp:
            input_path = Path(tmp) / "input.json"
            input_path.write_text(json.dumps(record), encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "revenue.verified_paid_proof.verified_paid_proof",
                    str(input_path),
                    "--public-json",
                ],
                check=True,
                capture_output=True,
                text=True,
                cwd=ROOT,
            )
            payload = json.loads(result.stdout)
            self.assertEqual(payload["release_state"], "NO_PUBLIC_CLAIM")
            self.assertNotIn("Synthetic Buyer", result.stdout)
            self.assertNotIn("9000", result.stdout)


if __name__ == "__main__":
    unittest.main()
