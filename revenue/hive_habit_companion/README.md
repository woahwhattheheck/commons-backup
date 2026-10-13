# Paceboard

Paceboard is a private, local-first habit companion for self-chosen goals. It treats **done**, **paused**, and **resumed** as honest observations rather than a streak score. A missed or paused day never becomes a penalty.

This is the published recovery of Hive demand `bm-hive-20260908-018`. Original ASTRA-PACEBOARD concept/build/test attribution is preserved; see `RELEASE.md` for the reconstruction boundary.

## What a user can do

- create, edit, archive, reactivate, and delete self-chosen goals;
- choose an in-app reminder interval and a default focus target;
- record `DONE`, `PAUSED`, and `RESUMED` check-ins with optional private notes;
- record private trigger notes, either general or linked to a goal;
- start, pause, resume, finish, and delete focus sessions;
- review a chronological history with no streak or missed-day penalty;
- download a deterministic, digest-bound JSON backup;
- download a chronological CSV history;
- replace the workspace from a verified Paceboard backup;
- delete individual items or erase all local user content.

The browser can optionally display an operating-system notification **only after the user grants browser permission and only while the local app is open**. There is no external notification provider. The visible page checks its current workspace reminders about every 15 seconds and when returning to the tab, so a reminder becoming due appears without a reload. This background refresh updates only reminders and preserves unsaved fields and keyboard focus. A changed workspace revision or restarted server still uses the ordinary full refresh path.

## Run

Requires Python 3.9+ and no third-party packages.

```bash
cd revenue/hive_habit_companion
python app.py --db "$HOME/.paceboard/paceboard.sqlite3"
```

Open the printed loopback URL, normally `http://127.0.0.1:8765/`.

Paceboard refuses non-loopback bind addresses. The server validates `Host`, validates mutating `Origin` when present, requires a per-process CSRF token for mutation, rejects transfer-encoded or unbounded request bodies, serves a strict content-security policy, and suppresses request logging so private notes do not enter access logs.

## Synthetic demonstration

```bash
python demo.py --db /tmp/paceboard-demo.sqlite3
python app.py --db /tmp/paceboard-demo.sqlite3 --port 8766
```

The demo is explicitly synthetic. It does not represent a customer, sale, or treatment scenario.

## Test

```bash
python -m unittest -v test_paceboard test_paceboard_data test_app test_browser_contract test_browser_acceptance
python -O -m unittest -v test_paceboard test_paceboard_data test_app test_browser_contract test_browser_acceptance
node --check app.js
```

The core tests require only Python. `test_browser_acceptance` runs a complete Chromium workflow when Playwright and Chromium are present, and otherwise reports a skip rather than changing the runtime dependency boundary.

The suite uses real temporary SQLite databases and a real loopback HTTP server. It covers retry-safe mutation, same-second pause/resume chronology, focus timing, reminder currentness, deterministic backup/restore, digest tamper rejection, scoped deletion, full erase, host/origin/CSRF/framing boundaries, export, static browser composition, a real Chromium goal → pause → resume → focus → export → erase → restore workflow, and deterministic source packaging.

## Deterministic source package

```bash
python build_release.py --output /tmp/paceboard-source.zip
```

The archive uses fixed ZIP timestamps, a stable file order, normalized permissions, and an internal SHA-256 manifest. Rebuilding from unchanged source yields identical bytes.

## Data model and privacy

All content is stored in one user-selected SQLite file. Paceboard creates no account, cloud workspace, cookie, tracking identifier, analytics event, email, or outbound webhook. Ordinary timestamps are owned by the local process clock. Each created check-in, trigger note, and focus session also receives a revision-backed event sequence, so actions remain totally ordered even when several happen within the same clock second; the sequence is preserved and validated through backup/restore. Mutation requests carry a unique operation ID; a byte-equivalent retry returns the original response, while reusing the ID for a different request fails closed.

Backups are canonical JSON with a SHA-256 digest over the exact semantic payload. Restore is explicit replace-only, validates every identifier, reference, state, timestamp, and digest inside one SQLite transaction, and rejects a backup that claims a running focus session. Pause a running session before exporting.

## Not medical care

Paceboard is a habit utility, not treatment, diagnosis, monitoring, crisis support, or medical advice. It does not infer a condition or claim that a behavior is healthy, unhealthy, addictive, safe, or unsafe. Users choose their own goals and retain full control over their local data.

## Commercial posture

Proposed offer: **$6/month or $39/year — PROPOSED_NOT_ACCEPTED**. The software being present in this repository is not evidence of buyer acceptance, payment, or revenue.
