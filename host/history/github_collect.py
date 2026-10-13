"""Read-only, resumable GitHub history intake for the owner's two accounts.

Outputs batches for work/jev-bounty-recovery/read_history.py. Never marks
notifications read, mutates GitHub, or prints credentials/message bodies.
"""
from __future__ import annotations

import argparse
import base64
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import shutil
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

ACCOUNTS = ('woahwhattheheck', 'tokenjunkielabs')
ROOT = Path(os.environ.get('JEV_HISTORY_ROOT', str(Path(os.environ.get('LOCALAPPDATA',str(Path.home()/'.local/share'))) / 'TJLabs/JevMailReview/2026-09-20'))) / 'github'
API = 'https://api.github.com'
TOKEN = re.compile(r'(?i)\b(?:ghp_|gho_|ghu_|ghs_|ghr_|github_pat_)[A-Za-z0-9_]{12,}\b|\bsk-proj-[A-Za-z0-9_-]{16,}\b')

def clean(value):
    if isinstance(value, str):
        return TOKEN.sub('[REDACTED_TOKEN]', value)
    if isinstance(value, list):
        return [clean(x) for x in value]
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items() if k.lower() not in ('authorization', 'access_token', 'refresh_token')}
    return value

def atomic_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    # A fixed .pending name left by an interrupted write must not prevent
    # every later checkpoint. Keep each attempt in a unique sibling file.
    fd, name = tempfile.mkstemp(prefix=path.name + '.', suffix='.pending', dir=path.parent)
    temp = Path(name)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as out:
            json.dump(clean(data), out, ensure_ascii=False, separators=(',', ':'))
            out.flush(); os.fsync(out.fileno())
        os.replace(temp, path)
    except BaseException:
        temp.unlink(missing_ok=True)
        raise


class GitHubReadError(RuntimeError):
    """A provider status, without provider prose or credential-bearing data."""
    def __init__(self, status):
        self.status = status
        super().__init__(f'GitHub read returned HTTP {status}')


class ReadDeferred(Exception):
    """The provider's persisted cooldown postpones this road, not its queue."""


def retry_deadline(headers, now, fallback):
    deadlines = []
    value = headers.get('retry-after')
    if value is not None:
        try:
            seconds = float(value)
            if math.isfinite(seconds) and 0 <= seconds <= 3153600000:
                deadlines.append(now + seconds)
        except (TypeError, ValueError, OverflowError):
            try:
                stamp = parsedate_to_datetime(value)
                if stamp.tzinfo is not None:
                    seconds = stamp.timestamp() - now
                    if math.isfinite(seconds) and seconds <= 3153600000:
                        deadlines.append(now + max(0, seconds))
            except (TypeError, ValueError, OverflowError):
                pass
    if headers.get('x-ratelimit-remaining') == '0':
        try:
            reset = float(headers.get('x-ratelimit-reset'))
            if math.isfinite(reset) and now <= reset <= now + 3153600000:
                deadlines.append(reset)
        except (TypeError, ValueError, OverflowError):
            pass
    return max(now + 1, *deadlines) if deadlines else now + fallback


def split_search_job(job):
    """Partition an inclusive search range without overlaps or missing seconds."""
    start, end = job['start'], job['end']
    if len(start) == len(end) == 10:
        first, last = date.fromisoformat(start), date.fromisoformat(end)
        if first < last:
            middle = first + (last - first) // 2
            return [{'start': first.isoformat(), 'end': middle.isoformat(), 'page': 1},
                    {'start': (middle + timedelta(days=1)).isoformat(), 'end': last.isoformat(), 'page': 1}]
        first = datetime.fromisoformat(start).replace(tzinfo=timezone.utc)
        last = datetime.fromisoformat(end).replace(tzinfo=timezone.utc) + timedelta(days=1, seconds=-1)
    else:
        first = datetime.fromisoformat(start.replace('Z', '+00:00')).astimezone(timezone.utc)
        last = datetime.fromisoformat(end.replace('Z', '+00:00')).astimezone(timezone.utc)
    seconds = int((last - first).total_seconds())
    if seconds <= 0:
        return None
    middle = first + timedelta(seconds=seconds // 2)
    stamp = lambda value: value.isoformat(timespec='seconds').replace('+00:00', 'Z')
    return [{'start': stamp(first), 'end': stamp(middle), 'page': 1},
            {'start': stamp(middle + timedelta(seconds=1)), 'end': stamp(last), 'page': 1}]

def token_for(account):
    value=os.environ.get('GH_TOKEN_PRIMARY' if account==ACCOUNTS[0] else 'GH_TOKEN_SECONDARY')
    if value:return value
    executable=shutil.which('gh') or str(Path.home()/'AppData/Local/Programs/GitHub CLI/gh.exe')
    proc = subprocess.run([executable, 'auth', 'token', '--hostname', 'github.com', '--user', account],
                          capture_output=True, text=True, timeout=30, check=True)
    token = proc.stdout.strip()
    if not token:
        raise RuntimeError('shared GitHub credential unavailable for ' + account)
    return token

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('GitHub API redirect refused')

class Reader:
    def __init__(self, account, budget):
        self.account, self.token, self.budget = account, None, budget
        self.calls = 0
        self.home = ROOT / account
        self.state_path = self.home / 'checkpoint.json'
        self.state = json.loads(self.state_path.read_text(encoding='utf-8')) if self.state_path.exists() else {
            'schema': 'github-history-checkpoint-v1', 'account': account, 'roads': {},
            'details': [], 'detail_keys': [], 'repositories': [], 'repository_keys': [], 'gaps': []}
        self._index_keys()
        self.opener = urllib.request.build_opener(NoRedirect())

    def _index_keys(self):
        # Keep ordered JSON checkpoints compatible while avoiding a full scan
        # for every detail discovered in a large recovered account history.
        self._detail_keys = set(self.state['detail_keys'])
        self._repository_keys = set(self.state['repository_keys'])

    def save(self):
        atomic_json(self.state_path, self.state)

    def get(self, path, params=None, accept='application/vnd.github+json'):
        if self.calls >= self.budget:
            raise StopIteration('request budget reached')
        if path.startswith(API + '/'):
            url = path
        elif path.startswith('/'):
            url = API + path
        else:
            raise ValueError('Non-GitHub API path')
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != 'https' or parsed.netloc != 'api.github.com':
            raise ValueError('Non-GitHub API URL')
        resource = 'search' if parsed.path.startswith('/search/') else 'core'
        current = time.time()
        cooldowns = self.state.setdefault('cooldowns', {})
        if any(cooldowns.get(scope, 0) > current for scope in ('global', resource)):
            raise ReadDeferred('GitHub provider cooldown active')
        # A deferred restart needs only its checkpoint, not a credential lookup.
        # Resolve the account token when an actual provider read can begin.
        if self.token is None:
            self.token = token_for(self.account)
        if params:
            url += ('&' if parsed.query else '?') + urllib.parse.urlencode(params)
        request = urllib.request.Request(url, method='GET', headers={
            'Authorization': 'Bearer ' + self.token, 'Accept': accept,
            'User-Agent': 'TJLabs-JevHistory/1.0', 'X-GitHub-Api-Version': '2022-11-28'})
        self.calls += 1
        try:
            with self.opener.open(request, timeout=25) as response:
                raw = response.read(8 * 1024 * 1024 + 1)
                if len(raw) > 8 * 1024 * 1024:
                    raise RuntimeError('GitHub page exceeds intake byte bound')
                body = json.loads(raw)
                headers = {name.lower(): value for name, value in response.headers.items()}
        except urllib.error.HTTPError as exc:
            # Store only code and rate metadata, never provider prose or token.
            status = exc.code
            headers = {name.lower(): value for name, value in (exc.headers or {}).items()}
            secondary = False
            empty_repository = False
            if status in (403, 409, 429):
                try:
                    error = json.loads(exc.read(65536))
                    message = str(error.get('message', '')).lower() if isinstance(error, dict) else ''
                    secondary = any(term in message for term in ('secondary rate limit', 'abuse detection mechanism'))
                    empty_repository = (status == 409 and message.strip() == 'git repository is empty.' and
                        bool(re.fullmatch(r'/(?:repos/[^/]+/[^/]+|repositories/\d+)/commits', parsed.path)))
                except (OSError, ValueError, TypeError):
                    pass
            limited = status == 429 or status == 403 and (
                headers.get('x-ratelimit-remaining') == '0' or
                bool(headers.get('retry-after')) or secondary)
            exc.close()
            if empty_repository:
                # Preserve an empty batch and advance the normal commit cursor.
                for scope in ('global', resource):
                    self.state.get('cooldown_backoff', {}).pop(scope, None)
                return [], {}, url
            if limited:
                primary = (headers.get('x-ratelimit-remaining') == '0' and not secondary
                           and headers.get('x-ratelimit-resource') in (None, resource))
                scope = resource if primary else 'global'
                backoff = self.state.setdefault('cooldown_backoff', {})
                attempt = min(backoff.get(scope, 0) + 1, 7)
                backoff[scope] = attempt
                until = retry_deadline(headers, time.time(), min(3600, 60 * 2 ** (attempt - 1)))
                cooldowns[scope] = max(cooldowns.get(scope, 0), until)
            self.state['gaps'].append({'road': self.state.get('active_road'), 'status': status,
                 'at': url.split('?')[0], 'rate_reset': headers.get('x-ratelimit-reset'),
                 'reason': 'rate_limit' if limited else 'provider_error'})
            self.save()
            if limited:
                raise ReadDeferred('GitHub rate limit reached') from None
            raise GitHubReadError(status) from None
        backoff = self.state.get('cooldown_backoff', {})
        for scope in ('global', resource):
            backoff.pop(scope, None)
        links = {}
        for piece in headers.get('link', '').split(','):
            match = re.search(r'<([^>]+)>;\s*rel="([^"]+)"', piece)
            if match:
                links[match[2]] = match[1]
        return body, links, url

    def emit(self, road, key, records, coverage):
        document = clean({'source': 'github', 'account': self.account, 'road': road,
                          'coverage': coverage, 'records': records})
        version = hashlib.sha256(json.dumps(document, ensure_ascii=False, sort_keys=True,
                                            separators=(',', ':')).encode()).hexdigest()
        # A retried page may have changed after an interrupted checkpoint.
        # Preserve both versions; only an exact content replay reuses a batch.
        safe = re.sub(r'[^A-Za-z0-9_.-]', '-', key)[:32]
        path = self.home / f'github-{self.account}-{road}-{safe}-{version}.json'
        if not path.exists():
            atomic_json(path, document)
        elif json.loads(path.read_text(encoding='utf-8')) != document:
            raise RuntimeError('GitHub history batch content differs from its immutable identity')
        return path

    def enqueue_detail(self, url, kind='subject'):
        if not url or not url.startswith(API + '/'): return
        if url in self._detail_keys: return
        self._detail_keys.add(url)
        self.state['detail_keys'].append(url)
        self.state['details'].append({'url': url, 'kind': kind, 'next': url})

    @staticmethod
    def record(obj, kind, account, thread=None):
        who = (obj.get('user') or obj.get('author') or {}).get('login') if isinstance(obj, dict) else None
        body = obj.get('body') or obj.get('message') or obj.get('commit', {}).get('message') or ''
        title = obj.get('title') or obj.get('subject', {}).get('title') or ''
        return {'id': str(obj.get('id') or obj.get('sha') or obj.get('node_id') or ''),
                'thread_id': str(thread or obj.get('url') or obj.get('html_url') or ''),
                'date': obj.get('updated_at') or obj.get('submitted_at') or obj.get('created_at') or obj.get('commit', {}).get('author', {}).get('date'),
                'url': obj.get('html_url') or obj.get('url'), 'body': (title + '\n\n' + body).strip(),
                'metadata': {'kind': kind, 'account': account, 'author': who,
                   'state': obj.get('state'), 'number': obj.get('number'), 'type': obj.get('type')}}

    def simple_road(self, road, path, params, transform, per_page=100):
        slot = self.state['roads'].setdefault(road, {'next': path, 'pages': 0, 'complete': False})
        if slot['complete']: return None
        self.state['active_road'] = road
        query = params if slot['pages'] == 0 else None
        data, links, url = self.get(slot['next'], query)
        if not isinstance(data, list): raise ValueError('Expected GitHub list for ' + road)
        records = transform(data)
        out = self.emit(road, str(slot['pages'] + 1).zfill(5), records,
                        {'api_url': url, 'next': bool(links.get('next')), 'count': len(data)})
        slot['next'] = links.get('next')
        slot['pages'] += 1
        slot['complete'] = not bool(slot['next'])
        self.save()
        return out

    def notifications(self):
        def build(items):
            records = []
            for obj in items:
                subject = obj.get('subject') or {}
                url = subject.get('url')
                self.enqueue_detail(url, 'notification_subject')
                self.enqueue_detail(subject.get('latest_comment_url'), 'notification_latest_comment')
                records.append({'id': str(obj['id']), 'thread_id': url or str(obj['id']),
                   'date': obj.get('updated_at'), 'url': url,
                   'body': subject.get('title') or '',
                   'metadata': {'kind': 'notification', 'account': self.account,
                      'reason': obj.get('reason'), 'unread': obj.get('unread'),
                      'subject_type': subject.get('type'), 'repository': (obj.get('repository') or {}).get('full_name'),
                      'latest_comment_url': subject.get('latest_comment_url'),
                      'body_status': 'subject_only_pending_hydration'}})
            return records
        return self.simple_road('notifications', '/notifications',
                {'all': 'true', 'participating': 'false', 'per_page': 50}, build)

    def events(self):
        def build(items):
            return [{'id': str(x.get('id')), 'thread_id': str(x.get('repo', {}).get('name')),
                     'date': x.get('created_at'), 'url': None,
                     'body': json.dumps(clean({'type': x.get('type'), 'action': x.get('payload', {}).get('action'),
                           'repo': x.get('repo', {}).get('name')})),
                     'metadata': {'kind': 'event', 'account': self.account,
                           'event_type': x.get('type'), 'repo': x.get('repo', {}).get('name')}} for x in items]
        return self.simple_road('events', f'/users/{self.account}/events', {'per_page': 100}, build)

    def init_search(self, kind):
        road = 'search_' + kind
        if road in self.state['roads']:
            # Older checkpoints abandoned whole capped days. Recover each one
            # once, preserving the original gap as historical evidence.
            slot = self.state['roads'][road]
            recovered = False
            for gap in self.state['gaps']:
                day = gap.get('date')
                if (gap.get('road') != road or gap.get('reason') != 'search_1000_cap'
                        or gap.get('resolution') == 'second' or gap.get('requeued_for_subday')
                        or not isinstance(day, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', day)):
                    continue
                if not any(job['start'] == job['end'] == day for job in slot['jobs']):
                    slot['jobs'].append({'start': day, 'end': day, 'page': 1})
                gap['requeued_for_subday'] = True
                slot['complete'], recovered = False, True
            if recovered:
                self.save()
            return
        self.state['active_road'] = road
        profile, _, _ = self.get('/users/' + self.account)
        first = profile['created_at'][:10]
        self.state['roads'][road] = {'jobs': [{'start': first, 'end': date.today().isoformat(),
                                              'page': 1}], 'pages': 0, 'complete': False}
        self.save()

    def search(self, kind):
        self.init_search(kind)
        road = 'search_' + kind
        slot = self.state['roads'][road]
        if not slot['jobs']:
            slot['complete'] = True; self.save(); return None
        self.state['active_road'] = road
        job = slot['jobs'][0]
        qualifier = 'type:pr' if kind == 'pulls' else 'type:issue'
        q = f'author:{self.account} {qualifier} created:{job["start"]}..{job["end"]}'
        data, links, url = self.get('/search/issues', {'q': q, 'per_page': 100, 'page': job['page']})
        total = data.get('total_count', 0)
        if total > 1000:
            smaller = split_search_job(job)
            if smaller is None:
                self.state['gaps'].append({'road': road, 'date': job['start'][:10],
                    'start': job['start'], 'end': job['end'], 'resolution': 'second', 'reason': 'search_1000_cap'})
                slot['jobs'].pop(0); self.save(); return None
            slot['jobs'][:1] = smaller
            self.save(); return None
        items = data.get('items') or []
        for obj in items:
            self.enqueue_detail(obj.get('url'), kind)
        records = [self.record(x, kind, self.account) for x in items]
        key = f'{job["start"]}-{job["end"]}-p{job["page"]}'
        out = self.emit(road, key, records, {'query': q, 'page': job['page'],
                       'total_count': total, 'incomplete_results': data.get('incomplete_results'),
                       'next': bool(links.get('next'))})
        if data.get('incomplete_results'):
            self.state['gaps'].append({'road': road, 'range': key, 'reason': 'incomplete_results'})
        if links.get('next'): job['page'] += 1
        else: slot['jobs'].pop(0)
        slot['pages'] += 1
        slot['complete'] = not bool(slot['jobs'])
        self.save()
        return out

    def repositories(self):
        def build(items):
            for obj in items:
                name = obj.get('full_name')
                if name and name not in self._repository_keys:
                    self._repository_keys.add(name)
                    self.state['repository_keys'].append(name)
                    self.state['repositories'].append({'name': name, 'next': f'/repos/{name}/commits?author={self.account}&per_page=100'})
            return [self.record({**x, 'body': x.get('description')}, 'repository', self.account) for x in items]
        return self.simple_road('repositories', '/user/repos',
              {'affiliation': 'owner,collaborator,organization_member', 'per_page': 100}, build)

    def commits(self):
        if not self.state['repositories']: return None
        job = self.state['repositories'][0]
        self.state['active_road'] = 'commits'
        try:
            data, links, url = self.get(job['next'])
        except GitHubReadError as exc:
            if exc.status not in (404, 410):
                raise
            # Only a definitively unavailable resource leaves the queue.
            # Transient/read-bound failures preserve its exact resume cursor.
            self.state['repositories'].pop(0); self.save(); return None
        if not isinstance(data, list): raise ValueError('Expected commit list')
        page = job.get('page', 1)
        out = self.emit('commits', hashlib.sha256((job['name'] + str(page)).encode()).hexdigest()[:18],
              [self.record(x, 'commit', self.account, job['name']) for x in data],
              {'repository': job['name'], 'page': page, 'next': bool(links.get('next')), 'api_url': url})
        if links.get('next'):
            job['next'] = links['next']; job['page'] = page + 1
        else: self.state['repositories'].pop(0)
        self.save(); return out

    def details(self):
        if not self.state['details']: return None
        job = self.state['details'][0]
        self.state['active_road'] = 'details'
        try:
            obj, links, url = self.get(job['next'], accept='application/vnd.github+json')
        except GitHubReadError as exc:
            if exc.status not in (404, 410):
                raise
            self.state['details'].pop(0); self.save(); return None
        objs = obj if isinstance(obj, list) else [obj]
        records = [self.record(x, job['kind'], self.account, job['url']) for x in objs if isinstance(x, dict)]
        key = hashlib.sha256((job['url'] + str(job.get('page', 1))).encode()).hexdigest()[:20]
        out = self.emit('details', key, records, {'api_url': url, 'kind': job['kind'], 'next': bool(links.get('next'))})
        if job['kind'] in ('pulls', 'issues', 'notification_subject') and isinstance(obj, dict):
            endpoint = obj.get('url') or job['url']
            match = re.search(r'/repos/([^/]+/[^/]+)/(issues|pulls)/(\d+)$', endpoint)
            if match:
                repo, subject_type, number = match.groups()
                related = [(f'issues/{number}/comments', 'issue_comment'),
                           (f'issues/{number}/timeline', 'timeline_event')]
                if subject_type == 'pulls' or isinstance(obj.get('pull_request'), dict):
                    related.extend([(f'pulls/{number}/reviews', 'review'),
                                    (f'pulls/{number}/comments', 'review_comment')])
                for suffix, name in related:
                    self.enqueue_detail(f'{API}/repos/{repo}/{suffix}?per_page=100', name)
        if links.get('next'):
            job['next'] = links['next']; job['page'] = job.get('page', 1) + 1
        else: self.state['details'].pop(0)
        self.save(); return out

    def run(self):
        paths = []
        order = [self.notifications, lambda: self.search('pulls'), lambda: self.search('issues'),
                 self.repositories, self.events, self.details, self.commits]
        while self.calls < self.budget:
            progressed = False
            for action in order:
                if self.calls >= self.budget: break
                before = self.calls
                path = None
                try:
                    path = action()
                except ReadDeferred:
                    # Other roads may use an independent quota. With every
                    # road deferred, the no-progress condition ends this run.
                    pass
                except StopIteration:
                    # An action may need several reads; the budget is a normal
                    # checkpoint boundary, even when reached inside that action.
                    self.save()
                    return self.summary(paths)
                if path: paths.append(str(path))
                if self.calls > before: progressed = True
            if not progressed: break
        self.save()
        return self.summary(paths)

    def summary(self, paths):
        return {'account': self.account, 'requests': self.calls, 'files': len(paths),
                'road_pages': {k: v.get('pages') for k, v in self.state['roads'].items()},
                'queued_details': len(self.state['details']), 'queued_repositories': len(self.state['repositories']),
                'gaps': len(self.state['gaps']), 'output': str(self.home),
                'cooldowns': {scope: until for scope, until in self.state.get('cooldowns', {}).items()
                              if until > time.time()}}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--account', choices=ACCOUNTS, action='append')
    parser.add_argument('--max-requests', type=int, default=12)
    parser.add_argument('--status', action='store_true',
                        help='show saved progress and active cooldowns without collecting or writing')
    args = parser.parse_args()
    if args.max_requests < 1 or args.max_requests > 200: parser.error('max-requests must be 1..200')
    for account in args.account or ACCOUNTS:
        try:
            reader = Reader(account, args.max_requests)
            result = reader.summary([]) if args.status else reader.run()
            print(json.dumps(result), flush=True)
        except Exception as exc:
            print(json.dumps({'account': account, 'error': type(exc).__name__ + ': ' + str(exc)}), flush=True)
            return 1
    return 0

if __name__ == '__main__': sys.exit(main())
