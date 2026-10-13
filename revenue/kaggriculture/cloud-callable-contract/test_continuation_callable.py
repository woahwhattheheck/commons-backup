"""Exercise the complete continuation module and its real file-policy loader.

TITAN_CONTINUATION_PATH selects another source revision. The full source is
compiled unchanged; only unrelated imports are isolated with temporary module
entries. Built-in dispatch uses an explicitly supplied engine fixture. No game,
opponent, simulation, or seed is created by this suite.
"""

import hashlib
import os
from pathlib import Path
import sys
import tempfile
import textwrap
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch


DEFAULT = Path(__file__).resolve().parents[1] / "cloud-model-lab" / "continuation.py"
SOURCE = Path(os.environ.get("TITAN_CONTINUATION_PATH", DEFAULT))


def read_continuation():
    cards = ModuleType("cards")
    constraints = ModuleType("constraints")

    def unused_engine():
        raise AssertionError("An engine must be supplied explicitly by the test")

    constraints.engine = unused_engine
    namespace = {"__name__": "_continuation_callable_contract", "__file__": str(SOURCE)}
    with patch.dict(sys.modules, {"cards": cards, "constraints": constraints}):
        exec(compile(SOURCE.read_bytes(), str(SOURCE), "exec"), namespace)
    return namespace


class ContinuationCallableContract(unittest.TestCase):
    def setUp(self):
        self.namespace = read_continuation()
        self.load = self.namespace["load_agent"]
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def policy(self, source, entry="agent"):
        path = self.root / "policy.py"
        path.write_text(textwrap.dedent(source), encoding="utf-8")
        return self.load(f"{path}::{entry}")

    def test_one_argument_preserves_observation(self):
        call, _ = self.policy("def agent(obs): return obs")
        obs = {"value": 42}
        self.assertIs(call(obs, {"provided": True}), obs)

    def test_two_arguments_preserve_objects(self):
        call, _ = self.policy("def agent(obs, cfg): return obs, cfg")
        obs, cfg = {}, {}
        result = call(obs, cfg)
        self.assertIs(result[0], obs)
        self.assertIs(result[1], cfg)

    def test_optional_configuration_prefers_two_arguments(self):
        call, _ = self.policy("def agent(obs, cfg=None): return cfg")
        cfg = {"provided": True}
        self.assertIs(call({}, cfg), cfg)

    def test_wrapper_default_configuration_remains_none(self):
        call, _ = self.policy("def agent(obs, cfg): return cfg")
        self.assertIsNone(call({}))

    def test_positional_only_configuration(self):
        call, _ = self.policy("def agent(obs, cfg, /): return obs, cfg")
        obs, cfg = {}, {}
        result = call(obs, cfg)
        self.assertIs(result[0], obs)
        self.assertIs(result[1], cfg)

    def test_variadic_callable_receives_both_arguments(self):
        call, _ = self.policy("def agent(*args): return args")
        obs, cfg = {}, {}
        result = call(obs, cfg)
        self.assertEqual(len(result), 2)
        self.assertIs(result[0], obs)
        self.assertIs(result[1], cfg)

    def test_bound_method(self):
        call, _ = self.policy("""
            class Policy:
                def act(self, obs, cfg): return obs, cfg
            agent = Policy().act
        """)
        obs, cfg = {}, {}
        result = call(obs, cfg)
        self.assertIs(result[0], obs)
        self.assertIs(result[1], cfg)

    def test_partial_callable(self):
        call, _ = self.policy("""
            from functools import partial
            def run(prefix, obs, cfg): return prefix, obs, cfg
            agent = partial(run, 10)
        """)
        obs, cfg = {}, {}
        result = call(obs, cfg)
        self.assertEqual(result[0], 10)
        self.assertIs(result[1], obs)
        self.assertIs(result[2], cfg)

    def test_optional_keyword_configuration_keeps_one_argument_form(self):
        call, _ = self.policy("def agent(obs, *, cfg='default'): return obs, cfg")
        obs = {}
        result = call(obs, {"provided": True})
        self.assertIs(result[0], obs)
        self.assertEqual(result[1], "default")

    def assert_body_error(self, source, error):
        call, _ = self.policy(source)
        obs = {"calls": 0, "error": error}
        caught = None
        try:
            call(obs, {"provided": True})
        except Exception as exc:
            caught = exc
        # Both diagnostics are retained even if the first check fails.
        with self.subTest("exception identity"):
            self.assertIs(caught, error)
        with self.subTest("single invocation"):
            self.assertEqual(obs["calls"], 1)

    def test_required_configuration_body_typeerror_identity(self):
        self.assert_body_error("""
            def agent(obs, cfg):
                obs['calls'] += 1
                raise obs['error']
        """, TypeError("required-config-body"))

    def test_optional_configuration_body_typeerror_never_retries(self):
        self.assert_body_error("""
            def agent(obs, cfg=None):
                obs['calls'] += 1
                if cfg is not None:
                    raise obs['error']
                return {'silently_retried': True}
        """, TypeError("optional-config-body"))

    def test_variadic_body_typeerror_never_retries(self):
        self.assert_body_error("""
            def agent(obs, *args):
                obs['calls'] += 1
                raise obs['error']
        """, TypeError("variadic-body"))

    def test_one_argument_body_typeerror_identity(self):
        self.assert_body_error("""
            def agent(obs):
                obs['calls'] += 1
                raise obs['error']
        """, TypeError("one-argument-body"))

    def test_other_body_exception_identity(self):
        self.assert_body_error("""
            def agent(obs, cfg=None):
                obs['calls'] += 1
                raise obs['error']
        """, RuntimeError("runtime-body"))

    def test_separate_loads_preserve_module_state_isolation(self):
        first, _ = self.policy("""
            calls = 0
            def agent(obs, cfg=None):
                global calls
                calls += 1
                return calls
        """)
        second, _ = self.load(f"{self.root / 'policy.py'}::agent")
        self.assertEqual([first({}), first({}), second({})], [1, 2, 1])

    def test_callable_object_preserves_state(self):
        call, _ = self.policy("""
            class Policy:
                def __init__(self): self.calls = 0
                def __call__(self, obs):
                    self.calls += 1
                    return self.calls
            agent = Policy()
        """)
        self.assertEqual([call({}, {}), call({}, {})], [1, 2])

    def test_signature_selection_never_executes_policy(self):
        sentinel = self.root / "policy-ran"
        call, _ = self.policy(f"""
            from pathlib import Path
            def agent(obs, cfg):
                Path({str(sentinel)!r}).write_text('ran')
                return obs
        """)
        self.assertFalse(sentinel.exists())
        call({}, {})
        self.assertEqual(sentinel.read_text(), "ran")

    def test_custom_entrypoint_and_identity_metadata(self):
        call, metadata = self.policy("def finish(obs): return obs", entry="finish")
        path = self.root / "policy.py"
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        spec = f"{path}::finish"
        self.assertEqual(metadata, {
            "spec": spec, "kind": "file", "path": str(path), "function": "finish",
            "sha256": digest, "label": f"policy.py::finish@{digest[:12]}",
        })
        obs = {}
        self.assertIs(call(obs), obs)

    def test_builtin_dispatch_and_metadata_preserved(self):
        calls = []

        def builtin(label):
            def call(obs):
                calls.append((label, obs))
                return label
            return call

        fixture = SimpleNamespace(**{
            f"{label}_agent": builtin(label) for label in ("starter", "random", "pass")
        })
        self.namespace["engine"] = lambda: fixture
        for label in ("starter", "random", "pass"):
            with self.subTest(label=label):
                call, metadata = self.load(label)
                obs = {"label": label}
                self.assertEqual(call(obs, {"ignored": True}), label)
                self.assertEqual(metadata, {
                    "spec": label, "kind": "builtin", "path": None,
                    "sha256": None, "label": label,
                })
                self.assertIs(calls[-1][1], obs)
        self.assertEqual(len(calls), 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
