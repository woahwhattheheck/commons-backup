-- Separate tables in the existing Commons D1 database. No publisher table is changed.
CREATE TABLE IF NOT EXISTS slack_shipping_cursors (
  channel TEXT PRIMARY KEY, latest_ts TEXT NOT NULL, initialized INTEGER NOT NULL,
  page_cursor TEXT, scan_upper_ts TEXT, updated_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS slack_shipping_threads (
  channel TEXT NOT NULL, root_ts TEXT NOT NULL, latest_ts TEXT NOT NULL,
  refs TEXT NOT NULL, signature TEXT NOT NULL, baseline INTEGER NOT NULL,
  page_cursor TEXT, scan_messages TEXT, active INTEGER NOT NULL DEFAULT 1,
  updated_at INTEGER NOT NULL,
  PRIMARY KEY (channel, root_ts)
);
CREATE TABLE IF NOT EXISTS slack_shipping_outbox (
  id TEXT PRIMARY KEY, channel TEXT NOT NULL, thread_ts TEXT,
  kind TEXT NOT NULL, body TEXT NOT NULL, state TEXT NOT NULL,
  slack_ts TEXT, readback_cursor TEXT, readback_messages TEXT,
  readback_complete INTEGER NOT NULL DEFAULT 0,
  created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS slack_shipping_outbox_state
  ON slack_shipping_outbox(state, created_at);
CREATE TABLE IF NOT EXISTS slack_shipping_state (
  key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS slack_shipping_operator_notices (
  notice_id TEXT PRIMARY KEY, reason_code TEXT NOT NULL, tool_name TEXT NOT NULL,
  operation_id TEXT, repository TEXT, issue_number INTEGER,
  created_at INTEGER NOT NULL, queued_at INTEGER
);
