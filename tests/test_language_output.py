"""Actual output language must follow the turn, not just its metadata or prompt."""
import unittest
from unittest.mock import patch
from bankbot.config import Settings
from bankbot.dialogue import State
from bankbot.language import detect_language
from bankbot.llm_client import APIError
from bankbot.service import ChatService
from bankbot.ui_runtime import reply_details
from tests.test_system import ScriptedClient, call


class OutputLanguageTests(unittest.TestCase):
    def service(self, messages):
        client = ScriptedClient(messages)
        return ChatService(Settings(api_key='test'), client), client

    def test_chinese_to_english_tool_answer_is_corrected_and_history_stays_clean(self):
        service, client = self.service([
            {'role':'assistant','content':'可以通过在线申请窗口办理学生账户。'},
            {'role':'assistant','content':None,'tool_calls':[call('get_product_info',{'product_name':'student_account'})]},
            {'role':'assistant','content':'需要照片身份证件、在读学生证明和地址证明。'},
            {'role':'assistant','content':'You need photo ID, proof of student status, and proof of address.'},
        ])
        first = service.respond('我想开学生账户，可以在网上申请吗？')
        second = service.respond('Before I apply, what documents do I need? Please keep it brief.', first.state)
        self.assertEqual(second.mode, 'agent')
        self.assertEqual(detect_language(second.answer), 'en')
        self.assertEqual(second.api_calls, 3)
        self.assertEqual(second.language_corrections, 1)
        self.assertIn('PRODUCT_STUDENT', second.source_ids)
        self.assertEqual(len(second.state.turns), 2)
        self.assertEqual(second.state.turns[-1][-1]['content'], second.answer)
        self.assertNotIn('Internal output correction', str(second.state.turns))
        self.assertNotIn('需要照片身份证件', str(second.state.turns[-1]))
        self.assertIn('Internal output correction', client.requests[-1][-1]['content'])
        self.assertEqual(reply_details(second, 'question')['language_corrections'], 1)

    def test_english_to_chinese_is_also_corrected(self):
        service, _ = self.service([
            {'role':'assistant','content':'The student account has no monthly fee.'},
            {'role':'assistant','content':'学生账户不收取月费。'},
        ])
        result = service.respond('学生账户有月费吗？', State(language='en'))
        self.assertEqual(result.mode, 'agent')
        self.assertIn('不收取', result.answer)
        self.assertEqual(result.api_calls, 2)

    def test_failed_correction_returns_labeled_fallback_in_current_language(self):
        service, _ = self.service([
            {'role':'assistant','content':'学生账户不收月费。'},
            {'role':'assistant','content':'学生账户免费。'},
        ])
        result = service.respond('Does the student account have a monthly fee?')
        self.assertEqual(result.mode, 'offline_fallback')
        self.assertEqual(result.error, 'response_language')
        self.assertEqual(detect_language(result.answer), 'en')
        self.assertEqual(result.api_calls, 2)
        self.assertEqual(len(result.state.turns[-1]), 2)

    def test_correct_answer_does_not_add_an_api_call(self):
        service, client = self.service([{'role':'assistant','content':'The 学生账户 requires photo ID and proof of address.'}])
        result = service.respond('What documents do I need for 学生账户?')
        self.assertEqual(result.mode, 'agent')
        self.assertEqual(result.language_corrections, 0)
        self.assertEqual(result.api_calls, 1)
        self.assertEqual(len(client.requests), 1)

    def test_correction_usage_is_included_and_tools_are_disabled(self):
        class Client:
            def __init__(self): self.requests = []
            def complete(self, messages, tools=None, timeout=None):
                self.requests.append((tools, timeout))
                return {'message':{'role':'assistant','content':'学生账户不收月费。' if len(self.requests)==1 else 'There is no monthly fee.'},
                        'usage':{'prompt_tokens':10,'completion_tokens':5,'total_tokens':15}}
        client = Client()
        result = ChatService(Settings(api_key='test'), client).respond('Student account fee?')
        self.assertEqual(result.usage['total_tokens'], 30)
        self.assertIsNone(client.requests[-1][0])
        self.assertGreater(client.requests[-1][1], 0)

    def test_correction_network_failure_preserves_valid_dialogue(self):
        service, _ = self.service([
            {'role':'assistant','content':'学生账户不收月费。'},
            APIError('network_error', 'Simulated failure'),
        ])
        result = service.respond('Student account monthly fee?')
        self.assertEqual(result.error, 'network_error')
        self.assertEqual(result.mode, 'offline_fallback')
        self.assertEqual(detect_language(result.answer), 'en')
        self.assertEqual(len(result.state.turns[-1]), 2)

    def test_expired_budget_does_not_start_a_correction(self):
        service, client = self.service([{'role':'assistant','content':'学生账户不收月费。'}])
        expired=service.settings.timeout_seconds+1
        with patch('bankbot.service.time.monotonic', side_effect=[0, 0, expired, expired]):
            result = service.respond('Student account monthly fee?')
        self.assertEqual(result.error, 'timeout')
        self.assertEqual(result.mode, 'offline_fallback')
        self.assertEqual(len(client.requests), 1)


if __name__ == '__main__':
    unittest.main()
