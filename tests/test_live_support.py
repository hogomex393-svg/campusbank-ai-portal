"""Independent identities, invitations, chat handoff and competing support workers."""
import json
import sqlite3
import tempfile
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from fastapi.testclient import TestClient
from bankbot.web import create_app
from bankbot.portal_store import PortalStore
from bankbot.service import ChatService, wants_human
from bankbot.config import Settings
from tests.test_portal import StubAgent
from tests.test_system import ScriptedClient


class LiveSupportTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.bot=StubAgent()
        self.app=create_app(Path(self.folder.name)/'support.sqlite3',self.bot)
        self.clients=[]
        self.admin=self.client()
        self.register(self.admin,'manager',role='staff')

    def tearDown(self):
        for c in self.clients:c.close()
        self.folder.cleanup()

    def client(self):
        c=TestClient(self.app);self.clients.append(c)
        c.headers['X-CSRF-Token']=c.get('/api/bootstrap').json()['csrf']
        return c

    def register(self,c,name,role='customer',code=''):
        r=c.post('/api/register',json={'username':name,'password':'SyntheticTestPass2026','display_name':name,'portal_role':role,'invite_code':code})
        self.assertEqual(r.status_code,200,r.text)
        c.headers['X-CSRF-Token']=r.json()['csrf'];return r.json()

    def invite(self):
        r=self.admin.post('/api/admin/staff-invites');self.assertEqual(r.status_code,200)
        return r.json()['invite_code']

    def staff(self,name):
        c=self.client();self.register(c,name,'staff',self.invite());return c

    def logout(self,c):
        r=c.post('/api/logout');c.headers['X-CSRF-Token']=r.json()['csrf']

    def test_invited_staff_have_support_but_not_manager_privileges(self):
        code=self.invite();staff=self.client();result=self.register(staff,'worker','staff',code)
        self.assertTrue(result['user']['is_staff']);self.assertFalse(result['user']['is_admin'])
        self.assertEqual(result['portal_role'],'staff')
        self.assertEqual(staff.get('/api/admin/tickets').status_code,200)
        self.assertEqual(staff.post('/api/admin/staff-invites').status_code,403)
        self.assertEqual(staff.post('/api/admin/import-legacy').status_code,403)
        again=self.client()
        r=again.post('/api/register',json={'username':'reuse','password':'SyntheticTestPass2026','display_name':'reuse','portal_role':'staff','invite_code':code})
        self.assertEqual(r.status_code,403)
        with self.app.state.store.db() as db:
            self.assertIsNone(db.execute("SELECT id FROM users WHERE username='reuse'").fetchone())
            self.assertIsNone(db.execute('SELECT token_hash FROM staff_invites WHERE token_hash=?',(code,)).fetchone())

    def test_role_picker_cannot_grant_permissions_but_existing_user_can_redeem_invite(self):
        c=self.client();self.register(c,'customer');self.logout(c)
        body={'username':'customer','password':'SyntheticTestPass2026','portal_role':'staff'}
        self.assertEqual(c.post('/api/login',json=body).status_code,403)
        code=self.invite()
        self.assertEqual(c.post('/api/login',json={**body,'password':'WrongTestPassword','invite_code':code}).status_code,401)
        r=c.post('/api/login',json={**body,'invite_code':code})
        self.assertEqual(r.status_code,200);c.headers['X-CSRF-Token']=r.json()['csrf']
        self.assertEqual(c.get('/api/bootstrap').json()['portal_role'],'staff')
        self.assertEqual(c.get('/api/admin/tickets').status_code,200)

    def test_chat_handoff_keeps_context_is_idempotent_and_delivers_manual_reply(self):
        worker=self.staff('worker');customer=self.client();self.register(customer,'customer')
        chat=customer.post('/api/chats').json()['id']
        customer.post('/api/chats/'+chat+'/messages',json={'text':'我的补卡申请需要修改地址','request_id':uuid.uuid4().hex})
        r=customer.post('/api/chats/'+chat+'/handoff');self.assertEqual(r.status_code,200)
        ticket=r.json()['ticket']['id'];self.assertFalse(r.json()['existing'])
        self.assertIn('修改地址',r.json()['ticket']['description'])
        again=customer.post('/api/chats/'+chat+'/handoff').json()
        self.assertTrue(again['existing']);self.assertEqual(again['ticket']['id'],ticket)
        original_calls=self.bot.calls
        customer.post('/api/chats/'+chat+'/messages',json={'text':'我希望寄到新的宿舍','request_id':uuid.uuid4().hex})
        self.assertEqual(self.bot.calls,original_calls)
        context=worker.get('/api/admin/tickets/'+ticket).json()['chat']
        self.assertTrue(any(m['content']=='我希望寄到新的宿舍' for m in context['messages']))
        self.assertEqual(worker.post('/api/admin/tickets/'+ticket+'/reply',json={'text':'人工回复：我们一起核对演示申请地址。'}).status_code,200)
        messages=customer.get('/api/chats/'+chat).json()['messages']
        self.assertEqual(messages[-1]['metadata']['sender'],'staff')
        self.assertEqual(len(worker.get('/api/admin/tickets').json()),1)
        self.assertGreater(worker.get('/api/admin/tickets').json()[0]['message_count'],2)

    def test_handoff_requires_customer_login_and_chat_ownership(self):
        guest=self.client();chat=guest.post('/api/chats').json()['id']
        self.assertEqual(guest.post('/api/chats/'+chat+'/handoff').status_code,401)
        self.register(guest,'customer')
        outsider=self.client();self.register(outsider,'outsider')
        self.assertEqual(outsider.post('/api/chats/'+chat+'/handoff').status_code,404)

    def test_two_staff_cannot_overwrite_each_others_assignment(self):
        first=self.staff('worker_one');second=self.staff('worker_two')
        customer=self.client();self.register(customer,'customer')
        chat=customer.post('/api/chats').json()['id']
        ticket=customer.post('/api/chats/'+chat+'/handoff').json()['ticket']['id']
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes=list(pool.map(lambda c:c.post('/api/admin/tickets/'+ticket+'/claim').status_code,(first,second)))
        self.assertEqual(sorted(outcomes),[200,409])
        loser=(first,second)[outcomes.index(409)]
        self.assertEqual(loser.post('/api/admin/tickets/'+ticket+'/reply',json={'text':'不应覆盖其他人的回复'}).status_code,409)
        self.assertEqual(loser.post('/api/admin/tickets/'+ticket+'/resolve').status_code,409)
        self.assertEqual(customer.post('/api/tickets/'+ticket+'/resume-ai').status_code,200)

    def test_handoff_button_available_online_and_offline_without_false_negation(self):
        offline=ChatService(Settings(api_key=''))
        for text in ('请转人工客服','Can I speak to a real person?'):
            reply=offline.respond(text,mode='offline')
            self.assertTrue(any(a['service_id']=='human_support' for a in reply.actions))
        self.assertFalse(wants_human('不需要转人工客服'))
        self.assertFalse(wants_human("I don't need a human agent"))
        client=ScriptedClient([{'role':'assistant','content':'可以，点击转人工按钮联系工作人员。'}])
        online=ChatService(Settings(api_key='synthetic'),client)
        self.assertTrue(any(a['service_id']=='human_support' for a in online.respond('我要转人工客服').actions))

    def test_expired_invite_cannot_enable_staff(self):
        code=self.invite()
        with self.app.state.store.db() as db:db.execute('UPDATE staff_invites SET expires=0')
        c=self.client()
        r=c.post('/api/register',json={'username':'expired','password':'SyntheticTestPass2026','display_name':'expired','portal_role':'staff','invite_code':code})
        self.assertEqual(r.status_code,403)

    def test_existing_database_migrates_without_removing_chats_or_accounts(self):
        path=Path(self.folder.name)/'legacy.sqlite3'
        with sqlite3.connect(path) as c:
            c.execute('CREATE TABLE users(id TEXT PRIMARY KEY,username TEXT UNIQUE NOT NULL,display_name TEXT NOT NULL,password_hash TEXT NOT NULL,salt TEXT NOT NULL,is_admin INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL)')
            c.execute('CREATE TABLE sessions(token_hash TEXT PRIMARY KEY,owner TEXT NOT NULL,user_id TEXT,csrf TEXT NOT NULL,expires REAL NOT NULL)')
            c.execute("INSERT INTO users VALUES('legacy','legacy','Old manager','dummy','dummy',1,'2026-10-12')")
        c.close()
        store=PortalStore(path)
        with store.db() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM users').fetchone()[0],1)
            self.assertIn('is_staff',{r['name'] for r in c.execute('PRAGMA table_info(users)')})
            self.assertIn('portal_role',{r['name'] for r in c.execute('PRAGMA table_info(sessions)')})


if __name__=='__main__':unittest.main()
