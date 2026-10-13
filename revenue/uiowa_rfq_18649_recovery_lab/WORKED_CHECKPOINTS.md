# Worked checkpoints — synthetic only

Generated from `examples.json` by `python lab.py examples.json --format json`.
These are fictional logical minutes and model results, not University exercise evidence.

Canonical scenario SHA-256: `df0fb7e7623fd9be097ba24a6041679849c0660d3d36d1b31be1c82f97370cf0`.

| Scenario | Checkpoint | Minute | Readable | All six invariants | Verified interval | Failed invariants |
|---|---|---:|---|---|---:|---|
| R63-CONFIG | `baseline` | 0 | True | True | not established | none |
| R63-CONFIG | `incompatible_reader` | 2 | False | False | not established | balances_match_accepted_log, capacity_valid, service_readable |
| R63-CONFIG | `configuration_restored` | 4 | True | True | 3 | none |
| R63-SNAPSHOT | `healthy_but_missing_writes` | 6 | True | False | not established | accepted_events_accounted_for, balances_match_accepted_log |
| R63-SNAPSHOT | `log_replayed` | 8 | True | True | 4 | none |
| R63-FORWARD | `old_binary_is_not_data_rollback` | 6 | False | False | not established | accepted_events_accounted_for, balances_match_accepted_log, capacity_valid, service_readable |
| R63-FORWARD | `forward_compatibility_repair` | 9 | True | True | 6 | none |
| R63-REPLAY | `duplicate_safely_skipped` | 4 | True | True | not established | none |
| R63-REPLAY | `healthy_but_double_applied` | 6 | True | False | not established | applied_at_most_once, balances_match_accepted_log |
| R63-REPLAY | `snapshot_and_idempotent_replay` | 10 | True | True | 5 | none |
| R63-MIXED | `split_views` | 5 | True | False | not established | balances_match_accepted_log, legacy_and_new_views_agree |
| R63-MIXED | `bridge_refuses_conflicting_fields` | 8 | False | False | not established | accepted_events_accounted_for, balances_match_accepted_log, capacity_valid, legacy_and_new_views_agree, service_readable |
| R63-MIXED | `reconciled_dual_representation` | 12 | True | True | 9 | none |
| R63-MIXED | `contracted_and_duplicate_safe` | 16 | True | True | 13 | none |
| R63-NETZERO | `totals_match_but_work_is_missing` | 4 | True | False | not established | accepted_events_accounted_for |
| R63-NETZERO | `each_event_accounted_for` | 6 | True | True | 3 | none |

A verified interval belongs to that checkpoint, not automatically the first recovery.
Run the JSON report for exact event IDs, raw stored rows, versions and application counts.
Run `python lab.py examples.json --format markdown` for the expanded action transcript.

Counterexamples pinned by tests: the restored snapshot reads 2 against expected 7; the mixed
representation contains units=5 and quantity=2; and the net-zero case has equal totals of 2
while NET-001 and NET-002 are both unapplied. All three remain failed model recoveries.
