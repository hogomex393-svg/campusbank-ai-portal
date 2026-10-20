"""Gather independently requested facts without treating missing policy as no limit."""
import re
from .dialogue import PRODUCT_ALIASES, attributes_of

LABELS = {
    'documents':('Required documents','所需材料'),'fees':('Fees','费用'),
    'eligibility':('Eligibility','资格'),'rate':('Interest rate','利率'),
    'apply':('How to apply','办理方式'),'minimum':('Minimum opening deposit','最低开户存款'),
    'payment':('Interest payments','利息发放'),
}

def requested_products(text, fallback=None):
    lower=text.lower()
    products=[p for p,aliases in PRODUCT_ALIASES.items() if any(a in lower for a in aliases)]
    return products or ([fallback] if fallback else [])

def policy_facts(text, prepared, knowledge, retriever, threshold):
    """Collect each requested attribute and unrelated transfer facts separately."""
    language=prepared.state.language
    attrs=attributes_of(text)
    products=requested_products(text,prepared.state.product)
    parts=[];sources=[];records=[]
    for product in products:
        record=next((r for r in knowledge.products if r['product_name']==product),None)
        if not record:continue
        for attr in attrs:
            # Fee words may refer to a separate transfer question, not product fees.
            if attr=='fees' and re.search(r'国际转账|international transfer',text,re.I) and not re.search(r'月费|年费|monthly|annual fee',text,re.I):continue
            value=record.get(attr+'_zh' if language=='zh' else attr)
            if not value:
                matches=[h for h in retriever.search(product.replace('_',' ')+' '+attr,product=product) if h['score']>=threshold and h.get('attribute')==attr]
                value=matches[0].get('answer_zh' if language=='zh' else 'answer') if matches else None
            if value:
                title=record.get('display_name_zh' if language=='zh' else 'display_name',product)
                label=LABELS[attr][1 if language=='zh' else 0]
                parts.append((title+' · '+label,value));sources.append(record['source_id']);records.append(record)
            elif attr=='minimum':
                parts.append((LABELS[attr][1 if language=='zh' else 0],
                    '资料未说明这个产品的最低开户存款，不能据此认为没有限制。' if language=='zh' else 'The demo records do not specify this product’s minimum deposit; this does not mean there is no limit.'))
    if re.search(r'国际.*(?:转账|汇款)|international.*transfer',text,re.I) and re.search(r'费|cost|fee|charge',text,re.I):
        matches=[h for h in retriever.search('international transfer fee') if h['score']>=threshold]
        if matches:
            hit=matches[0];parts.append(('国际转账费用' if language=='zh' else 'International transfer fee',hit['answer_zh' if language=='zh' else 'answer']))
            sources.append(hit['faq_id']);records.append(hit)
    # Preserve order while removing repeated records.
    unique={r.get('source_id',r.get('faq_id')):r for r in records}
    return parts,list(dict.fromkeys(sources)),list(unique.values())


def product_comparison(text,prepared,knowledge):
    products=requested_products(text)
    if len(products)<2 or not re.search(r'比较|对比|哪个好|区别|compare|better|difference|versus|\bvs\b',text,re.I):return None
    records=[r for r in knowledge.products if r['product_name'] in products]
    language=prepared.state.language
    def local(r,key):return r.get(key+'_zh' if language=='zh' else key,'资料未说明' if language=='zh' else 'Not specified')
    headers=['项目' if language=='zh' else 'Feature']+[local(r,'display_name') for r in records]
    lines=['| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |']
    for attr in ('fees','eligibility','documents','rate'):
        cells=[LABELS[attr][1 if language=='zh' else 0]]+[local(r,attr).replace('|','/').replace('\n',' ') for r in records]
        lines.append('| '+' | '.join(cells)+' |')
    return '\n'.join(lines),[r['source_id'] for r in records],records
