# Public replay cash-gap bridge

DELVE's additive consumer of ROWAN's existing reconciled trace. No existing
analyzer, policy, selected entrypoint or opponent source is modified. The callable
is reusable by the separate LOSS-DELTA episode analysis.

## Interface

```python
from cash_bridge import build_bridge
report = build_bridge(existing_rowan_trace, own_seat=1)
```

The report exactly connects opening cash to terminal cash through reconciled
cash events, unverified observed changes and nonzero reconciliation residuals.
Causes, daily changes and adverse/favorable transitions are retained by seat.
A nonzero residual that cancels a later residual still prevents a complete
attribution claim. Unreconciled events never become inferred sales or purchases.

For products sold by both players, the symmetric identity is
`delta(q*p) = delta(q)*mean(p) + delta(p)*mean(q)`, using exact rational numbers.
These volume and realized-average-price terms are descriptive arithmetic, not
causal estimates of policy value. Timing and rival interaction can both affect
the realized average. If one player sells none, its price is null and the
revenue difference remains undecomposed. Nonintegral rational values are JSON
objects with `numerator` and `denominator`; integral values are JSON integers.

## Reproduction

Reuse the existing cloud engine cache from artifact10005621438. The existing
source archive10030763484 supplies both evaluator modules. Keep the repository
layout and use ROWAN's unchanged `cloud-frontier-trace/analyze.py` at Git blob
`9c7cd95005ce9c84b862f218049fd71e16ccd604`, available in Commons commit
`e161df9d48bf65e95a11ab4baff12ffba4cdddfd`. The loader verifies that exact blob and
the existing evaluator verifies official engine28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c.
No new source-export workflow, network setup or engine distribution is required.

```sh
D=revenue/kaggriculture/cloud-hosted-loss-response/new_loss_106567489
KAG_ENGINE_DIR=/path/to/existing/engine python -m unittest discover -s "$D" -p 'test_*.py' -v
python "$D/cash_bridge.py" /path/to/106567489.raw \
  --engine-dir /path/to/existing/engine \
  --episode-id 106567489 --player-index 1 \
  --our-submission-id 56081391 --rival-submission-id 56082977 \
  --expected-cash 70683,105675 \
  --provider-source 'Slack C0C0Z8AHGP2/1788816519.316279' \
  --output /path/to/new-output-directory
```

The CLI selects the recorded game position with `--player-index`; its initial
`--own-seat` spelling is replaced. The callable's `own_seat` argument and output
schema remain unchanged. This is a replay-data index, not a Commons identity.

The CLI accepts any explicitly bound two-player episode. Embedded EpisodeId, when
present, is compared as an integer/string identifier, matching the existing T13
diagnostics contract. Missing embedded identifiers remain null; the separately
recorded requested_episode_id comes from the provider reference. The CLI does not
inject that identifier into the raw replay or its trace. Terminal cash is checked
against the supplied receipt; the provider receipt, not a cash match, establishes
submission/seat identity. It writes `cash-bridge.json`, the
complete unchanged analyzer trace as `trace.json.gz`, exact observed before/after
frames as `observed-witnesses.json.gz`, and a hash manifest. Witnesses are
observations, not replacement actions or counterfactuals. Existing output
directories are never overwritten. No opponent program is executed.

## Validation and current input state

Twenty-two tests passed in the cloud with Python3.13.5: fourteen arithmetic/error
controls and eight actual pinned-interpreter fixture methods, including the CLI,
exact frame/hash readback, shared-seat observation normalization, day grouping,
capital spending, unequal sale volumes and different realized prices. The
insufficient-funding and sufficient-funding cases are distinct retained controls.
These are manufactured transitions, not scored games or hosted episode results.
`TEST-RESULT.txt` contains the executed test output.

The provider checkpoint binds episode106567489 to own seat1 and a34992 terminal
cash deficit. The new raw replay was requested through the existing shared cloud
retrieval/transport route. It was not present at this source checkpoint; no
cash-cause diagnosis, counterfactual gain or policy improvement for that episode
is claimed here. Original T13 replay and policy evidence remains unchanged.

Source follows the repository Apache-2.0 license. Preserve existing engine and
analyzer attribution and notices when redistributing dependencies. This
component adds no hosted submissions, notebook writes, owner-PC execution or
scored seed consumption.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
