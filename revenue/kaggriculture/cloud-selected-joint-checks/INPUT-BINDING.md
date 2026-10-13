# Bind receipt digest and parser to one captured ZIP

`check_joint_receipt.inspect_archive` captures the evidence ZIP bytes once, hashes
that capture, and parses a `BytesIO` over the same bytes. Previously it hashed
`path.read_bytes()` and then reopened the pathname in `read_members(path)`. A
normal atomic replacement between those operations could therefore attach the
first ZIP's digest to the second ZIP's parsed contents.

Public path-based `read_members(Path)` callers remain supported. Archive member
limits, supplemental-suite contracts, JSON-output isolation, line-ending handling,
method-identity checks, exit statuses and report fields are unchanged. This is a
single-input lifecycle repair, not a new receipt format or execution attestation.

## Executed validation

`test_archive_input_binding.py` passes all **16 methods** on the composed current
reader using the original provider artifacts:

- artifact 10036877991: 95 represented methods, SHA-256
  `af9b3fc1de67eaed39c842b6c71d8fcd84e4ae8c0bd31465cb89ed73252cae29`;
- artifact 10037093197: 117 represented methods, SHA-256
  `ff4fd2542982ba5cf04e081bf3cc74a9206d5c3ec2e430118d76b109de6111b6`.

The exact unpatched current reader, Git blob
`9f76538e852db5a9df7f82c7e761cef115667685`, executes the same 16 methods with
**13 assertion failures and zero errors**. The discriminators cover replacement,
reverse replacement, deletion, truncation, non-ZIP substitution, failed-log
substitution, expected metadata, missing or mismatched provider digests, required
suites, absence of a pathname reopen, legacy `read_members(Path)`, and unchanged
CLI stdout/report publication.

The original preparing session also retained compatibility evidence for its then
current output/newline/archive-fault suites. That historical count remains bound
to its source revision; it is not relabeled as a fresh run on later supplemental
contracts.

No archived source or test suite is imported or executed. The lifecycle tests
perform no policy calls, game panels, engine transitions, seed use, provider
writes or canonical TITAN package changes.

## Reproduce

Download the two existing workflow artifacts and run:

```sh
python3 -B revenue/kaggriculture/cloud-selected-joint-checks/test_archive_input_binding.py \
  --reader revenue/kaggriculture/cloud-selected-joint-checks/check_joint_receipt.py \
  --archive-a /path/to/artifact10036877991.zip \
  --archive-b /path/to/artifact10037093197.zip \
  --report /tmp/input-binding-results.json
```

The suite verifies both provider digests before exercising the selected reader.
It returns nonzero if the reader parses a different byte stream from the one it
hashes. Its controlled file replacements occur only in temporary directories.

A captured byte stream is not an atomic filesystem transaction against an
in-place writer mutating bytes during the capture itself. Existing artifact
limits and upstream download responsibilities remain unchanged.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
