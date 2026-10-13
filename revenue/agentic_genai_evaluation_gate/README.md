# Agentic GenAI Evaluation Evidence Gate

A deterministic, read-only pre-release evidence control for agentic GenAI
systems. It compiles a closed-schema evaluation portfolio into one canonical
`RELEASE_CANDIDATE` or `HOLD` receipt and can later verify both:

1. whether the historical receipt still matches the exact packet and compile
   instant; and
2. whether that same evidence remains fit **now** under its freshness policy.

The second check is intentionally separate. A byte-perfect historical release
receipt can have `integrity_valid: true` while returning `valid: false`,
`current_valid: false`, and `CURRENT_EVIDENCE_HOLD` after its evidence expires.

This module does not deploy a model, execute a tool, access customer data, send
a message, or make a financial, insurance, compliance, or production-release
decision.

## Bound evidence

Schema version 2 binds:

- exact evaluation-set ID, generation, digest, and required scenario universe;
- exact agent ID/version/build digest;
- exact rubric ID/generation/digest and minimum score;
- scenario category, trace digest, result digest, and evidence time;
- an automated-result object binding scenario identity, score, status,
  evaluator digest, build, rubric, trace, and result generation;
- human review binding scenario identity, decision, build, rubric, trace, and
  result generation;
- safety evidence binding scenario identity, build, trace, and result generation;
- observability evidence binding scenario identity, trace, and result generation;
- every tool-call observation binding scenario identity, trace, and result
  generation;
- verifier-owned compile and verification instants;
- canonical packet and self-verifying receipt digests.

A fresh compile therefore rejects a transplanted or arbitrary
`result_sha256` unless every evidence layer that interprets that result names
the same digest. This is a consistency guarantee, not proof that the
caller-supplied digest came from an independently authenticated producer.

Unknown fields, bool/int aliasing, floating-point basis-point scores,
non-canonical timestamps, duplicate IDs, missing scenarios, future/stale
evidence, cross-build/rubric/trace/result bindings, unsafe or unknown outcomes,
and receipt drift fail closed.

## Decision semantics

`RELEASE_CANDIDATE` means only that the supplied evidence satisfies the declared
policy at the receipt's verifier-owned instant. It is not production release
authority.

`verify_receipt()` first reconstructs the historical receipt at its claimed
instant. Only an exact canonical match has `integrity_valid: true`. It then
recompiles at `verified_at`. Current-use `valid` is true only when both the
historical and current decisions are `RELEASE_CANDIDATE`; a historical `HOLD`
never silently promotes without a new receipt.

Stable reason codes include:

- `SCENARIO_UNIVERSE_MISMATCH`
- `SCENARIO_BINDING_MISMATCH`
- `AGENT_BUILD_MISMATCH`
- `RUBRIC_MISMATCH`
- `TRACE_BINDING_MISMATCH`
- `RESULT_BINDING_MISMATCH`
- `FUTURE_EVIDENCE`
- `STALE_EVIDENCE`
- `AUTOMATED_SCORE_BELOW_THRESHOLD`
- `AUTOMATED_EVALUATION_FAILED`
- `HUMAN_REVIEW_MISSING` / `HUMAN_REVIEW_FAILED`
- `SAFETY_UNKNOWN` / `SAFETY_FAILED`
- `OBSERVABILITY_INCOMPLETE`
- `TOOL_RESULT_UNKNOWN` / `TOOL_RESULT_FAILED`

Malformed schema is rejected rather than interpreted.

## Strict file custody

The CLI's JSON ingress:

- opens with no-follow semantics where supported;
- requires a regular file bounded to 8 MiB;
- reads twice through one retained descriptor;
- requires stable device, inode, mode, size, mtime, and ctime across both reads;
- requires the two byte sequences to match;
- decodes strict UTF-8 and rejects non-finite constants;
- rejects duplicate object keys at every nesting level.

Publication is intentionally single-output. The CLI rejects attempts to publish
multiple artifacts in one command, so a failed invocation cannot truthfully look
atomic while leaving a durable subset behind. Each artifact is written to an
anonymous `O_TMPFILE` inode through a retained read/write descriptor, fsynced,
and read back byte-for-byte while its link count is zero. One hard-link operation
is the namespace commit. A destination that appears after preflight wins without
exposing the caller payload.

After commit, the gate requires one visible hard link, exact retained-descriptor
bytes, stable mode/device/inode/size/mtime/ctime/link count, and an unchanged
lexical parent plus basename. Symlinked parent components and occupied or
symlink final names are rejected. Failure never triggers pathname rollback, so
an unowned replacement is not deleted.

Output parent directories must already exist. A host without Linux-style
`O_TMPFILE`, `/proc/self/fd`, and descriptor-relative `O_DIRECTORY` /
`O_NOFOLLOW` / `link` support fails closed.

## Synthetic acceptance portfolio

`golden.py` deterministically generates 180 synthetic scenarios:

- 45 normal;
- 45 tool-using;
- 45 adversarial;
- 45 degraded-observability challenge cases whose retained observations remain
  complete.

The fixture contains no buyer or production data.

## CLI

Compile one receipt using host current UTC:

```bash
python -m revenue.agentic_genai_evaluation_gate.cli compile \
  evaluation.json receipt.json
```

Render that receipt in a separate, single-output transaction:

```bash
python -m revenue.agentic_genai_evaluation_gate.cli render \
  receipt.json receipt.md
```

`compile --markdown-out ...` is rejected before publication. This is a deliberate
v2 contract change: no command claims an all-or-nothing multi-output transaction.
Schema-v1 packets are likewise rejected rather than silently reinterpreted;
callers must regenerate their portfolio under the v2 evidence bindings.

Verify historical integrity and current fitness:

```bash
python -m revenue.agentic_genai_evaluation_gate.cli verify \
  evaluation.json receipt.json
```

Exit codes are `0` for current release validity, `2` for a compiled `HOLD`, `3`
for a receipt that is not currently valid, and `4` for malformed evidence or
file-custody failure.

## Test contract

```bash
python -m py_compile \
  revenue/agentic_genai_evaluation_gate/*.py \
  tests/_agentic_gate_*.py \
  tests/test_agentic_genai_evaluation_gate.py
python -m unittest -v tests.test_agentic_genai_evaluation_gate
python -O -m unittest -v tests.test_agentic_genai_evaluation_gate
```

The focused hostile suite covers current-time expiry, historical HOLD
non-promotion (including future-evidence HOLDs after time catches up),
whole-object scenario transplantation, every result-binding layer, global
review/tool ID uniqueness, cross-build/rubric/trace evidence, duplicate-key JSON,
same-inode input rewrite with restored mtime, bounded/no-follow ingress,
private-inode staging, late destination occupation, same-size output mutation,
foreign hard links, parent/final-name replacement, short-write draining,
single-output enforcement, deterministic ordering, receipt tamper, and the
authority ceiling.

## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)
