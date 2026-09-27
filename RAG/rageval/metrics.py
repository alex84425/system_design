"""檢索端指標，全部手刻。

刻意不呼叫 sklearn 或 ranx——面試被問到 NDCG 怎麼算的時候，
你要能在白板上寫出來，而不是說「library 幫我算的」。

共同介面
--------
每個函式吃兩個東西：
    ranked   : 檢索系統回傳的文件 id，依分數由高到低排序
    relevant : 正解文件 id 的集合

只有 ndcg_at_k 額外支援分級相關性（graded relevance），
其餘都是二元相關（相關／不相關）。
"""

from __future__ import annotations

import math
from typing import Iterable, Mapping, Sequence


def _dedupe(ranked: Sequence[str]) -> list[str]:
    """同一份文件在排序中出現兩次會虛增 Recall，先去重。

    保留第一次出現的位置——那是系統對它最有信心的排名。
    """
    seen: set[str] = set()
    out: list[str] = []
    for doc in ranked:
        if doc not in seen:
            seen.add(doc)
            out.append(doc)
    return out


def recall_at_k(ranked: Sequence[str], relevant: Iterable[str], k: int) -> float:
    """前 k 筆裡撈到了多少比例的正解。

    Recall@k = |前k筆 ∩ 正解| / |正解|

    這是最重要的檢索指標：這裡漏掉的東西，生成端再強也救不回來。

    注意分母是正解總數，不是 k。所以當正解有 11 筆而 k=5 時，
    Recall@5 的上限就是 5/11 ≈ 0.45——不是系統爛，是 k 不夠大。
    評估集裡的 multi_hop 題常常踩到這個天花板，解讀分數時要記得。
    """
    rel = set(relevant)
    if not rel:
        # 沒有正解的題目（negative testing）不適用 Recall，
        # 回傳 nan 讓它在彙總時被排除，而不是用 0 或 1 污染平均。
        return float("nan")
    top = _dedupe(ranked)[:k]
    return len(rel.intersection(top)) / len(rel)


def precision_at_k(ranked: Sequence[str], relevant: Iterable[str], k: int) -> float:
    """前 k 筆裡有多少比例是正解。

    Precision@k = |前k筆 ∩ 正解| / k

    分母固定是 k，不是實際回傳筆數——如果系統只回傳 3 筆而 k=5，
    剩下兩個空位算是浪費掉的機會，應該被扣分。
    """
    rel = set(relevant)
    if k <= 0:
        raise ValueError("k 必須為正整數")
    if not rel:
        return float("nan")
    top = _dedupe(ranked)[:k]
    return len(rel.intersection(top)) / k


def reciprocal_rank(ranked: Sequence[str], relevant: Iterable[str]) -> float:
    """第一個正解排在第幾名的倒數。第 1 名得 1.0，第 2 名得 0.5，以此類推。

    整份評估集取平均就是 MRR（Mean Reciprocal Rank）。

    只看「第一個」正解，所以適合那種只需要一筆正確文件的場景（FAQ、單跳事實）。
    多正解的 multi_hop 題用 MRR 會浪費資訊——那種題目該看 Recall 或 NDCG。
    """
    rel = set(relevant)
    if not rel:
        return float("nan")
    for i, doc in enumerate(_dedupe(ranked), start=1):
        if doc in rel:
            return 1.0 / i
    return 0.0


def _dcg(gains: Sequence[float]) -> float:
    """Discounted Cumulative Gain。

    第 i 名（從 1 起算）的貢獻 = gain / log2(i + 1)

    分母用 log2(i+1) 而不是 log2(i)，是為了讓第 1 名的折扣為
    log2(2) = 1，也就是不打折。排越後面折扣越重，這就是「位置有價值」
    這件事的數學表達。
    """
    return sum(g / math.log2(i + 1) for i, g in enumerate(gains, start=1))


def ndcg_at_k(
    ranked: Sequence[str],
    relevant: Iterable[str] | Mapping[str, float],
    k: int,
) -> float:
    """Normalized DCG@k——同時考慮「有沒有撈到」和「排在第幾名」。

    NDCG@k = DCG@k / IDCG@k

    IDCG 是理想排序（所有正解依相關度由高到低排在最前面）的 DCG，
    用它來正規化，讓分數落在 0 到 1 之間、不同題目之間可以比較。

    `relevant` 可以是：
      - 集合／列表：二元相關，每筆正解 gain = 1
      - 字典 {doc_id: gain}：分級相關性，例如 {"negroni": 3, "americano": 1}

    評估 rerank 效果一定要看這個指標。Recall 不會因為把正解從第 8 名
    拉到第 1 名而改變，但 NDCG 會——而那正是 rerank 唯一在做的事。
    """
    if k <= 0:
        raise ValueError("k 必須為正整數")

    if isinstance(relevant, Mapping):
        gains: dict[str, float] = {d: float(g) for d, g in relevant.items() if g > 0}
    else:
        gains = {d: 1.0 for d in relevant}

    if not gains:
        return float("nan")

    top = _dedupe(ranked)[:k]
    actual = _dcg([gains.get(doc, 0.0) for doc in top])

    # 理想排序：把 gain 最高的正解擺前面，最多取 k 筆
    ideal = _dcg(sorted(gains.values(), reverse=True)[:k])
    if ideal == 0:
        return float("nan")
    return actual / ideal


def hit_rate_at_k(ranked: Sequence[str], relevant: Iterable[str], k: int) -> float:
    """前 k 筆裡有沒有撈到任何一個正解。有就是 1，沒有就是 0。

    Recall@k 的二元版本，資訊量比較少，但拿來當 CI 門檻很直觀：
    「95% 的題目要能在前 5 筆撈到答案」比「平均 Recall@5 要 0.82」好溝通。
    """
    rel = set(relevant)
    if not rel:
        return float("nan")
    return 1.0 if rel.intersection(_dedupe(ranked)[:k]) else 0.0
