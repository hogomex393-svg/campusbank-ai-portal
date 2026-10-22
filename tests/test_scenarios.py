"""Realistic fictional forms, canonical quotes, role boundaries and old-record migration."""
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
import uuid
from contextlib import closing
from datetime import date,timedelta
from unittest.mock import patch
from fastapi.testclient import TestClient
from bankbot.config import Settings
from bankbot.portal_store import PortalStore,PortalError
from bankbot.scenarios import SCENARIOS,validate_scenario
from bankbot.web import create_app
from tests.test_portal import StubAgent


def transfer():return {'transfer_type':'domestic','recipient':'Demo Alex','amount':'100.00','note':'Fictional rent'}
def account(student=False):return {'product':'student_account' if student else 'everyday_account','applicant':'Demo','channel':'online','documents_ready':True}
def scenario(service):return {f['name']:f['default'] for f in SCENARIOS[service]['fields']} | {'declaration':True}


class ScenarioTests(unittest.TestCase):
    def test_domestic_quote_is_canonical_and_does_not_move_balance(self):
        details=scenario('transfer_demo');quote=validate_scenario('transfer_demo',details,transfer())['quote']
        self.assertEqual(quote['total'],'100.00');self.assertEqual(quote['estimated_after'],'2400.00')
        self.assertEqual(quote['receive_amount'],'100.00');self.assertTrue(quote['fictional'])
        self.assertEqual(validate_scenario('transfer_demo',details,transfer())['quote'],quote)

    def test_international_quote_uses_decimal_fictional_rate_and_fee(self):
        details=scenario('transfer_demo')|{'payee_profile':'europe_demo','payee_name':'Example EU College'}
        result=validate_scenario('transfer_demo',details,transfer()|{'transfer_type':'international','amount':'100.05'})
        self.assertEqual(result['quote']['fee'],'8.00');self.assertEqual(result['quote']['total'],'108.05')
        self.assertEqual(result['quote']['receive_amount'],'117.06');self.assertEqual(result['quote']['receive_currency'],'EUR')

    def test_name_mismatch_blocked_and_close_match_needs_separate_confirmation(self):
        details=scenario('transfer_demo')|{'payee_name':'Wrong Person'}
        with self.assertRaisesRegex(ValueError,'名称不匹配'):validate_scenario('transfer_demo',details,transfer())
        details['payee_name']='Alex Morga'
        preview=validate_scenario('transfer_demo',details,transfer(),confirm=False)
        self.assertEqual(preview['payee_match'],'close')
        with self.assertRaisesRegex(ValueError,'细微差异'):validate_scenario('transfer_demo',details,transfer())
        details['payee_ack']=True
        self.assertEqual(validate_scenario('transfer_demo',details,transfer())['payee_match'],'close')

    def test_balance_includes_fee_and_payee_type_must_match(self):
        details=scenario('transfer_demo')|{'payee_profile':'europe_demo','payee_name':'Example EU College'}
        with self.assertRaisesRegex(ValueError,'类型不一致'):validate_scenario('transfer_demo',details,transfer())
        with self.assertRaisesRegex(ValueError,'余额不足'):validate_scenario('transfer_demo',details,transfer()|{'transfer_type':'international','amount':'2495'})

    def test_scheduling_requires_valid_future_date_and_now_clears_old_date(self):
        details=scenario('transfer_demo')|{'execution':'scheduled','execution_date':'2026-02-30'}
        with self.assertRaisesRegex(ValueError,'日期格式'):validate_scenario('transfer_demo',details,transfer())
        details['execution_date']='2000-01-01'
        with self.assertRaisesRegex(ValueError,'早于今天'):validate_scenario('transfer_demo',details,transfer())
        details['execution_date']=(date.today()+timedelta(days=2)).isoformat()
        self.assertEqual(validate_scenario('transfer_demo',details,transfer())['details']['execution_date'],details['execution_date'])
        details['execution']='now'
        self.assertEqual(validate_scenario('transfer_demo',details,transfer())['details']['execution_date'],'')

    def test_student_eligibility_and_missing_documents(self):
        details=scenario('open_account')
        with self.assertRaisesRegex(ValueError,'学生账户'):validate_scenario('open_account',details,account(True))
        details.update(profile='student_demo',employment='student',student_document='missing')
        result=validate_scenario('open_account',details,account(True))
        self.assertTrue(result['needs_info']);self.assertEqual(result['missing_fields'],['student_document'])
        self.assertIn('Jamie Demo',json.dumps(result));self.assertIn('example.invalid',json.dumps(result))

    def test_unknown_real_account_fields_and_unconfirmed_scenario_rejected(self):
        details=scenario('transfer_demo')|{'account_number':'do-not-store'}
        with self.assertRaisesRegex(ValueError,'未知字段'):validate_scenario('transfer_demo',details,transfer())
        details=scenario('transfer_demo')|{'declaration':False}
        with self.assertRaisesRegex(ValueError,'核对声明'):validate_scenario('transfer_demo',details,transfer())


class ScenarioPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.path=Path(self.folder.name)/'portal.sqlite3'
        with patch('bankbot.web.Settings.load',return_value=Settings(open_staff_testing=True)):
            self.app=create_app(self.path,StubAgent())
        self.client=TestClient(self.app);self.boot(self.client)
        user=self.client.post('/api/register',json={'username':'scenario_customer','password':'SyntheticFormPass2026','display_name':'Demo'}).json()
        self.client.headers['X-CSRF-Token']=user['csrf']
    def boot(self,c):c.headers['X-CSRF-Token']=c.get('/api/bootstrap').json()['csrf']
    def tearDown(self):self.client.close();self.folder.cleanup()

    def test_preview_is_read_only_final_checks_consents_and_staff_gets_full_record(self):
        values=scenario('open_account')|{'identity_document':'missing','declaration':False}
        body={'service_id':'open_account','payload':account(),'scenario':values}
        preview=self.client.post('/api/scenarios/preview',json=body)
        self.assertEqual(preview.status_code,200);self.assertTrue(preview.json()['needs_info'])
        self.assertEqual(self.client.get('/api/requests').json(),[])
        body.update(confirmed=True,request_id=uuid.uuid4().hex)
        self.assertEqual(self.client.post('/api/requests',json=body).status_code,400)
        body['scenario']['declaration']=True
        receipt=self.client.post('/api/requests',json=body).json()
        self.assertEqual(receipt['status'],'needs_info')
        self.assertEqual(self.client.post('/api/requests',json=body).json(),receipt)
        own=self.client.get('/api/requests').json()[0];self.assertEqual(own['scenario'],receipt['scenario'])
        self.assertNotIn('scenario_json',own)
        body['scenario']['tax_residence']='other'
        self.assertEqual(self.client.post('/api/requests',json=body).status_code,409)
        with TestClient(self.app) as staff:
            self.boot(staff);identity=staff.post('/api/testing/staff-session').json();staff.headers['X-CSRF-Token']=identity['csrf']
            record=staff.get('/api/admin/requests/'+receipt['id']).json()
            self.assertEqual(record['scenario'],receipt['scenario'])
        self.assertEqual(self.client.get('/api/admin/requests/'+receipt['id']).status_code,403)

    def test_preview_csrf_and_final_quote_tampering_is_rejected_in_english(self):
        body={'service_id':'transfer_demo','payload':transfer(),'scenario':scenario('transfer_demo')}
        route='/api/scenarios/preview'
        self.assertEqual(self.client.post(route,json=body,headers={'X-CSRF-Token':'wrong'}).status_code,403)
        body['scenario']['payee_name']='Wrong Person'
        bad=self.client.post(route,json=body,headers={'Accept-Language':'en'})
        self.assertEqual(bad.status_code,400);self.assertIn('does not match',bad.json()['detail'])
        body['scenario']=scenario('transfer_demo')|{'quote':{'total':'0'}}
        self.assertEqual(self.client.post('/api/requests',json={**body,'confirmed':True}).status_code,400)

    def test_migration_and_legacy_requests_survive_restart(self):
        legacy=self.app.state.store.submit('u:legacy','transfer_demo',transfer())
        with closing(sqlite3.connect(self.path)) as db:
            db.execute('ALTER TABLE requests DROP COLUMN scenario_json');db.commit()
        restarted=PortalStore(self.path)
        row=restarted.requests('u:legacy')[0]
        self.assertEqual(row['id'],legacy['id']);self.assertIsNone(row['scenario'])
        new=restarted.submit('u:legacy','transfer_demo',transfer(),scenario=scenario('transfer_demo'))
        self.assertEqual(PortalStore(self.path).requests('u:legacy')[0]['scenario']['quote']['total'],'100.00')
        self.assertNotEqual(new['id'],legacy['id'])
