# Tool routing

This is a companion workflow, not a new MCP tool owner. Use exact live Mermail schemas.

## Read path

- `search_emails`: bounded candidate discovery by sender/subject/date/folder.
- `get_email`: selected quote message; request clean/agent-safe content and a bounded body when available.
- `get_thread`: surrounding vendor thread and amendment history.
- `list_mailboxes`: prerequisite workspace discovery; prefer returned mailbox `public_id`.

Do not treat search filters as sender authentication. Bind a quote to the vendor identity and the exact thread recorded when that vendor was solicited.

## External-effect path

- `send_email`: one RFQ solicitation per vendor after exact preview + fresh approval.
- `reply_to_email`: clarification/follow-up after exact preview + fresh approval.

For send-like tools, canonical Sold/Mermail MCP content is under `body.text` and/or `body.html`, with required `body.from`; source email ids remain top-level path parameters where applicable. Pass explicit `to` on replies because external MCP does not infer Reply All recipients.

A stable idempotency key may protect an identical request replay, but it never authorizes retrying an ambiguous send with a new key.

## Deliberately absent

This skill does not call PayBox/wallet tools, create purchase orders, accept contracts, or send funds. If the user later requests payment, route that request to the official wallet skill under its own approval and signing rules.
