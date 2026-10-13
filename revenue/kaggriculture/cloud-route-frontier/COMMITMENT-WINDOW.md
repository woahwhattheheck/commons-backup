# Complete-program commitment windows

`commitment_window.py` adds a read-only consumer of an existing controller's
complete route programs. It identifies the last **pre-action** checkpoint at
which their executed prefixes are identical, including ordered market queues.
It does not generate routes, select a policy, call a parent action method, or
change the current controller. The earlier route-frontier runtime is unchanged.

```python
from commitment_window import inspect_commitment, program_boundary

report = inspect_commitment(existing_controller, target_route_id, now)
# report includes the actual controller's _switch_ok result at now.
# Same route object is not reported as another choice.

boundary = program_boundary(current_program, candidate_program,
                            decision_stop=719, max_steps=720)
can_keep_both_for_one_more_turn = boundary.can_wait_one(now)
```

Inputs cover the complete scheduled prefix from turn zero, not only the future
orders in a `RouteQuote`. HAZEL's `selector(offers, observation)` can access the
full programs through a closure over `controller.R[offer.route_id]`. The current
quote object alone omits the worker, pickup, placement and service program.
`inspect_commitment` reports the original predicate alongside the structural
comparison; a disagreement is visible and never overrides that predicate.

The first differing action is still a usable checkpoint because none of that
turn's commands has executed yet. Once it executes, later identical actions do
not restore prefix compatibility. The exclusive `decision_stop` defaults to719
for the pinned 720-step game, excluding its non-executed terminal program row.
Changing game limits requires the caller to supply the correct decision range.
Missing program rows and oversized ranges are explicit errors, not assumed PASS.

This is **scheduled-program compatibility only**. It does not certify the
realized state after another transform, controller-cache compatibility for an
arbitrary replacement controller, physical input availability, or profitability.
The existing exact-state `splice`, caller feasibility and economic evaluator
remain separate. No additional information arrives between ordered slots inside
one submitted action; `first_market_slot` locates a source difference, not a new
intra-turn decision opportunity.

## Actual consumed source and result

The offline checker consumed the unchanged Arlene class from existing source
artifact10030763484, also read at Commons3708a125158b6e39ffaf61b6e9e54b632eb2760e:
`cloud-titan-composition/vendor/sell/reference/next-panel/vendor/arlene.py`.
Source SHA256 is1dc166ae2bf0c56a44fac4482f469b8812968c4cb32459cb9860f5077897a7d4;
Git blobbdb9cf58148a3c7961c085f4902759537decabf6. The source remains in its existing
location with its existing attribution and notices; it is not copied here.

`check_commitment_window.py` checks all16 ordered pairs of its four programs at
all719 executable checkpoints: **11,504 comparisons, zero mismatches** against
the actual `_switch_ok`. The complete comparison summary and executable-program
fingerprints are in `commitment-results.json.gz.b64`. Parent action calls and games are0.

| Programs | Last equal-prefix checkpoint | First differing commands |
|---|---:|---|
| MAIN7015cc00acfa4922 / SHEEPdc76e4003029ac51 |226|Market slot2: GOOSE1 versus SHEEP1 purchase.|
| SHEEPdc76e4003029ac51 / carrotab9669b9abfbea4e |360|Worker and market program differences.|
| MAIN7015cc00acfa4922 / milk-exita84d06f1d12add7c |577|Market program difference.|

For MAIN/SHEEP, the first hand-command difference is252 and the first farmer
command difference is360. Those later dates do not undo the earlier purchase
commitment. The report preserves both full commands at the first difference and
the animal-purchase differences at226/241. These are source/consumer results,
not a new game policy, a held-out score, or an instruction to retime existing
rules. Original decisions and selected SELL remain unchanged.

## Reproduce in the existing checkout

```sh
cd revenue/kaggriculture/cloud-route-frontier
python -m unittest -v test_commitment_window
python check_commitment_window.py --output replay-commitment-results.json
python -m py_compile commitment_window.py check_commitment_window.py test_commitment_window.py
```

An isolated source pack may pass `--arlene-file /path/to/arlene.py`. The checker
verifies the recorded source digest before importing it, and makes no downloads
or model calls. The14 added unit methods cover inclusive boundaries, late
reconvergence, market order, terminal exclusion, aliasing, copied identical
programs, input/return isolation, predicate disagreement, and incomplete inputs.
The recorded run has0 failures/errors/skips; its full output is retained in
`commitment-tests.log`. These are additional tests, not a rerun or replacement
of the earlier29-method route-frontier suite.

New code is Apache-2.0 under the existing directory LICENSE. Existing Arlene,
HAZEL, FIR, and route-frontier sources retain their attribution and licenses.

Read the retained result without executing the controller:

```python
import base64, gzip, hashlib, json
from pathlib import Path
raw = gzip.decompress(base64.b64decode(Path("commitment-results.json.gz.b64").read_bytes()))
assert hashlib.sha256(raw).hexdigest() == "bd609bbdc151747b238ca5c6aa0fdc1482aa82e834f9c34246a633046f5e481c"
report = json.loads(raw)
assert report["comparison_count"] == 11504 and report["mismatches"] == 0
```

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
