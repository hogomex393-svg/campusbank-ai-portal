"""Small actual language/content checks. --online uses the configured paid API."""
import argparse
import hashlib
import json
import re
from datetime import datetime
from bankbot.config import ROOT
from bankbot.service import ChatService
from bankbot.dialogue import State
from bankbot.language import detect_language

CASES=[
 {'id':'switch','turns':[
     ('学生账户开户需要什么材料？','zh',['地址','学生']),
     ('那月费是多少？','zh',['不收']),
     ('What about the monthly fee?','en',['no monthly'])]},
 {'id':'branch','turns':[
     ('最近的网点在哪里？','zh',['城市']),
     ('London','zh',['20','周六'])]},
 {'id':'chinese_faq','turns':[('国际转账手续费是多少？','zh',['8'])]},
 {'id':'english_to_chinese','turns':[
     ('What documents do I need for a student account?','en',['student','address']),
     ('我的银行卡丢了怎么办？','zh',['冻结'])]},
 {'id':'service_then_language_switch','turns':[
     ('我想开学生账户，可以在网上申请吗？请给我办理入口，简短回答就好。','zh',[]),
     ('Before I apply, what documents do I need? Please keep it brief.','en',['student','address'])]},
]


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--online',action='store_true')
    p.add_argument('--mode',choices=['agent','rag','llm'],default='agent')
    args=p.parse_args()
    service=ChatService()
    if args.online and not service.settings.api_key:p.error('API configuration is missing')
    mode=args.mode if args.online else 'offline'
    outputs=[]
    for case in CASES:
        state=State()
        for text,expected,words in case['turns']:
            r=service.respond(text,state,mode);state=r.state
            outputs.append({'case':case['id'],'input':text,'answer':r.answer,'expected_language':expected,
                'language':r.language,'language_pass':r.language==expected and detect_language(r.answer,expected)==expected,
                'keypoint_pass':all(w.casefold() in r.answer.casefold() for w in words),
                'mode':r.mode,'source_ids':r.source_ids,'tool_names':[t['name'] for t in r.tools],
                'api_calls':r.api_calls,'usage':r.usage,'error':r.error,'latency_ms':r.latency_ms,
                'language_corrections':r.language_corrections,'actions':r.actions})
    summary={'mode':mode,'turns':len(outputs),'language_pass':sum(o['language_pass'] for o in outputs),
             'keypoint_pass':sum(o['keypoint_pass'] for o in outputs),'api_calls':sum(o['api_calls'] for o in outputs),
             'errors':sum(bool(o['error']) for o in outputs),
             'language_corrections':sum(o['language_corrections'] for o in outputs)}
    document={'run_time':datetime.now().astimezone().isoformat(),'model':service.settings.model if args.online else None,
              'faq_sha256':hashlib.sha256((ROOT/'data/faq.json').read_bytes()).hexdigest(),
              'note':f'{len(outputs)} authored turns for language regression; keyword checks are proxies, not full answer quality ratings.',
              'summary':summary,'outputs':outputs}
    dest=ROOT/'evaluation/results';dest.mkdir(exist_ok=True)
    (dest/f'bilingual_{mode}.json').write_text(json.dumps(document,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(summary))
    for o in outputs:
        if not o['language_pass'] or not o['keypoint_pass']:print(json.dumps(o,ensure_ascii=False))


if __name__=='__main__':main()
