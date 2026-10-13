from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from .core import CoordinationError, Envelope, MailCoordinator, QueueRequest


class CoordinatorHandler(BaseHTTPRequestHandler):
    coordinator: MailCoordinator
    server_version = "CommonsMailCoordinator/1.0"

    def _send(self, status: int, value: dict[str, Any] | list[Any]) -> None:
        payload = json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def _body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > 2_100_000:
            raise ValueError("request body must be between 1 byte and 2.1 MB")
        value = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("request body must be a JSON object")
        if "now" in value:
            raise ValueError("now is service-owned and cannot be supplied by a client")
        return value

    def _dispatch(self) -> tuple[int, dict[str, Any] | list[Any]]:
        parsed = urlparse(self.path)
        if self.command == "GET" and parsed.path == "/health":
            return HTTPStatus.OK, {"status": "ok", "service": "mail-coordinator", "version": 1}
        if self.command == "GET" and parsed.path == "/v1/ready":
            query = parse_qs(parsed.query)
            mailbox = query.get("mailbox", [None])[0]
            limit = int(query.get("limit", ["100"])[0])
            return HTTPStatus.OK, self.coordinator.list_ready(mailbox=mailbox, limit=limit)
        if self.command == "GET" and parsed.path.startswith("/v1/messages/"):
            message_id = parsed.path.removeprefix("/v1/messages/")
            return HTTPStatus.OK, self.coordinator.status(message_id)
        if self.command != "POST":
            return HTTPStatus.NOT_FOUND, {"error": "NOT_FOUND"}

        body = self._body()
        if parsed.path == "/v1/inbounds":
            result = self.coordinator.record_inbound(**body)
        elif parsed.path == "/v1/messages":
            envelope_data = body.pop("envelope")
            result = self.coordinator.enqueue(QueueRequest(envelope=Envelope(**envelope_data), **body)).as_dict()
        elif parsed.path == "/v1/claims":
            result = self.coordinator.claim(**body)
            result = {
                "claim_id": result.claim_id,
                "message_id": result.message_id,
                "worker_id": result.worker_id,
                "lease_until": result.lease_until,
                "body_sha256": result.body_sha256,
                "envelope": {
                    "sender": result.envelope.sender,
                    "to": result.envelope.to,
                    "cc": result.envelope.cc,
                    "bcc": result.envelope.bcc,
                    "subject": result.envelope.subject,
                    "body": result.envelope.body,
                },
            }
        elif parsed.path == "/v1/attempts":
            result = self.coordinator.begin_attempt(**body)
        elif parsed.path == "/v1/receipts":
            result = self.coordinator.record_provider_receipt(**body)
        elif parsed.path == "/v1/uncertain":
            result = self.coordinator.mark_uncertain(**body)
        elif parsed.path == "/v1/reconcile-not-sent":
            result = self.coordinator.reconcile_not_sent(**body)
        elif parsed.path == "/v1/suppressions":
            result = self.coordinator.suppress(**body)
        else:
            return HTTPStatus.NOT_FOUND, {"error": "NOT_FOUND"}
        return HTTPStatus.OK, result

    def do_GET(self) -> None:  # noqa: N802
        self._handle()

    def do_POST(self) -> None:  # noqa: N802
        self._handle()

    def _handle(self) -> None:
        try:
            status, payload = self._dispatch()
        except CoordinationError as exc:
            status = HTTPStatus.NOT_FOUND if exc.code == "NOT_FOUND" else HTTPStatus.CONFLICT if exc.code not in ("VALIDATION_ERROR",) else HTTPStatus.BAD_REQUEST
            payload = {"error": exc.code, "message": str(exc), "details": exc.details}
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            status = HTTPStatus.BAD_REQUEST
            payload = {"error": "BAD_REQUEST", "message": str(exc)}
        self._send(int(status), payload)

    def log_message(self, format: str, *args: object) -> None:
        return


def serve(coordinator: MailCoordinator, host: str = "127.0.0.1", port: int = 8788) -> None:
    coordinator.initialize()
    handler = type("BoundCoordinatorHandler", (CoordinatorHandler,), {"coordinator": coordinator})
    ThreadingHTTPServer((host, port), handler).serve_forever()
