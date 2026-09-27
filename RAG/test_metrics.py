"""指標實作的驗證：每個期望值都是手算出來的，不是跑出來反填的。

反填期望值是自欺欺人——程式錯了測試也會跟著錯。
下面每個 NDCG 的期望值都附上算式，你可以自己驗一遍。

執行：.venv/Scripts/python.exe test_metrics.py
也可以用 pytest 收集（函式名都是 test_ 開頭）。
"""

import math

from rageval.metrics import (
    hit_rate_at_k,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)

TOL = 1e-9


def close(a, b, tol=TOL):
    return abs(a - b) < tol


# ------------------------------------------------------------ Recall

def test_recall_basic():
    ranked = ["a", "b", "c", "d", "e"]
    rel = {"a", "c"}
    # 前3筆 a,b,c 撈到 a 和 c，正解共 2 筆 → 2/2
    assert close(recall_at_k(ranked, rel, 3), 1.0)
    # 前1筆只有 a → 1/2
    assert close(recall_at_k(ranked, rel, 1), 0.5)
    # 完全沒撈到
    assert close(recall_at_k(ranked, {"z"}, 5), 0.0)


def test_recall_ceiling_when_k_too_small():
    """正解比 k 多的時候，Recall@k 有數學天花板。

    multi_hop 題目常常撞到這個上限——分數低不代表系統爛，
    要先確認 k 有沒有開夠大。q037（哪些是攪拌的）有 11 個正解，
    k=5 時上限就是 5/11。
    """
    rel = {f"d{i}" for i in range(11)}
    ranked = [f"d{i}" for i in range(11)]
    assert close(recall_at_k(ranked, rel, 5), 5 / 11)
    assert close(recall_at_k(ranked, rel, 11), 1.0)


def test_recall_dedupe():
    """同一份文件出現兩次不該虛增分數。"""
    ranked = ["a", "a", "b"]
    rel = {"a", "b"}
    # 去重後前2筆是 a,b → 2/2 = 1.0
    # 若沒去重，前2筆是 a,a → 只撈到 a → 0.5（錯的）
    assert close(recall_at_k(ranked, rel, 2), 1.0)


# ------------------------------------------------------------ Precision

def test_precision_basic():
    ranked = ["a", "b", "c", "d", "e"]
    rel = {"a", "c"}
    assert close(precision_at_k(ranked, rel, 3), 2 / 3)
    assert close(precision_at_k(ranked, rel, 5), 2 / 5)


def test_precision_denominator_is_k_not_returned_count():
    """只回傳 2 筆但 k=5，剩下 3 個空位要被扣分。"""
    ranked = ["a", "b"]
    rel = {"a", "b"}
    assert close(precision_at_k(ranked, rel, 5), 2 / 5)


# ------------------------------------------------------------ MRR

def test_reciprocal_rank():
    assert close(reciprocal_rank(["a", "b", "c"], {"a"}), 1.0)
    assert close(reciprocal_rank(["a", "b", "c"], {"b"}), 0.5)
    assert close(reciprocal_rank(["a", "b", "c"], {"c"}), 1 / 3)
    assert close(reciprocal_rank(["a", "b", "c"], {"z"}), 0.0)


def test_reciprocal_rank_takes_first_hit_only():
    """多個正解時只看最前面那個。"""
    assert close(reciprocal_rank(["a", "b", "c"], {"b", "c"}), 0.5)


# ------------------------------------------------------------ NDCG

def test_ndcg_perfect_ranking():
    """正解都排在最前面 → 1.0"""
    assert close(ndcg_at_k(["a", "c", "b"], {"a", "c"}, 3), 1.0)


def test_ndcg_hand_computed():
    """ranked=[a,b,c], relevant={a,c}, k=3

    DCG  = 1/log2(2) + 0/log2(3) + 1/log2(4)
         = 1.0 + 0 + 0.5
         = 1.5
    IDCG = 1/log2(2) + 1/log2(3)          (理想排序 a,c 擺前兩名)
         = 1.0 + 0.6309297535714574
         = 1.6309297535714574
    NDCG = 1.5 / 1.6309297535714574
    """
    idcg = 1.0 + 1.0 / math.log2(3)
    expected = 1.5 / idcg
    got = ndcg_at_k(["a", "b", "c"], {"a", "c"}, 3)
    assert close(got, expected)
    assert close(got, 0.9197207891481876, tol=1e-12)


def test_ndcg_graded_relevance():
    """分級相關性：relevant={a:3, c:1}, ranked=[a,b,c], k=3

    DCG  = 3/log2(2) + 0/log2(3) + 1/log2(4) = 3 + 0 + 0.5 = 3.5
    IDCG = 3/log2(2) + 1/log2(3)             = 3 + 0.6309297535714574
    """
    idcg = 3.0 + 1.0 / math.log2(3)
    expected = 3.5 / idcg
    assert close(ndcg_at_k(["a", "b", "c"], {"a": 3, "c": 1}, 3), expected)


def test_ndcg_detects_rerank_while_recall_does_not():
    """這一題是整份測試的重點。

    rerank 唯一在做的事就是把正解往前搬。Recall 完全感覺不到這件事，
    NDCG 才看得到——所以評估 rerank 效果一定要看 NDCG。
    """
    rel = {"a"}
    before = ["x", "y", "z", "a"]   # 正解墊底
    after = ["a", "x", "y", "z"]    # rerank 之後排第一

    # Recall 對這個改善完全無感
    assert close(recall_at_k(before, rel, 4), 1.0)
    assert close(recall_at_k(after, rel, 4), 1.0)

    # NDCG 抓得到：DCG_before = 1/log2(5)，IDCG = 1
    ndcg_before = ndcg_at_k(before, rel, 4)
    ndcg_after = ndcg_at_k(after, rel, 4)
    assert close(ndcg_before, 1.0 / math.log2(5))
    assert close(ndcg_after, 1.0)
    assert ndcg_after > ndcg_before


def test_ndcg_respects_k_cutoff():
    """正解掉在 k 之外就拿不到分。"""
    assert close(ndcg_at_k(["x", "y", "a"], {"a"}, 2), 0.0)


# ------------------------------------------------------------ Hit rate

def test_hit_rate():
    assert close(hit_rate_at_k(["a", "b"], {"b"}, 2), 1.0)
    assert close(hit_rate_at_k(["a", "b"], {"b"}, 1), 0.0)


# ------------------------------------------------------------ negative 題

def test_empty_relevant_returns_nan():
    """negative 題（答案不在語料裡）沒有正解，不適用檢索指標。

    回傳 nan 而不是 0 或 1——用 0 會不公平地拉低平均，
    用 1 則會虛高。這類題目要用「有沒有誠實說不知道」單獨評估。
    """
    assert math.isnan(recall_at_k(["a"], set(), 5))
    assert math.isnan(precision_at_k(["a"], set(), 5))
    assert math.isnan(reciprocal_rank(["a"], set()))
    assert math.isnan(ndcg_at_k(["a"], set(), 5))
    assert math.isnan(hit_rate_at_k(["a"], set(), 5))


# ------------------------------------------------------------ runner

def main():
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {name}  {e}")
        except Exception as e:
            failed += 1
            print(f" ERROR  {name}  {type(e).__name__}: {e}")
    print()
    print(f"{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
