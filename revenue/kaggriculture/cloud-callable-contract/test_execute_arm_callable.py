"""Exercise the real executor loader without importing its unused game engine.

Set TITAN_EXECUTOR_PATH to test another source revision. Only the top-level
`import cards as cards_mod` is omitted when loading: every function body,
including load_callable, is compiled unchanged from the supplied source.
No game, opponent, simulation or seed is created by this suite.
"""
import ast
import hashlib
import os
from pathlib import Path
import sys
import tempfile
import textwrap
import unittest


DEFAULT = Path(__file__).resolve().parents[1] / 'cloud-model-lab' / 'execute_arm.py'
SOURCE = Path(os.environ.get('TITAN_EXECUTOR_PATH', DEFAULT))


def read_executor():
    tree = ast.parse(SOURCE.read_text(encoding='utf-8'), filename=str(SOURCE))
    tree.body = [node for node in tree.body if not (
        isinstance(node, ast.Import) and any(a.name == 'cards' for a in node.names))]
    namespace = {'__name__': '_executor_callable_contract', '__file__': str(SOURCE)}
    exec(compile(tree, str(SOURCE), 'exec'), namespace)
    return namespace['load_callable']


class CallableContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.load = staticmethod(read_executor())

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.original_modules = set(sys.modules)
        self.original_path = list(sys.path)
        self.addCleanup(self.cleanup_imports)

    def cleanup_imports(self):
        sys.path[:] = self.original_path
        for name in set(sys.modules) - self.original_modules:
            module = sys.modules.get(name)
            location = getattr(module, '__file__', '')
            if location and str(location).startswith(str(self.root)):
                sys.modules.pop(name, None)

    def factory(self, source, extra=()):
        path = self.root / 'policy.py'
        path.write_text(textwrap.dedent(source), encoding='utf-8')
        return self.load(path, extra)

    def call(self, source, observation=None, configuration=None):
        factory, _ = self.factory(source)
        obs = {} if observation is None else observation
        cfg = {} if configuration is None else configuration
        return factory()(obs, cfg)

    def test_two_arguments_preserve_objects(self):
        obs, cfg = {}, {}
        result = self.call('def agent(obs, cfg): return obs, cfg', obs, cfg)
        self.assertIs(result[0], obs)
        self.assertIs(result[1], cfg)

    def test_one_argument_supported(self):
        obs = {'value': 42}
        self.assertIs(self.call('def agent(obs): return obs', obs), obs)

    def test_optional_configuration_prefers_two_arguments(self):
        cfg = {'provided': True}
        self.assertIs(self.call('def agent(obs, cfg=None): return cfg', {}, cfg), cfg)

    def test_variadic_callable_receives_both_arguments(self):
        obs, cfg = {}, {}
        self.assertEqual(self.call('def agent(*args): return args', obs, cfg), (obs, cfg))

    def test_positional_only_callable(self):
        cfg = {'provided': True}
        self.assertIs(self.call('def agent(obs, cfg, /): return cfg', {}, cfg), cfg)

    def test_required_two_argument_typeerror_is_preserved(self):
        obs = {}
        factory, _ = self.factory('''
            def agent(obs, cfg):
                obs['calls'] = obs.get('calls', 0) + 1
                raise TypeError('policy-body-sentinel')
        ''')
        with self.assertRaisesRegex(TypeError, '^policy-body-sentinel$'):
            factory()(obs, {})
        self.assertEqual(obs['calls'], 1)

    def test_optional_configuration_typeerror_never_retries(self):
        obs = {}
        factory, _ = self.factory('''
            def agent(obs, cfg=None):
                obs['calls'] = obs.get('calls', 0) + 1
                if cfg is not None:
                    raise TypeError('original-policy-failure')
                return {'silently_retried': True}
        ''')
        with self.assertRaisesRegex(TypeError, '^original-policy-failure$'):
            factory()(obs, {})
        self.assertEqual(obs['calls'], 1)

    def test_variadic_typeerror_never_retries(self):
        obs = {}
        factory, _ = self.factory('''
            def agent(obs, *args):
                obs['calls'] = obs.get('calls', 0) + 1
                raise TypeError('variadic-policy-failure')
        ''')
        with self.assertRaisesRegex(TypeError, '^variadic-policy-failure$'):
            factory()(obs, {})
        self.assertEqual(obs['calls'], 1)

    def test_one_argument_body_typeerror_preserved(self):
        obs = {}
        factory, _ = self.factory('''
            def agent(obs):
                obs['calls'] = obs.get('calls', 0) + 1
                raise TypeError('one-argument-body')
        ''')
        with self.assertRaisesRegex(TypeError, '^one-argument-body$'):
            factory()(obs, {})
        self.assertEqual(obs['calls'], 1)

    def test_other_body_exception_not_retried(self):
        obs = {}
        factory, _ = self.factory('''
            def agent(obs, cfg=None):
                obs['calls'] = obs.get('calls', 0) + 1
                raise RuntimeError('runtime-body')
        ''')
        with self.assertRaisesRegex(RuntimeError, '^runtime-body$'):
            factory()(obs, {})
        self.assertEqual(obs['calls'], 1)

    def test_stateful_factory_is_fresh_per_match(self):
        factory, _ = self.factory('''
            class Policy:
                def __init__(self): self.calls = 0
                def __call__(self, obs, cfg):
                    self.calls += 1
                    return self.calls
            def make_agent(): return Policy()
        ''')
        first, second = factory(), factory()
        self.assertEqual([first({}, {}), first({}, {}), second({}, {})], [1, 2, 1])

    def test_bound_method_factory(self):
        result = self.call('''
            class Policy:
                def act(self, obs): return obs['value']
            def make_agent(): return Policy().act
        ''', {'value': 17})
        self.assertEqual(result, 17)

    def test_partial_factory(self):
        self.assertEqual(self.call('''
            from functools import partial
            def run(prefix, obs, cfg): return prefix + obs['value'] + cfg['value']
            def make_agent(): return partial(run, 10)
        ''', {'value': 2}, {'value': 3}), 15)

    def test_factory_typeerror_preserved(self):
        factory, _ = self.factory('''
            def make_agent(): raise TypeError('construction-error')
        ''')
        with self.assertRaisesRegex(TypeError, '^construction-error$'):
            factory()

    def test_signature_selection_never_executes_policy(self):
        sentinel = self.root / 'policy-ran'
        factory, _ = self.factory(f'''
            from pathlib import Path
            def agent(obs, cfg):
                Path({str(sentinel)!r}).write_text('ran')
                return obs
        ''')
        call = factory()
        self.assertFalse(sentinel.exists())
        call({}, {})
        self.assertEqual(sentinel.read_text(), 'ran')

    def test_metadata_and_extra_import_root_preserved(self):
        vendor = self.root / 'vendor'
        vendor.mkdir()
        (vendor / 'callable_dependency.py').write_text('VALUE = 29\n')
        factory, metadata = self.factory('''
            from callable_dependency import VALUE
            def agent(obs, cfg): return VALUE
        ''', (str(vendor),))
        self.assertEqual(factory()({}, {}), 29)
        expected = hashlib.sha256((self.root / 'policy.py').read_bytes()).hexdigest()
        self.assertEqual(metadata['sha256'], expected)
        self.assertEqual(metadata['path'], str(self.root / 'policy.py'))
        self.assertTrue(metadata['label'].endswith(expected[:12]))


if __name__ == '__main__':
    unittest.main(verbosity=2)
