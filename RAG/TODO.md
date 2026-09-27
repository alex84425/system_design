# 調酒 RAG 施工清單

進度 12/28。直接改這個檔案，勾 `[x]` 就好。

---

## 前置作業　4/4

- [x] **決定評估方法論** — 檢索端／生成端分開量測，指標與門檻見 `NOTES.md`
- [x] **決定語料主題** — 經典調酒。可驗證、有天然 hard negative、demo 有記憶點
- [x] **產生 50 篇 markdown 語料** — `data/cocktails/*.md`，frontmatter + 敘述正文，平均 196 字
- [x] **產生 51 題評估集** — `eval/eval_set.jsonl`，factual 26／multi_hop 8／colloquial 9／negative 8

## Stage 0 — 環境與指標校準　4/5

- [x] **修 Python 環境** — `RAG/.venv`（3.12.1）。Avast 做 SSL 攔截，憑證設定寫在 `.venv/pip.ini`
- [x] **安裝套件** — numpy 2.5.3、rank-bm25、torch 2.14.0+cpu
- [x] **手刻四個檢索指標** — `rageval/metrics.py`，Recall／Precision／MRR／NDCG
- [x] **指標單元測試** — `test_metrics.py`，14 項手算期望值全過
- [ ] **用公開 benchmark 交叉驗證** — BEIR 小 dataset。手算測試已覆蓋大半，這步是外部對答案

## Stage 1 — 最小可跑 RAG　4/5

- [x] **markdown loader** — `rageval/corpus.py`，frontmatter 進 metadata、正文進索引
- [x] **決定 chunking 策略** — 一檔一 chunk，配方是自足語意單位。之後再試切段比較
- [ ] **接 embedding model** — 卡住：`sentence-transformers` 被 Avast 擋（hash 驗證失敗）
- [x] **純 numpy 暴力檢索** — 手刻 TF-IDF + 餘弦相似度。dense 向量之後接同一套
- [x] **跑出第一組基準線** — BM25 最佳 Recall@5 0.758 / NDCG@10 0.792。詳見 `EXPERIMENTS.md`

## Stage 2 — 改進檢索　1/6

- [ ] **換 FAISS 並比較** — 50 篇看不出速度差，重點是搞懂 Flat／IVF／HNSW 的取捨
- [x] **加 BM25 做 hybrid** — RRF 融合已實作（c=60）。兩路都是詞彙式，要等 dense 才有意義
- [ ] **加 cross-encoder rerank** — retrieve k=20 → rerank → top 5，看 NDCG@10 有沒有動
- [ ] **hard negative 叢集單獨分析** — 目前大多滿分但不算數，題目裡有酒名。dense 上線後才會變難
- [ ] **metadata filtering** — 用 frontmatter 的 base、method 過濾。Gibson 那題唯一的解法
- [ ] **修 q044 的 ground truth** — `corpse-reviver-2` 正文寫「解宿醉用的晨間酒」，是合理答案卻被算錯

## Stage 3 — 生成端評估　0/4

- [ ] **接 LLM 生成答案並附引用** — 強制輸出來源檔名，沒引用就不算完成
- [ ] **實作 Faithfulness 與 Answer Relevancy** — LLM-as-judge，結構化 rubric + 強制 JSON 輸出
- [ ] **驗證 judge 本身** — 人工標 20 題算 Cohen's kappa。kappa 太低代表後面數字全假
- [ ] **negative 題專項測試** — 8 題答案不在語料裡，測「我不知道」的回答率

## Stage 4 — 工程化與收尾　0/4

- [ ] **接 RAGAS 對照手刻分數** — 兩邊對得上，才證明實作是對的
- [ ] **寫 CI script 並設門檻** — 任一指標掉超過 3% 就擋
- [ ] **實驗記錄表** — `EXPERIMENTS.md` 已開始記，每次改動補一列
- [ ] **寫 README 的面試講稿版** — 把每個決策的「為什麼」寫下來，面試前讀這份就好

---

## 現在卡在哪

`sentence-transformers` 裝不起來，Avast 竄改下載內容導致 pip hash 驗證失敗。
torch 本身已經裝好了（改走 PyTorch 官方 CPU index 就過），所以問題只在那幾個
從 PyPI 抓的套件。

三條路：

1. 手動下載 wheel 再本機安裝 — 繞過 pip 的下載環節
2. 暫時關閉 Avast 的網頁防護再裝 — 最快，但要你自己操作
3. 改用 OpenAI API 做 embedding — 不需要本機模型，但要 API key 且會產生費用
