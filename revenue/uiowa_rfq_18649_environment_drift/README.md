# Environment consistency and drift assessment kit

UIOWA-061 / `uiowa-061-basalt-20260919` / ZZ-BASALT-61 (GPT-6 Astra Pro).

This is an offline preparation instrument, not an assessment of University systems. The fixture is entirely fictional. No live environment is contacted or changed, source locator is fetched, secret is requested, or deployment permission is granted. The tool establishes consistency of supplied records, not their authenticity or completeness. It does not assign a maturity score or infer that a difference caused a defect.

## Run and reuse

Python 3.10+; standard library only. From this directory:

```sh
python drift.py synthetic.json --format markdown
python drift.py synthetic.json --format json --output new-report.json
python -m unittest discover -s . -p 'test_drift.py' -v
```

A valid packet returns exit 0 even when observations are unknown or differences need investigation. Malformed input or an output-write problem returns exit 2 with a diagnostic. An existing output is never overwritten, and the input path cannot be used as output. Inputs over 4 MB, non-finite numbers and duplicate JSON keys are rejected. There is no network, subprocess, or shell-evaluation path in the evaluator. Stdout can be redirected when overwrite behavior is deliberately managed by the caller.

`test_drift.packet()` also creates a fresh editable fixture; the checked-in `synthetic.json` is its serialized form. Tests load the adjacent evaluator by an isolated module name to avoid collisions with other swarm modules.

## Editable packet contract (schema version 1)

The executable validator is `validate()` in `drift.py`. Unknown extension fields are retained in input hashing but do not affect the current comparison. Do not use unrecognized fields as evidence of an implemented assessment rule.

| Field | Contract |
|---|---|
| `schema_version` | Integer `1`, not boolean. |
| `label` | Nonempty provenance/context label. Synthetic material must say so. |
| `as_of` | Explicit ISO date `YYYY-MM-DD`; no dependence on the machine clock. |
| `max_age_days` | Integer 0–3660; a stated assessment assumption, not a universal freshness rule. |
| `environments` | At least two unique IDs; the example uses development, test, staging, production. |
| `baseline` | One of the declared environment IDs. A comparison reference, not an assertion that it is correct. |
| `evidence` | Records with unique `id`, `kind` (`artifact` or `statement`), `captured_on`, and nonempty `locator`. Future-dated records are malformed. Locators are not fetched. |
| `checks` | Nonempty list with unique IDs. Each declares `group`, `service`, `dimension`, `key`, `impact`, `owner_role`, and a nonnegative ordered `effort_hours` range. Impact, owner, and effort are proposed inputs, not measured findings or staff commitments. |
| `checks[].values` | Map from known environment IDs to observations. Missing environments remain missing; unknown environment names are rejected as likely typos. |
| Observation | `state` is `observed`, `unknown`, or `not_applicable`. Observed requires `value`, including explicit JSON null when meaningful. Unknown/NA requires `reason` and cannot carry `value`. Optional `evidence_id` links an artifact; missing/unresolved links remain diagnostic. |
| `checks[].intentions` | Optional history of intentional-difference records. Each has unique `id` within its check, target `environment`, both expected `value` and `baseline_value`, `reason`, `owner_role`, `evidence_id`, `valid_from`, and `review_on`. The target cannot be the baseline; validity dates must be ordered. |

IDs begin with a letter and use letters, digits, underscore, dot, colon or hyphen, at most 80 characters. Values may be finite JSON scalars, arrays or objects. Equality is exact canonical JSON equality: object-key ordering is irrelevant; array ordering, value types and number representation matter. Thus `true`, `1`, `1.0` and `"1"` are distinct. Null is not an alias for unknown. Normalize version strings or units deliberately before import; the tool does not guess equivalence.

Use configuration metadata only: runtime/component versions, feature modes, build labels, provisioning references and purpose-bound nonsecret settings. Do not put tokens, passwords, personal records, or production data in packets. A hash of low-entropy sensitive data is not adequate anonymization. Keep real evidence in its approved storage boundary; an ID/locator is sufficient for this worksheet.

## Interpretation rules

| Status | What the supplied records establish | Practical next step |
|---|---|---|
| `ALIGNED` | Both observed values have current artifact references and equal typed values. | Ask whether the relevant behavior was actually tested. Equal settings are not functional equivalence. |
| `INTENTIONAL_DIFFERENCE` | Current differing observations match exactly one currently valid, artifact-supported explanation of both values. | Preserve purpose, accountable role and review date; seek behavioral evidence before concluding it is adequate. |
| `UNEXPLAINED_DIFFERENCE` | Current observed values differ without a current supported matching explanation. | Determine necessity and consequence. Do not automatically remove the difference or call it a defect. |
| `EXPLANATION_REVIEW_DUE` | Differing values match supported explanations whose review dates have passed, with no current supported explanation. | Review the rationale and both expected values; a passed review date does not itself prove operational failure. |
| `UNKNOWN` | Observation/reference missing or stale, a statement is the only support, or multiple current matching explanations are ambiguous. | Request a focused current artifact or reconcile explanations. Do not convert this to a low score. |
| `NOT_APPLICABLE` | Target has a current artifact-supported non-applicability reason. | Check that the stated service/environment scope is still appropriate. |
| `NOT_COMPARABLE` | Target has a current observation, but the baseline has current supported non-applicability. | Choose another reference or a behavior-based comparison. |

Snapshot age is checked for observed and NA records, inclusively: an age equal to `max_age_days` is current. An intentional-difference record is assessed by its explicit inclusive validity/review window rather than the snapshot age threshold; a July decision can still explain a September difference. An uncorroborated statement never establishes observed parity or intentionality. Rationale records must bind both target and baseline values; an explanation for an older baseline cannot silently cover a new baseline.

A target with evidenced non-applicability is not assessed against an unavailable baseline. Unknown target and unknown baseline diagnostics are both retained. An evidenced NA baseline with an observed target is not comparable. Multiple active matching rationales remain unknown even if their text appears similar; a reviewer resolves the history rather than the tool choosing one.

## Worked fictional exercise and expected results

The ready-to-run packet has seven checks and three non-baseline environments per check: 21 comparisons across fictional ESS, RIS and IAM services. Expected counts are **4 aligned, 2 intentional differences, 2 unexplained differences, 1 explanation review due, 9 unknown, 2 not applicable and 1 not comparable**. Nine comparisons have current comparable observations; the other twelve are explicitly outside that denominator. These are fixture assertions, not organizational measurements.

ESS demonstrates an intentional older development runtime, an unexplained database-version difference, an expired staging explanation and an absent production reference. RIS demonstrates boolean-versus-integer configuration drift, an unreceived export, and equal settings supported only by a statement or an absent artifact. IAM demonstrates a deliberate reduced topology, stale equal settings and a baseline to which a development-only mock does not apply.

Run the rehearsal in three passes. First, read the environment matrix and explain why each status follows from the cited fixture record. Second, use the follow-up worksheet to request one proportionate missing artifact or decision per unknown/difference, identifying a proposed organizational role and an effort range. Third, modify the relevant fixture evidence and rerun; verify that only supportable conclusions change. Never relabel a synthetic packet as supplied University evidence.

## Interview and improvement worksheet

| Prompt | Evidence to seek | Proportionate improvement and dependency |
|---|---|---|
| Which differences exist because environments have different purposes? | Paired dated snapshots plus a purpose/constraint record binding both values. | Capture a lightweight exception record; needs a maintainer and test-purpose agreement. |
| How are environment versions provisioned and reproduced? | Build/configuration reference and a recent reconstruction example. | Record the inputs used for one representative service before expanding automation; requires accessible nonsecret metadata. |
| When did a production behavior differ from a passing test? | Specific change, test behavior and contemporaneous environment observations. | Add a targeted contract/behavior check after reproducing the cause; do not assume configuration alone explains it. |
| Which records depend on staff recollection? | Missing source IDs, stale exports and interview statements kept distinct. | Assign artifact ownership and an appropriate refresh interval; agree the evidence window first. |
| Which deliberate differences have not been reviewed? | Rationale dates, both expected values and operational owner role. | Review necessary differences together by service; avoid blanket environment cloning. |
| Can a different analyst repeat the comparison? | Exact input, source locators, reported input digest and command/version. | Preserve a read-only packet and an explicit handoff; needs approved evidence storage, not a new commercial platform. |

Markdown output contains the environment matrix, follow-up worksheet, every applicable explanation record and the supplied evidence register. JSON retains the observations, reasons, all rationale candidates, diagnostics and source IDs, including unresolved IDs. Values are HTML-escaped and table delimiters/newlines are handled in Markdown. Follow-up ordering is stable by check/environment, not a hidden priority or risk score. Effort ranges are per proposed investigation row and must not be summed as a project budget without deduplicating shared work.

The canonical input SHA-256 is a reproducibility fingerprint (sorted object keys; array order retained), not a signature or authenticity proof. Reordering input records can change that fingerprint while leaving the comparison rows unchanged. Capture periods, selection bias and completeness of real source exports require human assessment; this tool cannot verify them.

## Integration seam and boundaries

This package is independent of the existing assessment compiler/workbench. Consumers may link `check_id`, `group`, `service`, evidence IDs/locators, status and questions into an assessment cell without translating them into a numeric maturity rating. `impact_hypothesis` must remain a hypothesis until triangulated; `effort_hours_assumption` must remain an estimate. Missing evidence is not evidence of absence. No adapter into another package is claimed to exist yet.

32 regression tests cover the rehearsal, date boundaries, type distinctions, missing/stale evidence, rationale windows and ambiguity, input validation, rendering, determinism and no-overwrite CLI behavior. This is scoped kit validation, not a claim that the entire Commons test suite passes. Build/task context is the UIOWA-061 work order; all assessment rules and synthetic cases here are proposed design, not a standard, policy mandate, or empirical benchmark.
