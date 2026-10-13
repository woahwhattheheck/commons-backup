# Action Pad ntfy transport contract

Status: recovered and pinned on 2026-09-14 from the existing Commons implementation. This document describes the current road; it does not add a provider, credential, permission boundary, execution verb, publication audience, or alternate transport.

## Source of truth

The live path is split across existing files:

- [`action.html`](../action.html) — browser producer and relay failover;
- [`relay-manifest.json`](../relay-manifest.json) and [`relay_manifest.py`](../relay_manifest.py) — ordered relay origins and the shared topic;
- [`ntfy_relays.py`](../ntfy_relays.py) — failover-to-home reconciliation without reminting an action id;
- [`board_ingest.py`](../board_ingest.py) — canonical ntfy event intake and durable Commons record creation;
- [`action_executor.py`](../action_executor.py) — execution from the durable `kind: ACTION` record and result latch; and
- [`ground/ACTION_DOOR.md`](../ground/ACTION_DOOR.md) — the owner rule that every nonblank verb remains usable.

`commons-ntfy-relay-v1` is the browser's `localStorage` key for relay selection and cooldown state. It is not currently serialized as a `protocol` field in the ntfy message body. Code or documentation must not claim that a receiver negotiated a packet protocol merely because that local key exists.

## Browser producer

The Action Pad builds one caller-supplied action id, constructs an envelope, and sends it with:

- method: `POST`;
- destination: the first available configured relay at `/<topic>`;
- header: `Content-Type: application/json`; and
- request body: `JSON.stringify(packet)`.

The serialized envelope has these fields:

| Field | Current meaning |
| --- | --- |
| `from` | Optional normalized sender label, or `UNSEATED`. Routing metadata only. |
| `to` | `TOOLS`. |
| `id` | The Action Pad-generated durable action id. |
| `subject` | `COMMONS ACTION <VERB>`. |
| `board` | `TOOLS`. |
| `kind` | `ACTION`. |
| `act` | The upper-cased free-text verb. |
| `target` | Optional target or working directory. |
| `body` | Verb line, `target:` line, optional `circuit:` line, blank line, then the exact pasted payload. |

Named verbs are convenience handlers. The producer defaults a blank verb to `ACTION`; every other nonblank verb remains executable through the existing shell path. This contract must not be turned into a verb allowlist.

## Relay and reconciliation

The ordered relay list and topic come from `relay-manifest.json`. The manifest declares sequential first-accept delivery and direct polling of every relay. `action.html` rotates through those origins and records cooldown state locally.

A browser status of `CARRIER_ACCEPTED` proves only that one relay accepted the HTTP request. It does **not** prove that a Git record landed or that execution finished.

`ntfy_relays.py` polls every configured relay. For an event absent from the canonical home relay, it replays the same caller-supplied id and payload to the home relay, adding carrier-origin receipt fields. It refuses to manufacture or rewrite an inconsistent id.

## Canonical ingest and execution

`board_ingest.py` polls the canonical ntfy topic and reads the ntfy event's `message` field. `ntfy_envelope` accepts the existing Commons envelope forms, including a JSON object carrying `from`, `id`, or `body`, and then follows the normal durable publication path.

The receipt ladder is:

1. **Address generated** — the browser encoded the requested action.
2. **`CARRIER_ACCEPTED`** — one relay accepted the request bytes.
3. **Git durable** — `p/<id>.md` exists on current `main` with the expected action id and body.
4. **Executed** — the corresponding `actions/results/<id>.json` latch records the terminal executor result, including any circuit step receipts.

Only the latter two are repository evidence. Retrying solely from an HTTP acceptance message can duplicate intent before durability is known; read the current Git state by id first.

## SMTP / email boundary

The ntfy email-to-topic bridge is **not a producer in this v1 Action Pad contract**. `action.html` uses JSON HTTP POST, and this repository currently has no adapter fixture proving that an SMTP subject/body round trip reconstructs the canonical envelope with the same `id`, `kind`, `act`, `target`, and `body`.

An email body may happen to parse as one of the generic Commons intake forms. That does not make SMTP acceptance equivalent to Action Pad carrier acceptance, Git durability, or execution. Do not report an accepted email as any of those receipts, and do not use the email bridge as an operational substitute for the existing HTTP producer without repository evidence.

A future SMTP adapter can join this road without changing the open-door rule when it supplies a deterministic fixture showing the reconstructed ntfy `message`, preserves the caller-supplied id and payload fields, and then uses the ordinary Git-durable and executor-result receipts. This document neither creates nor exercises such an adapter.

## Regression check

Run:

```bash
python3 test_action_pad_transport_contract.py
```

The test is network-free. It checks the generated relay block against the manifest, the JSON POST envelope, id-preserving reconciliation, canonical message parsing, the unrestricted-verb rule, this SMTP boundary, and the transport-document index link.
