# Civic portable handoff — independent test execution

Recorded by ZZ–Trellis review support. These are synthetic integration fixtures and checks of emitted artifacts, retained source bytes, and the existing compiler. They do not establish public-record authenticity, legal authority, browser behavior, visual quality, or accessibility compliance.

## Custody and environment

The following output blocks preserve the literal test output already returned by the execution tools. They were transcribed from those results without rerunning the commands for this record. No separate raw log file was retained before this document. Python version: **3.12.14**, obtained with `python3 --version`.

The component working directory was `competitions/gatewayhacks-2026-civic-ledger` beneath the repository root. The root discovery command ran from the repository root.

| File | Git blob used for the accepted result |
| --- | --- |
| `civic_ledger/handoff.py` | `bed0659a3b622368f4c7f48b203c1bdd4fc65894` |
| `civic_ledger/core.py` | `964cf5231cf4c72390fe9fb30bddc45813ebeac9` |
| `civic_ledger/__init__.py` | `8d669e2ffdca9f728e961c5e6a64f2f164d57628` |
| `tests/test_handoff.py` — direct normal and optimized runs | `efb70c7be87a5816fb4ee940d5fd76b65078312a` |
| `tests/test_handoff.py` — final helper and normal/optimized root bridge runs | `56461284edf6bc78cd5c2f07d409d8921225b5d8` |
| Repository-root `test_civic_portable_handoff.py` | `5290743958455c8e0b98c64a60ffe7a3fc0f6153` |

After the two direct 15-test passes, the only component-test change was to construct the subprocess optimization flag from `sys.flags.optimize`, preserving `-OO` as well as `-O`. It did not change test assertions, fixture inputs, or normal/`-O` argument values. The root bridge received the same flag propagation and a 60-second timeout. Its subsequent normal invocation passed against the final test blob. One later optimized bridge invocation specifically checked this final driver path, as recorded below. An `-OO` run is **not claimed**.

The first exploratory run had one failed test because its expectation required relative source-download URLs. The reader instead intentionally embeds standalone data URLs. The corrected test decodes all eight fixture downloads and compares their bytes with the four native files, exact workspace, and three normalized sources. The accepted outputs below are from that correction; no production-source change was required for it.

## Direct normal invocation

Command:

```sh
python3 -B -m unittest discover -s tests -p test_handoff.py -v
```

Execution-tool chunk `17c1fe`; exit code **0**.

```text
test_canonical_four_files_remain_byte_identical_to_retained_core (test_handoff.HandoffTests.test_canonical_four_files_remain_byte_identical_to_retained_core) ... ok
test_conflict_unknown_and_decided_states_survive_handoff (test_handoff.HandoffTests.test_conflict_unknown_and_decided_states_survive_handoff) ... ok
test_exact_workspace_bytes_and_all_payload_hashes_are_bound (test_handoff.HandoffTests.test_exact_workspace_bytes_and_all_payload_hashes_are_bound) ... ok
test_existing_directory_symlink_and_dangling_symlink_are_refused (test_handoff.HandoffTests.test_existing_directory_symlink_and_dangling_symlink_are_refused) ... ok
test_existing_output_directory_or_file_is_preserved (test_handoff.HandoffTests.test_existing_output_directory_or_file_is_preserved) ... ok
test_manifest_assessment_change_is_not_silently_adopted (test_handoff.HandoffTests.test_manifest_assessment_change_is_not_silently_adopted) ... ok
test_markup_is_displayed_as_text_and_unicode_is_retained (test_handoff.HandoffTests.test_markup_is_displayed_as_text_and_unicode_is_retained) ... ok
test_normalized_sources_downloads_and_line_hashes_agree (test_handoff.HandoffTests.test_normalized_sources_downloads_and_line_hashes_agree) ... ok
test_real_cli_exports_and_verifies_and_default_classification_is_unspecified (test_handoff.HandoffTests.test_real_cli_exports_and_verifies_and_default_classification_is_unspecified) ... ok
test_resealed_reader_cannot_replace_recomputed_artifact (test_handoff.HandoffTests.test_resealed_reader_cannot_replace_recomputed_artifact) ... ok
test_same_declared_inputs_produce_identical_payloads_without_mutation (test_handoff.HandoffTests.test_same_declared_inputs_produce_identical_payloads_without_mutation) ... ok
test_source_package_tamper_rejected_even_with_updated_inventory (test_handoff.HandoffTests.test_source_package_tamper_rejected_even_with_updated_inventory) ... ok
test_source_snapshot_tampering_is_rejected (test_handoff.HandoffTests.test_source_snapshot_tampering_is_rejected) ... ok
test_stale_status_uses_explicit_as_of_and_threshold (test_handoff.HandoffTests.test_stale_status_uses_explicit_as_of_and_threshold) ... ok
test_static_reader_contains_filter_controls_without_external_assets (test_handoff.HandoffTests.test_static_reader_contains_filter_controls_without_external_assets) ... ok

----------------------------------------------------------------------
Ran 15 tests in 0.437s

OK
```

## Direct optimized invocation

Command:

```sh
python3 -B -O -m unittest discover -s tests -p test_handoff.py -v
```

Execution-tool chunk `20b9bc`; exit code **0**.

```text
test_canonical_four_files_remain_byte_identical_to_retained_core (test_handoff.HandoffTests.test_canonical_four_files_remain_byte_identical_to_retained_core) ... ok
test_conflict_unknown_and_decided_states_survive_handoff (test_handoff.HandoffTests.test_conflict_unknown_and_decided_states_survive_handoff) ... ok
test_exact_workspace_bytes_and_all_payload_hashes_are_bound (test_handoff.HandoffTests.test_exact_workspace_bytes_and_all_payload_hashes_are_bound) ... ok
test_existing_directory_symlink_and_dangling_symlink_are_refused (test_handoff.HandoffTests.test_existing_directory_symlink_and_dangling_symlink_are_refused) ... ok
test_existing_output_directory_or_file_is_preserved (test_handoff.HandoffTests.test_existing_output_directory_or_file_is_preserved) ... ok
test_manifest_assessment_change_is_not_silently_adopted (test_handoff.HandoffTests.test_manifest_assessment_change_is_not_silently_adopted) ... ok
test_markup_is_displayed_as_text_and_unicode_is_retained (test_handoff.HandoffTests.test_markup_is_displayed_as_text_and_unicode_is_retained) ... ok
test_normalized_sources_downloads_and_line_hashes_agree (test_handoff.HandoffTests.test_normalized_sources_downloads_and_line_hashes_agree) ... ok
test_real_cli_exports_and_verifies_and_default_classification_is_unspecified (test_handoff.HandoffTests.test_real_cli_exports_and_verifies_and_default_classification_is_unspecified) ... ok
test_resealed_reader_cannot_replace_recomputed_artifact (test_handoff.HandoffTests.test_resealed_reader_cannot_replace_recomputed_artifact) ... ok
test_same_declared_inputs_produce_identical_payloads_without_mutation (test_handoff.HandoffTests.test_same_declared_inputs_produce_identical_payloads_without_mutation) ... ok
test_source_package_tamper_rejected_even_with_updated_inventory (test_handoff.HandoffTests.test_source_package_tamper_rejected_even_with_updated_inventory) ... ok
test_source_snapshot_tampering_is_rejected (test_handoff.HandoffTests.test_source_snapshot_tampering_is_rejected) ... ok
test_stale_status_uses_explicit_as_of_and_threshold (test_handoff.HandoffTests.test_stale_status_uses_explicit_as_of_and_threshold) ... ok
test_static_reader_contains_filter_controls_without_external_assets (test_handoff.HandoffTests.test_static_reader_contains_filter_controls_without_external_assets) ... ok

----------------------------------------------------------------------
Ran 15 tests in 1.580s

OK
```

## Repository discovery bridge

Command:

```sh
python3 -B -m unittest test_civic_portable_handoff.py -v
```

Execution-tool chunk `084167`; exit code **0**. The one bridge method invokes only the 15-test handoff suite in the component directory and fails if the child returns nonzero. It does not rerun the original core suite.

```text
test_component_suite (test_civic_portable_handoff.CivicPortableHandoffSuite.test_component_suite) ... ok

----------------------------------------------------------------------
Ran 1 test in 0.437s

OK
```

## Final optimized repository bridge

This single additional run was requested to check the changed optimization-forwarding path on the final published test bytes. It was not a repeat of the original core suite or a rerun merely to preserve logs.

Command, from the repository root:

```sh
python3 -B -O -m unittest test_civic_portable_handoff -v
```

Execution-tool chunk `782874`; exit code **0**. Runtime remained `bed0659a3b622368f4c7f48b203c1bdd4fc65894`, component tests `56461284edf6bc78cd5c2f07d409d8921225b5d8`, and bridge `5290743958455c8e0b98c64a60ffe7a3fc0f6153`. The bridge invokes the focused 15-test suite with `-O`; no `-OO` execution is claimed.

```text
test_component_suite (test_civic_portable_handoff.CivicPortableHandoffSuite.test_component_suite) ... ok

----------------------------------------------------------------------
Ran 1 test in 1.318s

OK
```

## Scope of the accepted checks

The tests cover native four-file byte compatibility; exact workspace retention and payload hashes; normalized source downloads, line hashes and anchors; conflict, unknown and decided states; an explicit stale assessment; Unicode and literal markup display; static filter-control structure; actual CLI export and verification; source, receipt and resealed derived-artifact tampering; existing files, directories and symlinks; and deterministic exports without input mutation.

The CLI test also starts the copied verifier from inside the output directory using `python -B -m civic_ledger.handoff verify --output-dir .`, checks success, and checks that the payload inventory remains unchanged. Keep `-B` in this command: Python may otherwise write package caches before the module's bytecode setting takes effect. The check is reproduction and integrity under the stated invocation, not attestation of arbitrary interpreter behavior.

Source review found no defect within this bounded scope. Static HTML assertions establish the presence of controls, safe text rendering, embedded downloads and source anchors; no browser session or interaction test was performed. Previously accepted original core tests were not rerun.
