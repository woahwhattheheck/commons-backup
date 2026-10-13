# Lantern chess-style challenges

This is an **additive presentation companion** for the existing Lantern community-event app. It uses the same SQLite `events`, `members`, and `answers` records and the same scheduling, first-answer-wins, reconnect, scoring, and leaderboard behavior from `app.py`.

It is deliberately **not a chess engine**. The host authors a board position plus one square-to-square move for each normal answer choice. Clicking a start and destination square only selects the matching authored choice. Lantern never decides whether a move is legal, best, or valid under chess rules.

## Run

From `revenue/hive_community_events/`:

```text
python3 chess_challenge.py --db /private/path/events.sqlite3 --port 8765
```

Open `http://127.0.0.1:8765/chess`. The ordinary Lantern UI remains at `/`; both use the same event database. Use the chess launcher when creating/rendering board-aware questions. Existing trivia events and question packs remain compatible.

## Host and participant handoff

Creating an event in `/chess` retains the core event's one-time host capability
under the same separate `lantern-host:<event>` browser key used by `/`.
Expand **Host controls**, then **Host recovery key** to keep a private copy.
The participant event URL never includes that key. If browser storage is
unavailable, the page explicitly says the key is available only in the current
tab; copy it before leaving.

On another browser, open the same event URL, expand **Host controls**, paste
the saved key and select **Restore host controls**. The existing server verifies
it before the page retains it. **Finish event** asks for confirmation and uses
that capability. Events created before host protection retain the core's
explicitly labelled legacy shared-finish behavior.

Participants join with a display name or reconnect with their saved participant
reference. Click an occupied board square and an authored destination, or choose
the ordinary radio answer, then select **Save answer**. The board never infers
chess legality. Answers retain the core's first-answer-wins behavior. Finishing
reveals the authored answer and the same persisted non-cash leaderboard.

The native browser handoff has been exercised with the page's shipped two-question
demonstration, ordinary HTTP, browser storage, host recovery, participant reload,
and database restart. The main homepage and its separate recovery-persistence
work remain independent source scope.

## Authoring schema

A normal Lantern question may add a `chess` object:

```json
{
  "prompt": "Choose the authored knight move.",
  "choices": ["g1→f3", "g1→h3"],
  "correct": 0,
  "points": 100,
  "chess": {
    "orientation": "white",
    "pieces": {"e1": "K", "g1": "N", "e8": "k"},
    "moves": [
      {"from": "g1", "to": "f3", "choice": 0},
      {"from": "g1", "to": "h3", "choice": 1}
    ]
  }
}
```

`pieces` uses standard one-letter piece symbols: uppercase `KQRBNP` and lowercase `kqrbnp`. Squares are `a1` through `h8`. Orientation is `white` or `black`. Every ordinary answer choice must have exactly one distinct authored move, and every move must start on an occupied square.

The sidecar persists only display metadata (`orientation`, `pieces`, and authored move→choice mappings). The event's existing `correct` choice remains the scoring key and stays hidden from participant state until the event finishes.

## Behavioral boundaries

- Free entry and non-cash points only; no wagering or prizes.
- No chess legality, best-move, engine, rating, identity, anti-cheat, or tournament claims.
- No platform/community-provider installation is implied.
- Board metadata is public to participants once the question opens. Do not put private information in it.
- Existing result exports remain governed by their current allowlists; the sidecar does not add participant references, individual answer records, or question keys to exports.
- Running plain `app.py` against the same database is a compatible fallback: the underlying choices still work, but board metadata is not rendered.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)

