"""User-controlled next-question suggestions; no extra model call or automatic action."""
import re

def suggested_questions(text,state,actions,language):
    zh=language=='zh';lower=text.lower();service=next((a['service_id'] for a in actions if a.get('service_id')),state.active_service)
    if re.search(r'转人工|人工客服|human support|live agent',lower):return []
    if service=='education_loan' or re.search(r'助学贷款|学贷|student loan|education loan',lower):
        pairs=[('助学贷款需要准备哪些材料？','What documents should I prepare for a student loan?'),('贷款还款和利率要怎么确认？','How can I confirm repayment terms and interest?'),('贷款和奖学金补助有什么区别？','How do student loans differ from scholarships and grants?')]
    elif service=='funding_enquiry' or re.search(r'奖学金|补助|scholarship|grant',lower):
        pairs=[('我该先比较奖学金还是助学补助？','Should I compare scholarships or need-based grants first?'),('可以按本科或研究生筛选项目吗？','Can I filter programs by undergraduate or postgraduate level?'),('这些项目需要哪些材料？','What documents do these programs need?')]
    elif service=='transfer_demo' or re.search(r'转账|transfer',lower):
        pairs=[('国内和国际转账的费用有什么区别？','How do domestic and international transfer fees differ?'),('帮我准备一笔演示转账，我需要提供什么？','What do I need to prepare a demo transfer?'),('提交后在哪里查看处理进度？','Where can I track progress after submitting?')]
    elif service=='replace_card' or re.search(r'丢|挂失|lost|stolen',lower):
        pairs=[('补卡费用是多少？','How much does a replacement card cost?'),('演示冻结和真实冻结有什么区别？','How does a demo freeze request differ from a real freeze?'),('需要人工客服帮忙核对吗？','Can a staff member help review my request?')]
    elif re.search(r'办.*卡|bank card|debit|credit',lower) and not state.product:
        pairs=[('主要用于日常消费，应该怎么选？','What should I choose for everyday spending?'),('学生用于学费和生活费，应该怎么选？','What suits a student paying tuition and living costs?'),('借记卡和信用卡有什么区别？','How do debit and credit cards differ?')]
    elif state.product or service=='open_account':
        pairs=[('开户需要哪些材料？','What documents do I need to open an account?'),('月费和最低存款要注意什么？','What should I know about fees and minimum deposits?'),('怎样在线办理并查看申请进度？','How can I apply online and track the request?')]
    elif state.bank_mode=='student':
        pairs=[('我想了解学费和生活费支持。','What support is available for tuition and living costs?'),('查询奖学金和助学补助。','Show me scholarships and student grants.'),('学生账户适合哪些日常用途？','What everyday needs does a student account cover?')]
    else:
        pairs=[('日常收付款应该选什么账户？','Which account suits everyday payments?'),('我想比较储蓄和贷款服务。','Can I compare savings and loan services?'),('帮我找到合适的在线办理入口。','Help me find the right online service.')]
    previous={m.get('content','').strip() for turn in state.turns for m in turn if m.get('role')=='user'}
    recent=' '.join(m.get('content','') for turn in state.turns[-2:] for m in turn if m.get('role')=='user')
    asked_materials=bool(re.search(r'材料|证明|documents?|paperwork',recent,re.I))
    asked_fees=bool(re.search(r'月费|费用|手续费|fees?|charges?',recent,re.I))
    asked_repayment=bool(re.search(r'利率|还款|repay|interest',recent,re.I))
    questions=[]
    for pair in pairs:
        question=pair[0 if zh else 1]
        if question in previous:continue
        if asked_materials and re.search(r'材料|documents?',question,re.I):continue
        if asked_fees and re.search(r'费用|月费|fees?',question,re.I):continue
        if asked_repayment and re.search(r'利率|还款|repay|interest',question,re.I):continue
        questions.append(question)
    extras=[('怎样让工作人员继续跟进？','How can staff follow up on my request?'),
            ('怎样比较其他适合我的服务？','How can I compare other services that might suit my needs?'),
            ('怎样核对演示表单后再决定是否提交？','How can I review a demo form before deciding whether to submit?')]
    for pair in extras:
        question=pair[0 if zh else 1]
        if question not in previous and question not in questions:questions.append(question)
    return questions[:3]
