"""Narrow checks for confirmed UI/answer contradictions from the group review."""
import re
from decimal import Decimal

def conflicts(answer,constraints,has_quote=False):
    issues=[]
    if has_quote and re.search(r'(?:汇率|外汇|\bfx\b|exchange).{0,35}(?:不在.{0,12}演示范围|不支持.{0,10}换算|outside.{0,15}(?:demo|scope)|not.{0,20}(?:demo scope|supported))',answer,re.I):issues.append('The portal supports fixed fictional FX quotes; use the calculator values.')
    if (constraints or {}).get('exclude_loan') and re.search(r'(?<!不)(?:推荐|建议|可以申请|进入).{0,8}(?:助学贷款|贷款申请)|(?:you can apply|recommend|open the).{0,20}(?:student loan|loan application)',answer,re.I):issues.append('The customer excluded loans. Offer only non-repayable funding services.')
    if re.search(r'(?:同时|默认|已).{0,5}勾选.{0,25}(?:奖学金.{0,10}(?:和|及).{0,5}补助|scholarship)|selected both|checked both',answer,re.I):issues.append('funding_type is single-select: all, scholarship or grants. Do not claim two boxes were checked.')
    if isinstance(has_quote,dict):
        plain=re.sub(r'[*_`#,]','',answer)
        for key,pattern in [('total',r'总扣款|合计扣款|合计扣除|total debit|total deducted'),('fee',r'转账手续费|国际转账费用|手续费|transfer fee'),('receive_amount',r'预计到账|预计收款|estimated recipient amount')]:
            found=re.search(r'(?:'+pattern+r')[^\d]{0,24}(\d+(?:\.\d{1,2})?)',plain,re.I)
            if found and Decimal(found[1])!=Decimal(has_quote[key]):issues.append(f'The labelled {key} must equal the canonical quote {has_quote[key]}.')
    return issues
