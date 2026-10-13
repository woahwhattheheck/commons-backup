"""Shared provider tools, including the no-key Jina public URL reader.

Provider keys are fetched only at call time and remain in memory.  The outer
shared-equipment carrier owns request_id/call_id journaling and replay policy;
this adapter never retries a provider request.
"""

from __future__ import annotations

import copy
import json
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any

from .provider_io import _NoRedirect, redacted


GROQ_BASE = "https://api.groq.com/openai/v1"
EXA_BASE = "https://api.exa.ai"
JINA_READER_BASE = "https://r.jina.ai/"
PARALLEL_FREE_MCP = "https://search.parallel.ai/mcp"
MAX_RESPONSE_BYTES = 12 * 1024 * 1024
MAX_READER_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_PROMPT_CHARS = 300_000
MAX_MESSAGES = 100
MAX_CHAT_COMPLETION_TOKENS = 8192
MAX_SEARCH_RESULTS = 10
MAX_CONTENT_URLS = 5


def _tool(name: str, description: str, properties: dict, required: list[str] | None = None) -> dict:
    return {
        "name": name,
        "description": description,
        "inputSchema": {
            "type": "object",
            "properties": properties,
            "required": required or [],
            "additionalProperties": False,
        },
    }


TOOLS = [
    _tool("parallel_anonymous_tools", "Discover the current anonymous Parallel MCP tool schemas. No key, paid fallback or automatic retry.", {}),
    _tool(
        "parallel_anonymous_search",
        "Search with the anonymous free Parallel MCP. Send a stable conversation session_id across related search/fetch calls. Never adds a key, upgrades to a paid endpoint, or automatically retries.",
        {
            "objective": {"type": "string", "minLength": 1, "maxLength": 4096},
            "search_queries": {"type": "array", "minItems": 1, "maxItems": 8,
                               "items": {"type": "string", "minLength": 1, "maxLength": 500}},
            "session_id": {"type": "string", "minLength": 1, "maxLength": 100},
        },
        ["objective", "search_queries"],
    ),
    _tool(
        "parallel_anonymous_fetch",
        "Read public HTTP(S) URLs with the anonymous free Parallel MCP. Reuse search session_id and search_queries when fetching its results. No key, paid fallback or automatic retry.",
        {
            "urls": {"type": "array", "minItems": 1, "maxItems": 20,
                     "items": {"type": "string", "minLength": 8, "maxLength": 2048}},
            "objective": {"type": "string", "maxLength": 200},
            "search_queries": {"type": "array", "maxItems": 8,
                               "items": {"type": "string", "minLength": 1, "maxLength": 500}},
            "full_content": {"type": "boolean"},
            "session_id": {"type": "string", "minLength": 1, "maxLength": 100},
        },
        ["urls"],
    ),
    _tool(
        "jina_public_read",
        "Read one publicly accessible HTTP(S) URL through Jina Reader without an API key. Uses the free per-IP pool; returns status and cooldown headers and never retries a provider request.",
        {"url": {"type": "string", "minLength": 8, "maxLength": 2048}},
        ["url"],
    ),
    _tool(
        "groq_list_models",
        "List models available to the shared Groq account. Uses the shared secure groq/api-key reference.",
        {},
    ),
    _tool(
        "groq_chat_completion",
        "Create one non-streaming Groq chat completion. Uses the shared secure groq/api-key reference and never retries a provider call.",
        {
            "model": {"type": "string", "minLength": 1, "maxLength": 200},
            "messages": {
                "type": "array",
                "minItems": 1,
                "maxItems": MAX_MESSAGES,
                "items": {
                    "type": "object",
                    "properties": {
                        "role": {"type": "string", "enum": ["system", "developer", "user", "assistant", "tool"]},
                        "content": {"type": "string"},
                        "name": {"type": "string"},
                        "tool_call_id": {"type": "string"},
                    },
                    "required": ["role", "content"],
                    "additionalProperties": True,
                },
            },
            "max_completion_tokens": {"type": "integer", "minimum": 1, "maximum": MAX_CHAT_COMPLETION_TOKENS},
            "temperature": {"type": "number", "minimum": 0, "maximum": 2},
            "top_p": {"type": "number", "exclusiveMinimum": 0, "maximum": 1},
            "stop": {
                "oneOf": [
                    {"type": "string", "maxLength": 256},
                    {"type": "array", "maxItems": 4, "items": {"type": "string", "maxLength": 256}},
                ]
            },
        },
        ["model", "messages"],
    ),
    _tool(
        "exa_search",
        "Search the web with Exa. Results contain URLs and metadata by default; request page text or highlights only when needed. Uses the shared secure exa/api-key reference.",
        {
            "query": {"type": "string", "minLength": 1, "maxLength": 2000},
            "num_results": {"type": "integer", "minimum": 1, "maximum": MAX_SEARCH_RESULTS},
            "include_text": {"type": "boolean"},
            "include_highlights": {"type": "boolean"},
        },
        ["query"],
    ),
    _tool(
        "exa_contents",
        "Retrieve page text and optional highlights for up to five HTTP(S) URLs using Exa's Contents API. Uses the shared secure exa/api-key reference.",
        {
            "urls": {
                "type": "array",
                "minItems": 1,
                "maxItems": MAX_CONTENT_URLS,
                "items": {"type": "string", "minLength": 8, "maxLength": 2048},
            },
            "include_text": {"type": "boolean"},
            "include_highlights": {"type": "boolean"},
        },
        ["urls"],
    ),
]


class ProviderToolError(RuntimeError):
    def __init__(self, result: dict[str, Any]):
        super().__init__(str(result.get("code", "provider_error")))
        self.result = result


class GroqExaEquipment:
    """Provider extension for inference, search and no-key public URL reading."""

    def __init__(self, *, credential_sources=None, opener=None, timeout: float = 30):
        self.credential_sources = credential_sources
        self.opener = opener or urllib.request.urlopen
        self.reader_opener = opener or urllib.request.build_opener(_NoRedirect()).open
        self.timeout = min(60.0, max(1.0, float(timeout)))
        self.parallel_protocol = "2025-03-26"
        self.parallel_session = None
        self.parallel_initialized = False
        self.parallel_conversation = uuid.uuid4().hex

    def tools(self, **_kwargs) -> list[dict]:
        return copy.deepcopy(TOOLS)

    def call(self, name: str, arguments: dict) -> dict:
        try:
            result = self._call(name, arguments)
            return {"isError": False, "result": result, "uncertain": False}
        except ProviderToolError as exc:
            return {"isError": True, **exc.result}
        except Exception as exc:
            # Do not put exception text, URLs, request bodies, or provider keys
            # into the shared journal or carrier response.
            return {
                "isError": True,
                "error": "provider_request_failed",
                "code": type(exc).__name__,
                "message": "Provider request failed before a usable response was received.",
                "uncertain": False,
            }

    def _call(self, name: str, args: dict) -> dict:
        if name in {"parallel_anonymous_search", "parallel_anonymous_fetch", "parallel_anonymous_tools"}:
            arguments = {} if name == "parallel_anonymous_tools" else self._parallel_arguments(name, args)
            if not self.parallel_initialized:
                initialized = self._parallel_rpc("initialize", {
                    "protocolVersion": self.parallel_protocol,
                    "capabilities": {},
                    "clientInfo": {"name": "CommonsSharedEquipment", "version": "1.0"},
                })
                self.parallel_protocol = initialized["data"].get("protocolVersion", self.parallel_protocol)
                self._parallel_rpc("notifications/initialized", {}, notification=True)
                self.parallel_initialized = True
            if name == "parallel_anonymous_tools":
                return self._parallel_rpc("tools/list", {})
            tool = "web_search" if name == "parallel_anonymous_search" else "web_fetch"
            return self._parallel_rpc("tools/call", {"name": tool, "arguments": arguments})
        if name == "jina_public_read":
            value = args.get("url")
            if not isinstance(value, str) or len(value) > 2048 or any(ord(char) < 33 for char in value):
                raise ProviderToolError({"error": "invalid_arguments", "code": "invalid_url", "message": "url must be HTTP(S) text up to 2048 characters without embedded credentials.", "uncertain": False})
            try:
                parsed = urllib.parse.urlsplit(value)
                hostname, port = parsed.hostname, parsed.port
            except ValueError:
                parsed, hostname = None, None
            if parsed is None or parsed.scheme not in {"http", "https"} or not hostname or parsed.username or parsed.password:
                raise ProviderToolError({"error": "invalid_arguments", "code": "invalid_url", "message": "url must be HTTP(S) text without embedded credentials.", "uncertain": False})
            # Fragments are client-side references, not part of the fetched URL.
            target = urllib.parse.urlunsplit(parsed._replace(fragment=""))
            return self._request("jina", "GET", JINA_READER_BASE + target, key="",
                                 response_limit=MAX_READER_RESPONSE_BYTES, opener=self.reader_opener)
        if name == "groq_list_models":
            key = self._key("groq/api-key")
            return self._request("groq", "GET", GROQ_BASE + "/models", key=key)
        if name == "groq_chat_completion":
            key = self._key("groq/api-key")
            payload = self._groq_chat_payload(args)
            return self._request("groq", "POST", GROQ_BASE + "/chat/completions", key=key, payload=payload)
        if name == "exa_search":
            key = self._key("exa/api-key")
            payload = self._exa_search_payload(args)
            return self._request("exa", "POST", EXA_BASE + "/search", key=key, payload=payload)
        if name == "exa_contents":
            key = self._key("exa/api-key")
            payload = self._exa_contents_payload(args)
            return self._request("exa", "POST", EXA_BASE + "/contents", key=key, payload=payload)
        raise ProviderToolError({
            "error": "unknown_provider_tool",
            "code": "unknown_provider_tool",
            "message": "Unknown shared provider tool.",
            "uncertain": False,
        })

    def _parallel_arguments(self, name: str, args: dict) -> dict:
        def invalid():
            raise ProviderToolError({"error": "invalid_arguments", "code": "invalid_parallel_arguments",
                                     "message": "Parallel arguments do not match the advertised tool schema.", "uncertain": False})
        session = args.get("session_id", self.parallel_conversation)
        if not isinstance(session, str) or not 1 <= len(session) <= 100:
            invalid()
        result = {"session_id": session}
        queries = args.get("search_queries")
        if queries is not None:
            if not isinstance(queries, list) or len(queries) > 8 or any(not isinstance(q, str) or not q.strip() or len(q) > 500 for q in queries):
                invalid()
            result["search_queries"] = queries
        objective = args.get("objective")
        if name == "parallel_anonymous_search":
            if not isinstance(objective, str) or not objective.strip() or len(objective) > 4096 or not queries:
                invalid()
            result["objective"] = objective
        else:
            if objective is not None:
                if not isinstance(objective, str) or len(objective) > 200:
                    invalid()
                result["objective"] = objective
            urls = args.get("urls")
            if not isinstance(urls, list) or not 1 <= len(urls) <= 20:
                invalid()
            for url in urls:
                if not isinstance(url, str) or len(url) > 2048 or any(ord(char) < 33 for char in url):
                    invalid()
                try:
                    parsed = urllib.parse.urlsplit(url)
                    hostname, port = parsed.hostname, parsed.port
                except ValueError:
                    invalid()
                if parsed.scheme not in {"http", "https"} or not hostname or parsed.username or parsed.password:
                    invalid()
            result["urls"] = urls
            if "full_content" in args:
                if not isinstance(args["full_content"], bool):
                    invalid()
                result["full_content"] = args["full_content"]
        return result

    def _parallel_rpc(self, method: str, params: dict, *, notification: bool = False) -> dict:
        request_id = uuid.uuid4().hex
        payload = {"jsonrpc": "2.0", "method": method, "params": params}
        if not notification:
            payload["id"] = request_id
        headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json",
                   "MCP-Protocol-Version": self.parallel_protocol}
        if self.parallel_session:
            headers["Mcp-Session-Id"] = self.parallel_session
        request = urllib.request.Request(PARALLEL_FREE_MCP, data=json.dumps(payload).encode("utf-8"),
                                         headers=headers, method="POST")
        try:
            with self.reader_opener(request, timeout=self.timeout) as response:
                status = int(getattr(response, "status", None) or response.getcode())
                response_headers = response.headers
                raw = response.read(MAX_READER_RESPONSE_BYTES + 1)
                self.parallel_session = response_headers.get("Mcp-Session-Id") or self.parallel_session
        except urllib.error.HTTPError as exc:
            try:
                raw = exc.read(MAX_READER_RESPONSE_BYTES + 1)
            except Exception:
                raw = b""
            error = self._safe_error_body(raw, "")
            try:
                diagnostic = json.loads(raw)
                if isinstance(diagnostic, dict):
                    error = {**(error if isinstance(error, dict) else {}),
                             **{field: diagnostic[field] for field in ("error_code", "error_name", "retryable", "owner_action_required")
                                if isinstance(diagnostic.get(field), (str, int, bool))}}
            except (ValueError, UnicodeDecodeError):
                pass
            raise ProviderToolError({"error": "provider_http_error", "code": "provider_http_error", "provider": "parallel",
                                     "http_status": int(exc.code), "provider_error": redacted(error),
                                     "retry_after": (exc.headers or {}).get("Retry-After"),
                                     "rate_limit_headers": self._rate_headers(exc.headers or {}),
                                     "message": "Anonymous Parallel MCP rejected the request.", "uncertain": False}) from None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ProviderToolError({"error": "provider_network_error", "code": type(exc).__name__, "provider": "parallel",
                                     "message": "Anonymous Parallel MCP failed at the network layer.", "uncertain": False}) from None
        metadata = {"provider": "parallel", "http_status": status,
                    "retry_after": response_headers.get("Retry-After"),
                    "rate_limit_headers": self._rate_headers(response_headers),
                    "provider_request_id": response_headers.get("x-request-id") or response_headers.get("request-id")}
        if len(raw) > MAX_READER_RESPONSE_BYTES:
            raise ProviderToolError({**metadata, "error": "provider_response_too_large", "code": "provider_response_too_large",
                                     "message": "Anonymous Parallel MCP exceeded the response-size limit.", "uncertain": False})
        if notification and status in {200, 202, 204} and not raw.strip():
            return {**metadata, "data": {}}
        try:
            text = raw.decode("utf-8")
            if "text/event-stream" in response_headers.get("Content-Type", ""):
                messages = []
                for event in text.replace("\r\n", "\n").split("\n\n"):
                    data = "\n".join(line[5:].lstrip() for line in event.splitlines() if line.startswith("data:"))
                    if data:
                        messages.append(json.loads(data))
                parsed = next(message for message in messages if message.get("id") == request_id)
            else:
                parsed = json.loads(text)
            if not isinstance(parsed, dict) or parsed.get("id") != request_id:
                raise ValueError()
        except (ValueError, UnicodeDecodeError, StopIteration, AttributeError):
            raise ProviderToolError({**metadata, "error": "provider_response_invalid", "code": "provider_response_invalid",
                                     "message": "Anonymous Parallel MCP returned an invalid JSON-RPC response.", "uncertain": False}) from None
        if "error" in parsed or not isinstance(parsed.get("result"), dict) or parsed["result"].get("isError"):
            raise ProviderToolError({**metadata, "error": "provider_tool_error", "code": "provider_tool_error",
                                     "provider_error": redacted(parsed.get("error", parsed.get("result"))),
                                     "message": "Anonymous Parallel MCP reported a tool error.", "uncertain": False})
        return {**metadata, "data": redacted(parsed["result"])}

    def _key(self, reference: str) -> str:
        sources = self.credential_sources
        if sources is None:
            from .credential_transfer import CredentialSources
            sources = CredentialSources()
            self.credential_sources = sources
        try:
            value = sources.read(reference)
        except Exception:
            raise ProviderToolError({
                "error": "credential_unavailable",
                "code": "credential_unavailable",
                "provider": reference.split("/", 1)[0],
                "message": "The provider credential is not available from the shared secure credential facility.",
                "uncertain": False,
            }) from None
        if not isinstance(value, str) or not value.strip():
            raise ProviderToolError({
                "error": "credential_unavailable",
                "code": "credential_unavailable",
                "provider": reference.split("/", 1)[0],
                "message": "The provider credential is not available from the shared secure credential facility.",
                "uncertain": False,
            })
        return value.strip()

    @staticmethod
    def _groq_chat_payload(args: dict) -> dict:
        model = args.get("model")
        messages = args.get("messages")
        if not isinstance(model, str) or not model.strip() or len(model) > 200:
            raise ProviderToolError({"error": "invalid_arguments", "code": "invalid_model", "message": "model must be non-empty text up to 200 characters.", "uncertain": False})
        if not isinstance(messages, list) or not 1 <= len(messages) <= MAX_MESSAGES:
            raise ProviderToolError({"error": "invalid_arguments", "code": "invalid_messages", "message": "messages must contain between 1 and 100 items.", "uncertain": False})
        normalized = []
        content_size = 0
        for message in messages:
            if not isinstance(message, dict) or message.get("role") not in {"system", "developer", "user", "assistant", "tool"}:
                raise ProviderToolError({"error": "invalid_arguments", "code": "invalid_message", "message": "Each message needs a supported role and text content.", "uncertain": False})
            content = message.get("content")
            if not isinstance(content, str):
                raise ProviderToolError({"error": "invalid_arguments", "code": "invalid_message", "message": "Each message content must be text.", "uncertain": False})
            content_size += len(content)
            if content_size > MAX_PROMPT_CHARS:
                raise ProviderToolError({"error": "invalid_arguments", "code": "prompt_too_large", "message": "Combined message content exceeds the local request limit.", "uncertain": False})
            row = {"role": message["role"], "content": content}
            if isinstance(message.get("name"), str):
                row["name"] = message["name"]
            if isinstance(message.get("tool_call_id"), str):
                row["tool_call_id"] = message["tool_call_id"]
            normalized.append(row)
        payload = {"model": model.strip(), "messages": normalized, "stream": False}
        if "max_completion_tokens" in args:
            value = args["max_completion_tokens"]
            if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= MAX_CHAT_COMPLETION_TOKENS:
                raise ProviderToolError({"error": "invalid_arguments", "code": "invalid_max_completion_tokens", "message": "max_completion_tokens must be an integer from 1 to 8192.", "uncertain": False})
            payload["max_completion_tokens"] = value
        for field, low, high in (("temperature", 0, 2), ("top_p", 0, 1)):
            if field in args:
                value = args[field]
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not low <= value <= high or field == "top_p" and value == 0:
                    raise ProviderToolError({"error": "invalid_arguments", "code": "invalid_" + field, "message": field + " is outside the supported range.", "uncertain": False})
                payload[field] = value
        if "stop" in args:
            stop = args["stop"]
            if isinstance(stop, str) and len(stop) <= 256:
                payload["stop"] = stop
            elif isinstance(stop, list) and len(stop) <= 4 and all(isinstance(item, str) and len(item) <= 256 for item in stop):
                payload["stop"] = stop
            else:
                raise ProviderToolError({"error": "invalid_arguments", "code": "invalid_stop", "message": "stop must be text or up to four short text values.", "uncertain": False})
        return payload

    @staticmethod
    def _exa_search_payload(args: dict) -> dict:
        query = args.get("query")
        if not isinstance(query, str) or not query.strip() or len(query) > 2000:
            raise ProviderToolError({"error": "invalid_arguments", "code": "invalid_query", "message": "query must be non-empty text up to 2000 characters.", "uncertain": False})
        count = args.get("num_results", 5)
        if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= MAX_SEARCH_RESULTS:
            raise ProviderToolError({"error": "invalid_arguments", "code": "invalid_num_results", "message": "num_results must be an integer from 1 to 10.", "uncertain": False})
        for field in ("include_text", "include_highlights"):
            if field in args and not isinstance(args[field], bool):
                raise ProviderToolError({"error": "invalid_arguments", "code": "invalid_" + field, "message": field + " must be a boolean.", "uncertain": False})
        payload: dict[str, Any] = {"query": query.strip(), "type": "auto", "numResults": count}
        if args.get("include_text") or args.get("include_highlights"):
            contents: dict[str, Any] = {}
            if args.get("include_text"):
                contents["text"] = True
            if args.get("include_highlights"):
                contents["highlights"] = {"query": query.strip()}
            payload["contents"] = contents
        return payload

    @staticmethod
    def _exa_contents_payload(args: dict) -> dict:
        urls = args.get("urls")
        if not isinstance(urls, list) or not 1 <= len(urls) <= MAX_CONTENT_URLS:
            raise ProviderToolError({"error": "invalid_arguments", "code": "invalid_urls", "message": "urls must contain between 1 and 5 HTTP(S) URLs.", "uncertain": False})
        for field in ("include_text", "include_highlights"):
            if field in args and not isinstance(args[field], bool):
                raise ProviderToolError({"error": "invalid_arguments", "code": "invalid_" + field, "message": field + " must be a boolean.", "uncertain": False})
        safe_urls = []
        for value in urls:
            if not isinstance(value, str) or len(value) > 2048 or any(ord(char) < 32 for char in value):
                raise ProviderToolError({"error": "invalid_arguments", "code": "invalid_url", "message": "Each URL must be valid HTTP(S) text up to 2048 characters.", "uncertain": False})
            try:
                parsed = urllib.parse.urlsplit(value)
            except ValueError:
                parsed = None
            if parsed is None or parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password:
                raise ProviderToolError({"error": "invalid_arguments", "code": "invalid_url", "message": "Each URL must be valid HTTP(S) text without embedded credentials.", "uncertain": False})
            safe_urls.append(value)
        payload: dict[str, Any] = {"urls": safe_urls}
        if args.get("include_text", True):
            payload["text"] = True
        if args.get("include_highlights"):
            payload["highlights"] = True
        return payload

    def _request(self, provider: str, method: str, url: str, *, key: str, payload: dict | None = None,
                 response_limit: int = MAX_RESPONSE_BYTES, opener=None) -> dict:
        body = None if payload is None else json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        headers = {"Accept": "application/json"}
        if provider == "groq":
            headers["Authorization"] = "Bearer " + key
            headers["User-Agent"] = "CommonsSharedEquipment/1.0"
        elif provider == "exa":
            headers["x-api-key"] = key
        elif provider == "jina":
            headers["X-Timeout"] = str(int(self.timeout))
        if body is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            response = (opener or self.opener)(request, timeout=self.timeout)
            with response:
                status = getattr(response, "status", None) or response.getcode()
                raw = response.read(response_limit + 1)
                response_headers = response.headers
        except urllib.error.HTTPError as exc:
            body_read_failed = False
            try:
                raw = exc.read(response_limit + 1)
            except Exception:
                raw = b""
                body_read_failed = True
            safe_body = None if body_read_failed else self._safe_error_body(raw, key)
            headers = exc.headers or {}
            raise ProviderToolError({
                "error": "provider_http_error",
                "code": "provider_http_error",
                "provider": provider,
                "http_status": int(exc.code),
                "provider_error": safe_body,
                "retry_after": headers.get("Retry-After"),
                "rate_limit_headers": self._rate_headers(headers),
                "provider_request_id": headers.get("x-request-id") or headers.get("request-id"),
                "message": "Provider rejected the request.",
                "uncertain": method == "POST" and int(exc.code) >= 500,
                "error_body_read_failed": body_read_failed,
            }) from None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ProviderToolError({
                "error": "provider_network_error",
                "code": type(exc).__name__,
                "provider": provider,
                "message": "Provider request failed at the network layer.",
                "uncertain": method == "POST",
            }) from None
        if len(raw) > response_limit:
            raise ProviderToolError({
                "error": "provider_response_too_large",
                "code": "provider_response_too_large",
                "provider": provider,
                "http_status": int(status),
                "message": "Provider response exceeded the local response-size limit.",
                "uncertain": method == "POST",
            })
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise ProviderToolError({
                "error": "provider_response_invalid",
                "code": "provider_response_invalid",
                "provider": provider,
                "http_status": int(status),
                "message": "Provider returned a non-JSON response.",
                "uncertain": method == "POST",
            }) from None
        result = self._sanitize(parsed, key)
        if provider == "jina":
            return {
                "provider": provider,
                "http_status": int(status),
                "retry_after": response_headers.get("Retry-After"),
                "rate_limit_headers": self._rate_headers(response_headers),
                "provider_request_id": response_headers.get("x-request-id") or response_headers.get("request-id"),
                "data": result,
            }
        return result

    @staticmethod
    def _safe_error_body(raw: bytes, key: str) -> dict | str | None:
        if len(raw) > MAX_RESPONSE_BYTES:
            return {"truncated": True}
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return None
        if isinstance(parsed, dict):
            error = parsed.get("error", parsed)
            if isinstance(error, dict):
                result = {}
                for field in ("code", "type", "message", "param"):
                    if isinstance(error.get(field), (str, int, float)):
                        result[field] = error[field]
                return GroqExaEquipment._sanitize(result, key)
            if isinstance(error, str):
                return {"message": GroqExaEquipment._sanitize(error, key)}
        return {"type": "provider_error"}

    @staticmethod
    def _sanitize(value: Any, key: str) -> Any:
        if isinstance(value, str):
            safe = value.replace(key, "[REDACTED]") if key else value
            return redacted(safe)
        if isinstance(value, list):
            return [GroqExaEquipment._sanitize(item, key) for item in value]
        if isinstance(value, dict):
            safe = {}
            for name, item in value.items():
                safe_name = str(name).replace(key, "[REDACTED]") if key else str(name)
                safe[str(redacted(safe_name))] = GroqExaEquipment._sanitize(item, key)
            return safe
        return value

    @staticmethod
    def _rate_headers(headers) -> dict[str, str]:
        allowed = (
            "retry-after",
            "x-ratelimit-limit-requests",
            "x-ratelimit-remaining-requests",
            "x-ratelimit-reset-requests",
            "x-ratelimit-limit-tokens",
            "x-ratelimit-remaining-tokens",
            "x-ratelimit-reset-tokens",
            "x-ratelimit-limit",
            "x-ratelimit-remaining",
            "x-ratelimit-reset",
        )
        return {name: value for name in allowed if (value := headers.get(name)) is not None}
