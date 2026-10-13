# S3 SE-land — NO_BUILD evidence receipt

Canonical preservation of the reviewed S3 lane from closed PR #12592. The exact historical source/test bytes are retained for auditability only.

## Canonical disposition

**NO_BUILD. Do not port or activate.** Current `candidates/v4/INTEGRATION.json` records S3 as `NO_BUILD_measured_negative_0_of_23_positive_do_not_port` and explicitly forbids reopening S3 as a new key without new evidence that overturns that disposition. The key historically shipped OFF and remains OFF.

This directory is a negative/evidence receipt, not an active gameplay repair candidate. Do not execute the legacy materializer, wire `r04_s3_land` into the modern production ABI, buy land in production, move a production archive/submission/Kaggle ref, or create a successor V4 line from these bytes.

## Exact historical authorities

- owner PR: `#12592`
- historical head: `fa8cdfdaf7163041e300a902e2430963da099b21`
- helper/source blob: `9c17c8ccc197d12383d29bba717016435a4a863f`
- focused test blob: `beb896b6e39e2d9e12608c97533ed57583725a00`
- historical package gate: 291 package checks, 26 focused S3 checks; key shipped OFF

## Historical mechanism and boundary

The lane appended one guarded `BUY_LAND` for SE after NE+SW ownership, with cash/order/timing/demand/V219 guards and an explicit dependency on the SE operator/S1+S2 herd. Those bytes are retained only to make the rejected experiment reproducible; the historical composition boundary does not authorize a modern port.