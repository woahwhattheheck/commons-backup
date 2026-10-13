"""Concrete provider entrypoints for the mandatory organization-aware chain.

Each adapter fixes one provider and one transport protocol. Callers cannot pass a
provider name or arbitrary provider callback through this surface.

Production dependencies are captured once at module load. Top-level declarations
remain visible to the existing registry; no scanner exemption is required.
"""
from __future__ import annotations

from typing import Any

from .chain import execute_guarded_initial_outreach
from .provider_boundary import (
    DiscordBoundary,
    DiscordTransport,
    GmailBoundary,
    GmailTransport,
    SlackDmBoundary,
    SlackDmTransport,
    WebhookMailBoundary,
    WebhookMailTransport,
)


def _build_first_load_adapters(_execute=execute_guarded_initial_outreach):
    def run_impl(boundary: object, *args: Any, **kwargs: Any):
        forbidden = {"provider", "provider_callback", "provider_boundary"} & set(kwargs)
        if forbidden:
            raise TypeError(
                "provider identity and mutation boundary are fixed by the registered adapter"
            )
        return _execute(*args, provider_boundary=boundary, **kwargs)

    def bind_provider(boundary_type):
        def decorate(declaration):
            # Neither boundary_type nor run_impl is a caller-overridable default
            # or a late lookup through an exported module alias.
            def adapter(*args: Any, transport: Any, **kwargs: Any):
                return run_impl(boundary_type(transport), *args, **kwargs)

            adapter.__name__ = declaration.__name__
            adapter.__qualname__ = declaration.__qualname__
            adapter.__doc__ = declaration.__doc__
            adapter.__annotations__ = declaration.__annotations__.copy()
            return adapter
        return decorate

    return run_impl, bind_provider


_run, _bind_provider = _build_first_load_adapters()
del _build_first_load_adapters


# These are real module-level declarations for registry.validate_registry().
# Decoration replaces each declaration with its first-load-bound implementation;
# the declaration body fails closed if ever invoked without that binding.
@_bind_provider(GmailBoundary)
def gmail_initial_outreach(*args: Any, transport: GmailTransport, **kwargs: Any):
    """Run the organization-aware chain with the fixed Gmail boundary."""
    raise RuntimeError("first-load adapter binding missing")


@_bind_provider(SlackDmBoundary)
def slack_dm_initial_outreach(*args: Any, transport: SlackDmTransport, **kwargs: Any):
    """Run the organization-aware chain with the fixed Slack DM boundary."""
    raise RuntimeError("first-load adapter binding missing")


@_bind_provider(DiscordBoundary)
def discord_initial_outreach(*args: Any, transport: DiscordTransport, **kwargs: Any):
    """Run the organization-aware chain with the fixed Discord boundary."""
    raise RuntimeError("first-load adapter binding missing")


@_bind_provider(WebhookMailBoundary)
def webhook_mail_initial_outreach(*args: Any, transport: WebhookMailTransport, **kwargs: Any):
    """Run the organization-aware chain with the fixed webhook-mail boundary."""
    raise RuntimeError("first-load adapter binding missing")


del _bind_provider
