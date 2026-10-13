# Security Questionnaire Desk

`Security Questionnaire Desk` is an **offline fulfillment compiler** for the existing Commons human-outcomes candidate `ho-security-questionnaire` ($3,000 / 10 calendar days in the current catalog). It does not promote that candidate, publish a checkout, contact a buyer, or claim demand. It makes the fulfillment promise mechanically safer: every required questionnaire row is represented as an evidence-linked proposed answer, `UNMEASURED`, `OWNER_INPUT_REQUIRED`, or `HOLD`, with exact question/evidence/answer lineage and an explicit owner-review boundary.

The strongest product state emitted by this compiler is `EVIDENCE_LINKED_PROPOSED_ANSWER`, and the packet remains `READY_FOR_OWNER_REVIEW`. That state means caller-supplied evidence is content-bound to one exact question/answer generation. It does **not** authenticate the evidence source, infer owner approval, or authorize return to a buyer. Candidate `owner_dispositions` supplied in input are retained only as committed context and are deliberately ignored as authority. This product does not create a certification, compliance determination, security audit, legal conclusion, buyer acceptance, provider state, payment, or recognized revenue.

## Contract

The compiler accepts one strict JSON object containing:

- one opaque questionnaire identity, source ref, and SHA-256;
- exact question rows (`BOOLEAN`, `TEXT`, `ENUM`, or `MULTI`) with immutable source refs/digests and an explicit `GENERAL` or `CERTIFICATION` assurance kind;
- an evidence library with immutable evidence IDs, an explicit supported question ID plus exact question source-row SHA-256, `supports_answer_sha256`, claim key/value, statement, evidence kind, `PUBLIC` / `NON_PUBLIC` disclosure, source ref/digest, capture time, and freshness window;
- exactly one proposed answer per question; and
- optional candidate owner dispositions, which are committed into lineage but never become owner authority.

An `EVIDENCE_LINKED_PROPOSED_ANSWER` requires current cited evidence scoped to the exact question ID, exact question source-row SHA-256, and exact proposed-answer binding. Missing or mismatched answer binding forces `HOLD`. Evidence with the same claim key but conflicting values makes the answer `HOLD`. A `CERTIFICATION` question cannot be evidence-linked unless a current cited row is explicitly `CERTIFICATION_REFERENCE`; generic documentation cannot mint a certification claim. Future or stale evidence cannot support a measured answer.

The compiler does not claim that `supports_answer_sha256` proves the underlying security statement is true. It proves only that the supplied evidence row and proposed answer are content-bound to the same exact questionnaire generation. Source provenance remains unauthenticated.

`NON_PUBLIC` evidence may appear in the internal owner-review packet. If any cited evidence for a row is non-public, the generated `public-safe.json` degrades the entire row to generic `UNMEASURED`, strips the private answer/evidence IDs/claim keys/statements, and emits aggregate status `PUBLIC_OWNER_REVIEW_REQUIRED`. The public-safe artifact is not a buyer-send action; it is only a leak-resistant projection.

## Production commands

```bash
python revenue/security_questionnaire_desk/security_questionnaire_desk.py compile \
  revenue/security_questionnaire_desk/example_input.json \
  /tmp/security-questionnaire-output
```

Production compile takes **current process UTC itself**. There is deliberately no `--as-of` argument that can backdate stale evidence. Compilation publishes five create-exclusive files into a new or empty ordinary directory:

- `packet.json` — canonical internal owner-review packet;
- `review.md` — human-readable review material;
- `answers.csv` — deterministic answer matrix;
- `public-safe.json` — non-public-dependent rows degraded and stripped;
- `receipt.sha256` — packet receipt.

Publication is descriptor-retained and fail-closed. The output path is component-walked with `O_NOFOLLOW`; the admitted directory descriptor is retained for the complete transaction; every file is created relative to that directory with `O_EXCL`; files and the directory are fsynced; and before returning success the compiler reopens the caller-visible path without creating anything and proves that it still names the admitted directory generation and that every visible artifact still names the exact file generation created by this call. If the visible directory or a created file is replaced/detached during publication, the call fails instead of returning stale or misleading pathnames. Already-written bytes are not deleted by pathname during failure because a concurrent actor may have replaced the visible names.

Verification replays the packet at its bound compile time, then uses **fresh current process UTC** to ensure evidence supporting measured answers has not expired:

```bash
python revenue/security_questionnaire_desk/security_questionnaire_desk.py verify \
  revenue/security_questionnaire_desk/example_input.json \
  /tmp/security-questionnaire-output/packet.json
```

A packet therefore remains verifiable while its exact supporting evidence is current and fails closed after support expiry or any source/question/answer/receipt drift.

## Input safety

Input is strict UTF-8 JSON with duplicate-key rejection, no floats/non-finite values, bounded integers/arrays/text, exact-key schemas, canonical whole-second UTC, lowercase SHA-256, and obvious direct-contact PII / secret-shaped durable material rejection. Parsed-object entry points accept only exact plain JSON types before snapshotting, rejecting tuples, dict subclasses, `IntEnum`, floats, and coercive aliases. Files are read through one bounded regular-file descriptor generation with symlink and pathname-replacement fences.

Outputs are create-exclusive. Existing files and final symlinks are refused. Output-ancestor symlinks are refused. Directory detachment, parent replacement, and created-file generation replacement cannot be reported as successful visible publication.

## Owner review boundary

Input may contain candidate dispositions such as `APPROVED_FOR_RETURN`, `REVISE`, or `REJECT`, but this open-door compiler does not authenticate who supplied them. They are committed into lineage only. Compiled rows force:

- `owner_disposition = null`;
- `owner_disposition_status = UNTRUSTED_CANDIDATE_CONTEXT_IGNORED`;
- `required_approved_for_return = 0`;
- `review_authority.candidate_dispositions_are_owner_authority = false`;
- `review_authority.owner_approval_inferred = false`;
- `review_authority.owner_action_required = true`.

Changing a question, answer, evidence bytes, or support binding changes the compiled generation, but generation binding is lineage, not authentication. The compiler intentionally adds no login, key, token, allowlist, permission gate, or protected owner action.

## Validation

Run the complete package suite in both ordinary and optimized Python, then compile the production modules:

```bash
python -m unittest discover -v revenue/security_questionnaire_desk 'test_*.py'
python -O -m unittest discover -v revenue/security_questionnaire_desk 'test_*.py'
python -m py_compile \
  revenue/security_questionnaire_desk/security_questionnaire_desk.py \
  revenue/security_questionnaire_desk/_engine.py \
  revenue/security_questionnaire_desk/_secure_input.py \
  revenue/security_questionnaire_desk/_secure_packet.py \
  revenue/security_questionnaire_desk/_secure_publish.py
```

Coverage includes deterministic replay/order invariance, cross-question and cross-answer evidence rejection, unsupported certification, stale/future/conflicting evidence, untrusted candidate-disposition handling, changed evidence/question input, packet receipt tamper, evidence expiry at verify time, duplicate JSON keys, Python object-alias traps, secret/PII-shaped material, whole-row private-evidence public-export stripping, create-exclusive publication, symlink refusal, descriptor-bound input, visible directory-generation detachment, created-file generation replacement, and absence of a caller-controlled production clock.

## Authority ceiling

This product has **no authority** to contact a buyer/customer, send a questionnaire, access a CRM/provider/account, run a security scanner, create a certification/compliance claim, sign a contract, publish/promote the catalog candidate, create checkout, charge/refund/move money, or recognize revenue. The existing candidate price/status are read-only catalog facts.
