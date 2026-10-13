# Atomic Organization Outbound Lease

This package closes one coordination race: two workers can target **different people or routes at the same organization** and therefore both win narrower per-prospect/per-destination locks. The organization outbound lease introduces one atomic organization-level writer before any provider send authority is approached.

It composes with, rather than replaces, the organization contact-pressure gate, per-prospect/contact CAS controls, outbound destination mutexes, opportunity/initial-outreach guards, and the terminal provider-send consumer.

## Authority boundary

Version 2 separates **pressure-attestation signing** from **acquire verification**, and the supported production acquire path pins verifier identity outside claimant control.

The pressure host signs a canonical `commons.organization-pressure-attestation/v2` body with an RSA private key that does **not** enter this package or the claimant process. Acquire verifies an exact PKCS#1 v1.5 SHA-256 signature under a domain-separated message using the public key loaded from exactly:

`/etc/tokenjunkielabs/organization-pressure-rsa-public.json`

There is no CLI or environment override for that path, modulus, exponent, or key id. The parent directory and file must be root-owned, non-group/world-writable, non-symlinked, and stable across a retained-descriptor read; the file must also have exactly one hard link. If any custody check fails, acquire fails closed. Key rotation is a host deployment operation, not a claimant option.

The trust-root file is strict JSON with exactly:

```json
{
  "schema": "commons.organization-pressure-trust-root/v1",
  "algorithm": "RS256-PKCS1-v1_5",
  "keyId": "HOST-PINNED-KEY-ID",
  "modulusHex": "LOWER_CASE_RSA_MODULUS_HEX",
  "exponent": 65537
}
```

The package contains no private signing key and no signing helper. Caller-supplied verifier material survives only for deterministic local-reference tests, and that seam is mechanically bound to the unchanged `FileLeaseStore` acquisition call graph. A subclass/proxy/delegated store, an instance with rebound acquire methods, a later monkeypatch of the reference acquire implementation, or noncanonical local path state is rejected **before store I/O**. The production `GitHubContentsLeaseStore` and supported CLI never accept claimant-selected verifier identity.

The signed body binds:

- organization fingerprint;
- exact pressure-receipt SHA-256;
- authority-generation commitment;
- ledger-generation commitment;
- exact positive upstream state `READY_FOR_SINGLE_WRITER_REVIEW`; and
- verification time.

Acquire samples process UTC internally. New authority requires both request and pressure verification to be fresh within five minutes, with at most five seconds of future skew. An exact already-active replay may recover its existing lease after freshness expires because it creates no new authority.

## Privacy-safe organization identity

The organization fingerprint is HMAC-SHA256 over the host's independently retained canonical organization identity. Raw organization/contact identity never belongs in lease paths, receipts, branch names, or logs. Prospect, route, opportunity and authority inputs are commitments rather than raw labels.

## Private holder capability

Before acquire, the claimant generates a fresh **32-byte CSPRNG secret** and places only:

`sha256(b"holder-capability-v1\\0" + secret)`

in `holderCapabilityCommitment`.

The raw holder capability is never serialized in the active lease, outcome receipt, branch path, status output, or collision response. Every first-time terminal finalization and every exact terminal replay must present the raw 32-byte capability; core recomputes the commitment and compares it to the lease/outcome commitment.

This means another protocol writer can read the entire active organization lease and still cannot emit `SENT`, `REJECTED`, `HELD_AUTHORITY`, `OUTCOME_UNKNOWN`, or `UNSENT_RELEASED` for the winner. Losing the holder capability fails closed to explicit administrative reconciliation.

## GitHub atomicity

Production mode uses the GitHub Contents API on a dedicated coordination branch (default `outbound-lease-ledger`):

- acquire creates `active/<org-hmac>.json` **without** a prior SHA, so one organization path has one winner;
- immutable outcomes create `outcomes/<org-hmac>/<lease-id>.json` without a prior SHA;
- the only releasable terminal is `UNSENT_RELEASED`, and its outcome is committed **before** active deletion;
- release supplies the exact active blob SHA, so a stale deleter cannot remove a distinct successor generation;
- network/create/delete ambiguity is reconciled by authoritative read rather than blind mutation retry;
- time passage alone never expires an active lease.

The coordination branch must already exist and must be restricted to this protocol. This package never creates, force-updates, or resets it.

## Terminal and replay rules

A retained outcome is stronger than an active-byte match.

- `SENT`, `OUTCOME_UNKNOWN`, `REJECTED`, and `HELD_AUTHORITY` stay blocking and exact acquire replay returns `LEASE_FINALIZED_<OUTCOME>`, never `LEASE_ACQUIRED`.
- `UNSENT_RELEASED` removes the active lease only after its immutable outcome exists.
- Exact terminal replay remains idempotent after freshness expiry and after an unsent release removes the active file, but it still requires the private holder capability.
- An exact acquire identity that already has a retained outcome cannot be recreated. This prevents A -> release -> byte-identical A ABA reuse.
- A later legitimate acquire must have a genuinely new lease identity (normally a new request/claim and fresh holder capability). Replaying an old release cannot delete that successor because release compares the exact retained `leaseSha256` and holder capability commitment.

## Authority ceiling

A positive result means only **internal organization-lease ownership**. Every lease and outcome hard-codes `externalSendAuthorized=false`; every outcome also hard-codes `cashOrRevenueClaimed=false`. The package has no email/Slack/SMS/form sender and makes no buyer-response, payment, cash, booked-revenue, or recognized-revenue claim.

The mandatory provider-bound composition layer remains responsible for proving all downstream send authority. It must bind the exact winning organization fingerprint, `leaseId`, `leaseNonce`, `leaseSha256`, holder-capability commitment, and active store generation; the lease itself is never provider authority.

## CLI

```text
python -m revenue.organization_outbound_lease.cli fingerprint --organization-file canonical-org.txt
python -m revenue.organization_outbound_lease.cli acquire --input acquire.json --repository OWNER/REPO
python -m revenue.organization_outbound_lease.cli status --organization-fingerprint HEX --repository OWNER/REPO
python -m revenue.organization_outbound_lease.cli finalize --input outcome.json --repository OWNER/REPO
python -m revenue.organization_outbound_lease.cli release --input unsent-release.json --repository OWNER/REPO
python -m revenue.organization_outbound_lease.cli verify --input lease.json
```

Acquire has **no pressure-key selector**. The fixed host trust-root file supplies public verification material. Other secrets are read only from environment (`ORG_FINGERPRINT_KEY`, `ORG_LEASE_NONCE_KEY`, `GITHUB_TOKEN` by default). The private pressure-signing key is intentionally unsupported.

Finalize/release JSON contains the raw `holderCapability` only as an input capability. Treat that input as secret: create it with owner-only permissions, do not retain it in shared logs/artifacts, and destroy it according to the surrounding host policy after terminal reconciliation.

For deterministic local tests, `--store file --store-root DIR` uses a reference create-exclusive store. Unit tests may inject a verifier only while the store retains the mechanically unchanged local acquisition implementation. That seam rejects subclass/proxy delegation and instance method rebinding before I/O; it is not accepted by the production GitHub store and is not exposed by the CLI.