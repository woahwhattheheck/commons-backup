# Portable AI lifecycle investigation reader

`review_html.py` turns the **existing UIOWA-079 input record** into one linked,
script-free HTML document. It calls the canonical `lifecycle.load()` and
`lifecycle.analyze()` functions rather than trusting an imported report or
introducing a second scoring engine. The JSON, Markdown, CSV, and schema
entrypoints in `lifecycle.py` are unchanged.

## Generate and open a review

Python 3.10+ and the standard library are sufficient. From this directory, use a
new working directory for the existing fictional example:

```sh
work="$(mktemp -d)"
python synthetic.py > "$work/history.json"
python review_html.py "$work/history.json" --output "$work/review.html" --include-artifact-text
```

Open `review.html` with a browser that permits local files. No server, account,
model, JavaScript, external asset, or network connection is needed by the
resulting document. On Windows, substitute a new writable directory for the
`mktemp` command. The renderer also works from the repository root:

```sh
python -m revenue.uiowa_rfq_18649_ai_lifecycle.review_html history.json --output review-new.html
```

The input must be original lifecycle metadata, not the analyzer's projected
`report.json`. A path or `-` for standard input is accepted. UTF-8 input is bounded
to 16 MiB and passes the existing duplicate-key, shape, reference, chronology,
and artifact-integrity checks before any output file is created.

The destination must not exist. There is no overwrite/force option; existing
files, input aliases, and final-component symbolic links are refused by exclusive
creation. Parent directories are not silently created. On POSIX, the new output
is created with owner-only permissions subject to the process umask. A write or
disk error may leave an incomplete newly created output: exit 2 is not a valid
report, and the diagnostic does not promise rollback. This is accidental-output
protection, not protection from a concurrent actor replacing directory ancestors.

## Walk the investigation, not just the average

Start at **Review focus**. Its four lists link to existing analyzer findings:
version reproduction gaps, runs with missing metric values, incomparable/subset
comparisons, and open or unsupported-resolution incidents. Empty lists do not
establish source completeness or permission to deploy.

Follow a version to its parent, model revision, support role, seed, eight
component references, recorded evidence states, and associated runs/replays.
Follow an artifact reference to its locator, supplied digest, retention declaration,
and reverse links to the versions, runs, cases, or events that use it. Locators
remain literal text; none is fetched or made into an external hyperlink.

For a run, read the known/expected/missing counts beside each mean, then the table
of **all expected cases**, including missing observations. Follow the case to its
input and expected-answer artifacts, and follow a supplied output to its text.
`UNKNOWN`, empty text, `False`, and numeric zero remain different values.

For a comparison, inspect its explicit baseline/candidate, changed components,
coverage, and excluded case IDs. An incomparable result displays the parent's
reasons instead of manufacturing a delta. Each available delta retains its paired
and expected denominators, units, and better direction. No favorable run is
silently selected and no comparison becomes an approval.

Follow incident → resolution → related runs and evidence. The reader preserves
`resolution_recorded_with_evidence`, `resolution_claim_without_evidence`, and
`open` rather than declaring an incident independently fixed. Recorded replay
outcomes remain finite supplied-output comparisons, not fresh model execution.

The existing fictional history demonstrates these distinctions: `r2` has a
recorded timeout and unknown answer-quality values, `changed-evaluation` is
incomparable, the repaired version's repeated output differs for one case,
`incident1` has a linked resolution, and `incident2` remains open. None is an
observation about the University of Iowa or a deployed model.

## Sharing and printing

Artifact text is **omitted by default**. `--include-artifact-text` includes every
supplied inline artifact, including prompts, inputs, expected answers, outputs,
and investigations. The banner states which mode was used. Sharing an inclusive
HTML file shares that content. Even an export without artifact text still contains
metadata, observations, summaries, and locators; it is not automatic redaction.
Keep real confidential inputs/outputs outside this source repository and share
only through the engagement's approved handling route.

The HTML uses escaped text, fragment-only links, native keyboard navigation,
responsive tables, and print styles. Browser Find works without a scripted search
index. The source contains no remote asset or executable record-content path.
Print/export behavior varies by browser; check the chosen print layout before
using it as a delivery document. This change does not claim screen-reader
certification, rendered-browser acceptance, or universal PDF pagination.

Keep the original JSON separately. HTML is a reader view, not lossless JSON
interchange. Its input SHA-256 identifies the supplied bytes only; it establishes
neither authenticity, authorship, approval, nor the truth of observations.

## Execution recorded for this delivery

One end-to-end CLI workflow was executed in the ephemeral Linux cloud container
with CPython 3.13.5: existing `synthetic.py` → original JSON → `review_html.py`
using the unmodified current `lifecycle.py`. It exited 0 and produced a
70,445-byte HTML document from the existing 26,761-byte synthetic input.

The local runtime files were reconstructed from connector reads because direct
GitHub DNS resolution was unavailable. Their Git blob identities matched the
provider before execution: lifecycle `80a49adb4cd80338115e1a9b347757e81e8dc60c`,
synthetic generator `87019c6f0065937c5e9023783721bdbaf9734dd9`, and published reader
`c1a1709d6f371edb5bdb0069c12e3e08ae632c6b`. This is one actual product workflow,
not a full-checkout suite, hosted CI pass, browser test, or model-performance
measurement. No tests, fixtures, snapshots, workflows, dependencies, or receipt
frameworks were added.

Operation: `uiowa079-portable-review-yz-kestrel72-20260923`; work record #19221.
The current analyzer and its original authorship are preserved. Old PR #16224
contains a different implementation and is not overlaid onto this component.
