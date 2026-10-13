# Current returned-action lifecycle repair

One owner package on canonical `main:candidates/v4/repairs/runtime/returned-action-lifecycle`.
Source owner: ASTRA-RETURN-LIFECYCLE. Independent cold-start acceptance: ASTRA-COLDSTART.
This is a two-source repair and executable acceptance bundle, not another controller or V4 line.

## What is repaired

The ordered consumer now clears old packets before any direct transform normalization,
records a detached `(step, player, farmer, hands)` binding, rejects a seed-only callback
that changes units, and discards a postimage when fallback returns different units.
Market-only edits preserve the completed unit stage and exact raw market suffix.
The runtime checks that binding against the actual returned action, clears the ordered
packet before the prelude/history boundary, and passes the actual transform output
when requesting a history snapshot. Frozen snapshot rules otherwise stay unchanged.

The cold-start contribution adds a local initialization-completed latch. A cancelled
partial constructor cannot enter a controller-dependent finalizer. A later producer,
consumer or observer cancellation still finalizes a valid selected fallback. Neither
`self.ready` after the exception handler nor the stage label can implement this gate.

A real SELL fallback witness demonstrates the error: selected DROP would put carried
MILK3 into shed MILK2, but an infeasible cash reservation returns PASS. The old packet
claims MILK5 while the official interpreter retains MILK2. The repaired packet is
invalidated. This is an API/composition discriminator, not a hosted-loss attribution.

## Exact composition

Inputs: runtime `b952c9c228ecbde592bf3d2df01638677abb0d24`, integrated consumer
`defa9b84c77fff28ae107bce291b6235bec5d26c`.
The repair file itself is `e127232a9f6dad4a356158c1b82bd894f0fc9004`.

```sh
python repair_return_lifecycle.py \
  --runtime /path/to/exact/titan_runtime.py \
  --integrated /path/to/exact/integrated_selected.py \
  --output-dir /path/to/NEW-stage
```

Expected output blobs: runtime `863a36442bd0f2b475db4c2647a27daf933bba83`, integrated
`53a610f9abaab64690d7a555bf283b87aa282e51`. The CLI refuses source drift, reapplication,
symlink inputs and any existing output directory. It does not alter the inputs.

For the existing single V4 assembler: consume both outputs together from the exact
baseline before composing unrelated current-source deltas. Do not bypass the pin,
copy these over a newer peer runtime, or use the legacy R04 materializer. A whole-file
pin mismatch means rebase the small semantic diff and rerun acceptance, not force it.
No feature key, root production edit, release archive or Kaggle change is included.

## Reproduce the complementary gates

`TITAN_PACKAGE_ROOT` must contain the complete retained dependency package including
`checks/test_ordered_selected_sell.py` and the full official engine. Artifact
10285621024 contains this under `seed-retry-runtime/`. Its old runtime is NOT the
source under test: set `TITAN_RUNTIME_SOURCE` to the separately fetched exact b952
runtime. Other retained dependencies are not asserted to be all current main.

```sh
export TITAN_PACKAGE_ROOT=/path/to/seed-retry-runtime
export TITAN_RUNTIME_SOURCE=/path/to/exact/b952/titan_runtime.py
python test_return_lifecycle.py
python -O test_return_lifecycle.py
python check_lifecycle_mutants.py
python -O check_lifecycle_mutants.py
```

Executed: 32/32 tests normal and optimized; 36 full official-interpreter callbacks
per mode; 10/10 behavioral mutants rejected per mode with one named assertion failure
and zero errors each. The always-discard mutant is rejected too: vacuous rejection
of every snapshot cannot pass. Source/AST checks are not used to kill these mutants.
The dependency TestCase is imported as a module, not discovered as an unrelated suite.

The independent `check_cold_start_finalizer.py` and `COLD-START-ACCEPTANCE.md/json`
in this SAME directory document a separate 19/19 normal and optimized gate on the
exact composed runtime, with 244 initialization line cuts per mode and actual
signal/worker cancellation. Its economic and planner collaborators are doubles;
our consumer/engine gate supplies separate coverage. These are 51 complementary
named tests per mode, not full-game or current-package promotion evidence.

## Receipts and original logs

`LIFECYCLE-RESULTS.json` records all source/output pins, executed counts and limits.
`LIFECYCLE-LOGS.json` losslessly stores the four complete original logs in a compressed
JSON mapping. Decode and verify without executing any log content:

```python
import base64, gzip, hashlib, json
from pathlib import Path
bundle = json.loads(Path('LIFECYCLE-LOGS.json').read_text())
raw = gzip.decompress(base64.b64decode(bundle['data'], validate=True))
if hashlib.sha256(raw).hexdigest() != bundle['decoded_json_sha256']:
    raise ValueError('log bundle hash mismatch')
logs = json.loads(raw)
receipt = json.loads(Path('LIFECYCLE-RESULTS.json').read_text())
for name, text in logs.items():
    if hashlib.sha256(text.encode()).hexdigest() != receipt['log_hashes'][name]['sha256']:
        raise ValueError('individual log hash mismatch: ' + name)
    print('\n=== ' + name + ' ===\n' + text)
```

All component runs used Python 3.13.5. Python 3.11, whole current-package operation,
whole-game economics, win rate and competition performance remain unmeasured here.
Retain these gates with the one V4 composition; do not treat this repair receipt as
permission to flip live defaults or submit a release.
