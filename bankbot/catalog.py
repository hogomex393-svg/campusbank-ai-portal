"""Approved local service windows. Every submission is a fictional demo request."""

CATEGORIES = [
    {"id":"accounts","name":"账户与开户","en":"Accounts","icon":"wallet"},
    {"id":"cards","name":"银行卡服务","en":"Cards","icon":"card"},
    {"id":"payments","name":"转账支付","en":"Payments","icon":"transfer"},
    {"id":"savings","name":"储蓄与存款","en":"Savings","icon":"savings"},
    {"id":"loans","name":"贷款服务","en":"Loans","icon":"loan"},
    {"id":"support","name":"客服与网点","en":"Support","icon":"support"},
]

def field(name,label,type_="text",options=None,required=True):
    return {"name":name,"label":label,"type":type_,"options":options or [],"required":required}

def option(value,label):return {"value":value,"label":label}

SERVICES = {
    "open_account":{"id":"open_account","category":"accounts","title":"在线开户申请","en":"Open an account","description":"选择账户，核对材料，登记演示申请。","icon":"wallet",
        "fields":[field("product","账户类型","select",[option("student_account","学生账户 · 无月费"),option("everyday_account","日常账户 · 月费 £3")]),field("applicant","申请人称呼（演示）"),field("channel","办理渠道","select",[option("online","网上申请"),option("branch","网点办理")]),field("documents_ready","已了解身份证件、地址证明及产品材料要求","checkbox")],
        "notice":"本窗口登记课程演示申请；提交后等待审核，不会开立真实银行账户。"},
    "apply_card":{"id":"apply_card","category":"cards","title":"银行卡申请","en":"Apply for a card","description":"申请配套借记卡，或登记信用卡审核申请。","icon":"card",
        "fields":[field("card_type","银行卡类型","select",[option("debit_card","借记卡"),option("credit_card","信用卡")]),field("linked_product","配套账户","select",[option("student_account","学生账户"),option("everyday_account","日常账户")]),field("purpose","使用用途（演示）"),field("reviewed","已核对申请条件与资料要求","checkbox")],"notice":"信用卡申请只登记待审核请求，本系统不会自动批准授信。"},
    "replace_card":{"id":"replace_card","category":"cards","title":"挂失与补卡服务","en":"Lost or damaged card","description":"登记挂失、冻结或补卡演示请求。","icon":"shield",
        "fields":[field("reason","办理原因","select",[option("lost","卡片遗失"),option("stolen","卡片被盗"),option("damaged","卡片损坏")]),field("action","服务选择","select",[option("freeze","登记冻结请求"),option("replace","申请补卡（演示费 £5）")]),field("note","情况说明","textarea",required=False)],"notice":"不会操作真实银行卡，也不需要填写卡号或 PIN。"},
    "transfer_demo":{"id":"transfer_demo","category":"payments","title":"转账服务窗口","en":"Transfer request","description":"核对收款信息与费用，登记模拟付款。","icon":"transfer",
        "fields":[field("transfer_type","转账类型","select",[option("domestic","国内转账 · 免费"),option("international","国际转账 · 演示费 £8")]),field("recipient","演示收款人昵称"),field("amount","演示金额（GBP）","number"),field("note","附言","textarea",required=False)],"notice":"只记录模拟转账，不扣款，不连接真实支付系统。"},
    "open_savings":{"id":"open_savings","category":"savings","title":"储蓄账户申请","en":"Open savings","description":"了解演示利率并登记储蓄账户申请。","icon":"savings",
        "fields":[field("applicant","申请人称呼（演示）"),field("opening_deposit","演示开户存款（GBP，至少 10）","number"),field("reviewed","已了解无月费、演示年利率 2% 与取款规则","checkbox")],"notice":"资金不会实际存入；2% 为本项目虚构政策，并非银行报价。"},
    "apply_loan":{"id":"apply_loan","category":"loans","title":"个人贷款申请","en":"Loan application","description":"登记申请意向，交由演示审核队列处理。","icon":"loan",
        "fields":[field("applicant","申请人称呼（演示）"),field("amount","演示贷款金额（GBP）","number"),field("purpose","贷款用途（演示）"),field("reviewed","已了解材料要求与偿还能力审核流程","checkbox")],"notice":"提交不代表审批通过。本窗口不会进行真实信用评估。"},
    "branch_appointment":{"id":"branch_appointment","category":"support","title":"网点服务预约","en":"Branch appointment","description":"选择城市与日期，登记待确认预约。","icon":"location",
        "fields":[field("city","预约城市","select",[option("Lancaster","兰开斯特"),option("London","伦敦"),option("Manchester","曼彻斯特")]),field("date","希望到访的日期","date"),field("purpose","希望办理的业务")],"notice":"预约进入待确认队列；不是实际网点预约。"},
    "human_support":{"id":"human_support","category":"support","title":"转接人工客服","en":"Human support","description":"带上对话上下文，创建客服工单。","icon":"support",
        "fields":[field("category","问题类型","select",[option("accounts","账户"),option("cards","银行卡"),option("payments","转账"),option("savings","储蓄"),option("loans","贷款"),option("digital","网上银行"),option("other","其他")]),field("subject","问题标题"),field("description","需要工作人员帮助的内容","textarea")],"notice":"转入本地演示客服队列。工作人员可在工作台接单并回复。"},
    "digital_help":{"id":"digital_help","category":"accounts","title":"网上银行协助","en":"Digital banking help","description":"登录、密码找回或网上办理问题的协助请求。","icon":"shield",
        "fields":[field("issue","问题类型","select",[option("login","无法登录"),option("password","密码找回流程"),option("application","网上申请协助")]),field("description","问题说明","textarea")],"notice":"请勿填写密码或验证码。本窗口不会修改实际登录凭据。"},
}

BANK_REFERENCES = [
    {"name":"HSBC UK","url":"https://www.hsbc.co.uk/","detail":"账户、储蓄、银行卡与贷款的业务分类"},
    {"name":"HSBC 帮助中心","url":"https://www.hsbc.co.uk/help/","detail":"按问题进入银行卡、支付和数字银行帮助"},
    {"name":"NatWest Cora","url":"https://www.natwest.com/support-centre/cora.html","detail":"对话咨询、追问与工作人员转接"},
    {"name":"中国银行个人金融","url":"https://www.bankofchina.com/pbservice/","detail":"存款账户、个人贷款、汇兑与银行卡入口"},
]

def service_action(id_):
    s=SERVICES.get(id_)
    if not s:return None
    return {"service_id":s['id'],"title":s['title'],"title_en":s['en'],"category":s['category'],"description":s['description']}
