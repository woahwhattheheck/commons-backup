"""Compatibility names for Creator Desk's retired operator-key interface.

Creator Desk is a shared workspace. These legacy entry points perform no
credential checks, create no keys, and do not read or alter a workspace database.
The application and multisite runtime no longer depend on this module.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


class OperatorSetupRequired(RuntimeError):
    """Legacy exception name retained for imports; no setup is required."""


class OperatorAuth:
    """Compatibility object with no access decision or database side effects."""

    def __init__(self, database: str | Path):
        self.database = str(database)

    @classmethod
    def initialize(cls, database: str | Path) -> str:
        """Retain the old return type without creating a credential."""
        return ""

    def verify(self, candidate) -> bool:
        return True

    def verify_header(self, authorization) -> bool:
        return True

    def rotate(self) -> str:
        """Retain the old return type without rotating or reading credentials."""
        return ""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, help="Legacy workspace argument; no database is opened")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init", help="Report the shared-workspace mode; no setup is performed")
    sub.add_parser("rotate", help="Report the shared-workspace mode; no rotation is performed")
    parser.parse_args()
    print(json.dumps({"shared_workspace": True, "operator_setup_required": False}, sort_keys=True))


if __name__ == "__main__":
    main()
