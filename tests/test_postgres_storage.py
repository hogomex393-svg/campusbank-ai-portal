"""Configuration checks and real PostgreSQL workflow regressions.

Set PG_TEST_DATABASE_URL to a dedicated test branch. Each test uses its own schema.
"""
import os
import tempfile
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode, quote
from unittest.mock import patch

from fastapi.testclient import TestClient
from bankbot.config import Settings
from bankbot.migrate_database import import_sqlite
from bankbot.portal_store import PortalStore, PortalError
from bankbot.web import create_app
from tests.test_portal import StubAgent


class DatabaseConfigurationTests(unittest.TestCase):
    def load(self, **environment):
        with patch('bankbot.config.read_env', return_value={}):
            with patch.dict(os.environ, environment, clear=True):
                return Settings.load()

    def cloud_values(self):
        return {'BANKBOT_DEPLOYMENT': 'cloud',
            'BANKBOT_BOOTSTRAP_CODE': 'synthetic-owner-code-2026',
            'BANKBOT_TEST_ACCESS_CODE': 'synthetic-class-code'}

    def test_render_uses_database_url_and_external_origin(self):
        url = 'postgresql://user:synthetic-password@db.example/bank?sslmode=require'
        settings = self.load(**self.cloud_values(), DATABASE_URL=url,
            RENDER='true', RENDER_EXTERNAL_URL='https://bank.onrender.com')
        self.assertEqual(settings.database_url, url)
        self.assertEqual(settings.public_url, 'https://bank.onrender.com')
        self.assertNotIn('synthetic-password', repr(settings))

    def test_render_cannot_silently_use_ephemeral_sqlite(self):
        with self.assertRaisesRegex(ValueError, 'Render requires DATABASE_URL'):
            self.load(**self.cloud_values(), RENDER='true', BANKBOT_DB_PATH='C:/data/portal.sqlite3')

    def test_cloud_postgres_requires_tls_and_valid_url(self):
        for url in ['postgresql://user:password@db.example/bank', 'https://db.example/bank',
                    'postgresql://user:password@db.example/']:
            with self.subTest(url=url), self.assertRaises(ValueError):
                self.load(**self.cloud_values(), DATABASE_URL=url)


@unittest.skipUnless(os.environ.get('PG_TEST_DATABASE_URL'), 'Set PG_TEST_DATABASE_URL for real PostgreSQL tests')
class PostgresWorkflowTests(unittest.TestCase):
    def setUp(self):
        import psycopg
        from psycopg import sql

        self.psycopg = psycopg
        self.sql = sql
        self.base_url = os.environ['PG_TEST_DATABASE_URL']
        self.schema = 'bankbot_test_' + uuid.uuid4().hex
        with psycopg.connect(self.base_url, autocommit=True) as connection:
            connection.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(self.schema)))
        parsed = urlsplit(self.base_url)
        options = parse_qsl(parsed.query) + [('options', '-c search_path=' + self.schema)]
        self.url = urlunsplit(parsed._replace(query=urlencode(options, quote_via=quote)))
        self.settings = Settings(database_url=self.url, cloud_mode=True,
            public_url='https://bank.example', bootstrap_code='synthetic-owner-code-2026',
            test_access_code='synthetic-class-code', staff_access_code='SyntheticSharedStaff2026')
        self.apps = []
        self.clients = []
        self.app = self.make_app()

    def make_app(self):
        with patch('bankbot.web.Settings.load', return_value=self.settings):
            app = create_app(service=StubAgent())
        self.apps.append(app)
        return app

    def tearDown(self):
        for client in self.clients:
            client.close()
        for app in self.apps:
            app.state.store.close()
        self.assertTrue(self.schema.startswith('bankbot_test_'))
        with self.psycopg.connect(self.base_url, autocommit=True) as connection:
            connection.execute(self.sql.SQL('DROP SCHEMA {} CASCADE').format(self.sql.Identifier(self.schema)))

    def client(self, app=None):
        client = TestClient(app or self.app, base_url=self.settings.public_url)
        self.clients.append(client)
        client.headers['X-CSRF-Token'] = client.get('/api/bootstrap').json()['csrf']
        return client

    def register(self, client, name, role='customer'):
        response = client.post('/api/register', json={'username': name, 'password': 'SyntheticPass2026',
            'display_name': name, 'portal_role': role,
            'invite_code': self.settings.staff_access_code if role == 'staff' else '',
            'test_access_code': self.settings.test_access_code})
        self.assertEqual(response.status_code, 200, response.text)
        client.headers['X-CSRF-Token'] = response.json()['csrf']
        return response.json()['user']

    def test_chat_duplicate_send_and_restart_persistence(self):
        client = self.client()
        user = self.register(client, 'customer')
        self.assertFalse(user['is_admin'])
        chat = client.post('/api/chats').json()['id']
        payload = {'text': "中文 question? 100% 'quoted'", 'request_id': uuid.uuid4().hex}
        self.assertEqual(client.post(f'/api/chats/{chat}/messages', json=payload).status_code, 200)
        self.assertEqual(client.post(f'/api/chats/{chat}/messages', json=payload).status_code, 200)
        self.assertEqual(self.app.state.bot.calls, 1)
        again = self.client(self.make_app())
        login = again.post('/api/login', json={'username': 'customer', 'password': 'SyntheticPass2026'})
        self.assertEqual(login.status_code, 200)
        self.assertEqual(len(again.get('/api/chats/' + chat).json()['messages']), 2)

    def test_staff_claim_is_atomic_and_reply_reaches_customer(self):
        customer = self.client()
        self.register(customer, 'customer')
        first, second = self.client(), self.client()
        user_one = self.register(first, 'worker_one', 'staff')
        user_two = self.register(second, 'worker_two', 'staff')
        chat = customer.post('/api/chats').json()['id']
        ticket = customer.post('/api/chats/' + chat + '/handoff').json()['ticket']['id']
        store = self.app.state.store
        def claim(user):
            try:
                store.claim_ticket(ticket, user['id'])
                return 200
            except PortalError as error:
                return error.status
        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(claim, [user_one, user_two]))
        self.assertEqual(sorted(outcomes), [200, 409])
        assigned = store.ticket(ticket)['assigned_to']
        worker = first if assigned == user_one['id'] else second
        self.assertEqual(worker.post('/api/admin/tickets/' + ticket + '/reply',
            json={'text': 'A saved PostgreSQL staff reply'}).status_code, 200)
        messages = customer.get('/api/chats/' + chat).json()['messages']
        self.assertEqual(messages[-1]['metadata']['sender'], 'staff')
        self.assertEqual(customer.get('/api/admin/tickets').status_code, 403)

    def test_sqlite_import_preserves_login_ids_and_is_retry_safe(self):
        with tempfile.TemporaryDirectory() as folder:
            source_path = Path(folder) / 'source.sqlite3'
            source = PortalStore(source_path)
            user = source.register('legacy_user', 'SyntheticPass2026', '历史用户')
            owner = 'u:' + user['id']
            chat = source.create_chat(owner)
            source.append_message(chat['id'], 'user', '原来的历史记录? 100%')
            result = import_sqlite(source_path, self.url)
            self.assertEqual(result['status'], 'imported')
            self.assertEqual(result['rows']['users'], 1)
            self.assertEqual(import_sqlite(source_path, self.url)['status'], 'already_imported')
            store = self.app.state.store
            self.assertEqual(store.login('legacy_user', 'SyntheticPass2026')['id'], user['id'])
            store.append_message(chat['id'], 'assistant', 'New record after migration')
            messages = store.chat(owner, chat['id'])['messages']
            self.assertEqual([m['id'] for m in messages], [1, 2])
            self.assertEqual(messages[0]['content'], '原来的历史记录? 100%')


if __name__ == '__main__':
    unittest.main()
