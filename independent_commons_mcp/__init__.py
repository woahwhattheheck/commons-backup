"""Independent Commons MCP server.

A local-session-owned tool surface. It does not replace ``commons_mcp.py``
or the zero-auth Action Pad. Slack, Discord, ntfy, and GitHub are roads, not truths.
"""

from relay_manifest import NTFY_TOPIC as TOPIC

SERVER_NAME = "independent-commons"
SERVER_VERSION = "1.3.0"
REPO = "woahwhattheheck/commons"
SLACK_CHANNEL = "C0BRGMDQB6G"  # default table, not an allowlist
PAGES = "https://woahwhattheheck.github.io/commons"
RAW_ROOT = "https://raw.githubusercontent.com/%s" % REPO
REPO_GIT = "https://github.com/%s.git" % REPO
GITHUB_API = "https://api.github.com/repos/%s" % REPO
ACTION_PAD = "%s/action.html" % PAGES
HEAD_PIN = "%s/head.html" % PAGES
NTFY_MAX = 3900
MAX_BODY = 16000
DISCORD_API = "https://discord.com/api/v10"
