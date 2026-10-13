from __future__ import annotations

import builtins
import inspect
import unittest
from pathlib import Path, PurePath
from unittest.mock import patch

from . import AuthorityError, compile_current, verify_current_authority
from . import authority as a
from . import engine
from . import strict_json
from .cli import main as cli_main
from .current_runtime import assert_current_runtime
from .test_authority import packet


class FrozenCurrentRuntimeTests(unittest.TestCase):
    def _both_fail_closed(self) -> None:
        with self.assertRaises(AuthorityError):
            compile_current(packet())
        with self.assertRaises(AuthorityError):
            verify_current_authority(packet(), {})

    def test_guard_is_intact_immediately_after_import(self):
        self.assertIsNone(assert_current_runtime())

    def test_public_surfaces_have_no_trust_or_time_injection_parameters(self):
        self.assertEqual(tuple(inspect.signature(compile_current).parameters), ("packet",))
        self.assertEqual(tuple(inspect.signature(verify_current_authority).parameters), ("packet", "report"))
        self.assertEqual(tuple(inspect.signature(cli_main).parameters), ("argv",))
        with self.assertRaises(TypeError):
            compile_current(packet(), _clock=lambda: None)
        with self.assertRaises(TypeError):
            verify_current_authority(packet(), {}, _guard=lambda: True)

    def test_pathlib_special_dispatch_is_not_in_current_trust_root(self):
        expected_root = a._fixed_host_root()
        expected_paths = a._host_paths()
        concrete = type(Path("."))
        mutations = (
            (PurePath, "__truediv__", lambda self, _other: Path("/tmp/attacker")),
            (concrete, "__truediv__", lambda self, _other: Path("/tmp/attacker")),
            (PurePath, "__new__", staticmethod(lambda cls, *_a, **_k: object.__new__(cls))),
        )
        for owner, name, replacement in mutations:
            with self.subTest(owner=owner.__name__, name=name), patch.object(owner, name, replacement):
                self.assertEqual(a._fixed_host_root(), expected_root)
                self.assertEqual(a._host_paths(), expected_paths)
                assert_current_runtime()

    def test_post_import_rebinding_of_authority_roots_fails_closed(self):
        mutations = (
            (a, "now_utc", lambda: None),
            (a, "_key", lambda: b"x" * 32),
            (a, "_load_current", lambda _key: ({}, "0" * 64)),
            (a, "_authority_status", lambda *_args, **_kwargs: {"authenticated": True}),
            (a, "canonical_json", lambda _value: "{}"),
            (a, "digest", lambda _value: "0" * 64),
            (a, "_compile_current_at", lambda *_args: {"state": a.READY}),
            (a, "_verify_current_at", lambda *_args: {"state": "CURRENT_VERIFIED"}),
            (a, "_host_paths", lambda: ("/tmp/a", "/tmp/b", "/tmp/c")),
        )
        for owner, name, replacement in mutations:
            with self.subTest(name=name), patch.object(owner, name, replacement):
                self._both_fail_closed()

    def test_post_import_rebinding_of_clock_json_and_builtin_graph_fails_closed(self):
        class FakeDateTime:
            @classmethod
            def now(cls, _tz=None):
                raise AssertionError("fake clock must never be authoritative")

        mutations = (
            (engine, "datetime", FakeDateTime),
            (strict_json.json, "dumps", lambda *_a, **_k: "{}"),
            (strict_json.json, "loads", lambda *_a, **_k: {}),
            (strict_json.hashlib, "sha256", lambda *_a, **_k: None),
            (builtins, "any", lambda _items: False),
        )
        for owner, name, replacement in mutations:
            with self.subTest(name=f"{getattr(owner, '__name__', type(owner).__name__)}.{name}"), patch.object(owner, name, replacement):
                self._both_fail_closed()

    def test_in_place_json_class_and_cached_encoder_mutation_fails_closed(self):
        mutations = (
            (strict_json.json.JSONEncoder, "encode", lambda self, _obj: "{}"),
            (strict_json.json.JSONDecoder, "decode", lambda self, _text, **_kw: {}),
            (strict_json.json._default_encoder, "encode", lambda _obj: "{}"),
            (strict_json.json._default_decoder, "decode", lambda _text, **_kw: {}),
        )
        for owner, name, replacement in mutations:
            with self.subTest(owner=type(owner).__name__, name=name), patch.object(owner, name, replacement):
                self._both_fail_closed()

    def test_post_import_rebinding_and_in_place_mac_graph_mutation_fails_closed(self):
        mutations = (
            (a.hmac, "new", lambda *_a, **_k: None),
            (a.hmac, "compare_digest", lambda *_a, **_k: True),
            (a.hashlib, "sha256", lambda *_a, **_k: None),
            (a.hmac.HMAC, "__init__", lambda self, *_a, **_k: None),
            (a.hmac.HMAC, "digest", lambda self: b"x" * 32),
        )
        for owner, name, replacement in mutations:
            with self.subTest(name=name), patch.object(owner, name, replacement):
                self._both_fail_closed()

    def test_runtime_recovers_after_temporary_rebinding_is_restored(self):
        original = a.now_utc
        with patch.object(a, "now_utc", lambda: None):
            self._both_fail_closed()
        self.assertIs(a.now_utc, original)
        assert_current_runtime()
        try:
            compile_current(packet())
        except AuthorityError as exc:
            self.assertNotIn("dependency graph changed", str(exc))

    def test_authority_source_has_no_public_current_verifier_surface(self):
        from pathlib import Path

        from tools.current_readiness_guard.guard import analyze_source

        source = Path(__file__).with_name("authority.py").read_text(encoding="utf-8")
        findings = analyze_source(
            source, path="revenue/service_deal_economics/authority.py"
        )
        self.assertEqual([(finding.rule, finding.function) for finding in findings], [])
        self.assertIs(a.verify_current_authority, verify_current_authority)


if __name__ == "__main__":
    unittest.main()
