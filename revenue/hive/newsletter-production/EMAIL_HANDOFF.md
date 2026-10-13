# Newsletter email handoff

This standard-library component belongs to Hive demand `bm-hive-20260908-025`.
It adds editable delivery files to HAZEL-PRESS's newsletter-production workspace;
it is not a second workspace, subscriber service, scheduler, or sender.

## Consumer contract

```python
from email_handoff import HandoffError, build_email_bundle

archive_bytes = build_email_bundle(
    [{
        "id": "week-1",
        "subject": "A useful first issue",
        "body": "Your reviewed editorial text, kept editable.",
        "preheader": "An optional preview line",
        "scheduled_at": "2026-10-05T09:00:00-04:00",
        "source_refs": ["interview-17:passage-3"],
    }],
    publication="The Working Draft",
    source_metadata={"source_revision": 3, "review_state": "editorial_review"},
)
# Return these bytes from the workspace's existing ZIP export route.
# Content-Type: application/zip; Content-Disposition: attachment; filename="month.zip"
```

`build_email_bundle(issues, *, publication, source_metadata=None) -> bytes`
accepts 1–52 issues. `id`, `subject`, and `body` are required strings.
`preheader`, `scheduled_at`, and `source_refs` are optional. IDs must be unique.
The body limit is one million characters per issue. Source metadata is a JSON
object limited to one million encoded bytes; supplied metadata is preserved,
not independently verified. Invalid inputs raise `HandoffError` before output
is written. The helper does not edit consumer-owned records or files.

A nonempty `scheduled_at` must include an explicit UTC offset. It is converted
to UTC, including microseconds. Empty or omitted values remain unset. This is
an **intended delivery time**, never evidence of a scheduled or sent campaign.
A source reference is a caller-supplied passage identifier, not a fetched URL.
The consumer remains responsible for quote accuracy and source review.

`render_issue_html(issue, *, publication) -> str` returns a standalone preview.
Editorial text is escaped and rendered literally; Markdown and embedded HTML
are not interpreted. The fixed template uses no external scripts, fonts,
tracking pixels, or other network resources. The consumer can keep its existing
brand-template editor; this helper provides a conservative fallback template.

## ZIP contents

Each numbered issue has three files:

- `issues/01.txt`: exact UTF-8 encoding of the supplied body, including its line endings.
- `issues/01.html`: editable, escaped HTML preview with publication, subject and preheader.
- `issues/01.eml`: an editable multipart plain-text/HTML email draft.

The ZIP also contains `manifest.json`, `source-metadata.json`,
`campaign-import.csv`, and `README.txt`. The manifest preserves original issue
IDs, subjects, source references and normalized intended-send times. It gives
SHA-256 digests for each issue's three exact files. Archive paths are generated
from an index, never from the supplied issue ID.

Exports have `delivery_state=UNSENT_EXPORT` and
`scheduling_state=NOT_SCHEDULED`. Drafts omit sender, recipients, Date and
Message-ID rather than inventing them. `X-Unsent: 1` is a draft hint, not a
universal mail-client control. MIME serialization normalizes line endings and
adds a final newline; the `.txt` file is the exact body-text source.

The CSV is a neutral handoff, not a promise of native import into every email
provider. Its columns are `issue_id`, `subject`, `intended_send_at_utc`,
`text_file`, `html_file`, `eml_file`, and `delivery_state`. Leading spreadsheet
formula characters receive an apostrophe in CSV cells only; the original
values remain in the manifest. Map this CSV to the client's existing platform
and verify its interpretation before delivery.

For the same input and implementation/runtime, repeated exports produce the
same ZIP bytes. This removes transient timestamps and random MIME boundaries;
it is not a cross-version compression compatibility guarantee.

## Run and test

Python 3.10 or newer; no third-party runtime dependencies.

```sh
python email_handoff.py packet.json --output month.zip
python -m unittest -v test_email_handoff.py
```

The packet is a JSON object with `publication`, `issues`, and optional
`source_metadata`. Duplicate JSON keys, non-finite numbers, malformed text,
naive timestamps and duplicate issue IDs are rejected. The CLI validates the
entire packet before creating output, stages in the destination directory,
then atomically replaces the requested file. The destination directory must
already exist. Concurrent writers to the same output path are last-writer-wins;
the workspace should use its own revision policy or distinct output paths.

A four-issue original scripted example is available from the test module:

```sh
python -c 'import json; from test_email_handoff import packet; print(json.dumps(packet(), ensure_ascii=False))' > packet.json
python email_handoff.py packet.json --output month.zip
```

That example is synthetic editorial material, not a customer interview,
verified recording, customer installation or completed delivery.

## Integration boundary

Only this helper, its focused tests, this document, and its delivery receipt
are contributed by WREN-MIME. HAZEL-PRESS retains app/UI/database and actual
workspace-export integration. Calling this helper must not change any campaign
into a sent or provider-scheduled state. Before real delivery, use the client's
chosen platform to configure the authorized sender, audience, preference/footer
content, and schedule. No provider calls, email transmission, calendar writes,
account provisioning, paid service use or customer-data operations occur here.

The focused test suite covers MIME parsing, Unicode fidelity, timezone
normalization, deterministic ZIPs, source manifests, invalid inputs and real
CLI/file replacement. Browser rendering was additionally inspected in Chromium
at desktop and mobile sizes; it is not an email-client compatibility matrix.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
