"""Small explicit user constraints. They supplement model intent, not classify every turn."""
import re

LOAN_SERVICES={'education_loan','apply_loan'}

def update_constraints(text,previous=None):
    result=dict(previous or {})
    negative=list(re.finditer(r'(?:不(?:想|要|需要|考虑|打算|愿意)?|别)(?:再)?\s*(?:借钱|借款|贷款|助学贷款|学贷)|不用(?:偿还|还款|还钱)|无需(?:偿还|还款)|(?:do not|don.t|not interested in|exclude|avoid|without)\s+(?:(?:want|consider|any|taking|take|a)\s+)*(?:loans?|borrowing|debt)|non[- ]repayable|without repayment',text,re.I))
    positive=list(re.finditer(r'(?:改(?:为|成)?|现在|重新|也|愿意|还是|开始|考虑).{0,8}(?:贷款|借钱)|(?:贷款|借钱).{0,6}(?:也可以|可以看看|也行)|(?:include|consider|open to|actually|also show).{0,16}(?:loans?|borrowing)|loans?.{0,10}(?:fine|okay|as well|too)',text,re.I))
    events=[(m.end(),True) for m in negative]
    events += [(m.end(),False) for m in positive if not any(n.start()<=m.start()<n.end() for n in negative)]
    if events:result['exclude_loan']=max(events,key=lambda x:x[0])[1]
    return result

def permitted(service_id,constraints):return not ((constraints or {}).get('exclude_loan') and service_id in LOAN_SERVICES)

def funding_prefill(text):
    values={}
    if re.search(r'本科|undergraduate',text,re.I):values['study_level']='undergraduate'
    elif re.search(r'研究生|硕士|博士|postgraduate|masters?|phd',text,re.I):values['study_level']='postgraduate'
    scholarship=bool(re.search(r'奖学金|scholarship',text,re.I));grants=bool(re.search(r'补助|助学金|grant',text,re.I))
    if scholarship and grants:values['funding_type']='all'
    elif scholarship:values['funding_type']='scholarship'
    elif grants:values['funding_type']='grants'
    return values
