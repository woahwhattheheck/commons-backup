"""Offline regression of the production Discord push Bash using real Git history.

The two Python sender/readiness commands are inert, explicit recording fixtures:
NO Discord request, credential, connection or delivery is exercised. Git clone,
fetch, diff, shallow-history behavior and Bash execute for real. Set
DISCORD_SCOPE_WORKFLOW to test an alternate workflow (including the predecessor).
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest

WORKFLOW = Path(os.environ.get('DISCORD_SCOPE_WORKFLOW', '.github/workflows/commons-discord-cloud.yml'))


def outbound_script() -> str:
    text = WORKFLOW.read_text(encoding='utf-8')
    block = text.split('  outbound:\n', 1)[1]
    lines = block.split('        run: |\n', 1)[1].splitlines()
    script = []
    for line in lines:
        if line and not line.startswith('          '):
            break
        script.append(line[10:] if line else '')
    return '\n'.join(script) + '\n'


SENDER = '''import json, sys
from pathlib import Path
if sys.argv[1:] == ['doctor']:
    print(json.dumps({'state': 'READY'}))
elif len(sys.argv) == 4 and sys.argv[1:3] == ['to-discord', 'send']:
    p = Path(sys.argv[3])
    p.read_bytes()  # A quoted/incorrect pathname fails as the real sender would.
    with Path('sender.jsonl').open('a', encoding='utf-8') as out:
        out.write(json.dumps(str(p), ensure_ascii=False) + '\\n')
else:
    raise SystemExit(2)
'''
READINESS = '''import json, sys
from pathlib import Path
with Path('readiness.jsonl').open('a') as out:
    out.write('checked\\n')
raise SystemExit(0 if json.loads(Path(sys.argv[2]).read_text())['state'] == 'READY' else 2)
'''


@unittest.skipUnless(shutil.which('git') and shutil.which('bash'), 'Git and Bash required')
class DiscordPushScopeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='discord-push-proof-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.origin = self.root / 'origin'
        self.origin.mkdir()
        self.env = {key: value for key, value in os.environ.items() if not key.startswith(('GIT_', 'DISCORD_', 'COMMONS_DISCORD'))}
        self.env.update({'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': os.devnull,
                         'GIT_TERMINAL_PROMPT': '0', 'LC_ALL': 'C.UTF-8',
                         'GIT_AUTHOR_NAME': 'Offline scope fixture', 'GIT_AUTHOR_EMAIL': 'fixture@example.invalid',
                         'GIT_COMMITTER_NAME': 'Offline scope fixture', 'GIT_COMMITTER_EMAIL': 'fixture@example.invalid'})
        # The sender is already an inert stdlib fixture, not production Python.
        # Skip unrelated environment/site-package startup in this fixture only.
        fixture_bin = self.root / 'fixture-bin'
        fixture_bin.mkdir()
        fixture_python = fixture_bin / 'python3'
        fixture_python.write_text('#!/bin/sh\nexec ' + shlex.quote(sys.executable) + ' -S "$@"\n')
        fixture_python.chmod(0o755)
        self.env['PATH'] = str(fixture_bin) + os.pathsep + self.env.get('PATH', os.defpath)
        self.git(self.origin, 'init', '-q')
        self.write('commons_discord.py', SENDER)
        self.write('infra/discord/assert_ready.py', READINESS)
        self.write('p/existing.md', 'original\n')
        self.base = self.commit('base fixture')

    def run_command(self, cwd, *args, check=True, input=None):
        return subprocess.run(args, cwd=cwd, env=self.env, input=input, text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=check, timeout=20)

    def git(self, cwd, *args, check=True, input=None):
        return self.run_command(cwd, 'git', *args, check=check, input=input)

    def write(self, name, content):
        path = self.origin / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')

    def commit(self, message):
        self.git(self.origin, 'add', '-A')
        self.git(self.origin, 'commit', '-qm', message)
        return self.git(self.origin, 'rev-parse', 'HEAD').stdout.strip()

    def checkout(self, *, depth=2):
        target = self.root / 'checkout'
        self.run_command(self.root, 'git', 'clone', '-q', '--no-local', '--depth', str(depth), self.origin.as_uri(), str(target))
        self.work = target
        return self.git(target, 'rev-parse', 'HEAD').stdout.strip()

    def execute(self, *, before=None, expected=None, env_patch=None):
        head = self.git(self.work, 'rev-parse', 'HEAD').stdout.strip()
        before = self.base if before is None else before
        expected = head if expected is None else expected
        script = outbound_script().replace("${{ github.event.before }}", before)
        env = dict(self.env, BEFORE_SHA=before, EXPECTED_HEAD_SHA=expected, GITHUB_SHA=expected)
        if env_patch:
            env.update(env_patch)
        result = subprocess.run(['bash', '-c', script], cwd=self.work, env=env, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=25)
        log = self.work / 'sender.jsonl'
        sent = [json.loads(row) for row in log.read_text().splitlines()] if log.exists() else []
        return result, sent

    def expect_records(self, expected, **kwargs):
        result, sent = self.execute(**kwargs)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(sent, expected)

    def expect_no_send_failure(self, **kwargs):
        result, sent = self.execute(**kwargs)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(sent, [])
        return result

    def test_bash_syntax(self):
        result = subprocess.run(['bash', '-n'], input=outbound_script(), text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_single_commit_added_record(self):
        self.write('p/new.md', 'new'); self.commit('add'); self.checkout()
        self.expect_records(['p/new.md'])

    def test_modification_of_existing_record(self):
        self.write('p/existing.md', 'updated'); self.commit('modify'); self.checkout()
        self.expect_records(['p/existing.md'])

    def test_deleted_record_not_sent(self):
        (self.origin / 'p/existing.md').unlink(); self.commit('delete'); self.checkout()
        self.expect_records([])

    def test_non_record_change_sends_nothing(self):
        self.write('README.md', 'docs'); self.commit('docs'); self.checkout()
        self.expect_records([])

    def test_irrelevant_push_never_calls_readiness(self):
        self.write('README.md', 'docs'); self.commit('docs'); self.checkout()
        self.expect_records([])
        self.assertFalse((self.work / 'readiness.jsonl').exists())

    def test_two_commit_push_fetches_missing_predecessor(self):
        self.write('p/first.md', 'first'); self.commit('first')
        self.write('p/second.md', 'second'); self.commit('second'); self.checkout()
        self.assertNotEqual(self.git(self.work, 'cat-file', '-e', self.base, check=False).returncode, 0)
        self.expect_records(['p/first.md', 'p/second.md'])
        self.assertEqual(self.git(self.work, 'cat-file', '-e', self.base, check=False).returncode, 0)

    def test_long_push_fetches_only_predecessor_not_full_history(self):
        for index in range(7):
            self.write(f'p/item-{index}.md', str(index)); self.commit(str(index))
        self.checkout()
        self.expect_records([f'p/item-{index}.md' for index in range(7)])
        self.assertEqual(self.git(self.work, 'rev-parse', '--is-shallow-repository').stdout.strip(), 'true')
        self.assertEqual(int(self.git(self.work, 'rev-list', '--count', '--all').stdout), 2)

    def test_present_predecessor_does_not_fetch(self):
        self.write('p/new.md', 'new'); self.commit('new'); self.checkout()
        self.git(self.work, 'remote', 'set-url', 'origin', (self.root/'unavailable').as_uri())
        self.expect_records(['p/new.md'])

    def test_missing_predecessor_unavailable_origin_sends_nothing(self):
        for index in range(3):
            self.write(f'p/{index}.md', str(index)); self.commit(str(index))
        self.checkout(); self.git(self.work, 'remote', 'set-url', 'origin', (self.root/'unavailable').as_uri())
        self.expect_no_send_failure()

    def test_unknown_exact_predecessor_sends_nothing(self):
        self.write('p/new.md', 'new'); self.commit('new'); self.checkout()
        self.expect_no_send_failure(before='f'*40)

    def test_missing_before_is_not_silently_replaced_by_parent(self):
        self.write('p/new.md', 'new'); self.commit('new'); self.checkout()
        self.expect_no_send_failure(before='')

    def test_zero_before_requires_manual_reconciliation(self):
        self.write('p/new.md', 'new'); self.commit('new'); self.checkout()
        self.expect_no_send_failure(before='0'*40)

    def test_branch_name_is_not_an_immutable_predecessor(self):
        self.write('p/new.md', 'new'); self.commit('new'); self.checkout()
        self.expect_no_send_failure(before='HEAD^')

    def test_checkout_mismatch_stops_before_any_send(self):
        self.write('p/new.md', 'new'); self.commit('new'); self.checkout()
        self.expect_no_send_failure(expected=self.base)

    def test_malformed_expected_head_stops(self):
        self.write('p/new.md', 'new'); self.commit('new'); self.checkout()
        self.expect_no_send_failure(expected='HEAD')

    def test_space_in_filename(self):
        self.write('p/two words.md', 'value'); self.commit('space'); self.checkout()
        self.expect_records(['p/two words.md'])

    def test_tab_in_filename(self):
        self.write('p/a\tb.md', 'value'); self.commit('tab'); self.checkout()
        self.expect_records(['p/a\tb.md'])

    def test_newline_in_filename(self):
        self.write('p/a\nb.md', 'value'); self.commit('newline'); self.checkout()
        self.expect_records(['p/a\nb.md'])

    def test_unicode_in_filename(self):
        self.write('p/caf\u00e9.md', 'value'); self.commit('unicode'); self.checkout()
        self.expect_records(['p/caf\u00e9.md'])

    def test_backslash_in_filename(self):
        self.write('p/a\\b.md', 'value'); self.commit('backslash'); self.checkout()
        self.expect_records(['p/a\\b.md'])

    def test_nested_record_keeps_existing_pathspec_semantics(self):
        self.write('p/folder/nested.md', 'value'); self.commit('nested'); self.checkout()
        self.expect_records(['p/folder/nested.md'])

    def test_missing_worktree_record_blocks_complete_batch(self):
        self.write('p/aaa.md', 'a'); self.write('p/zzz.md', 'z'); self.commit('batch'); self.checkout()
        (self.work/'p/zzz.md').unlink()
        self.expect_no_send_failure()

    def test_symlink_blocks_complete_batch(self):
        self.write('p/aaa.md', 'a'); (self.origin/'p/zzz.md').symlink_to('../commons_discord.py')
        self.commit('symlink batch'); self.checkout()
        self.expect_no_send_failure()

    def test_rename_into_records_is_delivered_even_when_git_renames_enabled(self):
        self.write('outside.md', 'same'); self.base=self.commit('outside')
        self.git(self.origin, 'mv', 'outside.md', 'p/moved.md'); self.commit('move'); self.checkout()
        self.git(self.work, 'config', 'diff.renames', 'true')
        self.expect_records(['p/moved.md'])

    def test_rename_inside_records_delivers_new_path(self):
        self.git(self.origin, 'mv', 'p/existing.md', 'p/renamed.md'); self.commit('rename'); self.checkout()
        self.git(self.work, 'config', 'diff.renames', 'true')
        self.expect_records(['p/renamed.md'])

    def test_scope_script_uses_environment_not_expression_interpolation(self):
        self.assertNotIn('${{', outbound_script())
        self.assertNotIn('python3 -S', outbound_script())
        text=WORKFLOW.read_text()
        self.assertIn('BEFORE_SHA: ${{ github.event.before }}', text)
        self.assertIn('EXPECTED_HEAD_SHA: ${{ github.sha }}', text)
        self.assertIn('ref: ${{ github.sha }}', text.split('  outbound:\n',1)[1])

    def test_no_new_job_or_full_history_checkout(self):
        text = WORKFLOW.read_text()
        self.assertEqual(re.findall(r'^  ([a-z][a-z_-]+):$', text.split('jobs:\n',1)[1], re.M), ['inbound', 'outbound'])
        self.assertNotIn('fetch-depth: 0', text)
        self.assertIn('fetch-depth: 2', text)
        self.assertNotIn('"test_discord_push_scope.py"', text)
        source_parse = Path('.github/workflows/source-parses.yml').read_text()
        self.assertIn('"test_discord_push_scope.py"', source_parse.split('  pull_request:', 1)[0])
        self.assertIn('test_discord_push_scope.py', source_parse.split('      - name: Verify checker contract', 1)[1].split('      - name:', 1)[0])
        # Poll frequency and concurrency belong to the independent cost-floor lane.


if __name__ == '__main__':
    unittest.main(verbosity=2)
