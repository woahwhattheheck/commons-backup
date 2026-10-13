# Outbound send pre-send forensics

This package audits **already-attempted external sends** against the connector-native
lease protocol in `revenue/outbound_connector_lease`. It is offline: it performs no
provider call, creates no Git ref, sends no message, and never turns a historical
violation into permission to retry.

Every audited record remains `dnr: true`.

## Authority model

The current authority-bearing schema is `outbound-send-forensics/v3`.

`v3` deliberately does **not** accept caller-selected strings such as
`provider-receipt` or `github-create-result` as proof. Positive factual conclusions
require HMAC-SHA256 attestations under the fixed, operator-provisioned host trust
root:

`/etc/commons/outbound-send-forensics/authority-key.json`

The production CLI has no key-path flag and no environment selector. The authority
path is an absolute code constant: `HOME`, `USERPROFILE`, XDG variables, cwd, and
other caller process environment do not choose or relocate it. On POSIX the key is
opened by descriptor-walking every path component with no-follow semantics; the
final object must be a regular file and must not be group/other accessible. Hosts
that have not provisioned the fixed root fail closed with `HOLD:` for current v3
authority. The exact key document is:

```json
{
  "schema": "outbound-send-forensics-authority-key/v1",
  "key_hex": "<64 lowercase hex>"
}
```

This package **verifies** attestations but intentionally exposes no command that
mints them. The upstream trusted adapter that observes the real provider/GitHub
receipt must validate that external receipt first and then attest the normalized
commitment. An arbitrary evidence claimant who controls only the record and process
environment cannot relocate the production verifier onto a claimant-selected key.
Deployment still relies on the normal host/service boundary: anyone who can read
the operator key can mint attestations and therefore belongs inside the trusted
adapter/verifier boundary, not the untrusted-evidence boundary.

The provider-send attestation commits to:

- schema/domain separator `outbound-send-forensics-authority-attestation/v1`;
- kind `provider-send`;
- the exact canonical seam SHA-256;
- provider + provider event ID;
- canonical SENT/ambiguous timestamp and status; and
- the exact retained provider receipt SHA-256.

Binding the seam digest prevents a genuine provider receipt from being transplanted
to another buyer/opportunity seam.

The GitHub-create attestation commits to:

- the same attestation schema/domain separator;
- kind `github-branch-create`;
- normalized repository identity;
- exact connector-lease branch;
- canonical create timestamp + result;
- exact base commit; and
- exact retained GitHub receipt SHA-256.

## Current `v3` evidence

A provider-send row is exact-field:

```json
{
  "provider": "gmail",
  "event_id": "provider-message-id",
  "sent_at": "2026-09-14T01:20:00Z",
  "status": "sent",
  "receipt_sha256": "<64 lowercase hex>",
  "attestation_hmac_sha256": "<64 lowercase hex>"
}
```

A lease-create row is `null` or exact-field:

```json
{
  "repository_full_name": "woahwhattheheck/commons",
  "branch": "outbound-connector-lease/v1/<64 lowercase hex>",
  "created_at": "2026-09-14T01:19:00Z",
  "result": "created",
  "base_sha": "<40 lowercase hex commit>",
  "receipt_sha256": "<64 lowercase hex>",
  "attestation_hmac_sha256": "<64 lowercase hex>"
}
```

The top-level document remains:

```json
{
  "schema": "outbound-send-forensics/v3",
  "records": [
    {
      "record_id": "case-1",
      "seam": {
        "schema": "outbound-connector-lease/v1",
        "buyer_scope": "example.com",
        "opportunity": {
          "kind": "external",
          "authority": "issuer.example",
          "id": "rfp-04254"
        }
      },
      "send": {},
      "lease_create": {}
    }
  ]
}
```

## Compatibility / migration

`outbound-send-forensics/v1` and `outbound-send-forensics/v2` remain readable for
historical reconstruction, but they are **claim-only inputs**. Their old
`authority="provider-receipt"` / `authority="github-create-result"` strings are
parsed as historical labels and never become authenticated authority. Therefore
v1/v2 cannot emit `PROTECTED_PRE_SEND`, `POST_SEND_LEASE_VIOLATION`,
`MISSING_LEASE`, `SEAM_MISMATCH`, or factual duplicate-send incidents from those
labels alone; the records remain `AMBIGUOUS_UNTRUSTED_EVIDENCE`/DNR.

Likewise, `audit_document()` / `audit_json()` are intentionally historical,
non-authoritative library entry points. They never load the host secret.
`audit_current_document()` / `audit_current_json()` and the CLI use the fixed host
trust root for v3.

This separation means a caller cannot create a custom HMAC key, hand it to the
public current-use API, redirect `HOME` to that key, and promote its own JSON to
provider/GitHub authority.

## Classifications

With valid current v3 host attestations:

- `PROTECTED_PRE_SEND`: the canonical Commons branch-create is host-attested,
  matches the exact seam, and is strictly earlier than a host-attested provider
  SENT event.
- `POST_SEND_LEASE_VIOLATION`: both facts are host-attested, but the create is
  equal to or later than the provider SENT event.
- `MISSING_LEASE`: a host-attested provider SENT event exists and no lease-create
  evidence was supplied.
- `SEAM_MISMATCH`: host-attested GitHub create evidence proves a different
  connector-lease branch.
- `AMBIGUOUS_UNTRUSTED_EVIDENCE`: missing/invalid host attestation, non-created
  lease result, noncanonical repository, ambiguous send, or legacy claim-only
  evidence.

Only host-attested provider `status="sent"` rows participate in factual
`DUPLICATE_SEND_SAME_SEAM` incidents. A caller-asserted, forged-MAC, ambiguous,
legacy-v1, or legacy-v2 row remains individually auditable/DNR but cannot create,
inflate, or contaminate a duplicate-send incident.

## Canonical repository / chronology

Only `woahwhattheheck/commons` may support positive pre-send protection. A valid
attestation for the same branch name in a fork is still noncanonical and therefore
untrusted for the Commons mutex.

Repository identity is normalized case-insensitively as `owner/repo`. Exact branch,
receipt digest, base commit, timestamp, result, and repository identity are covered
by the lease attestation. The provider attestation covers the seam, provider,
event, timestamp, status, and exact retained receipt digest.

Create time must be strictly earlier than provider SENT time for
`PROTECTED_PRE_SEND`.

## Deterministic receipts

Per-record receipts use `outbound-send-forensics-receipt/v3` and include:

- source input schema;
- canonical seam/repository/branch identities;
- exact provider + lease receipt digests;
- `send_authority_authenticated`;
- `lease_authority_authenticated`;
- classification/reasons;
- DNR state; and
- duplicate-incident flags/count.

All fields are sealed by `receipt_sha256`. Batch output is input-order independent
and sealed by `batch_sha256`.

The receipt digest proves what this verifier concluded from its inputs. It is not a
replacement for the fixed host trust root or the retained external receipts.

## Run / validation

Current CLI:

```bash
python -m revenue.outbound_send_forensics.audit evidence.json --pretty
```

The CLI uses the fixed `/etc/commons/outbound-send-forensics/authority-key.json`
root only for v3. It has no key override switch or environment-selected authority
path.

Focused validation:

```bash
python -m py_compile \
  revenue/outbound_send_forensics/audit.py \
  revenue/outbound_send_forensics/test_audit.py \
  revenue/outbound_send_forensics/test_authority_root.py

python -m unittest -v \
  revenue.outbound_send_forensics.test_audit \
  revenue.outbound_send_forensics.test_authority_root

python -O -m unittest -v \
  revenue.outbound_send_forensics.test_audit \
  revenue.outbound_send_forensics.test_authority_root
```

Exit `0` means structurally audited. It never means "safe to send." Invalid input
or missing/unsafe v3 host-key custody exits `2` with `HOLD:`.

The hostile suites cover self-asserted authority labels, forged attestations,
send-generation and cross-seam transplant, lease-generation transplant, canonical
vs fork repository identity, chronology, malformed top-level schema types,
duplicate-event/incident injection, strict JSON/time/hash/type boundaries,
fixed-key permissions/symlinks, alternate-`HOME` trust-root relocation, seam
normalization, and deterministic receipts.

The consolidated Commons root battery bridge `test_outbound_send_forensics.py`
enrolls both hostile suites without adding another active workflow. The earlier
exact-head focused workflow proved the same production/test blobs in both normal
and optimized Python; current integration deliberately uses the retained shared
battery instead of a product-specific workflow.

## Authority ceiling

No provider send, buyer/customer contact, Git ref creation, retry, payment,
contract, spend, booked-revenue, or recognized-revenue authority is granted or
performed by this package.