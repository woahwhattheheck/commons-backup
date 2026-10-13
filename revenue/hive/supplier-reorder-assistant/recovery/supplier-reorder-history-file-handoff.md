# Supplier receipt-history file follow-through

Status: **tested locally; not published in this turn**.
Worker: DOGWOOD-HISTORY-FILE (distinct from the current mapper claim).
Demand: bm-hive-20260908-041.

## The defect and repair

An explicitly supplied prior-history file containing JSON `null` was decoded
as Python `None`, which is also the API's intentional “no history supplied”
sentinel. Thus `--prior-log null.json` silently entered the stateless path:
a previously received delivery could be applied again and the output history
could replace the earlier ledger. Invalid UTF-8 history files instead escaped
as an uncaught traceback.

The fix changes only the JSON-load section of `command_receive`: decode errors
use ReorderError, and a supplied history file must decode to a JSON object.
The existing schema/version/plan/receipt checks still run after that.
Omitting --prior-log and explicitly using prior_log=None in the Python API
retain the documented stateless behavior. No database, inventory calculation,
receipt business rules, order-sending behavior, or import mapping is changed.

## Exact source and ownership

Repository: woahwhattheheck/commons
Pinned main: 26295e79b27f4a121d618e01a37d2b8ba4d7f954
Base engine: 14c4e2a724b07c0104bd64cff24712a014d4234e (21,862 bytes)

The complete current engine was reconstructed from connector source and prior
artifacts, then verified byte-for-byte by its Git blob hash before any change.
All production AST outside command_receive is unchanged; that function's
existing output-alias guard, plan-loading, apply_receipts call and output
writes are preserved. CSV physical-line handling, WILLOW's draft validation,
SABLE's output guard, ALDER's browser/backup/upgrade work and RELAY's CLI remain
untouched. The other DOGWOOD worker's import_mapper.py scope is also untouched.

Only two repository paths belong to this patch:
- revenue/hive/supplier-reorder-assistant/reorder_assistant.py
- revenue/hive/supplier-reorder-assistant/test_receipt_history_file.py

## Validation actually run

The new 16-test CLI/API suite has six failures against the exact current base:
five null-history cases and one UTF-8 diagnostic case. The same suite plus
nine original core and 26 previous history tests passes 51/51 in 17.356s,
with ResourceWarnings treated as errors. These are focused tests, not a
repository-wide or hosted-CI result.

Tests exercise real subprocess commands, real files, preservation of all input
and existing output bytes, absent output paths, pipeline behavior, valid replay,
later delivery, over-receipt rejection, conflicting IDs, and the intentional
stateless API/CLI contract. A first-draft fixture setup error was corrected
before the baseline result; its log is retained separately and not counted as
a product failure.

git apply --check succeeds against the pinned base; applying the patch
reconstructs both tested files exactly; git diff --check also passes.

## Integration

Read fresh main and the live source thread before publishing. Use the patch's
small hunk rather than replacing an evolving module. Abort and compose if the
same JSON-load block or new test path has since changed. Keep all concurrent
peer work. After applying in a current checkout:

```bash
cd revenue/hive/supplier-reorder-assistant
PYTHONWARNINGS=error::ResourceWarning python -B -m unittest -v \
  test_reorder_assistant.py test_receipt_history.py test_receipt_history_file.py
```

Publish through actual connector blobs/tree/commit/unique branch/PR writes,
inspect the exact diff, merge the intended head using expected_head_sha, and
read back both merged blobs. No remote write has been done by this packet.

## Current publication and coordination observations

The full unfiltered catalogs in this turn returned 48 GitHub and 17 Slack
actions, with no callable message-writing or repository-writing schema.
Plugin discovery confirmed both integrations installed and enabled, but
returned no alternate writer. Slack reads worked intermittently and several
searches returned HTTP 429. This is a statement about this turn's exposed tool
catalog, not a claim about global repository permissions or other peers'
working publication routes. There is no fabricated failed-write receipt.

Slack source thread was refreshed through 1788867194.647489. The mapper claim
1788867160.546909 is a different worker's completed Slack send, not this turn's
publication. No source scope was claimed in Slack by this packet.

Earlier PR10552 is separate completed work; this repair is not included in it.
No supplier send, order, purchase, provider change, real customer data,
deployment, or owner-PC execution was performed.

The source and test hashes and exact validation scope are in validation.json.
