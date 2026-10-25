"""Public source titles and stable knowledge fingerprints, without private model reasoning."""
import hashlib
import json
from .knowledge import Knowledge
from .config import ROOT
from .student_finance import PROGRAMS

def public_sources(ids,knowledge=None):
    knowledge=knowledge or Knowledge(ROOT/'data');records={}
    for r in knowledge.faq:records[r['faq_id']]={'title':r.get('question_zh',r['question']),'title_en':r['question'],'topic':r['topic'],'record':r}
    for r in knowledge.products:records[r['source_id']]={'title':r.get('display_name_zh',r['display_name']),'title_en':r['display_name'],'topic':'products','record':r}
    for r in knowledge.branches:records[r['branch_id']]={'title':r.get('name_zh',r['name']),'title_en':r['name'],'topic':'branches','record':r}
    for r in PROGRAMS:records[r['id']]={'title':r['title'],'title_en':r['title_en'],'topic':'student_finance','record':r}
    from .scenarios import PAYEES,PAYERS,TRANSFER_POLICY
    records['DEMO_TRANSFER_QUOTE']={'title':'演示转账费用与汇率计算','title_en':'Fictional transfer fees and FX calculator','topic':'payments','record':{'payees':PAYEES,'payers':PAYERS,'policy':TRANSFER_POLICY}}
    result=[]
    for id_ in dict.fromkeys(ids):
        r=records.get(id_)
        if r:result.append({'id':id_,'title':r['title'],'title_en':r['title_en'],'topic':r['topic'],'version':hashlib.sha256(json.dumps(r['record'],sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:12]})
    return result
