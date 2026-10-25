"""Partial demo-form drafts. Drafting never confirms or submits a request."""
import re
from decimal import Decimal, InvalidOperation
from .catalog import SERVICES, service_action
from .language import CITY_ALIASES, canonical_city
from .intent import update_constraints,permitted,funding_prefill


def clean_prefill(service_id, values):
    service = SERVICES.get(service_id)
    if not service or not isinstance(values, dict):
        raise ValueError('Choose an approved service and an object of demo fields.')
    fields = {f['name']: f for f in service['fields']}
    if set(values) - set(fields):
        raise ValueError('Use only fields listed in this demo service form; no account numbers or credentials.')
    clean = {}
    for name, value in values.items():
        f = fields[name]
        # Agreement and confirmation boxes can only be checked by the person.
        if f['type'] == 'checkbox': continue
        if isinstance(value, bool) or not isinstance(value, (str, int, float)):
            raise ValueError('Draft values must be text or numbers.')
        value = str(value).strip()
        if len(value) > 2000: raise ValueError('Draft value is too long.')
        if f['type'] == 'select':
            choices = {o['value'] for o in f['options']}
            if name == 'city': value = canonical_city(value)
            elif value not in choices:
                value = value.lower().replace(' ', '_')
            if value not in choices: raise ValueError('Choose a listed demo option.')
        clean[name] = value
    return clean


def update_draft(state, service_id, patch):
    clean = clean_prefill(service_id, patch)
    current = dict(state.service_drafts.get(service_id, {}))
    current.update(clean)
    state.service_drafts[service_id] = current
    state.active_service = service_id
    action = service_action(service_id)
    action['prefill'] = current.copy()
    return action


def chinese_number(text):
    digits = {'零':0,'一':1,'二':2,'两':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9}
    units = {'十':10,'百':100,'千':1000,'万':10000}
    total, section, number, last_unit = 0, 0, 0, 1
    for char in text:
        if char in digits: number = digits[char]
        elif char in units:
            unit = units[char]
            last_unit=unit
            if unit == 10000:
                total += (section + number) * unit; section = number = 0
            else: section += (number or 1) * unit; number = 0
        else: raise ValueError('Unsupported number')
    # Colloquial 两千五 means 2500; an explicit 零 keeps 两千零五 at 2005.
    if number and last_unit>10 and '零' not in text[text.rfind(next((c for c in reversed(text) if c in units),''))+1:]:
        number*=last_unit//10
    return str(total + section + number)


def draft_from_message(text, state):
    """Extract explicit common slots; the LLM tool handles broader paraphrases."""
    lower = text.lower()
    service_id = None
    was_excluded=state.constraints.get('exclude_loan',False)
    constraints=update_constraints(text,state.constraints);state.constraints=constraints
    if constraints.get('exclude_loan') and re.search(r'资助|借钱|贷款|补助|奖学金|aid|funding|loans?|borrow|repay',lower):service_id='funding_enquiry'
    elif (was_excluded and not constraints.get('exclude_loan') and re.search(r'贷款|借钱|loan|borrow',lower)) or re.search(r'助学贷款|学贷|student loan|education loan|tuition loan',lower):service_id='education_loan'
    elif re.search(r'奖学金|助学金|补助|scholarship|student grant|financial aid',lower):service_id='funding_enquiry'
    elif re.search(r'预约|appointment|book.*branch|visit.*branch', lower): service_id = 'branch_appointment'
    elif re.search(r'转账|汇款|transfer|payment', lower): service_id = 'transfer_demo'
    elif re.search(r'挂失|补卡|卡.*丢|lost.*card|replace.*card', lower) or state.active_service=='replace_card' and re.search(r'补办|冻结|replacement|freeze|费用|cost',lower): service_id = 'replace_card'
    elif re.search(r'申请.*贷款|贷款申请|apply.*loan', lower): service_id = 'apply_loan'
    elif re.search(r'开.*储蓄|open.*saving', lower): service_id = 'open_savings'
    elif re.search(r'开户|开.*账户|开.*帐户|open.*account|apply.*account', lower): service_id = 'open_account'
    elif state.active_service and re.search(r'改|换|金额|收款人|日期|城市|change|instead|recipient|amount|date|city|^[\w£., -]+$', lower):
        service_id = state.active_service
    if not service_id or not permitted(service_id,constraints): return None
    patch = funding_prefill(text) if service_id=='funding_enquiry' else {}
    if service_id=='education_loan':patch.update({k:v for k,v in funding_prefill(text).items() if k=='study_level'})
    if service_id == 'branch_appointment':
        for city, aliases in CITY_ALIASES.items():
            if any(a in lower for a in aliases): patch['city'] = city
        date = re.search(r'(20\d{2})\s*(?:年|[-/])\s*(\d{1,2})\s*(?:月|[-/])\s*(\d{1,2})\s*日?', text)
        if date: patch['date'] = f'{date[1]}-{int(date[2]):02}-{int(date[3]):02}'
        purpose = re.search(r'(?:咨询|业务(?:说明)?[：:]?|purpose[: ]+)\s*([^，。;\n]+)', text, re.I)
        if purpose: patch['purpose'] = purpose[1].strip()
        elif 'purpose' not in state.service_drafts.get(service_id, {}) and re.search(r'学生账户|student account', lower):
            patch['purpose'] = '学生账户咨询' if re.search(r'[\u4e00-\u9fff]', text) else 'Student account enquiry'
    if service_id in ('transfer_demo', 'apply_loan', 'open_savings','education_loan'):
        if service_id == 'transfer_demo':
            if re.search(r'国际|international', lower): patch['transfer_type'] = 'international'
            elif re.search(r'国内|domestic', lower): patch['transfer_type'] = 'domestic'
            name = re.search(r'(?:\bto\s+|\brecipient\s*(?:is|to|:|=)?\s*|给\s*|收款人(?:改成|换成|为|是|：|:)?\s*)([A-Za-z][A-Za-z -]{0,45}?)(?=\s+(?:£|GBP|[\d]|for\b|an?\s|international\b|domestic\b|simulate\b)|\s*(?:模拟|转账|汇款)|[,.，。;!?]|$)', text, re.I)
            if not name:name=re.search(r'[、,，]\s*([A-Za-z][A-Za-z -]{0,35}?)\s*(?=[、,，])',text)
            if re.search(r'\b(?:change|set|update)\b',lower) and not re.search(r'recipient|收款人',lower):name=None
            if name and name[1].strip().lower() not in ('gbp','pounds','amount','it'): patch['recipient'] = name[1].strip()
            if state.pending=='form:recipient' and re.fullmatch(r'[A-Za-z][A-Za-z -]{0,45}',text.strip()) and lower.strip() not in ('hello','thanks','no','yes','international','domestic'):
                patch['recipient']=text.strip()
        amount = re.search(r'(?:£|GBP\s*)([+-]?\d[\d,]*(?:\.\d+)?)|([+-]?\d[\d,]*(?:\.\d+)?)\s*(?:英镑|GBP|pounds?)', text, re.I)
        if not amount:
            amount = re.search(r'(?:金额[为是：:]?|改(?:成|为)|change(?:\s+(?:the\s+)?(?:it|amount))?\s+to|amount\s*(?:is|:|=)?)\s*([+-]?\d[\d,]*(?:\.\d+)?)', text, re.I)
        value = next((v for v in amount.groups() if v), None) if amount else None
        if not value and state.pending=='form:amount' and re.fullmatch(r'[+-]?\d+(?:\.\d{1,2})?',text.strip()):value=text.strip()
        if not value:
            han = re.search(r'(?:给\s*[A-Za-z]+\s*(?:模拟国际转账|转账)?|转账|汇款|金额|改成|改为|存入)?\s*([零一二两三四五六七八九十百千万]+)\s*(?:英镑|镑|元|块|(?=[，。;]|$))', text)
            if han: value = chinese_number(han[1])
        if value:
            try: value = format(Decimal(value.replace(',', '')), 'f')
            except InvalidOperation: value = None
            if value: patch['opening_deposit' if service_id == 'open_savings' else 'amount'] = value
    if service_id == 'open_account':
        if re.search(r'学生|student', lower): patch['product'] = 'student_account'
        elif re.search(r'日常|everyday|current account', lower): patch['product'] = 'everyday_account'
        if re.search(r'网上|在线|online', lower): patch['channel'] = 'online'
        elif re.search(r'网点|branch', lower): patch['channel'] = 'branch'
    if service_id=='replace_card':
        if re.search(r'被盗|stolen',lower):patch['reason']='stolen'
        elif re.search(r'损坏|damaged',lower):patch['reason']='damaged'
        elif re.search(r'丢|遗失|挂失|lost|misplaced',lower):patch['reason']='lost'
        if re.search(r'补卡|补办|replace',lower):patch['action']='replace'
        elif re.search(r'冻结|freeze',lower):patch['action']='freeze'
    # Do not create a draft just because a question mentions a product.
    if not patch and not re.search(r'窗口|办理|预约|模拟|申请|改|open|apply|book|simulate|change', lower): return None
    action=update_draft(state, service_id, patch)
    action['_explicit_fields']=clean_prefill(service_id,patch)
    return action
