# Shared record boundary and independent consumer

This follow-through adds `recover_record` to the existing replayer; it does not
introduce another recovery algorithm or CLI. The CLI now uses this function too.
Original `recover_inputs`, tracer execution, authored actions and interpreter
remain unchanged.

```python
inputs, receipt = recorded_inputs.recover_record(
    document, evaluator, tracer, engine, engine_dir, loader, engine_hashes,
    game_index=0, expected_trace=None, seat=None,
)
```

The function checks the original schema, engine revision/file hashes, default
configuration contract, game selection, trace selection and original game
validity before selecting an optional player view. `seat=None` retains the
original candidate. `seat=0` or `seat=1` selects only that player's observations
for analysis; it does not combine private inputs from both players. Original
candidate identity is retained as `original_candidate_seat` and
`view_is_original_candidate`. The original rival's random/Python seed is
20260908, not the original candidate's 20260907. Do not pass receipt provenance
or the environment seed into a policy as extra information.

TRACE-9042's independent PR10042 contract can consume the same implementation
with field normalization only:

```python
def recover_for_contract(document, seat=None):
    inputs, receipt = recorded_inputs.recover_record(
        document, evaluator, tracer, engine, engine_dir, loader, hashes,
        seat=seat,
    )
    return {
        "configuration": inputs[0]["configuration"],
        "frame_count": len(inputs),
        "frames": inputs,
    }
```

This adapter performs no input validation or state reconstruction of its own.
The independent test owner retains execution and result publication for that
contract; its results are not asserted by this implementation packet.

## Executed local result

`test_recorded_inputs.py` now passes 22 methods: the original 19 plus three
covering document source/schema/custom-configuration checks, alternate-view
original identity/random seeds, and invalid original metadata not being masked
by a requested view. `RECORD-VALIDATION-RESULTS.json` binds this exact runtime
and test source. The original 19-method `TEST-RESULTS.json` from PR10047 remains
unchanged as its prior-version receipt; do not sum 19 and 22 as distinct tests.

The README's command is unchanged and now reports 22 methods. These are
constructed original-engine fixtures, not successful execution of the still
unmaterialized historical PR9997 record. No new gameplay, source exporter,
profiler, workflow or seed reservation is introduced.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
