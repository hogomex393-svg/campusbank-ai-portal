"""Reproduce the two group-review reports using synthetic requests only."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
import tempfile
from pathlib import Path
import unittest
import uuid
from fastapi.testclient import TestClient
from bankbot.config import Settings
from bankbot.dialogue import coerce_state
from bankbot.forms import draft_from_message
from bankbot.portal_store import PortalStore, PortalError
from bankbot.service import ChatService
from bankbot.web import create_app
from tests.test_portal import StubAgent
from tests.test_system import ScriptedClient, call


class ReviewRegressionTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.path=Path(self.folder.name)/'portal.sqlite3'
        self.bot=ChatService(Settings(api_key=''))

    def tearDown(self):self.folder.cleanup()

    def test_transfer_draft_keeps_type_and_recipient_when_only_amount_changes(self):
        first=self.bot.respond('给 Sam 模拟国际转账两千英镑',mode='offline')
        self.assertEqual(first.state.service_drafts['transfer_demo'],{'transfer_type':'international','recipient':'Sam','amount':'2000'})
        second=self.bot.respond('改成五百',first.state,mode='offline')
        self.assertEqual(second.actions[-1]['prefill'],{'transfer_type':'international','recipient':'Sam','amount':'500'})
        third=self.bot.respond('收款人改成 Amy',second.state,mode='offline')
        self.assertEqual(third.actions[-1]['prefill']['recipient'],'Amy')
        self.assertEqual(third.actions[-1]['prefill']['amount'],'500')

    def test_appointment_keeps_date_and_purpose_when_only_city_changes(self):
        first=self.bot.respond('预约伦敦，2026 年 11 月 2 日，咨询学生账户',mode='offline')
        second=self.bot.respond('改成曼彻斯特',first.state,mode='offline')
        self.assertEqual(second.actions[-1]['prefill'],{'city':'Manchester','date':'2026-11-02','purpose':'学生账户'})
        restored=coerce_state(vars(second.state))
        self.assertEqual(restored.service_drafts,second.state.service_drafts)

    def test_model_prefill_merges_with_previous_draft_and_does_not_check_consent(self):
        client=ScriptedClient([
            {'role':'assistant','content':None,'tool_calls':[call('open_service_window',{'service_id':'transfer_demo','prefill':{'transfer_type':'international','recipient':'Sam','amount':'2000'}})]},
            {'role':'assistant','content':'Review the demo transfer below.'},
            {'role':'assistant','content':None,'tool_calls':[call('open_service_window',{'service_id':'transfer_demo','prefill':{'amount':'500'}})]},
            {'role':'assistant','content':'The demo amount is now 500 GBP. Review before submitting.'}])
        bot=ChatService(Settings(api_key='test'),client)
        first=bot.respond('Prepare a simulated international transfer to Sam for GBP 2000.')
        second=bot.respond('Please change it to GBP 500.',first.state)
        self.assertEqual(second.actions[0]['prefill'],{'transfer_type':'international','recipient':'Sam','amount':'500'})
        self.assertEqual(bot.tools.execute('open_service_window',{'service_id':'open_account','prefill':{'documents_ready':True}})['ui_action']['prefill'],{})
        self.assertEqual(bot.tools.execute('open_service_window',{'service_id':'transfer_demo','prefill':{'iban':'GB-SYNTHETIC'}})['error'],'invalid_arguments')

    def test_offline_compound_materials_and_monthly_fee_are_both_answered(self):
        result=self.bot.respond('学生账户开户需要什么材料，有月费吗？',mode='offline')
        self.assertIn('在读学生证明',result.answer);self.assertIn('不收取',result.answer)

    def test_offline_compound_product_documents_and_transfer_fee(self):
        result=self.bot.respond('学生开户材料和国际转账手续费是多少？',mode='offline')
        self.assertIn('学生证明',result.answer);self.assertIn('8',result.answer)

    def test_rag_receives_all_requested_product_facts(self):
        client=ScriptedClient([{'role':'assistant','content':'Photo ID, student status and address proof are required. There is no monthly fee.'}])
        result=ChatService(Settings(api_key='test'),client).respond('Student account documents and monthly fee?',mode='rag')
        system=client.requests[0][0]['content']
        self.assertIn('no monthly',system);self.assertIn('photo',system.lower())
        self.assertIn('PRODUCT_STUDENT',result.source_ids)

    def test_comparison_has_structured_rows_and_missing_minimum_is_not_unlimited(self):
        result=self.bot.respond('比较学生账户和日常账户',mode='offline')
        self.assertIn('|',result.answer);self.assertIn('费用',result.answer);self.assertIn('3',result.answer)
        result=self.bot.respond('学生账户最低开户存款是多少？',mode='offline')
        self.assertIn('未说明',result.answer);self.assertIn('不能',result.answer)

    def test_knowledge_does_not_request_real_transfer_credentials_or_claim_app_freeze(self):
        transfer=next(r for r in self.bot.knowledge.faq if r['faq_id']=='PAY_INTERNATIONAL_DETAILS')
        self.assertIn('only',transfer['answer']);self.assertIn('Do not provide IBAN',transfer['answer'])
        lost=next(r for r in self.bot.knowledge.faq if r['faq_id']=='CARD_LOST')
        self.assertIn('cannot freeze a real card',lost['answer'])

    def test_past_date_and_whitespace_are_rejected_by_api_in_english(self):
        with TestClient(create_app(self.path,StubAgent())) as c:
            boot=c.get('/api/bootstrap').json();c.headers['X-CSRF-Token']=boot['csrf'];c.headers['Accept-Language']='en'
            user=c.post('/api/register',json={'username':'date_test','password':'SyntheticReviewPass2026','display_name':'Demo'}).json()
            c.headers['X-CSRF-Token']=user['csrf']
            data={'service_id':'branch_appointment','payload':{'city':'London','date':'2000-01-01','purpose':'Demo'},'confirmed':True}
            r=c.post('/api/requests',json=data);self.assertEqual(r.status_code,400);self.assertIn('earlier than today',r.json()['detail'])
            data['payload']['date']=boot['today'];data['payload']['purpose']='   '
            r=c.post('/api/requests',json=data);self.assertEqual(r.status_code,400);self.assertIn('complete',r.json()['detail'])

    def test_duplicate_confirmation_returns_same_receipt_under_concurrency(self):
        store=PortalStore(self.path)
        payload={'transfer_type':'international','recipient':'Sam','amount':'2000','note':''}
        key=uuid.uuid4().hex
        def submit(_):return store.submit('u:synthetic','transfer_demo',payload,request_id=key)
        with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(submit,range(4)))
        self.assertEqual(len({r['id'] for r in results}),1)
        self.assertEqual(len(store.requests('u:synthetic')),1)
        with self.assertRaises(PortalError):store.submit('u:synthetic','transfer_demo',{**payload,'amount':'500'},request_id=key)
        other=store.submit('u:another','transfer_demo',payload,request_id=key)
        self.assertNotEqual(other['id'],results[0]['id'])
        restarted=PortalStore(self.path)
        self.assertEqual(restarted.submit('u:synthetic','transfer_demo',payload,request_id=key)['id'],results[0]['id'])

    def test_catalog_all_visible_form_strings_have_english_labels(self):
        from bankbot.catalog import SERVICES
        for service in SERVICES.values():
            self.assertTrue(service['description_en']);self.assertTrue(service['notice_en'])
            for field in service['fields']:
                self.assertTrue(field['label_en'])
                for option in field['options']:self.assertTrue(option['label_en'])


if __name__=='__main__':unittest.main()
