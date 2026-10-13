# Trusted preflight authority — 920-45-269

Issues: `#13884`, `#13918`, `#13972`  
Current trust-boundary operation: `GRANDRAPIDS-PREFLIGHT-HOST-ROOT-SEPARATION-ZVAK6N8-20260913`

## Why this exists

`submission_state.json` is a proposal-working document, not a trust root. A state author must not be able to make the proposal READY by writing plausible evidence strings. Every state PASS is therefore a **claim** until trusted host integration resolves it against one separately authenticated current authority generation.

The authority boundary covers the exact solicitation, controlling packet digest, ordered addenda set, full canonical gate universe, typed evidence identities/digests, and an explicit `OWNER_RELEASE` record. Packet-local prose cannot create owner release.

## Trust-root separation

The package does **not** acquire a current authority root. It does not read authority generation/digest from process environment, proposal state, repository configuration, or public CLI flags.

`trusted_authority.load_current_authority(...)` is a trusted-host library boundary. It requires two explicit capability inputs:

- `trusted_generation` — the current positive integer generation;
- `trusted_authority_sha256` — SHA-256 of the exact canonical current authority material.

The function validates an authority document against those supplied values, but it deliberately does **not** authenticate where those values came from. The caller is trusted host integration and must independently authenticate that root outside candidate/proposal-controlled bytes and process state before invoking the function.

The public `preflight.py` CLI is intentionally unprivileged. It has no `--authority` option, never calls the trusted-host loader, and cannot produce READY. Even a caller that fabricates a complete authority, computes its digest, and sets the legacy environment variable names cannot promote CLI evaluation beyond HOLD.

This is the boundary:

```python
from preflight import evaluate
from trusted_authority import load_current_authority

# These two values must already have been authenticated by trusted host code.
root_generation = host_authenticated_generation
root_digest = host_authenticated_authority_sha256

authority = load_current_authority(
    "/trusted/path/authority.json",
    trusted_generation=root_generation,
    trusted_authority_sha256=root_digest,
)
receipt = evaluate(proposal_state, authority)
```

Do not source `root_generation` or `root_digest` from proposal bytes, CLI arguments, caller-controlled environment variables, a sibling file selected by the proposal process, or a digest calculated from the same candidate authority being authenticated. If an integration cannot establish that separation, it must use the public CLI/HOLD path rather than assert READY.

## Canonical authority material

The trusted digest covers exactly:

```json
{
  "schema_version": "grand-rapids-920-45-269-authority/v1",
  "solicitation_id": "920-45-269",
  "generation": 1,
  "packet_sha256": "<64 lowercase hex>",
  "addenda": [
    {"id": "addendum-1", "sha256": "<64 lowercase hex>"}
  ],
  "required_gates": ["<the exact built-in ordered gate universe>"],
  "evidence": [
    {
      "id": "ev:packet",
      "gate": "controlling_packet_acquired",
      "kind": "CONTROLLING_PACKET",
      "sha256": "<exact packet sha256>",
      "source_generation_sha256": "<digest of packet_sha256 + ordered addenda>"
    }
  ]
}
```

Every object has an exact key set. Generation uses a strict built-in integer; booleans are rejected. Digests are lowercase 64-hex. Addenda are strictly sorted with unique canonical IDs. Evidence IDs are unique and bounded. Each gate has one fixed evidence kind. Every evidence row must bind the same exact packet/addenda source-generation digest; changing packet or addenda invalidates stale evidence mechanically.

The `controlling_packet_acquired` evidence digest must equal the exact `packet_sha256`. The `packet_sha256_verified` / `PACKET_SHA256_VERIFICATION` evidence digest must also equal that exact current `packet_sha256`; an unrelated 64-hex digest is rejected.

`owner_release_to_submit` accepts only an evidence row whose gate is exactly `owner_release_to_submit` and whose kind is exactly `OWNER_RELEASE`. That row's digest must equal the **release-subject digest**: SHA-256 of the exact solicitation id, current packet/addenda source-generation digest, canonical required-gate universe, and complete non-release evidence projection (`id`, `gate`, `kind`, `sha256`, `source_generation_sha256`, sorted by id). Changing any non-release evidence identity, digest, type, gate, membership, packet, or addenda invalidates a carried-forward OWNER_RELEASE.

## Rotation / anti-rollback procedure

When the controlling packet, any addendum, or any trusted evidence changes:

1. Build a **new** authority material generation from retained bytes/evidence.
2. Increment `generation`.
3. Recompute the packet/addenda source-generation digest and bind every carried-forward evidence row to it only after re-verification.
4. Recompute the release-subject digest and bind `OWNER_RELEASE` to that exact digest.
5. Compute the canonical authority SHA-256 with `trusted_authority.authority_sha256(...)`.
6. Persist the exact authority document.
7. Independently authenticate and advance the trusted host's generation+digest root outside this package.
8. Update proposal state to reference that exact generation+authority digest.
9. Only trusted host integration may pass that authenticated root to `load_current_authority`; public CLI remains HOLD-only.

An old approved document fails when its generation does not match the trusted root. A fork at the current generation fails when its authority digest does not match. A carried-forward OWNER_RELEASE after non-release evidence change fails when it no longer matches the current release-subject digest.

## State semantics

`submission_state.json` v2 contains:

```json
"authority": {
  "generation": null,
  "authority_sha256": null
}
```

until an authenticated authority exists.

A PASS gate lists only authority evidence IDs. Those IDs are not trusted by themselves. Trusted host evaluation resolves them from a `VerifiedAuthority` and checks exact gate, type, source generation, and state-to-authority binding. Public CLI evaluation has no `VerifiedAuthority`, so a PASS claim remains a HOLD blocker rather than becoming READY.

Current repository state deliberately keeps every gate on HOLD because no controlling MITN packet/addenda or owner submit release is possessed.

## Authority ceiling

A trusted-host READY result proves only that the supplied readiness claims matched an authority generation whose root the **host caller says it independently authenticated**. The package does not turn that root into a portable authentication claim. This mechanism provides **no** portal mutation, buyer contact, signature, submission, award, payment, accounting, cash, or revenue-recognition authority.
