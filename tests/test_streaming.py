"""Streaming protocol, persistence, and retry tests; no paid API requests."""
import io
import json
import tempfile
import time
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from bankbot.config import Settings
from bankbot.llm_client import APIError, DeepSeekClient
from bankbot.service import ChatService
from bankbot.web import create_app
from tests.test_portal import StubAgent
from tests.test_system import ScriptedClient, call


def sse(*packets, done=True):
    lines=[': heartbeat\n\n']
    lines += ['data: '+json.dumps(p,ensure_ascii=False)+'\n\n' for p in packets]
    if done:lines.append('data: [DONE]\n\n')
    return io.BytesIO(''.join(lines).encode('utf-8'))


def packet(delta, finish=None):
    return {'choices':[{'delta':delta,'finish_reason':finish}]}


def events(response):
    return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]


class StreamingClient(ScriptedClient):
    def complete_stream(self,messages,tools=None,timeout=None,on_delta=None):
        result=self.complete(messages,tools,timeout)
        for part in (result['message'].get('content') or ''):
            on_delta(part)
        return result


class StreamProtocolTests(unittest.TestCase):
    def test_content_tool_fragments_usage_and_reasoning_are_separate(self):
        wire=sse(packet({'reasoning_content':'private reasoning'}),packet({'content':'先核对'}),
            packet({'content':'资料。','tool_calls':[{'index':0,'id':'call_demo','function':{'name':'open_service_window','arguments':'{"service_'}}]}),
            packet({'tool_calls':[{'index':0,'function':{'arguments':'id":"open_account"}'}}]},'tool_calls'),
            {'choices':[],'usage':{'total_tokens':23}})
        visible=[]
        with patch('bankbot.llm_client.urlopen',return_value=wire) as request:
            result=DeepSeekClient(Settings(api_key='synthetic-only')).complete_stream([],on_delta=visible.append)
        sent=json.loads(request.call_args.args[0].data)
        self.assertTrue(sent['stream']);self.assertTrue(sent['stream_options']['include_usage'])
        self.assertEqual(''.join(visible),'先核对资料。')
        self.assertEqual(result['usage']['total_tokens'],23)
        message=result['message'];self.assertEqual(message['reasoning_content'],'private reasoning')
        self.assertEqual(message['tool_calls'][0]['function']['name'],'open_service_window')
        self.assertEqual(json.loads(message['tool_calls'][0]['function']['arguments']),{'service_id':'open_account'})

    def test_incomplete_stream_and_deadline_raise_safe_errors(self):
        with self.assertRaises(APIError) as error:
            DeepSeekClient._read_stream(sse(packet({'content':'partial'}),done=False),lambda _:None,time.monotonic()+1)
        self.assertEqual(error.exception.code,'incomplete_stream')
        with self.assertRaises(APIError) as error:
            DeepSeekClient._read_stream(sse(packet({'content':'late'})),lambda _:None,time.monotonic()-1)
        self.assertEqual(error.exception.code,'timeout')

    def test_tool_narration_stream_matches_saved_answer_without_private_fields(self):
        first={'role':'assistant','content':'开户前需要核对身份证明。','reasoning_content':'private',
               'tool_calls':[call('open_service_window',{'service_id':'open_account'})]}
        second={'role':'assistant','content':'请在下方窗口检查信息。'}
        service=ChatService(Settings(api_key='synthetic-only'),StreamingClient([first,second]))
        seen=[];reply=service.respond_stream('如何在线开户？',on_event=seen.append)
        self.assertEqual(''.join(e['text'] for e in seen if e['type']=='delta'),reply.answer)
        self.assertNotIn('private',json.dumps(seen));self.assertNotIn('service_id',json.dumps(seen))
        self.assertEqual(reply.actions[0]['service_id'],'open_account')
        self.assertIsNone(reply.state.turns[-1][1]['content'])
        self.assertEqual(reply.state.turns[-1][-1]['content'],reply.answer)

    def test_interrupted_provider_replaces_partial_answer_with_saved_fallback(self):
        class Interrupted:
            def complete_stream(self,*args,on_delta=None,**kwargs):
                on_delta('Incomplete statement');raise APIError('network_error','Interrupted')
        service=ChatService(Settings(api_key='synthetic-only'),Interrupted())
        seen=[];reply=service.respond_stream('学生账户月费是多少？',on_event=seen.append)
        self.assertEqual(reply.mode,'offline_fallback')
        self.assertEqual(seen[-1],{'type':'replace','text':reply.answer})
        self.assertEqual(reply.state.turns[-1][-1]['content'],reply.answer)


class StreamEndpointTests(unittest.TestCase):
    def setUp(self):
        class StreamingAgent(StubAgent):
            def respond_stream(self,text,state,mode,on_event):
                on_event({'type':'delta','text':'可以进入'})
                on_event({'type':'delta','text':'开户窗口核对信息。'})
                return self.respond(text,state,mode)
        self.folder=tempfile.TemporaryDirectory();self.bot=StreamingAgent()
        with patch('bankbot.web.Settings.load',return_value=Settings()):
            self.app=create_app(Path(self.folder.name)/'portal.sqlite3',self.bot)
        self.client=TestClient(self.app);self.bootstrap(self.client)
        self.chat=self.client.post('/api/chats').json()['id']

    def bootstrap(self,client):client.headers['X-CSRF-Token']=client.get('/api/bootstrap').json()['csrf']
    def tearDown(self):self.client.close();self.folder.cleanup()

    def test_stream_events_persist_and_same_send_id_never_repeats_model_call(self):
        body={'text':'我要开户','request_id':uuid.uuid4().hex}
        response=self.client.post(f'/api/chats/{self.chat}/stream',json=body)
        self.assertIn('text/event-stream',response.headers['content-type'])
        self.assertIn('no-transform',response.headers['cache-control'])
        seen=events(response);self.assertEqual([e['type'] for e in seen],['start','delta','delta','complete'])
        saved=seen[-1]['chat'];self.assertEqual(len(saved['messages']),2)
        self.assertEqual(''.join(e['text'] for e in seen if e['type']=='delta'),saved['messages'][-1]['content'])
        self.assertEqual(self.client.get('/api/chats/'+self.chat).json(),saved)
        again=events(self.client.post(f'/api/chats/{self.chat}/stream',json=body))
        self.assertEqual(again[-1]['chat'],saved);self.assertEqual(self.bot.calls,1)
        self.assertEqual(self.client.post(f'/api/chats/{self.chat}/messages',json=body).json(),saved)
        self.assertEqual(self.bot.calls,1)

    def test_stream_enforces_ownership_csrf_and_nonblank_before_start(self):
        route=f'/api/chats/{self.chat}/stream'
        self.assertEqual(self.client.post(route,json={'text':'开户'},headers={'X-CSRF-Token':'wrong'}).status_code,403)
        self.assertEqual(self.client.post(route,json={'text':'   '}).status_code,400)
        with TestClient(self.app) as outsider:
            self.bootstrap(outsider)
            self.assertEqual(outsider.post(route,json={'text':'开户'}).status_code,404)
        self.assertEqual(self.bot.calls,0)

    def test_cloud_guest_blocked_and_quota_error_can_retry_same_id(self):
        settings=Settings(api_key='synthetic',cloud_mode=True,public_url='https://campusbank.example',
            bootstrap_code='synthetic-bootstrap-long-secret',test_access_code='synthetic-team-code')
        with patch('bankbot.web.Settings.load',return_value=settings):
            app=create_app(Path(self.folder.name)/'cloud.sqlite3',self.bot)
        with TestClient(app,base_url=settings.public_url) as client:
            self.bootstrap(client);chat=client.post('/api/chats').json()['id'];route=f'/api/chats/{chat}/stream'
            self.assertEqual(client.post(route,json={'text':'开户'}).status_code,401)
            user=client.post('/api/register',json={'username':'stream_test','password':'SyntheticPass2026',
                'display_name':'Synthetic','test_access_code':settings.test_access_code}).json()
            client.headers['X-CSRF-Token']=user['csrf']
            for i in range(6):self.assertEqual(events(client.post(route,json={'text':'测试'+str(i)}))[-1]['type'],'complete')
            body={'text':'稍后重试','request_id':uuid.uuid4().hex}
            error=events(client.post(route,json=body))[-1]
            self.assertEqual(error['type'],'error');self.assertEqual(error['status'],429)
            self.assertGreater(error['retry_after'],0)
            with patch('bankbot.web.time.time',return_value=time.time()+61):
                self.assertEqual(events(client.post(route,json=body))[-1]['type'],'complete')
            self.assertEqual(self.bot.calls,7)
