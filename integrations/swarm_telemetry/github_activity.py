"""Read-only, lossless GitHub account/activity/content backfill.

Every invocation spends a finite *request* budget against a persistent queue. It
does not select a corpus sample. Exact responses belong in ``full_source`` and
must pass through the telemetry store's encrypted custody before projection.
The returned state contains retrieval selectors and counts, never response bodies
or credentials. Unsupported/denied/template selectors remain accounted for.
"""
from __future__ import annotations

import base64
import copy
import hashlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from .discovery import GITHUB_SCOPES, _existing_credential, _native_gh_accounts, _run


def _now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _hash(*parts):
    return hashlib.sha256(json.dumps(parts, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def _api(host):
    return "https://api.github.com/" if host == "github.com" else "https://" + host + "/api/v3/"


def _graphql_api(host):
    return "https://api.github.com/graphql" if host == "github.com" else "https://" + host + "/api/graphql"


def _clean_url(url):
    # Query strings on signed artifact/log redirects contain credentials. The
    # exact URL remains inside encrypted custody; public metadata omits it.
    parts = urllib.parse.urlsplit(str(url))
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def _items(payload):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("items", "workflow_runs", "workflows", "jobs", "artifacts", "check_runs", "check_suites", "environments", "installations", "variables", "secrets", "repositories"):
            if isinstance(payload.get(key), list):
                return payload[key]
    return []


def _page_items(payload, kind):
    # Commit pages repeat the commit metadata; only the files array advances.
    # Keep _items unchanged so graph expansion still reads the commit itself.
    if kind == "commit_detail" and isinstance(payload, dict) and isinstance(payload.get("files"), list):
        return payload["files"]
    return _items(payload)


class _Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urllib.parse.urlsplit(newurl).scheme != "https":
            raise urllib.error.HTTPError(req.full_url, 502, "non_https_redirect", headers, fp)
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected and urllib.parse.urlsplit(req.full_url).netloc != urllib.parse.urlsplit(newurl).netloc:
            for name in ("Authorization", "Cookie", "Proxy-authorization"):
                redirected.remove_header(name)
        return redirected


def _response_bytes(value):
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        return value.encode("utf-8", "surrogatepass")
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8", "surrogatepass")


def _native_payload(value):
    """Decode installed connector envelopes without discarding their source."""
    for _ in range(12):
        if not isinstance(value, Mapping):
            return value, None
        if value.get("isError") or value.get("ok") is False or value.get("error"):
            return value, "native_reader_error"
        if isinstance(value.get("structuredContent"), (dict, list)):
            value = value["structuredContent"]
        elif isinstance(value.get("result"), (dict, list)):
            value = value["result"]
        elif isinstance(value.get("content"), str) and any(key in value for key in ("display_url", "display_title", "modified_date")):
            return value["content"], None
        elif isinstance(value.get("content"), list):
            texts = [block.get("text") for block in value["content"]
                     if isinstance(block, Mapping) and block.get("type") == "text" and isinstance(block.get("text"), str)]
            decoded = []
            for text in texts:
                try:
                    decoded.append(json.loads(text))
                except ValueError:
                    pass
            if len(decoded) == 1:
                value = decoded[0]
            elif len(texts) == 1 and not decoded:
                return texts[0], None
            else:
                return value, "native_response_unrecognized"
        else:
            return value, None
    return value, "native_response_unrecognized"


def _request(road, task, config, tokens):
    """A configured raw reader may return {body, headers, status, url}.

    Installed connector results retain their complete native envelope while
    their provider body is decoded for traversal. A legacy JSON reader remains
    usable, with reconstructed-JSON custody and page-length pagination when no
    native headers were supplied.
    """
    reader = road.get("reader")
    endpoint = task["next_endpoint"]
    query = task.get("query")
    native_envelope, reader_error = None, None
    if callable(reader):
        if query:
            graphql = road.get("graphql_reader")
            if not callable(graphql):
                raise RuntimeError("graphql_reader_binding_pending")
            value = graphql(query, task.get("variables") or {})
        else:
            value = reader(endpoint)
        if isinstance(value, Mapping) and ("isError" in value or "structuredContent" in value or
                                          isinstance(value.get("content"), list)):
            native_envelope = copy.deepcopy(value)
            value, reader_error = _native_payload(value)
        if isinstance(value, Mapping) and "body" in value and ("headers" in value or "status" in value):
            raw = _response_bytes(value["body"])
            headers = {str(k).lower(): str(v) for k, v in (value.get("headers") or {}).items()}
            status = int(value.get("status") or 200)
            url = str(value.get("url") or _api(road["host"]) + endpoint)
            exact = isinstance(value["body"], (str, bytes))
        else:
            raw, headers, status = _response_bytes(value), {}, 200
            url, exact = _api(road["host"]) + endpoint, False
    else:
        host, login, ref = road["host"], road.get("login"), road["account_ref"]
        if ref not in tokens:
            credential = None
            if not road.get("force_native_keyring"):
                try:
                    credential = _existing_credential(config, road.get("credential_ref") or ("github/" + str(login)))
                except Exception:
                    pass
            if not isinstance(credential, str) or not credential:
                if not login:
                    raise RuntimeError("account_login_unresolved")
                credential = _run([config.get("gh") or "gh", "auth", "token", "--hostname", host, "--user", login], max(45, float(config.get("http_timeout_seconds", 30)))).strip()
            if not credential:
                raise RuntimeError("credential_retrieval_pending")
            tokens[ref] = credential
        url = _graphql_api(host) if query else urllib.parse.urljoin(_api(host), endpoint)
        origin = urllib.parse.urlsplit(_api(host))
        target = urllib.parse.urlsplit(url)
        raw_download = task.get("external_download")
        if target.scheme != "https" or (target.netloc != origin.netloc and not raw_download):
            raise RuntimeError("source_origin_rejected")
        if raw_download and target.netloc not in {"gist.githubusercontent.com", "raw.githubusercontent.com", "github.com", host}:
            raise RuntimeError("download_origin_rejected")
        headers_out = {"Accept": task.get("accept") or "application/vnd.github+json", "User-Agent": "Commons-Swarm-Telemetry", "X-GitHub-Api-Version": "2022-11-28"}
        if target.netloc == origin.netloc:
            headers_out["Authorization"] = "Bearer " + tokens[ref]
        data = None
        method = "GET"
        if query:
            # GraphQL read queries are the only POST operation in this reader.
            if not re.match(r"^\s*query(?:\s|\(|\{)", query) or re.search(r"\bmutation\b", query):
                raise RuntimeError("non_read_graphql_rejected")
            data = json.dumps({"query": query, "variables": task.get("variables") or {}}).encode()
            method = "POST"
            headers_out["Content-Type"] = "application/json"
        req = urllib.request.Request(url, headers=headers_out, data=data, method=method)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _Redirect())
        try:
            response = opener.open(req, timeout=float(config.get("http_timeout_seconds", 30)))
        except urllib.error.HTTPError as error:
            response = error
        with response:
            raw = response.read()  # No byte cutoff: each response is preserved in full.
            status = int(response.code)
            headers = {str(k).lower(): str(v) for k, v in response.headers.items()}
            url = response.geturl()
        exact = True
    payload = None
    try:
        payload = json.loads(raw.decode("utf-8-sig"))
    except (ValueError, UnicodeError):
        pass
    if native_envelope is not None:
        # Native tools expose source text, not the original HTTP wire. A text
        # result only completes selectors that actually request text content.
        exact = False
        if not reader_error and payload is None and task["kind"] not in {"actions_logs", "pull_diff", "gist_file"}:
            reader_error = "native_response_unrecognized"
    return {"raw": raw, "payload": payload, "headers": headers, "status": status, "url": url, "exact": exact,
            "native_envelope": native_envelope, "reader_error": reader_error}


def _retry_epoch(headers, attempts=1):
    now = time.time()
    retry = headers.get("retry-after")
    if retry:
        try:
            return now + max(1, float(retry))
        except ValueError:
            try:
                return max(now + 1, parsedate_to_datetime(retry).timestamp())
            except (ValueError, TypeError):
                pass
    try:
        if int(headers.get("x-ratelimit-remaining", "1")) == 0:
            return max(now + 1, float(headers["x-ratelimit-reset"]) + 1)
    except (KeyError, ValueError):
        pass
    return now + min(86400, 60 * 2 ** min(attempts, 10))


REPO_ROADS = {
    "repository": "", "issues": "/issues?state=all&per_page=100", "issue_comments": "/issues/comments?per_page=100",
    "issue_events": "/issues/events?per_page=100", "pull_requests": "/pulls?state=all&per_page=100", "review_comments": "/pulls/comments?per_page=100",
    "commits": "/commits?per_page=100", "commit_comments": "/comments?per_page=100", "refs": "/git/matching-refs/?per_page=100",
    "branches": "/branches?per_page=100", "tags": "/tags?per_page=100", "actions_runs": "/actions/runs?per_page=100",
    "workflows": "/actions/workflows?per_page=100", "actions_artifacts": "/actions/artifacts?per_page=100",
    "releases": "/releases?per_page=100", "deployments": "/deployments?per_page=100", "events": "/events?per_page=100",
    "environments": "/environments?per_page=100", "rulesets": "/rulesets?per_page=100", "hooks": "/hooks?per_page=100",
    "security_alerts": "/dependabot/alerts?state=all&per_page=100", "code_scanning": "/code-scanning/alerts?per_page=100",
    "secret_scanning": "/secret-scanning/alerts?per_page=100", "subscribers": "/subscribers?per_page=100",
    "collaborators": "/collaborators?per_page=100", "languages": "/languages", "contributors": "/contributors?anon=true&per_page=100",
    "milestones": "/milestones?state=all&per_page=100", "labels": "/labels?per_page=100", "traffic_views": "/traffic/views",
    "traffic_clones": "/traffic/clones", "invitations": "/invitations?per_page=100", "actions_secrets_metadata": "/actions/secrets?per_page=100",
    "actions_variables": "/actions/variables?per_page=100", "stargazers": "/stargazers?per_page=100", "forks": "/forks?per_page=100",
}

_CLOUD_BINARY_KINDS = {"artifact_archive", "release_asset_binary", "actions_run_logs", "actions_attempt_logs", "git_lfs_object"}
_CODE_KINDS = {"blob", "tree", "contents", "commit_detail", "git_commit", "pull_diff", "pull_files", "git_tag", "submodule_commit", "gist_file"}
_FORBIDDEN_COMPONENT = re.compile(r"(?i)(?:^|[/\\_. -])(?:llama[.-]cpp(?:[.-]python)?|llama_cpp|node-llama-cpp|llama-(?:cli|server|bench|quantize))(?:$|[/\\_. -])")
_BINARY_PATH = re.compile(r"(?i)\.(?:zip|tar|tgz|tbz2|gz|bz2|xz|7z|rar|whl|egg|nupkg|exe|dll|pyd|so(?:\.\d+)*|dylib|lib|a|o|obj|bin|gguf|ggml|pt|pth|onnx|safetensors)$")


def _placement(task):
    """Decide before requesting bytes; no forbidden implementation is fetched.

    Source-placement requirements do not hide the source. Its original selector
    stays pending until the existing off-machine custody facility returns a
    receipt. Binary archives likewise never download into this local reader.
    """
    if task["kind"] in _CLOUD_BINARY_KINDS or task.get("accept") == "application/octet-stream":
        return "binary_cloud_custody"
    names = [task.get("repository") or "", task.get("endpoint") or ""] + list(task.get("source_paths") or [])
    if task["kind"] in {"blob", "contents", "gist_file"} and any(_BINARY_PATH.search(name) for name in names):
        return "binary_cloud_custody"
    if task["kind"] in _CODE_KINDS and any(_FORBIDDEN_COMPONENT.search(name) for name in names):
        return "machine_policy_cloud_custody"
    return None


def collect_github_activity(config=None, state=None, sources=None):
    """Return events, exhaustive selector coverage, resumable state and sources.

    Configuration can supply account-specific readers, account rows, repository
    names, discovery descriptors, and github_references/source_events from Slack
    or machine collectors. GET responses are losslessly captured. Ref expansions
    keep all reachable code/history, discussions, job logs and binary downloads.
    """
    config = dict(config or {})
    result_state = copy.deepcopy(dict(state or {}))
    queue = result_state.setdefault("queue", {})
    order = result_state.setdefault("order", list(queue))
    templates = result_state.setdefault("templates", {})
    source_aliases = result_state.setdefault("source_aliases", {})
    cooldowns = result_state.setdefault("cooldowns", {})
    accounts = result_state.setdefault("accounts", {})
    events, tokens = [], {}
    input_sources = list(sources or config.get("github_sources") or [])
    if isinstance(sources, Mapping):
        input_sources = list(sources.get("sources") or [])
    roads = {}
    native_rows = []
    try:
        native_rows, _ = _native_gh_accounts()
        if not native_rows:
            native_status = json.loads(_run([config.get("gh") or "gh", "auth", "status", "--json", "hosts"], 45))
            for host, entries in native_status.get("hosts", {}).items():
                for row in entries:
                    if row.get("login"):
                        native_rows.append({"host": host, "login": row["login"], "account_ref": "github:" + host + ":" + row["login"], "native_keyring": True})
        result_state["account_discovery"] = {"status": "observed", "accounts": len(native_rows), "observed_at": _now()}
    except Exception as error:
        result_state["account_discovery"] = {"status": "pending_recovery", "error_type": type(error).__name__, "observed_at": _now()}
    for row in native_rows + list(config.get("github_accounts") or []) + list(config.get("github_readers") or []):
        row = dict(row)
        host = str(row.get("host") or "github.com")
        login = row.get("login")
        ref = row.get("account_ref") or "github:" + host + ":" + str(login or "unresolved")
        match = re.fullmatch(r"github:([^:]+):(.+)", str(ref))
        if match:
            host, login = match.groups()
        roads[ref] = {**roads.get(ref, {}), **row, "account_ref": ref, "host": host, "login": login}
        prior_account = accounts.get(ref, {})
        if prior_account.get("preferred_credential_facility") == "native_keyring":
            roads[ref]["force_native_keyring"] = True
        accounts[ref] = {**prior_account, "account_ref": ref, "host": host, "login": login}
    for descriptor in input_sources:
        if descriptor.get("service", descriptor.get("source")) != "github":
            continue
        ref = descriptor.get("account_ref")
        if not ref:
            continue
        match = re.fullmatch(r"github:([^:]+):(.+)", str(ref))
        host = (descriptor.get("reader") or {}).get("host") or (match.group(1) if match else "github.com")
        if ref not in roads:
            roads[ref] = {"account_ref": ref, "host": host, "login": match.group(2) if match else None}
            accounts[ref] = {k: roads[ref][k] for k in ("account_ref", "host", "login")}

    def add(ref, endpoint, kind, repo=None, *, accept=None, immutable=False, query=None, variables=None, external_download=False, source_id=None, source_path=None):
        if not endpoint or not ref:
            return None
        if "{" in endpoint and not query or endpoint.startswith("graphql:"):
            sid = source_id or "github-template:" + _hash(ref, endpoint)[:32]
            templates.setdefault(sid, {"source_id": sid, "account_ref": ref, "repository": repo, "endpoint": endpoint, "kind": kind, "complete": False, "status": "pending_reference_discovery", "expanded_selectors": []})
            return sid
        sid = "github-source:" + _hash(ref, endpoint, accept, query, variables)[:32]
        if source_id and source_id != sid:
            source_aliases[source_id] = sid
        if sid not in queue:
            queue[sid] = {"source_id": sid, "account_ref": ref, "repository": repo, "endpoint": endpoint, "next_endpoint": endpoint,
                          "kind": kind, "accept": accept, "immutable": immutable, "query": query, "variables": variables,
                          "external_download": external_download, "complete": False, "status": "pending", "pages": 0, "records": 0, "byte_length": 0, "attempts": 0, "page": 1}
            order.append(sid)
        if source_path and source_path not in queue[sid].setdefault("source_paths", []):
            queue[sid]["source_paths"].append(source_path)
        return sid

    def repo_add(ref, repo):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", str(repo)):
            return
        base = "repos/" + repo
        for kind, suffix in REPO_ROADS.items():
            add(ref, base + suffix, kind, repo)
        discussion_query = "query($owner:String!,$name:String!,$cursor:String){repository(owner:$owner,name:$name){discussions(first:100,after:$cursor){nodes{id number title body createdAt updatedAt url author{login} answer{id} category{id name} labels(first:100){nodes{id name} pageInfo{hasNextPage endCursor}}} pageInfo{hasNextPage endCursor}}}}"
        owner, name = repo.split("/", 1)
        add(ref, "graphql", "discussions", repo, query=discussion_query, variables={"owner": owner, "name": name, "cursor": None})

    def commit_add(ref, repo, sha):
        if not re.fullmatch(r"[A-Fa-f0-9]{40,64}", str(sha)):
            return
        base = "repos/" + repo
        add(ref, base + "/commits/" + sha + "?per_page=100", "commit_detail", repo, immutable=True)
        add(ref, base + "/git/commits/" + sha, "git_commit", repo, immutable=True)
        add(ref, base + "/commits/" + sha + "/comments?per_page=100", "commit_comments", repo)
        add(ref, base + "/commits/" + sha + "/check-runs?per_page=100", "checks", repo)
        add(ref, base + "/commits/" + sha + "/check-suites?per_page=100", "check_suites", repo)
        add(ref, base + "/commits/" + sha + "/statuses?per_page=100", "statuses", repo)
        add(ref, base + "/commits/" + sha + "/pulls?per_page=100", "pull_requests", repo)

    def issue_add(ref, repo, number, pull=False):
        if not str(number).isdigit():
            return
        base = "repos/" + repo
        issue = base + "/issues/" + str(number)
        add(ref, issue, "issue_detail", repo)
        add(ref, issue + "/comments?per_page=100", "issue_comments", repo)
        add(ref, issue + "/timeline?per_page=100", "issue_timeline", repo)
        add(ref, issue + "/events?per_page=100", "issue_events", repo)
        add(ref, issue + "/reactions?per_page=100", "reactions", repo)
        if pull:
            pr = base + "/pulls/" + str(number)
            add(ref, pr, "pull_detail", repo)
            for kind, suffix in (("pull_commits", "commits"), ("pull_files", "files"), ("reviews", "reviews"), ("review_comments", "comments")):
                add(ref, pr + "/" + suffix + "?per_page=100", kind, repo)
            for accept in ("application/vnd.github.diff", "application/vnd.github.patch"):
                add(ref, pr, "pull_diff", repo, accept=accept)

    def referenced(value, ref, depth=0):
        if depth > 100:
            return
        if isinstance(value, str):
            host = roads.get(ref, {}).get("host", "github.com")
            pattern = r"https://(?:api\.)?" + re.escape(host) + r"/(?:repos/)?([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)(?:/(issues|pull|pulls|commit|commits|actions/runs)/([A-Za-z0-9]+))?"
            for match in re.finditer(pattern, value):
                repo = match.group(1).removesuffix(".git")
                if repo.split("/", 1)[0] in {"settings", "users", "orgs", "search", "features", "marketplace", "login", "notifications"}:
                    continue
                repo_add(ref, repo)
                kind, native = match.group(2), match.group(3)
                if kind in {"issues", "pull", "pulls"}:
                    issue_add(ref, repo, native, kind in {"pull", "pulls"})
                elif kind in {"commit", "commits"}:
                    commit_add(ref, repo, native)
                elif kind == "actions/runs" and native and native.isdigit():
                    add(ref, "repos/" + repo + "/actions/runs/" + native, "run_detail", repo)
            for match in re.finditer(r"(?:git@|ssh://git@)" + re.escape(host) + r"[:/]([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)", value):
                repo_add(ref, match.group(1).removesuffix(".git"))
            if host == "github.com":
                for match in re.finditer(r"https://gist\.github\.com/(?:[A-Za-z0-9_-]+/)?([a-fA-F0-9]{5,40})(?:[/?#\s]|$)", value):
                    add(ref, "gists/" + match.group(1), "gist_detail")
        elif isinstance(value, Mapping):
            # Incoming Slack/machine source envelopes can carry exact UTF-8
            # bytes in base64. Extract references in memory before custody;
            # never write the decoded source or credential-bearing log text.
            encoded = value.get("body") if isinstance(value.get("body"), str) else value.get("data")
            if value.get("encoding") == "base64" and isinstance(encoded, str):
                try:
                    decoded = base64.b64decode(encoded, validate=True).decode("utf-8")
                    referenced(decoded, ref, depth + 1)
                except (ValueError, UnicodeError):
                    pass
            for item in value.values():
                referenced(item, ref, depth + 1)
        elif isinstance(value, (tuple, list)):
            for item in value:
                referenced(item, ref, depth + 1)

    for ref, road in roads.items():
        login = road.get("login")
        for kind, endpoint in (("identity", "user"), ("repos", "user/repos?affiliation=owner,collaborator,organization_member&visibility=all&per_page=100"),
                               ("orgs", "user/orgs?per_page=100"), ("notifications", "notifications?all=true&per_page=100"),
                               ("gists", "gists?per_page=100"), ("starred", "user/starred?per_page=100"), ("subscriptions", "user/subscriptions?per_page=100"),
                               ("teams", "user/teams?per_page=100"), ("repo_invitations", "user/repository_invitations?per_page=100"),
                               ("installations", "user/installations?per_page=100"), ("ssh_keys", "user/keys?per_page=100"), ("gpg_keys", "user/gpg_keys?per_page=100"),
                               ("ssh_signing_keys", "user/ssh_signing_keys?per_page=100"), ("emails", "user/emails?per_page=100")):
            add(ref, endpoint, kind)
        if login:
            for kind, suffix in (("user_events", "/events?per_page=100"), ("received_events", "/received_events?per_page=100"),
                                 ("followers", "/followers?per_page=100"), ("following", "/following?per_page=100")):
                add(ref, "users/" + urllib.parse.quote(str(login), safe="") + suffix, kind)
            # Search is subdivided if the API's 1,000-result ceiling is reached.
            for kind, term in (("search_issues", "involves:"), ("search_issues", "reviewed-by:"), ("search_issues", "review-involves:"), ("search_commits", "author:"), ("search_commits", "committer:")):
                query = term + login
                sort = "committer-date" if kind == "search_commits" else "created"
                add(ref, "search/" + ("commits" if kind == "search_commits" else "issues") + "?q=" + urllib.parse.quote(query) + "&per_page=100&sort=" + sort + "&order=asc", kind)
        for repo in config.get("github_repositories") or []:
            repo_add(ref, repo)
        for candidate in (config.get("github_references"), config.get("source_events"), config.get("external_github_references")):
            referenced(candidate, ref)
    for descriptor in input_sources:
        if descriptor.get("service", descriptor.get("source")) != "github":
            continue
        reader = descriptor.get("reader") or {}
        endpoint = reader.get("endpoint") or descriptor.get("endpoint") or descriptor.get("locator") or descriptor.get("source_locator")
        ref, repo = descriptor.get("account_ref"), descriptor.get("repository")
        if repo:
            repo_add(ref, repo)
        if endpoint:
            kind = str(descriptor.get("kind") or descriptor.get("scope") or "discovered_source").split(":", 1)[0]
            if endpoint.startswith("graphql:"):
                kind = "discussions"
            add(ref, endpoint, kind, repo, source_id=descriptor.get("source_id"))
        if reader.get("audit_log_endpoint"):
            add(ref, reader["audit_log_endpoint"], "audit_logs")

    def expand(task, payload):
        ref, repo, kind = task["account_ref"], task.get("repository"), task["kind"]
        base = "repos/" + repo if repo else None
        rows = _items(payload)
        if isinstance(payload, dict) and not rows:
            rows = [payload]
        if kind in {"repos", "starred", "subscriptions", "forks"}:
            for row in rows:
                if isinstance(row, dict) and row.get("full_name"):
                    repo_add(ref, row["full_name"])
        if kind == "identity" and isinstance(payload, dict):
            accounts[ref]["provider_login"] = payload.get("login")
            accounts[ref]["provider_account_id"] = payload.get("id")
        if kind == "orgs":
            for row in rows:
                org = row.get("login")
                if org:
                    for subkind, suffix in (("repos", "/repos?type=all&per_page=100"), ("audit_logs", "/audit-log?include=all&per_page=100"),
                                             ("org_events", "/events?per_page=100"), ("org_hooks", "/hooks?per_page=100"), ("teams", "/teams?per_page=100")):
                        add(ref, "orgs/" + str(org) + suffix, subkind)
        if kind in {"events", "user_events", "received_events", "org_events"}:
            for row in rows:
                repository = row.get("repo") or row.get("repository") or {}
                event_repo = repository.get("name") or repository.get("full_name")
                detail = row.get("payload") or {}
                if event_repo and "/" in event_repo:
                    repo_add(ref, event_repo)
                    for member in ("head", "before", "after"):
                        commit_add(ref, event_repo, detail.get(member))
                    for commit in detail.get("commits") or []:
                        commit_add(ref, event_repo, commit.get("sha"))
                    for member in ("issue", "pull_request"):
                        issue = detail.get(member) or {}
                        if issue.get("number"):
                            issue_add(ref, event_repo, issue["number"], member == "pull_request" or bool(issue.get("pull_request")))
        if kind == "notifications":
            for row in rows:
                subject = row.get("subject") or {}
                for field in ("url", "latest_comment_url"):
                    value = subject.get(field)
                    if value and urllib.parse.urlsplit(value).netloc == urllib.parse.urlsplit(_api(roads[ref]["host"])).netloc:
                        endpoint = value.removeprefix(_api(roads[ref]["host"]))
                        source_repo = (row.get("repository") or {}).get("full_name")
                        add(ref, endpoint, "notification_subject", source_repo)
        if kind in {"issues", "search_issues", "issue_detail", "pull_requests", "pull_detail", "notification_subject"}:
            for row in rows:
                if not isinstance(row, dict):
                    continue
                source_repo = repo or (row.get("repository") or {}).get("full_name")
                if not source_repo:
                    match = re.search(r"/repos/([^/]+/[^/]+)/", str(row.get("repository_url") or row.get("url") or "") + "/")
                    source_repo = match.group(1) if match else None
                if source_repo and row.get("number"):
                    issue_add(ref, source_repo, row["number"], bool(row.get("pull_request")) or kind in {"pull_requests", "pull_detail"})
                if source_repo and row.get("head"):
                    for member in ("head", "base"):
                        detail = row.get(member) or {}
                        target_repo = (detail.get("repo") or {}).get("full_name") or source_repo
                        repo_add(ref, target_repo)
                        commit_add(ref, target_repo, detail.get("sha"))
                    commit_add(ref, source_repo, row.get("merge_commit_sha"))
        if repo and kind in {"commits", "commit_detail", "git_commit", "pull_commits", "search_commits", "branches", "tags"}:
            for row in rows:
                commit_add(ref, repo, row.get("sha") or (row.get("commit") or {}).get("sha"))
                for parent in row.get("parents") or []:
                    commit_add(ref, repo, parent.get("sha"))
                tree = row.get("tree") or (row.get("commit") or {}).get("tree") or {}
                if tree.get("sha"):
                    add(ref, base + "/git/trees/" + tree["sha"], "tree", repo, immutable=True)
                if kind == "branches" and row.get("name"):
                    branch = urllib.parse.quote(row["name"], safe="")
                    add(ref, base + "/commits?sha=" + branch + "&per_page=100", "commits", repo)
                    add(ref, base + "/branches/" + branch + "/protection", "branch_protection", repo)
        if kind == "search_commits" and not repo:
            for row in rows:
                target_repo = (row.get("repository") or {}).get("full_name")
                if target_repo:
                    repo_add(ref, target_repo)
                    commit_add(ref, target_repo, row.get("sha"))
        if repo and kind in {"refs", "git_tag"}:
            for row in rows:
                obj = row.get("object") or {}
                sha = obj.get("sha")
                if obj.get("type") == "commit":
                    commit_add(ref, repo, sha)
                elif obj.get("type") == "tag" and sha:
                    add(ref, base + "/git/tags/" + sha, "git_tag", repo, immutable=True)
                elif obj.get("type") == "tree" and sha:
                    add(ref, base + "/git/trees/" + sha, "tree", repo, immutable=True)
                elif obj.get("type") == "blob" and sha:
                    add(ref, base + "/git/blobs/" + sha, "blob", repo, immutable=True)
        if repo and kind == "tree":
            # Always walk individual trees. recursive=1 can truncate large trees.
            for row in payload.get("tree") or []:
                if row.get("type") in {"blob", "tree"} and row.get("sha"):
                    subtype = row["type"]
                    parent_paths = task.get("source_paths") or [""]
                    for parent_path in parent_paths:
                        child_path = (parent_path.rstrip("/") + "/" + str(row.get("path") or "")).lstrip("/")
                        add(ref, base + "/git/" + ("blobs/" if subtype == "blob" else "trees/") + row["sha"], subtype, repo, immutable=True, source_path=child_path)
                elif row.get("type") == "commit" and row.get("sha"):
                    # Submodules are recorded in the exact tree; discover their
                    # target URL from .gitmodules blob rather than guessing repo.
                    add(ref, "repos/{submodule_repo}/git/commits/" + row["sha"], "submodule_commit", repo)
        if repo and kind == "blob" and any(path.rsplit("/", 1)[-1] == ".gitmodules" for path in task.get("source_paths") or []):
            try:
                modules_text = base64.b64decode(payload.get("content") or "").decode("utf-8")
                referenced(modules_text, ref)
            except (ValueError, UnicodeError):
                pass
        if repo and kind == "blob" and payload.get("encoding") == "base64":
            # Git LFS returns a small pointer blob, not the referenced large
            # file. Keep its immutable oid/size and queue off-machine retrieval.
            try:
                pointer = base64.b64decode(payload.get("content") or "").decode("ascii")
            except (ValueError, UnicodeError):
                pointer = ""
            match = re.fullmatch(r"version https://git-lfs.github.com/spec/v1\r?\noid sha256:([a-f0-9]{64})\r?\nsize (\d+)\r?\n?", pointer)
            if match:
                lfs = add(ref, base + "/git/blobs/" + str(payload["sha"]) + "#lfs-" + match.group(1), "git_lfs_object", repo, immutable=True)
                queue[lfs].update(lfs_oid=match.group(1), lfs_size=int(match.group(2)), source_paths=list(task.get("source_paths") or []))
        if repo and kind in {"actions_runs", "run_detail"}:
            for row in rows:
                native = row.get("id")
                if native is None:
                    continue
                run = base + "/actions/runs/" + str(native)
                add(ref, run, "run_detail", repo)
                add(ref, run + "/jobs?filter=all&per_page=100", "actions_jobs", repo)
                add(ref, run + "/logs", "actions_run_logs", repo)
                add(ref, run + "/artifacts?per_page=100", "actions_artifacts", repo)
                for attempt in range(1, int(row.get("run_attempt") or 1) + 1):
                    add(ref, run + "/attempts/" + str(attempt), "run_attempt", repo)
                    add(ref, run + "/attempts/" + str(attempt) + "/jobs?per_page=100", "actions_jobs", repo)
                    add(ref, run + "/attempts/" + str(attempt) + "/logs", "actions_attempt_logs", repo)
                commit_add(ref, repo, row.get("head_sha"))
        if repo and kind == "actions_jobs":
            for row in rows:
                if row.get("id") is not None:
                    job = base + "/actions/jobs/" + str(row["id"])
                    add(ref, job, "job_detail", repo)
                    add(ref, job + "/logs", "actions_logs", repo)
        if repo and kind == "actions_artifacts":
            for row in rows:
                if row.get("id") is not None:
                    artifact = base + "/actions/artifacts/" + str(row["id"])
                    add(ref, artifact, "artifact_detail", repo)
                    download = add(ref, artifact + "/zip", "artifact_archive", repo, immutable=True)
                    if row.get("expired"):
                        queue[download]["provider_expired"] = True
        if repo and kind == "workflows":
            for row in rows:
                if row.get("id") is not None:
                    add(ref, base + "/actions/workflows/" + str(row["id"]), "workflow_detail", repo)
                    add(ref, base + "/actions/workflows/" + str(row["id"]) + "/runs?per_page=100", "actions_runs", repo)
                if row.get("path"):
                    add(ref, base + "/contents/" + urllib.parse.quote(row["path"], safe="/"), "contents", repo)
        if repo and kind in {"releases", "release_detail"}:
            for row in rows:
                if row.get("id") is not None:
                    release = base + "/releases/" + str(row["id"])
                    add(ref, release, "release_detail", repo)
                    add(ref, release + "/assets?per_page=100", "release_assets", repo)
                for asset in row.get("assets") or []:
                    if asset.get("id") is not None:
                        add(ref, base + "/releases/assets/" + str(asset["id"]), "release_asset_binary", repo, accept="application/octet-stream", immutable=True)
        if repo and kind == "release_assets":
            for row in rows:
                if row.get("id") is not None:
                    add(ref, base + "/releases/assets/" + str(row["id"]), "release_asset_binary", repo, accept="application/octet-stream", immutable=True)
        if repo and kind == "deployments":
            for row in rows:
                if row.get("id") is not None:
                    dep = base + "/deployments/" + str(row["id"])
                    add(ref, dep, "deployment_detail", repo)
                    add(ref, dep + "/statuses?per_page=100", "deployment_statuses", repo)
        if repo and kind in {"checks", "check_suites"}:
            for row in rows:
                if row.get("id") is not None:
                    if kind == "checks":
                        check = base + "/check-runs/" + str(row["id"])
                        add(ref, check, "check_detail", repo)
                        add(ref, check + "/annotations?per_page=100", "check_annotations", repo)
                    else:
                        suite = base + "/check-suites/" + str(row["id"])
                        add(ref, suite, "check_suite_detail", repo)
                        add(ref, suite + "/check-runs?per_page=100", "checks", repo)
        if repo and kind == "reviews":
            match = re.search(r"/pulls/(\d+)/reviews", task["endpoint"])
            if match:
                for row in rows:
                    if row.get("id") is not None:
                        review = base + "/pulls/" + match.group(1) + "/reviews/" + str(row["id"])
                        add(ref, review, "review_detail", repo)
                        add(ref, review + "/comments?per_page=100", "review_comments", repo)
        if repo and kind in {"issue_comments", "review_comments", "commit_comments"}:
            for row in rows:
                url = row.get("url")
                if url and str(url).startswith(_api(roads[ref]["host"])):
                    add(ref, url.removeprefix(_api(roads[ref]["host"])), "comment_detail", repo)
                    add(ref, url.removeprefix(_api(roads[ref]["host"])) + "/reactions?per_page=100", "reactions", repo)
        if kind in {"gists", "gist_detail"}:
            for row in rows:
                if row.get("id"):
                    add(ref, "gists/" + str(row["id"]), "gist_detail")
                    add(ref, "gists/" + str(row["id"]) + "/commits?per_page=100", "gist_commits")
                    add(ref, "gists/" + str(row["id"]) + "/comments?per_page=100", "gist_comments")
                for file in (row.get("files") or {}).values():
                    if file.get("raw_url"):
                        add(ref, file["raw_url"], "gist_file", immutable=True, external_download=True)
                for version in row.get("history") or []:
                    if version.get("version") and row.get("id"):
                        add(ref, "gists/" + str(row["id"]) + "/" + version["version"], "gist_detail", immutable=True)
        if kind == "gist_commits":
            match = re.match(r"gists/([^/]+)/", task["endpoint"])
            if match:
                for row in rows:
                    if row.get("version"):
                        add(ref, "gists/" + match.group(1) + "/" + row["version"], "gist_detail", immutable=True)
        if repo and kind in {"discussions", "discussion_comments", "discussion_replies"}:
            data = payload.get("data") or {}
            repository = data.get("repository") or {}
            if kind == "discussions":
                connection = repository.get("discussions") or {}
                for row in connection.get("nodes") or []:
                    number = row["number"]
                    query = "query($owner:String!,$name:String!,$number:Int!,$cursor:String){repository(owner:$owner,name:$name){discussion(number:$number){id number title body createdAt updatedAt url author{login} comments(first:100,after:$cursor){nodes{id body createdAt updatedAt url author{login} isAnswer} pageInfo{hasNextPage endCursor}}}}}"
                    vars = {"owner": repo.split("/")[0], "name": repo.split("/")[1], "number": number, "cursor": None}
                    add(ref, "graphql", "discussion_comments", repo, query=query, variables=vars)
                    label_query = "query($owner:String!,$name:String!,$number:Int!,$cursor:String){repository(owner:$owner,name:$name){discussion(number:$number){labels(first:100,after:$cursor){nodes{id name} pageInfo{hasNextPage endCursor}}}}}"
                    add(ref, "graphql", "discussion_labels", repo, query=label_query, variables=vars)
            elif kind == "discussion_comments":
                connection = (repository.get("discussion") or {}).get("comments") or {}
                for row in connection.get("nodes") or []:
                    query = "query($id:ID!,$cursor:String){node(id:$id){... on DiscussionComment{id replies(first:100,after:$cursor){nodes{id body createdAt updatedAt url author{login} isAnswer} pageInfo{hasNextPage endCursor}}}}}"
                    add(ref, "graphql", "discussion_replies", repo, query=query, variables={"id": row["id"], "cursor": None})
        # Source payloads can reference external contributions, run URLs or
        # linked owner work. Discover those roads from actual returned bytes.
        referenced(payload, ref)
        child_kinds = {}
        for child_id, child in queue.items():
            if child["account_ref"] == ref and child.get("repository") == repo:
                child_kinds.setdefault(child["kind"], []).append(child_id)
        for template in templates.values():
            if template["account_ref"] != ref or template.get("repository") != repo:
                continue
            replacements = {"reviews": {"reviews"}, "trees": {"tree"}, "blobs": {"blob"}, "contents": {"contents"},
                            "actions_jobs": {"actions_jobs"}, "actions_logs": {"actions_logs"}, "deployment_statuses": {"deployment_statuses"},
                            "checks": {"checks"}, "statuses": {"statuses"}, "discussions": {"discussions"}}
            scope = next((name for name in replacements if name in template["kind"] or name in template["endpoint"]), None)
            children = [child_id for child_kind in replacements.get(scope, set()) for child_id in child_kinds.get(child_kind, [])]
            if children:
                template["expanded_selectors"] = children
                template["status"] = "expanded_backfilling"

    budget = max(0, int(config.get("github_page_budget", config.get("page_budget", 10))))
    cursor = int(result_state.get("cursor", 0))
    requests = 0
    scanned = 0
    refresh = float(config.get("github_refresh_seconds", 300))
    while requests < budget and order and scanned < len(order):
        sid = order[cursor % len(order)]
        cursor = (cursor + 1) % len(order)
        scanned += 1
        task = queue[sid]
        ref = task["account_ref"]
        now = time.time()
        if task["kind"] == "commit_detail" and task.get("file_pagination_version") != 1:
            # Older checkpoints marked immutable commits complete after page
            # one when a JSON reader omitted Link headers. Reopen them once
            # through the normal request budget; retained envelopes stay intact.
            task.update(file_pagination_version=1, complete=False, next_endpoint=task["endpoint"], page=1)
            if task.get("pages"):
                task["status"] = "pending_file_pagination_recovery"
        if task.get("complete"):
            if task.get("immutable") or now - float(task.get("completed_epoch") or now) < refresh:
                continue
            task.update(complete=False, status="pending_refresh", next_endpoint=task["endpoint"], page=1)
            task.pop("cloud_read_cursor", None)
            if task.get("query"):
                task["variables"]["cursor"] = None
        if max(float(task.get("retry_epoch") or 0), float(cooldowns.get(ref, 0)), float(cooldowns.get(ref + ":" + str(task.get("repository")), 0))) > now:
            continue
        road = roads.get(ref)
        if not road:
            task["status"] = "reader_binding_pending"
            continue
        requests += 1
        task["attempts"] += 1
        try:
            placement = _placement(task)
            if placement:
                cloud_reader = config.get("github_cloud_reader")
                task.update(source_placement=placement, provider_original_ref=_api(road["host"]) + task["endpoint"])
                # The cloud reader owns this opaque continuation. Preserve its
                # last committed receipt across calls, retries and checkpoints.
                if task.get("cloud_read_cursor") is None:
                    task["cloud_read_cursor"] = {"endpoint": task["next_endpoint"], "page": task["page"]}
                if not callable(cloud_reader):
                    task.update(status="cloud_custody_pending", complete=False, retry_epoch=time.time() + refresh)
                    # No request was issued. Keep budget available for readable
                    # sources; pending cloud work is nevertheless in coverage.
                    requests -= 1
                    continue
                # The callback itself reads off-machine and must never return
                # source bytes to this host. It uses the shared credential road.
                receipt = cloud_reader({k: task.get(k) for k in ("source_id", "account_ref", "repository", "endpoint", "next_endpoint", "page", "accept", "kind", "source_paths", "source_placement", "cloud_read_cursor", "lfs_oid", "lfs_size")},
                                       {"account_ref": ref, "host": road["host"], "login": road.get("login"), "credential_ref": road.get("credential_ref"), "provider_original_ref": task["provider_original_ref"]})
                cloud_ref = receipt.get("source_record_ref") if isinstance(receipt, Mapping) else None
                if not isinstance(receipt, Mapping) or not isinstance(cloud_ref, Mapping) or not (cloud_ref.get("ref") or cloud_ref.get("url")) or any(key in receipt for key in ("body", "raw", "parsed_json", "data", "content")):
                    task.update(status="cloud_receipt_pending", complete=False, retry_epoch=time.time() + refresh)
                    continue
                # The receipt is a source response record, carrying the stable
                # immutable original reference and full bytes in cloud custody.
                safe_cloud_ref = {k: cloud_ref.get(k) for k in ("ref", "url", "sha256", "bytes")}
                safe_receipt = {k: receipt.get(k) for k in ("status", "complete", "next_cursor", "provider_request_id")}
                safe_receipt.update(source_record_ref=safe_cloud_ref, provider_original_ref=task["provider_original_ref"])
                captured = receipt.get("status") == "captured"
                cloud_complete = captured and bool(receipt.get("complete", True))
                digest = safe_cloud_ref.get("sha256") or _hash(safe_receipt)
                events.append({"event_id": _hash(ref, sid, digest), "source": "github", "source_id": sid + ":" + digest,
                               "observed_at": _now(), "event_type": "github_cloud_source_receipt", "provider": "github", "status": "observed" if captured else "cloud_pending",
                               "summary": "GitHub cloud source custody receipt", "url": _clean_url(task["provider_original_ref"]),
                               "metrics": {"body_byte_length": safe_cloud_ref.get("bytes") or 0},
                               "metadata": {"account_ref": ref, "repository": task.get("repository"), "kind": task["kind"], "source_placement": placement},
                               "source_ref": {"account_ref": ref, "selector_id": sid, "provider_original_ref": task["provider_original_ref"], "source_record_ref": safe_cloud_ref, "sha256": digest},
                               "full_source": safe_receipt})
                task.update(complete=cloud_complete, status="observed_cloud" if cloud_complete else "cloud_backfilling",
                            cloud_read_cursor=receipt.get("next_cursor") if captured else task["cloud_read_cursor"],
                            observed_at=_now(), last_sha256=digest, retry_epoch=0, completed_epoch=time.time() if cloud_complete else None)
                task["byte_length"] += int(safe_cloud_ref.get("bytes") or 0)
                continue
            response = _request(road, task, config, tokens)
            raw, payload, status, headers = response["raw"], response["payload"], response["status"], response["headers"]
            reader_error = response.get("reader_error")
            reported_status = None if reader_error else status
            digest = hashlib.sha256(raw).hexdigest()
            source_ref = {"account_ref": ref, "repository": task.get("repository"), "selector_id": sid, "endpoint": task["next_endpoint"],
                          "page": task["page"], "sha256": digest, "body_byte_length": len(raw), "http_status": reported_status,
                          "exact_http_bytes": response["exact"], "content_type": headers.get("content-type"), "provider_request_id": headers.get("x-github-request-id")}
            safe_headers = {k: v for k, v in headers.items() if k in {"content-type", "content-length", "etag", "last-modified", "x-github-request-id", "x-ratelimit-limit", "x-ratelimit-remaining", "x-ratelimit-reset", "x-ratelimit-resource", "retry-after"}}
            event_id = _hash(ref, sid, task["next_endpoint"], task.get("variables"), digest)
            events.append({"event_id": event_id, "source": "github", "source_id": sid + ":" + digest, "occurred_at": None, "observed_at": _now(),
                           "event_type": "github_source_response", "peer_id": None, "session_id": None, "agent_id": None, "parent_agent_id": None,
                           "provider": "github", "model": None, "harness": "existing_account_read_api", "work_id": None, "operation_id": None,
                           "status": "observed" if status < 400 and not reader_error else "read_unavailable", "summary": "GitHub source response captured",
                           "url": _clean_url(response["url"]), "metrics": {"body_byte_length": len(raw), "records": len(_page_items(payload, task["kind"])), "http_status": reported_status},
                           "metadata": {"account_ref": ref, "repository": task.get("repository"), "kind": task["kind"], "sha256": digest, "response_headers": safe_headers},
                           "source_ref": source_ref,
                           "full_source": {"encoding": "base64", "body": base64.b64encode(raw).decode("ascii"), "sha256": digest, "byte_length": len(raw),
                                           "url": response["url"], "headers": headers, "status": reported_status, "parsed_json": payload, "exact_http_bytes": response["exact"],
                                           "graphql_query": task.get("query"), "graphql_variables": copy.deepcopy(task.get("variables"))}})
            if response.get("native_envelope") is not None:
                envelope = response["native_envelope"]
                envelope_bytes = _response_bytes(envelope)
                envelope_digest = hashlib.sha256(envelope_bytes).hexdigest()
                events[-1]["full_source"]["native_envelope"] = envelope
                events[-1]["source_ref"].update(native_envelope_sha256=envelope_digest, native_envelope_byte_length=len(envelope_bytes))
                events[-1]["event_id"] = _hash(ref, sid, task["next_endpoint"], task.get("variables"), digest, envelope_digest)
            task.update(observed_at=_now(), last_status=reported_status, last_sha256=digest)
            task["byte_length"] += len(raw)
            if reader_error:
                task.update(status=reader_error, complete=False, retry_epoch=_retry_epoch(headers, task["attempts"]))
                continue
            if status >= 400:
                provider_message = str(payload.get("message", "")).lower() if isinstance(payload, dict) else ""
                explicit_rate = any(phrase in provider_message for phrase in ("rate limit exceeded", "secondary rate limit", "abuse detection mechanism"))
                rate = status == 429 or status == 403 and (headers.get("retry-after") or headers.get("x-ratelimit-remaining") == "0" or explicit_rate)
                task.update(status="rate_limited" if rate else "provider_denied_or_unavailable", complete=False, retry_epoch=_retry_epoch(headers, task["attempts"]))
                if rate:
                    cooldowns[ref] = task["retry_epoch"]
                continue
            if task["kind"] == "identity" and isinstance(payload, dict) and road.get("login") and str(payload.get("login", "")).lower() != str(road["login"]).lower():
                actual_ref = "github:" + road["host"] + ":" + str(payload.get("login") or "provider_principal_unresolved")
                # Keep every observed byte under its actual principal. Repair
                # the requested account road with its existing named keyring;
                # this mismatch never pauses unrelated account/source reads.
                events[-1]["source_ref"].update(account_ref=actual_ref, requested_account_ref=ref, account_mapping_status="mismatch")
                events[-1]["metadata"].update(account_ref=actual_ref, requested_account_ref=ref, actual_provider_login=payload.get("login"), account_mapping_status="mismatch")
                events[-1]["event_id"] = _hash(actual_ref, sid, task["next_endpoint"], digest)
                task.update(status="account_binding_recovery_pending", complete=False, retry_epoch=time.time() + 1)
                accounts[ref].update(identity_state="account_binding_recovery_pending", provider_login=payload.get("login"), provider_account_id=payload.get("id"), preferred_credential_facility="native_keyring")
                road["force_native_keyring"] = True
                tokens.pop(ref, None)
                continue
            if isinstance(payload, dict) and payload.get("errors"):
                task.update(status="graphql_partial_or_error", complete=False, retry_epoch=_retry_epoch(headers, task["attempts"]))
                # Preserve/expand available data, but never mark partial query complete.
                if payload.get("data"):
                    expand(task, payload)
                continue
            task["pages"] += 1
            task["records"] += len(_page_items(payload, task["kind"]))
            if payload is not None:
                expand(task, payload)
            task["retry_epoch"] = 0
            task["status"] = "backfilling"
            next_url = None
            link = headers.get("link", "")
            for target, relation in re.findall(r'<([^>]+)>;\s*rel="([^"]+)"', link):
                if relation == "next":
                    if urllib.parse.urlsplit(target).netloc == urllib.parse.urlsplit(_api(road["host"])).netloc:
                        next_url = target.removeprefix(_api(road["host"]))
                    else:
                        task.update(status="pagination_origin_rejected", complete=False, retry_epoch=_retry_epoch(headers))
            connection = None
            if task.get("query") and isinstance(payload, dict):
                data = payload.get("data") or {}
                repository = data.get("repository") or {}
                if task["kind"] == "discussions":
                    connection = repository.get("discussions")
                elif task["kind"] == "discussion_replies":
                    connection = (data.get("node") or {}).get("replies")
                else:
                    discussion = repository.get("discussion") or {}
                    connection = discussion.get("comments") if task["kind"] == "discussion_comments" else discussion.get("labels")
                info = (connection or {}).get("pageInfo") or {}
                if info.get("hasNextPage"):
                    task["variables"]["cursor"] = info["endCursor"]
                    next_url = task["endpoint"]
                elif connection is None:
                    task.update(status="graphql_source_unavailable", complete=False, retry_epoch=_retry_epoch(headers))
                    continue
                task["records"] += len((connection or {}).get("nodes") or [])
            # Matching refs returns the entire namespace and ignores page and
            # per_page. Inferring pages would reread that namespace forever.
            elif task["kind"] != "refs" and not headers and len(_page_items(payload, task["kind"])) >= 100 and "per_page=100" in task["endpoint"]:
                parts = urllib.parse.urlsplit(task["next_endpoint"])
                params = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
                params = [(k, v) for k, v in params if k != "page"] + [("page", str(task["page"] + 1))]
                next_url = urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, urllib.parse.urlencode(params), ""))
            # Search returns only 1,000 rows per query. Partition actual temporal
            # spans recursively and retain the parent as an aggregation selector.
            if task["kind"] in {"search_issues", "search_commits"} and isinstance(payload, dict):
                if payload.get("incomplete_results"):
                    task["provider_incomplete_results"] = True
                if int(payload.get("total_count") or 0) > 1000:
                    parsed = urllib.parse.urlsplit(task["endpoint"])
                    params = dict(urllib.parse.parse_qsl(parsed.query))
                    search_query = params.get("q", "")
                    field = "created" if task["kind"] == "search_issues" else "committer-date"
                    bounds = task.get("search_bounds") or [0, int(time.time())]
                    lower, upper = bounds
                    if upper - lower <= 1:
                        task.update(status="provider_search_limit_unresolved", complete=False, retry_epoch=_retry_epoch(headers))
                        continue
                    middle = (lower + upper) // 2
                    search_query = re.sub(r"\s+" + field + r":\S+", "", search_query)
                    children = []
                    for lo, hi in ((lower, middle), (middle + 1, upper)):
                        stamp = lambda value: datetime.fromtimestamp(value, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                        params["q"] = search_query + " " + field + ":" + stamp(lo) + ".." + stamp(hi)
                        child_endpoint = parsed.path + "?" + urllib.parse.urlencode(params)
                        child = add(ref, child_endpoint, task["kind"])
                        queue[child]["search_bounds"] = [lo, hi]
                        children.append(child)
                    task.update(status="partitioned_backfilling", child_selectors=children, partitioned=True, complete=False)
                    task["retry_epoch"] = time.time() + refresh
                    continue
                if payload.get("incomplete_results"):
                    task.update(status="provider_search_incomplete", complete=False, retry_epoch=_retry_epoch(headers))
                    continue
            if isinstance(payload, dict) and payload.get("truncated"):
                if task["kind"] == "tree":
                    sha = payload.get("sha")
                    if sha:
                        add(ref, "repos/" + task["repository"] + "/git/trees/" + sha, "tree", task["repository"], immutable=True)
                task.update(status="provider_truncated_unresolved", complete=False, retry_epoch=_retry_epoch(headers))
                continue
            if task.get("status") == "pagination_origin_rejected":
                continue
            if next_url:
                task.update(next_endpoint=next_url, page=task["page"] + 1)
            else:
                task.update(complete=True, status="observed", completed_epoch=time.time(), next_endpoint=task["endpoint"])
            if headers.get("x-ratelimit-remaining") == "0":
                cooldowns[ref] = _retry_epoch(headers)
        except Exception as error:
            # Exception strings can embed URLs, auth values, or source bodies.
            task.update(status="pending_recovery", error_type=type(error).__name__, complete=False, retry_epoch=_retry_epoch({}, task["attempts"]))
    tokens.clear()  # Tokens live only in this invocation, never state or logs.
    for task in queue.values():
        if task.get("partitioned"):
            children = task.get("child_selectors") or []
            task["complete"] = bool(children) and all(queue[child].get("complete") for child in children)
            task["status"] = "observed_partitioned" if task["complete"] else "partitioned_backfilling"
    producers_complete = {}
    for task in queue.values():
        if task["kind"] in {"pull_requests", "commits", "branches", "tags", "refs", "git_commit", "tree", "actions_runs", "actions_jobs", "deployments", "discussions"}:
            key = (task["account_ref"], task.get("repository"))
            producers_complete[key] = producers_complete.get(key, True) and bool(task.get("complete"))
    for template in templates.values():
        children = template.get("expanded_selectors") or []
        if children:
            # Template coverage closes only after concrete child capture and
            # discovery producers close. Empty unresolved templates stay pending.
            template["complete"] = all(queue[child].get("complete") for child in children) and producers_complete.get((template["account_ref"], template.get("repository")), False)
            template["status"] = "observed_expansion" if template["complete"] else "expanded_backfilling"
    result_state.update(cursor=cursor, observed_at=_now(), version=1)
    coverage = []
    source_descriptors = []
    for sid, task in list(queue.items()) + list(templates.items()):
        coverage.append({"source": sid, "source_id": sid, "service": "github", "account_ref": task["account_ref"], "repository": task.get("repository"),
                         "scope": task["kind"], "status": task["status"], "complete": bool(task.get("complete")), "records": task.get("records", 0),
                         "pages": task.get("pages", 0), "byte_length": task.get("byte_length", 0), "next_page": None if task.get("complete") else task.get("page"),
                         "retry_epoch": task.get("retry_epoch"), "last_status": task.get("last_status"), "observed_at": task.get("observed_at"),
                         "unread_regions": [] if task.get("complete") else ["remaining provider-retained records/content for this selector"],
                         "expanded_selectors": task.get("expanded_selectors", task.get("child_selectors", [])),
                         "source_placement": task.get("source_placement"), "provider_original_ref": task.get("provider_original_ref"), "cloud_read_cursor": task.get("cloud_read_cursor")})
        source_descriptors.append({"source_id": sid, "service": "github", "source": "github", "account_ref": task["account_ref"], "repository": task.get("repository"),
                                   "scope": task["kind"], "status": task["status"], "complete": bool(task.get("complete")),
                                   "reader": {"road": "existing_github_account", "host": roads.get(task["account_ref"], {}).get("host"), "endpoint": task["endpoint"], "full_content": True}})
    # Discovery's stable source IDs remain independently visible and inherit
    # concrete-selector progress. They must not remain falsely unread merely
    # because the collector deduplicated the same endpoint under a queue ID.
    canonical_coverage = {row["source_id"]: row for row in coverage}
    canonical_sources = {row["source_id"]: row for row in source_descriptors}
    for alias, canonical in source_aliases.items():
        if canonical in canonical_coverage and alias not in canonical_coverage:
            coverage.append({**canonical_coverage[canonical], "source": alias, "source_id": alias, "canonical_selector_id": canonical})
            source_descriptors.append({**canonical_sources[canonical], "source_id": alias, "canonical_selector_id": canonical})
    if result_state.get("account_discovery", {}).get("status") != "observed":
        coverage.append({"source": "github:native_account_discovery", "service": "github", "status": "pending_recovery", "complete": False,
                         "unread_regions": ["configured native GitHub account inventory pending recovery"], "observed_at": _now()})
    return {"events": events, "coverage": coverage, "state": result_state, "sources": source_descriptors, "accounts": list(accounts.values()),
            "observed_at": _now(), "complete": bool(coverage) and all(row["complete"] for row in coverage),
            "requests": requests, "response_count": len(events), "selector_count": len(coverage), "concrete_selector_count": len(queue), "discovery_alias_count": len(source_aliases),
            "pending_selectors": sum(not row["complete"] for row in coverage), "captured_bytes": sum(event["metrics"]["body_byte_length"] for event in events)}


__all__ = ["collect_github_activity"]
