"""Behaviour and provider-protocol tests; no live API calls in this suite."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from dataclasses import replace
from urllib.error import HTTPError
from bankbot.config import Settings
from bankbot.knowledge import load_faq
from bankbot.dialogue import State, prepare_turn
from bankbot.service import ChatService
from bankbot.llm_client import APIError, DeepSeekClient


class ScriptedClient:
    def __init__(self, messages):
        self.script = list(messages)
        self.requests = []

    def complete(self, messages, tools=None, timeout=None):
        self.requests.append(json.loads(json.dumps(messages)))
        entry = self.script.pop(0)
        if isinstance(entry, Exception):
            raise entry
        return {"message": entry, "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}


def call(name, args, id_="call_1"):
    return {"id": id_, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}


class SystemTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.settings = Settings(api_key="")
        cls.service = ChatService(cls.settings)

    def test_data_count_and_topics(self):
        self.assertEqual(len(self.service.knowledge.faq), 64)
        self.assertEqual(len({f['topic'] for f in self.service.knowledge.faq}), 8)

    def test_duplicate_data_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / 'faq.json'
            p.write_text(json.dumps([self.service.knowledge.faq[0]] * 2))
            with self.assertRaises(ValueError):
                load_faq(p)

    def test_retrieval_alias_deduplicates(self):
        results = self.service.retriever.search('What should I bring to open a student account?')
        self.assertEqual(results[0]['faq_id'], 'ACC_STUDENT_DOCUMENTS')
        self.assertEqual(len({r['faq_id'] for r in results}), len(results))

    def test_follow_up_and_original_state_unchanged(self):
        old = State()
        one = self.service.respond('I want to open a student account.', old, 'offline')
        two = self.service.respond('What about monthly fees?', one.state, 'offline')
        self.assertIn('no monthly', two.answer.lower())
        self.assertEqual(old.turns, [])
        self.assertEqual(len(one.state.turns), 1)
        self.assertEqual(len(two.state.turns), 2)

    def test_missing_product_then_answer(self):
        one = self.service.respond('How much does it cost?', mode='offline')
        self.assertEqual(one.mode, 'clarification')
        two = self.service.respond('An everyday account', one.state, 'offline')
        self.assertIn('GBP 3', two.answer)

    def test_topic_switch_to_lost_card(self):
        one = self.service.respond('Open a student account', mode='offline')
        two = self.service.respond('I lost my debit card.', one.state, 'offline')
        self.assertIn('freeze', two.answer.lower())
        self.assertIn('cannot freeze a real card',two.answer)
        self.assertEqual(two.state.product, 'debit_card')

    def test_freeze_is_not_interpreted_as_free_fees(self):
        result = self.service.respond('I need to freeze a lost debit card',mode='offline')
        self.assertIn('freeze',result.answer.lower())
        self.assertIn('cannot freeze a real card',result.answer)

    def test_branch_appointment_keeps_its_question(self):
        result = self.service.respond('How can I book a branch appointment in London?',mode='offline')
        self.assertIn('appointment',result.answer)
        self.assertIn('support',result.answer)

    def test_branch_city_clarification_and_unknown_city(self):
        one = self.service.respond('Where is the nearest branch?', mode='offline')
        self.assertEqual(one.mode, 'clarification')
        two = self.service.respond('Lancaster', one.state, 'offline')
        self.assertIn('10 Campus Way', two.answer)
        unknown = self.service.respond('Where is a branch in Oxford?', mode='offline')
        self.assertIn('No demo branch', unknown.answer)

    def test_generic_branch_question_needs_no_city(self):
        result = self.service.respond('Are branches open on bank holidays?', mode='offline')
        self.assertIn('closed on bank holidays', result.answer)

    def test_sessions_do_not_share_product(self):
        self.service.respond('Open a student account', State(), 'offline')
        other = self.service.respond('How much is the monthly fee?', State(), 'offline')
        self.assertEqual(other.mode, 'clarification')

    def test_tool_whitelist_and_argument_types(self):
        self.assertEqual(self.service.tools.execute('__import__', {})['error'], 'unknown_tool')
        self.assertEqual(self.service.tools.execute('find_branch', {'city': 2})['error'], 'invalid_arguments')
        self.assertEqual(self.service.tools.execute('find_branch', '{oops')['error'], 'invalid_arguments')
        self.assertEqual(self.service.tools.execute('find_branch', {'city':'London','extra':True})['error'], 'invalid_arguments')

    def test_agent_tool_protocol_preserves_reasoning(self):
        client = ScriptedClient([
            {'role':'assistant','content':None,'reasoning_content':'provider field',
             'tool_calls':[call('get_product_info', {'product_name':'student_account'})]},
            {'role':'assistant','content':'The student account has no monthly fee.'}])
        service = ChatService(replace(self.settings,api_key='test'), client)
        result = service.respond('Does the student account have a monthly fee?')
        self.assertEqual(result.mode,'agent')
        self.assertEqual(result.api_calls,2)
        self.assertIn('PRODUCT_STUDENT',result.source_ids)
        request = client.requests[1]
        self.assertEqual(request[-1]['role'],'tool')
        self.assertEqual(request[-1]['tool_call_id'],'call_1')
        self.assertEqual(request[-2]['reasoning_content'],'provider field')
        self.assertEqual(result.usage['total_tokens'],30)

    def test_multi_tool_messages_are_paired(self):
        client = ScriptedClient([
            {'role':'assistant','content':None,'tool_calls':[
                call('get_product_info',{'product_name':'student_account'},'a'),
                call('find_branch',{'city':'London'},'b')]},
            {'role':'assistant','content':'Student account details and London branch details.'}])
        result = ChatService(replace(self.settings,api_key='test'),client).respond('Tell me about student accounts and the London branch.')
        self.assertEqual([m['tool_call_id'] for m in result.state.turns[0] if m['role']=='tool'],['a','b'])

    def test_api_failure_produces_valid_plain_history(self):
        client = ScriptedClient([APIError('network_error','Simulated failure')])
        result = ChatService(replace(self.settings,api_key='test'),client).respond('What documents do I need for a student account?')
        self.assertEqual(result.mode,'offline_fallback')
        self.assertEqual([m['role'] for m in result.state.turns[0]],['user','assistant'])
        self.assertIn('photo ID',result.answer)

    def test_tool_loop_has_a_limit(self):
        message = {'role':'assistant','content':None,'tool_calls':[call('search_bank_faq',{'query':'student account fees'})]}
        client = ScriptedClient([message,message])
        result = ChatService(replace(self.settings,api_key='test',max_tool_rounds=1),client).respond('Student account fees?')
        self.assertEqual(result.error,'tool_limit')
        self.assertEqual(result.api_calls,2)
        self.assertEqual([m['role'] for m in result.state.turns[0]],['user','assistant'])

    def test_rag_and_llm_baselines_differ_in_evidence(self):
        for mode in ('rag','llm'):
            client = ScriptedClient([{'role':'assistant','content':'Test reply'}])
            ChatService(replace(self.settings,api_key='test'),client).respond('Student account documents?',mode=mode)
            self.assertEqual('FAQ evidence' in client.requests[0][0]['content'], mode=='rag')

    def test_empty_input_never_calls_api(self):
        client = ScriptedClient([])
        reply = ChatService(replace(self.settings,api_key='test'),client).respond('   ')
        self.assertEqual(reply.state.turns,[])
        self.assertEqual(client.requests,[])

    def test_http_error_is_sanitised(self):
        with patch('bankbot.llm_client.urlopen',side_effect=HTTPError('https://api.example',401,'sensitive-provider-body',{},None)):
            with self.assertRaises(APIError) as caught:
                DeepSeekClient(replace(self.settings,api_key='test-secret')).complete([{'role':'user','content':'hi'}])
        self.assertEqual(caught.exception.code,'http_401')
        self.assertNotIn('test-secret',str(caught.exception))
        self.assertNotIn('sensitive-provider-body',str(caught.exception))

    def test_history_window_keeps_complete_tool_turns(self):
        state=State(turns=[[{'role':'user','content':str(i)},{'role':'assistant','content':'answer'}] for i in range(8)])
        self.assertEqual(len(state.messages(2)),4)
        self.assertEqual(state.messages(2)[0]['content'],'6')


if __name__ == '__main__':
    unittest.main()
