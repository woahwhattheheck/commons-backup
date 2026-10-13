# SPDX-License-Identifier: MIT
"""Causal assessment of existing T14 development traces; never runs a policy."""
from __future__ import annotations

import argparse
import base64
from collections import Counter, defaultdict
from copy import deepcopy
import gzip
import hashlib
import importlib.util
import json
import lzma
from pathlib import Path
import sys
import tempfile

PRODUCTS = ('CARROT', 'TOMATO', 'STRAWBERRY', 'MELON', 'EGG', 'MILK', 'WOOL')
SETTINGS = dict(period=24, history_window=5, minimum=3, window_length=3,
                cutoff_offset=0, threshold=5, eta=2.0, gamma=1.0, unknown_mass=0.25)
TRACE_NAMES = tuple(f'{"development-v2" if seed == 9881001 else "development-v3"}/'
                    f'sell-lonespear-{seed}-seat{seat}.jsonl.gz'
                    for seed in (9881001, 9881019, 9881037) for seat in (0, 1))


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def blob(path):
    data = Path(path).read_bytes()
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def clock(observation, configuration):
    """Preserve explicit step precedence; work on caller-independent data."""
    step = observation.get('step')
    if step is None:
        step = observation['day'] * configuration.get('turnsPerDay', 24) + observation['hour']
    if type(step) is not int or step < 0:
        raise ValueError('invalid observation clock')
    return step


def own_sales(engine, observation, action, configuration):
    """Exact own non-operating fills; no rival queue, cash or private stock.

    These products cannot be purchased in the pinned market. Their SELL fills
    depend only on own post-unit shed and earlier own SELLs, including at $1.
    Operating goods are deliberately excluded because buys depend on paired
    quotes/funding. Unit/PLANT order follows the pinned interpreter verbatim.
    """
    obs, act = deepcopy(observation), deepcopy(action)
    seat = obs['player']; farm, private = obs['farms'][seat], obs['private']
    t = clock(obs, configuration); period = configuration.get('turnsPerDay', 24)
    farmer = act.get('farmer', ['PASS']) if isinstance(act, dict) else ['PASS']
    hands = act.get('hands', []) if isinstance(act, dict) else []
    hands = hands if isinstance(hands, list) else []
    units = [farmer, *hands]
    demand = Counter(a[1] for a in units if isinstance(a, list) and len(a) >= 2 and a[0] == 'PLANT')
    blocked = {p for p, q in demand.items() if q > private.get('seeds', {}).get(p, 0)}
    for index, unit in enumerate(units):
        if isinstance(unit, list) and len(unit) >= 2 and unit[0] == 'PLANT' and unit[1] in blocked:
            unit = ['PASS']
        engine._apply_unit_action(farm, private, index, unit,
                                 configuration.get('boardSize', 10), t // period,
                                 period, configuration.get('shedCapacity', 100))
    stock = dict(private['shed']); fills = dict.fromkeys(PRODUCTS, 0)
    queue = act.get('market', []) if isinstance(act, dict) else []
    queue = queue if isinstance(queue, list) else []
    for order in queue[:max(1, configuration.get('maxMarketOrdersPerTurn', 10))]:
        parsed = engine._parse_order(order)
        if not parsed or parsed['type'] != 'SELL' or parsed['item'] not in fills:
            continue
        product = parsed['item']
        count = min(stock.get(product, 0), parsed['remaining'], 99999)
        fills[product] += count; stock[product] = stock.get(product, 0) - count
    return fills


def absorption(engine, product, step, shops, configuration):
    """Known consumption; duplicate public shop instances each count."""
    count = 0
    if step % max(1, configuration.get('townShopSellInterval', 4)) == 0:
        for shop in shops:
            goods = engine.SHOPS[shop]
            if product in goods:
                count += 2 if len(goods) == 1 else 1
    if step % max(1, configuration.get('townCenterSellInterval', 24)) == 0:
        count += product in engine.TOWN_CENTER_PRODUCTS
    return count


class PublicReplay:
    """One sequential game; only public+own observation and own action enter.

    The offline driver may retain future rows for decoding, but cannot pass
    them, current rival actions, terminal scores or reconstructed rival stock
    to this interface. Forecast state is separate from offline truth labels.
    """
    def __init__(self, engine, flow, calibration, game_id, configuration=None):
        self.engine, self.flow, self.calibration = engine, flow, calibration
        self.cfg = dict(configuration or {})
        self.history = flow.FlowHistory(24, 5, 3)
        self.learners = {p: calibration.CausalWindowEnsemble(game_id, p) for p in PRODUCTS}
        self.pending = {}; self.previous = None; self.previous_fills = None
        self.intervals = []; self.outcomes = []; self.fills = []

    def feed(self, observation, own_action):
        now = clock(observation, self.cfg)
        if self.previous is None and now != 0:
            raise ValueError('a whole development game must start at step 0')
        if self.previous is not None and now != self.previous['step'] + 1:
            raise ValueError('observation gap, duplicate or reverse clock')
        # A narrow explicit input projection: no replay metadata or rival action.
        obs = {k: deepcopy(observation[k]) for k in ('player', 'farms', 'private', 'market', 'town')}
        obs['step'] = now
        if self.previous is not None:
            for p in PRODUCTS:
                interval = self.flow.infer_flow(self.previous, obs, self.previous_fills, p,
                                               self.cfg, self.engine,
                                               lambda product, t, shops, cfg: absorption(self.engine, product, t, shops, cfg))
                if interval is not None:
                    self.history.add(interval)
                self.intervals.append({'step': now - 1, 'product': p,
                                       'interval': None if interval is None else interval.as_dict()})
                pending = self.pending.get(p)
                if pending:
                    f, labels = pending
                    if interval is not None and f['now'] <= interval.step <= f['cutoff']:
                        labels.append(interval)
                    if now > f['end']:
                        result = self.learners[p].resolve(f['ticket'], labels, observed_at=now)
                        result.update(split='development', opponent_family='lonespear-v18-greedy')
                        self.outcomes.append(result); del self.pending[p]
        # Only dates whose matured observation can exist in this engine episode.
        final_decision = self.cfg.get('episodeSteps', 720) - 2
        if now % 3 == 0 and now + 3 <= final_decision:
            for p in PRODUCTS:
                f = self.calibration.predict_history(self.learners[p], self.history,
                                                      now=now, end=now + 2, cutoff=now, threshold=5)
                self.pending[p] = (f, [])
        fills = own_sales(self.engine, obs, own_action, self.cfg)
        self.fills.append({'step': now, 'sales': fills})
        self.previous, self.previous_fills = obs, fills


def retained(portfolio):
    """Decode only the six named DEVELOPMENT streams from the retained archive."""
    directory = portfolio / 'revision2/artifacts'
    manifest = json.loads((directory / 'MANIFEST.json').read_text())
    item = next(a for a in manifest['archives'] if a['name'] == 'full-traces.xz')
    parts = []
    for part in item['parts']:
        path = directory / part['name']
        if path.parent.resolve() != directory.resolve() or sha(path) != part['sha256']:
            raise ValueError('retained part identity mismatch')
        parts.append(path.read_bytes())
    raw = base64.b64decode(b''.join(parts), validate=True)
    if len(raw) != item['bytes'] or hashlib.sha256(raw).hexdigest() != item['sha256']:
        raise ValueError('retained archive identity mismatch')
    payload = json.loads(lzma.decompress(raw))
    codec = load(portfolio / 'evidence.py', 'quill_existing_codec')
    for name in TRACE_NAMES:
        member = payload['members'][name]; current = None; rows = []; h = hashlib.sha256()
        for patch in payload['streams'][member['semantic_sha256']]:
            current = codec.apply(current, patch)
            h.update(codec.encoded(current) + b'\n'); rows.append(deepcopy(current))
        if h.hexdigest() != member['semantic_sha256'] or len(rows) != member['rows']:
            raise ValueError('decoded semantic identity mismatch')
        yield name, member, rows, item['sha256']


def aggregate(outcomes):
    """Same-window comparisons, never mix an expert's warm subset with all labels."""
    groups = {}
    for r in outcomes:
        f = r['forecast']; warm = f['support'] >= 3
        for name in ('all', 'warm' if warm else 'cold', 'product:' + f['product'],
                     'game:' + f['game_id'], 'game-warm:' + f['game_id'] if warm else 'game-cold:' + f['game_id']):
            g = groups.setdefault(name, {'windows': 0, 'identified': 0, 'censored': 0, 'positive': 0, 'scores': {}})
            g['windows'] += 1
            if r['label'] is None:
                g['censored'] += 1; continue
            g['identified'] += 1; g['positive'] += r['label']
            for score_name, score in r['scores'].items():
                s = g['scores'].setdefault(score_name, {'n': 0, 'brier_sum': 0.0, 'log_loss_sum': 0.0,
                                                       'matched_prior_brier_sum': 0.0})
                s['n'] += 1; s['brier_sum'] += score['brier']; s['log_loss_sum'] += score['log_loss']
                s['matched_prior_brier_sum'] += r['scores']['prior_rate_control']['brier']
    for g in groups.values():
        for s in g['scores'].values():
            s['mean_brier'] = s['brier_sum'] / s['n']; s['mean_log_loss'] = s['log_loss_sum'] / s['n']
            s['mean_paired_brier_delta_vs_prior'] = (s['brier_sum'] - s['matched_prior_brier_sum']) / s['n']
    return groups


def truth_check(replay, audit, seat):
    own, rival = Counter(), Counter()
    for event in audit['events']:
        if event['op'] == 'SELL' and event['item'] in PRODUCTS:
            (own if event['player'] == seat else rival)[event['step'], event['item']] += event['quantity']
    own_checks = interval_checks = target_checks = 0
    for f in replay.fills:
        for p, q in f['sales'].items():
            if q != own[f['step'], p]:
                raise ValueError(('own fill mismatch', f['step'], p, q, own[f['step'], p]))
            own_checks += 1
    for r in replay.intervals:
        iv = r['interval']; actual = rival[r['step'], r['product']]
        if iv is not None:
            if not iv['lower'] <= actual <= iv['upper']:
                raise ValueError(('public interval excludes offline truth', r['step'], r['product'], iv, actual))
            interval_checks += 1
    for r in replay.outcomes:
        f = r['forecast']; actual = sum(rival[t, f['product']] for t in range(f['now'], f['cutoff'] + 1))
        if r['label'] is not None:
            if r['label'] != int(actual >= f['threshold']):
                raise ValueError(('threshold label mismatch', f['ticket']))
            target_checks += 1
    return dict(own_fill_checks=own_checks, interval_truth_checks=interval_checks,
                identifiable_target_checks=target_checks, offline_market_transitions=audit['checked_transitions'],
                cash_residual=audit['cash_residual'])


def assess(portfolio, calibration_dir, output):
    output.mkdir(parents=True, exist_ok=False)
    # Existing modules are loaded in place; nothing from their frozen source is edited.
    sys.path.insert(0, str(portfolio)); sys.path.insert(0, str(calibration_dir))
    calibration = load(calibration_dir / 'calibration.py', 'quill_original_calibration')
    flow = load(portfolio / 'revision2/vendor/t12/flow.py', 'quill_original_flow')
    evaluator = load(portfolio / 'vendor/cloud-eval/evaluate.py', 'quill_existing_evaluator')
    engine, _ = evaluator.get_engine(portfolio / 'vendor/engine')
    ledger = load(portfolio / 'revision2/trace_ledger.py', 'quill_existing_ledger')
    protocol = dict(settings=SETTINGS, products=PRODUCTS, members=TRACE_NAMES,
                    source_blobs={str(p.relative_to(portfolio)): blob(p) for p in
                                  (portfolio / 'revision2/vendor/t12/flow.py', portfolio / 'evidence.py',
                                   portfolio / 'revision2/trace_ledger.py', portfolio / 'vendor/engine/kaggriculture.py')},
                    calibration_blob=blob(calibration_dir / 'calibration.py'), assessor_blob=blob(__file__),
                    assessment='existing development only; no parameter fitting, games or policy changes')
    (output / 'PROTOCOL.json').write_bytes(encoded(protocol) + b'\n')
    all_outcomes = []; games = []
    for name, member, rows, archive_hash in retained(portfolio):
        game_id = Path(name).name.removesuffix('.jsonl.gz')
        learner = PublicReplay(engine, flow, calibration, game_id)
        for expected, row in enumerate(rows):
            if row['step'] != expected or row['candidate_seat'] != row['observation']['player']:
                raise ValueError('recorded row clock/seat mismatch')
            learner.feed(row['observation'], row['actions'][row['candidate_seat']])
        if len(rows) != 719 or learner.pending:
            raise ValueError('incomplete development trace')
        # Offline labels are computed only AFTER the complete causal assessment.
        with tempfile.TemporaryDirectory(prefix='quill-recorded-') as directory:
            path = Path(directory) / (game_id + '.jsonl.gz')
            path.write_bytes(gzip.compress(b''.join(encoded(r) + b'\n' for r in rows), mtime=0))
            audit = ledger.attribute(path)
        checks = truth_check(learner, audit, rows[0]['candidate_seat'])
        report = dict(game_id=game_id, archive_member=name, semantic_sha256=member['semantic_sha256'],
                      trace_archive_sha256=archive_hash, rows=len(rows), checks=checks,
                      inference_reasons=dict(Counter(r['interval']['reason'] if r['interval'] else 'unavailable'
                                                     for r in learner.intervals)),
                      summary=aggregate(learner.outcomes))
        (output / (game_id + '.json')).write_bytes(encoded(report) + b'\n')
        for label, value in [('outcomes', learner.outcomes), ('intervals', learner.intervals),
                             ('own-fills', learner.fills), ('offline-audit', audit)]:
            (output / f'{game_id}.{label}.json.gz').write_bytes(gzip.compress(encoded(value), mtime=0))
        games.append(report); all_outcomes.extend(learner.outcomes)
        print(json.dumps({'game': game_id, 'checks': checks, 'windows': len(learner.outcomes)}), flush=True)
    summary = dict(games=games, totals=aggregate(all_outcomes),
                   descriptive_reliability=calibration.summarize(all_outcomes),
                   scope='6 retained games, 3 seed clusters, 1 opponent lineage; development diagnostics only',
                   new_games=0, new_seeds=[], recommended_alpha=0.0,
                   operating_products='WHEAT/FERTILIZER remain unidentifiable; not encoded as zero')
    (output / 'results.json').write_bytes(encoded(summary) + b'\n')
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--portfolio', type=Path, required=True)
    parser.add_argument('--calibration-dir', type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = assess(args.portfolio.resolve(), args.calibration_dir.resolve(), args.output.resolve())
        print(json.dumps({'totals': result['totals']['all'], 'new_games': 0}))
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(2, f'assessment failed: {exc}\n')


if __name__ == '__main__':
    main()
