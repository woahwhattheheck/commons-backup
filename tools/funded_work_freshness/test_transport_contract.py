from __future__ import annotations

import io
import unittest
from unittest import mock

from funded_work_freshness import Candidate, EvidenceError, MAX_HTTP_BYTES
from transport import (
    UrlLibTransport,
    read_bounded,
    validate_public_destination,
    validate_redirect_destination,
)


class TransportContractTests(unittest.TestCase):
    def test_public_network_fence_rejects_loopback_resolution(self):
        with mock.patch("transport.socket.getaddrinfo") as lookup:
            lookup.return_value = [(2, 1, 6, "", ("127.0.0.1", 443))]
            with self.assertRaises(EvidenceError) as caught:
                validate_public_destination("https://board.example/reward")
        self.assertEqual(caught.exception.code, "unsafe_destination")

    def test_connection_uses_validated_ip_not_hostname(self):
        reply = mock.MagicMock()
        reply.status = 200
        reply.read.return_value = b"ok"
        reply.getheaders.return_value = []
        connection = mock.MagicMock()
        connection.getresponse.return_value = reply
        with (
            mock.patch("transport.socket.getaddrinfo") as lookup,
            mock.patch(
                "transport.http.client.HTTPConnection", return_value=connection
            ) as connector,
        ):
            lookup.return_value = [(2, 1, 6, "", ("93.184.216.34", 80))]
            response = UrlLibTransport(timeout=1).fetch(
                "http://board.example/reward", accept="text/plain"
            )
        connector.assert_called_once_with("93.184.216.34", port=80, timeout=1)
        self.assertEqual(lookup.call_count, 1)
        self.assertEqual(response.body, b"ok")

    def test_redirect_stays_inside_recognized_sponsor_domain_family(self):
        with mock.patch("transport.socket.getaddrinfo") as lookup:
            lookup.return_value = [(2, 1, 6, "", ("8.8.8.8", 443))]
            validate_redirect_destination(
                "https://algora.io/bounties/1",
                "https://console.algora.io/bounties/1",
            )
            with self.assertRaises(EvidenceError) as caught:
                validate_redirect_destination(
                    "https://algora.io/bounties/1",
                    "https://evilalgora.io/redirected",
                )
        self.assertEqual(caught.exception.code, "unsafe_redirect")

    def test_non_sponsor_read_rejects_cross_host_redirect(self):
        with mock.patch("transport.socket.getaddrinfo") as lookup:
            lookup.return_value = [(2, 1, 6, "", ("8.8.8.8", 443))]
            with self.assertRaises(EvidenceError) as caught:
                validate_redirect_destination(
                    "https://api.github.com/repos/acme/widget/issues/1",
                    "https://attacker.example/redirected",
                )
        self.assertEqual(caught.exception.code, "unsafe_redirect")

    def test_bounded_reader_rejects_oversized_response(self):
        with self.assertRaises(EvidenceError) as caught:
            read_bounded(io.BytesIO(b"x" * (MAX_HTTP_BYTES + 1)))
        self.assertEqual(caught.exception.code, "response_too_large")

    def test_invalid_url_port_is_input_error(self):
        with self.assertRaises(ValueError):
            Candidate.validated(
                candidate_url="https://example.com:bad/reward",
                platform="fixture",
                advertised_amount="5",
                currency="USD",
            )
