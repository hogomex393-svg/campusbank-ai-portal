"""Fictional student-finance directory; never presented as a real award or policy."""
PROGRAMS = [
 {'id':'DEMO_EDUCATION_LOAN','kind':'loan','title':'学费与生活费支持贷款（演示）','title_en':'Tuition and living-cost loan (demo)',
  'summary':'面向年满18岁的在读学生，可登记学费或生活费贷款意向。金额、利率和还款计划需工作人员另行审核；提交不代表获批。',
  'summary_en':'Students aged 18+ can record a tuition or living-cost loan enquiry. Amount, rate and repayment terms require staff review; submission is not approval.',
  'documents':'演示身份证明、在读证明、用途及预算说明。无需上传真实证件或账户资料。',
  'documents_en':'Example identity/student-status evidence and a purpose/budget summary. Do not upload real identity or account documents.',
  'repayment':'本金按最终演示条款偿还；是否计息、费用和期限均待审核，不默认免息，也不默认必定收息。',
  'repayment_en':'Principal follows the final demo terms; interest, charges and term await review. Neither interest-free treatment nor mandatory interest is assumed.',
  'amount':'按演示申请登记金额，条款待审核','amount_en':'Requested demo amount; terms subject to review',
  'levels':['undergraduate','postgraduate'],'service_id':'education_loan'},
 {'id':'DEMO_MERIT_SCHOLARSHIP','kind':'scholarship','title':'学业发展奖学金（演示）','title_en':'Academic development scholarship (demo)',
  'summary':'演示目录面向本科和研究生，参考学习计划及学业总结。需要向学校确认实际项目，本目录不代表任何学校真实名额。',
  'summary_en':'A fictional undergraduate/postgraduate program based on a study plan and academic summary. Confirm real awards with the institution; this directory does not represent actual places.',
  'documents':'演示在读状态、学业总结及学习计划。','documents_en':'Example student status, academic summary and study plan.',
  'amount':'演示参考 £500–£1,500，一次性，非真实承诺','amount_en':'Fictional GBP 500–1,500 once; no real award commitment',
  'levels':['undergraduate','postgraduate'],'service_id':'funding_enquiry'},
 {'id':'DEMO_NEED_GRANT','kind':'grant','title':'学习生活补助（演示）','title_en':'Study and living-cost grant (demo)',
  'summary':'用于展示按生活预算及学习需要查询补助的流程。工作人员只处理演示咨询，不判断真实助学资格，也不会发放资金。',
  'summary_en':'Demonstrates enquiries about study needs and living budgets. Staff handle a demo enquiry without determining real eligibility or disbursing money.',
  'documents':'演示在读状态、预算说明及需要帮助的事项。','documents_en':'Example student status, budget summary and support needs.',
  'amount':'演示参考最高 £800，是否符合需另行核实','amount_en':'Fictional reference up to GBP 800; real eligibility must be checked separately',
  'levels':['undergraduate','postgraduate'],'service_id':'funding_enquiry'},
 {'id':'DEMO_EMERGENCY_GRANT','kind':'emergency','title':'临时困难援助（演示）','title_en':'Emergency student support (demo)',
  'summary':'展示临时困难咨询与人工转接流程；若是实际紧急情况，应直接联系学校正式学生支持部门。',
  'summary_en':'Demonstrates an urgent-support enquiry and human handoff. For a real urgent situation, contact the institution’s official student-support service.',
  'documents':'演示情况摘要；无需敏感证明文件。','documents_en':'An example situation summary; no sensitive evidence files.',
  'amount':'演示参考最高 £300，不构成实际资助承诺','amount_en':'Fictional reference up to GBP 300; no real funding commitment',
  'levels':['undergraduate','postgraduate'],'service_id':'funding_enquiry'},
]

def search_funding(query='',level=None,kind=None):
    text=query.lower()
    if not kind:
        if any(w in text for w in ('贷款','loan')) and any(w in text for w in ('奖学金','scholarship','补助','grant')):kind='all'
        elif any(w in text for w in ('奖学金','scholarship')) and any(w in text for w in ('补助','助学金','grant')):kind='awards'
        elif any(word in text for word in ('助学贷款','学贷','education loan','student loan','tuition loan')):kind='loan'
        elif any(word in text for word in ('奖学金','scholarship')) and not any(word in text for word in ('补助','grant')):kind='scholarship'
        elif any(word in text for word in ('补助','助学金','grant')):kind='grants'
    return [dict(row) for row in PROGRAMS if (not level or level in row['levels']) and
            (not kind or kind=='all' or row['kind']==kind or kind=='grants' and row['kind'] in ('grant','emergency') or kind=='awards' and row['kind']!='loan')]

def is_funding_question(text,bank_mode='general'):
    import re
    return bool(re.search(r'助学|学贷|奖学金|补助|资助|scholarship|student loan|education loan|tuition loan|student.*(?:grant|funding)|financial aid',text,re.I)
                or re.search(r'(?:学费|生活费|tuition|living cost).*(?:支持|帮助|贷款|付不起|怎么办|support|funding|afford)',text,re.I)
                or bank_mode=='student' and re.search(r'经济.*(?:困难|压力)|付不起|financial difficult|struggling.*(?:pay|money)',text,re.I))

def funding_answer(text,language):
    rows=search_funding(text)
    intro='以下是学生银行的虚构演示项目，用于课程展示，并非真实国家或学校政策。' if language=='zh' else 'These are fictional student-banking programs for the coursework demo, not real government or university policies.'
    pieces=[intro]
    for row in rows:
        title=row['title'] if language=='zh' else row['title_en']
        pieces.append('**'+title+'**\n'+row['summary' if language=='zh' else 'summary_en']+'\n\n'+
                      ('参考额度：' if language=='zh' else 'Reference amount: ')+row['amount' if language=='zh' else 'amount_en']+'\n\n'+
                      ('准备材料：' if language=='zh' else 'Documents to prepare: ')+row['documents' if language=='zh' else 'documents_en'])
    return '\n\n'.join(pieces),[r['id'] for r in rows],rows
