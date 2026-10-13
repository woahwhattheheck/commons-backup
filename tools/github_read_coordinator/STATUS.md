# Offline read-rail status

`status.py` observes an existing GitHub read coordinator database using SQLite
`mode=ro`, `query_only` and one read transaction. It never instantiates Broker,
creates a database, changes cooldowns, cleans rows or calls GitHub. Select the
existing credential SHA-256 fingerprint locally; never pass a raw token.

```sh
python tools/github_read_coordinator/status.py --db /private/broker.sqlite --rail main-read --fingerprint <existing-64-hex-fingerprint>
```

The output excludes the fingerprint, database path, request keys, cached bodies,
validators, lease nonces and blocked reason. Use a neutral rail alias. It reports
only known cooldown buckets, authentication blocking and aggregate occupancy for
that selected namespace. The legacy `search` floor applies to both search buckets;
`secondary` and `burst` apply across buckets. Deadlines are local observations,
not proof that a future provider request will succeed. Absence of a cooldown is
not a healthy-rail assertion. Provider health remains `unknown`.

Request budget and last error are null because the existing broker does not
persist those observations. This helper cannot infer native-connector or other
token-rail state, and creates no credential-selection or submission permission.
Repeat only as part of an actual work decision; no polling or retries are added.
Expired leases and entries older than the existing 300-second maximum age are
excluded from occupancy without deleting them. `recent_cache_entries` is only
the cohort observed within that 300-second window; a request's chosen maximum
age can be shorter, so this count does not establish usable cache hits. The
connection closes on success and error, including use as an imported library.
Schema/read errors produce a
generic failure without printing private paths or database content.

Source basis: existing broker.py blob fd975a6195c1a46bd28a605e1d82dc1af6ac8472,
GitHub read coordinator version-1 schema, observed 2026-10-06. This is an additive
offline observability helper, not a deployed gateway endpoint.
