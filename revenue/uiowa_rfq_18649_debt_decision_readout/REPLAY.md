# Replay the UIOWA-049 decision readout

**SYNTHETIC data only.** This is an analysis recipe consuming the existing
calculator, not a new runtime entry point or alternative scoring engine.
Read [the decision report](README.md) before interpreting the output.

Use an ephemeral cloud checkout containing the published UIOWA-049 package.
Do not create a new checkout on Bryce's machine. The source revision used here
is `d50b57c6ac658fe4e110ad500a7101949edafb3b`; the calculator was subsequently
merged by its owner. Working on a newer main is acceptable only when the two
input blobs below still match. A mismatch means refresh the analysis, not remove
the check or silently attribute new results to this report.

From the checkout root, run the following Python recipe. It verifies the exact
input blobs before import, executes all 10,508 scenarios, checks the returned
portfolio invariants, and prints the grid digest and decision transitions.
It does not modify the register, perform network calls, publish anything,
make appointments or execute a recommended change. It retains the grid in memory
for serialization; the canonical serialized result is about 108 MiB, so this is
not a memory-capacity benchmark or an arbitrary-size input reader.

```python
from pathlib import Path
import hashlib
import json
import platform

folder = Path('revenue/uiowa_rfq_18649_debt')
expected = {
    'model.py': 'a36e01416f7f6eebad420e5b7d9705fb22fdd368',
    'examples/synthetic-register.json': '856618996c6f5b51a6ee8dc37e518d22074b4439',
}
for name, wanted in expected.items():
    data = (folder / name).read_bytes()
    actual = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
    if actual != wanted:
        raise RuntimeError(f'Input version changed: {name}: {actual}')

from revenue.uiowa_rfq_18649_debt.model import analyze, canonical, load_register
packet = load_register((folder / 'examples/synthetic-register.json').read_bytes())
items = {item['id']: item for item in packet['items']}
reports = []

def require(condition, reason):
    if not condition:
        raise RuntimeError(reason)

def exercise(capacity, horizon, required):
    report = analyze(packet, capacity, horizon, required)
    require(report['evidence_class'] == 'SYNTHETIC', 'evidence label changed')
    payload = dict(report)
    digest = payload.pop('report_sha256')
    require(hashlib.sha256(canonical(payload)).hexdigest() == digest, 'report digest')
    for selected in report['portfolios'].values():
        if selected is None:
            continue
        ids = selected['ids']
        keys = set(ids)
        require(len(ids) == len(keys), 'duplicate selection')
        require(set(required) <= keys, 'required item missing')
        for key in keys:
            require(set(items[key]['dependencies']) <= keys, 'dependency missing')
            require(all(items[key][field] is not None for field in
                        ('effort_hours', 'weekly_support_hours', 'reduction_pct')),
                    'unknown estimate selected')
        cost = sum(items[key]['effort_hours']['high'] for key in keys)
        require(cost == selected['effort_hours_high'], 'shared-cost accounting')
        require(cost <= capacity, 'capacity exceeded')
        for field in ('benefit_pool', 'alternative_group'):
            values = [items[key][field] for key in keys if items[key][field] is not None]
            require(len(values) == len(set(values)), 'overlapping alternatives')
    unknown = next(row for row in report['items'] if row['id'] == 'UNKNOWN')
    require(unknown['disposition'] == 'NEEDS_ESTIMATE', 'missing estimate reclassified')
    reports.append(report)

# Ordering matters for the complete-grid digest: required setting, horizon, capacity.
for required in ((), ('OBSOLETE',)):
    for horizon in range(1, 53):
        for capacity in range(101):
            exercise(capacity, horizon, required)
for capacity in (0, 25, 50, 100):
    exercise(capacity, 12, ('UNKNOWN',))
    require(reports[-1]['decision_status'] == 'NO_FEASIBLE_PORTFOLIO',
            'required unknown returned a successful plan')

complete_digest = hashlib.sha256(canonical(reports) + b'\n').hexdigest()
require(len(reports) == 10508, 'scenario count changed')
require(complete_digest == '6f7da138f5b0ac2f02a88cd3579bf9e5a1d6e5bda025c34c447c873d3e147ddf',
        'complete grid differs from published execution')
print('Python:', platform.python_version())
print('Scenarios and invariant checks:', len(reports), 'PASS')
print('Complete grid SHA-256:', complete_digest)

lookup = {(r['parameters']['budget_hours'], r['parameters']['horizon_weeks'],
           tuple(r['parameters']['required_ids'])): r for r in reports}

def transitions(axis, fixed, objective, required):
    result = []
    values = range(101) if axis == 'capacity' else range(1, 53)
    for value in values:
        key = (value, fixed, required) if axis == 'capacity' else (fixed, value, required)
        selected = lookup[key]['portfolios'][objective]
        ids = tuple(selected['ids']) if selected is not None else None
        if not result or result[-1]['ids'] != ids:
            result.append({'from': value, 'to': value, 'ids': ids,
                           'selected_at_interval_start': selected})
        else:
            result[-1]['to'] = value
    return result

for axis, fixed, required in (('capacity', 12, ()),
                              ('capacity', 12, ('OBSOLETE',)),
                              ('horizon', 80, ())):
    for objective in ('conservative', 'optimistic'):
        print(axis, fixed, required, objective)
        print(json.dumps(transitions(axis, fixed, objective, required), indent=2))
for required in ((), ('OBSOLETE',)):
    report = lookup[50, 12, required]
    print('50 hours / 12 weeks / required', required)
    print(report['report_sha256'], json.dumps(report['portfolios'], sort_keys=True))
```

## Observed execution

The recipe above was extracted from this Markdown and executed under normal
CPython 3.13.5 and real optimized `python -O`. Both completed successfully and
produced byte-identical stdout, including the following:

```text
Python: 3.13.5
Scenarios and invariant checks: 10508 PASS
Complete grid SHA-256: 6f7da138f5b0ac2f02a88cd3579bf9e5a1d6e5bda025c34c447c873d3e147ddf
```

The checks use explicit exceptions, not assertions removed by optimized Python.
They establish the named returned-output invariants for this fixed fictional
cohort, not optimality for every possible input or performance on University
data. The solver's independent package review and original retained tests are
separate evidence on [PR #16189](https://github.com/woahwhattheheck/commons/pull/16189).

For one scenario instead of the full grid, use the existing documented CLI:

```sh
python -m revenue.uiowa_rfq_18649_debt \
  revenue/uiowa_rfq_18649_debt/examples/synthetic-register.json \
  --budget-hours 50 --horizon-weeks 12 --output-dir NEW_OUTPUT_DIRECTORY
```

Add `--require OBSOLETE` for the explicit lifecycle scenario. The normal module's
existing no-overwrite behavior still applies. This readout does not introduce
another report format, another approval state or another model of staff time.
