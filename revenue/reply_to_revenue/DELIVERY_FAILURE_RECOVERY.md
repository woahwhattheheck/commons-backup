# Delivery-failure recovery boundary

The reply-to-revenue funnel treats a proven delivery failure as a dead transport route, not as an automated acknowledgement that can still produce a human reply.

## Classification

`DELIVERY_FAILURE` is selected before generic `AUTO_RESPONSE` handling when an inbound observation contains a bounded hard-failure marker such as `mailer-daemon`, `delivery status notification (failure)`, `message blocked`, `address not found`, `undeliverable`, `couldn't be delivered`, `recipient address rejected`, or `user unknown`.

A delivery-failure marker wins over a caller-requested `POSITIVE_SCOPE`, `QUESTION`, or `NEEDS_HUMAN` classification on the same event. Transport failure is not buyer interest and cannot be promoted into a human response by operator labeling.

At contact aggregation, later independent human evidence can still supersede an older failed-route event: an actual positive human reply becomes `HUMAN_POSITIVE`, and an actual human question becomes `HUMAN_QUESTION`. The failed route itself never does.

## Owner-review queue

Run:

```sh
python3 host/reply_to_revenue.py recover
```

The command emits a deterministic `OWNER_REVIEW_ONLY` queue for contacts whose current aggregate lane is `DELIVERY_FAILURE`. Every item carries the exact observed failure event reference and time plus the fixed next action `RECOVER_ROUTE_OWNER_REVIEW`.

The recovery surface is deliberately non-executing:

- `transport_actions` is always `0`;
- `resends` is always `0`;
- buyer interest is always `false`;
- no alternate address, person, mailbox, web form, phone number, or other route is discovered by this module;
- no message is drafted or sent by this module;
- no CRM, provider, checkout, invoice, payment, or revenue state is mutated.

## What an owner may do next

A human owner may separately investigate whether an official/public alternate route exists and whether a new contact attempt is appropriate. That decision must preserve existing opt-outs and do-not-resend policy, deconflict against other outreach custody, and use a separately authorized transport lane. A failed delivery is evidence that one route failed; it is not permission to bypass recipient policy or contact another person automatically.

This boundary exists to prevent a commercially harmful false wait state: once transport proves the original route dead, the funnel should surface the routing defect for review rather than waiting indefinitely for a reply that cannot arrive on that route.
