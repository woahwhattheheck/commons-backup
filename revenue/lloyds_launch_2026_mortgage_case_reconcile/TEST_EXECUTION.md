# Mortgage reconciliation — independent test and source-review evidence

Recorded by ZZ–Trellis review support for the reconstruction of #15959. Original contract/source attribution remains **Z-Quorum-7F2C**. The corrupted original carrier was treated only as static evidence; it was not imported or executed.

## Accepted result

**32/32 normal and 32/32 optimized component tests passed on the first run in each mode. Both repository discovery bridge invocations also passed.** The bridge has one outer unittest method which launches the same 32 component methods; it does not add another 32 distinct test cases. No test expectations or runtime files were changed to obtain these results.

Python was `3.12.14 (main, Aug 25 2026, 14:00:49) [Clang 22.1.3 ]`. All input records in these tests are independently specified synthetic examples.

The four literal output blocks below are copied from the already completed execution-tool results and the preserved scratch logs. No test was rerun to create this document. A subsequent source-identity check confirmed the four pinned files still matched.

## Source identities

Paths below are relative to this component except the explicitly marked repository-root bridge.

| File | Bytes | Git blob | SHA-256 |
| --- | ---: | --- | --- |
| `mortgage_core.py` | 21909 | `811add9edce0955428385294c540d3d25ce577a8` | `3e4fe6e51951e71043cc330217d5fd5e9a04fb5308760b281a4a740a7cd4b007` |
| `mortgage_case_reconcile.py` | 20335 | `3a00835019b28ff86f1da76be1131d630a207566` | `56612fb21284e58a36e79911c2d3167c38e2488982d93da1e4f84942c02d0d28` |
| `test_mortgage_case_reconcile.py` | 24762 | `0a655b90c781931e3241e32f15e321798cb4b28b` | `fe9d84d828b795925733eee7191a6386ead058047c7256e31f99b7b2cf03b36e` |
| `test_lloyds_mortgage_case_reconcile.py` (repository root) | 863 | `d993de622781fcd725a91943ba59cc0474b5dd57` | `2bd70e760421d2673bc1bf605293b89e4ff2c953b73b2ea48c4520edb13d63ac` |

The stored identities were checked before the optimized/bridge invocations and again after all three completed. These are observed disk identities and local proof, not authentication of a producer or attestation of arbitrary Python execution.

## Test scope

The suite covers all five field kinds, strict money/calendar/Boolean types, duplicate and nonfinite JSON, unknown keys and references, normalization and permitted permutations, missing and conflicting observations, exact issue/action association, document-count deduplication, contradictory hash/status/identity records, and retained evidence.

It also covers explicit status regression, simultaneous ambiguity, informational-event retention without false regression, revised supplied records, recompilation-based receipt verification, formula-safe CSV, escaped Unicode HTML, exact raw input retention, the complete bundle inventory, a copied-package verifier, resealed derived-output tampering, invalid-input containment, and preservation of existing or aliased output paths.

The legacy three-file export is checked for preflight preservation. It is not claimed to be a transactional filesystem operation if a later write fails. The preferred bundle writes its manifest last.

## Direct component suite — normal

Working directory: `revenue/lloyds_launch_2026_mortgage_case_reconcile`.

```sh
python3 -B -m unittest test_mortgage_case_reconcile.py -v
```

Execution-tool chunk `23f7b2`; exit code **0**. Literal output:

```text
test_actions_link_exact_issue_ids_for_suffix_related_subjects (test_mortgage_case_reconcile.MortgageCaseTests.test_actions_link_exact_issue_ids_for_suffix_related_subjects) ... ok
test_actual_legacy_cli_compile_verify_and_revised_input (test_mortgage_case_reconcile.MortgageCaseTests.test_actual_legacy_cli_compile_verify_and_revised_input) ... ok
test_actual_status_regression_is_blocking_and_retains_current_status (test_mortgage_case_reconcile.MortgageCaseTests.test_actual_status_regression_is_blocking_and_retains_current_status) ... ok
test_aligned_baseline_is_reconciliation_only_with_false_authority (test_mortgage_case_reconcile.MortgageCaseTests.test_aligned_baseline_is_reconciliation_only_with_false_authority) ... ok
test_bool_code_date_and_text_values_are_typed_and_calendar_valid (test_mortgage_case_reconcile.MortgageCaseTests.test_bool_code_date_and_text_values_are_typed_and_calendar_valid) ... ok
test_bundle_existing_directory_symlinks_and_extra_file_do_not_pass (test_mortgage_case_reconcile.MortgageCaseTests.test_bundle_existing_directory_symlinks_and_extra_file_do_not_pass) ... ok
test_bundle_keeps_exact_input_and_all_payloads_and_runs_copied_verifier (test_mortgage_case_reconcile.MortgageCaseTests.test_bundle_keeps_exact_input_and_all_payloads_and_runs_copied_verifier) ... ok
test_bundle_rejects_derived_tamper_even_if_inventory_hash_is_resealed (test_mortgage_case_reconcile.MortgageCaseTests.test_bundle_rejects_derived_tamper_even_if_inventory_hash_is_resealed) ... ok
test_cli_malformed_input_is_contained_and_creates_no_outputs (test_mortgage_case_reconcile.MortgageCaseTests.test_cli_malformed_input_is_contained_and_creates_no_outputs) ... ok
test_cli_preflights_existing_destinations_and_input_or_output_aliases (test_mortgage_case_reconcile.MortgageCaseTests.test_cli_preflights_existing_destinations_and_input_or_output_aliases) ... ok
test_conflict_and_missing_are_both_retained (test_mortgage_case_reconcile.MortgageCaseTests.test_conflict_and_missing_are_both_retained) ... ok
test_different_input_cannot_reuse_old_receipt (test_mortgage_case_reconcile.MortgageCaseTests.test_different_input_cannot_reuse_old_receipt) ... ok
test_html_escapes_supported_text_and_csv_protects_formula_looking_cells (test_mortgage_case_reconcile.MortgageCaseTests.test_html_escapes_supported_text_and_csv_protects_formula_looking_cells) ... ok
test_identifier_scopes_duplicates_and_unresolved_references_rejected (test_mortgage_case_reconcile.MortgageCaseTests.test_identifier_scopes_duplicates_and_unresolved_references_rejected) ... ok
test_informational_events_are_retained_without_false_state_regression (test_mortgage_case_reconcile.MortgageCaseTests.test_informational_events_are_retained_without_false_state_regression) ... ok
test_missing_required_observation_preserves_available_evidence (test_mortgage_case_reconcile.MortgageCaseTests.test_missing_required_observation_preserves_available_evidence) ... ok
test_money_requires_exact_nonboolean_integer_units_and_currency_shape (test_mortgage_case_reconcile.MortgageCaseTests.test_money_requires_exact_nonboolean_integer_units_and_currency_shape) ... ok
test_no_status_event_leaves_current_state_unknown (test_mortgage_case_reconcile.MortgageCaseTests.test_no_status_event_leaves_current_state_unknown) ... ok
test_normalization_is_idempotent_permutation_stable_and_does_not_mutate (test_mortgage_case_reconcile.MortgageCaseTests.test_normalization_is_idempotent_permutation_stable_and_does_not_mutate) ... ok
test_receipt_verification_recompiles_instead_of_trusting_resealed_digest (test_mortgage_case_reconcile.MortgageCaseTests.test_receipt_verification_recompiles_instead_of_trusting_resealed_digest) ... ok
test_rejected_documents_do_not_satisfy_requirement (test_mortgage_case_reconcile.MortgageCaseTests.test_rejected_documents_do_not_satisfy_requirement) ... ok
test_repeated_document_hash_is_one_validated_document (test_mortgage_case_reconcile.MortgageCaseTests.test_repeated_document_hash_is_one_validated_document) ... ok
test_required_source_and_document_threshold_references_are_validated (test_mortgage_case_reconcile.MortgageCaseTests.test_required_source_and_document_threshold_references_are_validated) ... ok
test_revised_snapshot_resolves_only_after_supplied_values_agree (test_mortgage_case_reconcile.MortgageCaseTests.test_revised_snapshot_resolves_only_after_supplied_values_agree) ... ok
test_root_schema_missing_unknown_and_pii_shaped_keys_rejected (test_mortgage_case_reconcile.MortgageCaseTests.test_root_schema_missing_unknown_and_pii_shaped_keys_rejected) ... ok
test_same_document_id_changed_hash_or_type_preserves_contested_records (test_mortgage_case_reconcile.MortgageCaseTests.test_same_document_id_changed_hash_or_type_preserves_contested_records) ... ok
test_same_hash_conflicting_status_is_not_counted_as_validated (test_mortgage_case_reconcile.MortgageCaseTests.test_same_hash_conflicting_status_is_not_counted_as_validated) ... ok
test_simultaneous_status_disagreement_remains_ambiguous (test_mortgage_case_reconcile.MortgageCaseTests.test_simultaneous_status_disagreement_remains_ambiguous) ... ok
test_strict_json_rejects_duplicate_keys_and_nonfinite_numbers (test_mortgage_case_reconcile.MortgageCaseTests.test_strict_json_rejects_duplicate_keys_and_nonfinite_numbers) ... ok
test_timestamps_are_canonical_valid_and_not_after_assessment (test_mortgage_case_reconcile.MortgageCaseTests.test_timestamps_are_canonical_valid_and_not_after_assessment) ... ok
test_two_distinct_uncontested_validated_documents_satisfy_two (test_mortgage_case_reconcile.MortgageCaseTests.test_two_distinct_uncontested_validated_documents_satisfy_two) ... ok
test_typed_containers_and_nested_unknown_keys_rejected (test_mortgage_case_reconcile.MortgageCaseTests.test_typed_containers_and_nested_unknown_keys_rejected) ... ok

----------------------------------------------------------------------
Ran 32 tests in 0.868s

OK
```

## Direct component suite — optimized

Working directory: `revenue/lloyds_launch_2026_mortgage_case_reconcile`.

```sh
python3 -B -O -m unittest test_mortgage_case_reconcile.py -v
```

Execution-tool chunk `308fbf`; exit code **0**. Literal output:

```text
test_actions_link_exact_issue_ids_for_suffix_related_subjects (test_mortgage_case_reconcile.MortgageCaseTests.test_actions_link_exact_issue_ids_for_suffix_related_subjects) ... ok
test_actual_legacy_cli_compile_verify_and_revised_input (test_mortgage_case_reconcile.MortgageCaseTests.test_actual_legacy_cli_compile_verify_and_revised_input) ... ok
test_actual_status_regression_is_blocking_and_retains_current_status (test_mortgage_case_reconcile.MortgageCaseTests.test_actual_status_regression_is_blocking_and_retains_current_status) ... ok
test_aligned_baseline_is_reconciliation_only_with_false_authority (test_mortgage_case_reconcile.MortgageCaseTests.test_aligned_baseline_is_reconciliation_only_with_false_authority) ... ok
test_bool_code_date_and_text_values_are_typed_and_calendar_valid (test_mortgage_case_reconcile.MortgageCaseTests.test_bool_code_date_and_text_values_are_typed_and_calendar_valid) ... ok
test_bundle_existing_directory_symlinks_and_extra_file_do_not_pass (test_mortgage_case_reconcile.MortgageCaseTests.test_bundle_existing_directory_symlinks_and_extra_file_do_not_pass) ... ok
test_bundle_keeps_exact_input_and_all_payloads_and_runs_copied_verifier (test_mortgage_case_reconcile.MortgageCaseTests.test_bundle_keeps_exact_input_and_all_payloads_and_runs_copied_verifier) ... ok
test_bundle_rejects_derived_tamper_even_if_inventory_hash_is_resealed (test_mortgage_case_reconcile.MortgageCaseTests.test_bundle_rejects_derived_tamper_even_if_inventory_hash_is_resealed) ... ok
test_cli_malformed_input_is_contained_and_creates_no_outputs (test_mortgage_case_reconcile.MortgageCaseTests.test_cli_malformed_input_is_contained_and_creates_no_outputs) ... ok
test_cli_preflights_existing_destinations_and_input_or_output_aliases (test_mortgage_case_reconcile.MortgageCaseTests.test_cli_preflights_existing_destinations_and_input_or_output_aliases) ... ok
test_conflict_and_missing_are_both_retained (test_mortgage_case_reconcile.MortgageCaseTests.test_conflict_and_missing_are_both_retained) ... ok
test_different_input_cannot_reuse_old_receipt (test_mortgage_case_reconcile.MortgageCaseTests.test_different_input_cannot_reuse_old_receipt) ... ok
test_html_escapes_supported_text_and_csv_protects_formula_looking_cells (test_mortgage_case_reconcile.MortgageCaseTests.test_html_escapes_supported_text_and_csv_protects_formula_looking_cells) ... ok
test_identifier_scopes_duplicates_and_unresolved_references_rejected (test_mortgage_case_reconcile.MortgageCaseTests.test_identifier_scopes_duplicates_and_unresolved_references_rejected) ... ok
test_informational_events_are_retained_without_false_state_regression (test_mortgage_case_reconcile.MortgageCaseTests.test_informational_events_are_retained_without_false_state_regression) ... ok
test_missing_required_observation_preserves_available_evidence (test_mortgage_case_reconcile.MortgageCaseTests.test_missing_required_observation_preserves_available_evidence) ... ok
test_money_requires_exact_nonboolean_integer_units_and_currency_shape (test_mortgage_case_reconcile.MortgageCaseTests.test_money_requires_exact_nonboolean_integer_units_and_currency_shape) ... ok
test_no_status_event_leaves_current_state_unknown (test_mortgage_case_reconcile.MortgageCaseTests.test_no_status_event_leaves_current_state_unknown) ... ok
test_normalization_is_idempotent_permutation_stable_and_does_not_mutate (test_mortgage_case_reconcile.MortgageCaseTests.test_normalization_is_idempotent_permutation_stable_and_does_not_mutate) ... ok
test_receipt_verification_recompiles_instead_of_trusting_resealed_digest (test_mortgage_case_reconcile.MortgageCaseTests.test_receipt_verification_recompiles_instead_of_trusting_resealed_digest) ... ok
test_rejected_documents_do_not_satisfy_requirement (test_mortgage_case_reconcile.MortgageCaseTests.test_rejected_documents_do_not_satisfy_requirement) ... ok
test_repeated_document_hash_is_one_validated_document (test_mortgage_case_reconcile.MortgageCaseTests.test_repeated_document_hash_is_one_validated_document) ... ok
test_required_source_and_document_threshold_references_are_validated (test_mortgage_case_reconcile.MortgageCaseTests.test_required_source_and_document_threshold_references_are_validated) ... ok
test_revised_snapshot_resolves_only_after_supplied_values_agree (test_mortgage_case_reconcile.MortgageCaseTests.test_revised_snapshot_resolves_only_after_supplied_values_agree) ... ok
test_root_schema_missing_unknown_and_pii_shaped_keys_rejected (test_mortgage_case_reconcile.MortgageCaseTests.test_root_schema_missing_unknown_and_pii_shaped_keys_rejected) ... ok
test_same_document_id_changed_hash_or_type_preserves_contested_records (test_mortgage_case_reconcile.MortgageCaseTests.test_same_document_id_changed_hash_or_type_preserves_contested_records) ... ok
test_same_hash_conflicting_status_is_not_counted_as_validated (test_mortgage_case_reconcile.MortgageCaseTests.test_same_hash_conflicting_status_is_not_counted_as_validated) ... ok
test_simultaneous_status_disagreement_remains_ambiguous (test_mortgage_case_reconcile.MortgageCaseTests.test_simultaneous_status_disagreement_remains_ambiguous) ... ok
test_strict_json_rejects_duplicate_keys_and_nonfinite_numbers (test_mortgage_case_reconcile.MortgageCaseTests.test_strict_json_rejects_duplicate_keys_and_nonfinite_numbers) ... ok
test_timestamps_are_canonical_valid_and_not_after_assessment (test_mortgage_case_reconcile.MortgageCaseTests.test_timestamps_are_canonical_valid_and_not_after_assessment) ... ok
test_two_distinct_uncontested_validated_documents_satisfy_two (test_mortgage_case_reconcile.MortgageCaseTests.test_two_distinct_uncontested_validated_documents_satisfy_two) ... ok
test_typed_containers_and_nested_unknown_keys_rejected (test_mortgage_case_reconcile.MortgageCaseTests.test_typed_containers_and_nested_unknown_keys_rejected) ... ok

----------------------------------------------------------------------
Ran 32 tests in 2.686s

OK
```

## Repository discovery bridge — normal

Working directory: `repository root`.

```sh
python3 -B -m unittest test_lloyds_mortgage_case_reconcile -v
```

Execution-tool chunk `e88736`; exit code **0**. Literal output:

```text
test_component_suite (test_lloyds_mortgage_case_reconcile.MortgageCaseReconciliationSuite.test_component_suite) ... ok

----------------------------------------------------------------------
Ran 1 test in 0.994s

OK
```

## Repository discovery bridge — optimized

Working directory: `repository root`.

```sh
python3 -B -O -m unittest test_lloyds_mortgage_case_reconcile -v
```

Execution-tool chunk `62b221`; exit code **0**. Literal output:

```text
test_component_suite (test_lloyds_mortgage_case_reconcile.MortgageCaseReconciliationSuite.test_component_suite) ... ok

----------------------------------------------------------------------
Ran 1 test in 3.112s

OK
```

## Independent source review

A full read of the pinned `mortgage_core.py` found no defect against the locked reconstruction contract:

- Every supplied source observation remains represented in the normalized case and receipt projections. Missing required fields and disagreements remain separate findings.
- Conflicting statuses for one hash, or conflicting hash/type assignments for one document ID, mark every associated hash contested. Contested hashes are excluded from distinct validated counts. Duplicate identifiers are rejected within their declared scopes.
- Only status events establish milestone state. Equal-time status observations form a group; differing milestones remain explicit ambiguity. Informational events remain in the timeline. A regression is reported only when every current group position precedes every previous group position; earlier ambiguity remains a blocking issue.
- Structural validation checks exact JSON types, cycles, Unicode scalar values, finite numbers, depth 64, a 100,000-node limit and a 2,000,000-byte canonical input bound. The facade separately caps raw input bytes. Unknown schema keys and unresolved references are rejected.
- Collection ordering, issue ordering and explicit issue/action links are deterministic. The full normalized case, all events, evidence projections, issues, actions and eight false authority flags are retained. Returning a JSON round-trip removes shared mutable aliases inside the receipt.
- Source and semantic digests use canonical normalized values. The facade verifier compares a complete new compilation, rather than trusting a supplied self-hash.

The facade source review found the promised preflight checks, exclusive file creation, complete bundle-file comparison, source-copy comparison, direct issue-ID action linkage and text escaping. Its support files are unsigned reproduction aids. The copied verifier was actually invoked with `python -B mortgage_case_reconcile.py verify-bundle .` within the bundle test.

No browser session, visual/accessibility acceptance, `-OO` execution, hosted CI result, integration authority, live lender integration, public-source authentication or financial decision is established by these checks. “No declared blockers” means only that the supplied reconciliation rules found no blocker. It is not lending approval, eligibility, affordability, fraud clearance or permission to act.

