"""Dual banking, reversible open staff testing and the application workbench."""
from dataclasses import replace
import json,os,tempfile,unittest,uuid
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from bankbot.config import Settings
from bankbot.dialogue import State
from bankbot.llm_client import DeepSeekClient
from bankbot.service import ChatService
from bankbot.web import create_app
from tests.test_portal import StubAgent
from tests.test_system import ScriptedClient,call


class DualBankingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.database=Path(self.tmp.name)/'portal.sqlite3'
        self.settings=Settings(api_key='',open_staff_testing=True)
        self.clients=[]
        with patch('bankbot.web.Settings.load',return_value=self.settings):self.app=create_app(self.database,StubAgent())

    def tearDown(self):
        for c in self.clients:c.close()
        self.tmp.cleanup()

    def client(self,app=None):
        c=TestClient(app or self.app);self.clients.append(c)
        b=c.get('/api/bootstrap').json();c.headers['X-CSRF-Token']=b['csrf'];return c

    def register(self,c,name,role='customer'):
        r=c.post('/api/register',json={'username':name,'display_name':name,'password':'SyntheticDualBankPass2026','portal_role':role})
        self.assertEqual(r.status_code,200,r.text);d=r.json();c.headers['X-CSRF-Token']=d['csrf'];return d

    def test_mode_switch_creates_separate_retained_conversations(self):
        c=self.client();general=c.post('/api/chats',json={'bank_mode':'general'}).json();student=c.post('/api/chats',json={'bank_mode':'student'}).json()
        self.assertEqual(student['bank_mode'],'student');self.assertEqual(general['bank_mode'],'general')
        c.post('/api/chats/'+student['id']+'/messages',json={'text':'student help','bank_mode':'student'})
        self.assertEqual(c.get('/api/chats/'+student['id']).json()['bank_mode'],'student')
        self.assertEqual(len(c.get('/api/chats').json()),2)
        self.assertEqual(c.post('/api/chats',json={'bank_mode':'other'}).status_code,422)

    def test_student_records_are_fictional_and_never_inherit_personal_loan_apr(self):
        bot=ChatService(Settings(api_key=''))
        answer=bot.respond('助学贷款利率和还款怎么办？',State(bank_mode='student'),'offline')
        self.assertIn('演示',answer.answer);self.assertIn('审核',answer.answer);self.assertNotIn('8%',answer.answer)
        self.assertIn('DEMO_EDUCATION_LOAN',answer.source_ids)
        self.assertEqual(answer.actions[0]['service_id'],'education_loan')
        grants=bot.respond('奖学金和助学补助有哪些？',State(bank_mode='student'),'offline')
        self.assertIn('DEMO_MERIT_SCHOLARSHIP',grants.source_ids);self.assertIn('DEMO_NEED_GRANT',grants.source_ids)
        rows=self.client().get('/api/student-funding?level=postgraduate&kind=scholarship').json()
        self.assertTrue(rows['fictional']);self.assertEqual(len(rows['programs']),1)

    def test_followups_are_contextual_unique_and_in_turn_language(self):
        bot=ChatService(Settings(api_key=''))
        first=bot.respond('助学贷款需要哪些材料？',State(bank_mode='student'),'offline')
        self.assertGreaterEqual(len(first.followups),2);self.assertEqual(len(first.followups),len(set(first.followups)))
        self.assertNotIn('助学贷款需要哪些材料？',first.followups)
        second=bot.respond('What about student loan repayment?',first.state,'offline')
        self.assertTrue(all('?' in q for q in second.followups))
        human=bot.respond('转人工客服',first.state,'offline');self.assertEqual(human.followups,[])

    def test_tool_call_explanation_is_visible_once_without_reasoning_or_tool_json(self):
        explanation='日常账户每月收取3英镑，要求年满18岁。需要照片身份证明和地址证明。提交后可以在我的办理记录查看进度。'
        client=ScriptedClient([
            {'role':'assistant','content':explanation,'reasoning_content':'INTERNAL_TRACE_NOT_FOR_DISPLAY','tool_calls':[call('open_service_window',{'service_id':'open_account'})]},
            {'role':'assistant','content':'开户窗口已准备好，请核对后确认。'}])
        result=ChatService(Settings(api_key='test'),client).respond('请说明日常开户费用、材料和进度。')
        self.assertIn(explanation,result.answer);self.assertEqual(result.answer.count(explanation),1)
        self.assertIn('窗口已准备',result.answer);self.assertNotIn('INTERNAL_TRACE',result.answer);self.assertNotIn('tool_call_id',result.answer)
        self.assertEqual(result.state.turns[-1][-1]['content'],result.answer)
        self.assertIsNone(result.state.turns[-1][1]['content'])

    def test_open_test_staff_is_not_admin_and_sessions_revoke_when_disabled(self):
        staff=self.client();r=staff.post('/api/testing/staff-session',json={});self.assertEqual(r.status_code,200)
        data=r.json();staff.headers['X-CSRF-Token']=data['csrf']
        self.assertEqual(data['portal_role'],'staff');self.assertFalse(data['user']['is_admin']);self.assertTrue(data['user']['is_staff'])
        self.assertEqual(staff.get('/api/admin/requests').status_code,200)
        self.assertEqual(staff.post('/api/admin/staff-invites').status_code,403)
        self.assertEqual(staff.post('/api/admin/import-legacy').status_code,403)
        with patch('bankbot.web.Settings.load',return_value=replace(self.settings,open_staff_testing=False)):
            closed=create_app(self.database,StubAgent())
        other=self.client(closed);other.cookies.update(staff.cookies)
        self.assertEqual(other.get('/api/admin/requests').status_code,401)
        closed_guest=self.client(closed);self.assertEqual(closed_guest.post('/api/testing/staff-session',json={}).status_code,403)
        with self.app.state.store.db() as db:
            user=db.execute('SELECT is_admin,is_staff FROM users WHERE id=?',(data['user']['id'],)).fetchone()
        self.assertEqual(tuple(user),(0,0))

    def test_staff_registration_needs_no_invite_but_passwords_are_not_bypassed(self):
        c=self.client();data=self.register(c,'test_worker','staff');self.assertTrue(data['testing_staff']);self.assertFalse(data['user']['is_admin'])
        out=c.post('/api/logout');c.headers['X-CSRF-Token']=out.json()['csrf']
        self.assertEqual(c.post('/api/login',json={'username':'test_worker','password':'WrongSyntheticPassword','portal_role':'staff'}).status_code,401)
        r=c.post('/api/login',json={'username':'test_worker','password':'SyntheticDualBankPass2026','portal_role':'staff'});self.assertEqual(r.status_code,200)

    def test_application_forms_reach_staff_and_review_reaches_only_owner(self):
        customer=self.client();self.register(customer,'customer_one')
        other=self.client();self.register(other,'customer_two')
        chat=customer.post('/api/chats',json={'bank_mode':'student'}).json()['id']
        body={'service_id':'education_loan','payload':{'applicant':'Demo applicant','institution':'Example College','study_level':'undergraduate','amount':'2500','purpose':'Fictional tuition budget','reviewed':True},'confirmed':True,'chat_id':chat}
        receipt=customer.post('/api/requests',json=body);self.assertEqual(receipt.status_code,200,receipt.text);id_=receipt.json()['id']
        self.assertEqual(customer.get('/api/admin/requests').status_code,403)
        self.assertEqual(other.get('/api/admin/requests/'+id_).status_code,403)
        staff=self.client();login=staff.post('/api/testing/staff-session',json={}).json();staff.headers['X-CSRF-Token']=login['csrf']
        row=staff.get('/api/admin/requests/'+id_).json();self.assertEqual(row['payload']['amount'],'2500');self.assertEqual(row['bank_mode'],'student')
        self.assertEqual(staff.patch('/api/admin/requests/'+id_,json={'status':'needs_info','note':''}).status_code,400)
        note='Please provide a fictional budget summary.'
        r=staff.patch('/api/admin/requests/'+id_,json={'status':'needs_info','note':note});self.assertEqual(r.status_code,200)
        self.assertEqual(len(r.json()['events']),1)
        own=customer.get('/api/requests').json()[0];self.assertEqual(own['staff_note'],note);self.assertEqual(own['status'],'needs_info')
        self.assertEqual(other.get('/api/requests').json(),[])
        self.assertEqual(customer.patch('/api/admin/requests/'+id_,json={'status':'completed','note':'wrong role'}).status_code,403)

    def test_larger_budget_and_qwen_key_isolation(self):
        self.assertGreaterEqual(Settings().max_tokens,1400)
        with patch('bankbot.config.read_env',return_value={}),patch.dict(os.environ,{'LLM_PROVIDER':'qwen','DEEPSEEK_API_KEY':'synthetic-deepseek-secret'},clear=True):
            settings=Settings.load()
        self.assertEqual(settings.api_key,'');self.assertEqual(settings.provider,'qwen');self.assertIn('qwen',settings.model)

    def test_provider_payloads_do_not_send_foreign_thinking_options(self):
        import io
        def response():return io.BytesIO(json.dumps({'choices':[{'message':{'role':'assistant','content':'A helpful answer.'}}],'usage':{}}).encode())
        for provider in ('deepseek','qwen','openai_compatible'):
            with patch('bankbot.llm_client.urlopen',return_value=response()) as opened:
                DeepSeekClient(Settings(api_key='synthetic',provider=provider)).complete([{'role':'assistant','content':'prior','reasoning_content':'private provider trace'},{'role':'user','content':'question'}])
                payload=json.loads(opened.call_args[0][0].data)
            self.assertEqual('thinking' in payload,provider=='deepseek')
            self.assertEqual('enable_thinking' in payload,provider=='qwen')
            if provider!='deepseek':self.assertNotIn('reasoning_content',payload['messages'][0])


if __name__=='__main__':unittest.main()
