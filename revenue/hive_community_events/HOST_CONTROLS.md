# Lantern host capability contract

Operation: `LANTERN-HOST-CAPABILITY-AUTH-ZL913X-20260913`

Lantern uses a per-event bearer capability for host-only mutations. This is a narrow control boundary, not an account or identity system.

## New events

- Event creation generates a cryptographically random host key with `secrets.token_urlsafe`.
- The create response returns the plaintext key once so the browser can retain it for the host.
- SQLite persists only the SHA-256 digest of the key.
- Public event listings, event state, participant references, leaderboard/results exports, participant links, and normal server logs never contain the key or its digest.
- Candidate keys are reduced to SHA-256 digests and compared with `hmac.compare_digest`.

## Protected mutations

`POST /api/events/{id}/finish` requires the matching `host_key` for protected events. A missing or incorrect key receives the same HTTP 403 error and does not mutate the event.

`POST /api/events/{id}/host/verify` validates a host key without changing event state. The browser uses this endpoint when a host pastes a recovery key on another browser.

`Store.finish()` remains the trusted internal primitive used by local tools and test fixtures. Authorization is enforced at the HTTP boundary rather than duplicated inside export/calendar internals that already operate with direct database authority.

## Browser storage and recovery

Host capabilities are stored under a separate browser-storage key from participant reconnect references. The event share URL never receives the capability. A host can reveal the stored value locally to back it up, or paste a previously saved value to recover host controls after changing browsers.

The server cannot recover plaintext host keys from the database. If the create response and every browser/backup copy are lost, create a replacement event before sharing it rather than weakening the authorization boundary.

## Legacy rows

Existing SQLite databases are migrated in place by adding nullable `events.host_hash`. Rows created before this feature retain `NULL` because no historical plaintext host key exists to hash. Those legacy rows therefore preserve the old shared-finish behavior; newly created rows are protected. The UI labels this distinction explicitly.

## Failure semantics

- Unknown event: HTTP 404.
- Missing or incorrect host key for a protected event: HTTP 403 with the same generic error.
- Valid host key: verification succeeds and protected finish may proceed.
- Finishing remains final and idempotent after authorization.

This contract does not provide verified participant identity, competitive anti-cheat guarantees, public multi-tenant isolation, a hosted deployment, or customer/account administration.
