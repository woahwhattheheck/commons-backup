"""Run: python -m unittest -v test_workflow.py. All HTTP traffic is loopback."""
import copy
import json
import socket
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from workflow import Conflict, InputError, Server, Store, encoded

EXAMPLE = json.loads(Path(__file__).with_name('example-intake.json').read_text())


@contextmanager
def running(server):
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}'
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def post(url, value, headers=None):
    request = Request(url, data=json.dumps(value).encode(), method='POST',
                      headers={'Content-Type': 'application/json', **(headers or {})})
    with urlopen(request, timeout=5) as response:
        return response.status, json.load(response)


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = str(Path(self.directory.name) / 'workspace.sqlite3')
        self.store = Store(self.path)
        self.request = copy.deepcopy(EXAMPLE)

    def tearDown(self):
        self.directory.cleanup()

    def test_atomic_customer_job_tasks_outbox(self):
        result = self.store.intake(self.request)
        state = self.store.snapshot()
        self.assertTrue(result['created'])
        self.assertEqual([len(state[t]) for t in ('customers', 'intakes', 'jobs', 'tasks', 'outbox')], [1, 1, 1, 3, 1])
        self.assertEqual(state['jobs'][0]['customer_id'], result['customer_id'])
        self.assertEqual(state['outbox'][0]['state'], 'pending')

    def test_exact_replay_and_restart(self):
        first = self.store.intake(self.request)
        result = Store(self.path).intake(self.request)
        self.assertFalse(result['created'])
        self.assertEqual(result['job_id'], first['job_id'])
        self.assertEqual(len(self.store.snapshot()['tasks']), 3)

    def test_same_id_different_payload_conflict(self):
        self.store.intake(self.request)
        self.request['payload']['address'] = 'A different address'
        with self.assertRaises(Conflict):
            self.store.intake(self.request)
        self.assertEqual(len(self.store.snapshot()['jobs']), 1)

    def test_parallel_duplicate_requests(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            rows = list(pool.map(lambda _: self.store.intake(self.request), range(24)))
        self.assertEqual(sum(row['created'] for row in rows), 1)
        self.assertEqual(len({row['job_id'] for row in rows}), 1)

    def test_repeat_customer_new_job(self):
        first = self.store.intake(self.request)
        self.request['id'] = 'example-cleaning-002'
        self.request['payload']['email'] = ' CUSTOMER@EXAMPLE.COM '
        second = self.store.intake(self.request)
        self.assertEqual(first['customer_id'], second['customer_id'])
        self.assertNotEqual(first['job_id'], second['job_id'])
        self.assertEqual(len(self.store.snapshot()['customers']), 1)

    def test_mapping_persistence_and_replay_after_mapping_changes(self):
        first = self.store.intake(self.request)
        self.store.configure({'mapping': {'name': 'customer_name', 'email': 'contact_email'}})
        self.assertEqual(Store(self.path).settings()['mapping']['name'], 'customer_name')
        # An unchanged source replay remains idempotent even after configuration changes.
        self.assertEqual(Store(self.path).intake(self.request)['job_id'], first['job_id'])
        self.request['id'] = 'mapped-002'
        self.request['payload']['customer_name'] = self.request['payload'].pop('name')
        self.request['payload']['contact_email'] = self.request['payload'].pop('email')
        self.assertTrue(self.store.intake(self.request)['created'])

    def test_invalid_input_is_atomic(self):
        for field, invalid in [('name', ''), ('email', 'missing-at'), ('address', None), ('preferred_date', '2026-99-99'), ('notes', 'x' * 4001)]:
            with self.subTest(field=field):
                request = copy.deepcopy(self.request)
                request['payload'][field] = invalid
                with self.assertRaises(InputError):
                    self.store.intake(request)
        self.assertFalse(self.store.snapshot()['customers'])
        self.assertFalse(self.store.snapshot()['outbox'])

    def test_configuration_is_atomic(self):
        original = self.store.settings()
        with self.assertRaises(InputError):
            self.store.configure({'mapping': {'name': 'customer'}, 'endpoint': 'file:///tmp/customer'})
        self.assertEqual(self.store.settings(), original)
        with self.assertRaises(InputError):
            self.store.configure({'mapping': {'name': 'email'}})

    def test_local_notification_once_parallel_workers(self):
        self.store.intake(self.request)
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(lambda _: self.store.process_one(), range(12)))
        state = self.store.snapshot()
        self.assertEqual(sum(item['processed'] for item in results), 1)
        self.assertEqual(len(state['notifications']), 1)
        self.assertEqual(state['outbox'][0]['attempts'], 1)
        self.assertEqual(self.store.retry(state['outbox'][0]['id'])['state'], 'delivered')
        self.assertFalse(self.store.process_one()['processed'])

    def test_task_completion_and_reopen(self):
        self.store.intake(self.request)
        tasks = self.store.snapshot()['tasks']
        for task in tasks:
            self.store.complete_task(task['id'], True)
        self.assertEqual(self.store.snapshot()['jobs'][0]['status'], 'complete')
        self.store.complete_task(tasks[0]['id'], False)
        self.assertEqual(self.store.snapshot()['jobs'][0]['status'], 'in_progress')
        with self.assertRaises(InputError):
            self.store.complete_task(tasks[0]['id'], 'false')

    def test_receiver_replays_and_conflicts(self):
        event = {'event_id': 'event:1', 'details': 'synthetic'}
        self.assertFalse(self.store.receive('event:1', event)['duplicate'])
        self.assertTrue(self.store.receive('event:1', event)['duplicate'])
        with self.assertRaises(Conflict):
            self.store.receive('event:1', {**event, 'details': 'different'})
        with self.assertRaises(InputError):
            self.store.receive('event:2', event)
        self.assertEqual(len(self.store.snapshot()['inbox']), 1)

    def test_real_http_receiver(self):
        receiver = Store(str(Path(self.directory.name) / 'receiver.sqlite3'))
        with running(Server(('127.0.0.1', 0), receiver)) as url:
            self.store.configure({'endpoint': url + '/api/receive'})
            self.store.intake(self.request)
            self.assertEqual(self.store.process_one()['state'], 'delivered')
            self.assertEqual(len(receiver.snapshot()['inbox']), 1)
            self.assertEqual(self.store.snapshot()['notifications'], [])

    def test_disconnect_after_remote_commit_retries_without_remote_duplicate(self):
        receiver = Store(str(Path(self.directory.name) / 'receiver.sqlite3'))
        calls = []
        class DropFirst(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass
            def do_POST(self):
                payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                result = receiver.receive(self.headers['Idempotency-Key'], payload)
                calls.append(result)
                if len(calls) == 1:
                    self.connection.shutdown(socket.SHUT_RDWR)
                    self.connection.close()
                    return
                body = encoded(result).encode()
                self.send_response(200)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
        with running(ThreadingHTTPServer(('127.0.0.1', 0), DropFirst)) as url:
            self.store.configure({'endpoint': url + '/receiver'})
            self.store.intake(self.request)
            self.assertEqual(self.store.process_one()['state'], 'retry')
            row = self.store.snapshot()['outbox'][0]
            self.assertGreater(row['next_attempt'], time.time())
            self.assertFalse(self.store.process_one()['processed'])
            self.store.retry(row['id'])
            self.assertEqual(Store(self.path).process_one()['state'], 'delivered')
        self.assertEqual(len(calls), 2)
        self.assertFalse(calls[0]['duplicate'])
        self.assertTrue(calls[1]['duplicate'])
        self.assertEqual(len(receiver.snapshot()['inbox']), 1)
        self.assertEqual(len(self.store.snapshot()['jobs']), 1)

    def test_non_success_status_retains_retry(self):
        class Reject(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass
            def do_POST(self):
                self.rfile.read(int(self.headers['Content-Length']))
                self.send_response(503)
                self.end_headers()
        with running(ThreadingHTTPServer(('127.0.0.1', 0), Reject)) as url:
            self.store.configure({'endpoint': url})
            self.store.intake(self.request)
            self.assertEqual(self.store.process_one()['state'], 'retry')
        row = self.store.snapshot()['outbox'][0]
        self.assertEqual(row['last_error'], 'Receiver returned HTTP 503.')
        self.assertEqual(row['attempts'], 1)
        self.assertIsNone(row['delivered_at'])

    def test_redirect_is_not_delivery(self):
        class Redirect(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass
            def do_POST(self):
                self.rfile.read(int(self.headers['Content-Length']))
                self.send_response(302)
                self.send_header('Location', '/success')
                self.end_headers()
            def do_GET(self):
                self.send_response(200)
                self.end_headers()
        with running(ThreadingHTTPServer(('127.0.0.1', 0), Redirect)) as url:
            self.store.configure({'endpoint': url})
            self.store.intake(self.request)
            self.assertEqual(self.store.process_one()['state'], 'retry')
        self.assertIn('302', self.store.snapshot()['outbox'][0]['last_error'])

    def test_expired_worker_lease_recovered(self):
        self.store.intake(self.request)
        with self.store.transaction() as db:
            db.execute("UPDATE outbox SET state='sending',lease_until=?,lease_token='old-worker'", (time.time()-1,))
        self.assertEqual(self.store.process_one()['state'], 'delivered')
        self.assertEqual(len(self.store.snapshot()['notifications']), 1)

    def test_live_lease_not_reassigned(self):
        self.store.intake(self.request)
        with self.store.transaction() as db:
            db.execute("UPDATE outbox SET state='sending',lease_until=?,lease_token='live-worker'", (time.time()+30,))
        self.assertFalse(self.store.process_one()['processed'])
        with self.assertRaises(Conflict):
            self.store.retry('intake:' + self.request['id'])

    def test_http_api_dashboard_and_export(self):
        with running(Server(('127.0.0.1', 0), self.store)) as url:
            with urlopen(url, timeout=5) as response:
                self.assertIn(b'From request to ready-to-work.', response.read())
            first_status, first = post(url + '/api/intakes', self.request)
            second_status, second = post(url + '/api/intakes', self.request)
            self.assertEqual((first_status, second_status), (201, 200))
            self.assertEqual(first['job_id'], second['job_id'])
            post(url + '/api/process', {})
            with urlopen(url + '/api/export', timeout=5) as response:
                state = json.load(response)
            self.assertEqual(len(state['jobs']), 1)
            self.assertEqual(len(state['notifications']), 1)
            changed = copy.deepcopy(self.request)
            changed['payload']['service'] = 'Deep clean'
            with self.assertRaises(HTTPError) as error:
                post(url + '/api/intakes', changed)
            self.assertEqual(error.exception.code, 409)
            error.exception.close()

    def test_http_selected_retry_leaves_older_queue_pending(self):
        self.store.intake(self.request)
        second = copy.deepcopy(self.request)
        second['id'] = 'selected-second'
        self.store.intake(second)
        selected = 'intake:' + second['id']
        with running(Server(('127.0.0.1', 0), self.store)) as url:
            post(url + '/api/retry', {'id': selected})
            _, result = post(url + '/api/process', {'id': selected})
            self.assertEqual(result['id'], selected)
            state = self.store.snapshot()
            self.assertEqual([n['id'] for n in state['notifications']], [selected])
            states = {row['id']: row['state'] for row in state['outbox']}
            self.assertEqual(states['intake:' + self.request['id']], 'pending')
            _, next_result = post(url + '/api/process', {})
            self.assertEqual(next_result['id'], 'intake:' + self.request['id'])
            self.assertEqual(len(self.store.snapshot()['notifications']), 2)

    def test_selected_unavailable_event_does_not_process_other_job(self):
        self.store.intake(self.request)
        selected = 'intake:' + self.request['id']
        second = copy.deepcopy(self.request)
        second['id'] = 'other-pending'
        self.store.intake(second)
        with self.store.transaction() as db:
            db.execute("UPDATE outbox SET state='sending',lease_until=?,lease_token='live' WHERE id=?", (time.time()+30, selected))
        with running(Server(('127.0.0.1', 0), self.store)) as url:
            _, result = post(url + '/api/process', {'id': selected})
            self.assertFalse(result['processed'])
            _, missing = post(url + '/api/process', {'id': 'intake:not-present'})
            self.assertFalse(missing['processed'])
            self.assertEqual(self.store.snapshot()['notifications'], [])
            with self.assertRaises(HTTPError) as error:
                post(url + '/api/process', {'id': ''})
            self.assertEqual(error.exception.code, 400)
            error.exception.close()

    def test_http_malformed_json_and_size(self):
        with running(Server(('127.0.0.1', 0), self.store)) as url:
            for body in (b'{', b'[]', b'{"payload":NaN}', b' ' * 131073):
                request = Request(url + '/api/intakes', data=body, method='POST')
                with self.assertRaises(HTTPError) as error:
                    urlopen(request, timeout=5)
                self.assertEqual(error.exception.code, 400)
                error.exception.close()
            self.assertEqual(self.store.snapshot()['intakes'], [])

    def test_markup_is_stored_as_text(self):
        self.request['payload']['name'] = '<img src=x onerror=alert(1)>'
        self.store.intake(self.request)
        self.assertEqual(self.store.snapshot()['customers'][0]['name'], self.request['payload']['name'])
        html = Path(__file__).with_name('index.html').read_text()
        self.assertNotIn('.innerHTML', html)
        self.assertIn('.textContent=', html)


if __name__ == '__main__':
    unittest.main()
