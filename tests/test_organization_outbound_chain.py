from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import threading
import unittest
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import revenue.initial_outreach_slot.slot as initial_slot_impl
import revenue.organization_outbound_chain.provider_boundary as provider_boundary_impl
import revenue.organization_outbound_chain.registry as registry_impl
from revenue.organization_outbound_chain import chain
from revenue.organization_outbound_chain.provider_boundary import (
    GmailBoundary,
    ProviderBoundaryError,
    invoke_provider_boundary,
    provider_name,
    registered_boundary_types,
)
from revenue.organization_outbound_chain.registry import (
    ADAPTERS,
    find_bypasses,
    registered_host_mutation_identities,
    registered_provider_names,
    validate_registry,
)
from revenue.organization_outbound_lease import FileLeaseStore, acquire_lease


ORG = "1" * 64
CAP = bytes.fromhex("ab" * 32)
CAP_B = bytes.fromhex("cd" * 32)
PRESSURE = "2" * 64
AUTH = "3" * 64
LEDGER = "4" * 64
LOWER_ANCHOR = "5" * 40
ACTIVE_GENERATION = "6" * 40
CANONICAL_KEY = "opportunity-key"


def _ts(offset_seconds: int = 0) -> str:
    return (
        datetime.now(timezone.utc).replace(microsecond=0)
        + timedelta(seconds=offset_seconds)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")


class FakeStore:
    def __init__(self, raw: bytes, generation: str = ACTIVE_GENERATION):
        self.raw = raw
        self.generation = generation

    def get_active(self, org_fingerprint: str):
        if org_fingerprint != ORG:
            return None
        return self.raw, self.generation


def valid_lease(
    *,
    prospect: bytes = b"person-a",
    route: bytes = b"person-a@example.test",
    key: str = CANONICAL_KEY,
    cap: bytes = CAP,
):
    body = {
        "schema": "commons.organization-outbound-lease/v2",
        "leaseId": "7" * 64,
        "intentSha256": "8" * 64,
        "leaseNonce": "9" * 64,
        "claimId": "claim-a",
        "organizationFingerprint": ORG,
        "prospectFingerprint": chain.prospect_fingerprint(ORG, prospect),
        "routeCommitment": chain.route_commitment(ORG, route),
        "opportunityCommitment": chain.opportunity_commitment(
            ORG, "buyer.example", key
        ),
        "holderCapabilityCommitment": chain.holder_capability_commitment(cap),
        "requestedAt": "2026-09-17T19:00:00Z",
        "pressureReceiptSha256": PRESSURE,
        "authorityCommitment": AUTH,
        "ledgerCommitment": LEDGER,
        "pressureVerifiedAt": "2026-09-17T18:59:59Z",
        "externalSendAuthorized": False,
    }
    body["leaseSha256"] = hashlib.sha256(chain.lease_canonical_json(body)).hexdigest()
    return body


class RecordingGmailTransport:
    def __init__(self):
        self.calls: list[tuple[str, bytes]] = []
        self._lock = threading.Lock()

    def gmail_send_message(self, *, idempotency_key: str, request_bytes: bytes):
        with self._lock:
            self.calls.append((idempotency_key, request_bytes))
        return None


class ThreadSafeGit:
    """Minimal atomic Git refs/tags transport for the landed slot + consumer."""

    def __init__(self):
        self.refs: dict[str, str] = {}
        self.tags: dict[str, dict] = {}
        self._counter = 0
        self._lock = threading.RLock()

    def __call__(self, method: str, path: str, body):
        with self._lock:
            if method == "POST" and path.endswith("/git/tags"):
                self._counter += 1
                payload = json.dumps(
                    body, sort_keys=True, separators=(",", ":")
                ).encode("utf-8")
                sha = hashlib.sha1(
                    payload + b"\x00" + str(self._counter).encode("ascii")
                ).hexdigest()
                self.tags[sha] = {
                    "sha": sha,
                    "tag": body["tag"],
                    "message": body["message"],
                    "object": {
                        "sha": body["object"],
                        "type": body["type"],
                    },
                    "tagger": copy.deepcopy(body["tagger"]),
                }
                return 201, {"sha": sha}

            if method == "POST" and path.endswith("/git/refs"):
                ref = body["ref"]
                sha = body["sha"]
                if ref in self.refs:
                    return 422, {"message": "Reference already exists"}
                self.refs[ref] = sha
                return 201, {"ref": ref, "object": {"sha": sha}}

            if method == "GET" and "/git/ref/" in path:
                ref = "refs/" + urllib.parse.unquote(
                    path.split("/git/ref/", 1)[1]
                )
                if ref not in self.refs:
                    return 404, None
                return 200, {"ref": ref, "object": {"sha": self.refs[ref]}}

            if method == "GET" and "/git/tags/" in path:
                sha = path.rsplit("/", 1)[-1]
                if sha not in self.tags:
                    return 404, None
                return 200, copy.deepcopy(self.tags[sha])

            raise AssertionError((method, path, body))


class ChainHelpersTest(unittest.TestCase):
    def test_active_lease_requires_exact_bytes_generation_and_private_capability(self):
        lease = valid_lease()
        raw = chain.lease_canonical_json(lease)
        store = FakeStore(raw)
        parsed, observed = chain._active_organization_lease(
            store=store,
            lease_receipt=lease,
            active_generation=ACTIVE_GENERATION,
            holder_capability=CAP,
        )
        self.assertEqual(parsed["leaseId"], lease["leaseId"])
        self.assertEqual(observed, raw)
        with self.assertRaises(chain.ChainError):
            chain._active_organization_lease(
                store=store,
                lease_receipt=lease,
                active_generation="a" * 40,
                holder_capability=CAP,
            )
        with self.assertRaises(chain.ChainError):
            chain._active_organization_lease(
                store=store,
                lease_receipt=lease,
                active_generation=ACTIVE_GENERATION,
                holder_capability=CAP_B,
            )

    def test_pressure_must_be_current_and_exact_generation_bound(self):
        lease = valid_lease()
        current = {
            "decision": chain.READY,
            "external_send_authorized": False,
            "receipt_sha256": PRESSURE,
            "authority_sha256": AUTH,
            "ledger_sha256": LEDGER,
        }
        with patch.object(chain, "verify_receipt_current", return_value=current):
            self.assertEqual(
                chain._pressure_current(b"signed-pressure", lease)[
                    "receipt_sha256"
                ],
                PRESSURE,
            )
        for field in ("receipt_sha256", "authority_sha256", "ledger_sha256"):
            bad = dict(current)
            bad[field] = "f" * 64
            with patch.object(chain, "verify_receipt_current", return_value=bad):
                with self.assertRaises(chain.ChainError):
                    chain._pressure_current(b"signed-pressure", lease)

    def test_same_canonical_org_and_opportunity_define_same_initial_event_seam(self):
        opp = chain.opportunity_commitment(
            ORG, "buyer.example", CANONICAL_KEY
        )
        self.assertEqual(chain._event_key(ORG, opp), chain._event_key(ORG, opp))
        self.assertNotIn("person-a", chain._event_key(ORG, opp))
        self.assertNotIn("price", chain._event_key(ORG, opp))


class ProviderBoundaryTest(unittest.TestCase):
    def test_exact_gmail_boundary_invokes_only_named_transport_method(self):
        transport = RecordingGmailTransport()
        boundary = GmailBoundary(transport)
        self.assertEqual(provider_name(boundary), "gmail")
        result = invoke_provider_boundary(
            boundary,
            idempotency_key="tjlabs-outbound-v1:test",
            request_bytes=b"request",
        )
        self.assertIsNone(result)
        self.assertEqual(
            transport.calls,
            [("tjlabs-outbound-v1:test", b"request")],
        )

    def test_arbitrary_or_subclass_boundary_is_rejected(self):
        transport = RecordingGmailTransport()

        class FakeBoundary:
            provider = "gmail"
            transport_method = "gmail_send_message"

            def __init__(self):
                self.transport = transport

        with self.assertRaises(ProviderBoundaryError):
            provider_name(FakeBoundary())

        class EvilGmailBoundary(GmailBoundary):
            pass

        with self.assertRaises(ProviderBoundaryError):
            provider_name(EvilGmailBoundary(transport))


    def test_classvar_and_module_rebinding_cannot_redirect_frozen_boundary(self):
        class DriftTransport:
            def __init__(self):
                self.calls = []

            def gmail_send_message(self, *, idempotency_key, request_bytes):
                self.calls.append(("gmail", idempotency_key, request_bytes))

            def redirected(self, *, idempotency_key, request_bytes):
                self.calls.append(("redirected", idempotency_key, request_bytes))

        transport = DriftTransport()
        boundary = GmailBoundary(transport)
        original_provider = GmailBoundary.provider
        original_method = GmailBoundary.transport_method
        original_host_ids = GmailBoundary.host_mutation_identities
        try:
            GmailBoundary.transport_method = "redirected"
            with self.assertRaises(ProviderBoundaryError):
                invoke_provider_boundary(
                    boundary,
                    idempotency_key="tjlabs-outbound-v1:drift",
                    request_bytes=b"request",
                )
            self.assertEqual(transport.calls, [])
        finally:
            GmailBoundary.transport_method = original_method

        try:
            GmailBoundary.provider = "evil"
            with self.assertRaises(ProviderBoundaryError):
                provider_name(boundary)
        finally:
            GmailBoundary.provider = original_provider

        try:
            GmailBoundary.host_mutation_identities = ("evil.send",)
            with self.assertRaises(ProviderBoundaryError):
                registered_boundary_types()
        finally:
            GmailBoundary.host_mutation_identities = original_host_ids

        with patch.object(provider_boundary_impl, "GmailBoundary", object):
            self.assertIs(registered_boundary_types()[0], GmailBoundary)
            invoke_provider_boundary(
                boundary,
                idempotency_key="tjlabs-outbound-v1:stable",
                request_bytes=b"request",
            )
        self.assertEqual(
            transport.calls,
            [("gmail", "tjlabs-outbound-v1:stable", b"request")],
        )


class ChainCompositionTest(unittest.TestCase):
    def _run(
        self,
        *,
        prospect=b"person-a",
        route=b"person-a@example.test",
        transport=None,
        consumer_receipt=None,
    ):
        lease = valid_lease()
        identity = SimpleNamespace(
            repo="woahwhattheheck/commons",
            buyer_scope="buyer.example",
        )
        pressure = {
            "decision": chain.READY,
            "external_send_authorized": False,
            "receipt_sha256": PRESSURE,
            "authority_sha256": AUTH,
            "ledger_sha256": LEDGER,
        }
        lower = {
            "anchor_sha": LOWER_ANCHOR,
            "slot_ref": "refs/tags/slot",
            "slot_tag_sha": "a" * 40,
            "slot_metadata_sha256": "b" * 64,
            "lower_lease_ref": "refs/tags/lower",
            "lower_lease_tag_object_sha": "c" * 40,
            "lower_lease_claim_capability_sha256": "d" * 64,
            "lower_lease_preflight_sha256": "e" * 64,
            "lower_lease_claim_id": "claim-lower",
            "custody_generation": 1,
            "custody_history_sha256": "f" * 64,
            "custody_check_sha256": "0" * 64,
            "custody_basis": "WHOLE",
        }
        transport = transport or RecordingGmailTransport()
        if consumer_receipt is None:
            consumer_receipt = {
                "receipt_sha256": "a" * 64,
                "decision": "SENT",
                "terminal_state": "SENT",
                "external_send_completed": True,
                "prior_send_observed": False,
            }

        def fake_initial(*args, send_once, **kwargs):
            send_once()
            return {
                "receipt_sha256": "b" * 64,
                "provider_callback_invoked": True,
            }

        def fake_consume(
            intent,
            *,
            host_raw,
            transport,
            authority_probe,
            provider_callback,
        ):
            self.assertEqual(host_raw["buyer_scope"], ORG)
            self.assertEqual(intent["event_key"], host_raw["event_key"])
            self.assertIsNotNone(authority_probe())
            provider_callback("tjlabs-outbound-v1:test")
            return dict(consumer_receipt)

        with (
            patch.object(
                chain,
                "_active_organization_lease",
                return_value=(lease, b"lease"),
            ),
            patch.object(chain, "_pressure_current", return_value=pressure),
            patch.object(
                chain,
                "_identity_and_key",
                return_value=(identity, CANONICAL_KEY),
            ),
            patch.object(
                chain,
                "_lower_authority_current",
                return_value=lower,
            ),
            patch.object(
                chain.initial_slot,
                "execute_initial_outreach",
                side_effect=fake_initial,
            ),
            patch.object(chain, "consume_once", side_effect=fake_consume),
            patch.object(
                chain,
                "_finalize_organization_lease",
                return_value={"outcome_sha256": "c" * 64},
            ),
        ):
            result = chain.execute_guarded_initial_outreach(
                {"schema": "ignored-by-mock"},
                actor_owner="Sol-Z",
                actor_operation="issue-14269",
                lower_lease_receipt={"anchor_sha": LOWER_ANCHOR},
                lower_claim_capability="private-lower",
                git_transport=lambda *args: (404, None),
                pressure_receipt_data=b"pressure",
                organization_lease_store=object(),
                organization_lease_receipt=lease,
                organization_lease_generation=ACTIVE_GENERATION,
                organization_holder_capability=CAP,
                prospect_identity=prospect,
                route_identity=route,
                provider_boundary=GmailBoundary(transport),
                provider_request_bytes=b"provider-request",
            )
        return result, transport.calls

    def test_exact_winner_can_reach_provider_once_and_receipt_never_mints_authority(self):
        result, calls = self._run()
        self.assertEqual(len(calls), 1)
        self.assertEqual(result["decision"], "SENT")
        self.assertTrue(result["external_send_completed"])
        self.assertFalse(result["external_send_authorized"])
        self.assertFalse(result["replay_or_retry_authorized"])
        self.assertFalse(result["payment_or_revenue_inferred"])
        self.assertFalse(result["raw_capability_exported"])

    def test_same_org_different_prospect_cannot_reuse_winner_lease(self):
        result, calls = self._run()
        self.assertEqual(len(calls), 1)
        with self.assertRaises(chain.ChainError):
            self._run(prospect=b"person-b")

    def test_missing_action_specific_slot_is_zero_provider_calls(self):
        lease = valid_lease()
        identity = SimpleNamespace(
            repo="woahwhattheheck/commons",
            buyer_scope="buyer.example",
        )
        transport = RecordingGmailTransport()
        with (
            patch.object(
                chain,
                "_active_organization_lease",
                return_value=(lease, b"lease"),
            ),
            patch.object(
                chain,
                "_pressure_current",
                return_value={
                    "receipt_sha256": PRESSURE,
                    "authority_sha256": AUTH,
                    "ledger_sha256": LEDGER,
                },
            ),
            patch.object(
                chain,
                "_identity_and_key",
                return_value=(identity, CANONICAL_KEY),
            ),
            patch.object(
                chain.initial_slot,
                "execute_initial_outreach",
                return_value={
                    "receipt_sha256": "b" * 64,
                    "provider_callback_invoked": False,
                },
            ),
        ):
            result = chain.execute_guarded_initial_outreach(
                {},
                actor_owner="Sol-Z",
                actor_operation="issue-14269",
                lower_lease_receipt={"anchor_sha": LOWER_ANCHOR},
                lower_claim_capability="x",
                git_transport=lambda *args: (404, None),
                pressure_receipt_data=b"pressure",
                organization_lease_store=object(),
                organization_lease_receipt=lease,
                organization_lease_generation=ACTIVE_GENERATION,
                organization_holder_capability=CAP,
                prospect_identity=b"person-a",
                route_identity=b"person-a@example.test",
                provider_boundary=GmailBoundary(transport),
                provider_request_bytes=b"req",
            )
        self.assertEqual(transport.calls, [])
        self.assertEqual(result["decision"], "HOLD_ACTION_SPECIFIC_AUTHORITY")
        self.assertFalse(result["external_send_completed"])

    def test_unknown_consumer_outcome_is_reconciliation_only(self):
        unknown = {
            "receipt_sha256": "a" * 64,
            "decision": "RECONCILE_REQUIRED",
            "terminal_state": "OUTCOME_UNKNOWN",
            "external_send_completed": False,
            "prior_send_observed": False,
        }
        result, calls = self._run(consumer_receipt=unknown)
        self.assertEqual(len(calls), 1)
        self.assertEqual(result["decision"], "RECONCILE_REQUIRED")
        self.assertEqual(result["terminal_state"], "OUTCOME_UNKNOWN")
        self.assertFalse(result["replay_or_retry_authorized"])


class FullChainRaceTest(unittest.TestCase):
    def test_two_workers_same_org_different_prospect_route_offer_reach_provider_at_most_once(self):
        root = tempfile.TemporaryDirectory()
        self.addCleanup(root.cleanup)
        store = FileLeaseStore(root.name)
        git = ThreadSafeGit()
        provider = RecordingGmailTransport()
        barrier = threading.Barrier(2)
        lock = threading.Lock()
        outcomes: list[dict] = []
        errors: list[BaseException] = []

        pressure_verified_at = _ts(-2)
        requested_at = _ts(-1)
        pressure_body = {
            "schema": "commons.organization-pressure-attestation/v2",
            "organizationFingerprint": ORG,
            "pressureReceiptSha256": PRESSURE,
            "authorityCommitment": AUTH,
            "ledgerCommitment": LEDGER,
            "verifiedState": "READY_FOR_SINGLE_WRITER_REVIEW",
            "verifiedAt": pressure_verified_at,
        }
        current_pressure = {
            "decision": chain.READY,
            "external_send_authorized": False,
            "receipt_sha256": PRESSURE,
            "authority_sha256": AUTH,
            "ledger_sha256": LEDGER,
        }

        workers = (
            {
                "name": "a",
                "actor": "Z-WORKER-A",
                "operation": "ORG-CHAIN-RACE-A-20260917",
                "cap": CAP,
                "prospect": b"person-a",
                "route": b"person-a@example.test",
                "offer": "validation-5000",
                "opportunity_id": "rfp-04254",
            },
            {
                "name": "b",
                "actor": "Z-WORKER-B",
                "operation": "ORG-CHAIN-RACE-B-20260917",
                "cap": CAP_B,
                "prospect": b"person-b",
                "route": b"person-b@example.test",
                "offer": "validation-7500",
                "opportunity_id": "lacsd-04254",
            },
        )

        def resolved(_observation):
            return {
                "state": "RESOLVED",
                "canonical_opportunity_key": CANONICAL_KEY,
                "external_action_authorized": False,
                "provider_mutation_authorized": False,
                "buyer_contact_authorized": False,
                "payment_or_revenue_inferred": False,
            }

        def fake_pressure_attestation(
            _attestation,
            _verifier,
            *,
            organization_fingerprint,
        ):
            self.assertEqual(organization_fingerprint, ORG)
            return dict(pressure_body)

        def fake_custody(
            opportunity_document,
            *,
            actor_owner,
            actor_operation,
            lane,
            transport,
        ):
            self.assertEqual(lane, "outreach")
            identity = chain.coc.Identity.parse(dict(opportunity_document))
            return {
                "schema": "commercial-opportunity-custody-work-check/v1",
                "seam_sha256": identity.seam_sha256,
                "generation": 1,
                "history_sha256": "f" * 64,
                "actor_owner": actor_owner,
                "actor_operation": actor_operation,
                "lane": "outreach",
                "internal_work_authorized": True,
                "basis": "WHOLE",
                "external_send_authorized": False,
                "proposal_submission_authorized": False,
                "payment_or_revenue_inferred": False,
                "check_sha256": "0" * 64,
            }

        def worker(spec):
            opportunity = {
                "schema": "commercial-opportunity-custody/v1",
                "repo": "woahwhattheheck/commons",
                "buyer_scope": "buyer.example",
                "authority_scope": "rfp.example",
                "opportunity_id": spec["opportunity_id"],
            }
            request = {
                "schema": "commons.organization-outbound-acquire/v2",
                "claimId": f"claim-{spec['name']}",
                "organizationFingerprint": ORG,
                "prospectFingerprint": chain.prospect_fingerprint(
                    ORG, spec["prospect"]
                ),
                "routeCommitment": chain.route_commitment(
                    ORG, spec["route"]
                ),
                "opportunityCommitment": chain.opportunity_commitment(
                    ORG, "buyer.example", CANONICAL_KEY
                ),
                "holderCapabilityCommitment": chain.holder_capability_commitment(
                    spec["cap"]
                ),
                "requestedAt": requested_at,
                "pressureAttestation": {},
            }
            lower_receipt = {
                "repo": "woahwhattheheck/commons",
                "buyer_scope": "buyer.example",
                "claimant": spec["actor"],
                "lease_ref": f"refs/tags/lower-{spec['name']}",
                "tag_object_sha": ("a" if spec["name"] == "a" else "b") * 40,
                "claim_capability_sha256": (
                    "c" if spec["name"] == "a" else "d"
                )
                * 64,
                "preflight_sha256": (
                    "e" if spec["name"] == "a" else "f"
                )
                * 64,
                "claim_id": f"lower-{spec['name']}",
                "offer_scope": spec["offer"],
                "anchor_sha": LOWER_ANCHOR,
            }
            try:
                barrier.wait()
                acquired = acquire_lease(
                    store,
                    request,
                    pressure_verifier=object(),
                    lease_nonce_key=b"n" * 32,
                )
                try:
                    result = chain.execute_guarded_initial_outreach(
                        opportunity,
                        actor_owner=spec["actor"],
                        actor_operation=spec["operation"],
                        lower_lease_receipt=lower_receipt,
                        lower_claim_capability=f"private-{spec['name']}",
                        git_transport=git,
                        pressure_receipt_data=b"pressure-receipt",
                        organization_lease_store=store,
                        organization_lease_receipt=acquired.lease,
                        organization_lease_generation=acquired.active_generation,
                        organization_holder_capability=spec["cap"],
                        prospect_identity=spec["prospect"],
                        route_identity=spec["route"],
                        provider_boundary=GmailBoundary(provider),
                        provider_request_bytes=(
                            f"request-{spec['name']}".encode("ascii")
                        ),
                    )
                    chain_result = result
                    chain_error = None
                except BaseException as exc:
                    chain_result = None
                    chain_error = exc
                with lock:
                    outcomes.append(
                        {
                            "worker": spec["name"],
                            "acquire_state": acquired.state,
                            "chain_result": chain_result,
                            "chain_error": chain_error,
                        }
                    )
            except BaseException as exc:
                with lock:
                    errors.append(exc)

        with (
            patch(
                "revenue.organization_outbound_lease.core.verify_pressure_attestation",
                side_effect=fake_pressure_attestation,
            ),
            patch.object(
                chain,
                "verify_receipt_current",
                return_value=current_pressure,
            ),
            patch.object(
                initial_slot_impl.alias_v1,
                "resolve_current",
                side_effect=resolved,
            ),
            patch.object(
                chain.coc,
                "authorize_internal_work",
                side_effect=fake_custody,
            ),
            patch.object(chain.lower_lease, "verify_receipt", return_value=True),
            patch.object(
                chain.lower_lease,
                "verify_possession",
                return_value=True,
            ),
        ):
            threads = [
                threading.Thread(target=worker, args=(spec,))
                for spec in workers
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

        self.assertEqual(errors, [], f"worker errors: {errors!r}")
        self.assertEqual(len(outcomes), 2)
        self.assertEqual(
            sum(item["acquire_state"] == "LEASE_ACQUIRED" for item in outcomes),
            1,
            outcomes,
        )
        self.assertEqual(
            sum(
                item["acquire_state"] == "ORGANIZATION_ALREADY_LEASED"
                for item in outcomes
            ),
            1,
            outcomes,
        )
        self.assertEqual(len(provider.calls), 1, outcomes)
        successful = [
            item
            for item in outcomes
            if item["chain_result"] is not None
        ]
        self.assertEqual(len(successful), 1, outcomes)
        self.assertEqual(successful[0]["chain_result"]["decision"], "SENT")
        self.assertTrue(
            successful[0]["chain_result"]["external_send_completed"]
        )
        loser = [
            item for item in outcomes if item["chain_result"] is None
        ][0]
        self.assertIsInstance(loser["chain_error"], chain.ChainError)


class RegistryTest(unittest.TestCase):
    def test_supported_provider_registry_and_host_identities_are_explicit(self):
        self.assertEqual(
            registered_provider_names(),
            ("gmail", "slack_dm", "discord", "webhook_mail"),
        )
        identities = set(registered_host_mutation_identities())
        self.assertIn("mcp__Gmail__send_email", identities)
        self.assertIn("mcp__Gmail__send_draft", identities)
        self.assertIn("mcp__Gmail__forward_emails", identities)
        self.assertIn("mcp__Slack__slack_send_message", identities)
        self.assertIn("mcp__Slack__slack_schedule_message", identities)

    def test_manifest_exactly_matches_runtime_boundary_metadata(self):
        rows = {item.provider: item for item in ADAPTERS}
        boundaries = {
            boundary.provider: boundary
            for boundary in registered_boundary_types()
        }
        self.assertEqual(set(rows), set(boundaries))
        for provider, boundary in boundaries.items():
            row = rows[provider]
            self.assertEqual(row.boundary_class_name, boundary.__name__)
            self.assertEqual(row.transport_method, boundary.transport_method)
            self.assertEqual(
                tuple(row.host_mutation_identities),
                tuple(boundary.host_mutation_identities),
            )
        runtime_identities = {
            identity
            for boundary in registered_boundary_types()
            for identity in boundary.host_mutation_identities
        }
        self.assertEqual(
            set(registered_host_mutation_identities()),
            runtime_identities,
        )

    def test_direct_lower_primitive_provider_method_and_host_marker_fail_registry(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "live.py").write_text(
                "from revenue.outbound_send_consumer import consume_once as send\n"
                "def f(transport):\n"
                "    send({})\n"
                "    transport.gmail_send_message(idempotency_key='x', request_bytes=b'x')\n",
                encoding="utf-8",
            )
            (root / "live.ts").write_text(
                "const tool = 'mcp__Slack__slack_send_message';\n",
                encoding="utf-8",
            )
            violations = find_bypasses(root, validate_manifest=False)
            self.assertIn(
                "live.py:direct-terminal-consumer",
                violations,
            )
            self.assertIn(
                "live.py:provider-transport-method:gmail_send_message",
                violations,
            )
            self.assertTrue(
                any(
                    item.startswith("live.ts:provider-marker:")
                    and "mcp__Slack__slack_send_message" in item
                    for item in violations
                )
            )

    def test_alias_rebinding_of_lower_primitives_is_detected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "live.py").write_text(
                "from revenue import initial_outreach_slot as ios\n"
                "from revenue.outbound_send_consumer import consume_once as c\n"
                "first = ios.execute_initial_outreach\n"
                "terminal = c\n"
                "first({})\n"
                "terminal({})\n",
                encoding="utf-8",
            )
            violations = find_bypasses(root, validate_manifest=False)
            self.assertIn("live.py:direct-initial-outreach", violations)
            self.assertIn("live.py:direct-terminal-consumer", violations)

    def test_computed_nonpython_host_identity_is_detected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "live.ts").write_text(
                "const p = 'mcp__Slack__' + 'slack_' + 'send_message';\n",
                encoding="utf-8",
            )
            violations = find_bypasses(root, validate_manifest=False)
            self.assertTrue(
                any(
                    item.startswith("live.ts:provider-marker:")
                    and "mcp__Slack__slack_send_message" in item
                    for item in violations
                ),
                violations,
            )

    def test_english_send_mail_is_not_a_sendmail_call(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "notes.py").write_text(
                '"""This helper cannot send mail or a send mailbox."""\n'
                "SENDMAIL = 'adapter-name-only'\n",
                encoding="utf-8",
            )
            self.assertEqual(find_bypasses(root, validate_manifest=False), [])

            (root / "live.py").write_text(
                "def fire(smtp):\n    smtp.sendmail('a', 'b', 'c')\n",
                encoding="utf-8",
            )
            live = find_bypasses(root, validate_manifest=False)
            self.assertIn("live.py:provider-marker:.sendmail(", live)

            (root / "split.js").write_text(
                "const m = '.' + 'sendmail(';\n",
                encoding="utf-8",
            )
            split = find_bypasses(root, validate_manifest=False)
            self.assertIn("split.js:provider-marker:.sendmail(", split)

            (root / "hook.js").write_text(
                "fetch('https://hooks.slack.com/services/T00/B00/xxx');\n",
                encoding="utf-8",
            )
            hook = find_bypasses(root, validate_manifest=False)
            self.assertTrue(
                any(
                    "hook.js:provider-marker:hooks.slack.com/services/" in item
                    for item in hook
                ),
                hook,
            )

    def test_registry_public_rebinding_cannot_redefine_first_load_generation(self):
        root = Path(__file__).resolve().parents[1]
        with patch.object(registry_impl, "ADAPTERS", ()):
            self.assertIn(
                "registry:public-manifest-drift",
                validate_registry(root),
            )

        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            (temp_root / "live.ts").write_text(
                "const p = 'mcp__Slack__' + 'slack_' + 'send_message';\n",
                encoding="utf-8",
            )
            with patch.object(registry_impl, "PROVIDER_MARKERS", ()):
                violations = find_bypasses(
                    temp_root,
                    validate_manifest=False,
                )
            self.assertTrue(
                any(
                    "mcp__Slack__slack_send_message" in item
                    for item in violations
                ),
                violations,
            )

    def test_test_files_do_not_count_as_live_adapter_bypass(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "test_fake.py").write_text(
                "from revenue.outbound_send_consumer import consume_once\n"
                "consume_once({})\n"
                "mcp__Slack__slack_send_message\n",
                encoding="utf-8",
            )
            self.assertEqual(
                find_bypasses(root, validate_manifest=False),
                [],
            )

    def test_internal_peer_bridge_marker_exemptions_are_exact_byte_bound(self):
        repository_root = Path(__file__).resolve().parents[1]
        for rel in (
            "integrations/gemini_slack/bridge.py",
            "integrations/grok_slack/bridge.py",
        ):
            with self.subTest(rel=rel), tempfile.TemporaryDirectory() as td:
                temp_root = Path(td)
                target = temp_root / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                source = (repository_root / rel).read_bytes()
                target.write_bytes(source)
                self.assertEqual(
                    find_bypasses(temp_root, validate_manifest=False),
                    [],
                )
                target.write_bytes(source + b"\n# exact-byte drift\n")
                violations = find_bypasses(
                    temp_root,
                    validate_manifest=False,
                )
                self.assertIn(
                    f"{rel}:internal-provider-exemption-drift",
                    violations,
                )
                self.assertTrue(
                    any(
                        item.startswith(f"{rel}:provider-marker:")
                        for item in violations
                    ),
                    violations,
                )

    def test_internal_provider_exemption_requires_semantic_guard_contract(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            path = root / "unsafe.py"
            raw = b"def send(client, channel):\n    client.chat_postMessage(channel=channel, text='x')\n"
            path.write_bytes(raw)
            sha = registry_impl._git_blob_sha(raw)
            violations = find_bypasses(
                root,
                validate_manifest=False,
                _internal_provider_marker_exemptions=(
                    (
                        "unsafe.py",
                        sha,
                        ("class InternalSlackScope", "self.scope.require_channel(channel)"),
                    ),
                ),
            )
            self.assertIn(
                "unsafe.py:internal-provider-exemption-guard-missing",
                violations,
            )
            self.assertTrue(
                any(item.startswith("unsafe.py:provider-marker:") for item in violations),
                violations,
            )

    def test_gemini_peer_bridge_scope_blocks_shared_cross_team_and_nonmember_posts(self):
        from integrations.gemini_slack.bridge import (
            BridgeError as GeminiBridgeError,
            InternalSlackScope as GeminiInternalSlackScope,
            SlackSink,
        )

        class FakeWeb:
            def __init__(self, channel_info):
                self.channel_info = dict(channel_info)
                self.posts = []

            def conversations_info(self, *, channel, include_num_members=False):
                del include_num_members
                return {"ok": True, "channel": {"id": channel, **self.channel_info}}

            def chat_postMessage(self, **kwargs):
                self.posts.append(dict(kwargs))
                return {"ok": True, "ts": "1.0"}

        cases = (
            {"is_member": True, "is_ext_shared": True},
            {"is_member": True, "context_team_id": "TOTHER"},
            {"is_member": False},
        )
        for info in cases:
            with self.subTest(info=info):
                web = FakeWeb(info)
                sink = SlackSink(
                    web,
                    GeminiInternalSlackScope(web, "TLOCAL"),
                )
                with self.assertRaises(GeminiBridgeError):
                    sink.post("CDEST", "1.0", "MERIDIAN", "Internal peer reply.")
                self.assertEqual(web.posts, [])

    def test_grok_peer_bridge_scope_blocks_shared_cross_team_and_nonmember_posts(self):
        from integrations.grok_slack.bridge import (
            BridgeError as GrokBridgeError,
            BridgeStore,
            InternalSlackScope as GrokInternalSlackScope,
            SlackTransport,
        )

        class FakeWeb:
            def __init__(self, channel_info):
                self.channel_info = dict(channel_info)
                self.posts = []

            def conversations_info(self, *, channel, include_num_members=False):
                del include_num_members
                return {"ok": True, "channel": {"id": channel, **self.channel_info}}

            def chat_postMessage(self, **kwargs):
                self.posts.append(dict(kwargs))
                return {"ok": True, "ts": "1.0"}

        cases = (
            {"is_member": True, "is_ext_shared": True},
            {"is_member": True, "context_team_id": "TOTHER"},
            {"is_member": False},
        )
        with tempfile.TemporaryDirectory() as td:
            store = BridgeStore(Path(td) / "scope.sqlite3")
            try:
                for info in cases:
                    with self.subTest(info=info):
                        web = FakeWeb(info)
                        transport = SlackTransport(
                            web,
                            store,
                            scope=GrokInternalSlackScope(web, "TLOCAL"),
                        )
                        with self.assertRaises(GrokBridgeError):
                            transport.post_chunk(
                                "CDEST",
                                "1.0",
                                "Internal peer reply.",
                                event_id="evt-scope",
                                phase="RESULT",
                                index=0,
                                count=1,
                            )
                        self.assertEqual(web.posts, [])
            finally:
                store.close()


    def test_raw_slack_web_helper_alias_and_dynamic_access_are_low_level_bypasses(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "alias.py").write_text(
                "from integrations.grok_slack.bridge import slack_web_call as send\n"
                "again = send\n"
                "def bypass(token, channel):\n"
                "    return again('chat.postMessage', token, "
                "{'channel': channel, 'text': 'x'})\n",
                encoding="utf-8",
            )
            (root / "dynamic.py").write_text(
                "import integrations.grok_slack.bridge as bridge\n"
                "def bypass(token, channel):\n"
                "    send = getattr(bridge, 'slack_web_call')\n"
                "    return send('chat.postMessage', token, "
                "{'channel': channel, 'text': 'x'})\n",
                encoding="utf-8",
            )
            violations = find_bypasses(root, validate_manifest=False)
            self.assertIn("alias.py:direct-slack-web-api-helper", violations)
            self.assertIn("dynamic.py:dynamic-slack-web-api-helper", violations)

    def test_raw_slack_web_call_is_provider_send_outside_exempt_bridge(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "live.py").write_text(
                "def bypass(token, channel):\n"
                "    return slack_web_call('chat.postMessage', token, "
                "{'channel': channel, 'text': 'x'})\n",
                encoding="utf-8",
            )
            violations = find_bypasses(root, validate_manifest=False)
            self.assertTrue(
                any(
                    item.startswith(
                        "live.py:internal-provider-callsite-unguarded:bypass:"
                    )
                    for item in violations
                ),
                violations,
            )

    def test_internal_provider_exemption_is_callsite_scoped(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            path = root / "unsafe.py"
            raw = (
                "class InternalSlackScope:\n"
                "    pass\n"
                "def guarded(self, web, channel):\n"
                "    self.scope.require_channel(channel)\n"
                "    web.chat_postMessage(channel=channel, text='ok')\n"
                "def unguarded(token):\n"
                "    slack_web_call('chat.postMessage', token, {'channel': 'COTHER'})\n"
            ).encode("utf-8")
            path.write_bytes(raw)
            sha = registry_impl._git_blob_sha(raw)
            violations = find_bypasses(
                root,
                validate_manifest=False,
                _internal_provider_marker_exemptions=(
                    (
                        "unsafe.py",
                        sha,
                        (
                            "class InternalSlackScope",
                            "self.scope.require_channel(channel)",
                        ),
                    ),
                ),
            )
            self.assertTrue(
                any(
                    item.startswith(
                        "unsafe.py:internal-provider-callsite-unguarded:unguarded:"
                    )
                    for item in violations
                ),
                violations,
            )
            self.assertFalse(
                any(
                    item.startswith(
                        "unsafe.py:internal-provider-callsite-unguarded:guarded:"
                    )
                    for item in violations
                ),
                violations,
            )

    def test_internal_provider_guard_must_match_mutation_channel(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            path = root / "unsafe.py"
            raw = (
                "class InternalSlackScope:\n"
                "    pass\n"
                "def mismatched(self, web):\n"
                "    self.scope.require_channel('CONE')\n"
                "    web.chat_postMessage(channel='CTWO', text='no')\n"
            ).encode("utf-8")
            path.write_bytes(raw)
            sha = registry_impl._git_blob_sha(raw)
            violations = find_bypasses(
                root,
                validate_manifest=False,
                _internal_provider_marker_exemptions=(
                    (
                        "unsafe.py",
                        sha,
                        (
                            "class InternalSlackScope",
                            "self.scope.require_channel",
                        ),
                    ),
                ),
            )
            self.assertTrue(
                any(
                    item.startswith(
                        "unsafe.py:internal-provider-callsite-unguarded:mismatched:"
                    )
                    for item in violations
                ),
                violations,
            )

    def test_grok_table_proof_refuses_shared_channel_before_receipt_post(self):
        from integrations.grok_slack import bridge as grok_bridge

        calls: list[str] = []

        def fake_slack_web_call(method, _token, payload=None, **_kwargs):
            calls.append(method)
            if method == "auth.test":
                return {"ok": True, "team": "Local", "team_id": "TLOCAL"}
            if method == "conversations.history":
                return {"ok": True, "messages": []}
            if method == "conversations.info":
                self.assertEqual((payload or {}).get("channel"), grok_bridge.DEFAULT_CHANNEL)
                return {
                    "ok": True,
                    "channel": {
                        "id": grok_bridge.DEFAULT_CHANNEL,
                        "is_member": True,
                        "is_ext_shared": True,
                    },
                }
            if method == "chat.postMessage":
                return {"ok": True, "ts": "1.0"}
            raise AssertionError(method)

        health_report = {
            "state": "READY",
            "slack_bot_token": "present",
            "slack_app_token": "present",
        }
        with (
            patch.object(grok_bridge, "health", return_value=(0, health_report)),
            patch.object(
                grok_bridge,
                "slack_web_call",
                side_effect=fake_slack_web_call,
            ),
        ):
            with self.assertRaises(grok_bridge.BridgeError):
                grok_bridge.table_proof(
                    SimpleNamespace(post_receipt=True),
                    env={"SLACK_BOT_TOKEN": "xoxb-test-token"},
                )
        self.assertIn("conversations.info", calls)
        self.assertNotIn("chat.postMessage", calls)

    def test_grok_table_proof_internal_channel_allows_one_receipt_post(self):
        from integrations.grok_slack import bridge as grok_bridge

        calls: list[str] = []

        def fake_slack_web_call(method, _token, payload=None, **_kwargs):
            calls.append(method)
            if method == "auth.test":
                return {"ok": True, "team": "Local", "team_id": "TLOCAL"}
            if method == "conversations.history":
                return {"ok": True, "messages": []}
            if method == "conversations.info":
                return {
                    "ok": True,
                    "channel": {
                        "id": grok_bridge.DEFAULT_CHANNEL,
                        "is_member": True,
                        "team_id": "TLOCAL",
                    },
                }
            if method == "chat.postMessage":
                self.assertEqual((payload or {}).get("channel"), grok_bridge.DEFAULT_CHANNEL)
                return {"ok": True, "ts": "1.0"}
            raise AssertionError(method)

        health_report = {
            "state": "READY",
            "slack_bot_token": "present",
            "slack_app_token": "present",
        }
        with (
            patch.object(grok_bridge, "health", return_value=(0, health_report)),
            patch.object(
                grok_bridge,
                "slack_web_call",
                side_effect=fake_slack_web_call,
            ),
        ):
            code, report = grok_bridge.table_proof(
                SimpleNamespace(post_receipt=True),
                env={"SLACK_BOT_TOKEN": "xoxb-test-token"},
            )
        self.assertEqual(code, 0)
        self.assertTrue(report["internal_scope_verified"])
        self.assertEqual(calls.count("chat.postMessage"), 1)

    def test_parse_incompatible_python_still_gets_sensitive_lexical_scan(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            path = root / "future.py"
            path.write_text("def broken(:\n    pass\n", encoding="utf-8")
            self.assertEqual(
                find_bypasses(root, validate_manifest=False),
                [],
            )

            path.write_text(
                "def broken(:\n    chat_postMessage(\n",
                encoding="utf-8",
            )
            violations = find_bypasses(root, validate_manifest=False)
            self.assertTrue(
                any("provider-marker:chat_postMessage(" in item for item in violations),
                violations,
            )

            path.write_text(
                "def broken(:\n    consume_once(\n",
                encoding="utf-8",
            )
            violations = find_bypasses(root, validate_manifest=False)
            self.assertIn(
                "future.py:parse-incompatible-sensitive-marker:consume_once",
                violations,
            )

    def test_repository_manifest_is_closed_and_has_no_unguarded_live_provider_path(self):
        root = Path(__file__).resolve().parents[1]
        self.assertEqual(validate_registry(root), [])
        self.assertEqual(find_bypasses(root), [])


if __name__ == "__main__":
    unittest.main()
