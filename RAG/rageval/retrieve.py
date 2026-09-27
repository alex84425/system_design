"""檢索器。每個都實作同一個介面，方便在評估腳本裡直接對調比較。

介面：search(query, k) -> [(doc_id, score), ...]  依分數由高到低

目前有兩個純詞彙式（lexical）的基準線，都不需要 GPU 或模型下載：
  - TfidfRetriever : 手刻 TF-IDF + 餘弦相似度，用來看清楚原理
  - BM25Retriever  : 業界標準的詞彙檢索，hybrid search 的另一半

密集向量（dense）檢索等 torch 裝好再加。先把 lexical 基準線立起來是
正確的順序——如果 embedding 打不贏 BM25，那個 embedding 就不該用。
"""

from __future__ import annotations

import math
import re
from collections import Counter

import numpy as np

from .corpus import Doc

# CJK 統一表意文字的範圍
_CJK = r"一-鿿㐀-䶿"
_LATIN = re.compile(r"[a-zA-Z][a-zA-Z0-9'\-]*")
_CJK_RUN = re.compile(f"[{_CJK}]+")
_NUM = re.compile(r"\d+(?:\.\d+)?")


def tokenize(text: str) -> list[str]:
    """中英混合的斷詞。

    中文沒有空白分隔，這是詞彙檢索在中文語料上的第一個真實難題。
    這裡用 **字元 bigram**：把「琴酒」「酒加」這種相鄰兩字當成 token。

    為什麼不用 jieba？
      - bigram 不需要詞典，不會因為「金巴利」不在詞典裡就被切壞
      - 對檢索（而非顯示）來說，bigram 的召回通常比精確斷詞更好
      - 少一個依賴

    代價是 token 數量約為字數的兩倍，索引變大。50 篇文件無所謂。

    英文與數字照原樣保留（小寫化），因為酒名常是英文（Negroni、Daiquiri）。
    """
    out: list[str] = []
    out.extend(m.group().lower() for m in _LATIN.finditer(text))
    out.extend(m.group() for m in _NUM.finditer(text))
    for run in _CJK_RUN.finditer(text):
        s = run.group()
        if len(s) == 1:
            out.append(s)  # 單字沒有 bigram 可切，保留原字
        else:
            out.extend(s[i:i + 2] for i in range(len(s) - 1))
    return out


class TfidfRetriever:
    """手刻 TF-IDF 加餘弦相似度。

    刻意不用 sklearn——TF-IDF 只有幾行，自己寫一遍你就知道
    IDF 為什麼要取對數、為什麼要做長度正規化。
    """

    name = "tfidf"

    def __init__(self, docs: list[Doc]):
        self.docs = docs
        self.ids = [d.id for d in docs]

        tokenized = [tokenize(d.text) for d in docs]
        vocab: dict[str, int] = {}
        for toks in tokenized:
            for t in toks:
                if t not in vocab:
                    vocab[t] = len(vocab)
        self.vocab = vocab

        n_docs = len(docs)
        # df：每個 token 出現在幾篇文件裡
        df = np.zeros(len(vocab))
        for toks in tokenized:
            for t in set(toks):
                df[vocab[t]] += 1

        # 平滑的 IDF。+1 避免除以零，外層再 +1 讓 IDF 不會變成 0
        # （IDF=0 的 token 等於被完全忽略，對出現在所有文件裡的詞太嚴苛）
        self.idf = np.log((n_docs + 1) / (df + 1)) + 1.0

        m = np.zeros((n_docs, len(vocab)), dtype=np.float32)
        for i, toks in enumerate(tokenized):
            for t, c in Counter(toks).items():
                # 對數化的 TF：一個詞出現 100 次不該比出現 10 次重要 10 倍
                m[i, vocab[t]] = (1.0 + math.log(c)) * self.idf[vocab[t]]
        self.matrix = self._l2_normalize(m)

    @staticmethod
    def _l2_normalize(m: np.ndarray) -> np.ndarray:
        """長度正規化：讓長文件不會只因為字多就贏。

        正規化之後，內積就等於餘弦相似度。
        """
        norms = np.linalg.norm(m, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return m / norms

    def _vectorize(self, query: str) -> np.ndarray:
        v = np.zeros(len(self.vocab), dtype=np.float32)
        for t, c in Counter(tokenize(query)).items():
            j = self.vocab.get(t)
            if j is not None:  # 查詢裡的生詞直接忽略
                v[j] = (1.0 + math.log(c)) * self.idf[j]
        n = np.linalg.norm(v)
        return v / n if n else v

    def search(self, query: str, k: int = 10) -> list[tuple[str, float]]:
        scores = self.matrix @ self._vectorize(query)
        # argpartition 先取出前 k 大，再只對這 k 個排序，比全排序快
        k = min(k, len(self.ids))
        idx = np.argpartition(-scores, k - 1)[:k]
        idx = idx[np.argsort(-scores[idx])]
        return [(self.ids[i], float(scores[i])) for i in idx]


class BM25Retriever:
    """BM25，詞彙檢索的業界標準。

    與 TF-IDF 的關鍵差異是「詞頻飽和」：BM25 認為一個詞出現第 10 次
    帶來的資訊遠少於第 1 次，用 k1 參數控制飽和速度；
    b 參數則控制文件長度正規化的強度。
    """

    name = "bm25"

    def __init__(self, docs: list[Doc], k1: float = 1.5, b: float = 0.75):
        from rank_bm25 import BM25Okapi

        self.docs = docs
        self.ids = [d.id for d in docs]
        self.bm25 = BM25Okapi([tokenize(d.text) for d in docs], k1=k1, b=b)

    def search(self, query: str, k: int = 10) -> list[tuple[str, float]]:
        scores = np.asarray(self.bm25.get_scores(tokenize(query)))
        k = min(k, len(self.ids))
        idx = np.argpartition(-scores, k - 1)[:k]
        idx = idx[np.argsort(-scores[idx])]
        return [(self.ids[i], float(scores[i])) for i in idx]


def reciprocal_rank_fusion(
    runs: list[list[tuple[str, float]]], k: int = 10, c: int = 60
) -> list[tuple[str, float]]:
    """把多個檢索器的結果融合成一份排序（hybrid search 的融合步驟）。

    RRF 的分數是 sum(1 / (c + rank))，只看名次不看原始分數——
    這正是它好用的原因：BM25 的分數與餘弦相似度單位完全不同，
    直接加權相加需要調校，RRF 不需要。

    c=60 是原論文的建議值，作用是壓低前幾名之間的差距，
    避免單一檢索器的第一名獨大。
    """
    agg: dict[str, float] = {}
    for run in runs:
        for rank, (doc_id, _) in enumerate(run, start=1):
            agg[doc_id] = agg.get(doc_id, 0.0) + 1.0 / (c + rank)
    ranked = sorted(agg.items(), key=lambda kv: -kv[1])
    return ranked[:k]


class HybridRetriever:
    """TF-IDF 與 BM25 用 RRF 融合。

    兩個都是詞彙式的，所以提升有限——真正的 hybrid 要等 dense 檢索加進來
    才會展現價值（詞彙式擅長精確詞匹配，密集式擅長語意改寫）。
    先把融合機制寫好，之後換掉其中一路就行。
    """

    name = "hybrid-lexical"

    def __init__(self, docs: list[Doc]):
        self.a = TfidfRetriever(docs)
        self.b = BM25Retriever(docs)

    def search(self, query: str, k: int = 10) -> list[tuple[str, float]]:
        pool = max(k * 4, 20)
        return reciprocal_rank_fusion(
            [self.a.search(query, pool), self.b.search(query, pool)], k=k
        )
