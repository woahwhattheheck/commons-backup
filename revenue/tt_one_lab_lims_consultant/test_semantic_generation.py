from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import dis
import hashlib
import json
from pathlib import Path
import types
import unittest

import revenue.tt_one_lab_lims_consultant.carrier as carrier
from revenue.tt_one_lab_lims_consultant.test_carrier import complete_input


ROOTS = (
    carrier.compile_packet,
    carrier.verify_packet,
    carrier.source_manifest_digest,
    carrier.example_owner_input,
    carrier.loads_strict,
)
BOUNDARY = json.loads(
    Path(__file__).with_name("INTEGRITY_BOUNDARY.json").read_text(encoding="utf-8")
)


def _canonical(value) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _digest(value) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _recompute_outer_digest(packet: dict) -> dict:
    forged = deepcopy(packet)
    forged.pop("packet_digest", None)
    forged["packet_digest"] = _digest(forged)
    return forged


def _carrier_functions():
    queue = list(ROOTS)
    seen: set[int] = set()
    found: list[types.FunctionType] = []
    while queue:
        fn = queue.pop()
        if not isinstance(fn, types.FunctionType):
            continue
        if fn.__module__ != carrier.__name__:
            continue
        identity = id(fn)
        if identity in seen:
            continue
        seen.add(identity)
        found.append(fn)
        for cell in fn.__closure__ or ():
            try:
                value = cell.cell_contents
            except ValueError:
                continue
            if isinstance(value, types.FunctionType) and value.__module__ == carrier.__name__:
                queue.append(value)
    return found


def _cell(fn: types.FunctionType, name: str):
    closure = fn.__closure__ or ()
    cells = dict(zip(fn.__code__.co_freevars, closure))
    if name not in cells:
        raise AssertionError(f"{fn.__qualname__} has no freevar {name!r}")
    return cells[name]


def _freevar(fn: types.FunctionType, name: str):
    return _cell(fn, name).cell_contents


class SemanticGenerationTest(unittest.TestCase):
    def test_boundary_contract_is_explicitly_cooperative_only(self):
        self.assertEqual(
            BOUNDARY["public_api_boundary"],
            "COOPERATIVE_IN_PROCESS_ONLY_NOT_HOSTILE_RUNTIME",
        )
        self.assertTrue(BOUNDARY["resists_module_global_rebinding"])
        self.assertTrue(BOUNDARY["resists_helper_symbol_rebinding"])
        self.assertTrue(
            BOUNDARY["resists_public_compiler_symbol_rebinding_in_verifier"]
        )
        self.assertFalse(BOUNDARY["resists_cpython_closure_cell_mutation"])
        self.assertFalse(BOUNDARY["hostile_same_process_python_supported"])
        self.assertFalse(BOUNDARY["machine_strong_same_process_integrity_claimed"])
        self.assertFalse(BOUNDARY["externally_isolated_source_verified_runner_provided"])
        self.assertEqual(
            BOUNDARY["caller_supplied_evaluation_time"],
            "REPLAY_ONLY_NOT_CURRENT",
        )
        self.assertFalse(BOUNDARY["current_submission_authority_claimed"])

    def test_every_packet_binds_exact_boundary_and_digest(self):
        owner = complete_input()
        packet = carrier.compile_packet(owner)
        self.assertEqual(packet["schema"], "tt-one-lab-lims-owner-review-packet/v3")
        self.assertEqual(packet["integrity_boundary"], BOUNDARY)
        self.assertEqual(packet["integrity_boundary_digest"], _digest(BOUNDARY))
        self.assertTrue(carrier.verify_packet(packet, owner))

    def test_detached_boundary_deletion_rejected_even_after_outer_digest_recompute(self):
        owner = complete_input()
        packet = carrier.compile_packet(owner)
        forged = deepcopy(packet)
        forged.pop("integrity_boundary")
        forged = _recompute_outer_digest(forged)
        self.assertFalse(carrier.verify_packet(forged, owner))

    def test_detached_boundary_widening_rejected_even_after_both_digest_recomputes(self):
        owner = complete_input()
        packet = carrier.compile_packet(owner)
        forged = deepcopy(packet)
        forged["integrity_boundary"]["machine_strong_same_process_integrity_claimed"] = True
        forged["integrity_boundary"]["hostile_same_process_python_supported"] = True
        forged["integrity_boundary"]["resists_cpython_closure_cell_mutation"] = True
        forged["integrity_boundary_digest"] = _digest(forged["integrity_boundary"])
        forged = _recompute_outer_digest(forged)
        self.assertFalse(carrier.verify_packet(forged, owner))

    def test_reachable_runtime_generation_has_no_global_opcode(self):
        offenders = []
        for fn in _carrier_functions():
            for instruction in dis.get_instructions(fn):
                if instruction.opname in {"LOAD_GLOBAL", "STORE_GLOBAL", "DELETE_GLOBAL"}:
                    offenders.append(
                        (fn.__qualname__, instruction.opname, instruction.argval)
                    )
        self.assertEqual(offenders, [])

    def test_reachable_runtime_generation_captures_no_mutable_builtin_container(self):
        offenders = []
        for fn in _carrier_functions():
            for name, cell in zip(fn.__code__.co_freevars, fn.__closure__ or ()):
                try:
                    value = cell.cell_contents
                except ValueError:
                    continue
                if type(value) in {dict, list, set, bytearray}:
                    offenders.append((fn.__qualname__, name, type(value).__name__))
        self.assertEqual(offenders, [])

    def test_verifier_closes_over_the_same_compiler_generation(self):
        public_compile_impl = _freevar(carrier.compile_packet, "compile_impl")
        verify_impl = _freevar(carrier.verify_packet, "verify_impl")
        verifier_compile_impl = _freevar(verify_impl, "compile_impl")
        self.assertIs(verifier_compile_impl, public_compile_impl)

    def test_active_compiler_impl_is_not_exported_as_module_global(self):
        public_compile_impl = _freevar(carrier.compile_packet, "compile_impl")
        exported_aliases = [
            name for name, value in vars(carrier).items() if value is public_compile_impl
        ]
        self.assertEqual(exported_aliases, [])

    def test_global_namespace_poison_does_not_change_cooperative_generation(self):
        owner = complete_input()
        baseline = carrier.compile_packet(owner)
        poison = {
            "type": lambda value: object,
            "dict": lambda *args, **kwargs: {"forged": True},
            "set": lambda *args, **kwargs: {"forged"},
            "all": lambda values: True,
            "sorted": lambda values: [("submission_authorized", True)],
            "ValueError": RuntimeError,
        }
        missing = object()
        original = {}
        try:
            for name, value in poison.items():
                original[name] = getattr(carrier, name, missing)
                setattr(carrier, name, value)
            self.assertEqual(carrier.compile_packet(owner), baseline)
            self.assertTrue(carrier.verify_packet(baseline, owner))
        finally:
            for name, value in original.items():
                if value is missing:
                    delattr(carrier, name)
                else:
                    setattr(carrier, name, value)

    def test_closure_cell_source_digest_can_self_remint_only_inside_unsupported_hostile_runtime(self):
        compile_impl = _freevar(carrier.compile_packet, "compile_impl")
        source_cell = _cell(compile_impl, "source_digest")
        original = source_cell.cell_contents
        forged = "0" * 64
        owner = complete_input()
        owner["source_manifest_digest"] = forged
        try:
            source_cell.cell_contents = forged
            packet = carrier.compile_packet(owner)
            self.assertEqual(packet["source_manifest_digest"], forged)
            self.assertEqual(packet["integrity_boundary"], BOUNDARY)
            self.assertTrue(carrier.verify_packet(packet, owner))
            self.assertFalse(BOUNDARY["resists_cpython_closure_cell_mutation"])
            self.assertFalse(BOUNDARY["hostile_same_process_python_supported"])
        finally:
            source_cell.cell_contents = original
        self.assertEqual(carrier.source_manifest_digest(), original)

    def test_closure_cell_buyer_route_can_self_remint_only_inside_unsupported_hostile_runtime(self):
        compile_impl = _freevar(carrier.compile_packet, "compile_impl")
        route_cell = _cell(compile_impl, "buyer_submission_email")
        original = route_cell.cell_contents
        forged = "attacker@example.test"
        owner = complete_input()
        owner["submission"]["email"] = forged
        try:
            route_cell.cell_contents = forged
            packet = carrier.compile_packet(owner)
            self.assertEqual(packet["buyer"]["submission_email"], forged)
            self.assertNotIn("SUBMISSION_METADATA_MISMATCH", packet["blockers"])
            self.assertEqual(packet["integrity_boundary"], BOUNDARY)
            self.assertTrue(carrier.verify_packet(packet, owner))
            self.assertFalse(BOUNDARY["machine_strong_same_process_integrity_claimed"])
        finally:
            route_cell.cell_contents = original

    def test_closure_cell_deadline_can_reopen_replay_only_inside_unsupported_hostile_runtime(self):
        compile_impl = _freevar(carrier.compile_packet, "compile_impl")
        deadline_cell = _cell(compile_impl, "deadline")
        original = deadline_cell.cell_contents
        owner = complete_input()
        owner["evaluated_at"] = "2026-10-02T10:00:00-04:00"
        baseline = carrier.compile_packet(owner)
        self.assertIn("PROPOSAL_DEADLINE_PASSED", baseline["blockers"])
        try:
            deadline_cell.cell_contents = datetime.fromisoformat(
                "2099-12-31T23:59:59-04:00"
            )
            packet = carrier.compile_packet(owner)
            self.assertNotIn("PROPOSAL_DEADLINE_PASSED", packet["blockers"])
            self.assertEqual(
                packet["evaluation_time_authority"],
                "CALLER_SUPPLIED_REPLAY_ONLY_NOT_CURRENT",
            )
            self.assertFalse(packet["current_deadline_readiness_claimed"])
            self.assertEqual(packet["integrity_boundary"], BOUNDARY)
            self.assertTrue(carrier.verify_packet(packet, owner))
            self.assertFalse(BOUNDARY["hostile_same_process_python_supported"])
        finally:
            deadline_cell.cell_contents = original

    def test_closure_cell_authority_can_widen_and_self_verify_only_inside_unsupported_hostile_runtime(self):
        compile_impl = _freevar(carrier.compile_packet, "compile_impl")
        authority_projection = _freevar(compile_impl, "authority_projection")
        authority_cell = _cell(authority_projection, "authority_items")
        original = authority_cell.cell_contents
        forged = tuple(
            (name, True if name in {"submission_authorized", "revenue_claimed"} else value)
            for name, value in original
        )
        owner = complete_input()
        try:
            authority_cell.cell_contents = forged
            packet = carrier.compile_packet(owner)
            self.assertTrue(packet["authority"]["submission_authorized"])
            self.assertTrue(packet["authority"]["revenue_claimed"])
            self.assertEqual(packet["integrity_boundary"], BOUNDARY)
            self.assertTrue(carrier.verify_packet(packet, owner))
            self.assertFalse(BOUNDARY["resists_cpython_closure_cell_mutation"])
            self.assertFalse(BOUNDARY["hostile_same_process_python_supported"])
            self.assertFalse(BOUNDARY["machine_strong_same_process_integrity_claimed"])
        finally:
            authority_cell.cell_contents = original
        restored = carrier.compile_packet(owner)
        self.assertFalse(restored["authority"]["submission_authorized"])
        self.assertFalse(restored["authority"]["revenue_claimed"])

    def test_public_compiler_symbol_rebinding_still_does_not_change_verifier(self):
        owner = complete_input()
        baseline = carrier.compile_packet(owner)
        forged = deepcopy(baseline)
        forged["authority"]["submission_authorized"] = True
        forged = _recompute_outer_digest(forged)
        original = carrier.compile_packet
        try:
            carrier.compile_packet = lambda ignored: forged
            self.assertTrue(carrier.verify_packet(baseline, owner))
            self.assertFalse(carrier.verify_packet(forged, owner))
        finally:
            carrier.compile_packet = original


if __name__ == "__main__":
    unittest.main()
