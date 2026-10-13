# Shared provider publication admission

`host/provider_budget.py` admits cooperating GitHub publishers through the
existing `request-budget.sqlite3` ledger. Use one **shared authority**: either a
shared state directory on one machine, or the same command-center URL from every
machine. Remote calls use the server's existing state directory and the same
budget honored by its collectors. Do not copy the database into each checkout
or mix independent local and remote authorities. Canonical work claims stay in
`state/claims`; this lease covers provider capacity only.

The coordinator configures capacity once. Workers cannot raise it through an
acquisition. Reducing capacity lets existing admitted work finish and blocks new
holders until the active count drops below the new cap.

```sh
python host/provider_budget.py --state-dir /shared/command-center-state configure --capacity 3
python host/provider_budget.py --state-dir /shared/command-center-state status
python host/provider_budget.py --state-dir /shared/command-center-state acquire --holder lane-f
```

For callers on separate machines, replace `--state-dir PATH` with `--url URL`
on **every** command:

```sh
python host/provider_budget.py --url http://127.0.0.1:8890 status
python host/provider_budget.py --url http://127.0.0.1:8890 acquire --holder vm-a/lane-f
```

The URL above addresses the authority directly on its host or through an
already established trusted tunnel. The server still binds to loopback with
its existing Host/Origin checks; this feature does not deploy it, open a public
listener, create a tunnel, add authentication, or activate owner-PC changes.
Use an existing trusted equipment carrier or protected transport to the one
authority. Holder names identify cooperating callers; they are not credentials.

The existing equipment catalog exposes `command_center_provider_admission`.
Its arguments use `action` (`configure`, `status`, `acquire`, `renew`, `release`,
`limited`) and the CLI's underscore field names, for example
`{"action":"renew","holder":"vm-a/lane-f","lease_id":"..."}`.
HTTP callers use `POST /api/provider/admission` with that JSON object;
`GET /api/provider/admission` reads status. Both share the local CLI dispatcher.
The state directory and provider scopes are selected by the authority, never
by remote request fields. HTTP domain results use `ok` and may be deferred even
when the HTTP status is 200.

Successful acquisition returns `lease_id`, `holder`, `scope`, `capacity`, and
`expires_at`. Each concurrently executing publisher needs a distinct holder.
Repeated acquisition by the same holder returns its existing lease without
extending it or occupying another slot. Keep the returned lease ID.

Immediately before **each connector write**, renew using that exact ID:

```sh
python host/provider_budget.py --state-dir /shared/command-center-state renew --holder lane-f --lease-id LEASE_ID
```

Proceed only on exit 0 and `ok: true`. Exit 75 means no admission: the JSON
contains `reason` (`capacity_exhausted` or `rate_limited`) and
`retry_not_before`. Schedule a later continuation; the CLI never sleeps. The
capacity timestamp is the earliest current lease expiry, an advisory retry time,
not a reserved future slot. Earlier release may free capacity sooner.

`--url` never falls back to a local ledger, follows redirects, or retries a
request. The default timeout is 30 seconds (`--timeout` accepts up to 120).
A timeout, malformed response, or server error is nonzero and may have an
uncertain outcome: stop publication and read shared status. Re-acquisition by
the same holder can recover a still-live lease; renew/release always require
the exact returned ID. If the lease expired, reconcile any in-flight provider
write before acquiring new admission. Give `limited` a stable `--observation-id`
before its first call to make an exact retry count once. Without that ID, do not
automatically replay it after a lost response: repeated observations advance
headerless backoff. Check shared status first. `configure` belongs to the coordinator; reconcile
current capacity before retrying an uncertain configuration change.

The default lease lifetime is 300 seconds; `--ttl-seconds` accepts 1–3600. Choose
a lifetime longer than an individual connector call's timeout. Expiry cannot
cancel an already in-flight remote write. A paused/expired holder must stop
effects, preserve stable operation IDs, reconcile uncertain provider outcomes,
and obtain new admission. Old lease IDs cannot renew or release replacements.

On an observed secondary/unknown GitHub limit, record its actual evidence:

```sh
python host/provider_budget.py --state-dir /shared/command-center-state limited --retry-after 120 --observation-id publication-42-provider-call-3
# If no provider deadline was exposed, omit --retry-after; bounded fallback applies.
```

Use one unique observation ID per actual provider response, and reuse that ID
with the exact same scope and evidence if delivery to the authority is uncertain.
Its fingerprint is persisted atomically with the cooldown in the existing budget
database; header text is not retained. Repeated calls across processes or server
restarts do not increment the streak, count the limit twice, or shift a relative
deadline. Reusing an ID with different evidence returns a nonzero result. A
replay returns `replayed: true` and the currently governing deadline, including
any newer observation. Replaying an expired observation does not revive it.
Callers omitting the ID retain the previous one-call-per-observation behavior.

This uses the existing `github:GET` provider-wide cooldown identity, also honored
by command-center reads. Every publication acquisition and renewal checks it,
plus the existing `github:GET:core` primary cooldown. For confirmed primary core
quota exhaustion, add `--primary-core` and the observed `--reset-at` epoch.
Never invent a deadline or use primary classification for a secondary limit.

Release in a `finally` path after finishing or deferring:

```sh
python host/provider_budget.py --state-dir /shared/command-center-state release --holder lane-f --lease-id LEASE_ID --successful
```

Use `--successful` only after confirmed provider success; omit it on failures,
deferrals, or uncertainty. This resets expired fallback streaks while preserving
any newer active limit. Release is idempotent and requires both holder and ID.
The CLI makes no provider calls, grants no publication authority, and starts no
worker, timer, service, or paid compute.
