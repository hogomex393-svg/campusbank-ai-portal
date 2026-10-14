"""Save actual outputs and lexical proxy scores; do not equate them with human quality."""
import argparse
import hashlib
import json
import math
import platform
from datetime import datetime
from pathlib import Path
from bankbot.config import ROOT
from bankbot.service import ChatService
from bankbot.dialogue import State


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


def score(answer, groups):
    answer = answer.lower()
    return all(any(term.lower() in answer for term in group) for group in groups)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--mode',choices=['offline','agent','rag','llm'],default='offline')
    p.add_argument('--limit',type=int,default=None)
    p.add_argument('--dialogues',action='store_true')
    args=p.parse_args()
    service=ChatService()
    if args.mode != 'offline' and not service.settings.api_key:
        p.error('Online evaluation requires the local API configuration.')
    records=read_jsonl(ROOT/'data'/('test_dialogues.jsonl' if args.dialogues else 'test_queries.jsonl'))
    limit=args.limit if args.limit is not None else (len(records) if args.mode=='offline' else 8)
    if limit <= 0:
        p.error('--limit must be positive')
    records=records[:limit]
    outputs=[]
    for item in records:
        state=State()
        turns=item['turns'] if args.dialogues else [item]
        turn_outputs=[]
        for turn in turns:
            reply=service.respond(turn['text'],state,args.mode)
            state=reply.state
            retrieved=service.retriever.search(turn['text']) if not args.dialogues else []
            expected=set(turn.get('expected_source_ids',[]))
            rank=[r['faq_id'] for r in retrieved]
            turn_outputs.append({'input':turn['text'],'answer':reply.answer,'mode':reply.mode,
                'source_ids':reply.source_ids,'tools':reply.tools,'latency_ms':reply.latency_ms,
                'api_calls':reply.api_calls,'usage':reply.usage,'error':reply.error,
                'lexical_keypoint_pass':score(reply.answer,turn['keypoint_groups']),
                'hit_at_1':bool(expected.intersection(rank[:1])) if expected else None,
                'hit_at_3':bool(expected.intersection(rank[:3])) if expected else None,
                'retrieval_scorable':bool(expected) and not any(e.startswith('PRODUCT_') for e in expected)})
        outputs.append({'id':item.get('query_id',item.get('dialogue_id')),'turns':turn_outputs,
                        'all_turn_keypoints_pass':all(t['lexical_keypoint_pass'] for t in turn_outputs)})
    flat=[t for o in outputs for t in o['turns']]
    scorable=[t for t in flat if t['retrieval_scorable']]
    times=sorted(t['latency_ms'] for t in flat)
    summary={'requested_mode':args.mode,'cases':len(outputs),'turns':len(flat),
             'lexical_keypoint_pass_rate':sum(t['lexical_keypoint_pass'] for t in flat)/len(flat),
             'all_turn_keypoints_pass_rate':sum(o['all_turn_keypoints_pass'] for o in outputs)/len(outputs),
             'retrieval_scorable_queries':len(scorable),
             'hit_at_1':sum(t['hit_at_1'] for t in scorable)/len(scorable) if scorable else None,
             'hit_at_3':sum(t['hit_at_3'] for t in scorable)/len(scorable) if scorable else None,
             'latency_median_ms':times[len(times)//2],
             'latency_p95_ms':times[math.ceil(len(times)*.95)-1],
             'api_calls':sum(t['api_calls'] for t in flat),
             'total_tokens':sum(t['usage'].get('total_tokens',0) for t in flat),
             'online_failures':sum(bool(t['error']) for t in flat),
             'human_review_required':True}
    stamp=datetime.now().astimezone().isoformat()
    metadata={'run_time':stamp,'python':platform.python_version(),'model':service.settings.model if args.mode!='offline' else None,
              'faq_sha256':hashlib.sha256((ROOT/'data/faq.json').read_bytes()).hexdigest(),
              'note':'Authored small benchmark; lexical keypoint scores are proxies, not factuality or naturalness ratings. Online defaults to 8 cases. Cases become observed after evaluation.'}
    target=ROOT/'evaluation/results';target.mkdir(parents=True,exist_ok=True)
    file=target/(args.mode+('_dialogues' if args.dialogues else '_queries')+'.json')
    file.write_text(json.dumps({'metadata':metadata,'summary':summary,'outputs':outputs},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(summary,indent=2))
    print('Saved',file)


if __name__=='__main__': main()
