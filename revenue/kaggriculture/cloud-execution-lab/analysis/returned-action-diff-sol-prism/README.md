# TITAN same-state returned-action differential

This harness isolates the first **observable action-level divergence** between two
TITAN endpoints or two saved response captures. It addresses a failure mode that
aggregate cash and win/loss panels cannot localize: two policies may receive
nominally similar game situations but return different order, movement, or
resource actions long before the score gap becomes visible.

The endpoint path serializes the supplied state exactly once and reuses those
same bytes for both endpoints. Capture bundles preserve the request/state hash,
raw response, unwrapped action, wrapper path, action hash, and optional repeated
samples. The report then performs a semantic JSON diff rather than a text diff.

## Why this is useful for the V1 → V2/V3 regression

1. Replay or extract one state immediately before a known cash cliff.
2. Send that exact state to the frozen V1 endpoint and the suspect V2/V3 endpoint.
3. Inspect the report's first divergent path and its top-level concentration.
4. Trace that field back through candidate construction, selection, and response
   serialization.
5. Repeat around the preceding step until the earliest causal action seam is
   found.

A verified request hash rules out input drift. A stable repeated capture rules
out endpoint nondeterminism. At that point a returned-action divergence is a
focused policy/runtime fact, not an inference from final score.

## Endpoint mode

```bash
python returned_action_diff.py \
  --state fixtures/step-95-state.json \
  --left-url "$TITAN_V1_URL" \
  --right-url "$TITAN_V2_URL" \
  --left-name v1-frozen \
  --right-name v2-structural \
  --header "Authorization: Bearer $TOKEN" \
  --repeat 3 \
  --capture-dir captures/step-95 \
  --json-out reports/step-95.json \
  --md-out reports/step-95.md
```

`--repeat` alternates endpoint order between rounds and reports the number of
unique action fingerprints per endpoint. Any instability should be resolved
before attributing a cross-version difference.

The endpoint URL stored in a capture has user information and query parameters
removed/redacted. Headers are never written to disk.

## File mode

Saved capture bundles provide a cryptographic same-state check:

```bash
python returned_action_diff.py \
  --left captures/step-95/v1-frozen.capture.json \
  --right captures/step-95/v2-structural.capture.json \
  --left-name v1-frozen \
  --right-name v2-structural \
  --json-out reports/step-95.json \
  --md-out reports/step-95.md
```

Raw JSON responses can also be compared, but the report marks state proof as
`unavailable` unless both files carry `state_sha256`. Mismatched capture hashes
fail closed. `--allow-state-mismatch` exists for exploratory work and leaves the
report visibly marked as a mismatch.

## Semantic alignment

Dictionary keys are compared recursively. Numeric values expose absolute and
relative deltas and honor `--abs-tol` / `--rel-tol`. Lists of market, product,
delivery, agent, order, or offer records are aligned by stable IDs (including
composite identities) so a harmless reordering does not create positional diff
noise. Other lists fall back to positional comparison.

Common endpoint wrappers are unwrapped automatically, including nested JSON
strings such as API Gateway `body` responses and `result → action` envelopes. A
scalar action payload such as `{"action":"SELL","market":"M1"}` is retained as
the action itself rather than mistaken for an envelope.

## Exit behavior

The default exit code is zero after a valid comparison, whether equal or
different. Add `--fail-on-diff` for CI: it returns `1` for a semantic difference
and `2` for invalid input, state mismatch, or endpoint failure.

## Tests

```bash
python -m unittest -v test_returned_action_diff.py
```

The suite covers nested wrapper extraction, keyed/composite list alignment,
numeric tolerance and deltas, fail-closed state hashes, first-divergence
reporting, exact request-byte reuse, and repeat stability against a local HTTP
server.
