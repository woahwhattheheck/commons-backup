from __future__ import annotations

import copy
import unittest
from collections.abc import Mapping
from typing import Any, Iterator

from revenue.outbound_connector_lease.key import SUPPORTED_REPLY_PROVIDERS

from . import engine as direct_engine
from .acceptance import D, E, NOW, add, base_packet, offer_sent
from .guarded import CANONICAL_MESSAGE_PROVIDERS, ContractError, compile_board, verify_board


class FlippingProviderPayload(Mapping[str, Any]):
    """Stable-key mapping whose provider value changes after N reads."""

    def __init__(self, payload: Mapping[str, Any], canonical_reads: int) -> None:
        self._payload = dict(payload)
        self._canonical_reads = canonical_reads
        self._provider_reads = 0

    def __getitem__(self, key: str) -> Any:
        if key == "provider":
            self._provider_reads += 1
            if self._provider_reads <= self._canonical_reads:
                return "gmail"
            return "gmail-api"
        return self._payload[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._payload)

    def __len__(self) -> int:
        return len(self._payload)


def conflict_packet(name: str) -> dict[str, Any]:
    packet = base_packet(name)
    add(
        packet,
        "send-1",
        "OFFER_SENT",
        "2026-09-13T12:10:00Z",
        {
            "provider": "gmail",
            "provider_message_id": "m-shared",
            "scope_sha256": D,
            "terms_sha256": E,
        },
    )
    add(
        packet,
        "interest-1",
        "BUYER_INTEREST",
        "2026-09-13T12:20:00Z",
        {
            "provider": "gmail",
            "provider_message_id": "m-shared",
            "reply_to_event_id": "send-1",
        },
    )
    return packet


class GuardedProviderTests(unittest.TestCase):
    def test_registry_is_shared_with_outbound_reply_lease(self):
        self.assertIs(CANONICAL_MESSAGE_PROVIDERS, SUPPORTED_REPLY_PROVIDERS)

    def test_all_canonical_message_providers_are_accepted(self):
        for provider in sorted(CANONICAL_MESSAGE_PROVIDERS):
            with self.subTest(provider=provider):
                packet = base_packet(f"canonical-{provider}")
                offer_sent(packet)
                packet["events"][0]["payload"]["provider"] = provider
                self.assertEqual(compile_board(packet, now=NOW)["stage"], "AWAITING_BUYER")

    def test_aliases_and_malformed_provider_are_rejected(self):
        for provider in (
            "email",
            "googlemail",
            "gmail-api",
            "github-api",
            "slack-api",
            "webform",
            "GMAIL",
            "gmail.com",
            "smtp",
            "",
            ["gmail"],
        ):
            with self.subTest(provider=provider):
                packet = base_packet("alias")
                offer_sent(packet)
                packet["events"][0]["payload"]["provider"] = provider
                with self.assertRaises(ContractError):
                    compile_board(packet, now=NOW)

    def test_alias_cannot_split_one_message_across_semantic_facts(self):
        packet = conflict_packet("split")
        packet["events"][1]["payload"]["provider"] = "googlemail"
        with self.assertRaises(ContractError):
            compile_board(packet, now=NOW)

    def test_direct_engine_alias_is_rejected_after_package_import(self):
        packet = base_packet("direct-engine")
        offer_sent(packet)
        packet["events"][0]["payload"]["provider"] = "gmail-api"
        with self.assertRaises(ContractError):
            direct_engine.compile_board(packet, now=NOW)

    def test_canonical_same_message_conflict_still_holds(self):
        board = compile_board(conflict_packet("canonical-conflict"), now=NOW)
        self.assertEqual(board["stage"], "HOLD")
        self.assertIn("PROVIDER_MESSAGE_ID_CONFLICT", board["reasons"])

    def test_package_compile_consumes_same_snapshot_it_validates(self):
        packet = conflict_packet("package-flip")
        original = packet["events"][0]["payload"]
        # The RED predecessor performed two guard reads before the core read.
        # That head therefore consumed gmail-api here and missed the collision.
        packet["events"][0]["payload"] = FlippingProviderPayload(original, canonical_reads=2)
        board = compile_board(packet, now=NOW)
        self.assertEqual(board["stage"], "HOLD")
        self.assertIn("PROVIDER_MESSAGE_ID_CONFLICT", board["reasons"])

    def test_direct_engine_compile_consumes_same_snapshot_it_validates(self):
        packet = conflict_packet("direct-flip")
        original = packet["events"][0]["payload"]
        # The RED predecessor's direct-engine path had one guard read before the
        # core read. The repaired path performs one detached read total.
        packet["events"][0]["payload"] = FlippingProviderPayload(original, canonical_reads=1)
        board = direct_engine.compile_board(packet, now=NOW)
        self.assertEqual(board["stage"], "HOLD")
        self.assertIn("PROVIDER_MESSAGE_ID_CONFLICT", board["reasons"])

    def test_package_verify_uses_one_generation_for_both_evaluations(self):
        canonical = conflict_packet("verify-flip")
        board = compile_board(canonical, now=NOW)
        hostile = copy.deepcopy(canonical)
        original = hostile["events"][0]["payload"]
        # Old package verify read the live payload once outside core, then again
        # during historical normalization, then again during current evaluation.
        hostile["events"][0]["payload"] = FlippingProviderPayload(original, canonical_reads=2)
        result = verify_board(hostile, board, now=NOW)
        self.assertTrue(result["historical_valid"])
        self.assertEqual(result["current_stage"], "HOLD")
        self.assertIn("PROVIDER_MESSAGE_ID_CONFLICT", result["current_reasons"])

    def test_direct_engine_verify_uses_one_generation_for_both_evaluations(self):
        canonical = conflict_packet("direct-verify-flip")
        board = compile_board(canonical, now=NOW)
        hostile = copy.deepcopy(canonical)
        original = hostile["events"][0]["payload"]
        hostile["events"][0]["payload"] = FlippingProviderPayload(original, canonical_reads=1)
        result = direct_engine.verify_board(hostile, board, now=NOW)
        self.assertTrue(result["historical_valid"])
        self.assertEqual(result["current_stage"], "HOLD")
        self.assertIn("PROVIDER_MESSAGE_ID_CONFLICT", result["current_reasons"])

    def test_verify_rejects_plain_alias_even_for_preexisting_board(self):
        packet = base_packet("verify-alias")
        offer_sent(packet)
        board = compile_board(packet, now=NOW)
        aliased = copy.deepcopy(packet)
        aliased["events"][0]["payload"]["provider"] = "gmail-api"
        with self.assertRaises(ContractError):
            verify_board(aliased, board, now=NOW)


if __name__ == "__main__":
    unittest.main()
