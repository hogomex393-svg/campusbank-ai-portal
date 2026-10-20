"""Partial demo-form drafts. Drafting never confirms or submits a request."""
import re
from decimal import Decimal, InvalidOperation
from .catalog import SERVICES, service_action
from .language import CITY_ALIASES, canonical_city


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
    total, section, number = 0, 0, 0
    for char in text:
        if char in digits: number = digits[char]
        elif char in units:
            unit = units[char]
            if unit == 10000:
                total += (section + number) * unit; section = number = 0
            else: section += (number or 1) * unit; number = 0
        else: raise ValueError('Unsupported number')
    return str(total + section + number)


def draft_from_message(text, state):
    """Extract explicit common slots; the LLM tool handles broader paraphrases."""
    lower = text.lower()
    service_id = None
    if re.search(r'预约|appointment|book.*branch|visit.*branch', lower): service_id = 'branch_appointment'
    elif re.search(r'转账|汇款|transfer|payment', lower): service_id = 'transfer_demo'
    elif re.search(r'挂失|补卡|卡.*丢|lost.*card|replace.*card', lower): service_id = 'replace_card'
    elif re.search(r'申请.*贷款|贷款申请|apply.*loan', lower): service_id = 'apply_loan'
    elif re.search(r'开.*储蓄|open.*saving', lower): service_id = 'open_savings'
    elif re.search(r'开户|开.*账户|开.*帐户|open.*account|apply.*account', lower): service_id = 'open_account'
    elif state.active_service and re.search(r'改|换|金额|收款人|日期|城市|change|instead|recipient|amount|date|city|^[\w£., -]+$', lower):
        service_id = state.active_service
    if not service_id: return None
    patch = {}
    if service_id == 'branch_appointment':
        for city, aliases in CITY_ALIASES.items():
            if any(a in lower for a in aliases): patch['city'] = city
        date = re.search(r'(20\d{2})\s*(?:年|[-/])\s*(\d{1,2})\s*(?:月|[-/])\s*(\d{1,2})\s*日?', text)
        if date: patch['date'] = f'{date[1]}-{int(date[2]):02}-{int(date[3]):02}'
        purpose = re.search(r'(?:咨询|业务(?:说明)?[：:]?|purpose[: ]+)\s*([^，。;\n]+)', text, re.I)
        if purpose: patch['purpose'] = purpose[1].strip()
        elif 'purpose' not in state.service_drafts.get(service_id, {}) and re.search(r'学生账户|student account', lower):
            patch['purpose'] = '学生账户咨询' if re.search(r'[\u4e00-\u9fff]', text) else 'Student account enquiry'
    if service_id in ('transfer_demo', 'apply_loan', 'open_savings'):
        if service_id == 'transfer_demo':
            if re.search(r'国际|international', lower): patch['transfer_type'] = 'international'
            elif re.search(r'国内|domestic', lower): patch['transfer_type'] = 'domestic'
            name = re.search(r'(?:\bto\s+|\brecipient\s*(?:is|:|=)?\s*|给\s*|收款人(?:改成|换成|为|是|：|:)?\s*)([A-Za-z][A-Za-z -]{0,45}?)(?=\s+(?:£|GBP|[\d]|for\b|an?\s|international\b|domestic\b|simulate\b)|\s*(?:模拟|转账|汇款)|[,，。;]|$)', text, re.I)
            if not name:name=re.search(r'[、,，]\s*([A-Za-z][A-Za-z -]{0,35}?)\s*(?=[、,，])',text)
            if name and name[1].strip().lower() not in ('gbp','pounds','amount','it'): patch['recipient'] = name[1].strip()
        amount = re.search(r'(?:£|GBP\s*)([+-]?\d[\d,]*(?:\.\d+)?)|([+-]?\d[\d,]*(?:\.\d+)?)\s*(?:英镑|GBP|pounds?)', text, re.I)
        if not amount:
            amount = re.search(r'(?:金额[为是：:]?|改(?:成|为)|change(?:\s+(?:it|amount))?\s+to|amount\s*(?:is|:|=)?)\s*([+-]?\d[\d,]*(?:\.\d+)?)', text, re.I)
        value = next((v for v in amount.groups() if v), None) if amount else None
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
    # Do not create a draft just because a question mentions a product.
    if not patch and not re.search(r'窗口|办理|预约|模拟|申请|改|open|apply|book|simulate|change', lower): return None
    action=update_draft(state, service_id, patch)
    action['_explicit_fields']=clean_prefill(service_id,patch)
    return action
