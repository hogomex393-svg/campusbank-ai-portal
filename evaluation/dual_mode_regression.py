"""Small opt-in online check of richer answers, student finance and follow-ups."""
import argparse,json
from datetime import datetime,timezone
from bankbot.config import ROOT
from bankbot.dialogue import State
from bankbot.service import ChatService

CASES=[
 ('general_details','general','我想开日常账户，请详细解释费用、年龄要求、需要准备的材料，以及在线办理后如何查看进度。'),
 ('student_loan','student','请详细介绍演示助学贷款适合什么情况、需要哪些材料、利率和还款怎么确定，以及如何提交咨询。'),
 ('scholarship_grants','student','Please compare scholarships and student grants in this demo, including eligibility, documents and practical next steps.'),
 ('purpose_guidance','general','我想办张银行卡，但用途还不太确定，你能帮我了解一下吗？'),
]
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--online',action='store_true');args=parser.parse_args()
    if not args.online:parser.error('Pass --online deliberately; this check consumes the configured API quota.')
    service=ChatService()
    if not service.settings.api_key:parser.error('Configure your own provider key first.')
    outputs=[]
    for id_,mode,text in CASES:
        reply=service.respond(text,State(bank_mode=mode),'agent')
        checks={'online':reply.mode=='agent' and not reply.error,'followups':1<=len(reply.followups)<=3}
        if id_!='purpose_guidance':checks['substantive_length']=len(reply.answer)>=180
        if id_=='student_loan':checks['student_sources']='DEMO_EDUCATION_LOAN' in reply.source_ids;checks['no_personal_loan_apr']='8%' not in reply.answer
        if id_=='scholarship_grants':checks['awards_sources']=all(s in reply.source_ids for s in ('DEMO_MERIT_SCHOLARSHIP','DEMO_NEED_GRANT'))
        outputs.append({'case':id_,'bank_mode':mode,'input':text,'answer':reply.answer,'answer_characters':len(reply.answer),
                        'checks':checks,'passed':all(checks.values()),'followups':reply.followups,'actions':reply.actions,
                        'source_ids':reply.source_ids,'api_calls':reply.api_calls,'usage':reply.usage,'error':reply.error,'latency_ms':reply.latency_ms})
    summary={'cases':len(outputs),'cases_passed':sum(x['passed'] for x in outputs),'api_calls':sum(x['api_calls'] for x in outputs),
             'max_output_tokens':service.settings.max_tokens,'provider':service.settings.provider,'model':service.settings.model}
    result={'date':datetime.now(timezone.utc).isoformat(),'summary':summary,'note':'Authored synthetic regression; length is not a quality score. No Qwen live comparison is claimed.','outputs':outputs}
    path=ROOT/'evaluation/results';path.mkdir(exist_ok=True)
    (path/'dual_mode_online.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(summary))
    for row in outputs:
        if not row['passed']:print(json.dumps(row,ensure_ascii=True))
if __name__=='__main__':main()
