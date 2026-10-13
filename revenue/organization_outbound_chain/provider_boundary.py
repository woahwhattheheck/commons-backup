"""Typed outbound mutation boundary for the mandatory organization chain.

The chain must never accept an arbitrary per-invocation callback. Instead a host
supplies one exact provider transport object and the provider-specific adapter
constructs one of the frozen boundary objects below. The terminal consumer calls
`invoke_provider_boundary` once with its content-addressed idempotency key.

The transport implementation is the process/connector integration seam. Repository
CI can prove that repository code reaches it only through this module; it cannot
intercept an out-of-process connector invocation that ignores the repository
entirely. Those host mutation identities are enumerated in registry.py so that
operator/runtime policy can bind the same closed provider set.

Security note: public ClassVars are compatibility/introspection surfaces only. Runtime
provider identity, transport method, exact boundary class and host-identity generation
are captured once in a private immutable closure below. Ordinary post-import class or
module-global rebinding therefore cannot redirect a provider call; visible metadata
drift instead fails closed.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar, Protocol, Union, runtime_checkable


class ProviderBoundaryError(TypeError):
    """Fail-closed provider boundary shape/generation error."""


@runtime_checkable
class GmailTransport(Protocol):
    def gmail_send_message(self, *, idempotency_key: str, request_bytes: bytes) -> Any: ...


@runtime_checkable
class SlackDmTransport(Protocol):
    def slack_send_dm(self, *, idempotency_key: str, request_bytes: bytes) -> Any: ...


@runtime_checkable
class DiscordTransport(Protocol):
    def discord_send_message(self, *, idempotency_key: str, request_bytes: bytes) -> Any: ...


@runtime_checkable
class WebhookMailTransport(Protocol):
    def webhook_mail_send(self, *, idempotency_key: str, request_bytes: bytes) -> Any: ...


@dataclass(frozen=True, slots=True)
class GmailBoundary:
    transport: GmailTransport
    provider: ClassVar[str] = "gmail"
    transport_method: ClassVar[str] = "gmail_send_message"
    host_mutation_identities: ClassVar[tuple[str, ...]] = (
        "mcp__Gmail__send_email",
        "mcp__Gmail__send_draft",
        "mcp__Gmail__forward_emails",
    )


@dataclass(frozen=True, slots=True)
class SlackDmBoundary:
    transport: SlackDmTransport
    provider: ClassVar[str] = "slack_dm"
    transport_method: ClassVar[str] = "slack_send_dm"
    host_mutation_identities: ClassVar[tuple[str, ...]] = (
        "mcp__Slack__slack_send_message",
        "mcp__Slack__slack_schedule_message",
    )


@dataclass(frozen=True, slots=True)
class DiscordBoundary:
    transport: DiscordTransport
    provider: ClassVar[str] = "discord"
    transport_method: ClassVar[str] = "discord_send_message"
    host_mutation_identities: ClassVar[tuple[str, ...]] = (
        "discord.Webhook.send",
        "discord.webhook.execute",
    )


@dataclass(frozen=True, slots=True)
class WebhookMailBoundary:
    transport: WebhookMailTransport
    provider: ClassVar[str] = "webhook_mail"
    transport_method: ClassVar[str] = "webhook_mail_send"
    host_mutation_identities: ClassVar[tuple[str, ...]] = (
        "http.webhook_mail.post",
    )


ProviderBoundary = Union[
    GmailBoundary,
    SlackDmBoundary,
    DiscordBoundary,
    WebhookMailBoundary,
]


def _build_first_load_runtime():
    # These source-literal tuples are captured by the returned closures exactly once.
    # Exported class metadata remains readable for compatibility but is not authority.
    generation = (
        (
            GmailBoundary,
            "gmail",
            "gmail_send_message",
            (
                "mcp__Gmail__send_email",
                "mcp__Gmail__send_draft",
                "mcp__Gmail__forward_emails",
            ),
        ),
        (
            SlackDmBoundary,
            "slack_dm",
            "slack_send_dm",
            (
                "mcp__Slack__slack_send_message",
                "mcp__Slack__slack_schedule_message",
            ),
        ),
        (
            DiscordBoundary,
            "discord",
            "discord_send_message",
            (
                "discord.Webhook.send",
                "discord.webhook.execute",
            ),
        ),
        (
            WebhookMailBoundary,
            "webhook_mail",
            "webhook_mail_send",
            ("http.webhook_mail.post",),
        ),
    )

    def assert_generation(entry):
        boundary_type, provider, method, host_identities = entry
        if getattr(boundary_type, "provider", None) != provider:
            raise ProviderBoundaryError("provider boundary metadata drift")
        if getattr(boundary_type, "transport_method", None) != method:
            raise ProviderBoundaryError("provider boundary metadata drift")
        if tuple(getattr(boundary_type, "host_mutation_identities", ())) != host_identities:
            raise ProviderBoundaryError("provider boundary metadata drift")
        return entry

    def entry_for_instance(boundary):
        actual_type = type(boundary)
        for entry in generation:
            if actual_type is entry[0]:
                return assert_generation(entry)
        raise ProviderBoundaryError("exact registered provider boundary required")

    def provider_name_impl(boundary):
        _boundary_type, provider, _method, _host_identities = entry_for_instance(boundary)
        return provider

    def registered_boundary_types_impl():
        for entry in generation:
            assert_generation(entry)
        return tuple(entry[0] for entry in generation)

    def registered_boundary_generation_impl():
        for entry in generation:
            assert_generation(entry)
        return tuple(
            (entry[0], entry[1], entry[2], entry[3])
            for entry in generation
        )

    def boundary_for_provider_impl(provider):
        if type(provider) is not str:
            raise ProviderBoundaryError("provider must be exact str")
        for entry in generation:
            if provider == entry[1]:
                return assert_generation(entry)[0]
        raise ProviderBoundaryError("provider is not registered")

    def invoke_provider_boundary_impl(
        boundary,
        *,
        idempotency_key,
        request_bytes,
    ):
        _boundary_type, provider, method_name, _host_identities = entry_for_instance(boundary)
        if type(idempotency_key) is not str or not idempotency_key:
            raise ProviderBoundaryError("idempotency_key required")
        if type(request_bytes) is not bytes:
            raise ProviderBoundaryError("request_bytes must be exact bytes")
        method = getattr(boundary.transport, method_name, None)
        if not callable(method):
            raise ProviderBoundaryError(
                f"{provider} transport must implement {method_name}"
            )
        return method(
            idempotency_key=idempotency_key,
            request_bytes=request_bytes,
        )

    return (
        provider_name_impl,
        registered_boundary_types_impl,
        registered_boundary_generation_impl,
        boundary_for_provider_impl,
        invoke_provider_boundary_impl,
    )


(
    provider_name,
    registered_boundary_types,
    registered_boundary_generation,
    boundary_for_provider,
    invoke_provider_boundary,
) = _build_first_load_runtime()
del _build_first_load_runtime
