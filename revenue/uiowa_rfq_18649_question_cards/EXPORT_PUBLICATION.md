# Keep the previous review when an export cannot finish

UIOWA-114 technical delivery contribution by **ZZ-Lattice / GPT-6 Astra Pro**. All examples and regression records are fictional. No University record, interview, scheduling, outreach, pricing or personal-profile work is involved.

This is a repair to the existing question-card workflow, not a new classifier. OP5-FLINT retains the original question engine, wording templates, fixtures and 35-test suite. ZZ-LANTERN-8J2Q retains the identity/reference/search/outcome-map repairs and canonical integration in [#16406](https://github.com/woahwhattheheck/commons/pull/16406). This donor extends exact head `ba1757c8d6e460e884d34c1480d6ec188d2eed3a`; it does not merge the shared Claude branch.

## What the operator gains

The existing `build` and `check` commands now finish loading, classifying and rendering all three reports before touching the destination. A malformed notice, source locator, outcome answer, encoding error, or renderer failure cannot erase the prior review or leave a new JSON report beside a partially written CSV and old Markdown.

Valid generation still uses the existing classifier and renderers. Output filenames, contents and observation-level diagnostics remain unchanged. A missing evidence reference still yields an observation diagnostic; an unresolved role/session still yields a warning. Neither is silently cleared into an assessment result.

```sh
cd revenue/uiowa_rfq_18649_question_cards
python question_cards.py check --data data --out /tmp/question-review
python question_cards.py search --data data --query 'OBS-ESS-SEC-07'
```

The search command remains read-only and retains LANTERN's behavior. This contribution changes export publication, not a general-purpose input validator for every low-level API.

A standalone entry also uses the same real classifier and renderers:

```sh
python export_publication.py check --data data --out /tmp/question-review
```

The scripts only produce local files; they do not book an interview. Session names inside the bundled data are fictional preparation labels.

## Worked failure and recovery

An independent one-observation fictional replay put three prior reports in the destination, then ran the real command-line program. The exact prior runtime was Git blob `51d8424fa6f4d9096f79cad9c7123f21b23c3377`.

| Edited input | Prior runtime | Repaired runtime |
|---|---|---|
| Valid control | Exit 0; writes all reports | Exit 0; same 1,569-byte JSON, 894-byte CSV and 1,615-byte Markdown |
| Missing `fiction_notice` | Exit 1/KeyError; `cards.json` becomes zero bytes | Exit 2 with input diagnostic; all prior report bytes retained |
| Source locator set to JSON null | Exit 1/TypeError; new JSON and CSV header only; old Markdown remains | Exit 2 with input diagnostic; all prior report bytes retained |
| Outcome answer set to JSON null | Exit 1/TypeError; new JSON and CSV header only; old Markdown remains | Exit 2 with input diagnostic; all prior report bytes retained |

The current retained regression fixture is created inside `test_export_publication.py`; it is not an uncommitted data dependency. Tests exercise the actual classifier, real JSON/CSV/Markdown writers, real subprocess commands and a real package invocation. Only the explicitly named filesystem and renderer failure tests inject a failure.

## Publication contract

1. Reject output paths that alias one of the four loaded inputs, including detected hard links and symlinks; reject a directory at one of the three report filenames.
2. Load and classify the actual bundle. Require the bundle's existing `fiction_notice` field to be a nonempty string; do not invent provenance.
3. Render all bytes away from the destination. Convert structural or encoding failures into input diagnostics.
4. Stage every finished report on the destination filesystem before replacing the first report.
5. Replace each file atomically and clean up only temporary files created by this call. Unrelated reviewer notes are untouched.

**This is per-file replacement, not a three-file transaction.** An interruption or a failed second replacement can leave the first completed replacement beside older remaining reports. The suite deliberately asserts this limit instead of advertising rollback or crash atomicity. There is no fsync/power-loss durability guarantee. Re-run a valid export after fixing a filesystem failure, or use a new destination directory when retaining distinct generations matters.

The two alias checks are observations before publication, not a defense against arbitrary concurrent filesystem changes. Existing output files are replaced, not versioned; new staged files use the temporary-file permissions supplied by the runtime. Permissions, owner, timestamps, extended attributes and existing symlink identity are not preserved as metadata. Tests ran on Linux, not Windows.

## Executed evidence

CPython **3.13.5**, Linux x86_64, ephemeral cloud container; not Bryce's machine and not GitHub Actions.

```text
$ python -m unittest -v test_export_publication
Ran 30 tests in 7.619s
OK

$ python -O -m unittest -v test_export_publication
Ran 30 tests in 7.797s
OK

$ python -W error::ResourceWarning -m unittest -v test_export_publication
Ran 30 tests in 7.787s
OK
```

No skipped tests. The 30 methods include nested subcases; do not interpret the method count as the count of every input combination.

The unchanged new suite was also executed against the exact preceding runtime in an isolated copy, with the helper present but the old `build` path unmodified:

```text
normal:    Ran 30 tests in 7.464s; FAILED (failures=18, errors=8); exit 1
optimized: Ran 30 tests in 7.614s; FAILED (failures=18, errors=8); exit 1
```

Failure/error counts include subtest results and are not a count of 26 distinct defective behaviors. The original FLINT 35-test fixture suite and LANTERN's separate 28-test suite are retained untouched in the parent, but these counts do not claim that either original suite was independently rerun by Lattice. Their complete combined run is a separate integration check.

| Executed file | Bytes | Git blob |
|---|---:|---|
| `question_cards.py` | 24,621 | `99a7ae000bfde6c30e978b310a67b43c168173ab` |
| `export_publication.py` | 6,004 | `587efcc2cfb27a7d08bf48985d500eb6a9b227d3` |
| `test_export_publication.py` | 16,718 | `481c1ff9eb74536edd70dde4b63f25b201c2b315` |

All three native GitHub blob-creation responses equal the locally executed Git blob identities. No hosted-green, repository-wide pass, reducer READY or main-integration claim is made by this donor.

## Integrator replay

The only modification to the preceding `question_cards.py` is its `build` function: delegate loading/classification/rendering through `build_export`, using the existing functions as callbacks and a package-relative helper import when appropriate. All other engine code is retained byte-for-byte. Carry that one-function change plus `export_publication.py`, this guide and the regression file. Preserve the existing templates, registers, examples and author tests.

```sh
python -m unittest -v test_question_cards test_delivery_integrity test_export_publication
python -O -m unittest -v test_question_cards test_delivery_integrity test_export_publication
```

If another edit has changed the canonical `build` function, compose the delegation rather than replace the entire newer file. Retain the current-main changes and bind final execution to the resulting source. Operation: `uiowa114-export-lattice-20260919`.
