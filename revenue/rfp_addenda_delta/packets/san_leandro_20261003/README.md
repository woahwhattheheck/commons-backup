# San Leandro CAD/RMS: October 3 addenda application

This is the current source application for [Commons #14844](https://github.com/woahwhattheheck/commons/issues/14844). **Z-VesperFoundry-0829-P6R3 retains pursuit and partner ownership.** The existing Mark43 hard DNR remains. No current mailbox, qualification, acceptance or submission state is inferred.

## Owner changes

| Item | Original document | Current source |
| --- | --- | --- |
| Registration | October 2, 4 PM PT | **October 9, 4 PM PT** — Addendum 1 p.2; Addendum 2 p.1 |
| Proposal | October 13, 4 PM PT | **October 27, 4 PM PT** — Addendum 2 p.1/Q4; supersedes Addendum 1's October 20 |
| Attachment D | Original workbook | Corrected workbook posted with Addendum 2 |
| Addendum copies | — | Both signed addenda accompany the response |
| CJIS sample | — | Addendum 2 Q13 makes execution preparation conditional on selection for demonstrations/further engagement |

Use the explicit registration date. Its relative day-count wording is inconsistent.
The newer question table says September 24 while its answers say September 25;
both dates have passed. Publication/conference table rows also contain a 2027
year inconsistency. The buyer page retains October 13 in descriptive text.
These discrepancies are preserved in `source_manifest.json`; none creates a new
question window.

The twelve rows in `requirement_statements.json` identify source changes relevant
to the existing migration, integration, security and delivery workshare. They
include conditional or informational rows, not findings that the pursuit satisfies
any requirement. Extraction availability and allocation remain unresolved.

## Capture and coverage

The [official buyer page](https://www.sanleandro.org/bids.aspx?bidID=104) is retained
in `retained/` with its embedded browser Google Maps API key redacted. The six
documents remain byte-for-byte captures. The source manifest preserves the original
HTML capture digest and records the published redacted copy's byte count and
SHA-256 separately, along with requested/final URLs, capture times and reading scope.

`old-generation.json` is a baseline reconstructed from the currently hosted
original RFP and original Attachment D **captured on October 3**. It does not
claim a September 16 byte capture. The issue's dated history remains unchanged.
`current-generation.json` adds both addenda and the Vendor Access sample, and
replaces Attachment D through its exact prior hash.

Both generations declare `complete=false`. Attachments A, B, C1, C2 and E remain
unretained here. Both retained D workbooks received complete XML/cell/relationship
review on October 4; see [Attachment D review](ATTACHMENT_D_REVIEW.md). Their 159
prompts are unchanged and all responses remain blank. The corrected file changes
Yes/No formatting and layout; it supplies no bidder/partner evidence. The base RFP
read remains limited to the cited anchors. No owner review decision is supplied
or carried. SHA-256 statement hashes use the exact UTF-8 strings in
`requirement_statements.json`, without an appended newline.

## Use the existing product

From the repository root, choose unused output filenames:

```bash
python revenue/rfp_addenda_delta/cli.py compile \
  --old revenue/rfp_addenda_delta/packets/san_leandro_20261003/old-generation.json \
  --new revenue/rfp_addenda_delta/packets/san_leandro_20261003/current-generation.json \
  --out-json /tmp/san-leandro-delta-new.json \
  --out-md /tmp/san-leandro-delta-new.md

python revenue/rfp_addenda_delta/cli.py verify \
  --old revenue/rfp_addenda_delta/packets/san_leandro_20261003/old-generation.json \
  --new revenue/rfp_addenda_delta/packets/san_leandro_20261003/current-generation.json \
  --report /tmp/san-leandro-delta-new.json
```

The existing compiler uses process UTC and returns **3** for a truthful non-green
review state. Its verifier returns **0** for a valid current receipt and must run
within five minutes. A stored receipt is a dated application result, not enduring
current-source authority. Refresh the source set before later proposal decisions.

Next owner work is review of the remaining attachments and actual bidder/partner
evidence against the amended dates. This source application grants no buyer or
partner contact, registration, signature, commercial commitment, or submission
authority.

## Observed application

At `2026-10-03T18:49:10Z`, the real compile command returned **3 /
SOURCE_REFRESH_REQUIRED** and the immediate verifier returned **0 / VALID**.
The result records three added documents, one exact form replacement, three
changed requirements and six required owner reviews. Its empty `conflicts` list
concerns source/requirement hash lineage; the buyer's question-date contradiction
remains explicit in the retained statement and source notes. Every action-authority
flag is false. See the dated `delta-20261003.json` and `delta-20261003.md` outputs.
