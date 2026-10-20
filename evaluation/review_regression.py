"""Authored regression of reported dialogue/form issues; online modes consume API quota."""
import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from bankbot.config import ROOT
from bankbot.service import ChatService
from bankbot.dialogue import State

CASES=[
 ('compound_zh','agent',[
  ('学生账户开户需要什么材料，有月费吗，可以网上办吗？',[['学生','在读'],['地址'],['不收','无月费','免费','免月费']])]),
 ('compound_rag','rag',[
  ('What documents are needed for a student account, and what is the international transfer fee?',[['student'],['address'],['8']])]),
 ('transfer_edit','agent',[
  ('给 Sam 模拟国际转账两千英镑',[]),('改成五百',[])]),
 ('appointment_edit','agent',[
  ('预约伦敦，2026 年 11 月 2 日，咨询学生账户',[]),('改成曼彻斯特',[])]),
 ('minimum_unknown','agent',[
  ('学生账户最低开户存款是多少？',[['未说明','没有明确','未明确','没有提供','未提供','没有规定','没有列出']])]),
 ('simulation_fields','agent',[
  ('模拟国际转账需要提供什么资料？',[['昵称'],['金额']])]),
 ('lost_card_limit','agent',[
  ('我的银行卡丢了，能在这里直接冻结吗？',[['不能','无法'],['演示']])]),
 ('comparison_table','agent',[
  ('Please compare Student and Everyday accounts in a table: monthly fees, age and documents.',[['|'],['3'],['student']])]),
]

def main():
    p=argparse.ArgumentParser();p.add_argument('--online',action='store_true');args=p.parse_args()
    bot=ChatService()
    if args.online and not bot.settings.api_key:p.error('Configure your own API key before online checks.')
    outputs=[]
    for case,mode,turns in CASES:
        state=State()
        for text,groups in turns:
            result=bot.respond(text,state,mode if args.online else 'offline');state=result.state
            passed=all(any(word.lower() in result.answer.lower() for word in group) for group in groups)
            if case=='transfer_edit':
                expected='500' if len(outputs) and text=='改成五百' else '2000'
                passed=state.service_drafts.get('transfer_demo')=={'transfer_type':'international','recipient':'Sam','amount':expected}
            if case=='appointment_edit':
                city='Manchester' if text=='改成曼彻斯特' else 'London'
                draft=state.service_drafts.get('branch_appointment',{})
                passed=draft.get('city')==city and draft.get('date')=='2026-11-02' and '学生' in draft.get('purpose','')
            outputs.append({'case':case,'input':text,'answer':result.answer,'mode':result.mode,'error':result.error,
                            'proxy_pass':passed,'actions':result.actions,'drafts':state.service_drafts,
                            'source_ids':result.source_ids,'api_calls':result.api_calls,'usage':result.usage,'latency_ms':result.latency_ms})
    summary={'turns':len(outputs),'proxy_checks_passed':sum(x['proxy_pass'] for x in outputs),
             'online_failures':sum(bool(x['error']) for x in outputs),'api_calls':sum(x['api_calls'] for x in outputs)}
    doc={'run_time':datetime.now(timezone.utc).isoformat(),'online':args.online,'model':bot.settings.model if args.online else None,
         'faq_sha256':hashlib.sha256((ROOT/'data/faq.json').read_bytes()).hexdigest(),
         'note':'Authored regression only; lexical/draft checks do not establish general answer quality. Inspect recorded answers.',
         'summary':summary,'outputs':outputs}
    path=ROOT/'evaluation/results';path.mkdir(exist_ok=True)
    (path/('review_online.json' if args.online else 'review_offline.json')).write_text(json.dumps(doc,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(summary))
    for row in outputs:
        if not row['proxy_pass'] or row['error']:print(json.dumps(row,ensure_ascii=True))

if __name__=='__main__':main()
