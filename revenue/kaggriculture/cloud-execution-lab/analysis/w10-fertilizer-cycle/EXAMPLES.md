# W10 golden example pair

`examples/` contains one small, checked-in control/treatment pair and a one-pair matrix manifest. It is a **format and integration example**, not evidence that the current canonical TITAN producer has already achieved this outcome.

The example is deliberately legible:

- both runs start at tick 0 with cash 50, shed stock 2, and identical identity/capacity;
- the fertilized run records its additional fertilizer action at tick 1;
- incremental production first appears at tick 3;
- incremental harvest appears at tick 5;
- incremental deposit appears at tick 7;
- incremental sale appears at tick 9; and
- both runs terminate at the exact tick-10 horizon.

At the horizon, the treatment has one additional produced, harvested, deposited, and sold unit and six additional cash units, with no added discard, protected-obligation miss, or protected-stock shortfall. The pair therefore satisfies the v1 certificate contract.

Run the checked-in pair directly:

```bash
python realized_fertilizer.py \
  --control examples/control.json \
  --candidate examples/fertilized.json \
  --output /tmp/w10-certificate.json \
  --pretty
```

Run the manifest:

```bash
python matrix_runner.py \
  examples/matrix.json \
  --output /tmp/w10-matrix-result.json \
  --pretty
```

`test_example_fixtures.py` executes both library and CLI paths, checks the expected unit/cash deltas and milestone order, and independently verifies the certificate and matrix result hashes.

## Producer use

A producer recorder can begin by diffing its emitted document against these examples and `trace.schema.json`. Before promotion, replace every illustrative identity hash and counter with values observed from the real engine/evaluator/opponent/start state and run the complete required seed/opponent matrix. Do not copy this fixture into release evidence or treat its illustrative `CERTIFIED` result as a game-win receipt.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../../titanmcp.html). Cite Latch Pad KEEP.
