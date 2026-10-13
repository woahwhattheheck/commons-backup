# Exeter finance acceptance engine — v2 behavioral contract

Parent issue: #15896  
Recovery: \`EXETER-FINANCE-ACCEPTANCE-RECOVERY-ZCAIRN-20260918\`

## Purpose and authority ceiling

This standard-library-only engine evaluates a bounded, retained evidence packet for a municipal-finance implementation/data-conversion workshare. \`READY\` means only that the admitted packet reconciles under this contract. It never creates buyer acceptance, accounting judgment, production posting authority, bank authority, payment authority, or revenue recognition.

Every report emits the literal authority string \`EVIDENCE_ONLY_NO_BUYER_OR_PRODUCTION_ACCEPTANCE\` and literal-false authority bits for buyer acceptance, production posting, bank action, payment, and revenue recognition.

Production semantics are closure-bound at import time. Public compatibility constants can be rebound or mutated without changing validator/evaluator/verifier truth.

## Input schema

Schema: \`tjlabs.exeter_finance_acceptance/v2\`.

Exact top-level keys: \`schema\`, \`as_of_utc\`, \`source_pin\`, \`generation\`, \`crosswalks\`, \`control_totals\`, \`subledgers\`, \`bank_reconciliation\`, \`required_interfaces\`, \`interfaces\`, \`uat\`, \`cutover\`.

### Source pin

\`source_pin\` binds the packet to retained procurement evidence rather than allowing the executable gate to outrun the source ledger:

- \`ledger_sha256\`
- \`procurement_index_sha256\`
- \`rfp_sha256\`
- \`qa_addenda_sha256\` (nullable only when the state permits)
- \`observed_at_utc\`
- \`qa_recheck_due_at_utc\`
- \`qa_addenda_state\`

Allowed states: \`RECHECK_NOT_YET_DUE\`, \`POSTED_AND_RETAINED\`, \`NO_QA_ADDENDA_REQUIRED_CONFIRMED\`, \`OFFICIAL_PAGE_RECHECKED_NO_POSTING\`.

The source observation may not be in the future and becomes stale after 48 hours. After the recheck boundary, \`RECHECK_NOT_YET_DUE\` cannot pass. \`POSTED_AND_RETAINED\` and \`NO_QA_ADDENDA_REQUIRED_CONFIRMED\` require a retained evidence digest. \`OFFICIAL_PAGE_RECHECKED_NO_POSTING\` is an explicit HOLD, not permission to infer that no addendum/Q&A exists.

\`as_of_utc\` is packet data, not the host wall clock, so replay is deterministic.

### Generation and crosswalks

\`generation\` contains exact lowercase SHA-256 \`source_sha256\` and \`target_sha256\`.

Required crosswalk categories are \`accounts\`, \`vendors\`, \`customers\`, and \`employees\`. Every category is nonempty. Each row is exact \`{source_id,target_id}\`; duplicate source identity fails closed.

### GL/control totals

Each \`control_totals\` row is exact:

\`{id, source_cents, target_cents, approved_delta_cents, adjustment_sha256}\`

Amounts are strict integers, never booleans/floats. The engine requires \`target_cents - source_cents == approved_delta_cents\`. A nonzero approved delta requires its own SHA-256 evidence receipt. A zero delta must not carry an adjustment receipt.

### Subledgers and GL linkage

Required subledgers: \`ap\`, \`ar\`, \`payroll\`, \`utility\`, \`cashiering\`.

Each row contains \`control_id\`, source/target count, approved count delta, source/target cents, approved amount delta, adjustment receipt, and exceptions.

Each subledger must reference one unique GL/control row. The linked control source/target cents, approved amount delta, and adjustment receipt must exactly equal the subledger values. This closes the predecessor defect where independently valid subledger and GL totals could disagree while both passed.

Target-source count/amount deltas must exactly equal separately declared approved deltas. Nonzero approved subledger deltas require retained adjustment evidence. Any unresolved exception forces HOLD.

### Bank reconciliation

Ending/reconciled amounts may be signed integer cents. Addition/deduction fields are nonnegative magnitudes; a negative deduction cannot invert direction. Statement-side and book-side equations must independently equal the declared reconciled amount.

### Interfaces, UAT, cutover

\`required_interfaces\` is a nonempty unique list. Every required interface must be present with a retained manifest digest and \`status=verified\`.

Mandatory UAT IDs: \`GL_FUND_ACCOUNTING\`, \`AP\`, \`AR\`, \`PAYROLL\`, \`CASHIERING\`, \`BANK_RECONCILIATION\`, \`UTILITY_BILLING\`, \`FINANCIAL_REPORTING\`, \`INTEGRATIONS\`, \`DATA_CONVERSION\`.

Every required case must remain mandatory, pass, and carry retained evidence. Additional mandatory cases must also pass.

Cutover requires content-addressed source-freeze, rollback, and replay receipts plus an empty unresolved-exception set.

## Output and verifier

Report schema: \`tjlabs.exeter_finance_acceptance.report/v2\`.

Output includes the hard-false authority ceiling, canonical packet SHA-256, \`READY|HOLD\`, stable deterministic exception records, and exception count.

\`verify_report(report, packet)\` recomputes against the privately captured semantic generation. Rebinding exported \`evaluate\` after import cannot change verifier truth.

CLI:
- \`engine.py PACKET.json\` → exit 0 READY, 2 HOLD, 64 invalid input/invocation.
- \`engine.py --verify REPORT.json PACKET.json\` → exit 0 exact semantic match, 3 mismatch, 64 invalid input/invocation.

JSON ingress is bounded to 1 MiB UTF-8, rejects duplicate keys and non-finite constants, and normalizes malformed input to typed receipts.

## Exact recovery proof

Recovery bytes were exercised locally before publication:
- \`python -m py_compile engine.py test_engine.py\` — PASS
- \`python test_engine.py\` — **33/33 PASS**
- \`python -O test_engine.py\` — **33/33 PASS**

The suite covers the predecessor STOP classes: public-policy rebinding/mutation, source-pin freshness and unresolved Q&A state, subledger→GL arithmetic/evidence linkage, nonnegative bank-adjustment magnitudes, verifier-generation rebinding, report tamper, strict authority bits, and deterministic replay.

These are source-execution receipts only. They do not establish buyer acceptance, provider-hosted CI truth, production accounting truth, contract acceptance, payment, or revenue.
