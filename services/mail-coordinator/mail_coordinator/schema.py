SCHEMA = """
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA busy_timeout = 5000;

CREATE TABLE IF NOT EXISTS operations (
    operation_id TEXT PRIMARY KEY,
    action TEXT NOT NULL,
    request_sha256 TEXT NOT NULL,
    result_json TEXT NOT NULL,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS suppressions (
    address TEXT PRIMARY KEY,
    reason TEXT NOT NULL,
    evidence_ref TEXT NOT NULL,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS inbounds (
    mailbox TEXT NOT NULL,
    conversation_key TEXT NOT NULL,
    provider_message_id TEXT NOT NULL,
    received_at REAL NOT NULL,
    operation_id TEXT NOT NULL UNIQUE,
    created_at REAL NOT NULL,
    PRIMARY KEY (mailbox, provider_message_id)
);
CREATE INDEX IF NOT EXISTS idx_inbounds_conversation
    ON inbounds(mailbox, conversation_key, received_at DESC);

CREATE TABLE IF NOT EXISTS messages (
    message_id TEXT PRIMARY KEY,
    operation_id TEXT NOT NULL UNIQUE,
    mailbox TEXT NOT NULL,
    sender TEXT NOT NULL,
    subject TEXT NOT NULL,
    normalized_subject TEXT NOT NULL,
    body TEXT NOT NULL,
    body_sha256 TEXT NOT NULL,
    conversation_key TEXT,
    inbound_message_id TEXT,
    inbound_received_at REAL,
    state TEXT NOT NULL CHECK(state IN (
        'QUEUED','CLAIMED','ATTEMPTING','UNCERTAIN','SENT',
        'INVALIDATED','SUPPRESSED','CANCELLED'
    )),
    state_reason TEXT,
    current_claim_id TEXT,
    provider_message_id TEXT,
    provider_accepted_at REAL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_scope
    ON messages(mailbox, conversation_key, inbound_message_id, normalized_subject, state);
CREATE INDEX IF NOT EXISTS idx_messages_created
    ON messages(mailbox, created_at DESC);

CREATE TABLE IF NOT EXISTS message_recipients (
    message_id TEXT NOT NULL REFERENCES messages(message_id) ON DELETE CASCADE,
    address TEXT NOT NULL,
    kind TEXT NOT NULL CHECK(kind IN ('to','cc','bcc')),
    ordinal INTEGER NOT NULL,
    PRIMARY KEY (message_id, address, kind)
);
CREATE INDEX IF NOT EXISTS idx_recipients_address ON message_recipients(address, message_id);

CREATE TABLE IF NOT EXISTS claims (
    claim_id TEXT PRIMARY KEY,
    message_id TEXT NOT NULL REFERENCES messages(message_id),
    worker_id TEXT NOT NULL,
    state TEXT NOT NULL CHECK(state IN ('CLAIMED','EXPIRED','RELEASED','ATTEMPTING','COMPLETED')),
    claimed_at REAL NOT NULL,
    lease_until REAL NOT NULL,
    released_at REAL,
    attempt_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_claims_message ON claims(message_id, claimed_at DESC);

CREATE TABLE IF NOT EXISTS attempts (
    attempt_id TEXT PRIMARY KEY,
    message_id TEXT NOT NULL REFERENCES messages(message_id),
    claim_id TEXT NOT NULL REFERENCES claims(claim_id),
    state TEXT NOT NULL CHECK(state IN ('STARTED','UNCERTAIN','SENT','NOT_SENT')),
    started_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    detail TEXT,
    provider_message_id TEXT,
    provider_accepted_at REAL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_attempts_live_message
    ON attempts(message_id) WHERE state IN ('STARTED','UNCERTAIN','SENT');
CREATE UNIQUE INDEX IF NOT EXISTS idx_attempts_provider_message
    ON attempts(provider_message_id) WHERE provider_message_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id TEXT,
    event_type TEXT NOT NULL,
    data_json TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_message ON events(message_id, event_id);
"""

