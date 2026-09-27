"""跑評估集，產生基準線數字。

執行：.venv/Scripts/python.exe evaluate.py

輸出三張表：
  1. 各檢索器的整體分數
  2. 依題型拆解——看清楚哪一類在拖後腿
  3. hard negative 叢集單獨計分——這才是真正的難處

negative 題（答案不在語料裡）不列入檢索分數，它們要在生成端
單獨評估「有沒有誠實說不知道」。
"""

from __future__ import annotations

import argparse
import math
import os
from collections import defaultdict

from rageval.corpus import load_corpus, load_eval
from rageval.metrics import ndcg_at_k, precision_at_k, recall_at_k, reciprocal_rank
from rageval.retrieve import BM25Retriever, HybridRetriever, TfidfRetriever

HERE = os.path.dirname(os.path.abspath(__file__))

# 埋在語料裡的 hard negative 叢集。這些題目專門用來測檢索精度，
# 整體平均會把它們的失敗稀釋掉，所以要單獨看。
CLUSTERS = {
    "Sour 三兄弟": ["q027"],
    "苦甜三角": ["q021", "q022"],
    "Martini/Gibson": ["q026"],
    "Manhattan/RobRoy": ["q023"],
    "Collins/Fizz": ["q024"],
    "黑白俄羅斯": ["q025"],
}


def mean(xs):
    """忽略 nan 的平均。沒有有效值時回傳 nan。"""
    vals = [x for x in xs if not math.isnan(x)]
    return sum(vals) / len(vals) if vals else float("nan")


def fmt(x):
    return "  n/a" if math.isnan(x) else f"{x:5.3f}"


def evaluate(retriever, items, k_recall=5, k_ndcg=10, pool=20):
    """對單一檢索器跑完整份評估集，回傳每題的分數明細。"""
    rows = []
    for it in items:
        if not it["relevant"]:
            continue  # negative 題不適用檢索指標
        ranked = [doc_id for doc_id, _ in retriever.search(it["q"], pool)]
        rows.append({
            "id": it["id"],
            "type": it["type"],
            "n_rel": len(it["relevant"]),
            "recall": recall_at_k(ranked, it["relevant"], k_recall),
            "precision": precision_at_k(ranked, it["relevant"], k_recall),
            "ndcg": ndcg_at_k(ranked, it["relevant"], k_ndcg),
            "rr": reciprocal_rank(ranked, it["relevant"]),
            "ranked": ranked,
        })
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--k-recall", type=int, default=5)
    ap.add_argument("--k-ndcg", type=int, default=10)
    ap.add_argument("--show-failures", action="store_true",
                    help="列出 Recall 掛零的題目與實際撈回的前五名")
    args = ap.parse_args()

    docs = load_corpus(os.path.join(HERE, "data", "cocktails"))
    items = load_eval(os.path.join(HERE, "eval", "eval_set.jsonl"))
    scored = [i for i in items if i["relevant"]]

    print(f"語料 {len(docs)} 篇 · 評估集 {len(items)} 題"
          f"（{len(scored)} 題計分，{len(items) - len(scored)} 題為 negative）")
    print(f"Recall/Precision @ k={args.k_recall} · NDCG @ k={args.k_ndcg}")
    print()

    retrievers = [TfidfRetriever(docs), BM25Retriever(docs), HybridRetriever(docs)]
    all_rows = {}

    # ---- 表 1：整體 ----
    print("=" * 62)
    print(f"{'檢索器':<16}{'Recall':>9}{'Precision':>11}{'NDCG':>9}{'MRR':>9}")
    print("-" * 62)
    for r in retrievers:
        rows = evaluate(r, items, args.k_recall, args.k_ndcg)
        all_rows[r.name] = rows
        print(f"{r.name:<16}"
              f"{fmt(mean([x['recall'] for x in rows])):>9}"
              f"{fmt(mean([x['precision'] for x in rows])):>11}"
              f"{fmt(mean([x['ndcg'] for x in rows])):>9}"
              f"{fmt(mean([x['rr'] for x in rows])):>9}")
    print("=" * 62)
    print()

    # ---- 表 2：依題型 ----
    types = ["factual", "multi_hop", "colloquial"]
    print(f"{'題型':<14}{'題數':>5}", end="")
    for r in retrievers:
        print(f"{r.name:>16}", end="")
    print()
    print("-" * (19 + 16 * len(retrievers)))
    for t in types:
        n = sum(1 for x in all_rows[retrievers[0].name] if x["type"] == t)
        print(f"{t:<14}{n:>5}", end="")
        for r in retrievers:
            sub = [x["recall"] for x in all_rows[r.name] if x["type"] == t]
            print(f"{fmt(mean(sub)):>16}", end="")
        print()
    print()
    print("（表 2 為 Recall，multi_hop 正解多，容易撞到 Recall@k 的數學天花板）")
    print()

    # ---- 表 3：hard negative 叢集 ----
    print(f"{'叢集':<20}", end="")
    for r in retrievers:
        print(f"{r.name:>16}", end="")
    print()
    print("-" * (20 + 16 * len(retrievers)))
    for label, qids in CLUSTERS.items():
        print(f"{label:<20}", end="")
        for r in retrievers:
            sub = [x["recall"] for x in all_rows[r.name] if x["id"] in qids]
            print(f"{fmt(mean(sub)):>16}", end="")
        print()
    print()

    # ---- 失敗題 ----
    if args.show_failures:
        best = max(retrievers, key=lambda r: mean([x["recall"] for x in all_rows[r.name]]))
        by_id = {i["id"]: i for i in items}
        print(f"=== {best.name} 上 Recall 掛零的題目 ===")
        for x in all_rows[best.name]:
            if x["recall"] == 0.0:
                it = by_id[x["id"]]
                print(f"\n{x['id']} [{x['type']}] {it['q']}")
                print(f"  正解 {it['relevant']}")
                print(f"  撈回 {x['ranked'][:5]}")
                if it.get("note"):
                    print(f"  備註 {it['note']}")


if __name__ == "__main__":
    main()
