# Reference Authority Registry

This offline revenue-control surface keeps **capability evidence** separate from **customer-reference authority**. A merged open-source fix, internal engineering artifact, paid review-program result, or procurement pursuit may be useful capability proof, but none of those facts creates a client engagement, permission to disclose a customer reference, or comparability to a buyer requirement.

The package therefore has two inputs with different trust levels. Candidate packets contain only public-safe opportunity, requirement, and capability-evidence data. Authority lives in a separately normalized registry authenticated with HMAC-SHA256 under the host-only `COMMONS_REFERENCE_AUTHORITY_HMAC_KEY_HEX` key. Candidate JSON cannot supply authority rows, select `CLIENT_ENGAGEMENT`, or carry the HMAC.

## Currentness is a host boundary

The v2 trust registry adds a signed integer `generation_sequence` alongside `generation_id` and `issued_at`. Historical results bind the exact authenticated registry digest, generation ID, and sequence.

Fresh `verify_current()` does **not** accept a current registry, a registry path, or a clock from its caller. It reacquires the owner-controlled current registry from the fixed deployment path:

```text
/var/lib/commons/reference-authority/current-authority-registry.json
```

The host must maintain that file as its authoritative latest pointer in a directory ordinary candidate callers cannot modify. On supported POSIX systems the verifier opens every directory component with `O_DIRECTORY|O_NOFOLLOW`, retains the directory descriptor chain, then opens and reads the regular-file leaf relative to the retained parent descriptor. The registry itself must still authenticate under the host HMAC key.

Current verification rejects:

- a current sequence lower than the historical sequence (rollback);
- a different authenticated registry at the same sequence (fork), including a different generation ID or body digest;
- reuse of the same generation ID at a newer sequence; and
- a newer sequence whose `issued_at` is not strictly later than the historical generation.

The fixed host store is the authority for **which** signed generation is current; HMAC alone proves authenticity, not latestness. Deployments must update the fixed store when authority is revoked or superseded. This is intentionally not configurable by candidate packet or ordinary CLI argument.

## Reference-ready contract

`REFERENCE_READY_FOR_OWNER_REVIEW` requires all of the following at verifier-observed current time:

- a host-authenticated current classification for the exact evidence generation;
- `CLIENT_ENGAGEMENT` classification with a stable trusted `engagement_id`;
- host-authenticated `PROPOSAL_CAPABILITY` disclosure authority bound to exact evidence and opportunity generations;
- host-authenticated reference permission bound to exact evidence, opportunity, and requirement generations; and
- separately host-authenticated `COMPARABLE` assessment for the same exact generations.

Distinct-reference counts use unique trusted `engagement_id` values, not evidence IDs. Multiple authenticated evidence aliases for one engagement can be reviewed but count once.

The output is evidence state only. Every external-action authority flag remains false: no customer/reference contact, disclosure, proposal submission, contracting, payment/accounting, or revenue-recognition authority is created.

## Historical vs current verification

`verify_historical(packet, historical_registry, result)` proves that a retained result exactly replays from the exact historical packet and authenticated authority generation at its recorded evaluation time. It is an integrity statement only; it does not claim that the historical authority is still current.

`verify_current(packet, historical_registry, result)` first proves that historical integrity, then reacquires the fixed host current registry and reevaluates using the process clock. The returned status is `VERIFIED_WITH_FRESH_HOST_TIME_REASSESSMENT` only after both the lineage fence and fresh reassessment succeed.

## Schemas

Candidate packet: `commons-reference-authority/v2`.

Authenticated trust registry: `commons-reference-authority-trust/v2`. In addition to authority rows it carries `generation_id`, positive integer `generation_sequence`, `issued_at`, and an HMAC over the canonical normalized registry body.

Result: `commons-reference-authority-result/v3`; receipt: `commons-reference-authority-receipt/v3`. The result binds exact packet SHA-256, exact registry SHA-256, generation ID, and generation sequence.

Changing opportunity or requirement semantics under a stable ID invalidates prior authority because disclosure/permission/comparability records commit the canonical opportunity/requirement digests. Registry normalization also rejects a stable `engagement_id` being classified as conflicting engagement kinds.

## CLI

Compile a review result from a packet and one authenticated authority generation:

```bash
COMMONS_REFERENCE_AUTHORITY_HMAC_KEY_HEX=<host-secret-hex> \
python revenue/reference_authority/reference_authority.py compile \
  packet.json historical-authority-registry.json \
  --json-out review.json --markdown-out review.md
```

Fresh current verification has no current-registry argument. The host must have installed the latest authenticated generation at the fixed store path:

```bash
COMMONS_REFERENCE_AUTHORITY_HMAC_KEY_HEX=<host-secret-hex> \
python revenue/reference_authority/reference_authority.py verify \
  packet.json historical-authority-registry.json review.json
```

Historical-only integrity remains explicit:

```bash
COMMONS_REFERENCE_AUTHORITY_HMAC_KEY_HEX=<host-secret-hex> \
python revenue/reference_authority/reference_authority.py verify-historical \
  packet.json historical-authority-registry.json review.json
```

There is deliberately no `--current-authority-registry` escape hatch and no fallback that silently treats the historical generation as current.

## Fail-closed boundaries

The implementation rejects or HOLDs, as appropriate: missing/invalid host key or registry MAC; signed-registry rollback/fork; candidate authority injection; caller-selected engagement kind; stable-ID semantic replay; evidence/opportunity/requirement digest mismatch; renamed aliases without trusted classification; alias count inflation; conflicting engagement classification; expiry/revocation/future authority; duplicate JSON keys/IDs; non-finite numbers; bool-as-int integers; public contact/secret/path-shaped data; non-regular or changed-during-read files; fixed-store symlinks; result substitution/tamper; existing output destinations; and any attempted external-action authority escalation.

This package is a review/evidence control. It does not contact customers, request permission, store customer PII, submit proposals, sign contracts, mutate providers, move money, or book revenue.
