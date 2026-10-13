"""Direct Commons credentials for Claude and the existing Grok Bot app gateway.

Standard-library service adapter using existing Commons credential custody. The default CLI performs health and agent-count reads
only. API responses stay in caller memory and may contain private content.
No credential files are created, no prompts are sent automatically, and network
errors are not retried: retain a send_prompt client_nonce for the same operation.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from typing import Any, Callable, Mapping
import urllib.error
import urllib.parse
import urllib.request

from .credential_client import retrieve_http, retrieve_local

Reader = Callable[[str], Any]
CONNECTION_REF = 'vault/grokbot/local-exec/local-exec-daemon-connection'


class HeadlessError(RuntimeError):
    """Stable error code and optional HTTP status, without private response data."""

    def __init__(self, code: str, *, http_status: int | None = None):
        super().__init__(code)
        self.code = code
        self.http_status = http_status


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        return None


def credential_reader(*, source: str = 'local',
                      gateway_url: str = 'http://127.0.0.1:8878') -> Reader:
    """Use Commons' existing direct reader, with optional sealed HTTP delivery.

    Direct retrieval already discovers the existing box snapshot. This module
    adds no custody, peer grant, holder process, credential refresh, or install.
    Values are reread from the selected facility for each caller request.
    """
    if source == 'local':
        underlying = retrieve_local
    elif source == 'http':
        opener = urllib.request.build_opener(_NoRedirect)
        underlying = lambda ref: retrieve_http(ref, base_url=gateway_url, opener=opener.open)
    else:
        raise HeadlessError('credential_source_invalid')

    def read(reference: str):
        try:
            return underlying(reference)
        except Exception:
            raise HeadlessError('credential_retrieval_failed') from None
    return read


def claude_child_env(*, reader: Reader | None = None,
                     base_env: Mapping[str, str] | None = None,
                     config_dir: str | os.PathLike | None = None) -> dict[str, str]:
    """Return a child-only OAuth environment; never modifies os.environ.

    Use subprocess.run(['claude', 'auth', 'status', '--json'], env=returned_env)
    for a non-inference check. Authorized model tasks can use claude -p with the
    same environment. Do not print this mapping or use --bare for account OAuth.
    """
    token = (reader or credential_reader())('vault/claude/account/access')
    if not isinstance(token, str) or not token:
        raise HeadlessError('claude_access_token_invalid')
    env = dict(os.environ if base_env is None else base_env)
    for name in ('ANTHROPIC_API_KEY', 'ANTHROPIC_AUTH_TOKEN', 'CLAUDE_CODE_OAUTH_TOKEN_FILE'):
        env.pop(name, None)
    env['CLAUDE_CODE_OAUTH_TOKEN'] = token
    if config_dir is not None:
        env['CLAUDE_CONFIG_DIR'] = os.fspath(config_dir)
    return env


class GrokBotGateway:
    """Owner's existing app coordinator, using the actual saved vault connection.

    Every method returns (HTTP status, parsed JSON). Treat the parsed response
    as private input. This adapter logs neither requests nor response payloads.
    """

    def __init__(self, *, reader: Reader | None = None):
        try:
            value = (reader or credential_reader())(CONNECTION_REF)
            connection = json.loads(value) if isinstance(value, str) else value
            url = connection['baseUrl'].rstrip('/')
            parsed = urllib.parse.urlsplit(url)
            if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
                raise ValueError()
            headers = dict(connection.get('headers', {}))
            if not all(isinstance(k, str) and isinstance(v, str) for k, v in headers.items()):
                raise ValueError()
            token = connection.get('token')
            if token:
                if not isinstance(token, str):
                    raise ValueError()
                headers = {k: v for k, v in headers.items() if k.lower() != 'authorization'}
                headers['Authorization'] = 'Bearer ' + token
            headers['Content-Type'] = 'application/json'
            headers['User-Agent'] = 'Grok Bot/0.43.0'
        except HeadlessError:
            raise
        except Exception:
            raise HeadlessError('gateway_connection_invalid') from None
        self._base_url = url
        self._headers = headers
        self._opener = urllib.request.build_opener(_NoRedirect)

    def _request(self, path: str, arguments: dict | None, *, timeout: float):
        try:
            data = None if arguments is None else json.dumps(arguments, separators=(',', ':')).encode('utf-8')
            request = urllib.request.Request(self._base_url + path, data=data,
                                             headers=self._headers,
                                             method='GET' if data is None else 'POST')
            with self._opener.open(request, timeout=timeout) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as error:
            raise HeadlessError('gateway_http_error', http_status=error.code) from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise HeadlessError('gateway_transport_unavailable') from None
        except Exception:
            raise HeadlessError('gateway_response_invalid') from None

    def health(self, *, timeout: float = 25):
        return self._request('/health', None, timeout=timeout)

    def list_agents(self, *, timeout: float = 45):
        return self._request('/api/listAgents', {}, timeout=timeout)

    def send_prompt(self, agent_id: str, prompt: str, *, client_nonce: str, timeout: float = 45):
        """Send an explicitly supplied task. Reuse its nonce after an uncertain response.

        No automatic retries or new-agent creation. An accepted response is not
        proof that the agent completed the task; inspect its transcript/result.
        """
        if not all(isinstance(v, str) and v.strip() for v in (agent_id, prompt, client_nonce)):
            raise HeadlessError('prompt_arguments_invalid')
        return self._request('/api/sendPrompt', {'agentId': agent_id, 'prompt': prompt,
                             'clientNonce': client_nonce}, timeout=timeout)

    def transcript_tail(self, agent_id: str, *, limit: int = 30, before_seq: int | None = None,
                        session_id: str | None = None, timeout: float = 45):
        arguments = {'id': agent_id, 'limit': limit}
        if before_seq is not None:
            arguments['beforeSeq'] = before_seq
        if session_id is not None:
            arguments['sessionId'] = session_id
        return self._request('/api/getAgentTranscriptTail', arguments, timeout=timeout)

    def read_attachment_text(self, path: str, *, agent_id: str | None = None, timeout: float = 45):
        arguments = {'path': path}
        if agent_id is not None:
            arguments['agentId'] = agent_id
        return self._request('/api/readAttachmentText', arguments, timeout=timeout)

    def read_attachment_chunk(self, path: str, *, offset: int = 0, length: int = 1024 * 1024,
                              agent_id: str | None = None, video_playback: bool | None = None,
                              timeout: float = 45):
        """Read a normal attachment; length=0 returns provider size metadata.

        Returned bytesBase64 is file data. Decode it only in the intended media
        or artifact operation. This method creates no local file.
        """
        if type(offset) is not int or type(length) is not int or offset < 0 or length < 0:
            raise HeadlessError('attachment_range_invalid')
        arguments = {'path': path, 'offset': offset, 'length': length}
        if agent_id is not None:
            arguments['agentId'] = agent_id
        if video_playback is not None:
            arguments['videoPlayback'] = video_playback
        return self._request('/api/readAttachmentChunk', arguments, timeout=timeout)

    def upload_attachment_chunk(self, chunk: bytes, *, upload_id: str, filename: str,
                                offset: int, total_size: int, agent_id: str | None = None,
                                timeout: float = 45):
        """Upload explicitly supplied file bytes through the existing attachment RPC.

        Keep upload_id stable for one file and supply its actual byte offsets and
        total size. The provider's final response contains committedPath. Return
        that response to the caller in memory; never print it or retry implicitly.
        """
        if not isinstance(chunk, bytes):
            raise HeadlessError('upload_bytes_required')
        if not all(isinstance(value, str) and value.strip() for value in (upload_id, filename)):
            raise HeadlessError('upload_arguments_invalid')
        if (type(offset) is not int or type(total_size) is not int
                or offset < 0 or total_size < 0 or offset + len(chunk) > total_size):
            raise HeadlessError('upload_range_invalid')
        arguments = {'uploadId': upload_id, 'filename': filename, 'offset': offset,
                     'totalSize': total_size, 'bytesBase64': base64.b64encode(chunk).decode('ascii')}
        if agent_id is not None:
            arguments['agentId'] = agent_id
        return self._request('/api/uploadAttachmentChunk', arguments, timeout=timeout)


def check_metadata(gateway: GrokBotGateway) -> dict:
    health_status, health = gateway.health()
    agents_status, result = gateway.list_agents()
    agents = result if isinstance(result, list) else result.get('agents') if isinstance(result, dict) else None
    if not isinstance(agents, list):
        raise HeadlessError('agent_list_shape_invalid')
    return {'ok': health_status == 200 and agents_status == 200,
            'health_http_status': health_status, 'health_json_received': isinstance(health, dict),
            'list_agents_http_status': agents_status, 'agent_count': len(agents),
            'prompts_sent': False, 'credential_values_printed': False}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Read-only Grok Bot health and agent-count check.')
    parser.add_argument('--source', choices=('local', 'http'), default='local')
    args = parser.parse_args(argv)
    try:
        read = credential_reader(source=args.source)
        result = check_metadata(GrokBotGateway(reader=read))
        print(json.dumps(result, sort_keys=True))
        return 0 if result['ok'] else 1
    except HeadlessError as error:
        print(json.dumps({'ok': False, 'error': error.code, 'http_status': error.http_status,
                          'credential_values_printed': False}, sort_keys=True))
        return 1
    except Exception:
        print(json.dumps({'ok': False, 'error': 'headless_check_failed', 'credential_values_printed': False}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
