"""Deterministic Chinese/English selection and local response translations."""
import re

CITY_ALIASES = {
    "Lancaster": ("lancaster", "兰开斯特", "兰卡斯特"),
    "London": ("london", "伦敦"),
    "Manchester": ("manchester", "曼彻斯特", "曼城"),
}
CITY_ZH = {"Lancaster": "兰开斯特", "London": "伦敦", "Manchester": "曼彻斯特"}
NEUTRAL_ENTITIES = {"student_account", "everyday_account", "savings_account", "debit_card", "credit_card", "personal_loan", "campusbank"}


def detect_language(text: str, previous: str = "en") -> str:
    """Mixed messages follow their dominant prose; neutral names inherit history."""
    text = text.strip()
    han = len(re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff]", text))
    if han:
        words = re.findall(r"[A-Za-z]+", text)
        # An English question containing a Chinese product name remains English.
        return "en" if len(words) >= 4 and 2 * len(words) > han else "zh"
    cleaned = text.lower().strip(" .!?，。？！")
    cities = {a for aliases in CITY_ALIASES.values() for a in aliases}
    if not text or cleaned in cities | NEUTRAL_ENTITIES or not re.search(r"[A-Za-z]", text):
        return previous if previous in ("zh", "en") else "en"
    return "en"


def canonical_city(value: str) -> str:
    for city, aliases in CITY_ALIASES.items():
        if value.casefold().strip() in aliases:
            return city
    return value.strip()


MESSAGES = {
    "empty": ("Please enter a banking question.", "请输入一个银行业务问题。"),
    "too_long": ("Please shorten your question to 2,000 characters.", "请将问题缩短到 2000 个字符以内。"),
    "greeting": ("Hello! I can help with CampusBank accounts, cards, transfers and branches. What would you like to know?", "你好！我可以介绍 CampusBank 的账户、银行卡、转账和网点服务。你想了解哪方面？"),
    "city": ("Which city would you like to visit? Our demo branches are in Lancaster, London and Manchester.", "你想查询哪个城市的网点？演示网点位于兰开斯特、伦敦和曼彻斯特。"),
    "product": ("Which product do you mean: a student account, everyday account, savings account, debit card, credit card or personal loan?", "你想了解哪种产品：学生账户、日常账户、储蓄账户、借记卡、信用卡还是个人贷款？"),
    "unknown": ("I don't have enough CampusBank information to answer that. I can help with accounts, cards, transfers, savings, loans, online banking, branches and customer support.", "当前 CampusBank 演示资料不足以回答这个问题。我可以介绍账户、银行卡、转账、储蓄、贷款、网上银行、网点和客服流程。"),
    "empty_answer": ("I don't have enough information to answer that.", "当前资料不足以回答这个问题。"),
}


def local_message(key: str, language: str) -> str:
    return MESSAGES[key][1 if language == "zh" else 0]
