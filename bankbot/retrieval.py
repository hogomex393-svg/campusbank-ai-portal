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

    def search(self, query: str, k: int = 3, product: str | None = None) -> list[dict]:
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
        if product:
            allowed = [i for i in ranked if self.faq[i].get("product") in (product, "")]
            ranked = allowed
        return [dict(self.faq[i], score=round(float(scores[i]), 6)) for i in ranked[:k]]
