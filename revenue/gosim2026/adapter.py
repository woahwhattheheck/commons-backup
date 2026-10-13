"""ARC-Bench fixed-entry adapter for the pinned, unmodified ARC compiler.

This is generic bootcamp harness preparation, not a qualifier task solution.
Only the runner-injected metered model configuration is passed to ARC.
"""
from __future__ import annotations

import os
import sys


def translate_args(argv: list[str]) -> list[str]:
    """The platform omits ARC's 'compile' subcommand; preserve every other flag."""
    if not argv or argv[0] in {"-h", "--help", "--version"}:
        return argv
    if argv[0] in {"compile", "doctor", "config"}:
        return argv
    return ["compile", *argv]


def model_environment(env: dict[str, str]) -> dict[str, str]:
    """Keep organizer-injected values; never choose a direct provider fallback."""
    result = dict(env)
    required = ("OPENAI_API_KEY", "OPENAI_BASE_URL", "MODEL")
    missing = [key for key in required if not result.get(key, "").strip()]
    if missing:
        raise ValueError("Missing runner model configuration: " + ", ".join(missing))
    result["OPENAI_API_BASE"] = result["OPENAI_BASE_URL"]
    result["OPENAI_KEY"] = result["OPENAI_API_KEY"]
    result["ARC_OPENAI_API_MODE"] = result.get("ARC_OPENAI_API_MODE") or "chat_completions"
    # Visual inference uses the same metered gateway, never a personal endpoint.
    result["VISUAL_API_KEY"] = result["OPENAI_API_KEY"]
    result["VISUAL_BASE_URL"] = result["OPENAI_BASE_URL"]
    result["VISUAL_MODEL"] = result["MODEL"]
    return result


def main() -> int:
    args = translate_args(sys.argv[1:])
    # Help/version are local introspection, with zero model calls.
    introspection = not args or any(flag in args for flag in ("-h", "--help", "--version"))
    if not introspection:
        try:
            os.environ.update(model_environment(dict(os.environ)))
        except ValueError as error:
            print(str(error), file=sys.stderr)
            return 2
    import arc_cli
    sys.argv = [sys.argv[0], *args]
    arc_cli.main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
