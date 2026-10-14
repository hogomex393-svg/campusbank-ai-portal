"""Cloud deployment must retain records and prevent first-visitor admin takeover."""
from pathlib import Path
import tempfile
import time
import unittest
import uuid
from unittest.mock import patch
from fastapi.testclient import TestClient
from bankbot.config import Settings
from bankbot.web import create_app
from bankbot.cloud import cloud_port
from tests.test_portal import StubAgent


class CloudDeploymentTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.database=Path(self.folder.name)/'persistent'/'portal.sqlite3'
        self.settings=Settings(api_key='synthetic-api-secret',cloud_mode=True,database_path=self.database,
            public_url='https://campusbank.example',bootstrap_code='bootstrap-secret-for-owner-only',test_access_code='team-testing-secret')
        self.bot=StubAgent();self.clients=[]
        with patch('bankbot.web.Settings.load',return_value=self.settings):self.app=create_app(service=self.bot)

    def tearDown(self):
        for c in self.clients:c.close()
        self.folder.cleanup()

    def client(self,app=None):
        c=TestClient(app or self.app,base_url=self.settings.public_url);self.clients.append(c)
        r=c.get('/api/bootstrap');c.headers['X-CSRF-Token']=r.json()['csrf'];return c

    def register(self,c,name,staff=False,code=None):
        r=c.post('/api/register',json={'username':name,'password':'CloudSyntheticPass2026','display_name':name,
            'portal_role':'staff' if staff else 'customer','invite_code':code if code is not None else self.settings.bootstrap_code if staff else '',
            'test_access_code':self.settings.test_access_code})
        self.assertEqual(r.status_code,200,r.text);c.headers['X-CSRF-Token']=r.json()['csrf'];return r.json()['user']

    def test_first_customer_is_not_admin_and_only_owner_bootstrap_creates_admin(self):
        customer=self.client();user=self.register(customer,'early_customer')
        self.assertFalse(user['is_admin']);self.assertFalse(user['is_staff'])
        self.assertEqual(customer.get('/api/admin/tickets').status_code,403)
        owner=self.client();user=self.register(owner,'owner',staff=True)
        self.assertTrue(user['is_admin'])
        self.assertFalse(owner.get('/api/bootstrap').json()['first_admin_setup_required'])
        attacker=self.client()
        for code in ('wrong-code','错误的邀请码',self.settings.bootstrap_code):
            r=attacker.post('/api/register',json={'username':'attacker','password':'CloudSyntheticPass2026','display_name':'attacker','portal_role':'staff','invite_code':code})
            self.assertEqual(r.status_code,403)

    def test_customer_registration_requires_team_code(self):
        c=self.client()
        for code in ('','wrong','错误的邀请码'):
            r=c.post('/api/register',json={'username':'customer','password':'CloudSyntheticPass2026','display_name':'customer','test_access_code':code})
            self.assertEqual(r.status_code,403)
        self.assertFalse(self.register(c,'customer')['is_admin'])

    def test_https_cookie_and_proxy_origin_validation(self):
        c=TestClient(self.app,base_url=self.settings.public_url);self.clients.append(c)
        r=c.get('/api/bootstrap');header=r.headers['set-cookie']
        self.assertIn('Secure',header);self.assertIn('HttpOnly',header);self.assertIn('SameSite=strict',header)
        c.headers['X-CSRF-Token']=r.json()['csrf']
        self.assertEqual(c.post('/api/chats',headers={'Origin':self.settings.public_url}).status_code,200)
        self.assertEqual(c.post('/api/chats',headers={'Origin':'https://evil.example'}).status_code,403)
        self.assertNotIn(self.settings.bootstrap_code,r.text);self.assertNotIn(self.settings.test_access_code,r.text)
        self.assertNotIn(self.settings.api_key,r.text)

    def test_guest_cannot_spend_model_tokens(self):
        c=self.client();chat=c.post('/api/chats').json()['id']
        r=c.post('/api/chats/'+chat+'/messages',json={'text':'开户条件'})
        self.assertEqual(r.status_code,401);self.assertEqual(self.bot.calls,0)

    def test_tls_terminated_by_provider_does_not_break_origin_or_secure_cookies(self):
        external=self.client()
        internal=TestClient(self.app,base_url='http://internal-service');self.clients.append(internal)
        token=external.cookies.get('campusbank_session')
        r=internal.post('/api/register',headers={'Cookie':'campusbank_session='+token,'X-CSRF-Token':external.headers['X-CSRF-Token'],'Origin':self.settings.public_url},
            json={'username':'proxy_customer','password':'CloudSyntheticPass2026','display_name':'Proxy customer','test_access_code':self.settings.test_access_code})
        self.assertEqual(r.status_code,200);self.assertIn('Secure',r.headers['set-cookie'])

    def test_persistent_database_survives_application_restart(self):
        owner=self.client();self.register(owner,'owner',staff=True)
        customer=self.client();self.register(customer,'customer')
        chat=customer.post('/api/chats').json()['id']
        customer.post('/api/chats/'+chat+'/messages',json={'text':'我想咨询补卡'})
        ticket=customer.post('/api/chats/'+chat+'/handoff').json()['ticket']['id']
        with patch('bankbot.web.Settings.load',return_value=self.settings):again=create_app(service=StubAgent())
        restarted=self.client(again);self.registered_login(restarted,'customer')
        self.assertGreater(len(restarted.get('/api/chats/'+chat).json()['messages']),0)
        self.assertEqual(restarted.get('/api/chats/'+chat).json()['ticket']['id'],ticket)

    def registered_login(self,c,name):
        r=c.post('/api/login',json={'username':name,'password':'CloudSyntheticPass2026'})
        self.assertEqual(r.status_code,200);c.headers['X-CSRF-Token']=r.json()['csrf']

    def test_rate_limit_does_not_duplicate_or_lose_retry_reservations(self):
        c=self.client();self.register(c,'customer');chat=c.post('/api/chats').json()['id']
        for i in range(6):self.assertEqual(c.post('/api/chats/'+chat+'/messages',json={'text':'问题 '+str(i)}).status_code,200)
        request_id=uuid.uuid4().hex;body={'text':'稍后重试','request_id':request_id}
        self.assertEqual(c.post('/api/chats/'+chat+'/messages',json=body).status_code,429)
        self.assertEqual(self.bot.calls,6)
        with patch('bankbot.web.time.time',return_value=time.time()+61):
            self.assertEqual(c.post('/api/chats/'+chat+'/messages',json=body).status_code,200)
        self.assertEqual(self.bot.calls,7)
        self.assertEqual(c.post('/api/chats/'+chat+'/messages',json=body).status_code,200)
        self.assertEqual(self.bot.calls,7)

    def test_cloud_config_and_port_fail_closed_without_printing_secrets(self):
        with patch.dict('os.environ',{'BANKBOT_DEPLOYMENT':'cloud','BANKBOT_DB_PATH':str(self.database),'BANKBOT_BOOTSTRAP_CODE':'','BANKBOT_TEST_ACCESS_CODE':''}):
            with self.assertRaises(ValueError):Settings.load()
        with patch.dict('os.environ',{'BANKBOT_DEPLOYMENT':'cloud','BANKBOT_DB_PATH':str(self.database),'BANKBOT_BOOTSTRAP_CODE':self.settings.bootstrap_code,'BANKBOT_TEST_ACCESS_CODE':self.settings.test_access_code,'BANKBOT_PUBLIC_URL':'https://campusbank.example'}):
            settings=Settings.load()
            self.assertTrue(settings.cloud_mode);self.assertEqual(settings.database_path,self.database)
            self.assertNotIn(self.settings.bootstrap_code,repr(settings));self.assertNotIn(self.settings.test_access_code,repr(settings))
        for value in ('0','65536','not-a-port'):
            with patch.dict('os.environ',{'PORT':value}):
                with self.assertRaises(ValueError):cloud_port()


if __name__=='__main__':unittest.main()
