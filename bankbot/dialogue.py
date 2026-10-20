"""Explicit session state and small, inspectable clarification rules."""
from dataclasses import dataclass, field
from copy import deepcopy
import re
from .language import CITY_ALIASES, canonical_city, detect_language, local_message

PRODUCT_ALIASES = {
    "student_account": ("student account", "student bank account", "student banking", "学生账户", "学生帐户", "学生开户"),
    "everyday_account": ("everyday account", "current account", "checking account", "日常账户", "普通账户", "活期账户"),
    "savings_account": ("savings account", "saving account", "savings", "储蓄账户", "储蓄帐户", "储蓄"),
    "debit_card": ("debit card", "bank card", "借记卡", "储蓄卡", "银行卡"),
    "credit_card": ("credit card", "信用卡"),
    "personal_loan": ("personal loan", "个人贷款"),
}


@dataclass
class State:
    # Each item is one complete turn, including paired tool-call messages.
    turns: list[list[dict]] = field(default_factory=list)
    product: str | None = None
    topic: str | None = None
    city: str | None = None
    pending: str | None = None
    language: str = "en"
    service_drafts: dict = field(default_factory=dict)
    active_service: str | None = None

    def messages(self, limit: int) -> list[dict]:
        return [deepcopy(m) for turn in self.turns[-limit:] for m in turn]


def coerce_state(value=None) -> State:
    """Rebuild current state from JSON or an object left by a code hot reload."""
    if value is None:
        return State()
    def get(name, default=None):
        return value.get(name, default) if isinstance(value, dict) else getattr(value, name, default)
    return State(turns=deepcopy(get("turns", [])), product=get("product"),
                 topic=get("topic"), city=get("city"), pending=get("pending"),
                 language=get("language", "en"),service_drafts=deepcopy(get('service_drafts',{})),
                 active_service=get('active_service'))


@dataclass
class Prepared:
    text: str
    query: str
    state: State
    clarification: str | None = None
    attribute: str | None = None
    branch_lookup: bool = False


ATTRIBUTE_PATTERNS = {
        "minimum": r"minimum.*deposit|opening deposit|money.*start|最低.*(?:存款|存入)|起存|开户存款",
        "payment": r"(?:when|how often).*interest|interest.*(?:paid|credited)|利息.*(?:发放|到账|结算)|(?:多久|什么时候).*利息",
        "documents": r"document|paperwork|bring|proof|material|identification|what do i need|材料|证件|证明|需要带|要带什么",
        "fees": r"\bfee|\bcost|charge|how much|monthly|\bfree\b|费用|收费|手续费|月费|年费|多少钱|免费",
        "eligibility": r"eligible|eligibility|qualify|age|who can|requirement|年龄|资格|条件|谁能|谁可以|几岁|岁.*(?:能|可以)",
        "rate": r"interest|\brate\b|apr|apy|利率|利息",
        "apply": r"apply|application|sign up|open|set up|申请|开户|开通|办理账户|开个",
}

def attributes_of(text):
    return [a for a, pattern in ATTRIBUTE_PATTERNS.items() if re.search(pattern,text.lower())]

def attribute_of(text: str) -> str | None:
    return next(iter(attributes_of(text)),None)


def prepare_turn(text: str, old_state: State) -> Prepared:
    state = deepcopy(old_state)
    state.language = detect_language(text, getattr(old_state, "language", "en"))
    lowered = text.lower().strip()
    explicit = next((p for p, aliases in PRODUCT_ALIASES.items()
                     if any(a in lowered for a in aliases)), None)
    city = next((c for c, aliases in CITY_ALIASES.items() if any(a in lowered for a in aliases)), None)
    # Recognise an unknown city when a branch request supplies one.
    location = re.search(r"\b(?:in|near)\s+([a-z][a-z ]{1,35})[?.!]*$", lowered)
    if city:
        state.city = city
    elif location and re.search(r"branch|office|atm", lowered):
        state.city = location.group(1).strip().title()
    elif re.search(r"网点|分行|支行", lowered):
        location_zh = re.search(r"(?:在|位于)([\u4e00-\u9fff]{2,8}?)(?:有|附近|的|吗|么|网点|分行|支行)", lowered)
        if location_zh:
            state.city = canonical_city(location_zh.group(1))
    attr = attribute_of(lowered)
    # A new, explicit domain overrides a product left by a previous turn.
    branch_request = bool(re.search(r"branch|\batm\b|opening hours|office|网点|分行|支行|营业时间|银行地址|开门|关门|营业|取款机", lowered))
    generic_branch = bool(re.search(r"appointment|holiday|wheelchair|accessible|step.free|weekend|saturday|sunday|\batm\b|cash machine|预约|节假日|轮椅|无障碍|周末|星期六|周六|周日|取款机", lowered))
    branch_lookup = branch_request and not generic_branch and bool(re.search(r"where|nearest|near|locat|opening hours|branch.*(?:close|open)|(?:hours|address).*branch|哪里|在哪|最近|附近|地址|营业时间|几点|开门|关门|营业", lowered) or city)
    payment_request = bool(re.search(r"transfer|payment|\bswift\b|iban|转账|汇款|支付", lowered))
    support_request = bool(re.search(r"complain|complaint|contact|helpline|human|support|投诉|客服|人工|联系银行", lowered))
    card_problem = bool(re.search(r"\b(?:lost|stolen|misplaced|freeze|pin)\b|挂失|丢卡|卡丢|冻结|银行卡.*(?:丢|遗失|被盗)|借记卡.*(?:丢|遗失|被盗)", lowered))
    if explicit:
        state.product = explicit
        state.topic = "products"
    elif card_problem:
        state.product = "debit_card"
        state.topic = "cards"
    elif branch_request:
        state.product = None
        state.topic = "branches"
    elif payment_request:
        state.product = None
        state.topic = "payments"
    elif support_request:
        state.product = None
        state.topic = "support"
    elif re.search(r"password|login|online banking|banking app|密码|登录|网上银行|网银|手机银行", lowered):
        state.product = None
        state.topic = "digital"
    elif re.search(r"loan|贷款", lowered):
        state.product = "personal_loan"
        state.topic = "products"
    elif state.pending == "city":
        state.city = canonical_city(text.strip().rstrip(".!?。？！"))
        state.topic = "branches"
    previous_pending = state.pending
    state.pending = None
    query = text
    if previous_pending and previous_pending.startswith("product:") and explicit:
        attr = previous_pending.split(":", 1)[1]
        query = f"{explicit.replace('_', ' ')} {attr}"
    elif state.topic == "branches" and (previous_pending == "city" or (city and lowered.rstrip('.!?') == city.lower())):
        query = f"branch opening hours in {state.city}"
    elif state.product and attr:
        query = f"{state.product.replace('_', ' ')} {attr} {text}"
    branch_lookup = branch_lookup or previous_pending == "city"
    if branch_lookup and not state.city:
        state.pending = "city"
        return Prepared(text, query, state, local_message("city", state.language), attr, True)
    ambiguous = bool(re.search(r"how much|\bfees?\b|what documents|what should i bring|多少钱|费用|月费|年费|手续费|收费|材料|要带什么|需要带", lowered))
    if ambiguous and not state.product and state.topic not in ("payments", "branches", "digital", "support"):
        state.pending = "product:" + (attr or "fees")
        return Prepared(text, query, state, local_message("product", state.language), attr)
    return Prepared(text, query, state, attribute=attr, branch_lookup=branch_lookup)
