# SPDX-License-Identifier: Apache-2.0
"""Offline native-entrypoint parity and alternating timing, one game per process.

Authenticates the complete checked native package from bytes captured exactly once.
Child game processes execute the already-authenticated captured runner bytes through
a tiny parent-owned stdin bootstrap; they never reopen a repository or scratch
runner pathname. After each child authenticates its native-root manifest, runtime
Python and captured data reads execute from in-memory buffers through a memory
importer/file view rather than from materialized runtime paths. Child interpreter
startup is isolated from ambient Python startup hooks before the bootstrap runs.
No repository control helper is imported before capture/authentication; the
composer is compiled and executed only from already-authenticated captured bytes.
Runner provenance is supplied from external exact-head authority rather than
inferred from the mutable checkout. No config, route, archive or release mutation.
No observation filtering, actor/market truncation or synthetic fill.
"""
from __future__ import annotations
import argparse
import ast
import builtins
import collections
import copy
from contextlib import contextmanager
import hashlib
import importlib.abc
import importlib.machinery
import importlib.util
import io
import json
import locale
import os
from pathlib import Path, PurePosixPath
import random
import statistics
import subprocess
import sys
import tempfile
import time
import types
from typing import Any, Callable

SOURCE_SHA256 = 'e87d70dd3bcf5aea1e929f1a5dbdc86f3cc33d8a0b3492986f2970fc8e774be2'
BASE_MECHANICS_BLOB = '044a4f9c0a4a44dde10ada57563238bcaf82075d'
ENGINE_GIT_BLOBS = {
    'checks/reference/engine/kaggriculture.py': '3c202c7ee921da239356789e266b694635103fc4',
    'checks/reference/engine/kaggriculture.json': 'b354d06b742fe48402513792253f1a5c29366b20',
    'checks/reference/engine/utils.py': '91c8822ee6201ba4a5a8416c7dbe34f95dd61c87',
}
CONTROL_FILES = ('run_kinetic_games.py', 'compose_kinetic.py', 'check_kinetic.py')
CONTROL_GIT_BLOBS = {
    'compose_kinetic.py': 'd34362e98277c930b7b28519f2892bea758b3878',
    'check_kinetic.py': 'a8bf67cca8f34492dc28286da62168da5d59c146',
}
VIRTUAL_RUNTIME_ROOT = '/__titan_kinetic_captured_runtime__'
CAPTURED_RUNNER_BOOTSTRAP = r'''import hashlib
import sys
expected = sys.argv.pop(1)
raw = sys.stdin.buffer.read()
actual = hashlib.sha1(b"blob " + str(len(raw)).encode() + bytes([0]) + raw).hexdigest()
if actual != expected:
    raise SystemExit("captured runner Git blob mismatch before exec")
namespace = {
    "__name__": "__main__",
    "__file__": "<captured-run_kinetic_games.py>",
    "__package__": None,
    "_KINETIC_BOOTSTRAP_RUNNER_BLOB": actual,
}
exec(compile(raw, namespace["__file__"], "exec"), namespace, namespace)
'''


class Struct(dict):
    """Exact tiny attribute-dict shape used by the pinned reference loader."""
    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(key) from None

    def __setattr__(self, key, value):
        self[key] = value


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sha_bytes(raw):
    return hashlib.sha256(raw).hexdigest()


def git_blob(raw):
    """Git blob identity owned by this runner, not by a repo-path helper."""
    if not isinstance(raw, bytes):
        raise TypeError('git_blob requires bytes')
    return hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()


def _git_blob_pin(value, name='expected runner Git blob'):
    if not isinstance(value, str) or len(value) != 40 or any(c not in '0123456789abcdef' for c in value):
        raise ValueError(f'Invalid {name}')
    return value


def _sha256_pin(value, name='expected SHA-256'):
    if not isinstance(value, str) or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
        raise ValueError(f'Invalid {name}')
    return value


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def _safe_relative(name):
    if not isinstance(name, str) or not name or '\\' in name:
        raise ValueError(f'Unsafe runtime member: {name!r}')
    rel = PurePosixPath(name)
    if rel.is_absolute() or '..' in rel.parts or '.' in rel.parts:
        raise ValueError(f'Unsafe runtime member: {name!r}')
    return rel


def _virtual_runtime_path(name):
    rel = _safe_relative(name)
    return str(PurePosixPath(VIRTUAL_RUNTIME_ROOT, *rel.parts))


def control_bundle_digest(captured):
    """Length-delimited digest of the exact parent-authenticated control bytes."""
    if set(captured) != set(CONTROL_FILES):
        raise ValueError('Incomplete control bundle')
    digest = hashlib.sha256()
    for name in CONTROL_FILES:
        raw = captured[name]
        if not isinstance(raw, bytes):
            raise ValueError(f'Invalid control bytes: {name}')
        encoded_name = name.encode('utf-8')
        digest.update(len(encoded_name).to_bytes(4, 'big'))
        digest.update(encoded_name)
        digest.update(len(raw).to_bytes(8, 'big'))
        digest.update(raw)
    return digest.hexdigest()


def capture_control_bundle(root, expected_runner_git_blob):
    """Capture runner plus pinned helpers exactly once under external runner identity."""
    expected_runner_git_blob = _git_blob_pin(expected_runner_git_blob)
    root = Path(root).resolve(strict=True)
    captured = {}
    for name in CONTROL_FILES:
        path = root / name
        if path.is_symlink() or not path.is_file() or path.resolve(strict=True).parent != root:
            raise ValueError(f'Unsafe control input: {name}')
        raw = path.read_bytes()
        actual_blob = git_blob(raw)
        if name == 'run_kinetic_games.py':
            if actual_blob != expected_runner_git_blob:
                raise ValueError('Unverified control runner')
        else:
            expected_blob = CONTROL_GIT_BLOBS[name]
            if actual_blob != expected_blob:
                raise ValueError(f'Unverified control input: {name}')
        captured[name] = raw
    return captured, control_bundle_digest(captured)


def load_captured_composer(raw):
    """Execute only the already-authenticated composer capture privately."""
    if git_blob(raw) != CONTROL_GIT_BLOBS['compose_kinetic.py']:
        raise ValueError('Unverified captured composer')
    try:
        source = raw.decode('utf-8')
    except UnicodeError as exc:
        raise ValueError('Captured composer is not UTF-8') from exc
    module = types.ModuleType('kinetic_captured_composer')
    module.__file__ = '<captured-compose_kinetic.py>'
    exec(compile(source, module.__file__, 'exec'), module.__dict__)
    if getattr(module, 'BASE_BLOB', None) != BASE_MECHANICS_BLOB:
        raise ValueError('Captured composer baseline identity mismatch')
    if not callable(getattr(module, 'compose', None)):
        raise ValueError('Captured composer missing compose()')
    return module


def run_captured_runner(runner_bytes, expected_runner_git_blob, runner_args, *, optimized=False, timeout=90):
    """Start isolated child Python from authenticated runner bytes, never a path."""
    expected_runner_git_blob = _git_blob_pin(expected_runner_git_blob)
    if not isinstance(runner_bytes, bytes):
        raise TypeError('runner_bytes must be bytes')
    if git_blob(runner_bytes) != expected_runner_git_blob:
        raise ValueError('Captured runner bytes do not match external identity')
    if not isinstance(runner_args, (list, tuple)) or any(not isinstance(v, str) for v in runner_args):
        raise ValueError('runner_args must be strings')
    if type(optimized) is not bool:
        raise ValueError('optimized must be a bool')
    child_env = {
        key: value for key, value in os.environ.items()
        if not key.upper().startswith('PYTHON')
    }
    command = [sys.executable, '-I', '-S']
    if optimized:
        command.append('-O')
    command.extend([
        '-B',
        '-c',
        CAPTURED_RUNNER_BOOTSTRAP,
        expected_runner_git_blob,
        *runner_args,
    ])
    return subprocess.run(
        command,
        input=runner_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
        env=child_env,
    )


def capture_runtime(root, expected_mechanics_sha256=None):
    """Capture and authenticate every declared runtime byte exactly once.

    The returned buffers are the sole authority for later runtime execution.
    ``expected_mechanics_sha256`` is permitted only for the composed candidate;
    every other member remains bound to the pinned SOURCE manifest.
    """
    root = Path(root).resolve(strict=True)
    manifest_raw = (root / 'SOURCE.json').read_bytes()
    if sha_bytes(manifest_raw) != SOURCE_SHA256:
        raise ValueError('Unverified SOURCE manifest')
    manifest = json.loads(manifest_raw)
    runtime_manifest = manifest.get('runtime')
    if not isinstance(runtime_manifest, dict) or not runtime_manifest:
        raise ValueError('Invalid SOURCE runtime manifest')
    captured = {}
    for name, pin in runtime_manifest.items():
        rel = _safe_relative(name)
        if not isinstance(pin, dict) or not isinstance(pin.get('sha256'), str):
            raise ValueError(f'Invalid runtime pin: {name}')
        path = root.joinpath(*rel.parts)
        if path.is_symlink() or not path.is_file() or not path.resolve(strict=True).is_relative_to(root):
            raise ValueError(f'Unsafe runtime input: {name}')
        raw = path.read_bytes()
        expected = expected_mechanics_sha256 if name == 'mechanics.py' and expected_mechanics_sha256 else pin['sha256']
        if sha_bytes(raw) != expected:
            raise ValueError(f'Unverified runtime input: {name}')
        captured[name] = raw
    if 'mechanics.py' not in captured:
        raise ValueError('SOURCE runtime is missing mechanics.py')
    if expected_mechanics_sha256 is None and git_blob(captured['mechanics.py']) != BASE_MECHANICS_BLOB:
        raise ValueError('Expected immutable original mechanics input')
    for name, expected_blob in ENGINE_GIT_BLOBS.items():
        if name not in captured or git_blob(captured[name]) != expected_blob:
            raise ValueError(f'Unverified engine input: {name}')
    return manifest_raw, captured


def materialize_runtime(root, manifest_raw, captured):
    """Write a captured runtime only as child input transport, never execution authority."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=False)
    (root / 'SOURCE.json').write_bytes(manifest_raw)
    for name, raw in captured.items():
        rel = _safe_relative(name)
        path = root.joinpath(*rel.parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)


class _CapturedRuntimeFinder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """Import runtime Python modules directly from the authenticated byte capture."""
    def __init__(self, captured):
        self.modules = {}
        self.namespaces = set()
        for name, raw in captured.items():
            rel = _safe_relative(name)
            if rel.suffix != '.py':
                continue
            parts = list(rel.parts)
            is_package = parts[-1] == '__init__.py'
            if is_package:
                module_parts = parts[:-1]
            else:
                module_parts = parts[:-1] + [PurePosixPath(parts[-1]).stem]
            if not module_parts or any(not part.isidentifier() for part in module_parts):
                continue
            fullname = '.'.join(module_parts)
            self.modules[fullname] = (name, raw, is_package)
            for index in range(1, len(module_parts)):
                self.namespaces.add('.'.join(module_parts[:index]))

    def find_spec(self, fullname, path=None, target=None):
        record = self.modules.get(fullname)
        if record is not None:
            name, _raw, is_package = record
            spec = importlib.util.spec_from_loader(fullname, self, is_package=is_package)
            spec.origin = _virtual_runtime_path(name)
            if is_package:
                spec.submodule_search_locations = [
                    str(PurePosixPath(VIRTUAL_RUNTIME_ROOT, *PurePosixPath(name).parts[:-1]))
                ]
            return spec
        if fullname in self.namespaces:
            spec = importlib.machinery.ModuleSpec(fullname, loader=None, is_package=True)
            spec.submodule_search_locations = [
                str(PurePosixPath(VIRTUAL_RUNTIME_ROOT, *fullname.split('.')))
            ]
            return spec
        return None

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        name, raw, is_package = self.modules[module.__name__]
        virtual = _virtual_runtime_path(name)
        module.__file__ = virtual
        module.__package__ = module.__name__ if is_package else module.__name__.rpartition('.')[0]
        if is_package:
            module.__path__ = [str(PurePosixPath(virtual).parent)]
        exec(compile(raw, virtual, 'exec'), module.__dict__)


@contextmanager
def _captured_runtime_authority(captured):
    """Serve captured Python imports and captured file reads without filesystem reopen."""
    by_virtual_path = {
        os.path.abspath(_virtual_runtime_path(name)): raw
        for name, raw in captured.items()
    }
    real_builtin_open = builtins.open
    real_io_open = io.open

    def captured_open(file, mode='r', buffering=-1, encoding=None, errors=None,
                      newline=None, closefd=True, opener=None):
        if isinstance(file, (str, bytes, os.PathLike)):
            try:
                key = os.path.abspath(os.fsdecode(os.fspath(file)))
            except (TypeError, ValueError, OSError):
                key = None
            if key in by_virtual_path:
                if any(flag in mode for flag in ('w', 'a', 'x', '+')):
                    raise ValueError(f'Captured runtime member is immutable: {file}')
                raw = by_virtual_path[key]
                if 'b' in mode:
                    return io.BytesIO(raw)
                codec = locale.getencoding() if encoding in (None, 'locale') else encoding
                text = raw.decode(codec, errors or 'strict')
                return io.StringIO(text, newline=newline)
        return real_builtin_open(
            file, mode, buffering, encoding, errors, newline, closefd, opener
        )

    finder = _CapturedRuntimeFinder(captured)
    builtins.open = captured_open
    io.open = captured_open
    sys.meta_path.insert(0, finder)
    try:
        yield finder
    finally:
        if finder in sys.meta_path:
            sys.meta_path.remove(finder)
        builtins.open = real_builtin_open
        io.open = real_io_open


def _load_captured_module(name, runtime_name, captured):
    if runtime_name not in captured:
        raise ValueError(f'Missing captured runtime member: {runtime_name}')
    raw = captured[runtime_name]
    virtual = _virtual_runtime_path(runtime_name)
    module = types.ModuleType(name)
    module.__file__ = virtual
    module.__package__ = name.rpartition('.')[0]
    sys.modules[name] = module
    try:
        exec(compile(raw, virtual, 'exec'), module.__dict__)
    except Exception:
        sys.modules.pop(name, None)
        raise
    return module


def _load_captured_engine(captured):
    """Load the exact engine Python/JSON/utils from captured buffers only."""
    utils_name = 'checks/reference/engine/utils.py'
    engine_name = 'checks/reference/engine/kaggriculture.py'
    json_name = 'checks/reference/engine/kaggriculture.json'
    for name in (utils_name, engine_name, json_name):
        if name not in captured:
            raise ValueError(f'Missing captured engine member: {name}')

    utils_virtual = _virtual_runtime_path(utils_name)
    parsed = ast.parse(captured[utils_name].decode('utf-8'), filename=utils_virtual)
    helper = next(
        (node for node in parsed.body
         if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
         and node.name == 'resolve_episode_seed'),
        None,
    )
    if helper is None or isinstance(helper, ast.AsyncFunctionDef):
        raise ValueError('Captured engine utils missing synchronous resolve_episode_seed')
    namespace = {'Any': Any, 'Callable': Callable, 'random': random}
    exec(
        compile(ast.Module(body=[helper], type_ignores=[]), utils_virtual, 'exec'),
        namespace,
    )
    package = types.ModuleType('kaggle_environments')
    package.__path__ = []
    utils = types.ModuleType('kaggle_environments.utils')
    utils.resolve_episode_seed = namespace['resolve_episode_seed']
    package.utils = utils
    sys.modules['kaggle_environments'] = package
    sys.modules['kaggle_environments.utils'] = utils
    return _load_captured_module('official_kaggriculture', engine_name, captured)


def play(captured, seed, seat, instrument=False):
    """Execute one game using only authenticated captured runtime bytes."""
    with _captured_runtime_authority(captured):
        loader = _load_captured_module(
            'kinetic_game_loader',
            'checks/reference/evaluator/loader.py',
            captured,
        )
        if not hasattr(loader, 'Struct'):
            raise ValueError('Captured reference loader missing Struct')
        engine = _load_captured_engine(captured)
        main = _load_captured_module('kinetic_native_entrypoint', 'main.py', captured)
        histogram = collections.Counter()
        if instrument:
            mechanics = sys.modules.get('mechanics')
            if mechanics is None:
                mechanics = importlib.import_module('mechanics')
            original = mechanics._apply_unit_action

            def counted(*args, **kwargs):
                action = args[3]
                op = str(action[0]) if isinstance(action, list) and action else '<invalid>'
                histogram[op] += 1
                return original(*args, **kwargs)

            mechanics._apply_unit_action = counted
        cfg = loader.Struct({
            key: value.get('default') if isinstance(value, dict) else value
            for key, value in engine.specification['configuration'].items()
        })
        cfg.seed = seed
        env = loader.Struct(configuration=cfg, done=False, info={})
        state = [
            loader.Struct(observation=loader.Struct(), action={}, status='ACTIVE', reward=0)
            for _ in range(2)
        ]
        engine.interpreter(state, env)
        actions, states = hashlib.sha256(), hashlib.sha256()
        wall, cpu, statuses, daily = [], [], collections.Counter(), []
        for step in range(int(cfg.episodeSteps)):
            for state_row in state:
                state_row.observation.step = step
            observation = copy.deepcopy(state[seat].observation)
            started_wall, started_cpu = time.perf_counter(), time.process_time()
            action = main.agent(observation, cfg)
            cpu.append(time.process_time() - started_cpu)
            wall.append(time.perf_counter() - started_wall)
            instance = main._INSTANCE
            statuses[
                'no-instance' if instance is None else instance.diagnostics.get('status', 'missing')
            ] += 1
            state[seat].action = action
            state[1-seat].action = engine.starter_agent(copy.deepcopy(state[1-seat].observation))
            actions.update(encoded([row.action for row in state]) + b'\n')
            engine.interpreter(state, env)
            states.update(encoded([dict(row) for row in state]) + b'\n')
            if (step + 1) % int(cfg.turnsPerDay) == 0 or all(row.status == 'DONE' for row in state):
                daily.append({
                    'step': step,
                    'bank': [row.observation.farms[i]['money'] for i, row in enumerate(state)],
                })
            if all(row.status == 'DONE' for row in state):
                break
    return {
        'seed': seed,
        'seat': seat,
        'steps': step + 1,
        'scores': [row.reward for row in state],
        'terminal_status': [row.status for row in state],
        'statuses': dict(statuses),
        'action_sha256': actions.hexdigest(),
        'state_sha256': states.hexdigest(),
        'wall_seconds': sum(wall),
        'cpu_seconds': sum(cpu),
        'max_call_seconds': max(wall),
        'median_call_seconds': statistics.median(wall),
        'per_call_wall_seconds': wall,
        'daily_bank': daily,
        'instrumented': instrument,
        'unit_histogram': dict(histogram),
    }


def _require_captured_child_identity(expected_runner_git_blob):
    actual = globals().get('_KINETIC_BOOTSTRAP_RUNNER_BLOB')
    if actual != expected_runner_git_blob:
        raise ValueError('Child runner was not launched from authenticated captured bytes')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--expected-runner-git-blob', required=True,
                        help='external exact-head Git blob for run_kinetic_games.py')
    parser.add_argument('--seeds', default='17,101')
    parser.add_argument('--repetitions', type=int, default=2)
    parser.add_argument('--instrument', action='store_true')
    parser.add_argument('--order-offset', type=int, default=0)
    parser.add_argument('--child-seat', type=int, choices=[0, 1])
    parser.add_argument('--child-seed', type=int)
    parser.add_argument('--expected-mechanics-sha256')
    parser.add_argument('--expected-control-bundle-sha256')
    parser.add_argument('--control-probe', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    expected_runner_git_blob = _git_blob_pin(args.expected_runner_git_blob)

    if args.control_probe:
        _require_captured_child_identity(expected_runner_git_blob)
        if not args.expected_control_bundle_sha256:
            parser.error('Control bundle identity is required')
        control_digest = _sha256_pin(
            args.expected_control_bundle_sha256, 'expected control bundle SHA-256'
        )
        args.output.write_text(json.dumps({
            'executed_control_bundle_sha256': control_digest,
            'executed_control_runner_blob': expected_runner_git_blob,
            'authenticated_parent_control_compose_blob': CONTROL_GIT_BLOBS['compose_kinetic.py'],
            'authenticated_parent_control_check_blob': CONTROL_GIT_BLOBS['check_kinetic.py'],
            'runner_executed_from_captured_bytes': True,
        }, sort_keys=True, indent=2) + '\n')
        return 0

    if args.child_seat is not None:
        _require_captured_child_identity(expected_runner_git_blob)
        if not args.expected_mechanics_sha256:
            parser.error('Child mechanics identity is required')
        if not args.expected_control_bundle_sha256:
            parser.error('Child control bundle identity is required')
        control_digest = _sha256_pin(
            args.expected_control_bundle_sha256, 'expected control bundle SHA-256'
        )
        manifest_raw, captured = capture_runtime(args.native_root, args.expected_mechanics_sha256)
        result = play(captured, args.child_seed, args.child_seat, args.instrument)
        result['executed_source_manifest_sha256'] = sha_bytes(manifest_raw)
        result['executed_mechanics_sha256'] = sha_bytes(captured['mechanics.py'])
        result['executed_control_bundle_sha256'] = control_digest
        result['executed_control_runner_blob'] = expected_runner_git_blob
        result['authenticated_parent_control_compose_blob'] = CONTROL_GIT_BLOBS['compose_kinetic.py']
        result['authenticated_parent_control_check_blob'] = CONTROL_GIT_BLOBS['check_kinetic.py']
        result['runner_executed_from_captured_bytes'] = True
        result['runtime_executed_from_captured_bytes'] = True
        result['captured_runtime_members'] = len(captured)
        args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + '\n')
        return 0
    if args.repetitions < 1:
        parser.error('At least one repetition is required')
    if sys.flags.optimize not in (0, 1):
        raise ValueError('Only normal and -O parent modes are supported')

    control_files, control_digest = capture_control_bundle(
        Path(__file__).resolve().parent, expected_runner_git_blob
    )
    composer = load_captured_composer(control_files['compose_kinetic.py'])
    control_runner_bytes = control_files['run_kinetic_games.py']
    control_runner_blob = git_blob(control_runner_bytes)
    if control_runner_blob != expected_runner_git_blob:
        raise ValueError('Parent control runner identity mismatch')
    manifest_raw, baseline_files = capture_runtime(args.native_root)
    count = len(baseline_files)
    seeds = [int(value) for value in args.seeds.split(',')]
    parent_bytes = baseline_files['mechanics.py']
    parent_source = parent_bytes.decode()
    candidate_source = composer.compose(parent_source)
    candidate_bytes = candidate_source.encode()
    baseline_mechanics_sha256 = sha_bytes(parent_bytes)
    candidate_mechanics_sha256 = sha_bytes(candidate_bytes)
    results, pairs = [], []
    with tempfile.TemporaryDirectory(prefix='kinetic-native-') as scratch:
        scratch = Path(scratch)
        baseline = scratch / 'baseline'
        candidate = scratch / 'candidate'
        materialize_runtime(baseline, manifest_raw, baseline_files)
        candidate_files = dict(baseline_files)
        candidate_files['mechanics.py'] = candidate_bytes
        materialize_runtime(candidate, manifest_raw, candidate_files)
        for rep in range(args.repetitions):
            for seed in seeds:
                for seat in [0, 1]:
                    row_pair = {}
                    order = (
                        ['baseline', 'candidate']
                        if (rep + seat + args.order_offset) % 2 == 0
                        else ['candidate', 'baseline']
                    )
                    for arm in order:
                        root = baseline if arm == 'baseline' else candidate
                        expected_mechanics = (
                            baseline_mechanics_sha256 if arm == 'baseline'
                            else candidate_mechanics_sha256
                        )
                        result_file = scratch / 'one-game.json'
                        runner_args = [
                            '--native-root', str(root),
                            '--output', str(result_file),
                            '--expected-runner-git-blob', expected_runner_git_blob,
                            '--child-seat', str(seat),
                            '--child-seed', str(seed),
                            '--expected-mechanics-sha256', expected_mechanics,
                            '--expected-control-bundle-sha256', control_digest,
                        ]
                        if args.instrument:
                            runner_args.append('--instrument')
                        proc = run_captured_runner(
                            control_runner_bytes,
                            expected_runner_git_blob,
                            runner_args,
                            optimized=(sys.flags.optimize == 1),
                            timeout=90,
                        )
                        if proc.returncode:
                            stdout = proc.stdout.decode('utf-8', errors='replace')
                            stderr = proc.stderr.decode('utf-8', errors='replace')
                            raise RuntimeError(f'{arm} game failed: {stdout}\n{stderr}')
                        row = json.loads(result_file.read_text())
                        if row.get('executed_mechanics_sha256') != expected_mechanics:
                            raise ValueError(f'{arm} child executed unexpected mechanics bytes')
                        if row.get('executed_source_manifest_sha256') != sha_bytes(manifest_raw):
                            raise ValueError(f'{arm} child executed under unexpected source manifest')
                        if row.get('executed_control_bundle_sha256') != control_digest:
                            raise ValueError(f'{arm} child executed unexpected control bundle')
                        if row.get('executed_control_runner_blob') != expected_runner_git_blob:
                            raise ValueError(f'{arm} child executed unexpected runner bytes')
                        if row.get('runner_executed_from_captured_bytes') is not True:
                            raise ValueError(f'{arm} child lacks captured-runner execution receipt')
                        if row.get('runtime_executed_from_captured_bytes') is not True:
                            raise ValueError(f'{arm} child lacks captured-runtime execution receipt')
                        if row.get('captured_runtime_members') != count:
                            raise ValueError(f'{arm} child captured unexpected runtime member count')
                        if row.get('authenticated_parent_control_compose_blob') != CONTROL_GIT_BLOBS['compose_kinetic.py']:
                            raise ValueError(f'{arm} child lacks parent-authenticated composer identity')
                        if row.get('authenticated_parent_control_check_blob') != CONTROL_GIT_BLOBS['check_kinetic.py']:
                            raise ValueError(f'{arm} child lacks parent-authenticated checker identity')
                        row.update(arm=arm, repetition=rep)
                        row_pair[arm] = row
                        results.append(row)
                        print(json.dumps({
                            key: row[key]
                            for key in [
                                'arm', 'seed', 'seat', 'repetition', 'steps', 'scores',
                                'statuses', 'wall_seconds', 'cpu_seconds',
                            ]
                        }, sort_keys=True), flush=True)
                    baseline_row, candidate_row = row_pair['baseline'], row_pair['candidate']
                    equal = all(
                        baseline_row[key] == candidate_row[key]
                        for key in ['action_sha256', 'state_sha256', 'scores', 'steps', 'terminal_status']
                    )
                    complete = all(
                        row['steps'] == 719
                        and row['terminal_status'] == ['DONE', 'DONE']
                        and row['statuses'] == {'completed': 719}
                        for row in [baseline_row, candidate_row]
                    )
                    pairs.append({
                        'seed': seed,
                        'seat': seat,
                        'repetition': rep,
                        'parity': equal,
                        'complete': complete,
                        'wall_ratio': candidate_row['wall_seconds'] / baseline_row['wall_seconds'],
                        'cpu_ratio': candidate_row['cpu_seconds'] / baseline_row['cpu_seconds'],
                    })
    report = {
        'scope': 'b567 checked archive plus exactly one mechanics span; NOT current whole-V4 or field strength',
        'mode': 'optimized' if sys.flags.optimize else 'normal',
        'instrumented': args.instrument,
        'order_offset': args.order_offset,
        'authenticated_runtime_members': count,
        'source_manifest_sha256': sha_bytes(manifest_raw),
        'source_mechanics_blob': git_blob(parent_bytes),
        'candidate_mechanics_blob': git_blob(candidate_bytes),
        'source_mechanics_sha256': baseline_mechanics_sha256,
        'candidate_mechanics_sha256': candidate_mechanics_sha256,
        'control_bundle_sha256': control_digest,
        'control_runner_git_blob': control_runner_blob,
        'control_runner_external_pin': expected_runner_git_blob,
        'authenticated_parent_control_compose_blob': CONTROL_GIT_BLOBS['compose_kinetic.py'],
        'authenticated_parent_control_check_blob': CONTROL_GIT_BLOBS['check_kinetic.py'],
        'immutable_execution_snapshot': True,
        'immutable_control_snapshot': True,
        'child_runner_execution': 'isolated_captured_bytes_stdin_bootstrap',
        'child_runtime_execution': 'captured_bytes_memory_import_and_file_view',
        'child_python_startup': 'fixed_-I_-S_-B_plus_controlled_-O_no_inherited_PYTHON_env',
        'games': results,
        'pairs': pairs,
        'summary': {
            'games': len(results),
            'pairs': len(pairs),
            'all_parity': all(pair['parity'] for pair in pairs),
            'all_complete': all(pair['complete'] for pair in pairs),
            'median_paired_wall_ratio': statistics.median(pair['wall_ratio'] for pair in pairs),
            'median_paired_cpu_ratio': statistics.median(pair['cpu_ratio'] for pair in pairs),
        },
    }
    args.output.write_text(json.dumps(report, sort_keys=True, indent=2) + '\n')
    print(json.dumps(report['summary'], sort_keys=True), flush=True)
    return 0 if report['summary']['all_parity'] and report['summary']['all_complete'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
