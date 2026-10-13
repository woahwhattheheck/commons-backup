from __future__ import annotations

import copy
import dis
import hashlib
import inspect
import json
import types
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import validate_response_kit as validator  # noqa: E402


class ResponseKitValidatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = validator.load_manifest_text(
            (HERE / "readiness_manifest.json").read_text(encoding="utf-8")
        )
        cls.catalog = validator.load_catalog_text(
            (HERE / "evidence_catalog.json").read_text(encoding="utf-8")
        )

    def test_current_manifest_is_hold_with_source_owned_freshness_receipt(self) -> None:
        result = validator.evaluate_manifest(
            copy.deepcopy(self.manifest), copy.deepcopy(self.catalog)
        )
        self.assertEqual(result.status, "HOLD")
        states = {gate.gate_id: gate.state for gate in result.gates}
        self.assertEqual(states["source_freshness"], "RESOLVED")
        self.assertEqual(states["partner_legal_role_and_consent"], "OPEN")
        self.assertEqual(states["commercial_model_and_approved_prices"], "DRAFTED")

    def test_arbitrary_plausible_prose_cannot_mint_ready(self) -> None:
        payload = copy.deepcopy(self.manifest)
        for gate in payload["gates"]:
            gate["state"] = "RESOLVED"
            gate["evidence_note"] = (
                f"verified evidence receipt for {gate['id']} from a credible partner"
            )
            if gate["id"] != "source_freshness":
                gate["evidence_refs"] = []
        with self.assertRaisesRegex(ValueError, "typed receipt"):
            validator.evaluate_manifest(payload, copy.deepcopy(self.catalog))

    def test_cross_gate_receipt_transplant_is_rejected(self) -> None:
        payload = copy.deepcopy(self.manifest)
        gate = next(
            g for g in payload["gates"]
            if g["id"] == "partner_legal_role_and_consent"
        )
        gate["state"] = "RESOLVED"
        gate["evidence_note"] = "partner allegedly consented"
        gate["evidence_refs"] = ["scwdb-rfp-index-2026-09-17"]
        with self.assertRaisesRegex(ValueError, "cross-gate receipt transplant"):
            validator.evaluate_manifest(payload, copy.deepcopy(self.catalog))

    def test_same_claim_digest_relabel_is_rejected(self) -> None:
        catalog = copy.deepcopy(self.catalog)
        original = copy.deepcopy(catalog["receipts"][0])
        original.update({
            "receipt_id": "relabelled-partner-consent",
            "gate_id": "partner_legal_role_and_consent",
            "kind": "partner_consent",
        })
        catalog["receipts"].append(original)
        with self.assertRaisesRegex(ValueError, "digest reused/relabelled"):
            validator._index_catalog(catalog)

    def test_claim_digest_mismatch_is_rejected(self) -> None:
        catalog = copy.deepcopy(self.catalog)
        catalog["receipts"][0]["claim"]["checked_on"] = "2026-09-16"
        with self.assertRaisesRegex(ValueError, "claim digest mismatch"):
            validator._index_catalog(catalog)

    def test_stale_or_modified_catalog_generation_is_rejected(self) -> None:
        catalog = copy.deepcopy(self.catalog)
        catalog["generation"] = "2026-09-17T21:31:00-04:00"
        with self.assertRaisesRegex(ValueError, "catalog generation mismatch"):
            validator.verify_catalog_root(catalog)

    def test_manifest_catalog_root_mismatch_is_rejected(self) -> None:
        payload = copy.deepcopy(self.manifest)
        payload["evidence_catalog_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "stale or untrusted"):
            validator.evaluate_manifest(payload, copy.deepcopy(self.catalog))

    def test_source_receipt_cannot_be_relabelled_to_new_checked_date(self) -> None:
        payload = copy.deepcopy(self.manifest)
        payload["source_checked_on"] = "2026-09-18"
        with self.assertRaisesRegex(ValueError, "does not bind"):
            validator.evaluate_manifest(payload, copy.deepcopy(self.catalog))

    def test_three_reference_gate_requires_three_distinct_typed_receipts(self) -> None:
        payload = copy.deepcopy(self.manifest)
        gate = next(
            g for g in payload["gates"] if g["id"] == "three_comparable_references"
        )
        gate["state"] = "RESOLVED"
        gate["evidence_note"] = "three references allegedly verified"
        gate["evidence_refs"] = ["scwdb-rfp-index-2026-09-17"]
        with self.assertRaisesRegex(ValueError, "at least 3 typed receipt"):
            validator.evaluate_manifest(payload, copy.deepcopy(self.catalog))

    def test_open_gate_cannot_carry_pseudo_evidence(self) -> None:
        payload = copy.deepcopy(self.manifest)
        gate = next(
            g for g in payload["gates"]
            if g["id"] == "partner_legal_role_and_consent"
        )
        gate["evidence_note"] = "someone probably agreed"
        with self.assertRaisesRegex(ValueError, "OPEN must carry no evidence"):
            validator.evaluate_manifest(payload, copy.deepcopy(self.catalog))

    def test_drafted_gate_cannot_cite_authority_receipt(self) -> None:
        payload = copy.deepcopy(self.manifest)
        gate = next(
            g for g in payload["gates"]
            if g["id"] == "commercial_model_and_approved_prices"
        )
        gate["evidence_refs"] = ["scwdb-rfp-index-2026-09-17"]
        with self.assertRaisesRegex(ValueError, "DRAFTED must not cite authority"):
            validator.evaluate_manifest(payload, copy.deepcopy(self.catalog))

    def test_duplicate_gate_id_is_invalid(self) -> None:
        payload = copy.deepcopy(self.manifest)
        payload["gates"].append(copy.deepcopy(payload["gates"][0]))
        with self.assertRaisesRegex(ValueError, "duplicate gate id"):
            validator.evaluate_manifest(payload, copy.deepcopy(self.catalog))

    def test_missing_gate_is_invalid(self) -> None:
        payload = copy.deepcopy(self.manifest)
        payload["gates"] = payload["gates"][:-1]
        with self.assertRaisesRegex(ValueError, "missing required gate"):
            validator.evaluate_manifest(payload, copy.deepcopy(self.catalog))

    def test_unexpected_gate_is_invalid(self) -> None:
        payload = copy.deepcopy(self.manifest)
        payload["gates"].append({
            "id": "invented_gate",
            "mandatory": True,
            "state": "OPEN",
            "evidence_note": "",
            "evidence_refs": [],
        })
        with self.assertRaisesRegex(ValueError, "id invalid"):
            validator.evaluate_manifest(payload, copy.deepcopy(self.catalog))

    def test_duplicate_json_key_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
            validator.load_manifest_text(
                '{"schema_version":2,"schema_version":2,"gates":[]}'
            )

    def test_procurement_identity_is_source_bound(self) -> None:
        for field, value in (
            ("buyer", "Other Board"),
            ("deadline_local", "2026-09-19T16:00:00-05:00"),
            ("official_rfp_index", "https://example.invalid/rfp"),
        ):
            payload = copy.deepcopy(self.manifest)
            payload[field] = value
            with self.assertRaisesRegex(ValueError, f"manifest {field} mismatch"):
                validator.evaluate_manifest(payload, copy.deepcopy(self.catalog))

    def test_public_verifier_signatures_do_not_accept_trust_overrides(self) -> None:
        self.assertEqual(
            list(inspect.signature(validator.verify_catalog_root).parameters),
            ["payload"],
        )
        self.assertEqual(
            list(inspect.signature(validator.evaluate_manifest).parameters),
            ["payload", "catalog_payload"],
        )
        with self.assertRaises(TypeError):
            validator.evaluate_manifest(  # type: ignore[call-arg]
                self.manifest, self.catalog, "0" * 64
            )

    def test_public_trust_constant_rebind_does_not_authorize_alt_catalog(self) -> None:
        catalog = copy.deepcopy(self.catalog)
        catalog["generation"] = "attacker-generation"
        old = validator.TRUSTED_CATALOG_SHA256
        try:
            validator.TRUSTED_CATALOG_SHA256 = validator._sha256_canonical(catalog)
            with self.assertRaisesRegex(ValueError, "catalog generation mismatch"):
                validator.verify_catalog_root(catalog)
        finally:
            validator.TRUSTED_CATALOG_SHA256 = old

    def _attacker_ready_pair(self) -> tuple[dict, dict]:
        manifest = copy.deepcopy(self.manifest)
        catalog = {
            "schema_version": 1,
            "catalog_id": "ky-ai-workforce-response-kit-evidence",
            "generation": "attacker-generation",
            "receipts": [copy.deepcopy(self.catalog["receipts"][0])],
        }
        refs_by_gate: dict[str, list[str]] = {
            "source_freshness": ["scwdb-rfp-index-2026-09-17"]
        }
        for gate in manifest["gates"]:
            gate_id = gate["id"]
            if gate_id == "source_freshness":
                continue
            count = 3 if gate_id == "three_comparable_references" else 1
            refs: list[str] = []
            kind = sorted(validator.ALLOWED_KINDS_BY_GATE[gate_id])[0]
            for number in range(count):
                receipt_id = f"attacker-{gate_id}-{number}"
                claim = {
                    "assertion": f"fabricated {gate_id} evidence {number}",
                    "subject": "attacker-controlled",
                }
                digest = validator._sha256_canonical(claim)
                catalog["receipts"].append({
                    "receipt_id": receipt_id,
                    "gate_id": gate_id,
                    "kind": kind,
                    "source_identity": "attacker://fabricated",
                    "source_generation": "attacker-generation",
                    "claim": claim,
                    "content_sha256": digest,
                })
                refs.append(receipt_id)
            refs_by_gate[gate_id] = refs

        for gate in manifest["gates"]:
            gate["state"] = "RESOLVED"
            gate["evidence_note"] = f"fabricated evidence for {gate['id']}"
            gate["evidence_refs"] = refs_by_gate[gate["id"]]
        return manifest, catalog

    def test_sealed_generation_survives_reviewer_requested_global_rebinds(self) -> None:
        saved_evaluate = validator.evaluate_manifest
        saved_verify = validator.verify_catalog_root
        attacker_manifest, attacker_catalog = self._attacker_ready_pair()

        original_module_hashlib = validator.hashlib
        original_module_json = validator.json
        original_std_sha256 = hashlib.sha256
        original_json_dumps = json.dumps
        original_globals = {}
        injected_names = (
            "_sha256_canonical",
            "_index_catalog",
            "CATALOG_SCHEMA_VERSION",
            "MANIFEST_SCHEMA_VERSION",
            "TRUSTED_CATALOG_SHA256",
            "ALLOWED_STATES",
            "REQUIRED_GATE_IDS",
            "ALLOWED_KINDS_BY_GATE",
            "MIN_RECEIPTS_BY_GATE",
            "HEX64_RE",
            "RECEIPT_ID_RE",
            "Receipt",
            "GateResult",
            "Evaluation",
            "all",
            "len",
            "next",
            "set",
            "sorted",
            "type",
        )
        for name in injected_names:
            original_globals[name] = validator.__dict__.get(name, None)

        class FakeHash:
            def hexdigest(self) -> str:
                return self_digest

        self_digest = validator.TRUSTED_CATALOG_SHA256

        def fake_sha256(_raw: bytes = b"") -> FakeHash:
            return FakeHash()

        try:
            # This reproduces the exact review class: module alias changes,
            # shared stdlib attribute changes, helper replacement, policy/root
            # replacement, constructor replacement, and built-in shadowing.
            validator.hashlib = types.SimpleNamespace(sha256=fake_sha256)
            hashlib.sha256 = fake_sha256
            validator.json = types.SimpleNamespace(
                dumps=lambda *_a, **_k: "{}",
                loads=lambda *_a, **_k: {},
                JSONDecodeError=json.JSONDecodeError,
            )
            json.dumps = lambda *_a, **_k: "{}"
            validator._sha256_canonical = lambda _value: "a" * 64
            validator._index_catalog = lambda _value: {}
            validator.CATALOG_SCHEMA_VERSION = 999
            validator.MANIFEST_SCHEMA_VERSION = 999
            validator.TRUSTED_CATALOG_SHA256 = "0" * 64
            validator.ALLOWED_STATES = {"RESOLVED"}
            validator.REQUIRED_GATE_IDS = set()
            validator.ALLOWED_KINDS_BY_GATE = {}
            validator.MIN_RECEIPTS_BY_GATE = {}
            validator.HEX64_RE = object()
            validator.RECEIPT_ID_RE = object()
            validator.Receipt = object
            validator.GateResult = object
            validator.Evaluation = object
            validator.all = lambda _iterable: True
            validator.len = lambda _value: 0
            validator.next = lambda _iterable: None
            validator.set = lambda _value=(): set()
            validator.sorted = lambda _value: []
            validator.type = lambda _value: object

            # A genuine trusted catalog still verifies under the saved callable,
            # proving it is using the import-generation primitives.
            trusted = saved_verify(copy.deepcopy(self.catalog))
            self.assertIn("scwdb-rfp-index-2026-09-17", trusted)

            # The reviewer's fabricated all-RESOLVED catalog still cannot cross
            # the captured catalog root despite every live alias above lying.
            with self.assertRaisesRegex(ValueError, "catalog generation mismatch"):
                saved_evaluate(attacker_manifest, attacker_catalog)

            # The legitimate checked-in package remains HOLD, not READY.
            current = saved_evaluate(
                copy.deepcopy(self.manifest), copy.deepcopy(self.catalog)
            )
            self.assertEqual(current.status, "HOLD")
        finally:
            validator.hashlib = original_module_hashlib
            validator.json = original_module_json
            hashlib.sha256 = original_std_sha256
            json.dumps = original_json_dumps
            for name, value in original_globals.items():
                if value is None and name not in {
                    "_sha256_canonical",
                    "_index_catalog",
                    "CATALOG_SCHEMA_VERSION",
                    "MANIFEST_SCHEMA_VERSION",
                    "TRUSTED_CATALOG_SHA256",
                    "ALLOWED_STATES",
                    "REQUIRED_GATE_IDS",
                    "ALLOWED_KINDS_BY_GATE",
                    "MIN_RECEIPTS_BY_GATE",
                    "HEX64_RE",
                    "RECEIPT_ID_RE",
                    "Receipt",
                    "GateResult",
                    "Evaluation",
                }:
                    validator.__dict__.pop(name, None)
                else:
                    validator.__dict__[name] = value

    def test_authority_closure_graph_has_zero_live_global_loads(self) -> None:
        seen: set[int] = set()

        def walk(fn) -> None:
            if id(fn) in seen:
                return
            seen.add(id(fn))
            live = [
                instruction.argval
                for instruction in dis.get_instructions(fn)
                if instruction.opname == "LOAD_GLOBAL"
            ]
            self.assertEqual([], live, f"{fn.__name__} has live globals: {live}")
            for constant in fn.__code__.co_consts:
                if isinstance(constant, types.CodeType):
                    nested_live = [
                        instruction.argval
                        for instruction in dis.get_instructions(constant)
                        if instruction.opname == "LOAD_GLOBAL"
                    ]
                    self.assertEqual(
                        [],
                        nested_live,
                        f"{fn.__name__}/{constant.co_name} has live globals: "
                        f"{nested_live}",
                    )
            for cell in fn.__closure__ or ():
                value = cell.cell_contents
                if isinstance(value, types.FunctionType):
                    walk(value)

        for public in (
            validator.evaluate_manifest,
            validator.verify_catalog_root,
            validator._sha256_canonical,
            validator._index_catalog,
        ):
            walk(public)

    def test_sealed_canonical_root_matches_checked_in_catalog(self) -> None:
        self.assertEqual(
            validator._sha256_canonical(copy.deepcopy(self.catalog)),
            "e176078ff89b3740bf5db5a9183a2cb0513365da7d74fc13f25425f325128315",
        )

    def test_cli_dispatch_keeps_captured_verifier_after_public_rebind(self) -> None:
        saved_main = validator.main
        original = validator.evaluate_manifest

        class FakeReady:
            status = "READY"
            ready = True
            gates = ()

        try:
            validator.evaluate_manifest = lambda *_args, **_kwargs: FakeReady()
            self.assertEqual(
                saved_main([
                    str(HERE / "readiness_manifest.json"),
                    "--catalog", str(HERE / "evidence_catalog.json"),
                ]),
                2,
            )
        finally:
            validator.evaluate_manifest = original

    def test_cli_returns_hold_and_modified_catalog_returns_invalid(self) -> None:
        self.assertEqual(
            validator.main([
                str(HERE / "readiness_manifest.json"),
                "--catalog", str(HERE / "evidence_catalog.json"),
            ]),
            2,
        )
        with tempfile.TemporaryDirectory() as td:
            tampered = copy.deepcopy(self.catalog)
            tampered["generation"] = "tampered"
            path = Path(td) / "catalog.json"
            path.write_text(json.dumps(tampered), encoding="utf-8")
            self.assertEqual(
                validator.main([
                    str(HERE / "readiness_manifest.json"),
                    "--catalog", str(path),
                ]),
                1,
            )


if __name__ == "__main__":
    unittest.main()
