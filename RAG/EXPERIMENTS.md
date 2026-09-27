# 實驗記錄

每次改動記一列。面試時直接秀這張表——它證明的不是「我做過 RAG」，
而是「我做過受控比較」。

重跑：`.venv/Scripts/python.exe evaluate.py`

---

## 基準線 · 詞彙檢索（2026-09-15）

語料 50 篇 · 評估集 51 題（43 題計分，8 題 negative 不列入檢索分數）
Recall/Precision @ k=5 · NDCG @ k=10

| 檢索器 | Recall | Precision | NDCG | MRR |
|---|---:|---:|---:|---:|
| TF-IDF（手刻 numpy） | 0.752 | 0.237 | 0.778 | 0.796 |
| BM25 | **0.758** | 0.237 | **0.792** | **0.807** |
| Hybrid（TF-IDF + BM25，RRF） | 0.758 | 0.242 | 0.781 | 0.794 |

**設定**：中文用字元 bigram 斷詞（無 jieba）；索引文字 = 名稱 + 基酒 + 杯型 + 風味標籤 + 正文；BM25 參數 k1=1.5, b=0.75；RRF c=60。

### 依題型拆解（Recall@5）

| 題型 | 題數 | TF-IDF | BM25 | Hybrid |
|---|---:|---:|---:|---:|
| factual | 26 | 1.000 | 1.000 | 1.000 |
| multi_hop | 8 | 0.658 | 0.720 | 0.658 |
| colloquial | 9 | 0.120 | 0.093 | 0.148 |

### Hard negative 叢集（Recall@5）

| 叢集 | TF-IDF | BM25 | Hybrid |
|---|---:|---:|---:|
| Sour 三兄弟 | **0.000** | **0.000** | **0.000** |
| 苦甜三角 | 1.000 | 1.000 | 1.000 |
| Martini/Gibson | 1.000 | 1.000 | 1.000 |
| Manhattan/RobRoy | 1.000 | 1.000 | 1.000 |
| Collins/Fizz | 1.000 | 1.000 | 1.000 |
| 黑白俄羅斯 | 1.000 | 1.000 | 1.000 |

---

## 讀這組數字

**整體 0.758 是假象。** 拆開之後才看得到真相：factual 滿分，colloquial 幾乎全滅。
只看總分會以為系統堪用，實際上它只會回答「Negroni 的比例是多少」這種
把答案寫在問題裡的題目。這就是為什麼評估一定要分層拆解。

**詞彙檢索在 factual 拿滿分是合理的，不是好消息。** 使用者直接問酒名時，
字面匹配本來就該贏——這反而說明 dense embedding 如果在這類題目上
輸給 BM25，那個 embedding 就不該用。BM25 是地板，不是天花板。

**colloquial 0.09～0.15 是這次實驗最重要的發現。** 失敗原因全部相同：
問題與語料的用詞零重疊。

| 題目 | 正解 | 撈回前五 |
|---|---|---|
| 有沒有喝起來不像酒、很淡的？ | aperol-spritz, americano, bellini | daiquiri, rob-roy, french-75, mai-tai, aviation |
| 喝了會提神的調酒 | espresso-martini | sidecar, white-russian, jack-rose, black-russian, dark-n-stormy |
| 我喜歡苦一點的，有推薦嗎？ | negroni, americano, boulevardier, old-pal | paloma, hanky-panky, cosmopolitan, last-word, old-fashioned |

語料寫「低酒精」「清爽」，使用者說「不像酒」；語料寫「咖啡」「提神」的
語意，使用者說「提神」——但 bigram 切出來的「提神」在語料裡根本不存在，
因為那篇寫的是「清醒」。**這就是語意落差，詞彙檢索在原理上無解。**

**Hard negative 叢集大多滿分，但那是因為題目裡有酒名。** q021「把 Negroni 的
琴酒換成波本叫什麼」帶了 Negroni 和波本兩個字面線索，BM25 當然撈得到。
唯一掛零的 Sour 三兄弟（q027）正好是叢集裡唯一的 colloquial 題——
「有沒有酸酸甜甜、帶柑橘的短飲」一個酒名都沒有。

所以目前還沒真正測到 hard negative 的難度。**要等 dense 檢索上場，
語意能撈對之後，才會開始出現「三杯分數幾乎相同、排序等於擲骰子」
的情況**——那時 metadata filter 與 rerank 才有舞台。

**Hybrid 幾乎沒提升是預期內的。** TF-IDF 與 BM25 都是詞彙式，
犯一樣的錯，融合兩個瞎子不會變成看得見。融合機制先寫好，
等 dense 那一路接上去才會發揮作用。

---

## 待修：評估集品質問題

`q044`「宿醉的時候喝什麼比較好」目前只標 `bloody-mary` 為正解，
但 `corpse-reviver-2` 的正文明確寫著「解宿醉用的晨間酒」，
它是合理答案卻被算成錯誤。

**這是 ground truth 標錯，不是檢索失敗。** 正好示範了為什麼合成
eval set 的第 4 步（人工抽審）不能省——LLM 出題時只看一個 chunk，
不知道別篇也能回答。下一輪要把 q044 的正解補成兩篇。

---

## 下一步

1. 接 dense embedding（bge-m3 或 text-embedding-3-small），重跑同一份評估集
2. 預期 colloquial 大幅改善、factual 可能略降——如果 factual 掉很多，代表索引文字或模型選錯
3. dense 上線後 hard negative 叢集才會真正變難，屆時再加 rerank 與 metadata filter
4. 修 q044 的 ground truth
