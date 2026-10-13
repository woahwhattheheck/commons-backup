"""Integration tests for Parcel packages with the existing intake runner.

Set PARCEL_RUNNER_DIR only when using a separately materialized upstream checkout.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import shutil
import subprocess
import sys
import tempfile
import unittest
from urllib.request import Request, urlopen
import zipfile
import bundle

ROOT = Path(__file__).resolve().parent
RUNNER = Path(os.environ.get('PARCEL_RUNNER_DIR', ROOT.parent / 'intake-crm-workflow'))


class BundleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.input = self.root / 'deployment.json'
        self.output = self.root / 'package.zip'
        self.package = self.root / 'package'
        self.raw = self.deployment()
        self.write()

    def deployment(self, preset='client-intake', **fields):
        fields = {'workflowId': preset, 'agency': 'Example & Agency', 'client': 'Synthetic Client',
                  'title': 'Client onboarding', 'support': 'support@example.invalid', **fields}
        script = "const M=require('./model.js');console.log(JSON.stringify(M.deployment(M.newOrder(JSON.parse(process.argv[1]),'2026-09-08T11:00:00.000Z','test-order'))));"
        run = subprocess.run(['node', '-e', script, json.dumps(fields)], cwd=ROOT, text=True, capture_output=True, check=True, timeout=10)
        return json.loads(run.stdout)

    def write(self):
        self.input.write_text(json.dumps(self.raw), encoding='utf-8')

    def build(self, output=None, runner=None):
        return bundle.build(self.input, runner or RUNNER, output or self.output, '9f216e50135948488cb2d95dfaaca337b490d3f5')

    def unpack(self):
        self.build()
        with zipfile.ZipFile(self.output) as archive:
            archive.extractall(self.package)

    def cli(self, *args):
        run = subprocess.run([sys.executable, '-B', 'run.py', '--db', 'smoke.sqlite3', *args], cwd=self.package,
                             text=True, capture_output=True, check=True, timeout=15)
        return [json.loads(line) for line in run.stdout.splitlines() if line.strip()]

    def test_actual_upstream_with_implicit_body_packages(self):
        self.assertNotIn('<body', (RUNNER / 'index.html').read_text().lower())
        self.build()
        self.assertTrue(self.output.is_file())

    def test_manifest_hashes_all_members_and_preserves_upstream_bytes(self):
        result = self.build()
        with zipfile.ZipFile(self.output) as archive:
            manifest = json.loads(archive.read('MANIFEST.json'))
            self.assertEqual(set(archive.namelist()) - {'MANIFEST.json'}, set(manifest['files']))
            for name, meta in manifest['files'].items():
                actual = archive.read(name)
                self.assertEqual(meta, {'sha256': hashlib.sha256(actual).hexdigest(), 'bytes': len(actual)})
            for name in ('workflow.py', 'index.html'):
                self.assertEqual(archive.read(name), (RUNNER / name).read_bytes())
            self.assertFalse(manifest['sourceRevisionIndependentlyVerified'])
        self.assertEqual(result['sha256'], hashlib.sha256(self.output.read_bytes()).hexdigest())

    def test_existing_package_is_not_overwritten(self):
        self.output.write_bytes(b'existing customer package')
        with self.assertRaises(FileExistsError):
            self.build()
        self.assertEqual(self.output.read_bytes(), b'existing customer package')

    def test_only_source_not_customer_database_is_copied(self):
        source = self.root / 'runner'
        source.mkdir()
        for name in ('workflow.py', 'index.html'):
            shutil.copyfile(RUNNER / name, source / name)
        (source / 'customer.sqlite3').write_bytes(b'private record')
        (source / 'workspace-export.json').write_text('{"private":true}')
        self.build(runner=source)
        with zipfile.ZipFile(self.output) as archive:
            self.assertNotIn('customer.sqlite3', archive.namelist())
            self.assertNotIn('workspace-export.json', archive.namelist())

    def test_reproducible_bundle_bytes(self):
        first = self.build()
        second = self.build(self.root / 'second.zip')
        self.assertEqual(first['sha256'], second['sha256'])

    def test_three_presets_have_real_idempotent_cli_workflows(self):
        for preset in bundle.PRESETS:
            with self.subTest(preset=preset):
                self.raw = self.deployment(preset)
                self.write()
                self.output = self.root / (preset + '.zip')
                self.package = self.root / preset
                self.unpack()
                self.cli('configure', 'config.local.json')
                first = self.cli('ingest', 'example-intake.json')[0]
                second = self.cli('ingest', 'example-intake.json')[0]
                self.assertTrue(first['created'])
                self.assertFalse(second['created'])
                self.assertEqual(first['job_id'], second['job_id'])
                self.cli('work', '--limit', '20')
                state = self.cli('export')[0]
                self.assertEqual([len(state[k]) for k in ('customers', 'jobs', 'tasks', 'notifications')], [1, 1, 3, 1])
                self.assertEqual([t['title'] for t in state['tasks']], self.raw['tasks'])
                self.assertEqual(json.loads(state['notifications'][0]['body'])['type'], 'cleaning.job.created')

    def test_source_mapping_is_consumed_by_real_runner(self):
        self.raw['fieldMapping']['name'] = 'full_name'
        self.raw['exampleIntake']['payload']['full_name'] = self.raw['exampleIntake']['payload'].pop('name')
        self.write()
        self.unpack()
        self.cli('configure', 'config.local.json')
        self.cli('ingest', 'example-intake.json')
        self.assertEqual(self.cli('export')[0]['customers'][0]['name'], 'Example Client')

    def test_real_http_keeps_dashboard_routes_and_escapes_branding(self):
        self.raw['agency'] = '<script>not executable</script>'
        self.raw['title'] = 'Example & client'
        self.write()
        self.unpack()
        proc = subprocess.Popen([sys.executable, '-B', 'run.py', '--db', 'http.sqlite3', 'serve', '--port', '0'],
                                cwd=self.package, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        def stop():
            proc.terminate()
            try:
                proc.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.communicate(timeout=5)
        self.addCleanup(stop)
        with selectors.DefaultSelector() as sel:
            sel.register(proc.stdout, selectors.EVENT_READ)
            self.assertTrue(sel.select(timeout=10), 'server did not start')
            line = proc.stdout.readline()
        self.assertIn('http://', line, line + proc.stderr.read() if proc.poll() is not None else line)
        base = re.search(r'http://\S+', line).group(0)
        with urlopen(base + '/', timeout=5) as response:
            page = response.read().decode()
        self.assertIn('data-parcel="brand"', page)
        self.assertIn('&lt;script&gt;not executable&lt;/script&gt;', page)
        self.assertNotIn('<script>not executable</script>', page)
        self.assertIn('<title>Example &amp; client</title>', page)
        self.assertIn('id="intake"', page)
        request = Request(base + '/api/intakes', data=json.dumps(self.raw['exampleIntake']).encode(), headers={'Content-Type': 'application/json'})
        with urlopen(request, timeout=5) as response:
            self.assertEqual(response.status, 201)
        with urlopen(request, timeout=5) as response:
            self.assertEqual(response.status, 200)
        with urlopen(base + '/api/state', timeout=5) as response:
            state = json.load(response)
        self.assertEqual(len(state['jobs']), 1)
        self.assertEqual([t['title'] for t in state['tasks']], self.raw['tasks'])

    def test_nonempty_endpoint_not_inherited(self):
        self.raw['endpoint'] = 'https://example.invalid/not-called'
        self.write()
        self.build()
        with zipfile.ZipFile(self.output) as archive:
            self.assertEqual(json.loads(archive.read('config.local.json'))['endpoint'], '')

    def test_invalid_mapping_rejected_without_output(self):
        self.raw['fieldMapping']['email'] = 'name'
        self.write()
        with self.assertRaises(ValueError):
            self.build()
        self.assertFalse(self.output.exists())

    def test_bad_brand_rejected(self):
        self.raw['brand'] = '"bad'
        self.write()
        with self.assertRaises(ValueError):
            self.build()

    def test_missing_runner_reports_missing_source(self):
        with self.assertRaises(FileNotFoundError):
            self.build(runner=self.root / 'absent')
        self.assertFalse(self.output.exists())

    def test_unsupported_version_rejected(self):
        self.raw['version'] = 2
        self.write()
        with self.assertRaises(ValueError):
            self.build()

    def test_invalid_revision_not_certified(self):
        with self.assertRaises(ValueError):
            bundle.build(self.input, RUNNER, self.output, 'main')

    def test_invalid_sample_date_rejected(self):
        self.raw['exampleIntake']['payload']['preferred_date'] = 'not-a-date'
        self.write()
        with self.assertRaises(ValueError):
            self.build()
        self.assertFalse(self.output.exists())


if __name__ == '__main__':
    unittest.main()
