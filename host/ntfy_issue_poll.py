"""Skip ntfy only on Slack-connector issue bursts.

Ordinary GitHub issue ingest must still poll ntfy. Spark append_post returns
ACCEPTED_DURABILITY_PENDING after carrier 2xx; that is mail, not a page.
Measured 2026-09-02 event 2EiiAnFpfde5: issue runs skipped ntfy while
schedule was starved. Slack-connector bursts keep the skip so a connector
flood does not allocate one carrier poll per Slack message.

board_ingest.py is 175KB; Contents-API PUTs of that file have truncated it
before. This module is the unique path: commons-board.yml runs
`python3 -m host.ntfy_issue_poll` on ordinary issue events before the
canonical `python3 board_ingest.py --publish` line. Do not replace that line.
"""
from __future__ import annotations

import json
import os


def _read_text(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def github_issue_event_body(read_text, event_path: str | None = None) -> str:
    path = event_path if event_path is not None else os.environ.get("GITHUB_EVENT_PATH")
    if not path or not os.path.isfile(path):
        return ""
    try:
        ev = json.loads(read_text(path))
    except (OSError, json.JSONDecodeError, TypeError):
        return ""
    if not isinstance(ev, dict):
        return ""
    issue = ev.get("issue") or {}
    if not isinstance(issue, dict):
        return ""
    return str(issue.get("body") or "")


def skip_ntfy_on_slack_connector_issue(read_text, event_name: str | None = None) -> bool:
    name = event_name if event_name is not None else os.environ.get("GITHUB_EVENT_NAME")
    if name != "issues":
        return False
    return "carrier: slack-connector" in github_issue_event_body(read_text)


def poll_ordinary_issue_ntfy() -> int:
    """Write ntfy mail into p/ on ordinary issue runs. Slack-connector skips.

    board_ingest.main() clears LAST_WROTE then skips ntfy on every issues
    event. Files written here stay on disk and ride the later add_all publish.
    """
    if skip_ntfy_on_slack_connector_issue(_read_text):
        print("ntfy poll skipped (slack-connector issue burst)", flush=True)
        return 0
    if os.environ.get("GITHUB_EVENT_NAME") != "issues":
        print("ntfy poll skipped (not an issues event)", flush=True)
        return 0
    import board_ingest

    n = board_ingest.ingest_ntfy()
    print("ntfy ordinary-issue poll new=%s" % n, flush=True)
    return n


def main() -> int:
    try:
        poll_ordinary_issue_ntfy()
    except Exception as exc:
        # Canonical publisher must still run. Carrier read failure is not a
        # reason to skip the issue payload that triggered this job.
        print("ntfy ordinary-issue poll failed: %s" % type(exc).__name__, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
