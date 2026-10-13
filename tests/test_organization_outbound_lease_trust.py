from __future__ import annotations

import ast
import hashlib
import inspect
import json
import stat
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import revenue.organization_outbound_lease as package
import revenue.organization_outbound_lease.cli as cli
import revenue.organization_outbound_lease.core as core
import revenue.organization_outbound_lease.trust as trust
from revenue.organization_outbound_lease.core import RsaPublicKey
from revenue.organization_outbound_lease.stores import FileLeaseStore, GitHubContentsLeaseStore

ATTACKER_N_HEX = "e0d93d458bfda245a9d1404e84705e90a250cc520c26efa8de084532f7f7e3bfff9d8bf9f18dea68948538013ee0b1e18b86d6a4f2893c307c460ff5196184b0acfc6078fa0d735f9546d312e5d9baed7f09b34504a38e79d7be17c68a4cca6f9ac80da03f67e54a19b3f4d7f83e0d2c984327c6fd4a7f441e9772d54be7f46fc60f494821067e2849b13a639fd1cbaed1963f04e17a1dcc85902762f3ff7b571c128d25e4f68984ab63ac3a7fcb2ae75fe41339aa40e1fcb5c0beff47d32f64e5394fae20700423be6807189b68425e4a8773a42387c5347c1835f8c4efa8d8faf8a1963921230c9b40cefd04b555c6af273858acaebbf4800ca8db3ad940a5"
ATTACKER_D_HEX = "6e979b51fa3d99d38ee7abac12eb1c30228e003938ddebd210c75b95eaae44189b16f812cb5344a104b013b055277a8697b48e1d9a6792b1bc664f91fbd661c7ee85c1c3af25ef81eb6fe700ac0a302d8167198450784beb3508bc33fcb1317ebc503a977fa84ff866f502f0391af82adf876468b50bafd626ffd1cd04a545adca269a36b22e645b38ae5aa60df00f6698e0c45c7ac103d2456a958272140d410c14543559656ce9e3875e73e7d9126a1f3ed5f1d0206c9c1a92892cdcdc6147ed2d16c297b0835095b23d0c3da5a9dafe9a6304593d371c330c271493a6c0b9a7424fff4572d7a73369c0c79ea564a3be8034c2f842cccc39225cfcda19314f"
ATTACKER_N = int(ATTACKER_N_HEX, 16)
ATTACKER_D = int(ATTACKER_D_HEX, 16)
ATTACKER_E = 65537


def _utc(offset_seconds: int = 0) -> str:
    dt = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(seconds=offset_seconds)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _attacker_sign(message: bytes) -> str:
    k = (ATTACKER_N.bit_length() + 7) // 8
    digest_info = core.RSA_SHA256_DIGESTINFO_PREFIX + hashlib.sha256(message).digest()
    pad_len = k - len(digest_info) - 3
    encoded = b"\x00\x01" + (b"\xff" * pad_len) + b"\x00" + digest_info
    signature = pow(int.from_bytes(encoded, "big"), ATTACKER_D, ATTACKER_N)
    return signature.to_bytes(k, "big").hex()


class TrustBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.attacker = RsaPublicKey.from_hex(
            key_id="attacker-key",
            modulus_hex=ATTACKER_N_HEX,
            exponent=ATTACKER_E,
        )

    def _valid_attacker_ready_request(self):
        org = "1" * 64
        body = core.pressure_attestation_body({
            "schema": core.ATTESTATION_SCHEMA,
            "organizationFingerprint": org,
            "pressureReceiptSha256": "2" * 64,
            "authorityCommitment": "3" * 64,
            "ledgerCommitment": "4" * 64,
            "verifiedState": core.READY_STATE,
            "verifiedAt": _utc(-2),
        })
        attestation = {
            "body": body,
            "algorithm": "RS256-PKCS1-v1_5",
            "keyId": self.attacker.key_id,
            "signatureHex": _attacker_sign(core.PRESSURE_DOMAIN + core.canonical_json(body)),
        }
        verified = core.verify_pressure_attestation(
            attestation,
            self.attacker,
            organization_fingerprint=org,
        )
        self.assertEqual(verified["verifiedState"], core.READY_STATE)
        request = {
            "schema": core.ACQUIRE_SCHEMA,
            "claimId": "attacker-claim",
            "organizationFingerprint": org,
            "prospectFingerprint": "5" * 64,
            "routeCommitment": "6" * 64,
            "opportunityCommitment": "7" * 64,
            "holderCapabilityCommitment": core.holder_capability_commitment(b"c" * 32),
            "requestedAt": _utc(-1),
            "pressureAttestation": attestation,
        }
        return request

    def test_direct_core_import_is_same_hardened_public_acquire(self):
        self.assertIs(core.acquire_lease, package.acquire_lease)
        self.assertEqual(core.acquire_lease.__name__, "acquire_lease")

    def test_valid_attacker_keypair_and_ready_signature_cannot_replace_production_verifier(self):
        calls = []

        def opener(request):
            calls.append(request)
            raise AssertionError("production store must not be touched")

        store = GitHubContentsLeaseStore(
            repository="owner/repo",
            branch="outbound-lease-ledger",
            token="token",
            opener=opener,
        )
        request = self._valid_attacker_ready_request()
        with self.assertRaisesRegex(ValueError, "caller-supplied pressure verifier is forbidden"):
            core.acquire_lease(
                store,
                request,
                pressure_verifier=self.attacker,
                lease_nonce_key=b"n" * 32,
            )
        self.assertEqual(calls, [])

    def test_facade_global_rebinding_cannot_widen_verifier_seam(self):
        calls = []

        def opener(request):
            calls.append(request)
            raise AssertionError("production store must not be touched")

        store = GitHubContentsLeaseStore(
            repository="owner/repo",
            branch="outbound-lease-ledger",
            token="token",
            opener=opener,
        )
        request = self._valid_attacker_ready_request()
        with patch.object(package, "_mechanically_local_reference_store", lambda store: True), \
             patch.object(package, "_LOCAL_REFERENCE_CHECKER", lambda store: True), \
             patch.object(package, "FileLeaseStore", GitHubContentsLeaseStore), \
             patch.object(package, "_LOCAL_REFERENCE_ACQUIRE_IMPLS", ()), \
             patch.object(package, "Path", lambda value: object()):
            with self.assertRaisesRegex(ValueError, "caller-supplied pressure verifier is forbidden"):
                core.acquire_lease(
                    store,
                    request,
                    pressure_verifier=self.attacker,
                    lease_nonce_key=b"n" * 32,
                )
        self.assertEqual(calls, [])

    def test_file_store_subclass_cannot_launder_attacker_verifier_to_delegated_backend(self):
        calls = []

        class LaunderedProductionStore(FileLeaseStore):
            def _touch(self, operation):
                calls.append(operation)
                raise AssertionError("delegated production-like backend must not be touched")

            def get_active(self, org_fingerprint):
                return self._touch("get_active")

            def get_outcome(self, org_fingerprint, lease_id):
                return self._touch("get_outcome")

            def create_active(self, org_fingerprint, content):
                return self._touch("create_active")

            def create_outcome(self, org_fingerprint, lease_id, content):
                return self._touch("create_outcome")

            def delete_active(self, org_fingerprint, expected_generation):
                return self._touch("delete_active")

        with tempfile.TemporaryDirectory() as td:
            store = LaunderedProductionStore(td)
            with self.assertRaisesRegex(ValueError, "caller-supplied pressure verifier is forbidden"):
                core.acquire_lease(
                    store,
                    self._valid_attacker_ready_request(),
                    pressure_verifier=self.attacker,
                    lease_nonce_key=b"n" * 32,
                )
        self.assertEqual(calls, [])

    def test_exact_file_store_instance_method_rebinding_cannot_launder_attacker_verifier(self):
        calls = []
        with tempfile.TemporaryDirectory() as td:
            store = FileLeaseStore(td)

            def delegated_get_active(org_fingerprint):
                calls.append(("get_active", org_fingerprint))
                raise AssertionError("delegated backend must not be touched")

            store.get_active = delegated_get_active
            with self.assertRaisesRegex(ValueError, "caller-supplied pressure verifier is forbidden"):
                core.acquire_lease(
                    store,
                    self._valid_attacker_ready_request(),
                    pressure_verifier=self.attacker,
                    lease_nonce_key=b"n" * 32,
                )
        self.assertEqual(calls, [])

    def test_subclass_dict_descriptor_cannot_hide_rebound_acquire_methods(self):
        calls = []

        class HiddenDictStore(FileLeaseStore):
            @property
            def __dict__(self):
                return {}

        with tempfile.TemporaryDirectory() as td:
            store = HiddenDictStore(td)

            def delegated_get_active(org_fingerprint):
                calls.append(("get_active", org_fingerprint))
                raise AssertionError("hidden rebound backend must not be touched")

            store.get_active = delegated_get_active
            self.assertFalse(package._mechanically_local_reference_store(store))
            with self.assertRaisesRegex(ValueError, "caller-supplied pressure verifier is forbidden"):
                core.acquire_lease(
                    store,
                    self._valid_attacker_ready_request(),
                    pressure_verifier=self.attacker,
                    lease_nonce_key=b"n" * 32,
                )
        self.assertEqual(calls, [])

    def test_reference_base_method_monkeypatch_is_rejected_against_frozen_descriptor(self):
        calls = []
        with tempfile.TemporaryDirectory() as td:
            store = FileLeaseStore(td)

            def delegated_get_active(self, org_fingerprint):
                calls.append(("get_active", org_fingerprint))
                raise AssertionError("patched reference method must not be touched")

            with patch.object(FileLeaseStore, "get_active", delegated_get_active):
                self.assertFalse(package._mechanically_local_reference_store(store))
                with self.assertRaisesRegex(ValueError, "caller-supplied pressure verifier is forbidden"):
                    core.acquire_lease(
                        store,
                        self._valid_attacker_ready_request(),
                        pressure_verifier=self.attacker,
                        lease_nonce_key=b"n" * 32,
                    )
        self.assertEqual(calls, [])

    def test_terminal_only_reference_subclass_keeps_local_test_seam(self):
        class TerminalOnlyStore(FileLeaseStore):
            def delete_active(self, org_fingerprint, expected_generation):
                return super().delete_active(org_fingerprint, expected_generation)

        with tempfile.TemporaryDirectory() as td:
            store = TerminalOnlyStore(td)
            self.assertTrue(package._mechanically_local_reference_store(store))

    def test_cli_contains_no_claimant_pressure_key_selector(self):
        source = Path(cli.__file__).read_text(encoding="utf-8")
        self.assertNotIn("ORG_PRESSURE_RSA_N_HEX", source)
        self.assertNotIn("ORG_PRESSURE_RSA_E", source)
        self.assertNotIn("ORG_PRESSURE_KEY_ID", source)
        self.assertNotIn("pressure-rsa-modulus-env", source)
        self.assertNotIn("pressure-key-id-env", source)

    def test_fixed_trust_root_has_no_environment_or_cli_override(self):
        self.assertEqual(
            str(trust.TRUST_ROOT_PATH),
            "/etc/tokenjunkielabs/organization-pressure-rsa-public.json",
        )
        source = Path(trust.__file__).read_text(encoding="utf-8")
        self.assertNotIn("getenv", source)
        self.assertNotIn("environ", source)

    def test_trust_root_parser_is_exact_and_builds_public_verifier(self):
        root = {
            "schema": "commons.organization-pressure-trust-root/v1",
            "algorithm": "RS256-PKCS1-v1_5",
            "keyId": "host-pressure-2026",
            "modulusHex": ATTACKER_N_HEX,
            "exponent": 65537,
        }
        parsed = trust.parse_pressure_trust_root(root)
        self.assertEqual(parsed.key_id, "host-pressure-2026")
        self.assertEqual(parsed.modulus, ATTACKER_N)
        self.assertEqual(parsed.exponent, 65537)
        bad = dict(root)
        bad["extra"] = True
        with self.assertRaises(ValueError):
            trust.parse_pressure_trust_root(bad)

    def test_loader_uses_strict_pinned_document(self):
        raw = json.dumps({
            "schema": "commons.organization-pressure-trust-root/v1",
            "algorithm": "RS256-PKCS1-v1_5",
            "keyId": "host-pressure-2026",
            "modulusHex": ATTACKER_N_HEX,
            "exponent": 65537,
        }, separators=(",", ":")).encode()
        with patch.object(trust, "_read_trust_root_bytes", return_value=raw):
            parsed = trust.load_pressure_verifier()
        self.assertEqual(parsed.key_id, "host-pressure-2026")

    def test_secure_mode_rejects_non_root_or_mutable_trust_root(self):
        safe = stat.S_IFREG | 0o644
        with self.assertRaisesRegex(ValueError, "root-owned"):
            trust._secure_mode(SimpleNamespace(st_uid=1000, st_mode=safe), "root")
        with self.assertRaisesRegex(ValueError, "group/world writable"):
            trust._secure_mode(SimpleNamespace(st_uid=0, st_mode=stat.S_IFREG | 0o666), "root")

    def test_python39_syntax_fence_includes_trust_surface(self):
        root = Path(package.__file__).parent
        for path in [root / "__init__.py", root / "cli.py", root / "trust.py"]:
            with self.subTest(path=path.name):
                ast.parse(path.read_text(encoding="utf-8"), filename=str(path), feature_version=(3, 9))

    def test_public_acquire_signature_scopes_test_injection_explicitly(self):
        params = inspect.signature(core.acquire_lease).parameters
        self.assertIn("pressure_verifier", params)
        self.assertEqual(params["pressure_verifier"].default, None)
        self.assertIn("lease_nonce_key", params)


if __name__ == "__main__":
    unittest.main()
