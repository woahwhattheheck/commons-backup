# Revenue proof settlement ledger

`revenue_proof_ledger` is a deterministic, read-only reducer over already-produced
opportunity, delivery, settlement, and lookup receipts. It never queries or mutates
Slack, GitHub, payment providers, customers, invoices, accounts, or credentials.

Its four money states remain deliberately separate:

- **pipeline_expected** — canonical advertised/contracted opportunity amount;
- **earned_unsettled** — accepted current delivery value not yet backed by complete settlement evidence;
- **cash_settled** — net settled payment authorized only by complete, snapshot-bound evidence;
- **reversed_or_disputed** — settled refunds/reversals/disputes that back cash out without erasing delivery history.

Successor operation: `REVENUE-PROOF-LOOKUP-SNAPSHOT-BINDING-ZMASTHEAD913A-20260913`.

## Input v2

The required schema is `commons-revenue-proof-input/v2`. Every receipt carries
`kind`, canonical `opportunity_id`, `source`, `authority`, and an immutable lowercase
`sha256:<64 hex>` `evidence_digest`. Unknown fields are rejected and money is accepted
only as plain non-negative decimal strings.

Opportunity, delivery, and settlement semantics are unchanged from v1: canonical
opportunity terms must agree; one current accepted delivery establishes earned value;
settlement IDs are globally deduplicated; settled payments add cash while settled
refunds/reversals/disputes subtract it.

### Snapshot-bound lookup receipts

A v2 lookup is no longer a bare assertion that a reader was "complete". It must bind
that assertion to one exact inventory snapshot:

```json
{
  "kind": "lookup",
  "opportunity_id": "github:acme/widget#42",
  "source": "payment-reader:stripe",
  "authority": "complete",
  "evidence_digest": "sha256:...",
  "scope": "settlement",
  "snapshot_id": "stripe-account-snapshot-20260913T073000Z",
  "observed_at": "2026-09-13T07:30:00Z",
  "inventory_ids": ["stripe:pi_1", "stripe:re_1"],
  "inventory_digest": "sha256:..."
}
```

`inventory_digest` is SHA-256 over canonical JSON containing `scope`, `snapshot_id`,
UTC-normalized `observed_at`, and sorted `inventory_ids`. Duplicate inventory IDs are
invalid.

For each opportunity and scope (`delivery` or `settlement`), only the latest observed
snapshot controls lookup authority. Multiple receipts at that exact latest timestamp
must describe the same snapshot identity and inventory or authority becomes `unknown`.
An older partial/unknown lookup does not poison a later coherent complete snapshot; a
newer partial/unknown lookup correctly supersedes an older complete one.

Most importantly, a **complete** lookup inventory must exactly equal the deduplicated
delivery or settlement IDs supplied to the reducer. If a paid event is present but the
complete snapshot omitted it, or the snapshot lists a refund/reversal whose receipt is
missing, the ledger fails closed and authorizes zero `cash_settled`.

The emitted row includes the effective lookup snapshot ID, normalized observation
time, inventory digest, and count. This is explicit **as-of evidence**: the reducer
proves consistency with the supplied snapshot; it does not claim that no event can
occur after that observation time.

## Fail-closed authority

Settled cash is nonzero only when all of these are true:

- canonical opportunity amount/currency/identity are coherent;
- exactly one accepted delivery is current;
- the effective delivery and settlement lookup snapshots are both `complete`;
- each complete lookup inventory exactly matches the supplied receipts for that scope;
- all counted receipt authorities are complete;
- settlement IDs, delivery binding, currency, amount, and reversal arithmetic are coherent.

Explicit `partial` evidence remains partial. Missing, conflicting, inventory-mismatched,
or otherwise unknowable evidence becomes `unknown`. In either case `cash_settled=0`
while observed evidence, accepted delivery value, authorship lineage, and reversal
history remain visible.

## CLI

```sh
python -m tools.revenue_proof_ledger.ledger receipts.json \
  --json-out revenue-ledger.json \
  --summary-out revenue-ledger.md
```

Both outputs are create-exclusive. JSON includes a deterministic `ledger_digest`.
Exit status is `0` only when resulting ledger authority is complete; partial/unknown
authority and input/I/O failure return `2`.

## Verification

```sh
python -B -m unittest -v \
  tools.revenue_proof_ledger.test_ledger \
  tools.revenue_proof_ledger.test_partial_authority

python -O -B -m unittest -v \
  tools.revenue_proof_ledger.test_ledger \
  tools.revenue_proof_ledger.test_partial_authority

python -m py_compile \
  tools/revenue_proof_ledger/ledger.py \
  tools/revenue_proof_ledger/test_ledger.py \
  tools/revenue_proof_ledger/test_partial_authority.py
```

The suite retains the v1 arithmetic/identity/credit/output coverage and adds hostile
proofs for omitted refunds, snapshot-listed-but-missing receipts, delivery inventory
mismatch, digest tampering, duplicate inventory IDs, conflicting latest snapshots,
partial→complete and complete→partial snapshot succession, timestamp normalization,
and deterministic input permutation.
