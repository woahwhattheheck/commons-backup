# Lossless Slack delivery for MOVA work orders

The offline chunk_slack.py script accepts text produced by the existing MOVA bounty planner or its linked renderer. When a verified manifest produces a long Slack work-order block, one message can exceed the connector's 5,000-character text-element limit. Truncation loses claims, source owners, and provider URLs. This adapter splits only at complete work-order lines and emits UTF-8-byte-bounded texts.

Save the planner's Slack-format output to dispatch-slack.txt and run:

    python tools/mova_batch_sprint/chunk_slack.py --input dispatch-slack.txt > dispatch-chunks.json

The JSON contains schema, original source_sha256, message_count, max_message_bytes, and ordered messages with part and text. Post each text once, in order, to an authorized channel. Every part includes the same full source SHA-256 and its part N/total. A missing or repeated part is detectable without re-querying GitHub. After uncertain Slack delivery, the source digest is not a provider posting receipt: read back the actual message before any retry.

The default 4,000-byte bound is below the connector's 5,000-character limit, including the digest and part header. An indivisible line larger than capacity fails with exit code 2 by default. Optional `--split-long-lines` preserves UTF-8 characters across parts; reconstruct and verify the source hash before using those parts. The command NEVER truncates a bounty, drops a work-order line, silently splits a claim instruction, sends Slack messages, or submits a bounty claim. Large batches still need rate-safe message pacing by the sender. The adapter does no network access, credential reads, rate-limit bypass, or change to original-contributor attribution.

Focused local validation (from repository root):

    cd tools/mova_batch_sprint && python -m unittest test_chunk_slack.py

Do not run a repository-wide test suite for this change.
