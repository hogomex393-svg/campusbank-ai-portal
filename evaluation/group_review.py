"""Matched four-mode evaluation. Structured proxies and human ratings stay separate."""
import argparse,csv,json,time
from datetime import datetime,timezone
from dataclasses import asdict
from pathlib import Path
from bankbot.config import ROOT
from bankbot.dialogue import State
from bankbot.service import ChatService
from bankbot.language import detect_language

def score(reply,expected):
    checks={'nonempty':bool(reply.answer.strip()),'response_language':detect_language(reply.answer,reply.language)==reply.language};services={a['service_id'] for a in reply.actions}
    if 'service' in expected:checks['service']=expected['service'] in services
    if expected.get('exclude_loan'):checks['exclusion']=not services.intersection({'education_loan','apply_loan'}) and reply.state.constraints.get('exclude_loan') is True
    if 'fields' in expected:
        service=expected.get('service','transfer_demo');draft=reply.state.service_drafts.get(service,{})
        for k,v in expected['fields'].items():checks['field_'+k]=draft.get(k)==v
    for value in expected.get('contains',[]):checks['text_'+value]=value.casefold() in reply.answer.casefold()
    for value in expected.get('not_sources',[]):checks['source_not_'+value]=value not in reply.source_ids
    if expected.get('card_followups'):checks['followup_topic']=all(not any(w in q.lower() for w in ('贷款','储蓄','开户','loan','savings','open an account')) for q in reply.followups)
    return checks

def main():
    p=argparse.ArgumentParser();p.add_argument('--modes',default='offline');p.add_argument('--online',action='store_true');p.add_argument('--ids',default='');p.add_argument('--max-api-calls',type=int,default=50);p.add_argument('--output',type=Path,default=ROOT/'evaluation/results/group_review');args=p.parse_args()
    modes=args.modes.split(',')
    if any(m not in ('agent','rag','llm','offline') for m in modes):p.error('Choose agent, rag, llm or offline.')
    bot=ChatService()
    if any(m!='offline' for m in modes) and (not args.online or not bot.settings.api_key):p.error('Online modes require --online and a privately configured API key.')
    cases=json.loads((ROOT/'data/review_eval_50.json').read_text(encoding='utf-8'))
    if args.ids:cases=[c for c in cases if c['id'] in args.ids.split(',')]
    if not cases:p.error('No cases selected.')
    rows=[];calls=0;stopped=False
    for mode in modes:
        for case in cases:
            state=State(bank_mode=case.get('bank_mode','general'))
            for index,turn in enumerate(case['turns']):
                if mode!='offline' and calls>=args.max_api_calls:stopped=True;break
                start=time.monotonic();reply=bot.respond(turn['input'],state,mode);state=reply.state;calls+=reply.api_calls
                checks=score(reply,turn.get('expect',{}))
                rows.append({'case_id':case['id'],'category':case['category'],'mode_requested':mode,'mode_actual':reply.mode,'turn':index+1,'input':turn['input'],'answer':reply.answer,
                    'checks':checks,'structured_pass':all(checks.values()),'error':reply.error,'actions':reply.actions,'drafts':state.service_drafts,'constraints':state.constraints,
                    'source_ids':reply.source_ids,'source_versions':reply.sources,'api_calls':reply.api_calls,'tokens':reply.usage,'backend_ms':reply.latency_ms,'wall_ms':round((time.monotonic()-start)*1000),
                    'human_relevance':None,'human_naturalness':None,'human_evidence_review':None})
            if stopped:break
        if stopped:break
    summary={mode:{'turns':len(part:=[r for r in rows if r['mode_requested']==mode]),'structured_proxy_passed':sum(r['structured_pass'] for r in part),'online_errors':sum(bool(r['error']) for r in part),'api_calls':sum(r['api_calls'] for r in part)} for mode in modes}
    doc={'date':datetime.now(timezone.utc).isoformat(),'case_count':len(cases),'budget_stopped':stopped,'max_api_calls':args.max_api_calls,'summary':summary,
        'method_note':'All modes share portal constraints, drafts and the fictional calculator. Agent adds tools, RAG supplies filtered FAQ evidence, LLM omits FAQ retrieval, offline uses local rules. Structured checks are authored proxies, not overall accuracy. Naturalness, relevance and evidence quality require human review.','rows':rows}
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.with_suffix('.json').write_text(json.dumps(doc,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    with args.output.with_suffix('.csv').open('w',encoding='utf-8-sig',newline='') as file:
        fields=['case_id','category','mode_requested','mode_actual','turn','input','answer','structured_pass','error','api_calls','backend_ms','wall_ms','human_relevance','human_naturalness','human_evidence_review']
        writer=csv.DictWriter(file,fieldnames=fields,extrasaction='ignore');writer.writeheader();writer.writerows({k:("'"+v if isinstance(v,str) and v.startswith(('=','+','-','@','\t','\r')) else v) for k,v in row.items()} for row in rows)
    print(json.dumps({'case_count':len(cases),'budget_stopped':stopped,'summary':summary}))

if __name__=='__main__':main()
