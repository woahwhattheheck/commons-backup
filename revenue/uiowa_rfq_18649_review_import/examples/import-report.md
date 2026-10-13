SYNTHETIC DEMONSTRATION — NOT UNIVERSITY FINDINGS

# Reviewer-comment import

Import readiness is not a review decision or acceptance.

Source: comments.csv
Source SHA-256: 9165b39f3bc0571ae77a8532ef7a4b69e7625c1471928a9c09e4bc4a73cd90d3

```json
{
  "input_records": 9,
  "unique_comments": 6,
  "ready": 2,
  "unresolved": 4,
  "unkeyed_rows": 1
}
```

## REV-SYN-01 — READY

### Original comment

> The word &quot;always&quot; exceeds this example.
> Please retain the exception — it matters.

Source occurrences: record 1, physical lines 2-3; record 3, physical lines 5-6

Diagnostics: none

## REV-SYN-02 — READY

### Original comment

> Please attach the actual support record.

Source occurrences: record 2, physical lines 4-4

Diagnostics: none

## REV-SYN-03 — UNRESOLVED

### Original comment

> Which team&#x27;s finding is this?

Source occurrences: record 4, physical lines 7-7

Diagnostics: AMBIGUOUS_FINDING

## REV-SYN-04 — UNRESOLVED

### Original comment

> This review was written against the old report.

Source occurrences: record 5, physical lines 8-8

Diagnostics: VERSION_MISMATCH

## REV-SYN-05 — UNRESOLVED

### Original comment

> No matching finding was supplied.

Source occurrences: record 6, physical lines 9-9

Diagnostics: UNKNOWN_FINDING

## REV-SYN-06 — UNRESOLVED

### Original comment

> Keep both interpretations.

Source occurrences: record 7, physical lines 10-10

### Original comment

> Replace that comment without recording the change.

Source occurrences: record 8, physical lines 11-11

Diagnostics: COMMENT_CONTENT_CONFLICT

## Unkeyed source record 9

MISSING_VALUE: comment_id. Full source content retained in JSON.
