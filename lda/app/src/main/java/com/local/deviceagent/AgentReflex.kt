package com.local.deviceagent

/**
 * REMOVED 2026-07-23 (owner directive). This class was a "reflex table" that let the agent fire a CACHED action without
 * the model choosing it — a direct violation of the LDA's core principle: THE MODEL CHOOSES EVERY SINGLE ACTION and its
 * own perception; deterministic code only perceives, actuates, and gates safety. Replaying a cached action on the wrong
 * screen is a catastrophic real-world safety risk (e.g. a destructive tap). No reflexes, no scripts, no automatic actions.
 * The file is intentionally left empty as a tombstone so nothing reintroduces it.
 */
