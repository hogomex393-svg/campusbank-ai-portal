"""Active customer identity cannot use staff permissions, even on an admin account."""
from fastapi.testclient import TestClient
import tests.test_portal as fixtures
import unittest


class RoleSeparationTests(unittest.TestCase):
    setUp=fixtures.PortalTests.setUp
    tearDown=fixtures.PortalTests.tearDown
    bootstrap=fixtures.PortalTests.bootstrap
    register=fixtures.PortalTests.register
    chat=fixtures.PortalTests.chat
    # Reuse setup helpers, while only collecting the new role tests in this class.
    def test_customer_identity_on_admin_account_cannot_reply_until_explicit_switch(self):
        user=self.register(self.client,'manager')
        self.assertTrue(user['is_admin'])
        chat=self.chat(self.client)
        ticket=self.client.post('/api/chats/'+chat+'/handoff').json()['ticket']['id']
        self.assertEqual(self.client.get('/api/admin/tickets').status_code,403)
        self.assertEqual(self.client.post('/api/admin/staff-invites').status_code,403)
        self.assertEqual(self.client.post('/api/admin/tickets/'+ticket+'/reply',json={'text':'不可冒充人工'}).status_code,403)
        old=self.client.cookies.get('campusbank_session')
        r=self.client.post('/api/session/role',json={'portal_role':'staff'})
        self.assertEqual(r.status_code,200);self.client.headers['X-CSRF-Token']=r.json()['csrf']
        self.assertIsNone(self.app.state.store.session(old))
        self.assertEqual(self.client.post('/api/admin/tickets/'+ticket+'/reply',json={'text':'真正的工作人员回复'}).status_code,200)
        r=self.client.post('/api/session/role',json={'portal_role':'customer'});self.client.headers['X-CSRF-Token']=r.json()['csrf']
        self.assertEqual(self.client.get('/api/admin/tickets').status_code,403)
        record=self.client.get('/api/support-tickets/'+ticket).json()
        self.assertEqual(record['chat']['messages'][-1]['content'],'真正的工作人员回复')

    def test_customer_history_is_owned_and_plain_customer_cannot_switch_to_staff(self):
        self.register(self.client,'first')
        customer=TestClient(self.app);self.bootstrap(customer);self.register(customer,'customer')
        chat=self.chat(customer);ticket=customer.post('/api/chats/'+chat+'/handoff').json()['ticket']['id']
        self.assertEqual(customer.post('/api/session/role',json={'portal_role':'staff'}).status_code,403)
        self.assertEqual(len(customer.get('/api/support-tickets').json()),1)
        self.assertEqual(len(self.client.get('/api/support-tickets').json()),0)
        self.assertEqual(self.client.get('/api/support-tickets/'+ticket).status_code,404)
        self.assertEqual(customer.get('/api/support-tickets/'+ticket).status_code,200)
        customer.close()


if __name__=='__main__':unittest.main()
