# RAG 評估筆記

面試前讀這份就好。每一節都是「面試官會怎麼問 + 你要答什麼」。

---

## 1. 核心心法：拆兩段量

**最重要的一句話：端到端分數爛掉時，你必須知道是「沒撈到」還是「撈到了但講錯」。**

```
Query → [檢索] → Context → [生成] → Answer
           ↑                   ↑
      Recall@k / NDCG      Faithfulness
      (資訊有沒有進來)      (有沒有照著講)
```

拆開之後除錯變成可決策的：

| 症狀 | 診斷 | 動哪裡 |
|---|---|---|
| Recall 高、Faithfulness 低 | 資料撈對了，講錯了 | prompt、模型、引用約束 |
| Recall 低 | 生成端再強也沒用 | chunking、embedding、hybrid search |

這個因果順序本身就是一個完整的面試答案。只講「我用 RAGAS 跑分」的人在這裡就停了。

---

## 2. 檢索端指標

不需要 LLM，純數學。便宜、穩定、可以每次 commit 都跑。實作在 `rageval/metrics.py`。

| 指標 | 在測什麼 | 什麼時候看 |
|---|---|---|
| **Recall@k** | 前 k 筆裡撈到多少比例的正解 | **最重要**，這裡漏了後面救不回來 |
| Precision@k | 前 k 筆裡有幾筆是正解 | context 有限、雜訊會干擾 LLM 時 |
| MRR | 第一個正解排名的倒數平均 | 只需一筆正確文件的場景（FAQ） |
| **NDCG@k** | 同時考慮排序位置與分級相關性 | **評 rerank 一定看這個** |
| Hit Rate | Recall@k 的二元版 | CI 門檻，好溝通 |

### 業界參考門檻

- 窄領域知識庫：`Precision@5 ≥ 0.70`
- 廣語料搜尋：`Recall@20 ≥ 0.80`
- Faithfulness：一般 `> 0.80`，醫療／法律／金融 `> 0.90`

### NDCG 怎麼算（白板題）

```
DCG@k  = Σ  gain_i / log2(i + 1)        i 從 1 起算
IDCG@k = 理想排序（正解全擺前面）的 DCG
NDCG@k = DCG@k / IDCG@k
```

分母用 `log2(i+1)` 而不是 `log2(i)`，是為了讓第 1 名的折扣為 `log2(2) = 1`，也就是不打折。

### 為什麼評 rerank 一定要看 NDCG

rerank 唯一在做的事就是把正解往前搬。Recall 完全感覺不到：

```
正解 = {a}
rerank 前：[x, y, z, a]   Recall@4 = 1.0   NDCG@4 = 0.431
rerank 後：[a, x, y, z]   Recall@4 = 1.0   NDCG@4 = 1.000
                          ↑ 沒動          ↑ 抓到了
```

這個案例寫成測試了：`test_metrics.py::test_ndcg_detects_rerank_while_recall_does_not`

### 面試陷阱題：k 為什麼不能無限調大

k 越大 Recall 一定漲，但 Precision 掉、context 變長、成本變高，而且 LLM 會被雜訊干擾
（**lost-in-the-middle**：長 context 中段的資訊最容易被忽略）。

實務做法：`retrieve k=50 → rerank → top 5`。**答得出後半句才算過關。**

### 兩個實作細節（自己踩過才知道）

**Recall@k 有數學天花板。** 正解 11 筆而 k=5 時，上限就是 5/11 ≈ 0.45。分數低不代表系統爛，
先確認 k 有沒有開夠。multi_hop 題常撞到這個。

**negative 題要回傳 nan 而不是 0 或 1。** 答案不在語料裡的題目沒有正解，用 0 會不公平拉低平均，
用 1 會虛高。它們要在生成端單獨評估「有沒有誠實說不知道」。

---

## 3. 生成端指標

要用 LLM 當評審，所以貴、慢、有偏誤。不要每次 commit 都跑全量。

| 指標 | 在測什麼 |
|---|---|
| **Faithfulness / Groundedness** | 答案的每個 claim 都能從 context 找到支持嗎 —— 直接測幻覺 |
| Answer Relevancy | 有沒有真的回答問題（可能完全忠實卻答非所問） |
| Context Precision | 撈回的 context 有多少比例真的被用上 |
| Answer Correctness | 跟人工寫的標準答案比對 |

### RAG Triad（TruLens）

面試時用這個開場很有效，一句話交代完整個評估架構：

```
            Query
           /     \
  Context        Answer
  Relevance      Relevance
         \       /
          Context ——— Groundedness ——— Response
```

- **Context Relevance**：撈回來的跟問題有關嗎
- **Groundedness**：答案有根據 context 嗎
- **Answer Relevance**：答案有回答問題嗎

---

## 4. LLM-as-Judge 的坑

大部分人只知道「用 GPT-4o 當評審」，不知道**評審本身要先被評審**。這題答得出來就是資深。

> **評審沒校準過，後面所有數字都是假的。**

### 先驗證 judge

抽 100 題人工標註，跟 judge 的判斷算一致性（**Cohen's kappa**）。kappa 太低代表整個 eval
建立在流沙上 —— 你會根據錯誤訊號去調 chunk size，然後以為自己在進步。

參考值：GPT-4o 等級的評審在區分「真相關」與 hard negative 上約有 **80% 以上**準確率。夠用，但不是真理。

### 三個已知偏誤

| 偏誤 | 症狀 |
|---|---|
| Verbosity bias | 答案越長分數越高，即使沒增加資訊 |
| Position bias | 成對比較時排前面的系統性佔優 |
| Self-preference | 模型偏好自己家族的文字風格 |

### 對策

用**結構化 rubric**（明確寫出每一分的判準）加上**強制 JSON 輸出**，而不是丟一句「請給 1 到 5 分」。
分數穩定得多，而且每筆判斷可稽核 —— 企業場景裡這點比分數本身更重要。

---

## 5. 大廠實際怎麼做

### 分層評估

```
Unit       單一 chunk 能不能被它自己的問題檢索到
Component  整條 retrieval pipeline 的 Recall 與 NDCG
End-to-end 完整答案的 Faithfulness 與 Correctness
Online     真實使用者訊號 ← 這一層才是真相
```

### Golden set 是人工標的

合成資料是起點不是終點。正式 eval set 是幾百到幾千題人工逐題審過的。
看起來像雜務，實際上是**護城河** —— 模型會換、框架會換，標註過的 golden set 一直留著。

### Regression suite 進 CI

每次改 chunk size、換 embedding、動 prompt 全部自動跑。門檻：任一指標掉超過 3% 擋 PR。
DeepEval 直接接 pytest 就是為了這個。

### 線上訊號才是真相

| 訊號 | 代表什麼 |
|---|---|
| Thumbs up/down | 最直接，但回報率低且有自我選擇偏誤 |
| Escalation rate | 轉真人客服的比例 —— 系統失敗的硬指標 |
| Rephrase rate | 使用者換句話再問，等於上一輪失敗了 |

離線分數漂亮、線上爛透，是常態不是意外。

---

## 6. 失敗類型分類

不要只看總分，要看錯在哪。歸類之後優化才有方向。

| 失敗類型 | 該修哪裡 |
|---|---|
| 檢索沒撈到 | chunking、embedding 選型、加 hybrid search |
| 撈到了但排很後面 | 加 reranker（cross-encoder） |
| 撈到了但 LLM 沒用 | prompt 設計、context 排列順序 |
| 用了但講錯 | 模型能力、加強 faithfulness 約束 |
| **語料裡根本沒有** | **要能誠實說「我不知道」** |

最後一類是分水嶺。eval set 一定要包含答案不在語料裡的題目（**negative testing**），
測系統會不會硬掰。**沒有這類題目，Faithfulness 分數會虛高 —— 因為你從來沒給過系統說謊的機會。**

---

## 7. 工具選型

| 工具 | 定位 | 什麼時候用 |
|---|---|---|
| **RAGAS** | 最專注 RAG，內建合成測試集生成 | 從零到有分數最快，先用這個 |
| DeepEval | 測試優先，直接接 pytest 與 CI | RAG 是更大 agent／chatbot 的一部分時 |
| TruLens | evaluation + tracing 合一，RAG Triad 出處 | 想同時看到每一步發生什麼 |
| LangFuse / Phoenix | 線上 tracing 與監控 | 進生產之後 |

---

## 8. 這個專案的語料設計

選調酒的理由：**你看得懂答案對不對**。不懂的領域標不出 golden set，標不出 golden set 就沒有評估。

### 埋了六個 hard negative 叢集

| 叢集 | 成員 | 陷阱 |
|---|---|---|
| Sour 三兄弟 | Daiquiri / Margarita / Sidecar | 同骨架換基酒 |
| 苦甜三角 | Negroni / Boulevardier / Old Pal | 都是「烈酒+金巴利+香艾酒」 |
| Martini 雙生 | Dry Martini / Gibson | **材料欄位完全相同**，只差裝飾 |
| Manhattan 對照 | Manhattan / Rob Roy | 只換威士忌種類 |
| Collins / Fizz | Tom Collins / Gin Fizz | 材料幾乎一致，只差製程 |
| 俄羅斯兄弟 | Black / White Russian | 差一層鮮奶油 |

### 四種題型

| 題型 | 題數 | 範例 |
|---|---:|---|
| factual | 26 | Negroni 的三種材料比例？ |
| multi_hop | 8 | 我有琴酒和甜香艾酒，可以調什麼？ |
| colloquial | 9 | 有沒有喝起來不像酒、很淡的？ |
| negative | 8 | Negroni 的抹茶版本比例？（語料裡沒有） |

---

## 9. 合成 Eval Set 的五步驟

合成解決的是「標註成本」，不是「你看不懂答案」。

1. **取一個 chunk** — 隨機抽樣，涵蓋不同基酒與長度分布
2. **叫 LLM 出題** — 提示詞關鍵是「出一個客人*真的會在吧台問*的問題」。不加這個限定會得到一堆考卷式問題
3. **那個 chunk 自動就是 ground truth** — Recall@k 與 NDCG 免費拿到，零人工標註
4. **人工抽審 10-20%** — 砍掉答案抄在問題裡的、模糊的、不是人會問的。**這步不能省**
5. **補三種進階題型** — multi-hop、negative、口語化改寫

RAGAS 的 `TestsetGenerator` 做的是第 1-3 步。**第 4、5 步要自己補，也正是面試時能講出差異化的地方。**

> 實證：這個專案第 4 步沒做徹底，`q044`「宿醉喝什麼」只標了 bloody-mary，
> 但 corpse-reviver-2 正文寫著「解宿醉用的晨間酒」，也是合理答案。
> **這就是為什麼抽審不能省。**

---

## 10. 目前的實測結果

詳見 `EXPERIMENTS.md`。一句話版本：

**整體 Recall@5 = 0.758 是假象。** 拆開看：factual 1.000、multi_hop 0.720、**colloquial 0.093**。

詞彙檢索（BM25）在 factual 拿滿分是合理的 —— 使用者直接問酒名時字面匹配本來就該贏。
這反而說明 **BM25 是地板不是天花板**：dense embedding 如果在這類題目上輸給 BM25，那個 embedding 就不該用。

colloquial 幾乎全滅，失敗原因高度一致：**問題與語料用詞零重疊**。
語料寫「清醒」，使用者說「提神」；語料寫「低酒精」，使用者說「不像酒」。
**這是語意落差，詞彙檢索在原理上無解** —— 正是 dense embedding 該證明自己的地方。
