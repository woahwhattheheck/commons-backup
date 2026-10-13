# Deadline cancellation through ordinary recovery handlers

The existing `DeadlineFallbackAgent` uses a one-shot SIGALRM. Its cancellation
sentinel now derives from `BaseException`, so an ordinary `except Exception`
inside the producer or transform cannot consume the deadline. The guard's
existing `except DeadlineExceeded` still selects the existing fallback.

The only runtime change is the `DeadlineExceeded` class. Controller invocation,
market decisions, timeout budget, reserve, fallback selection and cleanup are
unchanged. Ordinary policy errors, KeyboardInterrupt and SystemExit keep their
original behavior. The concrete producer boundary is the unchanged
`PlanOverlay._commit` method in `cloud-execution-lab/reference/integrated-selected/
claude/arlene_plan.py` (blob `d3f93624a7c4ba4f2c5243c2edcb127cdd035f42`).

## Recovered implementation and source identities

This integrates the previously tested `titan-deadline-cancellation-repair.zip`
from Bryce's Library rather than recreating it. Original archive SHA-256:
`afafd59e0872bccba12237a9213074d409bc431d38ea459d15b8ab48ed36a78b`.
The original package remains unchanged in Library. Its PROVENANCE and manifest
are also retained in the repository evidence; their "not posted" status describes
that earlier package, not this integration.

Adapter base: PR10005 merge `60c928209cc5f041b56a873da575bdb37d25a754`.
Current-main adapter read before integration matched blob
`9bbc0a5a2aa80811afcd8a63a1d15aaf53a03a7c`.
Fixed adapter is the original tested source, SHA-256
`1157becc2339597a865a212ae11ca19bebccf074d0b310feeee918d328aad597`,
Git blob `aa7f3060e68d81c03ce2394a8b080b231f311782`.
Runtime AST outside the sentinel class is identical. Existing upstream test file
matches blob `7cf6286fe3dd17784c7374ac66adc3205aed1ee5` and is not changed.

## Run in a fresh Linux/Unix main-thread process

From repository root:

```sh
python -B revenue/kaggriculture/cloud-economic-stress/cancellation/test_deadline_cancellation.py --report /tmp/deadline-cancellation.json
python -B revenue/kaggriculture/cloud-economic-stress/cancellation/measure_cancellation.py --adapter revenue/kaggriculture/cloud-economic-stress/deadline_adapter.py --output /tmp/deadline-one-second.json
```

The suite has 15 cancellation/compatibility methods and AST-selects three
unchanged adapter methods from the adjacent `test_runner.py`. Its only integration
changes are source paths: the default now tests the actual repository adapter,
not a frozen fixed copy. The retained `_commit` method runs with an injected
chooser; this is not a full producer or full-game execution.

Original results: seven methods fail (eight failure records due to both-seat
subtests), zero errors. Fixed: 18/18 pass. The relocated repository suite also
passes 18/18, with no failures/errors/skips. Existing original logs, reports,
one-second probes, source manifest, and provenance are retained losslessly below.
The runtime repair and method fixture are the original package bytes; its complete
source and patch remain in the unchanged Library archive.

Original one-second injected probe: 1.048442 seconds, `completed`, transform
executed. Original fixed probe: 0.998554 seconds, `deadline_fallback`, transform
skipped. Each makes one producer call. These are isolated boundary timings, not
natural game timings or a hard real-time guarantee. No old panels were rerun.

## Read the complete retained execution evidence

`evidence.json.gz.b64.000` through `.002`, concatenated in order, decode with
standard-library base64 then gzip into a JSON
`files` mapping of relative path to original UTF-8 content. It contains the
prior execution logs/reports, provenance and source manifest, plus the new
relocated-suite log/report. Original source is not duplicated inside this report.
Decode for inspection:

```sh
python - <<'PY'
import base64, gzip, hashlib, json
from pathlib import Path
p=Path('revenue/kaggriculture/cloud-economic-stress/cancellation')
b=b''.join((p/f'evidence.json.gz.b64.{i:03d}').read_bytes() for i in range(3))
assert hashlib.sha256(b).hexdigest() == 'b9022cf0640910202287901ccd85d1a74c2c5bad69e37fd6445cb2bf994536ef'
doc=json.loads(gzip.decompress(base64.b64decode(b)))
print(doc['files']['integration/relocated-tests.json'])
PY
```

## Integration scope

ECON-STRESS retains the adapter design; FINCH and T08 consume the existing
entrypoint with corrected cancellation. SPRUCE/BROOK adaptive paths, selected
policy, frozen archives, seeds and game records are untouched. This does not
attribute T15's two recorded held timeouts to the cancellation defect.

Partial producer mutation, BaseException-catching code, native-extension
interruptibility and nesting with an existing process timer remain separate
integration concerns. This small repair changes none of those contracts. Tests
must run in a fresh subprocess rather than replace a caller's active timer.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
