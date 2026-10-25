"""Regression cases authored from the group's eight-page review (I01-I06)."""
from dataclasses import replace
from datetime import datetime,timezone
import json,tempfile,time,unittest,uuid
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from bankbot.config import Settings
from bankbot.dialogue import State,coerce_state
from bankbot.intent import update_constraints
from bankbot.service import ChatService
from bankbot.scenarios import transfer_quote,validate_scenario,SCENARIOS
from bankbot.web import create_app
from bankbot.consistency import conflicts
from tests.test_portal import StubAgent
from tests.test_system import ScriptedClient,call


class ReviewDialogueTests(unittest.TestCase):
    def test_numeric_quote_guard_and_currency_context_match_window(self):
        quote=transfer_quote('100','international',currency='USD')
        self.assertTrue(conflicts('预计到账 USD 117.00',{},quote));self.assertFalse(conflicts('预计到账 USD 128.00',{},quote))
        bot=ChatService(Settings());first=bot.respond('模拟国际转账100英镑，币种USD。',mode='offline')
        self.assertEqual(first.state.constraints['transfer_currency'],'USD');self.assertIn('128.00',first.answer)
        self.assertEqual(first.actions[0]['scenario_prefill']['payee_profile'],'us_demo')
        second=bot.respond('改成五百英镑',first.state,'offline');self.assertEqual(second.state.constraints['transfer_currency'],'USD')

    def test_short_missing_slot_and_english_edit_preserve_known_fields(self):
        bot=ChatService(Settings());first=bot.respond('Simulate an international transfer of GBP 100.',mode='offline')
        second=bot.respond('Sam',first.state,'offline')
        self.assertEqual(second.state.service_drafts['transfer_demo']['recipient'],'Sam')
        third=bot.respond('Change the amount to 500.',second.state,'offline')
        self.assertEqual(third.state.service_drafts['transfer_demo'],{'transfer_type':'international','recipient':'Sam','amount':'500'})
        self.assertEqual([f['name'] for f in third.actions[0]['changed_fields']],['amount'])
        self.assertNotIn('Sam',third.answer);self.assertIn('508.00',third.answer)

    def test_I01_chat_quote_and_preview_use_identical_calculator(self):
        bot=ChatService(Settings())
        first=bot.respond('给 Alex 模拟国际转账 100 英镑',mode='offline')
        second=bot.respond('我说的是国际转账，转 100 英镑，一共扣多少？',first.state,'offline')
        quote=next(t['result']['quote'] for t in second.tools if t['name']=='get_transfer_quote')
        values={f['name']:f['default'] for f in SCENARIOS['transfer_demo']['fields']}|{'payee_profile':'europe_demo','payee_name':'Example EU College','declaration':True}
        preview=validate_scenario('transfer_demo',values,{'transfer_type':'international','recipient':'Alex','amount':'100','note':''})
        self.assertEqual(quote,preview['quote']);self.assertIn('108.00',second.answer);self.assertIn('117.00',second.answer)
        self.assertNotIn('不在',second.answer);self.assertEqual(second.sources[0]['id'],'DEMO_TRANSFER_QUOTE')

    def test_I01_streamed_capability_contradiction_is_repaired_before_save(self):
        client=ScriptedClient([{'role':'assistant','content':'汇率换算 FX 不在本地演示范围内。'},
            {'role':'assistant','content':'本金 GBP 100.00、手续费 GBP 8.00，总扣款 GBP 108.00。固定演示汇率 1 GBP = 1.17 EUR，预计到账 EUR 117.00；不是真实换汇。'}])
        reply=ChatService(Settings(api_key='synthetic'),client).respond('模拟国际转账100英镑，一共扣多少？')
        self.assertEqual(reply.consistency_corrections,1);self.assertEqual(reply.api_calls,2)
        self.assertEqual(reply.state.turns[-1][-1]['content'],reply.answer)
        self.assertIn('117.00',reply.answer)

    def test_I02_negation_and_reversal_are_explicit_persistent_constraints(self):
        for text in ('我不想借钱，只看不用偿还的资助','不要贷款，想看奖学金','I do not want loans, only grants','Show non-repayable funding'):
            self.assertTrue(update_constraints(text).get('exclude_loan'),text)
        self.assertFalse(update_constraints('贷款也可以看看',{'exclude_loan':True})['exclude_loan'])
        self.assertFalse(update_constraints('Actually include loans too',{'exclude_loan':True})['exclude_loan'])

    def test_I02_original_reproduction_has_only_nonloan_button_and_single_select(self):
        bot=ChatService(Settings());state=State(bank_mode='student')
        reply=bot.respond('我不想借钱，只看不用偿还的资助，帮我打开合适的窗口，学习阶段选本科。',state,'offline')
        self.assertEqual([a['service_id'] for a in reply.actions],['funding_enquiry'])
        self.assertEqual(reply.actions[0]['prefill']['study_level'],'undergraduate')
        self.assertNotIn('DEMO_EDUCATION_LOAN',reply.source_ids)
        next_=bot.respond('那需要什么材料？',reply.state,'offline')
        self.assertTrue(next_.state.constraints['exclude_loan']);self.assertNotIn('education_loan',[a['service_id'] for a in next_.actions])
        reversed_=bot.respond('贷款也可以看看',next_.state,'offline')
        self.assertFalse(reversed_.state.constraints['exclude_loan']);self.assertIn('education_loan',[a['service_id'] for a in reversed_.actions])

    def test_I02_model_cannot_open_excluded_loan(self):
        client=ScriptedClient([{'role':'assistant','content':None,'tool_calls':[call('open_service_window',{'service_id':'education_loan'})]},
            {'role':'assistant','content':'可以查看无需偿还的奖学金和补助，资助类型选择一个类别或全部项目。'}])
        reply=ChatService(Settings(api_key='synthetic'),client).respond('不要贷款，只想看奖学金补助，本科，帮我打开窗口。',State(bank_mode='student'))
        self.assertEqual(reply.tools[0]['result']['error'],'excluded_by_user')
        self.assertEqual([a['service_id'] for a in reply.actions],['funding_enquiry'])
        self.assertEqual(reply.actions[0]['prefill']['funding_type'],'all')

    def test_I03_lost_card_followups_do_not_jump_to_accounts_or_loans(self):
        bot=ChatService(Settings())
        first=bot.respond('我的银行卡丢了，怎么办？',mode='offline')
        second=bot.respond('补办要多少钱？现在已经冻结了吗？',first.state,'offline')
        self.assertTrue(second.followups)
        self.assertIn('replace_card',[a['service_id'] for a in first.actions])
        self.assertFalse(any('账户' in q or '贷款' in q or 'savings' in q for q in second.followups))
        self.assertTrue(all(any(w in q for w in ('挂失','补卡','冻结','这项','这项请求')) for q in second.followups))

    def test_I03_rag_retrieves_only_requested_products_and_readable_versions(self):
        client=ScriptedClient([{'role':'assistant','content':'The student account has no monthly fee and requires student status from age 18.'}])
        reply=ChatService(Settings(api_key='synthetic'),client).respond('What are the student account fees and eligibility?',mode='rag')
        self.assertNotIn('CARD_CREDIT_FEES',reply.source_ids);self.assertNotIn('LOAN_ELIGIBILITY',reply.source_ids)
        self.assertTrue(reply.sources);self.assertTrue(all(len(s['version'])==12 and s['title'] for s in reply.sources))
        self.assertTrue(any('student' in s['title_en'].lower() for s in reply.sources))


class ReviewPortalTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'portal.sqlite3';self.settings=Settings(open_staff_testing=True)
        with patch('bankbot.web.Settings.load',return_value=self.settings):self.app=create_app(self.path,StubAgent())
        self.clients=[];self.customer=self.client();self.register(self.customer,'review_customer')
    def tearDown(self):
        for c in self.clients:c.close()
        self.tmp.cleanup()
    def client(self,app=None,base='http://testserver'):
        c=TestClient(app or self.app,base_url=base);self.clients.append(c);b=c.get('/api/bootstrap').json();c.headers['X-CSRF-Token']=b['csrf'];return c
    def register(self,c,name):
        r=c.post('/api/register',json={'username':name,'display_name':'Demo','password':'SyntheticReviewPass2026'});self.assertEqual(r.status_code,200,r.text);c.headers['X-CSRF-Token']=r.json()['csrf']
    def staff(self):
        c=self.client();r=c.post('/api/testing/staff-session').json();c.headers['X-CSRF-Token']=r['csrf'];return c
    def request(self):
        return self.customer.post('/api/requests',json={'service_id':'open_account','payload':{'product':'everyday_account','applicant':'Demo','channel':'online','documents_ready':True},'confirmed':True}).json()

    def test_feedback_is_owned_saved_once_and_survives_reload(self):
        chat=self.customer.post('/api/chats').json()['id'];reply=self.customer.post('/api/chats/'+chat+'/messages',json={'text':'开户'}).json();message=reply['messages'][-1]['id']
        route=f'/api/chats/{chat}/messages/{message}/feedback';body={'helpful':False,'reason':'misunderstood','comment':'Synthetic feedback'}
        self.assertEqual(self.customer.post(route,json=body).status_code,200)
        other=self.client();self.assertEqual(other.post(route,json=body).status_code,404)
        body.update(helpful=True,reason='helpful');self.assertEqual(self.customer.post(route,json=body).status_code,200)
        message=self.customer.get('/api/chats/'+chat).json()['messages'][-1]
        self.assertTrue(message['feedback']['helpful'])
        with self.app.state.store.db() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM answer_feedback').fetchone()[0],1)

    def test_original_request_supplement_keeps_id_and_revision_then_withdraws(self):
        receipt=self.request();id_=receipt['id'];staff=self.staff()
        staff.patch('/api/admin/requests/'+id_,json={'status':'needs_info','note':'Add the demo applicant name.'})
        body={'action':'supplement','payload':receipt['payload']|{'applicant':'Revised Demo'},'request_id':uuid.uuid4().hex}
        r=self.customer.post('/api/requests/'+id_+'/action',json=body)
        self.assertEqual(r.status_code,200,r.text);self.assertEqual(r.json()['id'],id_);self.assertEqual(r.json()['status'],'pending')
        self.assertEqual(self.customer.post('/api/requests/'+id_+'/action',json=body).json(),r.json())
        other=self.client();self.assertEqual(other.post('/api/requests/'+id_+'/action',json=body).status_code,404)
        own=self.customer.get('/api/requests/'+id_).json();self.assertEqual(own['payload']['applicant'],'Revised Demo');self.assertEqual(len(own['events']),2)
        with self.app.state.store.db() as db:
            revision=db.execute('SELECT before_json,after_json FROM request_revisions WHERE request_id=?',(id_,)).fetchone()
        self.assertEqual(json.loads(revision[0])['payload']['applicant'],'Demo')
        result=self.customer.post('/api/requests/'+id_+'/action',json={'action':'withdraw','request_id':uuid.uuid4().hex})
        self.assertEqual(result.json()['status'],'cancelled')
        self.assertEqual(staff.patch('/api/admin/requests/'+id_,json={'status':'completed','note':'Late review'}).status_code,409)
        self.assertEqual(len(self.customer.get('/api/requests').json()),1)

    def test_archive_is_reversible_not_deletion_and_owner_only(self):
        chat=self.customer.post('/api/chats').json()['id'];route='/api/chats/'+chat+'/archive'
        self.assertEqual(self.customer.patch(route,json={'archived':True}).status_code,200)
        self.assertEqual(self.customer.get('/api/chats').json(),[]);self.assertEqual(len(self.customer.get('/api/chats?archived=true').json()),1)
        self.assertEqual(self.customer.get('/api/chats/'+chat).status_code,200)
        other=self.client();self.assertEqual(other.patch(route,json={'archived':False}).status_code,404)
        self.customer.patch(route,json={'archived':False});self.assertEqual(len(self.customer.get('/api/chats').json()),1)
        receipt=self.request();id_=receipt['id'];self.assertEqual(self.customer.patch('/api/requests/'+id_+'/archive',json={'archived':True}).status_code,409)
        staff=self.staff();staff.patch('/api/admin/requests/'+id_,json={'status':'completed','note':'Synthetic demo reviewed.'})
        self.assertEqual(self.customer.patch('/api/requests/'+id_+'/archive',json={'archived':True}).status_code,200)
        self.assertEqual(self.customer.get('/api/requests').json(),[]);self.assertEqual(len(self.customer.get('/api/requests?archived=true').json()),1)
        self.assertEqual(self.customer.get('/api/requests/'+id_).status_code,200)

    def test_I04_demo_allowance_retains_global_and_hourly_caps(self):
        settings=replace(self.settings,cloud_mode=True,public_url='https://campusbank.example',bootstrap_code='synthetic-bootstrap-long-secret',test_access_code='synthetic-team-code',demo_accounts=('class_demo',),demo_rpm=18,hourly_requests=8)
        with patch('bankbot.web.Settings.load',return_value=settings):app=create_app(Path(self.tmp.name)/'cloud.sqlite3',StubAgent())
        c=self.client(app,settings.public_url)
        r=c.post('/api/register',json={'username':'class_demo','display_name':'Classroom demo','password':'SyntheticReviewPass2026','test_access_code':settings.test_access_code}).json();c.headers['X-CSRF-Token']=r['csrf']
        chat=c.post('/api/chats').json()['id'];self.assertEqual(c.get('/api/bootstrap').json()['limits']['account_per_minute'],18)
        for i in range(8):self.assertEqual(c.post('/api/chats/'+chat+'/messages',json={'text':str(i)}).status_code,200)
        body={'text':'retry','request_id':uuid.uuid4().hex};limited=c.post('/api/chats/'+chat+'/messages',json=body)
        self.assertEqual(limited.status_code,429);self.assertGreater(limited.json()['retry_after'],60)
        with patch('bankbot.web.time.time',return_value=time.time()+3601):self.assertEqual(c.post('/api/chats/'+chat+'/messages',json=body).status_code,200)

    def test_I04_twenty_minute_classroom_pace_with_simulated_clock(self):
        settings=replace(self.settings,cloud_mode=True,public_url='https://campusbank.example',bootstrap_code='synthetic-bootstrap-long-secret',test_access_code='synthetic-team-code',demo_accounts=('paced_demo',),demo_rpm=18,hourly_requests=240)
        with patch('bankbot.web.Settings.load',return_value=settings):app=create_app(Path(self.tmp.name)/'paced.sqlite3',StubAgent())
        c=self.client(app,settings.public_url);r=c.post('/api/register',json={'username':'paced_demo','display_name':'Demo','password':'SyntheticReviewPass2026','test_access_code':settings.test_access_code}).json();c.headers['X-CSRF-Token']=r['csrf']
        chat=c.post('/api/chats').json()['id'];start=time.time()
        for minute in range(20):
            for question in range(8):
                with patch('bankbot.web.time.time',return_value=start+minute*60+question*7):response=c.post('/api/chats/'+chat+'/messages',json={'text':'Synthetic classroom question'})
                self.assertEqual(response.status_code,200)
        self.assertEqual(len(c.get('/api/chats/'+chat).json()['messages']),320)
