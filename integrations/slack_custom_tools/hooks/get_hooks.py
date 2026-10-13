#!/usr/bin/env python3
"""Local Slack CLI get-hooks. No npm. Login stays #needs-bryce."""
from __future__ import annotations

import json
import sys

payload = {
    "hooks": {
        "get-manifest": "python3 hooks/get_manifest.py",
        "start": "python3 app.py",
    },
    "config": {
        "protocol-version": ["default"],
        "sdk-managed-connection-enabled": False,
        "watch": {
            "app": {"filter-regex": "\\.py$", "paths": ["."]},
            "manifest": {"paths": ["manifest.json"]},
        },
    },
    "runtime": "python",
}

if __name__ == "__main__":
    json.dump(payload, sys.stdout)
    sys.stdout.write("\n")
