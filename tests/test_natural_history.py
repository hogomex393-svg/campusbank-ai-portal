"""Regression tests for model-led intent and complete, durable conversations."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from dataclasses import replace
from bankbot.config import Settings
from bankbot.dialogue import State, coerce_state
from bankbot.service import ChatService
from bankbot.history import HistoryStore, conversation_id, repair_display
from bankbot.ui_runtime import reply_details
from tests.test_system import ScriptedClient


class NaturalHistoryTests(unittest.TestCase):
    def test_online_ambiguity_reaches_model(self):
        client=ScriptedClient([{'role':'assistant','content':'你想问办卡费用还是转账费用？'}])
        result=ChatService(Settings(api_key='test'),client).respond('要多少钱？')
        self.assertEqual(result.mode,'agent')
        self.assertEqual(len(client.requests),1)
        self.assertEqual(client.requests[0][-1]['content'],'要多少钱？')
        self.assertNotIn('Confirmed context',client.requests[0][0]['content'])

    def test_short_reply_uses_actual_model_question(self):
        client=ScriptedClient([
            {'role':'assistant','content':'你主要想日常刷卡，还是需要信用额度？'},
            {'role':'assistant','content':'日常消费可考虑借记卡，学生账户可以配套申请。'}])
        service=ChatService(Settings(api_key='test'),client)
        one=service.respond('我想办张银行卡，需要什么步骤')
        two=service.respond('我是学生，只想刷卡买东西，不想借钱',one.state)
        self.assertIn('你主要想日常刷卡',client.requests[1][-2]['content'])
        self.assertEqual(len(two.state.turns),2)

    def test_conversation_keeps_more_than_thirty_turns(self):
        service=ChatService(Settings(api_key=''))
        state=State()
        for _ in range(35):state=service.respond('hello',state,'offline').state
        self.assertEqual(len(state.turns),35)
        self.assertEqual(len(state.messages(6)),12)

    def test_legacy_reply_without_language_is_supported(self):
        reply=SimpleNamespace(answer='已收到',mode='agent')
        details=reply_details(reply,'我想办张卡')
        self.assertEqual(details['response_language'],'zh')
        self.assertEqual(details['source_ids'],[])

    def test_legacy_state_is_rebuilt(self):
        old=SimpleNamespace(turns=[[{'role':'user','content':'hello'}]],product=None)
        rebuilt=coerce_state(old)
        self.assertEqual(rebuilt.language,'en')
        rebuilt.turns.append([])
        self.assertEqual(len(old.turns),1)

    def test_recovers_assistant_replies_missing_from_old_ui(self):
        state=State(turns=[
            [{'role':'user','content':'办卡步骤？'},{'role':'assistant','content':'你主要想办理哪种卡？'}],
            [{'role':'user','content':'学生账户'},{'role':'assistant','content':'可以申请学生账户配套借记卡。'}]])
        visible=[{'role':'user','content':'办卡步骤？'},{'role':'user','content':'学生账户'}]
        repaired=repair_display(visible,state)
        self.assertEqual([m['role'] for m in repaired],['user','assistant','user','assistant'])
        self.assertEqual(repaired[1]['content'],'你主要想办理哪种卡？')

    def test_does_not_drop_pending_user_message(self):
        state=State(turns=[[{'role':'user','content':'first'},{'role':'assistant','content':'reply'}]])
        visible=[{'role':'user','content':'first'},{'role':'assistant','content':'reply'},{'role':'user','content':'pending'}]
        self.assertEqual(repair_display(visible,state),visible)

    def test_disk_round_trip_and_ids_are_isolated(self):
        with tempfile.TemporaryDirectory() as folder:
            store=HistoryStore(Path(folder))
            id_=conversation_id()
            state=State(turns=[[{'role':'user','content':'中文问题'},{'role':'assistant','content':'中文回复'}]],language='zh')
            visible=repair_display([],state)
            store.save(id_,state,visible)
            restored=store.load(id_)
            self.assertEqual(restored['display'],visible)
            self.assertEqual(coerce_state(restored['state']).language,'zh')
            self.assertIsNone(store.load(conversation_id()))
            self.assertIsNone(store.load('../../.env'))


if __name__=='__main__':unittest.main()
