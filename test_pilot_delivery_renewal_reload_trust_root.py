import builtins
import contextlib
import importlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

from revenue.pilot_delivery_renewal_expansion_gate import common, engine
from revenue.pilot_delivery_renewal_expansion_gate.test_gate import current_packet


class ReloadStableTrustRootTests(unittest.TestCase):
    def _generation_one_claim_packet(self):
        packet = current_packet()
        for row in packet["milestones"]:
            row["commercial_generation"] = 1
        packet["payment"]["commercial_generation"] = 1
        return packet

    def _assert_public_error_and_cli(self, stable_error):
        packet = current_packet()
        packet["baseline"]["generation"] = True
        with self.assertRaisesRegex(stable_error, "integer required"):
            engine.compile_current(packet)

        with tempfile.TemporaryDirectory() as td:
            packet_path = Path(td) / "packet.json"
            packet_path.write_text(json.dumps(packet), encoding="utf-8")
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                rc = engine.main(["compile", str(packet_path)])
            self.assertEqual(rc, 2)
            self.assertIn("ERROR:", stderr.getvalue())
            self.assertNotIn("Traceback", stderr.getvalue())

    def test_hostile_max_during_reload_cannot_ratify_generation_one(self):
        packet = self._generation_one_claim_packet()
        control = engine.compile_current(packet)
        self.assertEqual(control["state"], engine.HOLD_ACCEPTANCE)
        self.assertEqual(control["commercial_generation"], 2)
        original_compile = engine.compile_current
        original_verify = engine.verify_receipt

        real_max = builtins.max

        def forged_max(*args, **kwargs):
            if len(args) == 1 and not kwargs and type(args[0]) is list and args[0] == [1, 2]:
                return 1
            return real_max(*args, **kwargs)

        try:
            builtins.max = forged_max
            importlib.reload(engine)
        finally:
            builtins.max = real_max

        self.assertIs(engine.compile_current, original_compile)
        self.assertIs(engine.verify_receipt, original_verify)
        after = engine.compile_current(packet)
        self.assertEqual(after["state"], engine.HOLD_ACCEPTANCE)
        self.assertEqual(after["commercial_generation"], 2)
        self.assertFalse(any(after["authority"].values()))

    def test_hostile_max_during_direct_engine_execution_reuses_first_generation(self):
        packet = self._generation_one_claim_packet()
        original_compile = engine.compile_current
        original_verify = engine.verify_receipt
        real_max = builtins.max

        def forged_max(*args, **kwargs):
            if len(args) == 1 and not kwargs and type(args[0]) is list and args[0] == [1, 2]:
                return 1
            return real_max(*args, **kwargs)

        module_name = f"{engine.__package__}._hostile_engine_probe"
        spec = importlib.util.spec_from_file_location(module_name, engine.__file__)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        probe = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = probe
        try:
            builtins.max = forged_max
            spec.loader.exec_module(probe)
        finally:
            builtins.max = real_max
            sys.modules.pop(module_name, None)

        self.assertIs(probe.compile_current, original_compile)
        self.assertIs(probe.verify_receipt, original_verify)
        self.assertIs(probe.GateError, engine.GateError)
        after = probe.compile_current(packet)
        self.assertEqual(after["state"], engine.HOLD_ACCEPTANCE)
        self.assertEqual(after["commercial_generation"], 2)
        self.assertFalse(any(after["authority"].values()))

    def test_hostile_isinstance_during_reload_cannot_admit_bool_integer(self):
        packet = current_packet()
        packet["baseline"]["generation"] = True
        with self.assertRaisesRegex(engine.GateError, "integer required"):
            engine.compile_current(packet)

        original_compile = engine.compile_current
        real_isinstance = builtins.isinstance

        def forged_isinstance(value, kind):
            if value is True and kind is bool:
                return False
            return real_isinstance(value, kind)

        try:
            builtins.isinstance = forged_isinstance
            importlib.reload(engine)
        finally:
            builtins.isinstance = real_isinstance

        self.assertIs(engine.compile_current, original_compile)
        with self.assertRaisesRegex(engine.GateError, "integer required"):
            engine.compile_current(packet)

    def test_common_gate_error_rebind_then_engine_reload_preserves_public_generation(self):
        stable_error = engine.GateError
        prior_common_error = common.GateError

        class ReplacementGateError(ValueError):
            pass

        try:
            common.GateError = ReplacementGateError
            importlib.reload(engine)
            self.assertIs(engine.GateError, stable_error)
            self._assert_public_error_and_cli(stable_error)
        finally:
            common.GateError = prior_common_error
            importlib.reload(engine)

    def test_common_reload_preserves_public_error_generation_and_cli_catches_it(self):
        stable_error = engine.GateError
        importlib.reload(common)
        self.assertIsNot(common.GateError, stable_error)
        importlib.reload(engine)
        self.assertIs(engine.GateError, stable_error)
        self._assert_public_error_and_cli(stable_error)

    def test_packet_large_child_fails_at_node_budget(self):
        packet = current_packet()
        packet["oversized_untrusted_child"] = [None] * 10_001
        with self.assertRaisesRegex(engine.GateError, "node budget exceeded"):
            engine.compile_current(packet)

    def test_receipt_large_child_fails_at_node_budget(self):
        packet = current_packet()
        receipt = engine.compile_current(packet)
        receipt["oversized_untrusted_child"] = [None] * 10_001
        with self.assertRaisesRegex(engine.GateError, "node budget exceeded"):
            engine.verify_receipt(packet, receipt)

    def test_packet_large_string_fails_at_character_budget(self):
        packet = current_packet()
        packet["oversized_untrusted_text"] = "x" * 2_000_001
        with self.assertRaisesRegex(engine.GateError, "character budget exceeded"):
            engine.compile_current(packet)


if __name__ == "__main__":
    unittest.main()
