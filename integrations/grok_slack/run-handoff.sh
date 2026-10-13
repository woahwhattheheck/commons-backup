#!/usr/bin/env bash
# Loopback browser activation for the grok.com Slack connector.
# Tokens are pasted in the page, never as argv.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
exec python3 integrations/grok_slack/handoff.py serve --open-browser "$@"
