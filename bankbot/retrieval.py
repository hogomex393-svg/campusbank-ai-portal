"""Hybrid word/character TF-IDF retrieval over FAQ questions and aliases."""
import re
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from .language import detect_language

REPLACEMENTS = {
    "charges": "fees", "charge": "fee", "costs": "fees", "cost": "fee",
    "paperwork": "documents", "identification": "id", "set up": "open",
    "stolen": "lost", "misplaced": "lost", "lose": "lost", "locked out": "login problem",
    "overseas": "international", "abroad": "international", "cash machine": "atm",
    "shut": "close", "terminate": "close", "timetable": "opening hours",
}

CHINESE_TERMS = {
    "学生账户": "student account", "学生帐户": "student account", "日常账户": "everyday account", "普通账户": "everyday account",
    "储蓄账户": "savings account", "储蓄帐户": "savings account", "个人贷款": "personal loan", "信用卡": "credit card", "借记卡": "debit card", "银行卡": "debit card",
    "营业时间": "opening hours", "国际转账": "international transfer", "国内转账": "domestic transfer", "网上银行": "online banking",
    "身份证明": "photo id", "学生证明": "student status", "地址证明": "proof of address", "收入证明": "proof of income",
    "手续费": "fee", "月费": "monthly fee", "年费": "annual fee", "费用": "fees", "材料": "documents", "利率": "interest rate",
    "挂失": "lost card", "遗失": "lost", "丢了": "lost", "被盗": "stolen", "补办": "replacement", "激活": "activate",
    "投诉": "complaint", "网点": "branch", "分行": "branch", "转账": "transfer", "密码": "password", "忘记": "forgot",
}


def normalize(text: str) -> str:
    text = text.lower().strip()
    for old, new in REPLACEMENTS.items():
        text = re.sub(r"\b" + re.escape(old) + r"\b", new, text)
    for old, new in CHINESE_TERMS.items():
        text = text.replace(old, " " + new + " ")
    return re.sub(r"\s+", " ", text)


class Retriever:
    def __init__(self, faq: list[dict]):
        self.faq = faq
        self.indexes = {}
        # Separate document frequencies preserve the original English retrieval.
        # Both indexes still return the same canonical FAQ IDs.
        for language in ("en", "zh"):
            rows, texts = [], []
            for index, record in enumerate(faq):
                if language == "en":
                    questions = [record["question"], *record["aliases"]]
                elif record.get("question_zh"):
                    questions = [record["question_zh"], *record.get("aliases_zh", [])]
                else:
                    continue
                for question in questions:
                    texts.append(normalize(question)); rows.append(index)
            if texts:
                word = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True)
                char = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5))
                self.indexes[language] = (rows, word, char, word.fit_transform(texts), char.fit_transform(texts))

    def search(self, query: str, k: int = 3, product: str | None = None,exclude_loan=False) -> list[dict]:
        from .dialogue import PRODUCT_ALIASES,attributes_of
        text=query.lower()
        explicit={p for p,aliases in PRODUCT_ALIASES.items() if any(a in text for a in aliases)}
        products=explicit or ({product} if product else set())
        topics=set()
        for p in products:topics.add('accounts' if p.endswith('_account') and p!='savings_account' else 'savings' if p=='savings_account' else 'loans' if p=='personal_loan' else 'cards')
        for topic,pattern in [('payments',r'transfer|payment|转账|汇款'),('branches',r'branch|opening hours|网点|营业时间'),('cards',r'lost|stolen|freeze|replacement|挂失|补办|补卡|冻结'),('digital',r'login|password|登录|密码'),('support',r'complaint|human support|投诉|人工客服')]:
            if re.search(pattern,text):topics.add(topic)
        language = detect_language(query)
        query = normalize(query)
        if not query:
            return []
        # L2-normalised TF-IDF dot products equal cosine similarity.
        rows, word, char, word_matrix, char_matrix = self.indexes.get(language, self.indexes["en"])
        w = (word_matrix @ word.transform([query]).T).toarray().ravel()
        c = (char_matrix @ char.transform([query]).T).toarray().ravel()
        scores = np.zeros(len(self.faq))
        for index, score in zip(rows, 0.8 * w + 0.2 * c):
            scores[index] = max(scores[index], float(score))
        ranked = sorted(range(len(scores)), key=lambda i: (-scores[i], self.faq[i]["faq_id"]))
        if products:ranked=[i for i in ranked if self.faq[i].get('product') in products or not self.faq[i].get('product') and self.faq[i]['topic'] in topics]
        elif topics:ranked=[i for i in ranked if self.faq[i]['topic'] in topics]
        if exclude_loan:ranked=[i for i in ranked if self.faq[i]['topic']!='loans']
        procedural=set()
        for attribute,pattern in [('lost',r'\blost\b|stolen|freeze|挂失|遗失|丢|冻结'),('replacement',r'replac|damaged|补办|补卡|损坏'),('pin',r'\bpin\b'),('activate',r'activat|激活'),('declined',r'declin|拒付')]:
            if re.search(pattern,text):procedural.add(attribute)
        wanted=procedural or set(attributes_of(text))
        if wanted:
            matching=[i for i in ranked if self.faq[i].get('attribute') in wanted]
            if matching:ranked=matching
        return [dict(self.faq[i], score=round(float(scores[i]), 6)) for i in ranked[:k]]
