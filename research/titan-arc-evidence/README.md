# Titan ARC saved-run analyzer

This command turns the seven preserved aptitude runs into separate run summaries and matched question comparisons. It reads the original trace, configuration and summary files, and optionally the existing v2 regrading record. No model runtime or package installation is required.

The implementation is a portable JavaScript module with a Node.js command-line adapter. Node.js 18 or later is sufficient. The module's analysis path runs in a JavaScript runtime without filesystem access; the adapter reads the supplied files and writes JSON or Markdown.

## Run

Extract the three preserved result archives into directories containing each run's config.json, summary.json and trace.jsonl. Supply the original labels:

~~~sh
node analyze_runs.cjs \
  --run aptitude-v1-baseline=/data/baseline \
  --run aptitude-v1-development-thinking256=/data/development-thinking256 \
  --run aptitude-v1-holdout-thinking0=/data/holdout-thinking0 \
  --run aptitude-v1-holdout-thinking256=/data/holdout-thinking256 \
  --run aptitude-v1-development-check-first=/data/development-check-first \
  --run aptitude-v1-development-reversal-check-first=/data/reversal-check-first \
  --run aptitude-v1-holdout-check-first=/data/holdout-check-first \
  --regrade /data/aptitude-v2-regrade.json \
  --format json --output aggregate.json
~~~

Use --format markdown for the readable comparison. Omit --output to write to standard output. An existing output file is preserved; choose a new filename. --help describes the arguments. Errors print a diagnostic to standard error and set exit code 2.

A single run can also be analyzed. Comparisons explicitly list missing conditions until every matching run is supplied.

## What the output contains

- Per-run trace hash, byte count, recorded controls and source digests.
- Original semantic, contract and parse counts; the separate v2 counts when its record is supplied.
- Question-generation time, complete world outcomes and the actual accepted/rejected action sequence.
- The same twelve selected development IDs across the baseline, thinking and check-first conditions.
- The same reserved question IDs across all three reserved conditions.
- Bookkeeping totals for requests, question attempts, world decisions and generation time. Accuracy remains separated by condition.

Trace hashes and byte counts must match their saved summaries. The reader rejects duplicate JSON keys, non-finite numbers, duplicate operation/case IDs, unmatched request/response records, inconsistent episode summaries and mismatched comparison IDs or controls. Raw model output remains a string: a malformed generated answer is an observed result, not a malformed outer trace.

The optional v2 record is applied only after its trace hash, original counts, raw response and original grade match the saved run. It reads recorded grades and never executes generated code. Original scores are retained beside v2 scores.

The output excludes prompts, responses, notebook text, model paths and local input paths. It includes aggregate counts and recorded action names.

## ARC v7

--v7-final accepts a JSON object with source_type cloud_final_response, the original task/message identifiers, reported episode totals and archive/trace identities. This records the original final response separately. It never marks a raw trace available merely because the final response gives its hash.

The original final response was recovered on September 30. The recovered VM could not find the archive or trace at their original paths or elsewhere in its workspace. The direct project profile remains the recorded default.

## Execution

observed-20260930.json and observed-20260930.md were produced from all seven real saved runs using the exported analysis function in a V8 isolate. The function verified every trace hash, applied the existing v2 record and returned 170 calls, 108 question attempts and 62 world decisions. The Node filesystem/CLI adapter was not executed during that run.

No new inference, grader execution, test battery or CI workflow was used. The original model run times are reported as saved measurements; they are not analyzer execution times.

This implements the usable aggregation portion of issue #14081. Raw input archives and the v2 record remain outside Git.
