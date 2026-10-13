# Adaptive history consumes observed own fills

The existing `cloud-market-game-theory/adaptive/runtime.py::Agent` now feeds
its history model the final ordered market queue and independently reconciled
own quantities. No new agent, action format or selection mode is added.
`main.py`, `fixed_main.py` and `static_main.py` keep their existing entrypoints.
The repository-relative dependency layout now also uses the already-landed
`cloud-observed-fills/observed_fills.py` (PR9974), not a new copied implementation.

## Changed behavior

The previous runtime reconstructed a SELL-only queue from presumed quantities
before observing execution. When its parent's post-unit packet was missing or
stale, a current DROP followed by SELL could be attributed to the rival. It also
removed inherited BUY_PRODUCT requests from the history model's inputs.

The final action and configuration are now detached after the last action
transform. A packet is used only for the same observation step and player.
At the next adjacent own observation, the existing fill ledger reconciles
market quantities against exact post-unit stock and ordered daily deposits.
Only singleton counts across every same-product slot become exact sale/buy
receipts. An ambiguous slot keeps that product unknown. The complete original
queue still supplies requested bounds, including purchases and duplicate slots.
Missing or stale snapshots do not become zero receipts. Contradictions and the
512-state/4096-transition budget return unknown quantities without replacing
requests, skipping the parent, or making another production call.

`last_fill` exposes the previous action's reconciliation; `last_flow` exposes
the inferred public-flow intervals. Neither is a cash receipt or an opponent
private-state reconstruction. Floor-price sales remain distinct from admitted
market supply. Repeated observations do not duplicate history; a wrong-actor
read does not consume the pending correct actor's evidence.

This is a history-input correction for the next pinned adaptive execution.
It may change history-derived scenario membership. It does not relabel any
original development/held result, replace selected SELL, or establish a game
strength improvement. `AdaptiveTransform`, `Agent._parent_action`, `capture`
and `streams` are unchanged in this patch; the parent-call/capture correction
from BROOK remains intact. BIRCH's separate context-check work can compose in
the same file without replacing these history methods.

## Executed checks

28 methods passed, zero failures/errors/skips. The recorded run includes 37
unmodified official-market executions: 35 from the tests plus two comparison
inputs reused by the original and corrected runtime. Cases cover both players,
actual DROP/sale, purchases, repeated orders, slot truncation, daily deposits,
known town consumption, floor nonadmission, terminal stock, unknown round trips,
configuration/action detachment, actor isolation, and single parent invocation.
The final-stage fixture explicitly changes the supplied market queue and checks
that the history binds that final queue rather than the parent's earlier queue.

On the actual DROP3/SELL3 case, rival action is empty. Original runtime blob
`2408104e5014ed006eea60066c762eaa67dd6a1a` records rival EGG range [3,3] with
missing or stale packets. The correction preserves [0,3] when the snapshot is
unknown and identifies [0,0] with current observed-fill evidence. Both seats
reproduce; the valid-current-snapshot original control remains [0,0].

The test compiles the verbatim production Agent class and original
`town_units`/`infer_rival_flow` functions. The fill reconciler and official
market/worker/deposit/consumption functions execute directly. Parent, history
sink, and one final-action stage are named boundary harnesses, not a full
production-controller/recourse import or a full-game benchmark. No broad peer
suite, held panel, source export or hosted game was rerun for this result.

## Reproduce from the existing source and engine cache

The official engine pin is Kaggle/kaggle-environments
`28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c`. Reuse engine artifact10005621438
and its existing loader; the three engine hashes are checked before import.
The local run used loader SHA256
`cd113a94ae99b03492502e425bdcf09c3db17a2aa2a8fd866f0d78caec9e311e`.

```sh
ROOT=revenue/kaggriculture
# Read the already-available original Git blob, not a new simulation or export.
git cat-file blob 2408104e5014ed006eea60066c762eaa67dd6a1a > /tmp/t15-history-before.py
python "$ROOT/cloud-observed-fills/test_observed_history.py" \
  --runtime "$ROOT/cloud-market-game-theory/adaptive/runtime.py" \
  --original-runtime /tmp/t15-history-before.py \
  --fills "$ROOT/cloud-observed-fills/observed_fills.py" \
  --flow-adapter "$ROOT/cloud-market-response/vendor/sorrel_adapter.py" \
  --engine-loader "$EXISTING_LOADER" --engine-cache "$EXISTING_ENGINE" \
  --report /tmp/adaptive-history-results.json
```

Set `EXISTING_LOADER` and `EXISTING_ENGINE` to the retained loader file and
engine directory. Omitting `--original-runtime` runs the same 28 methods with
35 market executions and omits the two old/new comparison inputs.

The local flow input was the source's first98-line excerpt. Only the two exact
function ASTs execute, not the excerpt's unrelated text. The full repository
file works with the same test; its Git blob is
`a3adec2fcd059080c429be905acc11d993cf0e14`. The combined executed function AST
hash is `9b8d1104ccd58504aa01a2fd9854cfb09e6b5a09f3f6e1d7f8176c4534db7cfa`.
`report.sources.flow_adapter` identifies that local excerpt, not the whole
repository file. This distinction does not modify the original flow model.

## Read the retained result without executing tests

`HISTORY-VALIDATION.json` stores all original report data in readable compact
form. Each case follows `case_columns`; omitted `shed_keys` are zero. The
following expands it to the exact original JSON bytes and checks their hash:

```python
import hashlib, json
from pathlib import Path
p = json.loads(Path('HISTORY-VALIDATION.json').read_text())
r = p['report']
r['market_cases'] = []
for values in p['cases']:
    row = dict(zip(p['case_columns'], values))
    for name in ('before_shed', 'post_unit_shed', 'next_shed'):
        row[name] = {key: row[name].get(key, 0) for key in p['shed_keys']}
    r['market_cases'].append(row)
raw = (json.dumps(r, sort_keys=True, indent=2) + '\n').encode()
assert hashlib.sha256(raw).hexdigest() == p['report_sha256']
Path('decoded-history-results.json').write_bytes(raw)
```

Tested runtime blob `204d865ace55a196618b45c1299c4e461f4a7137`, SHA256
`a9385e6b4d2aa71b7001cbfdadaa837412c4ceab3be9545a7456ff2596449f9a`.
Test source SHA256
`a6113b09b70fd766d0ed24880d0284a3a39847cdeb603346f8402278866d6468`.
The earlier PR9974 component result remains separate from these direct-consumer
checks. No whole-agent latency or whole-repository CI claim is made here.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
