"""Reusable staff onboarding must preserve passwords, owner boundaries and rotation."""
from dataclasses import replace
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from bankbot.config import Settings
from bankbot.portal_store import PortalStore
from bankbot.web import create_app
from tests.test_portal import StubAgent


class SharedStaffInvitationTests(unittest.TestCase):
    CODE = 'synthetic-shared-staff-invitation'
    PASSWORD = 'SyntheticStaffPassword2026'

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.path = Path(self.folder.name) / 'portal.sqlite3'
        self.settings = Settings(cloud_mode=True, database_path=self.path,
            public_url='https://campusbank.example', bootstrap_code='synthetic-owner-bootstrap-secret',
            test_access_code='synthetic-customer-test-code', staff_access_code=self.CODE)
        self.clients = []
        self.app = self.build(self.settings)

    def tearDown(self):
        for client in self.clients: client.close()
        self.folder.cleanup()

    def build(self, settings):
        with patch('bankbot.web.Settings.load', return_value=settings):
            return create_app(service=StubAgent())

    def client(self, app=None):
        client = TestClient(app or self.app, base_url=self.settings.public_url)
        self.clients.append(client)
        client.headers['X-CSRF-Token'] = client.get('/api/bootstrap').json()['csrf']
        return client

    def register(self, client, name, code=None, role='staff'):
        result = client.post('/api/register', json={'username':name, 'password':self.PASSWORD,
            'display_name':name, 'portal_role':role, 'invite_code':code if code is not None else self.CODE,
            'test_access_code':self.settings.test_access_code})
        if result.status_code == 200: client.headers['X-CSRF-Token'] = result.json()['csrf']
        return result

    def sign_out(self, client):
        client.headers['X-CSRF-Token'] = client.post('/api/logout').json()['csrf']

    def test_many_accounts_can_reuse_code_after_restart_and_years_without_admin(self):
        for index in range(3):
            client = self.client()
            result = self.register(client, 'staff_'+str(index))
            self.assertEqual(result.status_code, 200, result.text)
            data = result.json()
            self.assertTrue(data['user']['is_staff'])
            self.assertFalse(data['user']['is_admin'])
            self.assertFalse(data['testing_staff'])
            client.headers['X-CSRF-Token'] = data['csrf']
            self.assertEqual(client.get('/api/admin/requests').status_code, 200)
            self.assertEqual(client.post('/api/admin/staff-invites').status_code, 403)
            self.assertEqual(client.post('/api/admin/import-legacy').status_code, 403)
        future = time.time() + 10*365*86400
        with patch('bankbot.portal_store.time.time', return_value=future):
            restarted = self.build(self.settings)
            result = self.register(self.client(restarted), 'staff_later')
            self.assertEqual(result.status_code, 200, result.text)
            self.assertFalse(result.json()['user']['is_admin'])
        with self.app.state.store.db() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM staff_invites').fetchone()[0], 0)

    def test_existing_customer_requires_correct_password_before_enrolment_then_no_code(self):
        client = self.client()
        self.assertEqual(self.register(client, 'customer', role='customer').status_code, 200)
        self.sign_out(client)
        body = {'username':'customer','password':self.PASSWORD,'portal_role':'staff'}
        self.assertEqual(client.post('/api/login', json=body).status_code, 403)
        self.assertEqual(client.post('/api/login', json={**body,'password':'WrongSyntheticPassword','invite_code':self.CODE}).status_code, 401)
        with self.app.state.store.db() as db:
            self.assertEqual(db.execute("SELECT is_staff FROM users WHERE username='customer'").fetchone()[0], 0)
        result = client.post('/api/login', json={**body,'invite_code':self.CODE})
        self.assertEqual(result.status_code, 200, result.text)
        client.headers['X-CSRF-Token'] = result.json()['csrf']
        self.sign_out(client)
        result = client.post('/api/login', json=body)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertTrue(result.json()['user']['is_staff'])
        self.assertFalse(result.json()['user']['is_admin'])

    def test_invalid_or_missing_shared_code_creates_no_account_and_old_test_route_is_closed(self):
        client = self.client()
        for code in ('', 'wrong-code', self.settings.test_access_code):
            self.assertEqual(self.register(client, 'not_created', code).status_code, 403)
        self.assertEqual(client.post('/api/testing/staff-session', json={}).status_code, 403)
        self.assertEqual(client.get('/api/admin/requests').status_code, 403)
        with self.app.state.store.db() as db:
            self.assertIsNone(db.execute("SELECT id FROM users WHERE username='not_created'").fetchone())
        boot = client.get('/api/bootstrap')
        self.assertNotIn(self.CODE, boot.text)
        self.assertNotIn(self.CODE, repr(self.settings))

    def test_rotating_shared_code_blocks_old_code_without_revoking_existing_staff(self):
        staff = self.client()
        result = self.register(staff, 'existing_staff')
        self.assertEqual(result.status_code, 200)
        rotated = replace(self.settings, staff_access_code='synthetic-replacement-staff-code')
        app = self.build(rotated)
        newcomer = self.client(app)
        self.assertEqual(self.register(newcomer, 'new_staff', self.CODE).status_code, 403)
        self.assertEqual(self.register(newcomer, 'new_staff', rotated.staff_access_code).status_code, 200)
        login = self.client(app).post('/api/login', json={'username':'existing_staff','password':self.PASSWORD,'portal_role':'staff'})
        self.assertEqual(login.status_code, 200)
        self.assertTrue(login.json()['user']['is_staff'])

    def test_fresh_local_shared_staff_is_not_implicitly_owner(self):
        store = PortalStore(Path(self.folder.name)/'fresh.sqlite3', staff_access_code=self.CODE)
        staff = store.register('first_staff', self.PASSWORD, 'Staff', 'staff', self.CODE)
        self.assertTrue(staff['is_staff'])
        self.assertFalse(staff['is_admin'])

    def test_private_settings_validate_length_and_allow_disabling(self):
        with patch('bankbot.config.read_env', return_value={}), patch.dict('os.environ', {'BANKBOT_STAFF_ACCESS_CODE':'short'}, clear=True):
            with self.assertRaisesRegex(ValueError, '16 to 128'):
                Settings.load()
        with patch('bankbot.config.read_env', return_value={}), patch.dict('os.environ', {'BANKBOT_STAFF_ACCESS_CODE':''}, clear=True):
            self.assertEqual(Settings.load().staff_access_code, '')
