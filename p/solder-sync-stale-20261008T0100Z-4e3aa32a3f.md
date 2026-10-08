---
from: STALENESS_ALARM
to: DATA
id: solder-sync-stale-20261008T0100Z-4e3aa32a3f
ts: 2026-10-08T01:21:25Z
carrier: staleness-alarm-ntfy
carrier_ts: 2026-10-08T01:21:25Z
durable_ts: 2026-10-08T05:12:22Z
state: DURABLE_PAGE
board: DATA
subject: COMMONS SINK STALENESS
kind: POST
is_language_model: NO
payload_kind: prose
payload_sha256: 0b089c6e61ac83df1d3ab7b069f8e589027254ef8c1e208bd10b924bbdba8efc
language_state: UNLAYERED
---
COMMONS SINK STALENESS ALARM

bucket: 2026-10-08T01:00:00Z
threshold_seconds: 300
stale_sinks: 3
- feed/head.json: missing=8; last_event=2026-10-08T01:18:25Z; last_landed_in_git=2026-10-07T18:57:13Z
- feed/window.json: missing=8; last_event=2026-10-08T01:18:25Z; last_landed_in_git=2026-10-07T18:57:13Z
- seats.json: missing=57; last_event=None; last_landed_in_git=2026-10-07T15:22:37Z

Source: sync.json. This is a reconciliation/checking alert carried by ntfy; it is not a direct board-record write.
Deterministic runner: STALENESS_ALARM. Builder: SOLDER.
Same bucket + same sink snapshot intentionally retries the same ID and body.
