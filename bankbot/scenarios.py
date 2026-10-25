"""Realistic banking journeys using only fixed, explicitly fictional identities/accounts."""
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from difflib import SequenceMatcher
import json
from pathlib import Path

TRANSFER_POLICY=json.loads((Path(__file__).resolve().parents[1]/'data/transfer_policy.json').read_text(encoding='utf-8'))


def choice(value,zh,en):return {'value':value,'label':zh,'label_en':en}
def item(name,zh,en,type_='select',options=None,default=None,when=None):
    return {'name':name,'label':zh,'label_en':en,'type':type_,'options':options or [],'default':default,'when':when}


PROFILES=[
 {'id':'adult_demo','name':'Taylor Demo','birth_date':'1998-05-12','email':'taylor@example.invalid','address':'1 Example Walk, Demo City, ZZ1 1ZZ','residence':'UK','student':False,'identity':'DEMO-ID-ADULT'},
 {'id':'student_demo','name':'Jamie Demo','birth_date':'2004-06-15','email':'jamie@example.invalid','address':'Room DEMO-12, Example Halls, ZZ1 1ZZ','residence':'UK','student':True,'identity':'DEMO-ID-STUDENT','institution':'Example University'},
 {'id':'international_demo','name':'Robin Demo','birth_date':'2002-03-10','email':'robin@example.invalid','address':'Room DEMO-24, Example Halls, ZZ1 1ZZ','residence':'UK','student':True,'identity':'DEMO-ID-INTERNATIONAL','institution':'Example College'},
]
PAYERS=[
 {'id':'everyday_demo','label':'日常账户 · DEMO-CUR-01','label_en':'Everyday · DEMO-CUR-01','balance':'2500.00','currency':'GBP'},
 {'id':'student_demo','label':'学生账户 · DEMO-STU-01','label_en':'Student · DEMO-STU-01','balance':'1200.00','currency':'GBP'},
]
PAYEES=[
 {'id':'alex_demo','name':'Alex Morgan','label':'Alex · 个人收款人','label_en':'Alex · individual','type':'domestic','account_type':'personal','bank':'CampusBank Demo','country':'UK','currency':'GBP','rate':'1','routing':'DEMO-SORT-01','account':'DEMO-ACCT-ALEX'},
 {'id':'tuition_demo','name':'Example University','label':'示例大学 · 学费账户','label_en':'Example University · tuition','type':'domestic','account_type':'business','bank':'CampusBank Demo','country':'UK','currency':'GBP','rate':'1','routing':'DEMO-SORT-02','account':'DEMO-ACCT-TUITION'},
 {'id':'europe_demo','name':'Example EU College','label':'欧洲示例学院 · EUR','label_en':'Example EU College · EUR','type':'international','account_type':'business','bank':'Example EU Demo Bank','country':'DE','currency':'EUR','rate':TRANSFER_POLICY['rates']['EUR'],'routing':'DEMO-BIC-EU','account':'DEMO-IBAN-EU-NOT-VALID'},
 {'id':'us_demo','name':'Example US College','label':'美国示例学院 · USD','label_en':'Example US College · USD','type':'international','account_type':'business','bank':'Example US Demo Bank','country':'US','currency':'USD','rate':TRANSFER_POLICY['rates']['USD'],'routing':'DEMO-ROUTING-US','account':'DEMO-ACCT-US-NOT-VALID'},
]

ACCOUNT_FIELDS=[
 item('profile','选择演示申请人','Choose a fictional applicant',options=[choice(p['id'],p['name']+(' · 学生' if p['student'] else ' · 社会人士'),p['name']+(' · student' if p['student'] else ' · working adult')) for p in PROFILES],default='adult_demo'),
 item('employment','职业／学习状态','Employment / study status',options=[choice('employed','在职','Employed'),choice('student','在读学生','Student'),choice('self_employed','自雇','Self-employed'),choice('other','其他／暂未就业','Other / not employed')],default='employed'),
 item('account_purpose','账户主要用途','Main purpose',options=[choice('daily','日常收付款','Everyday payments'),choice('salary','工资收入','Salary income'),choice('study','学习与生活支出','Study and living costs')],default='daily'),
 item('funding_source','主要资金来源','Main source of funds',options=[choice('salary','工资／工作收入','Employment income'),choice('savings','已有储蓄','Existing savings'),choice('family','家庭支持','Family support'),choice('scholarship','奖学金／助学支持','Scholarship / study support')],default='salary'),
 item('tax_residence','税务居住地（演示）','Tax residence (demo)',options=[choice('UK','英国（演示）','United Kingdom (demo)'),choice('other','其他地区（待人工补充）','Other jurisdiction (staff follow-up)')],default='UK'),
 item('identity_document','身份证明材料','Identity document',options=[choice('passport','演示护照资料已就绪','Demo passport record ready'),choice('identity_card','演示身份证明已就绪','Demo identity record ready'),choice('missing','需要协助补充','Need help providing this')],default='passport'),
 item('address_document','地址证明材料','Proof of address',options=[choice('statement','演示银行对账单已就绪','Demo bank statement ready'),choice('utility','演示公共事业账单已就绪','Demo utility bill ready'),choice('missing','需要协助补充','Need help providing this')],default='statement'),
 item('student_document','在读证明材料','Proof of enrolment',options=[choice('letter','演示在读证明已就绪','Demo enrolment letter ready'),choice('missing','需要协助补充','Need help providing this')],default='letter',when='student'),
 item('debit_card','是否需要配套借记卡','Linked debit card',options=[choice('yes','需要演示借记卡','Request a demo debit card'),choice('no','暂不需要','Not now')],default='yes'),
 item('declaration','我已核对演示资料及开户条件，了解申请需要审核','I reviewed the fictional details and eligibility; the application requires review','checkbox',default=False),
]
TRANSFER_FIELDS=[
 item('payer','付款账户（演示）','Pay from (demo)',options=[choice(p['id'],p['label'],p['label_en']) for p in PAYERS],default='everyday_demo'),
 item('payee_profile','选择演示收款资料','Choose a fictional payee',options=[choice(p['id'],p['label'],p['label_en']) for p in PAYEES],default='alex_demo'),
 item('payee_name','收款账户名称（可修改以测试核对）','Payee account name (editable for matching tests)','text',default='Alex Morgan'),
 item('payment_purpose','付款用途','Payment purpose',options=[choice('living','生活费用','Living costs'),choice('family','亲友往来','Family / friends'),choice('tuition','学费','Tuition'),choice('bill','账单','Bill'),choice('other','其他','Other')],default='living'),
 item('execution','执行安排','Payment timing',options=[choice('now','确认后登记待处理请求','Record for processing'),choice('scheduled','预约日期（模拟）','Schedule a date (simulated)')],default='now'),
 item('execution_date','预约日期','Scheduled date','date',default='',when='scheduled'),
 item('payee_ack','我已核对名称存在细微差异，仍使用所选演示收款资料','I reviewed the minor name difference and will use the selected demo payee','checkbox',default=False,when='close_match'),
 item('declaration','我已核对收款资料、金额及费用，了解本次不会实际扣款','I reviewed the payee, amount and fees; no real money will move','checkbox',default=False),
]
SCENARIOS={
 'open_account':{'kind':'account','fields':ACCOUNT_FIELDS,'profiles':PROFILES},
 'transfer_demo':{'kind':'transfer','fields':TRANSFER_FIELDS,'payers':PAYERS,'payees':PAYEES},
}

ERRORS={
 '场景资料不完整或包含未知字段。':'The scenario is incomplete or contains unknown fields.',
 '请选择有效的演示资料。':'Choose valid fictional scenario details.',
 '请勾选演示资料核对声明。':'Confirm that you reviewed the fictional details.',
 '学生账户需要选择在读学生资料和学习状态。':'A student account needs a student profile and student study status.',
 '收款资料与转账类型不一致。':'The selected payee does not match the transfer type.',
 '收款名称不匹配，请核对演示收款资料。':'The payee name does not match. Check the fictional payee details.',
 '名称存在细微差异，请勾选核对确认。':'Review and confirm the minor payee name difference.',
 '演示余额不足，请减少金额或更换付款账户。':'The fictional balance is insufficient. Reduce the amount or choose another payer.',
 '预约日期不能早于今天。':'The scheduled date cannot be earlier than today.',
 '日期格式不正确。':'Enter a valid date.',
}

def name_match(name,expected):
    normal=lambda s:' '.join(s.casefold().split())
    left,right=normal(name),normal(expected)
    return 'match' if left==right else 'close' if SequenceMatcher(None,left,right).ratio()>=.8 else 'mismatch'

def transfer_quote(amount,transfer_type='domestic',payer_id='everyday_demo',payee_id=None,currency=None):
    """One decimal calculation shared by chat tools, previews and saved receipts."""
    from decimal import InvalidOperation
    try:amount=Decimal(str(amount))
    except InvalidOperation:raise ValueError('金额格式不正确。') from None
    if not amount.is_finite() or not Decimal('0.01')<=amount<=1000000 or amount.as_tuple().exponent < -2:raise ValueError('金额超出允许范围或超过两位小数。')
    if transfer_type not in ('domestic','international'):raise ValueError('收款资料与转账类型不一致。')
    payer=next((p for p in PAYERS if p['id']==payer_id),None)
    if payee_id:payee=next((p for p in PAYEES if p['id']==payee_id),None)
    else:payee=next((p for p in PAYEES if p['type']==transfer_type and (not currency or p['currency']==currency)),None)
    if not payer or not payee or payee['type']!=transfer_type:raise ValueError('收款资料与转账类型不一致。')
    fee=Decimal(TRANSFER_POLICY['fees'][transfer_type]);total=amount+fee;balance=Decimal(payer['balance'])
    if total>balance:raise ValueError('演示余额不足，请减少金额或更换付款账户。')
    money=lambda x:f'{x.quantize(Decimal("0.01"),rounding=ROUND_HALF_UP):.2f}'
    return {'currency':'GBP','amount':money(amount),'fee':money(fee),'total':money(total),'available':money(balance),'estimated_after':money(balance-total),
            'receive_currency':payee['currency'],'receive_amount':money(amount*Decimal(payee['rate'])),'rate':payee['rate'],'fictional':True,
            'payee_profile':payee['id'],'source_id':'DEMO_TRANSFER_QUOTE','version':TRANSFER_POLICY['version']}

def validate_scenario(service_id,values,payload,today=None,confirm=True):
    if values is None:return None  # Readable compatibility for existing saved/legacy requests.
    schema=SCENARIOS.get(service_id)
    if not schema or not isinstance(values,dict) or set(values)-{f['name'] for f in schema['fields']}:raise ValueError('场景资料不完整或包含未知字段。')
    clean={}
    for f in schema['fields']:
        value=values.get(f['name'],f['default'])
        if f['type']=='checkbox':
            if not isinstance(value,bool):raise ValueError('请选择有效的演示资料。')
        else:
            if not isinstance(value,str) or len(value)>100:raise ValueError('请选择有效的演示资料。')
            value=value.strip()
            if f['type']=='select' and value not in {o['value'] for o in f['options']}:raise ValueError('请选择有效的演示资料。')
        clean[f['name']]=value
    if confirm and not clean['declaration']:raise ValueError('请勾选演示资料核对声明。')
    summary=[]
    def row(zh,en,value,value_en=None):summary.append({'label':zh,'label_en':en,'value':str(value),'value_en':str(value if value_en is None else value_en)})
    def selections(names):
        for name in names:
            f=next(f for f in schema['fields'] if f['name']==name)
            o=next((o for o in f['options'] if o['value']==clean[name]),None)
            if o:row(f['label'],f['label_en'],o['label'],o['label_en'])
    result={'version':1,'kind':schema['kind'],'details':clean,'summary':summary,'fictional':True}
    if service_id=='open_account':
        person=next(p for p in PROFILES if p['id']==clean['profile'])
        student=payload['product']=='student_account'
        if student and (not person['student'] or clean['employment']!='student'):raise ValueError('学生账户需要选择在读学生资料和学习状态。')
        row('演示法定姓名','Fictional legal name',person['name']);row('演示出生日期','Fictional date of birth',person['birth_date'])
        row('演示联系邮箱','Fictional contact email',person['email']);row('演示居住地址','Fictional residential address',person['address'])
        row('演示身份记录','Fictional identity record',person['identity'])
        if student:row('演示学校','Fictional institution',person['institution'])
        selections(['employment','account_purpose','funding_source','tax_residence','identity_document','address_document']+(['student_document'] if student else [])+['debit_card'])
        missing=[k for k in ('identity_document','address_document',*(['student_document'] if student else [])) if clean[k]=='missing']
        if clean['tax_residence']=='other':missing.append('tax_residence')
        result['needs_info']=bool(missing);result['missing_fields']=missing
        row('材料状态','Document status','待补充资料' if missing else '演示材料已准备，等待工作人员审核','Information needed' if missing else 'Demo documents ready; awaiting staff review')
    else:
        payer=next(p for p in PAYERS if p['id']==clean['payer']);payee=next(p for p in PAYEES if p['id']==clean['payee_profile'])
        if payee['type']!=payload['transfer_type']:raise ValueError('收款资料与转账类型不一致。')
        match=name_match(clean['payee_name'],payee['name'])
        if match=='mismatch':raise ValueError('收款名称不匹配，请核对演示收款资料。')
        if confirm and match=='close' and not clean['payee_ack']:raise ValueError('名称存在细微差异，请勾选核对确认。')
        quote=transfer_quote(payload['amount'],payload['transfer_type'],clean['payer'],clean['payee_profile'])
        if clean['execution']=='scheduled':
            try:scheduled=date.fromisoformat(clean['execution_date'])
            except ValueError:raise ValueError('日期格式不正确。') from None
            if scheduled<(today or date.today()):raise ValueError('预约日期不能早于今天。')
        else:clean['execution_date']=''
        result['quote']=quote;result['payee_match']=match
        row('付款账户','Pay from',payer['label'],payer['label_en']);row('演示可用余额','Fictional available balance','GBP '+quote['available'])
        row('收款账户名称','Payee account name',clean['payee_name']);row('收款银行／国家','Payee bank / country',payee['bank']+' / '+payee['country'])
        row('收款账户类型','Payee account type','个人账户' if payee['account_type']=='personal' else '机构账户','Personal' if payee['account_type']=='personal' else 'Business / institution')
        row('演示路由标识','Fictional routing identifier',payee['routing']);row('演示收款账户标识','Fictional payee identifier',payee['account'])
        row('名称核对（仅演示数据）','Name check (fictional records only)','名称一致' if match=='match' else '细微差异已确认','Match' if match=='match' else 'Minor difference confirmed')
        selections(['payment_purpose','execution'])
        if clean['execution_date']:row('预约日期','Scheduled date',clean['execution_date'])
        for zh,en,key in [('转账本金','Transfer amount','amount'),('演示手续费','Fictional fee','fee'),('预计总扣款（模拟）','Estimated total debit (simulation)','total'),('预计剩余余额（模拟）','Estimated remaining balance (simulation)','estimated_after')]:row(zh,en,'GBP '+quote[key])
        if payee['type']=='international':row('演示固定汇率','Fictional fixed exchange rate','1 GBP = '+payee['rate']+' '+payee['currency'])
        row('预计到账（模拟）','Estimated recipient amount (simulation)',payee['currency']+' '+quote['receive_amount'])
    return result
