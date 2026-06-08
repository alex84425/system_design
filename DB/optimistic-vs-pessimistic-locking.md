# 樂觀鎖 vs 悲觀鎖 (Optimistic vs Pessimistic Locking)

## 一句話區分

| | 核心假設 | 做法 |
|---|---|---|
| **悲觀鎖 (Pessimistic)** | 「一定會有人跟我搶」 | **先鎖再改** — 操作前就把資料鎖住,別人要等 |
| **樂觀鎖 (Optimistic)** | 「應該沒人跟我搶」 | **先改再驗** — 不鎖,提交時才檢查有沒有被別人改過 |

---

## 1. 悲觀鎖 (Pessimistic Locking)

**先把門鎖起來,我做完你才能進來。** 靠資料庫鎖機制 (`SELECT ... FOR UPDATE`)。

```sql
BEGIN;
-- 鎖住這筆,其他交易的 FOR UPDATE 會被擋住等待
SELECT stock FROM products WHERE id = 100 FOR UPDATE;
-- 檢查庫存
UPDATE products SET stock = stock - 1 WHERE id = 100;
COMMIT;  -- 鎖在這裡釋放
```

```
交易A: ──FOR UPDATE(鎖)──改──COMMIT(放鎖)──┐
交易B:        └─────等待 blocked─────────────┴─FOR UPDATE──改──COMMIT
```

- ✅ 簡單、不會有衝突後重試問題、強一致
- ❌ 會阻塞、吞吐量低、容易**死鎖**、鎖久了拖垮效能

---

## 2. 樂觀鎖 (Optimistic Locking)

**不鎖,大家都改,但提交時驗一下「我讀到之後有沒有人動過」。**
實作:加一個 `version` 欄位(或用 timestamp / 比對舊值)。

```sql
-- 1. 讀出來,記住 version
SELECT stock, version FROM products WHERE id = 100;
-- 假設 stock=10, version=5

-- 2. 更新時帶上「我讀到的 version」當條件
UPDATE products
SET stock = stock - 1, version = version + 1
WHERE id = 100 AND version = 5;   -- ← 關鍵

-- 3. 看 affected rows
--    = 1 → 成功
--    = 0 → 有人在我之前改了(version 已變),衝突 → 重試或報錯
```

```
交易A: 讀 v=5 ──改──UPDATE WHERE v=5 ✅ (v變6)
交易B: 讀 v=5 ──改──UPDATE WHERE v=5 ❌ 0 rows (已是v6) → 重試:重讀 v=6 再來
```

- ✅ 不阻塞、吞吐量高、無死鎖
- ❌ 衝突高時**一直重試**很浪費、要自己寫重試邏輯

---

## 3. 使用場景對照

| 情境 | 選哪個 | 為什麼 |
|------|--------|--------|
| **讀多寫少**、衝突機率低 | 🟢 樂觀鎖 | 大部分時候沒衝突,不鎖最快 |
| **寫多、高併發搶同一筆**(秒殺、熱門商品扣庫存) | 🔴 視情況 | 衝突太多 → 樂觀鎖一直重試反而慘;常改用 **Redis 預扣 / 排隊** |
| **金額轉帳、扣款** 要求強一致 | 🔴 悲觀鎖 | 不能容忍「重試中讀到中間值」,鎖住最穩 |
| **長交易**(讀完使用者慢慢填表單再提交) | 🟢 樂觀鎖 | 不可能鎖住資料庫等使用者幾分鐘 |
| **批次更新、報表** | 🔴 悲觀鎖 | 要保證過程中資料不被動 |

---

## 4. 電商扣庫存的實務選擇

```
低/中併發  → 樂觀鎖 (version 欄位)，衝突少，簡單夠用
            UPDATE ... SET stock=stock-1 WHERE id=? AND stock>=1
            (這招本身就是樂觀:用 stock>=1 當條件,0 rows 就是賣完)

超高併發(秒殺) → 不直接打 DB:
            Redis 預扣庫存 (decr) → 扛住流量
            → MQ 削峰 → 非同步落庫 → DB 對帳
```

> `UPDATE products SET stock=stock-1 WHERE id=? AND stock>0` 是最常用、最簡單的
> **樂觀鎖防超賣**寫法 —— 不需要 version 欄位,用業務欄位 (`stock>0`) 當 CAS 條件,
> affected rows = 0 就代表賣完了。

---

## 5. 一句話總結

> **衝突少 → 樂觀鎖**(不鎖、提交時驗 version,失敗就重試)。
> **衝突多 / 要求強一致 → 悲觀鎖**(`FOR UPDATE` 先鎖,別人等)。
> 高併發秒殺則跳過 DB 鎖,改用 **Redis 預扣 + MQ 削峰**。

延伸:[[keyword]](下訂單失敗 / Saga / 庫存設計)
