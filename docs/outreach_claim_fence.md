# Outreach claim fence v2

`outreach_claim_fence` is a **supplemental contact-level deduplication gate** for preventing concurrent workers from contacting the same person/endpoint seconds apart. It does **not** send mail/messages, choose recipients, authorize provider/customer/account mutation, move funds, prove revenue, or replace the landed organization-wide and opportunity/reply coordination controls.

## Composition with the landed outbound stack

Before any externally visible send, follow `.agents/skills/outbound-send/SKILL.md` and its fixed order. This package adds a contact-level seam inside that larger protocol; it is never the sole production mutex.

The safe composition is:

1. resolve authoritative organization scope;
2. acquire the current landed organization-wide atomic lease/control when required;
3. independently prove host rollback protection and acquire the canonical protected opportunity/reply seam;
4. acquire/arm this contact-level fence for the exact endpoint;
5. re-read provider truth and satisfy every independent owner/content/legal/route/cooldown/payment gate;
6. only when all those gates are green, consume this fence's one-time dispatch capability (`dispatch`) immediately before the provider side effect;
7. perform at most one provider send;
8. persist confirmed provider acceptance with `contacted`, or leave `OUTCOME_UNKNOWN` in force and reconcile provider history without retrying.

If any prerequisite fails, follow the authoritative outer lease/seam release contract and do not improvise lock order. A success receipt from this package is not `external_send_authorized`.

## Canonical authority

The package's own coordination namespace is code-pinned to one generation:

- API origin: `https://api.github.com`
- repository: `woahwhattheheck/commons`
- branch: `coordination/outreach-claims-v2`
- root: `.coordination/outreach-claims/v2`
- authority generation: `outreach-claims-v2/2026-09-14`

The CLI exposes no repository/branch/root/API override. Direct API callers that supply a different namespace fail closed. Every stored record and success receipt binds the complete authority identity plus a SHA-256 authority-policy digest.

This namespace pinning prevents callers from inventing alternate contact-fence universes. It does **not** make this package a substitute for the independently protected connector branch required by the canonical opportunity/reply layer.

The default HTTP transport accepts only canonical HTTPS GitHub API URLs and refuses redirects rather than forwarding bearer credentials to a redirect target.

## Safe contact-fence protocol

The state machine is deliberately asymmetric around the external side effect:

1. `acquire` — atomically reserve the normalized contact after the outer organization/opportunity seams are already held.
2. `arm` — bind the exact message digest, channel, and concrete compensation path. This returns a one-time plaintext dispatch token; only its digest is stored. ARMED is still not permission to send.
3. Complete provider readback and every independent send gate required by the landed outbound policy.
4. `dispatch` — CAS the exact ARMED generation to `OUTCOME_UNKNOWN` using that token. **Do this only after all other gates pass and immediately before calling the external provider.** A successful dispatch receipt means only that the ambiguity fence is durable; it is not evidence the provider send happened and is not send authority by itself.
5. perform at most one provider send using the already-bound message/channel.
6. on confirmed provider acceptance, `contacted` records digest-only contact evidence and a monotonic re-contact suppression window.
7. if the provider result is missing/ambiguous, do **not** release, reacquire, or retry. `OUTCOME_UNKNOWN` blocks reassignment indefinitely, even after ownership time expires.
8. only provider-history evidence signed by a separately controlled reconciliation key can execute `reconcile-unsent` for the exact unknown record generation. That transition proves the coordination layer received a trusted `UNSENT` attestation; it does not itself query a provider.

This closes the crash-after-send gap: time alone never turns an ambiguous external effect into new send authority.

## Lifecycle invariants

- `ACTIVE`: owned contact reservation, no dispatch commitment.
- `ARMED`: exact message/channel/payment path committed; still insufficient to send.
- `OUTCOME_UNKNOWN`: dispatch capability consumed; blocks reassignment indefinitely until confirmed contact or signed `UNSENT` reconciliation.
- `CONTACTED`: confirmed contact history plus `contact_not_before` suppression.
- `RELEASED`: contact-fence ownership ended; any existing `contact_not_before` suppression remains authoritative to this layer.

`renew` is monotonic and cannot shorten ownership. Contact suppression is stored separately from ownership and cannot be shortened by `renew` or `release`. A stale ARMED reservation may be taken over after ownership expiry because no dispatch capability was consumed; a stale OUTCOME_UNKNOWN reservation may not.

## Privacy and evidence

Raw contact values are used only to derive the deterministic claim key and masked hint. Records store digests, masked hints, ownership, lifecycle state, and paid-path metadata. Message files are hashed through a bounded descriptor read: final symlinks/non-regular inputs are rejected where the platform exposes `O_NOFOLLOW`, size is capped, and descriptor identity/size/timestamps must remain stable across the read.

Compensation paths must contain a concrete paid signal (amount, bounty, paid proposal, contract, invoice, fee, bid/award, etc.). This is an intent/path requirement, not proof of payment.

## CLI

```bash
python -m outreach_claim_fence key --kind email --contact lead@example.com

python -m outreach_claim_fence acquire \
  --kind email --contact lead@example.com \
  --agent-id Z-Tungsten --operation-id OP-123 \
  --opportunity '$1500 paid discovery' --lease-seconds 3600

python -m outreach_claim_fence arm \
  --kind email --contact lead@example.com \
  --agent-id Z-Tungsten --operation-id OP-123 \
  --message-file /path/to/exact-message.txt \
  --channel email --compensation-path '$1500 paid discovery'

# After all outer seams + provider/readback/policy gates pass, consume the token:
python -m outreach_claim_fence dispatch \
  --kind email --contact lead@example.com \
  --agent-id Z-Tungsten --operation-id OP-123 \
  --dispatch-token '<one-time token>'

# Only after the dispatch CAS succeeded may the caller attempt the one provider send.
# If provider acceptance is confirmed:
python -m outreach_claim_fence contacted \
  --kind email --contact lead@example.com \
  --agent-id Z-Tungsten --operation-id OP-123 \
  --message-file /path/to/exact-message.txt \
  --channel email --compensation-path '$1500 paid discovery' \
  --cooldown-seconds 259200
```

`GITHUB_TOKEN` is required for remote operations. `reconcile-unsent` additionally requires `OUTREACH_RECONCILIATION_KEY` (minimum 32 bytes) and an exact provider-history digest/signature produced by the trusted reconciliation authority. Ordinary workers should not possess that key.

## Tests

```bash
python -m py_compile outreach_claim_fence/*.py test_outreach_claim_fence.py
python -m unittest -q test_outreach_claim_fence.py
python -O -m unittest -q test_outreach_claim_fence.py
```

The 42-test suite covers canonical namespace pinning, token-origin and redirect fences, authority-bound receipts, normalization, CAS contention, server-time fail-closed behavior, one-time dispatch generation, crash/ambiguity blocking, contact confirmation, CONTACTED release suppression, ACTIVE and CONTACTED renewal monotonicity, contact-history takeover, signed exact-generation UNSENT reconciliation, record/authority tamper, privacy, bounded descriptor file hashing, symlink rejection, and CLI namespace-override rejection.

## Scope ceiling

This is a **contact-level supplemental gate**. Organization-wide exclusivity and canonical opportunity/reply protection are separate, authoritative outer layers and must compose ahead of it. A success receipt never grants provider/customer/account mutation authority; the caller must still satisfy the current landed outbound-send protocol and every external-send policy in force.
