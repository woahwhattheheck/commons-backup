"""Additional model APIs through existing private credential references.

Each invocation makes one bounded request. The caller owns quota selection,
account Free-plan facts and replay. Model catalog reads do not prove inference
entitlement. Keys are never returned and OAuth grants are not API-key substitutes.
"""
from __future__ import annotations

import copy
import json
import re
import urllib.error
import urllib.parse
import urllib.request

from .provider_apis import GroqExaEquipment, ProviderToolError, _tool

_PROVIDERS = ("gemini", "cloudflare", "openrouter", "mistral")
_COMMON = {
    "model": {"type": "string", "minLength": 1, "maxLength": 200},
    "messages": {"type": "array", "minItems": 1, "maxItems": 100},
    "max_completion_tokens": {"type": "integer", "minimum": 1, "maximum": 8192},
    "temperature": {"type": "number", "minimum": 0, "maximum": 2},
}
TOOLS = [
    _tool("free_model_catalog", "Read model metadata for one provider; OpenRouter public catalog needs no key. This does not establish a Free inference plan.",
          {"provider": {"type": "string", "enum": list(_PROVIDERS)}}, ["provider"]),
    *[_tool(provider + "_generate", "Make one bounded non-streaming " + provider + " inference request using its existing private API credential. Use the actual Free account/model route; never retries or creates an account.",
            _COMMON, ["model", "messages"]) for provider in _PROVIDERS],
]


class FreeModelEquipment(GroqExaEquipment):
    def tools(self, **_kwargs):
        return copy.deepcopy(TOOLS)

    def _call(self, name: str, args: dict) -> dict:
        if name == "free_model_catalog":
            provider = args.get("provider")
            if provider not in _PROVIDERS:
                self._invalid("provider must identify a supported API transport")
            if provider == "openrouter":
                return self._send(provider, "GET", "https://openrouter.ai/api/v1/models", key="")
            key = self._key(provider + "/api-key")
            if provider == "gemini":
                url = "https://generativelanguage.googleapis.com/v1beta/models?pageSize=1000"
            elif provider == "mistral":
                url = "https://api.mistral.ai/v1/models"
            else:
                account = self._account_id()
                url = "https://api.cloudflare.com/client/v4/accounts/" + account + "/ai/models/search?per_page=50"
            return self._send(provider, "GET", url, key=key)
        provider = name.removesuffix("_generate")
        if name != provider + "_generate" or provider not in _PROVIDERS:
            return super()._call(name, args)
        payload = self._groq_chat_payload(args)
        model = payload["model"]
        if provider == "openrouter" and not (model.endswith(":free") or model == "openrouter/free"):
            self._invalid("OpenRouter free transport requires an explicitly free model")
        # A bounded output is sent even when the caller omits it.
        limit = payload.pop("max_completion_tokens", 1024)
        key = self._key(provider + "/api-key")
        if provider == "gemini":
            if not re.fullmatch(r"[A-Za-z0-9._-]+", model):
                self._invalid("Gemini model must be a model identifier")
            contents, system = [], []
            for message in payload["messages"]:
                if message["role"] in {"system", "developer"}:
                    system.append({"text": message["content"]})
                elif message["role"] in {"user", "assistant"}:
                    contents.append({"role": "model" if message["role"] == "assistant" else "user",
                                     "parts": [{"text": message["content"]}]})
                else:
                    self._invalid("Gemini text transport accepts user, assistant and system messages")
            if not contents:
                self._invalid("Gemini request needs a conversation message")
            body = {"contents": contents, "generationConfig": {"maxOutputTokens": limit}}
            if system:
                body["systemInstruction"] = {"parts": system}
            if "temperature" in payload:
                body["generationConfig"]["temperature"] = payload["temperature"]
            url = "https://generativelanguage.googleapis.com/v1beta/models/" + model + ":generateContent"
        elif provider == "cloudflare":
            account = self._account_id()
            if not model.startswith("@cf/") or not re.fullmatch(r"@cf/[A-Za-z0-9._/-]+", model):
                self._invalid("Workers AI model must be an @cf model identifier")
            body = {"messages": payload["messages"], "max_tokens": limit}
            if "temperature" in payload:
                body["temperature"] = payload["temperature"]
            url = "https://api.cloudflare.com/client/v4/accounts/" + account + "/ai/run/" + urllib.parse.quote(model, safe="@/")
        else:
            body = payload | {"max_tokens": limit}
            url = ("https://openrouter.ai/api/v1" if provider == "openrouter" else "https://api.mistral.ai/v1") + "/chat/completions"
        return self._send(provider, "POST", url, key=key, payload=body)

    @staticmethod
    def _invalid(message):
        raise ProviderToolError({"error": "invalid_arguments", "code": "invalid_arguments", "message": message, "uncertain": False})

    def _account_id(self):
        account = self._key("cloudflare/account-id")
        if not re.fullmatch(r"[A-Fa-f0-9]{32}", account):
            self._invalid("Existing Cloudflare account reference must contain its 32-character account ID")
        return account

    def _send(self, provider, method, url, *, key, payload=None):
        headers = {"Accept": "application/json", "User-Agent": "CommonsSharedEquipment/1.0"}
        if key:
            headers["x-goog-api-key" if provider == "gemini" else "Authorization"] = key if provider == "gemini" else "Bearer " + key
        body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        if body is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        maximum = 4 * 1024 * 1024
        try:
            with self.opener(request, timeout=self.timeout) as response:
                status = response.status
                response_headers = response.headers
                raw = response.read(maximum + 1)
        except urllib.error.HTTPError as exc:
            response_headers = exc.headers or {}
            raise ProviderToolError({"error": "provider_http_error", "code": "provider_http_error", "provider": provider,
                "http_status": exc.code, "retry_after": response_headers.get("Retry-After"),
                "rate_limit_headers": self._rate_headers(response_headers), "provider_request_id": response_headers.get("x-request-id"),
                "message": "Provider rejected the request.", "uncertain": method == "POST" and exc.code >= 500}) from None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ProviderToolError({"error": "provider_network_error", "code": type(exc).__name__, "provider": provider,
                "message": "Provider request failed at the network layer.", "uncertain": method == "POST"}) from None
        if len(raw) > maximum:
            raise ProviderToolError({"error": "provider_response_too_large", "code": "provider_response_too_large",
                "provider": provider, "http_status": status, "uncertain": method == "POST"})
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise ProviderToolError({"error": "provider_response_invalid", "code": "provider_response_invalid",
                "provider": provider, "http_status": status, "uncertain": method == "POST"}) from None
        data = self._sanitize(data, key)
        if provider == "cloudflare" and isinstance(data, dict) and data.get("success") is False:
            raise ProviderToolError({"error": "provider_rejected", "code": "provider_rejected", "provider": provider,
                "http_status": status, "provider_error": data.get("errors"), "uncertain": False})
        result = {"provider": provider, "http_status": status, "data": data,
                  "retry_after": response_headers.get("Retry-After"), "rate_limit_headers": self._rate_headers(response_headers),
                  "provider_request_id": response_headers.get("x-request-id") or response_headers.get("request-id")}
        if provider == "openrouter" and isinstance(data, dict):
            result["upstream_backend"] = data.get("provider")
            result["backend_independence_known"] = bool(data.get("provider"))
        return result
