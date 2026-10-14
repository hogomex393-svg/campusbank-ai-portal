"""Chinese/English behaviour across local replies, data, tools and provider context."""
import unittest
from dataclasses import replace
from bankbot.config import Settings
from bankbot.dialogue import State
from bankbot.language import detect_language
from bankbot.service import ChatService
from bankbot.llm_client import APIError
from tests.test_system import ScriptedClient, call


class BilingualTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.settings=Settings(api_key='')
        cls.service=ChatService(cls.settings)

    def test_language_mixed_text_and_neutral_entity(self):
        self.assertEqual(detect_language('学生账户需要什么材料？'),'zh')
        self.assertEqual(detect_language('What documents do I need for 学生账户?'),'en')
        self.assertEqual(detect_language('student account 要带哪些材料？'),'zh')
        self.assertEqual(detect_language('London','zh'),'zh')
        self.assertEqual(detect_language('What about fees?','zh'),'en')

    def test_all_data_has_parallel_chinese_records(self):
        for row in self.service.knowledge.faq:
            self.assertTrue(row['question_zh'])
            self.assertTrue(row['aliases_zh'])
            self.assertTrue(row['answer_zh'])
        products={p['product_name']:p for p in self.service.knowledge.products}
        for row in self.service.knowledge.faq:
            p=products.get(row['product'])
            if p and row['attribute']+'_zh' in p:
                self.assertEqual(row['answer_zh'],p[row['attribute']+'_zh'])

    def test_chinese_documents_and_fee_followup(self):
        first=self.service.respond('学生账户开户需要什么材料？',mode='offline')
        self.assertEqual(first.language,'zh')
        self.assertIn('在读学生证明',first.answer)
        second=self.service.respond('那月费是多少？',first.state,'offline')
        self.assertIn('不收取',second.answer)
        self.assertEqual(second.state.product,'student_account')

    def test_switch_to_english_after_chinese(self):
        first=self.service.respond('学生账户需要哪些材料？',mode='offline')
        second=self.service.respond('What about the monthly fee?',first.state,'offline')
        self.assertEqual(second.language,'en')
        self.assertIn('no monthly',second.answer)

    def test_switch_to_chinese_after_english(self):
        first=self.service.respond('Student account documents?',mode='offline')
        second=self.service.respond('有月费吗？',first.state,'offline')
        self.assertEqual(second.language,'zh')
        self.assertIn('不收取',second.answer)

    def test_chinese_product_clarification(self):
        first=self.service.respond('要多少钱？',mode='offline')
        self.assertEqual(first.mode,'clarification')
        self.assertIn('哪种产品',first.answer)
        second=self.service.respond('日常账户',first.state,'offline')
        self.assertIn('3 英镑',second.answer)

    def test_chinese_branch_and_neutral_city_reply(self):
        first=self.service.respond('最近的网点在哪里？',mode='offline')
        self.assertIn('哪个城市',first.answer)
        second=self.service.respond('London',first.state,'offline')
        self.assertEqual(second.language,'zh')
        self.assertIn('伦敦网点',second.answer)
        self.assertIn('周六',second.answer)

    def test_chinese_lost_card_topic_switch(self):
        first=self.service.respond('学生账户材料是什么？',mode='offline')
        second=self.service.respond('我的银行卡丢了怎么办？',first.state,'offline')
        self.assertIn('冻结',second.answer)
        self.assertEqual(second.state.product,'debit_card')

    def test_chinese_non_product_faq(self):
        reply=self.service.respond('国际转账手续费是多少？',mode='offline')
        self.assertIn('8 英镑',reply.answer)
        self.assertIn('PAY_INTERNATIONAL_FEE',reply.source_ids)

    def test_chinese_tool_arguments(self):
        product=self.service.tools.execute('get_product_info',{'product_name':'学生账户'})
        self.assertEqual(product['record']['product_name'],'student_account')
        branch=self.service.tools.execute('find_branch',{'city':'伦敦'})
        self.assertTrue(branch['found'])
        self.assertEqual(branch['records'][0]['city'],'London')

    def test_bilingual_retrieval_keeps_unique_source_ids(self):
        hits=self.service.retriever.search('学生账户开户材料')
        self.assertEqual(hits[0]['faq_id'],'ACC_STUDENT_DOCUMENTS')
        self.assertEqual(len({h['faq_id'] for h in hits}),len(hits))

    def test_chinese_api_fallback(self):
        client=ScriptedClient([APIError('network_error','Simulated failure')])
        service=ChatService(replace(self.settings,api_key='test'),client)
        reply=service.respond('学生账户材料有哪些？')
        self.assertEqual(reply.mode,'offline_fallback')
        self.assertEqual(reply.language,'zh')
        self.assertIn('照片身份证件',reply.answer)

    def test_provider_instruction_changes_with_current_message(self):
        client=ScriptedClient([{'role':'assistant','content':'学生账户不收月费。'},
                               {'role':'assistant','content':'The student account has no monthly fee.'}])
        service=ChatService(replace(self.settings,api_key='test'),client)
        one=service.respond('学生账户有月费吗？')
        service.respond('Please explain that in English.',one.state)
        self.assertIn('THIS turn: Simplified Chinese',client.requests[0][0]['content'])
        self.assertIn('THIS turn: English',client.requests[1][0]['content'])
        self.assertIn('学生账户有月费吗？',str(client.requests[1]))

    def test_chinese_provider_tool_roundtrip(self):
        client=ScriptedClient([
            {'role':'assistant','content':None,'tool_calls':[call('get_product_info',{'product_name':'学生账户'})]},
            {'role':'assistant','content':'学生账户需要照片身份证件、在读证明和地址证明。'}])
        reply=ChatService(replace(self.settings,api_key='test'),client).respond('学生账户需要哪些材料？')
        self.assertEqual(reply.language,'zh')
        self.assertEqual(reply.api_calls,2)
        self.assertIn('PRODUCT_STUDENT',reply.source_ids)

    def test_empty_after_chinese_uses_chinese_prompt(self):
        reply=self.service.respond('',State(language='zh'),'offline')
        self.assertEqual(reply.answer,'请输入一个银行业务问题。')
        self.assertEqual(reply.state.turns,[])


if __name__=='__main__':unittest.main()
