# Funded-seed joined integration evidence

JUNIPER's single optional `seed_queue_selector` seam and repository-layout
`cloud-integration-differentials/funded_main.py` consume CEDAR's existing
certificate. CYPRESS supplies the composed-path tests and their step in the
existing `titan-selected-projection` workflow. No second hook, selector, producer,
solver, runner, or source export is introduced.

## Executed result

Hosted run [34174381218](https://github.com/woahwhattheheck/commons/actions/runs/34174381218),
source `ff81687372ac83c3a0684c038fe62cfdedf90dc6`: **16/16 new test methods pass,
14 official interpreter transitions, zero failures/errors, zero full games**.
The suite took 0.326358 seconds in that hosted process. The workflow's existing
79 methods also pass, for 95 methods across its seven test logs. Existing methods
are regression coverage, not new component discoveries or gameplay evidence.

The new composed cases use actual ALDER, the integrated agent, CEDAR, the existing
ordered seller, and the pinned official engine. Small explicitly constructed
route tapes activate the funding boundary; they are not reached-game observations.
Actual intact Arlene first calls are separate cases, one controller call per seat.
Their measured constructor-plus-call values (0.019155 / 0.017337 seconds) are in an
already-imported process, not fresh-process cold start or action maxima.

In the both-seat funded fixture, the existing demand proof trims BUY_SEED WHEAT
17 to 3 while preserving the same HIRE. Own cash is 597 versus 737 (+140); full
non-seed own/rival state, shared market and town match. Current-PLANT ordering
retains one future seed and saves 160. The terminal PLACE/sale fixture saves 170
without losing the deposited carrot. The underfunded negative keeps the original
queue and cash 130; an uncertified reduction would instead enable a HIRE and finish
at 67. These are current-transition cash effects, not terminal policy gains.

Other coverage: default/None parity, disabled seeds, extra current-PLANT demand,
no edit, nondependent queue, unresolved BUY_PRODUCT, parent-only control, order
truncation, detached callback inputs/outputs, exception fallback without retry,
and the published variant factory.

## Reproduce and inspect

From a normal repository checkout:

```sh
python3 -B revenue/kaggriculture/cloud-composition-cases/cypress/test_funded_join.py \
  --json-output /tmp/funded-join-results.json
```

The full original JSON receipt is retained losslessly as
`funded-join-results.json.gz.b64`. Decode it without running any game:

```python
import base64, gzip, hashlib
from pathlib import Path
raw = gzip.decompress(base64.b64decode(Path('funded-join-results.json.gz.b64').read_bytes()))
assert hashlib.sha256(raw).hexdigest() == '16528f4295e27153c444350074b47455ef04e9e7c64e351cbddd72d00ae6a2e6'
Path('/tmp/funded-join-recorded.json').write_bytes(raw)
```

Test SHA256: `795ff3a43adc8a91a8f3f43dbd1dfe89ac4110d48cd689938c4c3fd949caf843`.
Integrated runtime: `dd6b0b52575ad95a975695d372546ebfbdcb829065574d9c94eab5085a44a9fe`.
Funded entrypoint: `1b2587bc81533f4cafb9c844d8b5dec1e199460feb8f0a5e0cb7236e8c04ef56`.
Original CI artifact10036744675 ZIP SHA256:
`dbb8977c3394f0c1f857f844222b264981eff8c50761424e5a92b6cec842609d`.
The recorded source snapshot binds all tested dependency bytes.

## Existing frozen source transport

The same existing workflow now also copies the already-committed
`cloud-execution-lab/exports/integrated-selected-v1.tar.gz` into its ordinary
validation artifact. It asserts 103527 bytes and SHA256
`95c7bf10a20149419e6208e43cdf2bf0728e22fe61b600180eaa1a3fbcc1b153`.
This is the unchanged PR9997 source archive, **not** the optional funded variant.
It is copied, not rebuilt. The addition serves SPRUCE-7405 and ADMISSION's existing
actual-parent consumers; no separate exporter, workflow or dispatch is needed.

T08 can compare `funded_main.make_agent()` against
`funded_main.make_agent(funded=False)` with one separate producer per actor.
For the existing path-based executor, `cloud-execution-lab/integrated_main.py`
is the unchanged no-callback control. `integrated_parent.py` disables SELL and is
not the funding-only control. Keep frozen SELL as a separately labelled benchmark;
new full-game/held comparisons remain with existing executor owners.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
