"""Smoke-test a disposable loopback-only Docker instance and its mounted SQLite volume."""
import argparse
from http.cookies import SimpleCookie
import json
from pathlib import Path
import time
from urllib.parse import urlparse
from urllib.request import build_opener,ProxyHandler,Request
import uuid

ORIGIN='https://campusbank.example'
BOOTSTRAP='synthetic-bootstrap-for-disposable-ci'
ACCESS='synthetic-test-access-for-ci'
PASSWORD='SyntheticContainerPass2026'


class BrowserSession:
    def __init__(self,base):
        self.base=base;self.cookie='';self.csrf='';self.opener=build_opener(ProxyHandler({}))
        self.csrf=self.request('/api/bootstrap')['csrf']

    def request(self,path,method='GET',body=None):
        headers={'Content-Type':'application/json','Origin':ORIGIN,'X-CSRF-Token':self.csrf}
        if self.cookie:headers['Cookie']=self.cookie
        request=Request(self.base+path,data=json.dumps(body).encode() if body is not None else None,headers=headers,method=method)
        with self.opener.open(request,timeout=30) as response:
            cookie=SimpleCookie();cookie.load(response.headers.get('Set-Cookie',''))
            if 'campusbank_session' in cookie:self.cookie='campusbank_session='+cookie['campusbank_session'].value
            value=json.load(response)
        if isinstance(value,dict) and value.get('csrf'):self.csrf=value['csrf']
        return value

    def register(self,name,role='customer',invite=''):
        return self.request('/api/register','POST',{'username':name,'password':PASSWORD,'display_name':name,'portal_role':role,'invite_code':invite,'test_access_code':ACCESS})

    def login(self,name,role='customer'):
        return self.request('/api/login','POST',{'username':name,'password':PASSWORD,'portal_role':role})


def main():
    p=argparse.ArgumentParser();p.add_argument('--url',default='http://127.0.0.1:8511');p.add_argument('--state',required=True);p.add_argument('--verify-restart',action='store_true');args=p.parse_args()
    if urlparse(args.url).hostname not in ('127.0.0.1','localhost'):p.error('This fixture is restricted to a disposable loopback test server.')
    base=args.url.rstrip('/');opener=build_opener(ProxyHandler({}))
    for attempt in range(45):
        try:
            with opener.open(base+'/api/health',timeout=2) as response:
                if json.load(response)['ok']:break
        except OSError:time.sleep(1)
    else:raise RuntimeError('Disposable container failed to become healthy.')
    customer=BrowserSession(base)
    if args.verify_restart:
        state=json.loads(Path(args.state).read_text())
        customer.login('ci_customer')
        chat=customer.request('/api/chats/'+state['chat'])
        assert any(m['content']=='Container staff reply.' for m in chat['messages'])
        assert chat['ticket']['id']==state['ticket']
        staff=BrowserSession(base);staff.login('ci_worker','staff')
        assert staff.request('/api/admin/tickets/'+state['ticket'])['ticket']['status']=='active'
        print('Docker restart: accounts, chats, manual replies and ticket persisted.')
        return
    owner=BrowserSession(base);owner.register('ci_owner','staff',BOOTSTRAP)
    invitation=owner.request('/api/admin/staff-invites','POST')['invite_code']
    staff=BrowserSession(base);staff.register('ci_worker','staff',invitation)
    user=customer.register('ci_customer')['user'];assert not user['is_admin']
    chat=customer.request('/api/chats','POST')['id']
    customer.request('/api/chats/'+chat+'/messages','POST',{'text':'What documents do I need for a student account?','mode':'offline','request_id':uuid.uuid4().hex})
    result=customer.request('/api/chats/'+chat+'/handoff','POST');ticket=result['ticket']['id']
    assert customer.request('/api/chats/'+chat+'/handoff','POST')['existing']
    context=staff.request('/api/admin/tickets/'+ticket)['chat']
    assert any(m['role']=='user' for m in context['messages'])
    staff.request('/api/admin/tickets/'+ticket+'/claim','POST')
    staff.request('/api/admin/tickets/'+ticket+'/reply','POST',{'text':'Container staff reply.'})
    assert customer.request('/api/chats/'+chat)['messages'][-1]['metadata']['sender']=='staff'
    Path(args.state).write_text(json.dumps({'chat':chat,'ticket':ticket}),encoding='utf-8')
    print('Docker smoke: owner setup, invited staff, customer handoff and manual reply passed.')


if __name__=='__main__':main()
