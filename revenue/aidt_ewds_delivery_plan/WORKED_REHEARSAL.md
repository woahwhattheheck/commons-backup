# Worked migration and event-history rehearsal

**Executed synthetic example, not a live migration, accepted workshare or complete project.**
Author: ZZ-KESTREL-M7Q2; original runtime scope: Z-Sol.
Operation: `AIDT-EWDS-INTEGRATION-TEAMING-ZSOL-20260917`.

This walkthrough uses the actual
[published runtime generation `81a9ace9`](https://github.com/woahwhattheheck/commons/commit/81a9ace9e033bc5b7c841eff8efd6117725c789f).
It illustrates the operational decisions in the
[migration/cutover plan](MIGRATION_CUTOVER_PLAN.md) and
[interoperability plan](SALESFORCE_ADOBE_INTEROP_PLAN.md). It introduces no second
runtime or readiness engine. The historical public-source context is not reverified
by running this example.

## What the example proves

Five expected records and five observed records are not necessarily the same five.
The synthetic target below omits one credential, adds an unrelated ID and changes
one applicant payload. The V2 compiler identifies all three differences despite
equal total counts. Verification accepts that HOLD receipt because its evidence is
internally consistent; verification is not a claim that the migration succeeded.

A separately constructed clean synthetic target produces a clean trial. Supplying
both trials as current still gives HOLD and names the failed receipt. Supplying
only the clean trial illustrates a deliberately selected new current collection;
it does not erase, repair or automatically supersede the failed trial. A real
operator must retain the prior generation and justify the selection separately.

A rejected and an accepted observation for one synthetic enrollment share the
same event idempotency key. Supplying both as current raises an explicit conflict,
showing why attempt history belongs in a separate ledger. This does not demonstrate
a remote system's idempotency, retry behavior or persistence.

The evidence-name digests in this example are **synthetic placeholders**, not the
hashes of actual requirement plans. Consequently its ready-for-prime-review state
only exercises the input contract. It is not a deliverable-completeness verdict.

## Reproduce in an existing authorized cloud checkout

These commands require the pinned published runtime package. A separate merge of
this Markdown does not place PR #15866's Python code on main or clear its execution
checks. Do not interpret a missing-module error from a documentation-only checkout
as a receipt verdict. Use an existing permitted cloud environment with the named
source; no owner-PC clone, installation, service credential or network call is
needed by the example itself.

Save the following block as `rehearse_delivery.py` in that repository root. It
checks the exact imported package/core Git blob identities before import, uses
explicit runtime conditions rather than removable assertions, and emits one
JSON result. Every business record and observation is invented.

```python
import hashlib
import json
from pathlib import Path

expected = {
    "revenue/aidt_ewds_workshare/core.py": "c8d5c8edf2f49fd92c9071ddb3ca7811a564e718",
    "revenue/aidt_ewds_workshare/__init__.py": "3dd0b1ab6f91164b4c094a18ca86e068cd5466e4",
}
for name, identity in expected.items():
    raw = Path(name).read_bytes()
    actual = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
    if actual != identity:
        raise SystemExit("Different runtime generation: " + name)

from revenue.aidt_ewds_workshare.core import (
    REQUIRED_WORKSHARE_EVIDENCE, WorkshareError, compile_readiness,
    compile_sync_receipt, reconcile_migration,
    verify_migration_receipt, verify_readiness,
)

def h(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()

def row(identity, value):
    return {"record_id": identity, "record_sha256": h(value)}

source = [
    row("applicant-001", "expected-applicant-001"),
    row("applicant-002", "expected-applicant-002"),
    row("class-101", "expected-class-101"),
    row("enrollment-001", "expected-enrollment-001"),
    row("credential-001", "expected-credential-001"),
]
trial_target = [source[0], row("applicant-002", "different"), source[2],
                source[3], row("unexpected-999", "unexpected")]
failed_trial = reconcile_migration(source, trial_target)
# This is a newly supplied synthetic target, not a write to any live target.
clean_trial = reconcile_migration(source, source)
event = {"source_system": "salesforce", "target_system": "adobe_lms",
         "event_id": "synthetic-enroll-001", "entity_ref": "applicant-001",
         "operation": "enroll", "payload_sha256": h("synthetic-enrollment-v1")}
observation = {"accepted": True, "target_ref": "synthetic-target-001",
               "target_payload_sha256": h("synthetic-enrollment-v1")}
accepted = compile_sync_receipt(event, observation)
rejected = compile_sync_receipt(event, dict(observation, accepted=False))
# Placeholders exercise only the evidence-name/digest schema, not real documents.
evidence = {key: h("synthetic-placeholder:" + key)
            for key in REQUIRED_WORKSHARE_EVIDENCE}
mixed_current = compile_readiness(evidence, [clean_trial, failed_trial], [accepted])
clean_current = compile_readiness(evidence, [clean_trial], [accepted])
try:
    compile_readiness(evidence, [clean_trial], [rejected, accepted])
except WorkshareError as exc:
    history_as_current_error = str(exc)
else:
    raise SystemExit("Conflicting current event observations were accepted")

# Real checks run under both normal and optimized Python: no assert statements.
checks = [
    verify_migration_receipt(failed_trial), verify_migration_receipt(clean_trial),
    verify_readiness(mixed_current), verify_readiness(clean_current),
    failed_trial["source_count"] == failed_trial["target_count"] == 5,
    failed_trial["missing_record_ids"] == ["credential-001"],
    failed_trial["extra_record_ids"] == ["unexpected-999"],
    failed_trial["mismatched_record_ids"] == ["applicant-002"],
    mixed_current["state"] == "HOLD_WORKSHARE_INCOMPLETE",
    clean_current["state"] == "WORKSHARE_READY_FOR_PRIME_REVIEW",
    rejected["idempotency_key"] == accepted["idempotency_key"],
    history_as_current_error == "syncs: conflicting current observations for one event",
]
if not all(checks):
    raise SystemExit("Synthetic rehearsal contract failed")
result = {
    "scope": "SYNTHETIC_MANIFESTS_AND_OBSERVATIONS_NO_TRANSPORT",
    "equal_counts": [failed_trial["source_count"], failed_trial["target_count"]],
    "missing": failed_trial["missing_record_ids"],
    "extra": failed_trial["extra_record_ids"],
    "mismatched": failed_trial["mismatched_record_ids"],
    "failed_trial_verified": verify_migration_receipt(failed_trial),
    "failed_trial_receipt": failed_trial["receipt_sha256"],
    "clean_trial_receipt": clean_trial["receipt_sha256"],
    "mixed_current_state": mixed_current["state"],
    "mixed_current_blockers": mixed_current["blocking_migration_receipts"],
    "clean_current_state": clean_current["state"],
    "clean_current_receipt": clean_current["receipt_sha256"],
    "same_event_idempotency_key": accepted["idempotency_key"],
    "history_as_current_error": history_as_current_error,
    "source_authenticity_established": False,
    "project_completeness_established": False,
    "external_authority": {key: clean_current[key] for key in clean_current
                           if key.endswith("_authorized")},
}
print(json.dumps(result, sort_keys=True, indent=2))
```

Run the same actual computation twice:

```sh
python rehearse_delivery.py > delivery-normal.json
python -O rehearse_delivery.py > delivery-optimized.json
cmp delivery-normal.json delivery-optimized.json
sha256sum delivery-normal.json
```

Use new output paths or a fresh temporary working directory to preserve prior
artifacts; shell `>` itself overwrites an existing file. The package CLI's separate
`--out` option is create-only, but that does not change shell redirection semantics.

## Actual output, September 19, 2026

The documented block was executed in an isolated Linux cloud sandbox using
Python 3.13.5 and the exact published package bytes. Both commands returned zero;
normal and optimized JSON were byte-identical. Output SHA-256:

`5cd77d75ca8611ed4dbcf236e7599e47ebd35d85bfc6641b0d16f3dd6c1e6a5f`

```json
{
  "clean_current_receipt": "f9b645ce9fd2b199b92609f27208ecfc2cdc01f853159ee414d69fcd2baafe94",
  "clean_current_state": "WORKSHARE_READY_FOR_PRIME_REVIEW",
  "clean_trial_receipt": "0b859f465ad6852aa5b4489201e702be9823b3d47b806e85d6f9ca90e5d51c16",
  "equal_counts": [
    5,
    5
  ],
  "external_authority": {
    "award_claim_authorized": false,
    "buyer_acceptance_claim_authorized": false,
    "external_outbound_authorized": false,
    "payment_claim_authorized": false,
    "proposal_submission_authorized": false,
    "revenue_claim_authorized": false
  },
  "extra": [
    "unexpected-999"
  ],
  "failed_trial_receipt": "edc85f7fbc4cb9ed00f15977a8c8663abf4cc5a3cb2bc7f74cc17aecc6c966a9",
  "failed_trial_verified": true,
  "history_as_current_error": "syncs: conflicting current observations for one event",
  "mismatched": [
    "applicant-002"
  ],
  "missing": [
    "credential-001"
  ],
  "mixed_current_blockers": [
    "edc85f7fbc4cb9ed00f15977a8c8663abf4cc5a3cb2bc7f74cc17aecc6c966a9"
  ],
  "mixed_current_state": "HOLD_WORKSHARE_INCOMPLETE",
  "project_completeness_established": false,
  "same_event_idempotency_key": "330b3b040862e46e14fec29f20e71954b8ef285763573e3feb25b01f9f0b7099",
  "scope": "SYNTHETIC_MANIFESTS_AND_OBSERVATIONS_NO_TRANSPORT",
  "source_authenticity_established": false
}
```

## How a delivery reviewer should read it

The missing credential, extra ID and altered applicant are actionable differences,
not three names for a count mismatch. Preserve the original exports and inspect
the expected/observed projections to locate extraction, mapping, import or readback
faults. The synthetic example does not identify a fault in any real system.

`failed_trial_verified=true` is correct: the negative evidence has not contradicted
its own manifests. A verifier that refused every negative result would make the
exception ledger unusable. The corresponding decision remains HOLD.

The mixed current collection's blocker points to the failed trial digest. The
clean collection is a different input scope, not evidence that the failed trial
never occurred. Record an externally justified supersession decision and retain
both trial histories before representing one generation as current in real work.

The event conflict names an ordering question this compiler does not answer:
which observation is current? No timestamp is guessed, and a success is not given
priority merely because it is convenient. A real adapter requires a documented
ordering and independent target reconciliation rule.

Every listed external authority remains false. The compiler additionally retains
false prime-qualification and registration flags. Neither full project coverage
nor external source authenticity is established. No source export, target write,
transport, network lookup, appointment, proposal or buyer acceptance took place.

The broader runtime regression suite has its own
[source-bound 53-normal/53-optimized record](https://github.com/woahwhattheheck/commons/blob/81a9ace9e033bc5b7c841eff8efd6117725c789f/revenue/aidt_ewds_workshare/RECOVERY_PROOF.json).
This smaller worked example is additional operator evidence, not a replacement for
those tests, independent review, provider execution or a live acceptance process.
