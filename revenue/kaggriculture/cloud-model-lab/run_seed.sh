#!/usr/bin/env bash
# Seeding launcher. Two properties this file exists for:
#
#  1. It records its own PID and exit status in a status file, so a later step reads
#     a fact instead of inferring liveness from a process-name substring. A
#     `pgrep -f seed_bank.py` waiter matches its own command line and every sibling
#     waiter, so such a loop can never exit.
#  2. It builds the bank OUTSIDE the repository and copies it in only when complete.
#     Writing directly into the working tree meant git saw the file change between
#     `git add` and `git merge`, which aborted the merge repeatedly.
set -u
BANK="$1"; shift
STATUS_FILE="${BANK%.jsonl}.status.json"
WORK="$(mktemp -d)"
STAGE="$WORK/bank.jsonl"
echo "{\"pid\": $$, \"state\": \"running\", \"stage\": \"$STAGE\"}" > "$STATUS_FILE"
rc=0
for T in "$@"; do
  /home/user/work/venv/bin/python -B seed_bank.py --bank "$STAGE" \
    --seeds 4242001,5150011 --teacher "$T" --seat 0 --max-steps 300 \
    --exclude-seeds 7700001,8800001,9900017,3131017,6060013 || rc=$?
done
if [ $rc -eq 0 ] && [ -s "$STAGE" ]; then
  cp "$STAGE" "$BANK"          # single atomic-enough publish into the repo
fi
rows=$(wc -l < "$BANK" 2>/dev/null || echo 0)
echo "{\"pid\": $$, \"state\": \"done\", \"exit\": $rc, \"rows\": $rows}" > "$STATUS_FILE"
rm -rf "$WORK"
exit $rc
