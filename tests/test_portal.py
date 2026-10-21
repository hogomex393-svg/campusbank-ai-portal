"""Integration tests for authentication, ownership, workflows and human handoff."""
import json
import tempfile
import unittest
import uuid
from pathlib import Path
from fastapi.testclient import TestClient
from bankbot.web import create_app
from bankbot.service import Reply
from bankbot.dialogue import coerce_state
from bankbot.catalog import service_action
from bankbot.config import Settings
from bankbot.service import ChatService
from tests.test_system import ScriptedClient,call


class StubAgent:
    def __init__(self):self.calls=0
    def respond(self,text,state,mode):
        self.calls+=1;state=coerce_state(state)
        state.turns.append([{'role':'user','content':text},{'role':'assistant','content':'可以进入开户窗口核对信息。'}])
        return Reply('可以进入开户窗口核对信息。',state,'agent',language='zh',actions=[service_action('open_account')])


class PortalTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.bot=StubAgent()
        self.app=create_app(Path(self.folder.name)/'portal.sqlite3',self.bot)
        self.client=TestClient(self.app);self.bootstrap(self.client)

    def tearDown(self):self.client.close();self.folder.cleanup()
    def bootstrap(self,c):
        b=c.get('/api/bootstrap').json();c.headers['X-CSRF-Token']=b['csrf'];return b
    def register(self,c,name='student',display='学生用户',role='customer'):
        r=c.post('/api/register',json={'username':name,'password':'TestOnlyPass2026','display_name':display,'portal_role':role})
        self.assertEqual(r.status_code,200,r.text);c.headers['X-CSRF-Token']=r.json()['csrf'];return r.json()['user']
    def chat(self,c):return c.post('/api/chats').json()['id']

    def test_bootstrap_and_static_assets(self):
        b=self.bootstrap(self.client)
        self.assertEqual(len(b['categories']),7)
        self.assertEqual(len(b['services']),11)
        self.assertEqual(self.client.get('/').status_code,200)
        self.assertEqual(self.client.get('/assets/app.js').status_code,200)

    def test_registration_hashes_password_and_session_cookie(self):
        client=TestClient(self.app);r=client.get('/api/bootstrap')
        self.assertIn('HttpOnly',r.headers['set-cookie']);self.assertIn('SameSite=strict',r.headers['set-cookie'])
        client.headers['X-CSRF-Token']=r.json()['csrf'];user=self.register(client)
        with self.app.state.store.db() as db:
            row=db.execute('SELECT password_hash,salt FROM users WHERE id=?',(user['id'],)).fetchone()
        self.assertNotEqual(row['password_hash'],'TestOnlyPass2026');self.assertEqual(len(row['salt']),32)
        self.assertNotIn('password_hash',json.dumps(client.get('/api/bootstrap').json()))
        client.close()

    def test_history_survives_new_conversation_and_idempotent_send(self):
        first=self.chat(self.client);rid=uuid.uuid4().hex
        payload={'text':'学生开户','request_id':rid}
        r=self.client.post(f'/api/chats/{first}/messages',json=payload)
        self.assertEqual(len(r.json()['messages']),2)
        self.assertTrue(r.json()['messages'][-1]['metadata']['actions'])
        self.client.post(f'/api/chats/{first}/messages',json=payload)
        self.assertEqual(self.bot.calls,1)
        second=self.chat(self.client)
        self.assertNotEqual(first,second)
        self.assertEqual(len(self.client.get('/api/chats').json()),2)
        self.assertEqual(len(self.client.get('/api/chats/'+first).json()['messages']),2)

    def test_login_claims_guest_chat_and_logout_hides_it(self):
        first=self.chat(self.client);self.register(self.client)
        self.assertEqual(self.client.get('/api/chats/'+first).status_code,200)
        r=self.client.post('/api/logout');self.client.headers['X-CSRF-Token']=r.json()['csrf']
        self.assertEqual(self.client.get('/api/chats/'+first).status_code,404)
        r=self.client.post('/api/login',json={'username':'student','password':'TestOnlyPass2026'})
        self.assertEqual(r.status_code,200);self.client.headers['X-CSRF-Token']=r.json()['csrf']
        self.assertEqual(self.client.get('/api/chats/'+first).status_code,200)

    def test_accounts_are_isolated_and_admin_is_not_self_assignable(self):
        self.register(self.client,'first');id_=self.chat(self.client)
        other=TestClient(self.app);self.bootstrap(other);user=self.register(other,'second')
        self.assertFalse(user['is_admin'])
        self.assertEqual(other.get('/api/chats/'+id_).status_code,404)
        self.assertEqual(other.get('/api/admin/tickets').status_code,403)
        self.assertEqual(other.patch('/api/chats/'+id_,json={'title':'steal'}).status_code,404)
        other.close()

    def test_csrf_and_cross_origin_rejected(self):
        self.assertEqual(self.client.post('/api/chats',headers={'X-CSRF-Token':'wrong'}).status_code,403)
        self.assertEqual(self.client.post('/api/chats',headers={'Origin':'https://evil.example'}).status_code,403)

    def test_requests_require_login_confirmation_and_valid_values(self):
        body={'service_id':'transfer_demo','payload':{'transfer_type':'domestic','recipient':'Demo recipient','amount':'15','note':''},'confirmed':True}
        self.assertEqual(self.client.post('/api/requests',json=body).status_code,401)
        self.register(self.client)
        body['confirmed']=False;self.assertEqual(self.client.post('/api/requests',json=body).status_code,400)
        body['confirmed']=True;body['payload']['amount']='NaN'
        self.assertEqual(self.client.post('/api/requests',json=body).status_code,400)
        body['payload']['amount']='15.00';r=self.client.post('/api/requests',json=body)
        self.assertEqual(r.status_code,200);self.assertTrue(r.json()['demo'])
        self.assertEqual(len(self.client.get('/api/requests').json()),1)

    def test_all_catalog_service_forms_can_submit_demo_records(self):
        self.register(self.client)
        from bankbot.catalog import SERVICES
        for id_,service in SERVICES.items():
            payload={}
            for f in service['fields']:
                payload[f['name']]=True if f['type']=='checkbox' else f['options'][0]['value'] if f['type']=='select' else '100.00' if f['type']=='number' else '2026-12-01' if f['type']=='date' else '演示填写内容'
            r=self.client.post('/api/requests',json={'service_id':id_,'payload':payload,'confirmed':True})
            self.assertEqual(r.status_code,200,(id_,r.text))
        self.assertEqual(len(self.client.get('/api/requests').json()),11)

    def test_human_queue_and_actual_staff_reply(self):
        admin=self.register(self.client,'staff','演示工作人员',role='staff')
        customer=TestClient(self.app);self.bootstrap(customer);self.register(customer,'customer','演示客户')
        chat=self.chat(customer)
        r=customer.post('/api/requests',json={'service_id':'human_support','payload':{'category':'cards','subject':'补卡协助','description':'需要工作人员帮助'},'chat_id':chat,'confirmed':True})
        self.assertEqual(r.status_code,200);ticket=r.json()['id']
        self.assertEqual(customer.get('/api/chats/'+chat).json()['ticket']['status'],'waiting')
        customer.post('/api/chats/'+chat+'/messages',json={'text':'请帮助我','request_id':uuid.uuid4().hex})
        self.assertEqual(self.bot.calls,0)
        r=self.client.post('/api/admin/tickets/'+ticket+'/reply',json={'text':'人工回复：已查看你的演示请求。'})
        self.assertEqual(r.status_code,200)
        messages=customer.get('/api/chats/'+chat).json()['messages']
        self.assertEqual(messages[-1]['metadata']['sender'],'staff')
        self.assertIn('人工回复',messages[-1]['content'])
        self.assertEqual(customer.post('/api/tickets/'+ticket+'/resume-ai').status_code,200)
        customer.post('/api/chats/'+chat+'/messages',json={'text':'继续咨询','request_id':uuid.uuid4().hex})
        self.assertEqual(self.bot.calls,1);customer.close()

    def test_ticket_access_and_incorrect_credentials(self):
        self.register(self.client,'staff',role='staff');customer=TestClient(self.app);self.bootstrap(customer);self.register(customer,'customer')
        body={'service_id':'human_support','payload':{'category':'other','subject':'测试','description':'测试描述'},'confirmed':True}
        id_=customer.post('/api/requests',json=body).json()['id']
        outsider=TestClient(self.app);self.bootstrap(outsider);self.register(outsider,'outside')
        self.assertEqual(outsider.post('/api/tickets/'+id_+'/resume-ai').status_code,404)
        r=outsider.post('/api/logout');outsider.headers['X-CSRF-Token']=r.json()['csrf']
        self.assertEqual(outsider.post('/api/login',json={'username':'outside','password':'WrongPassword2026'}).status_code,401)
        customer.close();outsider.close()

    def test_service_window_tool_is_allowlisted_and_does_not_submit(self):
        client=ScriptedClient([{'role':'assistant','content':None,'tool_calls':[call('open_service_window',{'service_id':'open_account'})]},
                               {'role':'assistant','content':'点击开户窗口继续。'}])
        service=ChatService(Settings(api_key='test'),client)
        r=service.respond('学生账户怎么在网上办理？')
        self.assertEqual(r.actions[0]['service_id'],'open_account')
        self.assertIn('unknown_service',service.tools.execute('open_service_window',{'service_id':'https://evil.example'})['error'])


if __name__=='__main__':unittest.main()
