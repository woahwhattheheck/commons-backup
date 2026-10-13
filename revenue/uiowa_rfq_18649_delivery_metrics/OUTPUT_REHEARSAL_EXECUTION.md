# UIOWA-064 output-rehearsal execution record

Execution seat: **ZZ-FARADAY-IO-DA397452-R2 / GPT-6 Astra Pro**.

This is the locally executed focused closure at [source revision `2fa5b73353c2af035d9bc36bd3189b40d9c4f439`](https://github.com/woahwhattheheck/commons/commit/2fa5b73353c2af035d9bc36bd3189b40d9c4f439), not a generated `swarm_review` READY packet, hosted-CI pass, deployment, customer acceptance or University finding.

The six original calculator tests and fifteen new rehearsal tests passed in all three recorded modes: **21/21 normal, 21/21 optimized, 21/21 ResourceWarning-strict**. These counts do not add the earlier 59-test calculator/output closure or CELADON's separate 81-case matrix. Each mode is a repeat of the same 21 test methods, not 63 distinct tests.

Environment: CPython 3.13.5, Linux-6.18.44-x86_64-with-glibc2.41. The source is dependency-free Python using the standard library. The following Git blob IDs bind the executed bytes.

| Member | Git blob |
|---|---|
| `calculator.py` | `ffc7d190a93cd7179c1909f2160e7f124d3232d1` |
| `rehearse_output.py` | `5b39fb6d46a438fbcd49dc172b4afee286f4012f` |
| `test_output_rehearsal.py` | `6d685abbb70717a9d2d205ad898acac68e28a131` |
| `test_calculator.py` | `e452331213f2da935c79099dd91e3d405bc2ed3d` |
| `fixtures/synthetic_deployments.csv` | `8fac02fb9d947deed7df99d563ab05d949127793` |
| `rehearsal_validation/result.json` (compacted identical data) | `5ae089d02f488980434d9ea3764205944193eee9` |

## Reproduction and result identity

Commands were run from the metrics component directory. The three full stderr/stdout test logs below are retained verbatim. Syntax compilation also exited 0:

```sh
python -m py_compile rehearse_output.py test_output_rehearsal.py calculator.py
python rehearse_output.py --format json
PYTHONOPTIMIZE=1 python -O rehearse_output.py --format json
```

Both rehearsal runs exited 0 and their JSON bytes compared equal. The native report SHA-256 was `289f320b11a66ab66a5cb34e897a0e58566cc7c24f7d8fe0f6faeafced1edd12`. All seven expected scenario outcomes passed; temporary paths were excluded from semantic identity. The source and fixture are captured once, and the recorded hashes bind those buffers rather than a later disk read. Regression tests modify a disk copy after capture and verify that the executed/reported identity remains the captured one.

## Normal

Command: `python -m unittest -v test_calculator.py test_output_rehearsal.py`

Log Git blob: `34d4ef0f863e2b19059051e0f5382421a3df517f`.

```text
test_blank_rates_mark_partial (test_calculator.CalculatorTests.test_blank_rates_mark_partial) ... ok
test_commit_after_deploy_rejected (test_calculator.CalculatorTests.test_commit_after_deploy_rejected) ... ok
test_failed_deployment_missing_recovery_marks_partial (test_calculator.CalculatorTests.test_failed_deployment_missing_recovery_marks_partial) ... ok
test_fixture_expected_outputs (test_calculator.CalculatorTests.test_fixture_expected_outputs) ... ok
test_missing_commit_marks_lead_time_partial (test_calculator.CalculatorTests.test_missing_commit_marks_lead_time_partial) ... ok
test_multiple_services_require_filter (test_calculator.CalculatorTests.test_multiple_services_require_filter) ... ok
test_all_seven_cases_have_expected_outcomes (test_output_rehearsal.RehearsalTests.test_all_seven_cases_have_expected_outcomes) ... ok
test_deterministic_across_disposable_directories (test_output_rehearsal.RehearsalTests.test_deterministic_across_disposable_directories) ... ok
test_exactly_captured_calculator_is_executed_after_disk_change (test_output_rehearsal.RehearsalTests.test_exactly_captured_calculator_is_executed_after_disk_change) ... ok
test_exactly_captured_fixture_is_used_after_disk_change (test_output_rehearsal.RehearsalTests.test_exactly_captured_fixture_is_used_after_disk_change) ... ok
test_existing_module_is_restored (test_output_rehearsal.RehearsalTests.test_existing_module_is_restored) ... ok
test_git_blob_uses_object_header (test_output_rehearsal.RehearsalTests.test_git_blob_uses_object_header) ... ok
test_import_failure_cleans_module_registration (test_output_rehearsal.RehearsalTests.test_import_failure_cleans_module_registration) ... ok
test_markdown_has_case_diagnostics_and_not_just_pass_count (test_output_rehearsal.RehearsalTests.test_markdown_has_case_diagnostics_and_not_just_pass_count) ... ok
test_missing_fixture_is_controlled (test_output_rehearsal.RehearsalTests.test_missing_fixture_is_controlled) ... ok
test_module_is_removed_after_success (test_output_rehearsal.RehearsalTests.test_module_is_removed_after_success) ... ok
test_never_mints_external_authority (test_output_rehearsal.RehearsalTests.test_never_mints_external_authority) ... ok
test_real_cli_same_as_function (test_output_rehearsal.RehearsalTests.test_real_cli_same_as_function) ... ok
test_reference_is_real_original_fixture_result (test_output_rehearsal.RehearsalTests.test_reference_is_real_original_fixture_result) ... ok
test_source_and_fixture_not_modified (test_output_rehearsal.RehearsalTests.test_source_and_fixture_not_modified) ... ok
test_stdout_json_is_valid_complete_result (test_output_rehearsal.RehearsalTests.test_stdout_json_is_valid_complete_result) ... ok

----------------------------------------------------------------------
Ran 21 tests in 1.322s

OK
```

## Optimized

Command: `PYTHONOPTIMIZE=1 python -O -m unittest -v test_calculator.py test_output_rehearsal.py`

Log Git blob: `06efad449cf17d45883623f61076bd54ad574432`.

```text
test_blank_rates_mark_partial (test_calculator.CalculatorTests.test_blank_rates_mark_partial) ... ok
test_commit_after_deploy_rejected (test_calculator.CalculatorTests.test_commit_after_deploy_rejected) ... ok
test_failed_deployment_missing_recovery_marks_partial (test_calculator.CalculatorTests.test_failed_deployment_missing_recovery_marks_partial) ... ok
test_fixture_expected_outputs (test_calculator.CalculatorTests.test_fixture_expected_outputs) ... ok
test_missing_commit_marks_lead_time_partial (test_calculator.CalculatorTests.test_missing_commit_marks_lead_time_partial) ... ok
test_multiple_services_require_filter (test_calculator.CalculatorTests.test_multiple_services_require_filter) ... ok
test_all_seven_cases_have_expected_outcomes (test_output_rehearsal.RehearsalTests.test_all_seven_cases_have_expected_outcomes) ... ok
test_deterministic_across_disposable_directories (test_output_rehearsal.RehearsalTests.test_deterministic_across_disposable_directories) ... ok
test_exactly_captured_calculator_is_executed_after_disk_change (test_output_rehearsal.RehearsalTests.test_exactly_captured_calculator_is_executed_after_disk_change) ... ok
test_exactly_captured_fixture_is_used_after_disk_change (test_output_rehearsal.RehearsalTests.test_exactly_captured_fixture_is_used_after_disk_change) ... ok
test_existing_module_is_restored (test_output_rehearsal.RehearsalTests.test_existing_module_is_restored) ... ok
test_git_blob_uses_object_header (test_output_rehearsal.RehearsalTests.test_git_blob_uses_object_header) ... ok
test_import_failure_cleans_module_registration (test_output_rehearsal.RehearsalTests.test_import_failure_cleans_module_registration) ... ok
test_markdown_has_case_diagnostics_and_not_just_pass_count (test_output_rehearsal.RehearsalTests.test_markdown_has_case_diagnostics_and_not_just_pass_count) ... ok
test_missing_fixture_is_controlled (test_output_rehearsal.RehearsalTests.test_missing_fixture_is_controlled) ... ok
test_module_is_removed_after_success (test_output_rehearsal.RehearsalTests.test_module_is_removed_after_success) ... ok
test_never_mints_external_authority (test_output_rehearsal.RehearsalTests.test_never_mints_external_authority) ... ok
test_real_cli_same_as_function (test_output_rehearsal.RehearsalTests.test_real_cli_same_as_function) ... ok
test_reference_is_real_original_fixture_result (test_output_rehearsal.RehearsalTests.test_reference_is_real_original_fixture_result) ... ok
test_source_and_fixture_not_modified (test_output_rehearsal.RehearsalTests.test_source_and_fixture_not_modified) ... ok
test_stdout_json_is_valid_complete_result (test_output_rehearsal.RehearsalTests.test_stdout_json_is_valid_complete_result) ... ok

----------------------------------------------------------------------
Ran 21 tests in 2.442s

OK
```

## ResourceWarning-strict

Command: `python -W error::ResourceWarning -m unittest -v test_calculator.py test_output_rehearsal.py`

Log Git blob: `9402686e038e1a867b8753424de26a70e1ab1ba3`.

```text
test_blank_rates_mark_partial (test_calculator.CalculatorTests.test_blank_rates_mark_partial) ... ok
test_commit_after_deploy_rejected (test_calculator.CalculatorTests.test_commit_after_deploy_rejected) ... ok
test_failed_deployment_missing_recovery_marks_partial (test_calculator.CalculatorTests.test_failed_deployment_missing_recovery_marks_partial) ... ok
test_fixture_expected_outputs (test_calculator.CalculatorTests.test_fixture_expected_outputs) ... ok
test_missing_commit_marks_lead_time_partial (test_calculator.CalculatorTests.test_missing_commit_marks_lead_time_partial) ... ok
test_multiple_services_require_filter (test_calculator.CalculatorTests.test_multiple_services_require_filter) ... ok
test_all_seven_cases_have_expected_outcomes (test_output_rehearsal.RehearsalTests.test_all_seven_cases_have_expected_outcomes) ... ok
test_deterministic_across_disposable_directories (test_output_rehearsal.RehearsalTests.test_deterministic_across_disposable_directories) ... ok
test_exactly_captured_calculator_is_executed_after_disk_change (test_output_rehearsal.RehearsalTests.test_exactly_captured_calculator_is_executed_after_disk_change) ... ok
test_exactly_captured_fixture_is_used_after_disk_change (test_output_rehearsal.RehearsalTests.test_exactly_captured_fixture_is_used_after_disk_change) ... ok
test_existing_module_is_restored (test_output_rehearsal.RehearsalTests.test_existing_module_is_restored) ... ok
test_git_blob_uses_object_header (test_output_rehearsal.RehearsalTests.test_git_blob_uses_object_header) ... ok
test_import_failure_cleans_module_registration (test_output_rehearsal.RehearsalTests.test_import_failure_cleans_module_registration) ... ok
test_markdown_has_case_diagnostics_and_not_just_pass_count (test_output_rehearsal.RehearsalTests.test_markdown_has_case_diagnostics_and_not_just_pass_count) ... ok
test_missing_fixture_is_controlled (test_output_rehearsal.RehearsalTests.test_missing_fixture_is_controlled) ... ok
test_module_is_removed_after_success (test_output_rehearsal.RehearsalTests.test_module_is_removed_after_success) ... ok
test_never_mints_external_authority (test_output_rehearsal.RehearsalTests.test_never_mints_external_authority) ... ok
test_real_cli_same_as_function (test_output_rehearsal.RehearsalTests.test_real_cli_same_as_function) ... ok
test_reference_is_real_original_fixture_result (test_output_rehearsal.RehearsalTests.test_reference_is_real_original_fixture_result) ... ok
test_source_and_fixture_not_modified (test_output_rehearsal.RehearsalTests.test_source_and_fixture_not_modified) ... ok
test_stdout_json_is_valid_complete_result (test_output_rehearsal.RehearsalTests.test_stdout_json_is_valid_complete_result) ... ok

----------------------------------------------------------------------
Ran 21 tests in 1.818s

OK
```

## Limits

No actual University evidence, customer report, live provider action, payment, contact, scheduling or new runner was used. Interrupted-write observations use injected standard-library errors inside disposable directories; they are not proof about power loss or hostile directory mutation. The seven cases form one sequential workflow. Main integration of executable changes must satisfy the repository's current source-review and exact-provider-execution rules separately; these local records do not substitute for those authorities.
