#!/usr/bin/env bash
# Host-neutral always-on launcher. systemd/docker/compose also work.
# GitHub Actions is not an always-on Socket Mode host.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
ENV_FILE="${COMMONS_GROK_SLACK_ENV_FILE:-$ROOT/integrations/grok_slack/.env.local}"
if [[ -f "$ENV_FILE" ]]; then
  export COMMONS_GROK_SLACK_ENV_FILE="$ENV_FILE"
fi
python3 integrations/grok_slack/bridge.py doctor --json
status=0
while true; do
  set +e
  python3 integrations/grok_slack/bridge.py serve "$@"
  status=$?
  set -e
  if [[ "$status" -eq 2 ]]; then
    echo '{"state":"RUNTIME_UNCONFIGURED","restart":false}' 
    exit 2
  fi
  sleep 5
done
