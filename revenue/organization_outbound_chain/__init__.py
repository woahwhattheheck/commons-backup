"""Mandatory organization-aware provider-bound outbound chain."""
from .adapters import (
    discord_initial_outreach,
    gmail_initial_outreach,
    slack_dm_initial_outreach,
    webhook_mail_initial_outreach,
)
from .chain import (
    ChainError,
    execute_guarded_initial_outreach,
    opportunity_commitment,
    prospect_fingerprint,
    route_commitment,
)
from .provider_boundary import (
    DiscordBoundary,
    GmailBoundary,
    ProviderBoundaryError,
    SlackDmBoundary,
    WebhookMailBoundary,
)
from .registry import (
    ADAPTERS,
    find_bypasses,
    registered_host_mutation_identities,
    registered_provider_names,
    validate_registry,
)

__all__ = [
    "ChainError",
    "ProviderBoundaryError",
    "execute_guarded_initial_outreach",
    "prospect_fingerprint",
    "route_commitment",
    "opportunity_commitment",
    "gmail_initial_outreach",
    "slack_dm_initial_outreach",
    "discord_initial_outreach",
    "webhook_mail_initial_outreach",
    "GmailBoundary",
    "SlackDmBoundary",
    "DiscordBoundary",
    "WebhookMailBoundary",
    "ADAPTERS",
    "find_bypasses",
    "validate_registry",
    "registered_provider_names",
    "registered_host_mutation_identities",
]
