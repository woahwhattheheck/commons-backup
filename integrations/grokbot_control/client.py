#!/usr/bin/env python3
"""Thin peer client for commons-grokbot-control."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

DEFAULT_BASE = "http://127.0.0.1:8881"


class GrokBotControlClient:
    def __init__(self, base_url: str = DEFAULT_BASE) -> None:
        self.base_url = base_url.rstrip("/")

    def _request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        query: dict[str, Any] | None = None,
        timeout: float = 60.0,
    ) -> dict[str, Any]:
        url = self.base_url + path
        if query:
            url += "?" + urllib.parse.urlencode(
                {k: v for k, v in query.items() if v is not None}
            )
        data = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json; charset=utf-8"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            try:
                return json.loads(body)
            except json.JSONDecodeError:
                raise RuntimeError("HTTP %s: %s" % (exc.code, body)) from exc

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health")

    def pools(self) -> dict[str, Any]:
        return self._request("GET", "/v1/pools")

    def submit(
        self,
        prompt: str,
        *,
        pool_id: str = "grokbot",
        seat: str | None = None,
        async_mode: bool = True,
        case: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "pool_id": pool_id,
            "prompt": prompt,
            "async": async_mode,
        }
        if seat:
            body["seat"] = seat
        if case is not None:
            body["case"] = case
        return self._request("POST", "/v1/runs", payload=body)

    def inspect(self, run_id: str, *, wait_ms: int = 0) -> dict[str, Any]:
        return self._request(
            "GET",
            "/v1/runs/%s" % run_id,
            query={"wait_ms": wait_ms} if wait_ms else None,
            timeout=max(60.0, wait_ms / 1000.0 + 5),
        )

    def follow_up(
        self, run_id: str, prompt: str, *, async_mode: bool = True
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/v1/runs/%s/follow-up" % run_id,
            payload={"prompt": prompt, "async": async_mode},
        )

    def cancel(self, run_id: str) -> dict[str, Any]:
        return self._request("POST", "/v1/runs/%s/cancel" % run_id, payload={})

    def session(self, session_id: str) -> dict[str, Any]:
        return self._request("GET", "/v1/sessions/%s" % session_id)

    def events(
        self,
        *,
        after: int = 0,
        limit: int = 50,
        wait_ms: int = 0,
        pool_id: str | None = None,
    ) -> dict[str, Any]:
        return self._request(
            "GET",
            "/v1/events",
            query={
                "after": after,
                "limit": limit,
                "wait_ms": wait_ms,
                "pool_id": pool_id,
            },
            timeout=max(60.0, wait_ms / 1000.0 + 5),
        )
