# SPDX-License-Identifier: Apache-2.0
"""Offline composition and exact native-call observation for completed stock repairs.

This is test tooling, NOT a controller, production installer, feature flag, or
successor package. Prefix must precede harvest because its author authenticates
an entire preimage. Terminal release observes the actual feed consumer's input,
which already contains prior FERT edits; it must never restore pre-FERT input.
"""
from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
import hashlib
from pathlib import Path
import types

PEERS = {
    'prefix': ('operating-stock-prefix/port_operating_stock_prefix.py',
               'dfd13f1652fa1092d34576b3a66716421d9deabb'),
    'harvest': ('feed-stock-harvest/repair_feed_harvest.py',
                '9e842916795c23b8f819f6c1064ad669a26613ed'),
    'terminal': ('feed-stock-terminal/terminal_feed_gate.py',
                 '5befa6d995b46150ac1c9092e4c934cae1ee407a'),
}
STOCK_BEFORE = '781aa90da0d85d0ba23c665e29d6087d182c085e'
ENGINE = '3c202c7ee921da239356789e266b694635103fc4'


def blob(data: bytes) -> str:
    return hashlib.sha1(f'blob {len(data)}\0'.encode() + data).hexdigest()


def load_bound(path: Path, expected: str):
    data = path.read_bytes()
    if blob(data) != expected:
        raise ValueError(f'source drift: {path.name}')
    module = types.ModuleType('stockbridge_' + path.stem)
    module.__file__ = str(path)
    exec(compile(data, str(path), 'exec'), module.__dict__)
    return module


def peers(gameplay: Path | None = None) -> dict:
    root = gameplay or Path(__file__).resolve().parent.parent
    return {key: load_bound(root / path, digest)
            for key, (path, digest) in PEERS.items()}


def compose(stock: bytes, runtime: bytes, gameplay: Path | None = None) -> tuple[bytes, bytes, dict]:
    """Authenticate and consume existing source owners, without writing files.

    The runtime owner authenticates only its exact method. All unrelated runtime
    bytes are preserved, but that does NOT certify a different whole runtime.
    """
    modules = peers(gameplay)
    if blob(stock) != STOCK_BEFORE:
        raise ValueError('unsupported stock baseline; do not overwrite peer work')
    prefix = modules['prefix'].port_helper(stock.decode())
    combined = modules['harvest'].repair_source(prefix)
    native = modules['prefix'].port_runtime(runtime.decode())
    # Enforce the source seam independently of the transformations' own checks.
    before, after = modules['harvest'].function_span(stock.decode()), modules['harvest'].function_span(combined)
    prefix_span = modules['harvest'].function_span(prefix)
    if combined[:after[0]] != prefix[:prefix_span[0]] or combined[after[1]:] != prefix[prefix_span[1]:]:
        raise ValueError('harvest transformer changed unrelated FERT code')
    if before[2] == after[2]:
        raise ValueError('harvest repair was not consumed')
    compile(combined, '<combined-operating-stock>', 'exec')
    compile(native, '<prefix-runtime>', 'exec')
    receipt = {
        'stock_before': blob(stock), 'stock_prefix': blob(prefix.encode()),
        'stock_combined': blob(combined.encode()),
        'runtime_before': blob(runtime), 'runtime_after': blob(native.encode()),
        'peer_blobs': {key: pair[1] for key, pair in PEERS.items()},
        'order': ['prefix', 'harvest'],
        'terminal_mode': 'separate native-call probe; no installed runtime key',
        'production_modified': False,
    }
    return combined.encode(), native.encode(), receipt


class StockProbe:
    """Observe existing calls; optionally evaluate terminal release in a test run.

    Installs only in the current isolated test process and restores exact original
    callable objects even after errors. Terminal OFF is object-identity preserving.
    Reports are helper-call evidence, not proof that an outer deadline returned
    the candidate. A driver must separately record the final action and status.
    """
    def __init__(self, terminal, *, release: bool = False):
        if type(release) is not bool:
            raise ValueError('release must be literal bool')
        self.terminal = terminal
        self.release = release
        self.counts = Counter()
        self.events = []

    def _record(self, kind, obs, selected, proposed, report, gate_report=None):
        self.counts[kind + '_calls'] += 1
        reason = str(report.get('reason', 'missing'))
        self.counts[kind + ':' + reason] += 1
        if report.get('changed') is True:
            self.counts[kind + '_changed'] += 1
        if kind == 'feed' and 672 <= int(obs['step']) <= 694:
            self.counts['terminal_window_feed_calls'] += 1
        terminal_hit = gate_report is not None and 'terminal_feed_gate' in gate_report
        if terminal_hit:
            self.counts['terminal_matches'] += 1
        if report.get('changed') is True or terminal_hit:
            from copy import deepcopy
            self.events.append(deepcopy({
                'kind': kind, 'step': int(obs['step']), 'player': int(obs['player']),
                'selected': selected, 'proposed': proposed, 'report': report,
                'terminal_report': gate_report,
            }))

    @contextmanager
    def installed(self, stock):
        original_fert = stock.protect_operating_stock
        original_feed = stock.protect_feed_stock
        if getattr(original_feed, '_stockbridge', False):
            raise ValueError('probe already installed')

        def fert(mechanics, observation, configuration, selected, post_farm,
                 post_private, route, checkpoints=()):
            proposed, report = original_fert(mechanics, observation, configuration,
                selected, post_farm, post_private, route, checkpoints)
            self._record('fert', observation, selected, proposed, report)
            return proposed, report

        def feed(mechanics, observation, configuration, selected, post_farm,
                 post_private, route, checkpoints=()):
            proposed, report = original_feed(mechanics, observation, configuration,
                selected, post_farm, post_private, route, checkpoints)
            gated, gate_report = self.terminal.admit_terminal_feed_override(
                observation, configuration, selected, proposed, report, post_farm, route)
            self._record('feed', observation, selected, proposed, report, gate_report)
            return (gated, gate_report) if self.release else (proposed, report)

        feed._stockbridge = True
        stock.protect_operating_stock, stock.protect_feed_stock = fert, feed
        try:
            yield self
        finally:
            stock.protect_operating_stock, stock.protect_feed_stock = original_fert, original_feed
