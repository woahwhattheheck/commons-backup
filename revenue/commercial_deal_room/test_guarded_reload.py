from __future__ import annotations

import copy
import importlib
import unittest
from collections.abc import Mapping
from typing import Any, Iterator

from . import ContractError as exported_contract_error
from . import engine as direct_engine
from .acceptance import D, E, NOW, add, base_packet, offer_sent
from .guarded import compile_board as package_compile_board


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


def alias_packet(name: str) -> dict[str, Any]:
    packet = base_packet(name)
    offer_sent(packet)
    packet["events"][0]["payload"]["provider"] = "gmail-api"
    return packet


class ReloadGuardTests(unittest.TestCase):
    def test_reload_returns_with_direct_alias_guard_installed(self):
        reloaded = importlib.reload(direct_engine)
        with self.assertRaises(reloaded.ContractError):
            reloaded.compile_board(alias_packet("reload-direct"), now=NOW)

    def test_reload_preserves_exported_contract_error_identity(self):
        reloaded = importlib.reload(direct_engine)
        self.assertIs(reloaded.ContractError, exported_contract_error)
        with self.assertRaises(exported_contract_error):
            reloaded.compile_board(alias_packet("reload-contract-error"), now=NOW)

    def test_reload_preserves_package_alias_guard(self):
        reloaded = importlib.reload(direct_engine)
        with self.assertRaises(reloaded.ContractError):
            package_compile_board(alias_packet("reload-package"), now=NOW)

    def test_stale_compile_reference_cannot_bypass_reload_guard(self):
        stale_compile = direct_engine.compile_board
        reloaded = importlib.reload(direct_engine)
        with self.assertRaises(reloaded.ContractError):
            stale_compile(alias_packet("reload-stale-compile"), now=NOW)

    def test_reload_verify_uses_one_packet_generation(self):
        canonical = conflict_packet("reload-verify")
        board = package_compile_board(canonical, now=NOW)
        hostile = copy.deepcopy(canonical)
        original = hostile["events"][0]["payload"]
        hostile["events"][0]["payload"] = FlippingProviderPayload(original, canonical_reads=1)

        reloaded = importlib.reload(direct_engine)
        result = reloaded.verify_board(hostile, board, now=NOW)

        self.assertTrue(result["historical_valid"])
        self.assertEqual(result["current_stage"], "HOLD")
        self.assertIn("PROVIDER_MESSAGE_ID_CONFLICT", result["current_reasons"])

    def test_reload_finder_is_singleton(self):
        import sys

        importlib.reload(direct_engine)
        importlib.reload(direct_engine)
        finders = [
            finder
            for finder in sys.meta_path
            if getattr(finder, "__commercial_deal_room_reload_finder__", False)
        ]
        self.assertEqual(len(finders), 1)


if __name__ == "__main__":
    unittest.main()
