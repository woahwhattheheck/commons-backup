# SPDX-License-Identifier: Apache-2.0
"""Exercise the actual shared opponent loader without installing the engine."""
import hashlib
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

TARGET = Path(os.environ.get('TITAN_OPPONENT_RESOLVER',
    Path(__file__).resolve().parent.parent / 'cloud-model-lab' / 'arlene_arm.py'))


def load_resolver(path=TARGET):
    # Only unrelated game/overlay imports are replaced. _load, make_opponent,
    # inspect, importlib and each on-disk opponent module execute unchanged.
    deps = {n: types.ModuleType(n) for n in
            ('cards', 'native_motifs', 'arlene_motifs', 'arlene_plan', 'route_cards')}
    spec = importlib.util.spec_from_file_location('opponent_contract_subject', path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, deps):
        spec.loader.exec_module(module)
    return module


class OpponentInvocationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.subject = load_resolver()
        self.path = Path(self.temp.name) / 'opponent.py'

    def opponent(self, source):
        self.path.write_text(source, encoding='utf-8')
        self.subject.OPPONENTS['fixture'] = str(self.path)
        return self.subject.make_opponent('fixture', None)

    def test_one_argument(self):
        fn, _ = self.opponent('def agent(obs): return obs\n')
        obs = {}; self.assertIs(fn(obs, {'cfg': 1}), obs)

    def test_two_arguments(self):
        fn, _ = self.opponent('def agent(obs, cfg): return obs, cfg\n')
        obs, cfg = {}, {}; out = fn(obs, cfg)
        self.assertIs(out[0], obs); self.assertIs(out[1], cfg)

    def test_optional_configuration_is_supplied(self):
        fn, _ = self.opponent('def agent(obs, cfg=None): return cfg\n')
        cfg = {}; self.assertIs(fn({}, cfg), cfg)

    def test_required_body_typeerror_is_preserved(self):
        fn, _ = self.opponent('def agent(obs, cfg):\n obs.append(1)\n raise TypeError("body-sentinel")\n')
        obs = []
        with self.assertRaisesRegex(TypeError, '^body-sentinel$'):
            fn(obs, {})
        self.assertEqual(obs, [1])

    def test_optional_body_typeerror_is_not_retried(self):
        fn, _ = self.opponent('def agent(obs, cfg=None):\n obs.append(1)\n if cfg is not None: raise TypeError("body-sentinel")\n return "masked"\n')
        obs = []
        with self.assertRaisesRegex(TypeError, '^body-sentinel$'):
            fn(obs, {})
        self.assertEqual(obs, [1])

    def test_variadic_body_typeerror_is_not_retried(self):
        fn, _ = self.opponent('def agent(*args):\n args[0].append(len(args))\n raise TypeError("variadic-body")\n')
        obs = []
        with self.assertRaisesRegex(TypeError, '^variadic-body$'):
            fn(obs, {})
        self.assertEqual(obs, [2])

    def test_other_exception_is_unchanged(self):
        fn, _ = self.opponent('def agent(obs, cfg):\n obs.append(1)\n raise ValueError("value-body")\n')
        obs = []
        with self.assertRaisesRegex(ValueError, '^value-body$'):
            fn(obs, {})
        self.assertEqual(obs, [1])

    def test_bound_method(self):
        fn, _ = self.opponent('class Actor:\n def act(self, obs, cfg=None): return obs, cfg\nagent=Actor().act\n')
        obs, cfg = {}, {}; self.assertEqual(fn(obs, cfg), (obs, cfg))

    def test_callable_object(self):
        fn, _ = self.opponent('class Actor:\n def __call__(self, obs): return obs\nagent=Actor()\n')
        obs = {}; self.assertIs(fn(obs, {}), obs)

    def test_partial(self):
        fn, _ = self.opponent('from functools import partial\ndef run(prefix, obs, cfg): return prefix, obs, cfg\nagent=partial(run, "x")\n')
        obs, cfg = {}, {}; self.assertEqual(fn(obs, cfg), ('x', obs, cfg))

    def test_optional_keyword_only_keeps_one_argument_shape(self):
        fn, _ = self.opponent('def agent(obs, *, configuration="default"): return configuration\n')
        self.assertEqual(fn({}, {}), 'default')

    def test_unsupported_arity_does_not_execute(self):
        self.path.write_text('def agent(obs, cfg, third): raise AssertionError("executed")\n')
        self.subject.OPPONENTS['fixture'] = str(self.path)
        with self.assertRaises(TypeError):
            self.subject.make_opponent('fixture', None)

    def test_state_is_fresh_per_opponent(self):
        fn, _ = self.opponent('count=0\ndef agent(obs):\n global count\n count+=1\n return count\n')
        other, _ = self.subject.make_opponent('fixture', None)
        self.assertEqual([fn({}, {}), fn({}, {}), other({}, {})], [1, 2, 1])

    def test_arlene_special_case_is_unmodified(self):
        class Agent:
            def __init__(self): self.calls = 0
            def act(self, obs): self.calls += 1; return obs, self.calls
        A = types.SimpleNamespace(Agent=Agent)
        fn, ident = self.subject.make_opponent('arlene', A)
        other, _ = self.subject.make_opponent('arlene', A)
        obs = {}; self.assertEqual(fn(obs, {}), (obs, 1))
        self.assertEqual(fn(obs, {}), (obs, 2))
        self.assertEqual(other(obs, {}), (obs, 1))
        self.assertEqual(ident, {'label': 'arlene (vendored)'})

    def test_metadata_matches_loaded_source(self):
        _, ident = self.opponent('def agent(obs): return obs\n')
        self.assertEqual(ident['sha256'], hashlib.sha256(self.path.read_bytes()).hexdigest())
        self.assertEqual(ident['path'], str(self.path.resolve()))

    def test_signature_is_bound_only_at_construction(self):
        fn, _ = self.opponent('def agent(obs, cfg): return obs\n')
        with patch('inspect.signature', side_effect=AssertionError('rebound')):
            obs = {}; self.assertIs(fn(obs, {}), obs)
            self.assertIs(fn(obs, {}), obs)


if __name__ == '__main__':
    unittest.main(verbosity=2)
