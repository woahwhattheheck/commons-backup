from __future__ import annotations

import importlib
import unittest
from collections.abc import Mapping
from typing import Any, Iterator

from . import engine as direct_engine
from . import guarded as guard_module
from .acceptance import D, NOW, add, base_packet, offer_sent


class SharedFlippingPayload(Mapping[str, Any]):
    """One shared object changes canonical provider on a second traversal."""

    def __init__(self) -> None:
        self.provider_reads = 0
        self._data = {
            "provider_message_id": "shared-interest-message",
            "reply_to_event_id": "send-1",
        }

    def __getitem__(self, key: str) -> Any:
        if key == "provider":
            self.provider_reads += 1
            return "gmail" if self.provider_reads == 1 else "github"
        return self._data[key]

    def __iter__(self) -> Iterator[str]:
        return iter(("provider", *self._data))

    def __len__(self) -> int:
        return 3


class StatefulBoard(Mapping[str, Any]):
    """Board mapping exposes a different timestamp if traversed twice."""

    def __init__(self, board: Mapping[str, Any]) -> None:
        self._data = dict(board)
        self.evaluated_at_reads = 0

    def __getitem__(self, key: str) -> Any:
        if key == "evaluated_at":
            self.evaluated_at_reads += 1
            if self.evaluated_at_reads > 1:
                return "2099-01-01T00:00:00Z"
        return self._data[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def __contains__(self, key: object) -> bool:
        return key in self._data


class SemanticStr(str):
    """Wire bytes and equality/hash semantics deliberately disagree."""

    def __new__(cls, wire: str, semantic: str):
        obj = super().__new__(cls, wire)
        obj.semantic = semantic
        return obj

    def __hash__(self) -> int:
        return hash(self.semantic)

    def __eq__(self, other: object) -> bool:
        return str(other) == self.semantic


class SemanticInt(int):
    """Integer subclass whose semantic comparisons disagree with its wire value."""

    def __new__(cls, wire: int, semantic: int):
        obj = super().__new__(cls, wire)
        obj.semantic = semantic
        return obj

    def __hash__(self) -> int:
        return hash(self.semantic)

    def __eq__(self, other: object) -> bool:
        return other == self.semantic


def _nested_lists(depth: int) -> list[Any]:
    root: list[Any] = []
    cursor = root
    for _ in range(depth):
        child: list[Any] = []
        cursor.append(child)
        cursor = child
    return root


class GraphSnapshotTests(unittest.TestCase):
    def test_shared_stateful_mapping_is_traversed_once_by_identity(self):
        packet = base_packet("shared-identity")
        offer_sent(packet)
        shared = SharedFlippingPayload()
        add(packet, "interest-1", "BUYER_INTEREST", "2026-09-13T12:20:00Z", shared)
        add(packet, "interest-2", "BUYER_INTEREST", "2026-09-13T12:21:00Z", shared)

        board = direct_engine.compile_board(packet, now=NOW)

        self.assertEqual(1, shared.provider_reads)
        self.assertEqual("HOLD", board["stage"])
        self.assertIn("PROVIDER_MESSAGE_ID_CONFLICT", board["reasons"])

    def test_memo_retains_identity_witness_and_rejects_stale_integer_alias(self):
        source = {"fresh": ["value"]}
        memo: dict[int, tuple[Any, Any]] = {}
        snapshot = guard_module._detach(source, _memo=memo)
        witness, retained = memo[id(source)]
        self.assertIs(witness, source)
        self.assertIs(retained, snapshot)

        later = {"different": "object"}
        stale_witness = {"old": "object"}
        poisoned = {id(later): (stale_witness, {"wrong": "snapshot"})}
        with self.assertRaisesRegex(direct_engine.ContractError, "identity collision"):
            guard_module._detach(later, _memo=poisoned)

    def test_cycle_is_contract_error_not_recursion(self):
        packet = base_packet("cycle")
        cycle: list[Any] = []
        cycle.append(cycle)
        packet["events"] = cycle
        with self.assertRaisesRegex(direct_engine.ContractError, "cyclic input graph"):
            direct_engine.compile_board(packet, now=NOW)

    def test_depth_is_bounded_before_core_validation(self):
        packet = base_packet("depth")
        packet["unexpected-hostile-graph"] = _nested_lists(66)
        with self.assertRaisesRegex(direct_engine.ContractError, "depth limit"):
            direct_engine.compile_board(packet, now=NOW)

    def test_node_budget_is_bounded_without_mutable_policy_authority(self):
        # Root + 250000 edges exceeds the fixed 250000-node/edge budget.
        with self.assertRaisesRegex(direct_engine.ContractError, "node limit"):
            guard_module._detach([None] * 250_000)

    def test_product_limits_ignore_module_global_rebinding(self):
        old_depth = guard_module._MAX_SNAPSHOT_DEPTH
        old_nodes = guard_module._MAX_SNAPSHOT_NODES
        try:
            guard_module._MAX_SNAPSHOT_DEPTH = 10_000
            guard_module._MAX_SNAPSHOT_NODES = 10_000_000

            packet = base_packet("rebound-limits")
            packet["unexpected-hostile-graph"] = _nested_lists(80)
            with self.assertRaisesRegex(direct_engine.ContractError, "depth limit"):
                direct_engine.compile_board(packet, now=NOW)

            with self.assertRaisesRegex(direct_engine.ContractError, "node limit"):
                guard_module._detach([None] * 250_000)
        finally:
            guard_module._MAX_SNAPSHOT_DEPTH = old_depth
            guard_module._MAX_SNAPSHOT_NODES = old_nodes

    def test_installed_guards_ignore_helper_and_engine_global_rebinding(self):
        old_detach = guard_module._detach
        old_validator = guard_module.validate_message_providers
        old_engine = guard_module._engine
        try:
            guard_module._detach = lambda value, **kwargs: value
            guard_module.validate_message_providers = lambda packet: None
            guard_module._engine = object()

            alias_packet = base_packet("helper-rebind-provider")
            offer_sent(alias_packet)
            alias_packet["events"][0]["payload"]["provider"] = "gmail-api"
            with self.assertRaises(direct_engine.ContractError):
                direct_engine.compile_board(alias_packet, now=NOW)
            with self.assertRaises(direct_engine.ContractError):
                guard_module.compile_board(alias_packet, now=NOW)

            scalar_packet = base_packet("helper-rebind-scalar")
            offer_sent(scalar_packet)
            scalar_packet["events"][0]["type"] = SemanticStr(
                "BUYER_REJECTED", "OFFER_SENT"
            )
            with self.assertRaisesRegex(
                direct_engine.ContractError, "exact JSON builtin type"
            ):
                direct_engine.compile_board(scalar_packet, now=NOW)
        finally:
            guard_module._detach = old_detach
            guard_module.validate_message_providers = old_validator
            guard_module._engine = old_engine

    def test_reload_uses_retained_installer_after_helper_rebinding(self):
        old_detach = guard_module._detach
        old_validator = guard_module.validate_message_providers
        old_installer = guard_module._install_engine_guards
        try:
            guard_module._detach = lambda value, **kwargs: value
            guard_module.validate_message_providers = lambda packet: None
            guard_module._install_engine_guards = lambda module: None

            reloaded = importlib.reload(direct_engine)
            alias_packet = base_packet("reload-helper-rebind")
            offer_sent(alias_packet)
            alias_packet["events"][0]["payload"]["provider"] = "gmail-api"
            with self.assertRaises(reloaded.ContractError):
                reloaded.compile_board(alias_packet, now=NOW)

            scalar_packet = base_packet("reload-helper-scalar")
            offer_sent(scalar_packet)
            scalar_packet["events"][0]["type"] = SemanticStr(
                "BUYER_REJECTED", "OFFER_SENT"
            )
            with self.assertRaisesRegex(
                reloaded.ContractError, "exact JSON builtin type"
            ):
                reloaded.compile_board(scalar_packet, now=NOW)
        finally:
            guard_module._detach = old_detach
            guard_module.validate_message_providers = old_validator
            guard_module._install_engine_guards = old_installer

    def test_semantic_string_subclass_is_rejected_before_routing(self):
        packet = base_packet("scalar-subclass")
        offer_sent(packet)
        add(
            packet,
            "buyer-decision-1",
            SemanticStr("BUYER_REJECTED", "BUYER_ACCEPTED"),
            "2026-09-13T12:20:00Z",
            {
                "provider": "gmail",
                "provider_message_id": "m-decision-1",
                "reply_to_event_id": "send-1",
                "accepted_proposal_sha256": D,
            },
        )

        with self.assertRaisesRegex(
            direct_engine.ContractError, "exact JSON builtin type"
        ):
            direct_engine.compile_board(packet, now=NOW)

    def test_integer_subclass_is_rejected_before_core_authority(self):
        packet = base_packet("int-subclass")
        packet["offer"]["price_minor"] = SemanticInt(250000, 1)
        with self.assertRaisesRegex(
            direct_engine.ContractError, "exact JSON builtin type"
        ):
            direct_engine.compile_board(packet, now=NOW)

    def test_mapping_key_subclass_is_rejected_before_hash_aliasing(self):
        hostile_key = SemanticStr("events", "offer")
        with self.assertRaisesRegex(
            direct_engine.ContractError, "mapping key must use exact str"
        ):
            guard_module._detach({hostile_key: []})

    def test_verify_board_snapshots_stateful_board_once(self):
        packet = base_packet("board-stateful")
        offer_sent(packet)
        board = direct_engine.compile_board(packet, now=NOW)
        stateful = StatefulBoard(board)

        result = direct_engine.verify_board(packet, stateful, now=NOW)

        self.assertEqual(1, stateful.evaluated_at_reads)
        self.assertTrue(result["historical_valid"])
        self.assertEqual(board["receipt_sha256"], result["historical_receipt_sha256"])

    def test_verify_board_rejects_cyclic_board_graph_before_json(self):
        packet = base_packet("board-cycle")
        board = direct_engine.compile_board(packet, now=NOW)
        cycle: list[Any] = []
        cycle.append(cycle)
        board["hostile_graph"] = cycle

        with self.assertRaisesRegex(direct_engine.ContractError, "cyclic input graph"):
            direct_engine.verify_board(packet, board, now=NOW)

    def test_verify_board_rejects_deep_board_graph_before_core(self):
        packet = base_packet("board-depth")
        board = direct_engine.compile_board(packet, now=NOW)
        board["hostile_graph"] = _nested_lists(66)

        with self.assertRaisesRegex(direct_engine.ContractError, "depth limit"):
            direct_engine.verify_board(packet, board, now=NOW)

    def test_verify_board_enforces_shared_packet_board_node_budget(self):
        packet = base_packet("board-budget")
        board = direct_engine.compile_board(packet, now=NOW)
        board["hostile_graph"] = [None] * 250_000

        with self.assertRaisesRegex(direct_engine.ContractError, "node limit"):
            direct_engine.verify_board(packet, board, now=NOW)

    def test_engine_reload_keeps_graph_guard_and_bound_policy_installed(self):
        old_depth = guard_module._MAX_SNAPSHOT_DEPTH
        old_nodes = guard_module._MAX_SNAPSHOT_NODES
        try:
            guard_module._MAX_SNAPSHOT_DEPTH = 10_000
            guard_module._MAX_SNAPSHOT_NODES = 10_000_000
            reloaded = importlib.reload(direct_engine)

            cycle_packet = base_packet("reload-cycle")
            cycle: list[Any] = []
            cycle.append(cycle)
            cycle_packet["events"] = cycle
            with self.assertRaisesRegex(reloaded.ContractError, "cyclic input graph"):
                reloaded.compile_board(cycle_packet, now=NOW)

            deep_packet = base_packet("reload-depth")
            deep_packet["unexpected-hostile-graph"] = _nested_lists(80)
            with self.assertRaisesRegex(reloaded.ContractError, "depth limit"):
                reloaded.compile_board(deep_packet, now=NOW)
        finally:
            guard_module._MAX_SNAPSHOT_DEPTH = old_depth
            guard_module._MAX_SNAPSHOT_NODES = old_nodes


if __name__ == "__main__":
    unittest.main()
