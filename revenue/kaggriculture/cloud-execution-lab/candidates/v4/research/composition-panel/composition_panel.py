# SPDX-License-Identifier: Apache-2.0
"""Offline, deterministic pairwise feature compositions; never runs an agent."""
import argparse
import copy
import hashlib
import itertools
import json
import os
from pathlib import Path
import tempfile


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


class SpecError(ValueError):
    pass


class Model:
    def __init__(self, spec):
        allowed = {'schema_version', 'base_config', 'features', 'requires',
                   'excludes', 'fixed', 'provenance'}
        if type(spec) is not dict or set(spec) - allowed:
            raise SpecError('unknown or non-object specification')
        if type(spec.get('schema_version')) is not int or spec['schema_version'] != 1:
            raise SpecError('schema_version must be integer 1')
        base, names = spec.get('base_config'), spec.get('features')
        if type(base) is not dict or not all(type(k) is str for k in base):
            raise SpecError('base_config must be a JSON object')
        if (type(names) is not list or not 1 <= len(names) <= 48 or
                any(type(k) is not str or not k for k in names) or
                len(set(names)) != len(names)):
            raise SpecError('features must contain 1..48 distinct names')
        self.names = tuple(sorted(names))
        self.index = {k: i for i, k in enumerate(self.names)}
        if any(type(base.get(k)) is not bool for k in self.names):
            raise SpecError('each swept feature must be explicitly boolean in base_config')
        # JSON round trip also prevents mutable aliases into caller state.
        try:
            self.base = json.loads(canonical(base))
            self.provenance = json.loads(canonical(spec.get('provenance', {})))
        except (TypeError, ValueError) as exc:
            raise SpecError('configuration/provenance must be finite JSON') from exc
        self.clauses = []
        normalized = {}
        for kind in ('requires', 'excludes'):
            rows = spec.get(kind, [])
            if type(rows) is not list:
                raise SpecError(kind + ' must be a list')
            unique = set()
            for row in rows:
                if (type(row) is not list or len(row) != 2 or
                        any(type(x) is not str or x not in self.index for x in row)):
                    raise SpecError(kind + ' rows must name two swept features')
                a, b = row if kind == 'requires' else sorted(row)
                unique.add((a, b))
            normalized[kind] = [list(row) for row in sorted(unique)]
            for a, b in sorted(unique):
                self.clauses.append((2*self.index[a],
                                     2*self.index[b] + (kind == 'requires')))
        fixed = spec.get('fixed', {})
        if (type(fixed) is not dict or any(k not in self.index or type(v) is not bool
                                         for k, v in fixed.items())):
            raise SpecError('fixed must map swept features to literal booleans')
        for k, v in sorted(fixed.items()):
            literal = 2*self.index[k] + int(v)
            self.clauses.append((literal, literal))
        self.spec = {'schema_version': 1, 'base_config': self.base,
                     'features': list(self.names), **normalized,
                     'fixed': dict(sorted(fixed.items())), 'provenance': self.provenance}
        self.fingerprint = digest(self.spec)
        self.baseline = tuple(base[k] for k in self.names)
        if not self.valid(self.baseline):
            raise SpecError('baseline violates declared constraints')

    def valid(self, row):
        return (len(row) == len(self.names) and all(type(x) is bool for x in row)
                and all(row[a//2] == bool(a % 2) or row[b//2] == bool(b % 2)
                        for a, b in self.clauses))

    def solve(self, pins=()):
        """Exact 2-SAT model by iterative Kosaraju, no exponential enumeration."""
        n = 2*len(self.names)
        graph, reverse = [[] for _ in range(n)], [[] for _ in range(n)]
        clauses = self.clauses + [(2*i+int(v), 2*i+int(v)) for i, v in pins]
        for a, b in clauses:
            for src, dst in ((a ^ 1, b), (b ^ 1, a)):
                graph[src].append(dst)
                reverse[dst].append(src)
        seen, finish = set(), []
        for root in range(n):
            if root in seen:
                continue
            stack = [(root, False)]
            while stack:
                node, done = stack.pop()
                if done:
                    finish.append(node)
                elif node not in seen:
                    seen.add(node)
                    stack.append((node, True))
                    stack.extend((x, False) for x in reversed(graph[node]) if x not in seen)
        component = [-1]*n
        number = 0
        for root in reversed(finish):
            if component[root] != -1:
                continue
            stack = [root]
            component[root] = number
            while stack:
                for child in reverse[stack.pop()]:
                    if component[child] == -1:
                        component[child] = number
                        stack.append(child)
            number += 1
        if any(component[i] == component[i+1] for i in range(0, n, 2)):
            return None
        return tuple(component[i+1] > component[i] for i in range(0, n, 2))

    def universe(self):
        feasible, infeasible, witnesses = [], [], set()
        n = len(self.names)
        for strength in (1, 2):
            for indices in itertools.combinations(range(n), strength):
                for values in itertools.product((False, True), repeat=strength):
                    obligation = tuple(zip(indices, values))
                    witness = self.solve(obligation)
                    if witness is None:
                        infeasible.append(obligation)
                    else:
                        feasible.append(obligation)
                        witnesses.add(witness)
        return feasible, infeasible, witnesses

    def assignment(self, obligation):
        return {self.names[i]: value for i, value in obligation}

    def probes(self):
        rows, blocked = [self.baseline], []
        for i, name in enumerate(self.names):
            row = list(self.baseline)
            row[i] = not row[i]
            row = tuple(row)
            if self.valid(row):
                rows.append(row)
            else:
                blocked.append(name)
        return rows, blocked

    def case(self, row):
        config = copy.deepcopy(self.base)
        config.update(zip(self.names, row))
        identity = digest({'spec': self.fingerprint, 'values': list(row)})
        return {'case_id': identity, 'config': config,
                'toggled': [k for k, v, b in zip(self.names, row, self.baseline) if v != b]}


def covers(row, obligation):
    return all(row[i] == value for i, value in obligation)


def audit_plan(spec, plan):
    """Recompute obligations and coverage; do not trust reported coverage/status."""
    model = Model(spec)
    if (type(plan) is not dict or plan.get('spec_fingerprint') != model.fingerprint
            or type(plan.get('cases')) is not list or not plan['cases']
            or canonical(plan.get('spec')) != canonical(model.spec)):
        raise SpecError('plan fingerprint/cases mismatch')
    rows = []
    for case in plan['cases']:
        if type(case) is not dict or type(case.get('config')) is not dict:
            raise SpecError('invalid case/config')
        config = case['config']
        if set(config) != set(model.base):
            raise SpecError('case changed configuration keys')
        row = tuple(config[k] for k in model.names)
        if not model.valid(row):
            raise SpecError('case violates types or constraints')
        if canonical(case) != canonical(model.case(row)):
            raise SpecError('case identity, unswept configuration or toggle metadata drift')
        if row in rows:
            raise SpecError('duplicate configuration')
        rows.append(row)
    feasible, infeasible, _ = model.universe()
    missing = [model.assignment(o) for o in feasible if not any(covers(r, o) for r in rows)]
    probes, blocked = model.probes()
    missing_probes = [model.case(r)['case_id'] for r in probes if r not in rows]
    return {'complete': not missing and not missing_probes,
            'case_count': len(rows), 'feasible_obligations': len(feasible),
            'infeasible_obligations': [model.assignment(o) for o in infeasible],
            'missing_obligations': missing, 'missing_probe_ids': missing_probes,
            'blocked_isolated_toggles': blocked}


def build_plan(spec, *, max_cases=256):
    if type(max_cases) is not int or not 1 <= max_cases <= 4096:
        raise SpecError('max_cases must be integer 1..4096')
    model = Model(spec)
    feasible, _, candidates = model.universe()
    probes, _ = model.probes()
    candidates.update(probes)
    # Diverse deterministic witnesses avoid a quadratic panel for free flags.
    # Each preferred bit is accepted only if exact satisfiability is retained.
    for trial in range(max(32, 4*len(model.names))):
        pins = []
        for i in range(len(model.names)):
            value = bool(hashlib.sha256(f'{model.fingerprint}:{trial}:{i}'.encode()).digest()[0] & 1)
            if model.solve(pins + [(i, value)]) is None:
                value = not value
            pins.append((i, value))
        candidates.add(tuple(v for _, v in pins))
    masks = {r: sum(1 << j for j, o in enumerate(feasible) if covers(r, o))
             for r in candidates}
    remaining = (1 << len(feasible))-1
    selected = []
    for row in probes[:max_cases]:
        selected.append(row)
        remaining &= ~masks.pop(row)
    while remaining and masks and len(selected) < max_cases:
        # Set iteration never affects ties; prefer fewer baseline deviations.
        row = min(masks, key=lambda r: (-(masks[r] & remaining).bit_count(),
                                       sum(a != b for a, b in zip(r, model.baseline)), r))
        if not masks[row] & remaining:
            break
        selected.append(row)
        remaining &= ~masks.pop(row)
    plan = {'schema_version': 1, 'kind': 'offline_pairwise_composition_plan',
            'spec_fingerprint': model.fingerprint, 'spec': model.spec,
            'max_cases': max_cases, 'cases': [model.case(r) for r in selected]}
    plan['audit'] = audit_plan(spec, plan)
    plan['status'] = 'COMPLETE' if plan['audit']['complete'] else 'INCOMPLETE_BUDGET'
    return plan


def read_json(path):
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise SpecError('duplicate JSON key: ' + key)
            out[key] = value
        return out
    def bad_constant(value):
        raise SpecError('nonfinite JSON constant: ' + value)
    return json.loads(Path(path).read_text(encoding='utf-8'),
                      object_pairs_hook=pairs, parse_constant=bad_constant)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('spec', type=Path)
    parser.add_argument('--audit', type=Path, help='audit an existing plan instead of building')
    parser.add_argument('--max-cases', type=int, default=256)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    try:
        if args.output:
            for source in (args.spec, args.audit, Path(__file__)):
                if source and (args.output.resolve() == source.resolve() or
                               (args.output.exists() and os.path.samefile(args.output, source))):
                    raise SpecError('output aliases an input or this module')
        spec = read_json(args.spec)
        result = (audit_plan(spec, read_json(args.audit)) if args.audit else
                  build_plan(spec, max_cases=args.max_cases))
        complete = result['complete'] if args.audit else result['audit']['complete']
        text = json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + '\n'
        if args.output:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=args.output.parent,
                                             delete=False) as stream:
                temp = Path(stream.name)
                stream.write(text)
            try:
                os.replace(temp, args.output)
            finally:
                temp.unlink(missing_ok=True)
        else:
            print(text, end='')
        return 0 if complete else 1
    except (OSError, ValueError, TypeError) as exc:
        parser.exit(2, f'composition-panel: {exc}\n')


if __name__ == '__main__':
    raise SystemExit(main())
