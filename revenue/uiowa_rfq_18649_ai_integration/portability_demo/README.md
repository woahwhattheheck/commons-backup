# UIOWA-080: preserved toy-provider integration

Offline, deterministic demonstration only. ALPHA and BETA are fictional rule
engines, not real hosted or self-operated AI providers. No institutional data,
network call, external action, deployment, or spend occurs.

## Run

From this directory, using Python 3.10 or newer and the standard library:

```sh
python run_demo.py > /tmp/uiowa080-demo.json
python run_demo.py --verify /tmp/uiowa080-demo.json
python run_demo.py --markdown
python run_demo.py --assessment-input > /tmp/uiowa080-case.json
python ../assess.py /tmp/uiowa080-case.json --out /tmp/uiowa080-assessment
```

Each report executes eight provider/mode combinations on the same five invented
documents. Normal ALPHA and BETA runs send two and three items respectively to a
human queue. Their different counts are not labor savings or equivalent quality.
The six failure modes send all thirty affected items to a person. A separate
fictional negative control passes the startup probe, then returns NaN: the
original caller auto-routes it without the wrapper, but requests human review
with the wrapper. The report contains decisions, not a nonstandard JSON NaN.

`GuardedPort` checks every response's type, document identity, taxonomy, finite
confidence, explanation, capability class and degraded flag. It translates
unexpected adapter exceptions to a domain failure. Always pass the same policy
to the wrapper and caller. It is not an untrusted-code sandbox and does not prove
semantic correctness of a classification.

## Integration and preservation

All seven `portlib/` files retain the exact Git blobs from Commons commit
`c3a51c6b16eb2c45ba887e851fd75f7a2d5c5782`, subtree
`f6d3eabd6aaf70565b6d9de8f2ea8883aaca7326`. Original provider-swap and
QUARTZ/QUARRY source credit is preserved. The original caller and deliberately
leaky negative control are not edited. Neither original top-level implementation
nor its existing examples are overwritten.

The bridge calls the existing `../assess.py` on a **new synthetic case**. Only
these toy request/response contracts, adapter swaps and fault-to-review behavior
receive executed evidence. Real latency, availability, staffing, cost, migration
effort, data export, equivalent-quality replay and core continuity remain unknown.
Both architecture alternatives consequently remain `unknown`, not ready to deploy.

`--verify` strictly parses JSON and re-executes the fixed example, comparing the
complete report, population, policy, outcomes, assessment and local source hashes.
Donor drift, changed source identity and edited reports are rejected. This is a
local reproducibility check, not a signature, remote attestation, or proof about
a modified interpreter or malicious in-process code. Reports go to stdout; no
historical output/receipt collection or automatic workflow is added to the repo.

One focused regression is available as `python -m unittest -v test_flow`.
The historical 37/42/46-test claims in the old work order are not inherited.
