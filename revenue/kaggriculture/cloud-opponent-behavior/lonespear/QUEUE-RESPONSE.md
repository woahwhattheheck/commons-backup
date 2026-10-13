# Public lonespear proposal into the existing market comparator

`queue_response.evaluate_wheat_response` composes the published public predictor
and delay proposal with the existing `cloud-market-queue-delta` comparator. It
does not add a simulator, source classifier, flow predictor, controller or policy
selector. Existing `behavior.py` and QUEUE's source are unchanged.

```python
from queue_delta import compare_queues
from queue_response import evaluate_wheat_response

report = evaluate_wheat_response(
    compare_queues, mechanics,
    observation=original_observation,
    configuration=configuration,
    selected_action=selected_action,
    own_farm=post_unit_own_farm,
    own_private=post_unit_own_private,
    market=post_unit_market,
    scenarios=correlated_rival_scenarios,
    retained_wheat=committed_wheat_minimum,
    deadline=absolute_monotonic_deadline,
)
```

The original observation precedes the selected unit phase. The separate owned
farm/private/market inputs are **after** those selected worker actions and before
market. The helper never replays units. Each caller scenario uses QUEUE's existing
`id`, `provenance`, `farm`, `private`, and `action` structure; its complete correlated
rival state and queue apply equally to both arms. Hypothetical rival stock remains
a caller assumption, never observed truth or a value inferred by the detector.

The comparator is invoked once at most. Inactive/unsupported proposals preserve
`fallback_action` with no comparison. An unknown or partial comparison retains
that complete fallback and exposes no `proposal_action`; its completed rows may
remain diagnostics without aggregate bounds or a ranking. The existing deadline,
scenario, order and work budgets pass through unchanged. Cancellation exceptions
are not swallowed by this consumer.

For `status="complete_conditional"`, `proposal_action` holds the unchanged tested
proposal and `comparison` holds QUEUE's full two-arm states, per-slot effects and
bounds. **Even this status does not select the proposal**: `action_selected` stays
false. Bounds cover the supplied scenarios only, and only the current market;
future commitment feasibility, omitted flows and continuation value remain with
the existing caller. The helper does not filter away inconvenient scenarios.

## Executed correspondence

Twelve consumer methods pass against exact QUEUE source from PR10035,
`4dcda7adbbca5187303a8161b7774a263954c03c`, Git blob
`b95dff0010cf70941cc96e7f416798d36a8aa57d`. Source SHA256 is
`e95e0b8e3cc481d4687e9f0e6c3e53b4e4cbd4cf1b48f740f86acaa8a8b24122`.
The original public behavior is Git blob `fd0fbbb0e3a8c31f222aeed0c673517337f65970`.
Neither dependency was modified or replaced.

Tests include actual paired buyer/seller scenarios in both positions, exact
complete-report equality to direct comparator calls, one-call accounting,
nonmutation/detached results, reservations, public negatives, incomplete inputs,
forwarded work limits, expired deadlines and a controlled deadline after one
scenario has genuinely completed. That partial report is not promoted to a
ranking. These 12 consumer tests are separate from the original 12 model tests.

The real reached-state consumer uses the **same six** step697 cases retained by
PR10085, plus their original no-feed interventions. It does not invoke the source
policy or rerun any full game. All 12 conditional rows match both original complete
farm/private states and the complete market: 120 whole-state comparisons. Original
cash changes remain +17/−17 and +22/−22 in the buyer cases, and −70/+70 and −47/+47
in the seller cases. Removing the feed buy eliminates the positive changes but
does not remove the seller losses. No negative row is dropped or relabeled.

`QUEUE-CONSUMER.json` records the exact inputs, dependency blobs and results.
`QUEUE-TESTS.json` binds the three new source files and the separate test scope.
The official engine hash remains
`bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e`.

## Reuse and reproduction

From this directory, using the already-delivered dependencies:

```sh
TITAN_QUEUE_SOURCE="$QUEUE/queue_delta.py" TITAN_ENGINE="$ENGINE" \
  python -m unittest -v test_queue_response
python check_saved_queue_response.py \
  --cases "$ORIGINAL_ARCHIVE/analysis/cases.json.gz" \
  --queue-source "$QUEUE/queue_delta.py" \
  --engine-source "$ENGINE/kaggriculture.py" \
  --output queue-consumer-readback
```

The original archive is `TITAN-IRIS-Lonespear-D-20260907.zip`; it remains unchanged.
The companion `TITAN-IRIS-Lonespear-Queue-Consumer-20260907.zip` contains this
consumer, exact required dependencies/licenses, those six existing cases and the
complete comparison reports. Its separate `QUEUE-DELIVERY.json` identifies the
saved Library copy. No new source export, game, seed or policy freeze was needed.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
