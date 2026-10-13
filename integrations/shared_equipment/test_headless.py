"""Headless app transport and child-environment checks; no live provider calls."""
import base64
from contextlib import redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

from . import headless


class Reply(io.BytesIO):
    status = 200
    def __enter__(self): return self
    def __exit__(self, *_args): self.close()


class Capture:
    def __init__(self, body=b'{}'):
        self.requests = []
        self.body = body
    def open(self, request, timeout):
        self.requests.append((request.full_url, request.get_method(),
                              json.loads(request.data) if request.data else None))
        return Reply(self.body)


class HeadlessTests(unittest.TestCase):
    def client(self):
        return headless.GrokBotGateway(reader=lambda ref: {
            'baseUrl': 'https://example.invalid', 'token': 'test-only value', 'headers': {}})

    def test_default_reader_is_direct_and_preserves_types(self):
        value = {'typed': ['test-only value', 1, True]}
        with patch.object(headless, 'retrieve_local', return_value=value) as local, \
                patch.object(headless, 'retrieve_http') as http:
            self.assertIs(headless.credential_reader()('example/reference'), value)
            local.assert_called_once_with('example/reference')
            http.assert_not_called()

    def test_optional_http_uses_existing_sealed_client(self):
        with patch.object(headless, 'retrieve_http', return_value='test-only value') as http:
            reader = headless.credential_reader(source='http')
            self.assertEqual(reader('example/reference'), 'test-only value')
            self.assertEqual(http.call_args.args, ('example/reference',))
            self.assertEqual(http.call_args.kwargs['base_url'], 'http://127.0.0.1:8878')
            opener = http.call_args.kwargs['opener'].__self__
            self.assertTrue(any(isinstance(item, headless._NoRedirect) for item in opener.handlers))

    def test_custody_failure_does_not_expose_value(self):
        with patch.object(headless, 'retrieve_local', side_effect=ValueError('test-only private body')):
            with self.assertRaises(headless.HeadlessError) as caught:
                headless.credential_reader()('example/reference')
        self.assertEqual(str(caught.exception), 'credential_retrieval_failed')
        self.assertTrue(caught.exception.__suppress_context__)

    def test_child_env_changes_neither_parent_nor_arguments(self):
        parent = {'KEEP': 'yes', 'ANTHROPIC_API_KEY': 'test-only conflict',
                  'ANTHROPIC_AUTH_TOKEN': 'test-only conflict',
                  'CLAUDE_CODE_OAUTH_TOKEN_FILE': 'test-only path'}
        before = dict(parent)
        reader = unittest.mock.Mock(return_value='test-only oauth')
        child = headless.claude_child_env(reader=reader, base_env=parent, config_dir='/tmp/example-config')
        reader.assert_called_once_with('vault/claude/account/access')
        self.assertEqual(parent, before)
        self.assertEqual(child, {'KEEP': 'yes', 'CLAUDE_CODE_OAUTH_TOKEN': 'test-only oauth',
                                 'CLAUDE_CONFIG_DIR': '/tmp/example-config'})
        real_parent = dict(os.environ)
        headless.claude_child_env(reader=reader)
        self.assertEqual(dict(os.environ), real_parent)

    def test_existing_rpc_shapes_and_stable_operation_id(self):
        client = self.client()
        client._opener = capture = Capture()
        client.health()
        client.list_agents()
        client.send_prompt('agent', 'explicit task', client_nonce='stable-operation')
        client.transcript_tail('agent', before_seq=1, session_id='session')
        client.read_attachment_text('/attachment', agent_id='agent')
        client.read_attachment_chunk('/attachment', offset=2, length=3, agent_id='agent')
        self.assertEqual(capture.requests, [
            ('https://example.invalid/health', 'GET', None),
            ('https://example.invalid/api/listAgents', 'POST', {}),
            ('https://example.invalid/api/sendPrompt', 'POST', {'agentId': 'agent', 'prompt': 'explicit task', 'clientNonce': 'stable-operation'}),
            ('https://example.invalid/api/getAgentTranscriptTail', 'POST', {'id': 'agent', 'limit': 30, 'beforeSeq': 1, 'sessionId': 'session'}),
            ('https://example.invalid/api/readAttachmentText', 'POST', {'path': '/attachment', 'agentId': 'agent'}),
            ('https://example.invalid/api/readAttachmentChunk', 'POST', {'path': '/attachment', 'offset': 2, 'length': 3, 'agentId': 'agent'}),
        ])

    def test_upload_binary_offsets_optional_agent_and_response(self):
        client = self.client()
        client._opener = capture = Capture(b'{"committedPath":"/example/attachment"}')
        binary = bytes(range(256))
        output = io.StringIO()
        with redirect_stdout(output):
            result = client.upload_attachment_chunk(binary, upload_id='stable-upload', filename='example.bin',
                offset=0, total_size=256, agent_id='agent')
            client.upload_attachment_chunk(binary[7:19], upload_id='stable-upload', filename='example.bin',
                offset=7, total_size=256)
        self.assertEqual(result, (200, {'committedPath': '/example/attachment'}))
        self.assertEqual(output.getvalue(), '')
        url, method, first = capture.requests[0]
        self.assertEqual((url, method), ('https://example.invalid/api/uploadAttachmentChunk', 'POST'))
        self.assertEqual(first, {'uploadId': 'stable-upload', 'filename': 'example.bin', 'offset': 0,
            'totalSize': 256, 'agentId': 'agent', 'bytesBase64': base64.b64encode(binary).decode('ascii')})
        self.assertEqual(base64.b64decode(first['bytesBase64'], validate=True), binary)
        second = capture.requests[1][2]
        self.assertEqual((second['offset'], second['totalSize']), (7, 256))
        self.assertNotIn('agentId', second)
        self.assertEqual(base64.b64decode(second['bytesBase64'], validate=True), binary[7:19])

    def test_invalid_upload_ranges_never_make_request_or_expose_input(self):
        client = self.client()
        client._opener = capture = Capture()
        for chunk, offset, total in [('test-only private input', 0, 50), (b'ab', 0, 1),
                                     (b'a', -1, 2), (b'a', 0, -1), (b'a', True, 2),
                                     (b'a', 0, True), (b'', 3, 2)]:
            with self.subTest(offset=offset, total=total):
                with self.assertRaises(headless.HeadlessError) as caught:
                    client.upload_attachment_chunk(chunk, upload_id='stable-upload', filename='file',
                        offset=offset, total_size=total)
                self.assertIn(str(caught.exception), ('upload_bytes_required', 'upload_range_invalid'))
        self.assertEqual(capture.requests, [])

    def test_http_and_upload_errors_redact_provider_body(self):
        client = self.client()
        error = urllib.error.HTTPError('https://example.invalid', 403, 'test-only private reason',
                                       {}, io.BytesIO(b'test-only private body'))
        client._opener = unittest.mock.Mock()
        client._opener.open.side_effect = error
        for call in (client.health, lambda: client.upload_attachment_chunk(b'a', upload_id='id',
                     filename='file', offset=0, total_size=1)):
            with self.assertRaises(headless.HeadlessError) as caught:
                call()
            self.assertEqual((str(caught.exception), caught.exception.http_status), ('gateway_http_error', 403))
            self.assertTrue(caught.exception.__suppress_context__)
        self.assertEqual(client._opener.open.call_count, 2)  # No implicit retry.

    def test_real_redirect_is_rejected_before_second_request(self):
        visits = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args): pass
            def do_GET(self):
                visits.append(self.path)
                self.send_response(302 if self.path == '/start' else 200)
                if self.path == '/start': self.send_header('Location', '/sink')
                self.send_header('Content-Length', '0')
                self.end_headers()
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            request = urllib.request.Request('http://127.0.0.1:%d/start' % server.server_port,
                                             headers={'Authorization': 'test-only value'})
            with self.assertRaises(urllib.error.HTTPError) as caught:
                urllib.request.build_opener(headless._NoRedirect).open(request, timeout=5)
            self.assertEqual(caught.exception.code, 302)
            self.assertEqual(visits, ['/start'])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_default_cli_exposes_metadata_and_never_prompts(self):
        with patch.object(headless, 'GrokBotGateway') as constructor:
            client = constructor.return_value
            client.health.return_value = (200, {'ok': True, 'private': 'test-only private response'})
            client.list_agents.return_value = (200, [{'id': 'test-only agent'}])
            output = io.StringIO()
            with redirect_stdout(output): self.assertEqual(headless.main([]), 0)
            result = json.loads(output.getvalue())
            self.assertEqual(result['agent_count'], 1)
            self.assertTrue(result['ok'])
            self.assertNotIn('private', output.getvalue())
            self.assertNotIn('test-only', output.getvalue())
            self.assertEqual([call[0] for call in client.method_calls], ['health', 'list_agents'])


if __name__ == '__main__':
    unittest.main()
